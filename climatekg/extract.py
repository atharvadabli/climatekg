from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import PIPELINE, ROOT
from .extraction_models import ClaimBatch, FacetBatch, MapContext, MapTransition, PaperMap, SectionScout
from .location_extraction import enforce_copied_location_names
from .models import Claim, Context, Facet, Paper, SourceBlock, Transition
from .ollama import OllamaClient
from .retrieval import bm25, exact_alias_hit, semantic
from .utils import normalize_text_key, token_count, unique_in_order, write_json


@dataclass(frozen=True)
class ClaimExtractionTask:
    task_id: str
    scope_id: str
    scope_type: str
    result_focus: str
    queries: list[str]
    mandatory_block_ids: list[str]
    available_facets: list[Facet]


def _prompt(name: str) -> str:
    return (ROOT / "prompts" / name).read_text(encoding="utf-8")


def _render_blocks(blocks: list[SourceBlock]) -> str:
    return "\n\n".join(f"[{block.id}] page={block.page} section={' > '.join(block.section_path)} type={block.block_type}\n{block.text}" for block in blocks)


def _split_prompt(template: str) -> tuple[str, str]:
    system, user = template.split("USER\n", 1)
    return system.removeprefix("SYSTEM\n").strip(), user.strip()


def scout_setting_inventory(scouts: list[SectionScout]) -> list[dict[str, Any]]:
    """Build stable IDs for unique setting names copied by section scouts."""
    inventory: dict[str, dict[str, Any]] = {}
    for scout in scouts:
        for mention in scout.context_mentions:
            key = normalize_text_key(mention.name)
            if not key:
                continue
            if key not in inventory:
                inventory[key] = {
                    "name": mention.name,
                    "descriptions": [mention.description],
                    "block_ids": list(mention.block_ids),
                }
            else:
                inventory[key]["descriptions"] = unique_in_order([*inventory[key]["descriptions"], mention.description])
                inventory[key]["block_ids"] = unique_in_order([*inventory[key]["block_ids"], *mention.block_ids])
    return [
        {"mention_id": f"CM{index:03d}", **item}
        for index, item in enumerate(inventory.values(), 1)
    ]


def render_scout_notes(scouts: list[SectionScout]) -> str:
    """Render only map-relevant scout notes in a compact readable form."""
    lines = ["SETTING INVENTORY"]
    for item in scout_setting_inventory(scouts):
        lines.append(
            f"[{item['mention_id']}] {item['name']}: {' | '.join(item['descriptions'])} "
            f"[blocks: {', '.join(item['block_ids'])}]"
        )
    lines.append("")
    fields = (
        ("POSSIBLE LOCATIONS", "location_mentions"),
        ("POSSIBLE COMPARISONS", "comparison_mentions"),
    )
    for index, scout in enumerate(scouts, 1):
        lines.append(f"SECTION NOTE {index}")
        for heading, field in fields:
            mentions = getattr(scout, field)
            if not mentions:
                continue
            lines.append(heading)
            for mention in mentions:
                lines.append(f"- {mention.name}: {mention.description} [blocks: {', '.join(mention.block_ids)}]")
        if scout.facet_seed_block_ids:
            lines.append(f"SETTING-DETAIL BLOCKS: {', '.join(scout.facet_seed_block_ids)}")
        if scout.claim_seed_block_ids:
            lines.append(f"RESULT BLOCKS: {', '.join(scout.claim_seed_block_ids)}")
        if scout.ambiguities:
            lines.append("UNRESOLVED NOTES: " + " | ".join(scout.ambiguities))
        lines.append("")
    return "\n".join(lines).strip()


def validate_context_mention_resolution(mapped: PaperMap, inventory: list[dict[str, Any]]) -> None:
    expected = {item["mention_id"] for item in inventory}
    actual = set(mapped.context_mention_resolution)
    if actual != expected:
        raise ValueError(
            f"paper map setting inventory mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    context_ids = {context.temp_id for context in mapped.contexts}
    targets = list(mapped.context_mention_resolution.values())
    if any(target not in context_ids for target in targets):
        raise ValueError("paper map setting inventory refers to an unknown Context")


def validate_result_scope_coverage(mapped: PaperMap, required_block_ids: set[str]) -> None:
    """Require every scouted result passage to reach a focused Claim task."""
    covered = {
        block_id
        for scope in mapped.result_scopes
        for block_id in scope.claim_seed_block_ids
    }
    missing = required_block_ids - covered
    if missing:
        raise ValueError(f"paper map omitted scouted result blocks: {sorted(missing)}")


def remove_internal_inventory_aliases(mapped: PaperMap) -> PaperMap:
    """Keep temporary CM identifiers out of paper-local scientific aliases."""
    contexts = []
    for context in mapped.contexts:
        aliases = [
            alias
            for alias in context.aliases
            if not (len(alias) == 5 and alias.startswith("CM") and alias[2:].isdigit())
        ]
        contexts.append(context.model_copy(update={"aliases": aliases}))
    return mapped.model_copy(update={"contexts": contexts})


def select_map_consolidation_blocks(
    blocks: list[SourceBlock], scouts: list[SectionScout], budget_tokens: int
) -> tuple[list[SourceBlock], dict[str, Any]]:
    """Select compact structural evidence without rescanning on broad keywords."""
    by_id = {block.id: block for block in blocks}
    first_mention_blocks: list[str] = []
    additional_mention_blocks: list[str] = []
    facet_seed_blocks: list[str] = []
    claim_seed_blocks: list[str] = []

    for scout in scouts:
        for field in ("context_mentions", "comparison_mentions", "location_mentions"):
            for mention in getattr(scout, field):
                valid_ids = [block_id for block_id in mention.block_ids if block_id in by_id]
                if valid_ids:
                    first_mention_blocks.append(valid_ids[0])
                    additional_mention_blocks.extend(valid_ids[1:])
        facet_seed_blocks.extend(scout.facet_seed_block_ids)
        claim_seed_blocks.extend(scout.claim_seed_block_ids)

    overview_blocks = [block.id for block in blocks if block.block_type in ("title", "abstract")]
    priority_groups = (
        ("first_mention", first_mention_blocks),
        ("overview", overview_blocks),
        ("claim_seed", claim_seed_blocks),
        ("additional_mention", additional_mention_blocks),
        ("facet_seed", facet_seed_blocks),
    )
    selected_ids: list[str] = []
    selected_set: set[str] = set()
    dropped: dict[str, list[str]] = defaultdict(list)
    estimated_tokens = 0
    for reason, candidate_ids in priority_groups:
        for block_id in unique_in_order(candidate_ids):
            if block_id in selected_set or block_id not in by_id:
                continue
            block_tokens = token_count(_render_blocks([by_id[block_id]]))
            if estimated_tokens + block_tokens > budget_tokens:
                dropped[reason].append(block_id)
                continue
            selected_ids.append(block_id)
            selected_set.add(block_id)
            estimated_tokens += block_tokens

    selected = sorted((by_id[block_id] for block_id in selected_ids), key=lambda block: block.order)
    report = {
        "source_budget_tokens": budget_tokens,
        "estimated_source_tokens": estimated_tokens,
        "selected_block_count": len(selected),
        "selected_block_ids": [block.id for block in selected],
        "dropped_block_ids_by_reason": dict(dropped),
    }
    return selected, report


def render_paper_map_tree(mapped: PaperMap) -> str:
    """Render a compact review artifact from the structured paper map."""
    by_id = {context.temp_id: context for context in mapped.contexts}
    children: dict[str, list[str]] = defaultdict(list)
    roots: list[str] = []
    for context in mapped.contexts:
        if context.parent_temp_ids:
            for parent_id in context.parent_temp_ids:
                children[parent_id].append(context.temp_id)
        else:
            roots.append(context.temp_id)

    lines = ["STUDY SETTING TREE"]
    rendered: set[str] = set()

    def visit(context_id: str, depth: int) -> None:
        context = by_id[context_id]
        aliases = f"; aliases: {', '.join(context.aliases)}" if context.aliases else ""
        repeated = "; also inherits elsewhere" if context_id in rendered else ""
        lines.append(f"{'  ' * depth}- {context.label} [{context.temp_id}]{aliases}{repeated}")
        if context_id in rendered:
            return
        rendered.add(context_id)
        for child_id in children.get(context_id, []):
            visit(child_id, depth + 1)

    for root_id in roots:
        visit(root_id, 0)
    for context in mapped.contexts:
        if context.temp_id not in rendered:
            visit(context.temp_id, 0)

    lines.append("")
    lines.append("STUDIED COMPARISONS")
    for transition in mapped.transitions:
        left = by_id[transition.from_context_temp_id].label
        right = by_id[transition.to_context_temp_id].label
        lines.append(f"- {left} -> {right}: {transition.label} [{transition.temp_id}]")
    return "\n".join(lines) + "\n"


def group_sections(blocks: list[SourceBlock]) -> list[list[SourceBlock]]:
    cfg = PIPELINE["section_scout"]
    initial: list[list[SourceBlock]] = []
    for block in blocks:
        key = tuple(block.section_path[:2])
        if initial and tuple(initial[-1][0].section_path[:2]) == key:
            initial[-1].append(block)
        else:
            initial.append([block])
    packed: list[list[SourceBlock]] = []
    for group in initial:
        if sum(token_count(x.text) for x in group) <= cfg["max_tokens"]:
            packed.append(group)
            continue
        current: list[SourceBlock] = []
        count = 0
        for block in group:
            size = token_count(block.text)
            if current and count + size > cfg["target_tokens"]:
                packed.append(current)
                current, count = [], 0
            current.append(block)
            count += size
        if current:
            packed.append(current)
    merged: list[list[SourceBlock]] = []
    for group in packed:
        size = sum(token_count(x.text) for x in group)
        previous_parent = tuple(merged[-1][0].section_path[:-1]) if merged else ()
        current_parent = tuple(group[0].section_path[:-1])
        if merged and size < cfg["min_tokens"] and previous_parent == current_parent and size + sum(token_count(x.text) for x in merged[-1]) <= cfg["max_tokens"]:
            merged[-1].extend(group)
        else:
            merged.append(group)
    return merged


def _validate_map(result: PaperMap, block_ids: set[str]) -> None:
    context_ids = [x.temp_id for x in result.contexts]
    transition_ids = [x.temp_id for x in result.transitions]
    result_scope_ids = [x.temp_id for x in result.result_scopes]
    contexts = set(context_ids)
    if not contexts:
        raise ValueError("paper map contains no Context")
    if len(context_ids) != len(contexts):
        raise ValueError("paper map contains duplicate Context IDs")
    if len(transition_ids) != len(set(transition_ids)):
        raise ValueError("paper map contains duplicate Transition IDs")
    if len(result_scope_ids) != len(set(result_scope_ids)):
        raise ValueError("paper map contains duplicate result-scope IDs")
    for context in result.contexts:
        if bool(context.parent_temp_ids) != bool(context.split_reason):
            raise ValueError(f"paper-map Context has inconsistent parent/split_reason: {context.temp_id}")
        if not context.evidence_block_ids:
            raise ValueError(f"paper-map Context has no evidence: {context.temp_id}")
        if any(x not in contexts for x in context.parent_temp_ids) or any(x not in block_ids for x in context.evidence_block_ids + context.facet_seed_block_ids):
            raise ValueError(f"invalid paper-map Context references: {context.temp_id}")
    unresolved = set(contexts)
    resolved: set[str] = set()
    while unresolved:
        ready = {context.temp_id for context in result.contexts if context.temp_id in unresolved and set(context.parent_temp_ids) <= resolved}
        if not ready:
            raise ValueError("paper-map Context hierarchy contains a cycle")
        resolved.update(ready)
        unresolved.difference_update(ready)
    for transition in result.transitions:
        if transition.from_context_temp_id not in contexts or transition.to_context_temp_id not in contexts:
            raise ValueError(f"invalid paper-map Transition scope: {transition.temp_id}")
        if any(x not in block_ids for x in transition.evidence_block_ids + transition.claim_seed_block_ids):
            raise ValueError(f"invalid paper-map evidence: {transition.temp_id}")
        if transition.from_context_temp_id == transition.to_context_temp_id:
            raise ValueError(f"Transition has identical FROM/TO Context: {transition.temp_id}")
    transitions = set(transition_ids)
    for scope in result.result_scopes:
        valid_targets = contexts if scope.scope_type == "context" else transitions
        if scope.scope_temp_id not in valid_targets:
            raise ValueError(f"invalid result-scope target: {scope.temp_id}")
        if not scope.claim_seed_block_ids or any(x not in block_ids for x in scope.claim_seed_block_ids):
            raise ValueError(f"invalid result-scope evidence: {scope.temp_id}")


def _validate_map_references(result: PaperMap, block_ids: set[str]) -> None:
    contexts = {item.temp_id for item in result.contexts}
    for context in result.contexts:
        if any(parent_id not in contexts for parent_id in context.parent_temp_ids):
            raise ValueError(f"invalid paper-map Context hierarchy: {context.temp_id}")
        if any(block_id not in block_ids for block_id in context.evidence_block_ids + context.facet_seed_block_ids + context.claim_seed_block_ids):
            raise ValueError(f"invalid paper-map Context evidence: {context.temp_id}")
    for transition in result.transitions:
        if transition.from_context_temp_id not in contexts or transition.to_context_temp_id not in contexts:
            raise ValueError(f"invalid paper-map Transition scope: {transition.temp_id}")
        if any(block_id not in block_ids for block_id in transition.evidence_block_ids + transition.claim_seed_block_ids):
            raise ValueError(f"invalid paper-map Transition evidence: {transition.temp_id}")
    if any(block_id not in block_ids for context in result.contexts for block_id in context.claim_seed_block_ids):
        raise ValueError("invalid paper-map Context Claim seed evidence")
    if any(block_id not in block_ids for block_id in result.global_claim_seed_block_ids):
        raise ValueError("invalid paper-map global Claim seed evidence")
    if any(block_id not in block_ids for scope in result.result_scopes for block_id in scope.claim_seed_block_ids):
        raise ValueError("invalid paper-map result-scope evidence")


def _validate_reference_only_repair(original: PaperMap, repaired: PaperMap, block_ids: set[str]) -> None:
    _validate_map_references(repaired, block_ids)
    if original.ambiguities != repaired.ambiguities:
        raise ValueError("reference repair changed ambiguities")
    original_contexts = {item.temp_id: item for item in original.contexts}
    repaired_contexts = {item.temp_id: item for item in repaired.contexts}
    if set(original_contexts) != set(repaired_contexts):
        raise ValueError("reference repair changed Context IDs")
    for item_id, item in original_contexts.items():
        expected = item.model_copy(update={"evidence_block_ids": repaired_contexts[item_id].evidence_block_ids, "facet_seed_block_ids": repaired_contexts[item_id].facet_seed_block_ids, "claim_seed_block_ids": repaired_contexts[item_id].claim_seed_block_ids})
        if expected != repaired_contexts[item_id]:
            raise ValueError(f"reference repair changed Context semantics: {item_id}")
    original_transitions = {item.temp_id: item for item in original.transitions}
    repaired_transitions = {item.temp_id: item for item in repaired.transitions}
    if set(original_transitions) != set(repaired_transitions):
        raise ValueError("reference repair changed Transition IDs")
    for item_id, item in original_transitions.items():
        expected = item.model_copy(update={"evidence_block_ids": repaired_transitions[item_id].evidence_block_ids, "claim_seed_block_ids": repaired_transitions[item_id].claim_seed_block_ids})
        if expected != repaired_transitions[item_id]:
            raise ValueError(f"reference repair changed Transition semantics: {item_id}")
    original_scopes = {item.temp_id: item for item in original.result_scopes}
    repaired_scopes = {item.temp_id: item for item in repaired.result_scopes}
    if set(original_scopes) != set(repaired_scopes):
        raise ValueError("reference repair changed result-scope IDs")
    for item_id, item in original_scopes.items():
        expected = item.model_copy(update={"claim_seed_block_ids": repaired_scopes[item_id].claim_seed_block_ids})
        if expected != repaired_scopes[item_id]:
            raise ValueError(f"reference repair changed result-scope semantics: {item_id}")


def _validate_map_repair(original: PaperMap, repaired: PaperMap, block_ids: set[str]) -> None:
    _validate_map(repaired, block_ids)
    repaired_contexts = {item.temp_id: item for item in repaired.contexts}
    for context in original.contexts:
        if context.temp_id not in repaired_contexts or repaired_contexts[context.temp_id] != context:
            raise ValueError(f"repair changed immutable Context: {context.temp_id}")
    repaired_transitions = {item.temp_id: item for item in repaired.transitions}
    for transition in original.transitions:
        if transition.from_context_temp_id == transition.to_context_temp_id:
            continue
        if repaired_transitions.get(transition.temp_id) != transition:
            raise ValueError(f"repair changed immutable valid Transition: {transition.temp_id}")


def _apply_map_repair(original: PaperMap, proposed: PaperMap, block_ids: set[str]) -> PaperMap:
    """Apply only the additive endpoint changes allowed by map repair."""
    original_contexts = {item.temp_id: item for item in original.contexts}
    proposed_contexts = {item.temp_id: item for item in proposed.contexts}
    proposed_transitions = {item.temp_id: item for item in proposed.transitions}
    added: dict[str, MapContext] = {}
    transitions: list[MapTransition] = []
    for transition in original.transitions:
        if transition.from_context_temp_id != transition.to_context_temp_id:
            transitions.append(transition)
            continue
        replacement = proposed_transitions.get(transition.temp_id)
        if replacement is None or replacement.from_context_temp_id == replacement.to_context_temp_id:
            raise ValueError(f"repair did not replace invalid Transition: {transition.temp_id}")
        anchor_id = transition.from_context_temp_id
        endpoints = (replacement.from_context_temp_id, replacement.to_context_temp_id)
        for endpoint_id in endpoints:
            if endpoint_id in original_contexts:
                continue
            candidate = proposed_contexts.get(endpoint_id)
            if candidate is None:
                raise ValueError(f"repair endpoint Context is missing: {endpoint_id}")
            endpoint_evidence = candidate.evidence_block_ids or transition.evidence_block_ids
            endpoint_facet_seeds = candidate.facet_seed_block_ids or endpoint_evidence
            added[endpoint_id] = candidate.model_copy(update={"parent_temp_ids": [anchor_id], "split_reason": "explicit_transition_state", "evidence_block_ids": endpoint_evidence, "facet_seed_block_ids": endpoint_facet_seeds})
        transitions.append(transition.model_copy(update={"from_context_temp_id": endpoints[0], "to_context_temp_id": endpoints[1]}))
    repaired = PaperMap(
        contexts=[*original.contexts, *added.values()],
        transitions=transitions,
        result_scopes=original.result_scopes,
        context_mention_resolution=original.context_mention_resolution,
        global_claim_seed_block_ids=original.global_claim_seed_block_ids,
        ambiguities=unique_in_order([*original.ambiguities, *proposed.ambiguities]),
    )
    _validate_map(repaired, block_ids)
    return repaired


def _apply_missing_context_evidence_repair(original: PaperMap, proposed: PaperMap, block_ids: set[str]) -> PaperMap:
    """Apply evidence IDs only to Contexts whose original evidence list was empty."""
    proposed_contexts = {item.temp_id: item for item in proposed.contexts}
    repaired_contexts: list[MapContext] = []
    for context in original.contexts:
        candidate = proposed_contexts.get(context.temp_id)
        if candidate is None:
            raise ValueError(f"evidence repair omitted Context: {context.temp_id}")
        if context.evidence_block_ids:
            if candidate != context:
                raise ValueError(f"evidence repair changed immutable Context: {context.temp_id}")
            repaired_contexts.append(context)
            continue
        expected = context.model_copy(update={"evidence_block_ids": candidate.evidence_block_ids})
        if candidate != expected:
            raise ValueError(f"evidence repair changed Context semantics: {context.temp_id}")
        repaired_contexts.append(expected)
    repaired = original.model_copy(update={"contexts": repaired_contexts})
    _validate_map(repaired, block_ids)
    return repaired


def map_paper(paper: Paper, blocks: list[SourceBlock], paper_dir: Path, client: OllamaClient) -> PaperMap:
    cfg = PIPELINE
    cached_path = paper_dir / "extraction" / "map" / "paper_map.json"
    if cached_path.exists():
        cached = PaperMap.model_validate_json(cached_path.read_text(encoding="utf-8"))
        _validate_map(cached, {x.id for x in blocks})
        tree_path = paper_dir / "extraction" / "map" / "paper_map.tree.txt"
        if not tree_path.exists():
            tree_path.write_text(render_paper_map_tree(cached), encoding="utf-8")
        return cached
    candidate_path = paper_dir / "extraction" / "map" / "paper_map.candidate.json"
    useful = [x for x in blocks if x.block_type != "reference"]
    system, user_template = _split_prompt(_prompt("paper_map.txt"))
    stage_cfg = cfg["ollama"]["stages"]["paper_map"]
    if sum(token_count(x.text) for x in useful) <= cfg["paper_mapping"]["whole_paper_threshold_tokens"]:
        repair_system = system
        repair_base_user = user_template.format(paper_id=paper.id, paper_text=_render_blocks(useful))
        if candidate_path.exists():
            result = PaperMap.model_validate_json(candidate_path.read_text(encoding="utf-8"))
        else:
            result = client.structured(stage="paper_map", system=system, user=repair_base_user, schema=PaperMap, model=cfg["ollama"]["model"], temperature=stage_cfg["temperature"], thinking=stage_cfg["thinking"], artifact_dir=paper_dir / "extraction" / "map", paper_id=paper.id, input_block_ids=[x.id for x in useful], retries=stage_cfg["retries"])
    else:
        scout_system, scout_user = _split_prompt(_prompt("section_scout.txt"))
        scout_cfg = cfg["ollama"]["stages"]["section_scout"]
        scouts = []
        for index, group in enumerate(group_sections(useful)):
            scout = client.structured(stage="section_scout", system=scout_system, user=scout_user.format(paper_id=paper.id, section_path=" > ".join(group[0].section_path), section_blocks=_render_blocks(group)), schema=SectionScout, model=cfg["ollama"]["model"], temperature=scout_cfg["temperature"], thinking=scout_cfg["thinking"], artifact_dir=paper_dir / "extraction" / "map" / "scouts", paper_id=paper.id, input_block_ids=[x.id for x in group], retries=scout_cfg["retries"])
            scouts.append(scout)
            write_json(paper_dir / "extraction" / "map" / "scouts" / f"scout_{index:03d}.validated.json", scout.model_dump(by_alias=True))
        selected, selection_report = select_map_consolidation_blocks(
            useful,
            scouts,
            cfg["paper_mapping"]["map_consolidation_source_budget_tokens"],
        )
        write_json(paper_dir / "extraction" / "map" / "map_input_report.json", selection_report)
        setting_inventory = scout_setting_inventory(scouts)
        consolidation_system, consolidation_user = _split_prompt(_prompt("map_consolidation.txt"))
        repair_system = consolidation_system
        repair_base_user = consolidation_user.format(
            paper_metadata=paper.model_dump_json(),
            scout_outputs=render_scout_notes(scouts),
            required_result_block_ids=json.dumps(sorted({block_id for scout in scouts for block_id in scout.claim_seed_block_ids})),
            selected_blocks=_render_blocks(selected),
        )
        consolidation_cfg = cfg["ollama"]["stages"]["map_consolidation"]
        result = client.structured(stage="map_consolidation", system=consolidation_system, user=repair_base_user, schema=PaperMap, model=cfg["ollama"]["model"], temperature=consolidation_cfg["temperature"], thinking=consolidation_cfg["thinking"], artifact_dir=paper_dir / "extraction" / "map", paper_id=paper.id, input_block_ids=[x.id for x in selected], retries=consolidation_cfg["retries"])
        result = remove_internal_inventory_aliases(result)
        validate_context_mention_resolution(result, setting_inventory)
        validate_result_scope_coverage(
            result,
            {
                block_id
                for scout in scouts
                for block_id in scout.claim_seed_block_ids
            },
        )
    write_json(candidate_path, result.model_dump(by_alias=True))
    block_ids = {x.id for x in blocks}
    try:
        _validate_map_references(result, block_ids)
    except ValueError as exc:
        reference_path = paper_dir / "extraction" / "map" / "paper_map.reference_repaired.json"
        if reference_path.exists():
            reference_repaired = PaperMap.model_validate_json(reference_path.read_text(encoding="utf-8"))
        else:
            invalid_ids = sorted({block_id for context in result.contexts for block_id in context.evidence_block_ids + context.facet_seed_block_ids + context.claim_seed_block_ids if block_id not in block_ids} | {block_id for transition in result.transitions for block_id in transition.evidence_block_ids + transition.claim_seed_block_ids if block_id not in block_ids} | {block_id for scope in result.result_scopes for block_id in scope.claim_seed_block_ids if block_id not in block_ids} | {block_id for block_id in result.global_claim_seed_block_ids if block_id not in block_ids})
            unique_matches = {invalid_id: matches[0] for invalid_id in invalid_ids if len(matches := sorted(block_id for block_id in block_ids if block_id.endswith(f":{invalid_id}"))) == 1}
            reference_user = (
                "TASK\n\nCorrect invalid SourceBlock IDs in one previously generated study-setting map. "
                "Return the complete corrected JSON object in the supplied schema.\n\n"
                f"PAPER METADATA\n{paper.model_dump_json()}\n\n"
                f"PREVIOUS JSON OBJECT\n{result.model_dump_json(by_alias=True)}\n\n"
                f"VALIDATION ERROR\n{exc}\n\n"
                f"INVALID IDS\n{json.dumps(invalid_ids)}\n\n"
                f"UNAMBIGUOUS FULL-ID MATCHES\n{json.dumps(unique_matches)}\n\n"
                f"COMPLETE ALLOWED SOURCEBLOCK IDS\n{json.dumps(sorted(block_ids))}\n\n"
                "Copy every scientific field and structural decision from the previous object. Replace values only in "
                "evidence_block_ids, facet_seed_block_ids, claim_seed_block_ids, and global_claim_seed_block_ids, "
                "using exact IDs from the allowed list. Result-scope scientific focus and target fields must remain unchanged."
            )
            repair_cfg = cfg["ollama"]["stages"]["paper_map_reference_id_repair"]
            reference_repaired = client.structured(stage="paper_map_reference_id_repair", system=repair_system, user=reference_user, schema=PaperMap, model=cfg["ollama"]["model"], temperature=repair_cfg["temperature"], thinking=repair_cfg["thinking"], artifact_dir=paper_dir / "extraction" / "map" / "reference_id_repair", paper_id=paper.id, input_block_ids=[x.id for x in blocks], retries=repair_cfg["retries"])
            write_json(reference_path, reference_repaired.model_dump(by_alias=True))
        try:
            _validate_reference_only_repair(result, reference_repaired, block_ids)
        except ValueError as repair_exc:
            raise ValueError(f"FAILED_REFERENCE_VALIDATION: {repair_exc}") from repair_exc
        result = reference_repaired
    missing_contexts = [context for context in result.contexts if not context.evidence_block_ids]
    if missing_contexts:
        missing_ids = {context.temp_id for context in missing_contexts}
        related_ids = {
            block_id
            for context in result.contexts
            if context.temp_id in missing_ids
            or any(parent_id in missing_ids for parent_id in context.parent_temp_ids)
            or any(child.parent_temp_ids and context.temp_id in child.parent_temp_ids for child in missing_contexts)
            for block_id in context.evidence_block_ids
        }
        queries = [
            *(context.label for context in missing_contexts),
            "passages that establish the named study setting, baseline condition, forcing, period, treatment, or simulation case",
        ]
        repair_blocks = evidence_bundle(blocks, queries, [], sorted(related_ids), client)
        evidence_repair_user = (
            "TASK\n\nAdd directly supporting evidence passage IDs to study-setting records whose evidence list is empty. "
            "Return the complete JSON object in the supplied schema.\n\n"
            "INPUT\n\nYou will receive a previously generated study-setting map, the IDs of records with no evidence, "
            "a list of allowed passage IDs, and selected original passages.\n\n"
            f"PREVIOUS JSON OBJECT\n{result.model_dump_json(by_alias=True)}\n\n"
            f"RECORDS WITH MISSING EVIDENCE\n{json.dumps(sorted(missing_ids))}\n\n"
            f"ALLOWED SOURCEBLOCK IDS\n{json.dumps(sorted(block_ids))}\n\n"
            f"SELECTED ORIGINAL PASSAGES\n{_render_blocks(repair_blocks)}\n\n"
            "OUTPUT\n\nCopy every record and every field exactly. For each listed record only, fill `evidence_block_ids` "
            "with the smallest set of allowed SourceBlock IDs that directly establishes that named setting. "
            "Do not change labels, hierarchy, comparisons, result scopes, or any other evidence lists. "
            "Return valid JSON only, with no Markdown or commentary."
        )
        evidence_repair_path = paper_dir / "extraction" / "map" / "paper_map.evidence_repair_candidate.json"
        if evidence_repair_path.exists():
            evidence_repaired = PaperMap.model_validate_json(evidence_repair_path.read_text(encoding="utf-8"))
        else:
            repair_cfg = cfg["ollama"]["stages"]["paper_map_reference_repair"]
            evidence_repaired = client.structured(
                stage="paper_map_context_evidence_repair",
                system=repair_system,
                user=evidence_repair_user,
                schema=PaperMap,
                model=cfg["ollama"]["model"],
                temperature=repair_cfg["temperature"],
                thinking=repair_cfg["thinking"],
                artifact_dir=paper_dir / "extraction" / "map" / "context_evidence_repair",
                paper_id=paper.id,
                input_block_ids=[block.id for block in repair_blocks],
                retries=repair_cfg["retries"],
            )
            write_json(evidence_repair_path, evidence_repaired.model_dump(by_alias=True))
        result = _apply_missing_context_evidence_repair(result, evidence_repaired, block_ids)
    try:
        _validate_map(result, block_ids)
    except ValueError as exc:
        # Referential validation has its own bounded repair step. The model is
        # given the complete allowed registries and may repair IDs/structure,
        # but may not introduce scientific information.
        context_by_temp = {item.temp_id: item for item in result.contexts}
        invalid_transitions = [item for item in result.transitions if item.from_context_temp_id == item.to_context_temp_id]
        repair_ids = {block_id for item in invalid_transitions for block_id in item.evidence_block_ids + item.claim_seed_block_ids}
        for transition in invalid_transitions:
            repair_ids.update(context_by_temp[transition.from_context_temp_id].evidence_block_ids)
        repair_orders = {block.order for block in blocks if block.id in repair_ids}
        repair_orders.update(order + delta for order in list(repair_orders) for delta in (-1, 1))
        repair_blocks = [block for block in useful if block.order in repair_orders or block.block_type in ("title", "abstract")]
        repair_user = (
            "TASK\n\nCorrect comparisons in a previously generated study-setting map when a comparison incorrectly uses the same setting as both its start and end. Return the complete corrected JSON object.\n\n"
            + f"PAPER METADATA\n{paper.model_dump_json()}\n\n"
            + f"PREVIOUS JSON OBJECT\n{result.model_dump_json(by_alias=True)}\n\n"
            + f"VALIDATION ERROR\n{exc}\n\n"
            + f"ALLOWED SOURCEBLOCK IDS\n{json.dumps([x.id for x in blocks])}\n\n"
            + f"EVIDENCE FOR THE INVALID COMPARISONS\n{_render_blocks(repair_blocks)}\n\n"
            + "Copy every existing study-setting record exactly. Copy every already-valid comparison exactly. For each invalid comparison, identify two distinct evidence-supported start and end settings. Add only the minimum child settings required to represent those endpoints. Use only supplied evidence and allowed IDs."
        )
        original = result
        repair_candidate_path = paper_dir / "extraction" / "map" / "paper_map.repair_candidate.json"
        if repair_candidate_path.exists():
            proposed = PaperMap.model_validate_json(repair_candidate_path.read_text(encoding="utf-8"))
        else:
            repair_cfg = cfg["ollama"]["stages"]["paper_map_reference_repair"]
            proposed = client.structured(stage="paper_map_reference_repair", system=repair_system, user=repair_user, schema=PaperMap, model=cfg["ollama"]["model"], temperature=repair_cfg["temperature"], thinking=repair_cfg["thinking"], artifact_dir=paper_dir / "extraction" / "map", paper_id=paper.id, input_block_ids=[x.id for x in repair_blocks], retries=repair_cfg["retries"])
            write_json(repair_candidate_path, proposed.model_dump(by_alias=True))
        try:
            result = _apply_map_repair(original, proposed, block_ids)
        except ValueError as repair_exc:
            second_repair = (
                repair_user
                + f"\n\nSECOND CORRECTION\n\nThe proposed correction failed validation:\n{repair_exc}\n\n"
                + f"REJECTED CORRECTION\n{proposed.model_dump_json(by_alias=True)}\n\n"
                + "Return the complete JSON object again. Copy every original study-setting record exactly. Correct only comparisons whose start and end IDs are identical, adding the minimum evidence-supported child settings required for distinct endpoints."
            )
            repair_cfg = cfg["ollama"]["stages"]["paper_map_reference_repair"]
            proposed = client.structured(stage="paper_map_reference_repair", system=repair_system, user=second_repair, schema=PaperMap, model=cfg["ollama"]["model"], temperature=repair_cfg["temperature"], thinking=repair_cfg["thinking"], artifact_dir=paper_dir / "extraction" / "map", paper_id=paper.id, input_block_ids=[x.id for x in repair_blocks], retries=cfg["ollama"]["final_repair_retries"])
            write_json(repair_candidate_path, proposed.model_dump(by_alias=True))
            result = _apply_map_repair(original, proposed, block_ids)
    result = enforce_copied_location_names(result, (block.text for block in blocks))
    write_json(paper_dir / "extraction" / "map" / "paper_map.json", result.model_dump(by_alias=True))
    (paper_dir / "extraction" / "map" / "paper_map.tree.txt").write_text(render_paper_map_tree(result), encoding="utf-8")
    return result


def permanent_map(paper: Paper, mapped: PaperMap) -> tuple[list[Context], list[Transition], dict[str, Any]]:
    pending = list(mapped.contexts)
    ordered = []
    done: set[str] = set()
    while pending:
        available = [x for x in pending if set(x.parent_temp_ids) <= done]
        if not available:
            raise ValueError("Context hierarchy cycle")
        for item in available:
            ordered.append(item)
            done.add(item.temp_id)
            pending.remove(item)
    ids = {item.temp_id: f"{paper.id}_C{index:03d}" for index, item in enumerate(ordered, 1)}
    contexts = [Context(id=ids[x.temp_id], paper_id=paper.id, parent_ids=[ids[p] for p in x.parent_temp_ids], label=x.label, aliases=x.aliases, spatial_support=x.spatial_support.model_dump() if x.spatial_support else None, evidence_block_ids=x.evidence_block_ids) for x in ordered]
    transitions = [Transition(id=f"{paper.id}_T{index:03d}", paper_id=paper.id, from_context_id=ids[x.from_context_temp_id], to_context_id=ids[x.to_context_temp_id], label=x.label, aliases=x.aliases, description=x.description, evidence_block_ids=x.evidence_block_ids) for index, x in enumerate(mapped.transitions, 1)]
    registry = {x.id: {"label": x.label, "parent_ids": x.parent_ids, "aliases": x.aliases} for x in contexts}
    return contexts, transitions, {"registry": registry, "temp_to_permanent": ids}


def _section_priority(block: SourceBlock, claim: bool) -> int:
    section = normalize_text_key(" ".join(block.section_path))
    if claim:
        for value, terms in ((4, ("results", "analysis")), (3, ("discussion", "mechanism", "sensitivity")), (2, ("conclusion",)), (1, ("methods", "experimental design"))):
            if any(term in section for term in terms):
                return value
    else:
        if any(x in section for x in ("methods", "study area", "experimental design")): return 3
        if "results" in section: return 2
        if "discussion" in section: return 1
    return 0


def evidence_bundle(blocks: list[SourceBlock], queries: list[str], aliases: list[str], mandatory_ids: list[str], client: OllamaClient, claim: bool = False) -> list[SourceBlock]:
    cfg = PIPELINE["evidence_retrieval"]
    by_id = {x.id: x for x in blocks}
    lexical = bm25(blocks, queries, cfg["lexical_top_k"], cfg["bm25_k1"], cfg["bm25_b"])
    qvecs = client.embed(queries, PIPELINE["embeddings"]["model"], PIPELINE["embeddings"]["dimension"]) if PIPELINE["embeddings"]["block_embeddings"] else []
    sem = semantic(blocks, qvecs, cfg["semantic_top_k"])
    lexical_rank = {x.block.id: 1 / x.rank for x in lexical}
    semantic_rank = {x.block.id: 1 / x.rank for x in sem}
    direct = set(mandatory_ids) | set(lexical_rank) | set(semantic_rank) | {x.id for x in blocks if exact_alias_hit(x, aliases)}
    neighbors = {x.order + delta for x in blocks if x.id in direct for delta in range(-cfg["neighbor_blocks_each_side"], cfg["neighbor_blocks_each_side"] + 1)}
    candidates = [x for x in blocks if x.block_type != "reference" and (x.id in direct or x.order in neighbors)]
    candidates.sort(key=lambda x: (-(x.id in mandatory_ids), -exact_alias_hit(x, aliases), -_section_priority(x, claim), -semantic_rank.get(x.id, 0), -lexical_rank.get(x.id, 0), x.id not in direct, x.order))
    selected: list[SourceBlock] = []
    used = 0
    budget = PIPELINE["paper_mapping"]["evidence_input_budget_tokens"]
    for block in candidates:
        size = token_count(block.text)
        if block.id in mandatory_ids or used + size <= budget:
            selected.append(block)
            used += size
    return sorted({x.id: x for x in selected}.values(), key=lambda x: x.order)


def claim_result_pool(blocks: list[SourceBlock], mandatory_ids: list[str], excluded_sections: set[tuple[str, ...]] | None = None) -> list[SourceBlock]:
    mandatory = set(mandatory_ids)
    excluded_sections = excluded_sections or set()
    result_terms = ("results", "analysis", "discussion", "conclusion", "findings")
    stop_terms = ("acknowledgment", "author contribution", "data availability", "references", "bibliography")
    selected = []
    inside_results = False
    for block in sorted(blocks, key=lambda item: item.order):
        heading = normalize_text_key(block.text) if block.block_type == "heading" else ""
        if heading and any(term in heading for term in result_terms):
            inside_results = True
        elif heading and any(term in heading for term in stop_terms):
            inside_results = False
        section = normalize_text_key(" ".join(block.section_path))
        if block.id in mandatory or (tuple(block.section_path) not in excluded_sections and (inside_results or any(term in section for term in result_terms))):
            selected.append(block)
    return selected or blocks


def include_evidence_blocks(
    bundle: list[SourceBlock],
    blocks: list[SourceBlock],
    evidence_ids: set[str],
) -> list[SourceBlock]:
    """Add cited inherited evidence so reference validation matches the supplied context."""
    selected = {block.id: block for block in bundle}
    block_by_id = {block.id: block for block in blocks}
    for block_id in evidence_ids:
        if block_id in block_by_id:
            selected[block_id] = block_by_id[block_id]
    return sorted(selected.values(), key=lambda block: block.order)


def partition_claim_blocks(blocks: list[SourceBlock], target_tokens: int) -> list[list[SourceBlock]]:
    """Split large Claim inputs at section boundaries without dropping passages."""
    if token_count(_render_blocks(blocks)) <= target_tokens:
        return [blocks]
    groups: list[list[SourceBlock]] = []
    for block in sorted(blocks, key=lambda item: item.order):
        if not groups or groups[-1][0].section_path != block.section_path:
            groups.append([])
        groups[-1].append(block)
    parts: list[list[SourceBlock]] = []
    current: list[SourceBlock] = []
    for group in groups:
        if token_count(_render_blocks(group)) > target_tokens:
            for block in group:
                proposal = [*current, block]
                if current and token_count(_render_blocks(proposal)) > target_tokens:
                    parts.append(current)
                    current = []
                current.append(block)
            continue
        proposal = [*current, *group]
        if current and token_count(_render_blocks(proposal)) > target_tokens:
            parts.append(current)
            current = []
        current.extend(group)
    if current:
        parts.append(current)
    return parts


def is_outcome_like_facet(notion: str, description: str) -> bool:
    """Identify explicit response statements that belong in Claims, not Facets."""
    text = normalize_text_key(f"{notion} {description}")
    relation = re.search(r"\b(?:lead(?:s|ing)? to|caus(?:e|es|ed|ing)|increases|decreases|reduces|enhances|suppresses)\b", text)
    response = re.search(r"\b(?:temperature|precipitation|rainfall|wind|cloud|humidity|soil moisture|evaporation|evapotranspiration|heat flux|water stress)\b", text)
    return bool(relation and response)


def effective_facet_ids(context_id: str, contexts: list[Context], facets: list[Facet]) -> list[Facet]:
    by_context = {x.id: x for x in contexts}
    allowed: set[str] = set()
    pending = [context_id]
    while pending:
        current = pending.pop()
        if current in allowed:
            continue
        allowed.add(current)
        pending.extend(by_context[current].parent_ids)
    return [x for x in facets if x.context_id in allowed]


def relevant_claim_contexts(
    scope_id: str,
    scope_type: str,
    contexts: list[Context],
    transitions: list[Transition],
) -> list[dict[str, Any]]:
    """Return only the target Contexts and their ancestors for Claim extraction."""
    by_id = {context.id: context for context in contexts}
    if scope_type == "transition":
        transition = next(item for item in transitions if item.id == scope_id)
        pending = [transition.from_context_id, transition.to_context_id]
    else:
        pending = [scope_id]
    selected: set[str] = set()
    while pending:
        context_id = pending.pop()
        if context_id in selected or context_id not in by_id:
            continue
        selected.add(context_id)
        pending.extend(by_id[context_id].parent_ids)
    return [
        {
            "id": context.id,
            "label": context.label,
            "parent_ids": context.parent_ids,
            "aliases": context.aliases,
            "spatial_support": context.spatial_support.model_dump(mode="json") if context.spatial_support else None,
        }
        for context in contexts
        if context.id in selected
    ]


def compact_claim_facets(facets: list[Facet]) -> list[dict[str, Any]]:
    """Keep only Facet identity and scientific meaning needed by Claim extraction."""
    return [
        {
            "id": facet.id,
            "domain": facet.domain,
            "notion": facet.notion,
            "description": facet.description,
        }
        for facet in facets
    ]


def extract_facets(
    paper: Paper,
    mapped: PaperMap,
    contexts: list[Context],
    map_meta: dict[str, Any],
    blocks: list[SourceBlock],
    paper_dir: Path,
    client: OllamaClient,
    evidence_bundles: dict[str, list[SourceBlock]] | None = None,
    only_context_ids: set[str] | None = None,
) -> tuple[list[Facet], list[str]]:
    system, user = _split_prompt(_prompt("facet_extraction.txt"))
    cfg = PIPELINE["ollama"]["stages"]["facet_extraction"]
    by_temp = {x.temp_id: x for x in mapped.contexts}
    reverse = {v: k for k, v in map_meta["temp_to_permanent"].items()}
    facets, hints, excluded_outcomes = [], [], []
    context_by_id = {item.id: item for item in contexts}
    bundles: dict[str, list[SourceBlock]] = {}
    for context in contexts:
        if only_context_ids is not None and context.id not in only_context_ids:
            continue
        cached_path = paper_dir / "extraction" / "facets" / context.id / "validated.json"
        if cached_path.exists():
            continue
        if evidence_bundles and context.id in evidence_bundles:
            bundles[context.id] = evidence_bundles[context.id]
        else:
            source = by_temp[reverse[context.id]]
            parent_aliases = [alias for parent_id in context.parent_ids for alias in [context_by_id[parent_id].label, *context_by_id[parent_id].aliases]]
            queries = [context.label, *context.aliases, *(f"background context {alias}" for alias in parent_aliases), "study area location climate season meteorology", "wind atmospheric circulation humidity boundary layer", "land cover land use vegetation management", "hydrology soil moisture", "terrain topography elevation", "spatial configuration patch heterogeneity edge"]
            mandatory_ids = unique_in_order(source.evidence_block_ids + source.facet_seed_block_ids)
            bundles[context.id] = evidence_bundle(blocks, queries, context.aliases, mandatory_ids, client)
    for context in contexts:
        if only_context_ids is not None and context.id not in only_context_ids:
            continue
        parent_facets = [facet for facet in effective_facet_ids(context.id, contexts, facets) if facet.context_id != context.id]
        cached_path = paper_dir / "extraction" / "facets" / context.id / "validated.json"
        if cached_path.exists():
            batch = FacetBatch.model_validate_json(cached_path.read_text(encoding="utf-8"))
            allowed = {x.id for x in blocks}
        else:
            inherited_evidence_ids = {block_id for facet in parent_facets for block_id in facet.evidence_block_ids}
            bundle = include_evidence_blocks(bundles[context.id], blocks, inherited_evidence_ids)
            request_text = user.format(paper_id=paper.id, target_context=context.model_dump_json(), context_registry=json.dumps(map_meta["registry"]), parent_facets=json.dumps([x.model_dump() for x in parent_facets]), existing_target_facets="[]", evidence_blocks=_render_blocks(bundle))
            thinking = cfg["root_thinking"] if not context.parent_ids else cfg["thinking"]
            batch = client.structured(stage="facet_extraction", system=system, user=request_text, schema=FacetBatch, model=PIPELINE["ollama"]["model"], temperature=cfg["temperature"], thinking=thinking, artifact_dir=cached_path.parent, paper_id=paper.id, input_block_ids=[x.id for x in bundle], retries=cfg["retries"])
            allowed = {x.id for x in bundle}
            if batch.context_id != context.id or any(not set(x.evidence_block_ids) <= allowed for x in batch.facets):
                repair = request_text + f"\n\nCORRECTION TASK\n\nThe returned condition records used an invalid target ID or evidence ID.\n\nPREVIOUS JSON OBJECT\n{batch.model_dump_json(by_alias=True)}\n\nREQUIRED TARGET ID\n{context.id}\n\nALLOWED EVIDENCE IDS\n{json.dumps(sorted(allowed))}\n\nReturn the complete JSON object again. Copy already valid records. Keep an invalid record only when one or more allowed SourceBlocks directly supports it, and assign the smallest supporting allowed ID set. Remove a record that has no directly supporting allowed SourceBlock."
                repair_cfg = PIPELINE["ollama"]["stages"]["facet_reference_repair"]
                batch = client.structured(stage="facet_reference_repair", system=system, user=repair, schema=FacetBatch, model=PIPELINE["ollama"]["model"], temperature=repair_cfg["temperature"], thinking=repair_cfg["thinking"], artifact_dir=cached_path.parent, paper_id=paper.id, input_block_ids=[x.id for x in bundle], retries=repair_cfg["retries"])
        if batch.context_id != context.id or any(not set(x.evidence_block_ids) <= allowed for x in batch.facets):
            raise ValueError(f"FAILED_REFERENCE_VALIDATION: Facet batch {context.id}")
        parent_keys = {(x.domain, normalize_text_key(x.notion), normalize_text_key(x.description)) for x in parent_facets}
        for candidate in batch.facets:
            if not set(candidate.evidence_block_ids) <= allowed:
                continue
            if is_outcome_like_facet(candidate.notion, candidate.description):
                excluded_outcomes.append({
                    "context_id": context.id,
                    "notion": candidate.notion,
                    "description": candidate.description,
                    "evidence_block_ids": candidate.evidence_block_ids,
                    "reason": "explicit response relationship belongs in Claim extraction",
                })
                continue
            if (candidate.domain, normalize_text_key(candidate.notion), normalize_text_key(candidate.description)) in parent_keys:
                hints.append("PARENT_DUPLICATE_AMBIGUOUS")
            facets.append(Facet(id=f"{paper.id}_F{len(facets)+1:03d}", context_id=context.id, domain=candidate.domain, notion=candidate.notion, description=candidate.description, origin="reported", source={"type": "paper", "id": paper.id}, evidence_block_ids=unique_in_order(candidate.evidence_block_ids, {x.id: x.order for x in blocks})))
        hints.extend(batch.unmapped_context_hints)
        write_json(cached_path, batch.model_dump(by_alias=True))
    write_json(paper_dir / "extraction" / "facets" / "excluded_outcomes.json", excluded_outcomes)
    return exact_deduplicate_facets(facets, blocks), hints


def _permanent_context_ids(mapped: PaperMap, contexts: list[Context]) -> dict[str, str]:
    pending = list(mapped.contexts)
    ordered: list[MapContext] = []
    done: set[str] = set()
    while pending:
        ready = [item for item in pending if set(item.parent_temp_ids) <= done]
        if not ready:
            raise ValueError("Context hierarchy cycle")
        for item in ready:
            ordered.append(item)
            done.add(item.temp_id)
            pending.remove(item)
    if len(ordered) != len(contexts):
        raise ValueError("mapped and permanent Context counts differ")
    return {item.temp_id: context.id for item, context in zip(ordered, contexts, strict=True)}


def extract_claims(paper: Paper, mapped: PaperMap, contexts: list[Context], transitions: list[Transition], facets: list[Facet], blocks: list[SourceBlock], paper_dir: Path, client: OllamaClient) -> tuple[list[Claim], list[str]]:
    system, user = _split_prompt(_prompt("claim_extraction.txt"))
    cfg = PIPELINE["ollama"]["stages"]["claim_extraction"]
    context_ids = _permanent_context_ids(mapped, contexts)
    transition_ids = {item.temp_id: f"{paper.id}_T{index:03d}" for index, item in enumerate(mapped.transitions, 1)}
    reverse_t = {transition_ids[item.temp_id]: item for item in mapped.transitions}
    reverse_c = {permanent: temporary for temporary, permanent in context_ids.items()}
    by_temp_context = {item.temp_id: item for item in mapped.contexts}
    context_by_id = {item.id: item for item in contexts}
    transition_by_id = {item.id: item for item in transitions}
    tasks: list[ClaimExtractionTask] = []

    if mapped.result_scopes:
        for index, result_scope in enumerate(mapped.result_scopes, 1):
            scope_id = context_ids[result_scope.scope_temp_id] if result_scope.scope_type == "context" else transition_ids[result_scope.scope_temp_id]
            if result_scope.scope_type == "context":
                target_context = context_by_id[scope_id]
                available = effective_facet_ids(scope_id, contexts, facets)
                aliases = [target_context.label, *target_context.aliases]
                target_evidence = target_context.evidence_block_ids
            else:
                target_transition = transition_by_id[scope_id]
                from_context = context_by_id[target_transition.from_context_id]
                to_context = context_by_id[target_transition.to_context_id]
                available = effective_facet_ids(from_context.id, contexts, facets) + effective_facet_ids(to_context.id, contexts, facets)
                aliases = [target_transition.label, *target_transition.aliases, *from_context.aliases, *to_context.aliases]
                target_evidence = target_transition.evidence_block_ids
            queries = [result_scope.label, *aliases, "reported effect response mechanism association null reversal", "sensible heat latent heat evapotranspiration soil moisture boundary layer cloud precipitation convergence circulation temperature humidity wind"]
            facet_evidence = [block_id for facet in available for block_id in facet.evidence_block_ids]
            mandatory = unique_in_order(result_scope.claim_seed_block_ids + target_evidence + facet_evidence)
            tasks.append(ClaimExtractionTask(f"result_{index:03d}", scope_id, result_scope.scope_type, result_scope.label, queries, mandatory, available))
    else:
        for transition in transitions:
            source = reverse_t[transition.id]
            from_context = context_by_id[transition.from_context_id]
            to_context = context_by_id[transition.to_context_id]
            aliases = transition.aliases + from_context.aliases + to_context.aliases
            queries = [transition.label, *aliases, "effect response difference change increase decrease mechanism because due to caused associated result", "sensible heat latent heat evapotranspiration soil moisture boundary layer cloud precipitation convergence circulation temperature humidity wind dust aerosol"]
            available = effective_facet_ids(from_context.id, contexts, facets) + effective_facet_ids(to_context.id, contexts, facets)
            facet_evidence = [block_id for facet in available for block_id in facet.evidence_block_ids]
            tasks.append(ClaimExtractionTask(transition.id, transition.id, "transition", transition.label, queries, unique_in_order(transition.evidence_block_ids + source.claim_seed_block_ids + facet_evidence), available))

        endpoint_ids = {context_id for transition in transitions for context_id in (transition.from_context_id, transition.to_context_id)}
        parent_scope_ids = {parent_id for context_id in endpoint_ids for parent_id in context_by_id[context_id].parent_ids}
        root_context_ids = {item.id for item in contexts if not item.parent_ids}
        for context in contexts:
            source = by_temp_context[reverse_c[context.id]]
            global_seeds = mapped.global_claim_seed_block_ids if context.id in root_context_ids else []
            if not source.claim_seed_block_ids and not global_seeds and context.id not in parent_scope_ids:
                continue
            queries = [context.label, *context.aliases, "reported result subgroup stratum season wet dry year percentile subregion", "effect response mechanism climate temperature precipitation evapotranspiration"]
            available = effective_facet_ids(context.id, contexts, facets)
            facet_evidence = [block_id for facet in available for block_id in facet.evidence_block_ids]
            mandatory = unique_in_order(context.evidence_block_ids + source.claim_seed_block_ids + global_seeds + facet_evidence)
            tasks.append(ClaimExtractionTask(context.id, context.id, "context", context.label, queries, mandatory, available))

    if not tasks:
        for context in contexts:
            queries = [context.label, *context.aliases, "effect response difference change increase decrease mechanism results climate temperature precipitation evapotranspiration"]
            available = effective_facet_ids(context.id, contexts, facets)
            facet_evidence = [block_id for facet in available for block_id in facet.evidence_block_ids]
            mandatory = (mapped.global_claim_seed_block_ids or context.evidence_block_ids) + facet_evidence
            tasks.append(ClaimExtractionTask(context.id, context.id, "context", context.label, queries, unique_in_order(mandatory), available))

    claims, hints = [], []
    block_by_id = {block.id: block for block in blocks}
    transition_result_sections = {tuple(block_by_id[block_id].section_path) for transition in mapped.transitions for block_id in transition.claim_seed_block_ids if block_id in block_by_id}
    bundles = {
        task.task_id: evidence_bundle(
            claim_result_pool(blocks, task.mandatory_block_ids, transition_result_sections) if task.scope_type == "context" else blocks,
            task.queries,
            task.queries[:5],
            task.mandatory_block_ids,
            client,
            claim=True,
        )
        for task in tasks
        if not (paper_dir / "extraction" / "claims" / task.task_id / "validated.json").exists()
    }
    for task in tasks:
        reachable_facets = {item.id for item in task.available_facets}
        cached_path = paper_dir / "extraction" / "claims" / task.task_id / "validated.json"
        if cached_path.exists():
            batch = ClaimBatch.model_validate_json(cached_path.read_text(encoding="utf-8"))
            allowed_blocks = {item.id for item in blocks}
        else:
            bundle = bundles[task.task_id]
            target = next((item.model_dump(exclude={"transition_embedding"}) for item in transitions if item.id == task.scope_id), next((item.model_dump(exclude={"retrieval_embedding"}) for item in contexts if item.id == task.scope_id), {}))
            part_batches: list[ClaimBatch] = []
            for part_number, part in enumerate(partition_claim_blocks(bundle, PIPELINE["evidence_retrieval"]["claim_bundle_target_tokens"]), 1):
                part_dir = cached_path.parent / "parts" / f"part{part_number:03d}"
                part_cache = part_dir / "validated.json"
                allowed_part_blocks = {item.id for item in part}
                if part_cache.exists():
                    part_batch = ClaimBatch.model_validate_json(part_cache.read_text(encoding="utf-8"))
                else:
                    request_text = user.format(paper_id=paper.id, relevant_contexts=json.dumps(relevant_claim_contexts(task.scope_id, task.scope_type, contexts, transitions)), available_scope_facets=json.dumps(compact_claim_facets(task.available_facets)), target_scope=json.dumps(target), result_focus=task.result_focus, evidence_blocks=_render_blocks(part))
                    part_batch = client.structured(stage="claim_extraction", system=system, user=request_text, schema=ClaimBatch, model=PIPELINE["ollama"]["model"], temperature=cfg["temperature"], thinking=cfg["thinking"], artifact_dir=part_dir, paper_id=paper.id, input_block_ids=[item.id for item in part], retries=cfg["retries"])
                    if part_batch.scope_id != task.scope_id or any(not set(item.evidence_block_ids) <= allowed_part_blocks or any(not set(case.evidence_block_ids) <= allowed_part_blocks for case in item.analysis_cases) for item in part_batch.claims):
                        repair = request_text + f"\n\nCORRECTION TASK\n\nThe returned scientific relationships used an invalid scope or reference ID.\n\nPREVIOUS JSON OBJECT\n{part_batch.model_dump_json(by_alias=True)}\n\nREQUIRED SCOPE ID\n{task.scope_id}\n\nALLOWED EVIDENCE IDS\n{json.dumps(sorted(allowed_part_blocks))}\n\nALLOWED CONDITION IDS\n{json.dumps(sorted(reachable_facets))}\n\nReturn the complete JSON object again using the required scope ID and exact IDs from the allowed lists. Keep scientific content grounded in the original evidence passages above."
                        repair_cfg = PIPELINE["ollama"]["stages"]["claim_reference_repair"]
                        part_batch = client.structured(stage="claim_reference_repair", system=system, user=repair, schema=ClaimBatch, model=PIPELINE["ollama"]["model"], temperature=repair_cfg["temperature"], thinking=repair_cfg["thinking"], artifact_dir=part_dir, paper_id=paper.id, input_block_ids=[item.id for item in part], retries=repair_cfg["retries"])
                    write_json(part_cache, part_batch.model_dump(by_alias=True))
                if part_batch.scope_id != task.scope_id or any(not set(item.evidence_block_ids) <= allowed_part_blocks or any(not set(case.evidence_block_ids) <= allowed_part_blocks for case in item.analysis_cases) for item in part_batch.claims):
                    raise ValueError(f"FAILED_REFERENCE_VALIDATION: Claim batch {task.scope_id} part {part_number}")
                part_batches.append(part_batch)
            batch = ClaimBatch(scope_id=task.scope_id, claims=[claim for part_batch in part_batches for claim in part_batch.claims], unmapped_context_hints=unique_in_order([hint for part_batch in part_batches for hint in part_batch.unmapped_context_hints]), ambiguities=unique_in_order([item for part_batch in part_batches for item in part_batch.ambiguities]))
            allowed_blocks = {item.id for item in bundle}
        if batch.scope_id != task.scope_id or any(not set(item.evidence_block_ids) <= allowed_blocks or any(not set(case.evidence_block_ids) <= allowed_blocks for case in item.analysis_cases) for item in batch.claims):
            raise ValueError(f"FAILED_REFERENCE_VALIDATION: Claim batch {task.scope_id}")
        for candidate in batch.claims:
            if candidate.evidence_role not in ("OWN_RESULT", "AUTHORS_INTERPRETATION_OF_OWN_RESULT") or not set(candidate.evidence_block_ids) <= allowed_blocks:
                continue
            conditioning = [item for item in candidate.conditioning_facet_ids if item in reachable_facets]
            case_evidence = [block_id for case in candidate.analysis_cases for block_id in case.evidence_block_ids]
            claims.append(Claim(id=f"{paper.id}_CL{len(claims)+1:03d}", paper_id=paper.id, scope_type=task.scope_type, scope_id=task.scope_id, **{"from": candidate.from_.model_dump()}, to=candidate.to, relation=candidate.relation, description=candidate.description, evidence_role=candidate.evidence_role, conditioning_facet_ids=conditioning, analysis_cases=[case.model_dump() for case in candidate.analysis_cases], analysis_comparison=candidate.analysis_comparison.model_dump() if candidate.analysis_comparison else None, evidence_block_ids=unique_in_order(candidate.evidence_block_ids + case_evidence, {item.id: item.order for item in blocks})))
        hints.extend(batch.unmapped_context_hints)
        write_json(cached_path, batch.model_dump(by_alias=True))
    return exact_deduplicate_claims(claims), hints


def exact_deduplicate_claims(claims: list[Claim]) -> list[Claim]:
    found: dict[tuple[str, ...], Claim] = {}
    for claim in claims:
        key = (claim.scope_id, normalize_text_key(claim.from_.concept), normalize_text_key(claim.from_.state), claim.relation, normalize_text_key(claim.to.concept), normalize_text_key(claim.to.state), normalize_text_key(claim.description))
        if key in found:
            found[key].evidence_block_ids = unique_in_order(found[key].evidence_block_ids + claim.evidence_block_ids)
            found[key].conditioning_facet_ids = unique_in_order(found[key].conditioning_facet_ids + claim.conditioning_facet_ids)
            existing_cases = {(normalize_text_key(case.label), normalize_text_key(case.description)) for case in found[key].analysis_cases}
            found[key].analysis_cases.extend(case for case in claim.analysis_cases if (normalize_text_key(case.label), normalize_text_key(case.description)) not in existing_cases)
            if found[key].analysis_comparison is None:
                found[key].analysis_comparison = claim.analysis_comparison
        else:
            found[key] = claim
    result = list(found.values())
    for index, claim in enumerate(result, 1):
        claim.id = f"{claim.paper_id}_CL{index:03d}"
    return result


def exact_deduplicate_facets(facets: list[Facet], blocks: list[SourceBlock]) -> list[Facet]:
    order = {x.id: x.order for x in blocks}
    found: dict[tuple[str, ...], Facet] = {}
    for facet in facets:
        key = (facet.context_id, normalize_text_key(facet.domain), normalize_text_key(facet.notion), normalize_text_key(facet.description))
        if key in found:
            found[key].evidence_block_ids = unique_in_order(found[key].evidence_block_ids + facet.evidence_block_ids, order)
        else:
            found[key] = facet
    result = list(found.values())
    for index, facet in enumerate(result, 1):
        facet.id = f"{facet.id.split('_F', 1)[0]}_F{index:03d}"
    return result
