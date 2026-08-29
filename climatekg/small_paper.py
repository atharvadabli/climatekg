from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import PIPELINE, ROOT
from .extract import _render_blocks, _split_prompt, permanent_map
from .extraction_models import PaperMap, SmallPaperExtraction
from .models import Claim, Context, Facet, Paper, SourceBlock, Transition
from .ollama import OllamaClient
from .utils import token_count, unique_in_order, write_json


def cleaned_paper_blocks(blocks: list[SourceBlock]) -> list[SourceBlock]:
    """Return only useful cleaned-paper blocks in stable reading order."""
    return [block for block in blocks if block.block_type != "reference" and block.text.strip()]


def combined_extraction_token_count(blocks: list[SourceBlock]) -> int:
    return sum(token_count(block.text) for block in cleaned_paper_blocks(blocks))


def is_combined_extraction_eligible(blocks: list[SourceBlock]) -> bool:
    config = PIPELINE["paper_mapping"]
    return bool(config["combined_extraction_enabled"]) and combined_extraction_token_count(blocks) <= config["combined_extraction_threshold_tokens"]


def _validate_combined(result: SmallPaperExtraction, blocks: list[SourceBlock]) -> None:
    allowed_blocks = {block.id for block in cleaned_paper_blocks(blocks)}
    contexts = {item.temp_id: item for item in result.contexts}
    facets = {item.temp_id: item for item in result.facets}
    transitions = {item.temp_id: item for item in result.transitions}
    claims = {item.temp_id: item for item in result.claims}

    collections = (
        ("Context", contexts, result.contexts),
        ("Facet", facets, result.facets),
        ("Transition", transitions, result.transitions),
        ("Claim", claims, result.claims),
    )
    for label, indexed, original in collections:
        if len(indexed) != len(original) or any(not item.temp_id.strip() for item in original):
            raise ValueError(f"combined extraction contains duplicate or empty {label} IDs")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(context_id: str) -> None:
        if context_id in visiting:
            raise ValueError(f"combined extraction contains a Context cycle at {context_id}")
        if context_id in visited:
            return
        if context_id not in contexts:
            raise ValueError(f"combined extraction references unknown Context {context_id}")
        visiting.add(context_id)
        for parent_id in contexts[context_id].parent_temp_ids:
            visit(parent_id)
        visiting.remove(context_id)
        visited.add(context_id)

    for context_id in contexts:
        visit(context_id)

    for context in result.contexts:
        _validate_evidence(context.evidence_block_ids, allowed_blocks, f"Context {context.temp_id}")
        _validate_optional_evidence(context.facet_seed_block_ids, allowed_blocks, f"Context {context.temp_id}")
    for facet in result.facets:
        if facet.context_temp_id not in contexts:
            raise ValueError(f"Facet {facet.temp_id} references unknown Context {facet.context_temp_id}")
        _validate_evidence(facet.evidence_block_ids, allowed_blocks, f"Facet {facet.temp_id}")
    for transition in result.transitions:
        if transition.from_context_temp_id not in contexts or transition.to_context_temp_id not in contexts:
            raise ValueError(f"Transition {transition.temp_id} references an unknown Context")
        if transition.from_context_temp_id == transition.to_context_temp_id:
            raise ValueError(f"Transition {transition.temp_id} has identical endpoints")
        _validate_evidence(transition.evidence_block_ids, allowed_blocks, f"Transition {transition.temp_id}")
        _validate_optional_evidence(transition.claim_seed_block_ids, allowed_blocks, f"Transition {transition.temp_id}")

    for claim in result.claims:
        scopes = contexts if claim.scope_type == "context" else transitions
        if claim.scope_temp_id not in scopes:
            raise ValueError(f"Claim {claim.temp_id} references unknown {claim.scope_type} {claim.scope_temp_id}")
        if any(facet_id not in facets for facet_id in claim.conditioning_facet_temp_ids):
            raise ValueError(f"Claim {claim.temp_id} references an unknown conditioning Facet")
        reachable = _reachable_contexts(claim, contexts, transitions)
        if any(facets[facet_id].context_temp_id not in reachable for facet_id in claim.conditioning_facet_temp_ids):
            raise ValueError(f"Claim {claim.temp_id} references an unreachable conditioning Facet")
        _validate_evidence(claim.evidence_block_ids, allowed_blocks, f"Claim {claim.temp_id}")


def _validate_evidence(ids: list[str], allowed: set[str], label: str) -> None:
    if not ids or not set(ids) <= allowed:
        raise ValueError(f"{label} has missing or invalid evidence SourceBlock IDs")


def _validate_optional_evidence(ids: list[str], allowed: set[str], label: str) -> None:
    if not set(ids) <= allowed:
        raise ValueError(f"{label} has invalid evidence SourceBlock IDs")


def _reachable_contexts(claim: Any, contexts: dict[str, Any], transitions: dict[str, Any]) -> set[str]:
    if claim.scope_type == "context":
        pending = [claim.scope_temp_id]
    else:
        transition = transitions[claim.scope_temp_id]
        pending = [transition.from_context_temp_id, transition.to_context_temp_id]
    reachable: set[str] = set()
    while pending:
        context_id = pending.pop()
        if context_id not in reachable:
            reachable.add(context_id)
            pending.extend(contexts[context_id].parent_temp_ids)
    return reachable


def extract_small_paper(
    paper: Paper,
    blocks: list[SourceBlock],
    paper_dir: Path,
    client: OllamaClient,
) -> tuple[list[Context], list[Facet], list[Transition], list[Claim], list[str], dict[str, Any]]:
    useful = cleaned_paper_blocks(blocks)
    token_total = combined_extraction_token_count(blocks)
    threshold = PIPELINE["paper_mapping"]["combined_extraction_threshold_tokens"]
    if token_total > threshold:
        raise ValueError(f"combined extraction input is {token_total} tokens, above the {threshold}-token threshold")

    artifact_dir = paper_dir / "extraction" / "small_paper"
    validated_path = artifact_dir / "validated.json"
    if validated_path.exists():
        result = SmallPaperExtraction.model_validate_json(validated_path.read_text(encoding="utf-8"))
    else:
        system, user = _split_prompt((ROOT / "prompts" / "small_paper_extraction.txt").read_text(encoding="utf-8"))
        stage = PIPELINE["ollama"]["stages"]["small_paper_extraction"]
        result = client.structured(
            stage="small_paper_extraction",
            system=system,
            user=user.format(paper_id=paper.id, paper_text=_render_blocks(useful)),
            schema=SmallPaperExtraction,
            model=PIPELINE["ollama"]["model"],
            temperature=stage["temperature"],
            thinking=stage["thinking"],
            artifact_dir=artifact_dir,
            paper_id=paper.id,
            input_block_ids=[block.id for block in useful],
            retries=stage["retries"],
        )
        write_json(artifact_dir / "schema_validated.json", result.model_dump(by_alias=True))
    _validate_combined(result, blocks)
    write_json(validated_path, result.model_dump(by_alias=True))
    paper_map = PaperMap(
        contexts=result.contexts,
        transitions=result.transitions,
        context_mention_resolution={},
        global_claim_seed_block_ids=[],
        ambiguities=result.ambiguities,
    )
    contexts, transitions, map_meta = permanent_map(paper, paper_map)
    context_ids = map_meta["temp_to_permanent"]
    facet_ids = {item.temp_id: f"{paper.id}_F{index:03d}" for index, item in enumerate(result.facets, 1)}
    transition_ids = {item.temp_id: f"{paper.id}_T{index:03d}" for index, item in enumerate(result.transitions, 1)}
    block_order = {block.id: block.order for block in blocks}

    facets = [
        Facet(
            id=facet_ids[item.temp_id],
            context_id=context_ids[item.context_temp_id],
            domain=item.domain,
            notion=item.notion,
            description=item.description,
            origin="reported",
            source={"type": "paper", "id": paper.id},
            evidence_block_ids=unique_in_order(item.evidence_block_ids, block_order),
        )
        for item in result.facets
    ]
    claims = [
        Claim(
            id=f"{paper.id}_CL{index:03d}",
            paper_id=paper.id,
            scope_type=item.scope_type,
            scope_id=context_ids[item.scope_temp_id] if item.scope_type == "context" else transition_ids[item.scope_temp_id],
            **{"from": item.from_.model_dump()},
            to=item.to,
            relation=item.relation,
            description=item.description,
            evidence_role=item.evidence_role,
            conditioning_facet_ids=[facet_ids[facet_id] for facet_id in item.conditioning_facet_temp_ids],
            evidence_block_ids=unique_in_order(item.evidence_block_ids, block_order),
        )
        for index, item in enumerate(result.claims, 1)
    ]
    write_json(artifact_dir / "context_registry.json", map_meta)
    write_json(artifact_dir / "converted.json", {
        "contexts": [item.model_dump() for item in contexts],
        "facets": [item.model_dump() for item in facets],
        "transitions": [item.model_dump() for item in transitions],
        "claims": [item.model_dump(by_alias=True) for item in claims],
    })
    return contexts, facets, transitions, claims, result.ambiguities, map_meta
