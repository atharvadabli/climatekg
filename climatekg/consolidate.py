from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, TypeVar

from .canonicalize import canonical_direction
from .config import PIPELINE, ROOT
from .extraction_models import ConsolidationBatch
from .models import Claim, Context, Facet, Paper, SourceBlock, Transition
from .ollama import OllamaClient
from .utils import cosine, normalize_text_key, unique_in_order, write_json

T = TypeVar("T", Context, Facet, Claim)


def _pairs(items: list[T]) -> Iterable[tuple[T, T]]:
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            yield left, right


def _embed(client: OllamaClient, texts: list[str]) -> list[list[float]]:
    return client.embed(texts, PIPELINE["embeddings"]["model"], PIPELINE["embeddings"]["dimension"])


def _context_candidates(contexts: list[Context]) -> list[dict[str, Any]]:
    candidates = []
    for left, right in _pairs(contexts):
        left_names = {normalize_text_key(x) for x in [left.label, *left.aliases] if x.strip()}
        right_names = {normalize_text_key(x) for x in [right.label, *right.aliases] if x.strip()}
        shared_alias = bool(left_names & right_names)
        same_spatial = left.spatial_support is not None and left.spatial_support == right.spatial_support
        same_label = normalize_text_key(left.label) == normalize_text_key(right.label)
        if shared_alias or (same_spatial and same_label):
            candidates.append({"object_type": "context", "left": left.model_dump(), "right": right.model_dump(), "reason": "shared_alias" if shared_alias else "same_spatial_support_and_label"})
    return candidates


def _facet_candidates(facets: list[Facet], client: OllamaClient) -> list[dict[str, Any]]:
    if not facets:
        return []
    notion_vectors = _embed(client, [x.notion for x in facets])
    content_vectors = _embed(client, [x.description for x in facets])
    positions = {item.id: index for index, item in enumerate(facets)}
    cfg = PIPELINE["consolidation"]
    candidates = []
    for left, right in _pairs(facets):
        if left.context_id != right.context_id or left.domain != right.domain:
            continue
        li, ri = positions[left.id], positions[right.id]
        notion_equal = normalize_text_key(left.notion) == normalize_text_key(right.notion)
        notion_score = cosine(notion_vectors[li], notion_vectors[ri])
        content_score = cosine(content_vectors[li], content_vectors[ri])
        if notion_equal or notion_score >= cfg["facet_notion_candidate_cosine"] or content_score >= cfg["facet_content_candidate_cosine"]:
            candidates.append({"object_type": "facet", "left": left.model_dump(), "right": right.model_dump(), "scores": {"notion_cosine": notion_score, "content_cosine": content_score}})
    return candidates


def _claim_candidates(claims: list[Claim], client: OllamaClient) -> list[dict[str, Any]]:
    if not claims:
        return []
    from_vectors = _embed(client, [x.from_.concept for x in claims])
    to_vectors = _embed(client, [x.to.concept for x in claims])
    positions = {item.id: index for index, item in enumerate(claims)}
    threshold = PIPELINE["consolidation"]["claim_endpoint_candidate_cosine"]
    candidates = []
    for left, right in _pairs(claims):
        if left.scope_id != right.scope_id or left.relation != right.relation:
            continue
        if canonical_direction(left.from_.state) != canonical_direction(right.from_.state) or canonical_direction(left.to.state) != canonical_direction(right.to.state):
            continue
        li, ri = positions[left.id], positions[right.id]
        from_score = cosine(from_vectors[li], from_vectors[ri])
        to_score = cosine(to_vectors[li], to_vectors[ri])
        if from_score >= threshold and to_score >= threshold:
            candidates.append({"object_type": "claim", "left": left.model_dump(by_alias=True), "right": right.model_dump(by_alias=True), "scores": {"from_concept_cosine": from_score, "to_concept_cosine": to_score}})
    return candidates


def _components(ids: list[str], same_pairs: list[tuple[str, str]]) -> list[list[str]]:
    parent = {item_id: item_id for item_id in ids}

    def root(item_id: str) -> str:
        while parent[item_id] != item_id:
            parent[item_id] = parent[parent[item_id]]
            item_id = parent[item_id]
        return item_id

    for left_id, right_id in same_pairs:
        left_root, right_root = root(left_id), root(right_id)
        if left_root != right_root:
            parent[right_root] = left_root
    groups: dict[str, list[str]] = defaultdict(list)
    for item_id in ids:
        groups[root(item_id)].append(item_id)
    return list(groups.values())


def _merge_objects(items: list[T], same_pairs: list[tuple[str, str]], block_order: dict[str, int]) -> tuple[list[T], dict[str, str]]:
    by_id = {x.id: x for x in items}
    redirects: dict[str, str] = {}
    result: list[T] = []
    creation_order = {x.id: index for index, x in enumerate(items)}
    for group in _components(list(by_id), same_pairs):
        members = [by_id[item_id] for item_id in group]
        if isinstance(members[0], Context):
            canonical = min(members, key=lambda x: x.id)
            supports = [x.spatial_support for x in members if x.spatial_support is not None]
            if supports and any(x != supports[0] for x in supports[1:]):
                result.extend(members)
                continue
        else:
            canonical = sorted(members, key=lambda x: (-len(set(x.evidence_block_ids)), -len(x.description), creation_order[x.id]))[0]
        canonical.evidence_block_ids = unique_in_order([block_id for x in members for block_id in x.evidence_block_ids], block_order)
        if isinstance(canonical, Context):
            canonical.aliases = unique_in_order([alias for x in members for alias in [x.label, *x.aliases] if normalize_text_key(alias) != normalize_text_key(canonical.label)])
        if isinstance(canonical, Claim):
            canonical.conditioning_facet_ids = unique_in_order([facet_id for x in members for facet_id in x.conditioning_facet_ids])
        for member in members:
            redirects[member.id] = canonical.id
        result.append(canonical)
    return result, redirects


def consolidate_paper(paper: Paper, contexts: list[Context], facets: list[Facet], transitions: list[Transition], claims: list[Claim], blocks: list[SourceBlock], paper_dir: Path, client: OllamaClient) -> tuple[list[Context], list[Facet], list[Transition], list[Claim], list[str]]:
    validated_path = paper_dir / "extraction" / "consolidation" / "validated.json"
    if validated_path.exists():
        cached = json.loads(validated_path.read_text(encoding="utf-8"))
        return (
            [Context.model_validate(item) for item in cached["contexts"]],
            [Facet.model_validate(item) for item in cached["facets"]],
            [Transition.model_validate(item) for item in cached["transitions"]],
            [Claim.model_validate(item) for item in cached["claims"]],
            cached["warnings"],
        )
    candidates = _context_candidates(contexts) + _facet_candidates(facets, client) + _claim_candidates(claims, client)
    artifact_dir = paper_dir / "extraction" / "reconciliation"
    write_json(artifact_dir / "candidate_pairs.json", candidates)
    if not candidates:
        write_json(paper_dir / "extraction" / "consolidated.json", {"status": "OK", "candidate_pairs": [], "decisions": [], "unresolved_conflicts": []})
        return contexts, facets, transitions, claims, []

    template = (ROOT / "prompts" / "paper_consolidation.txt").read_text(encoding="utf-8")
    system, user = template.split("USER\n", 1)
    expected = {(x["object_type"], x["left"]["id"], x["right"]["id"]) for x in candidates}
    cfg = PIPELINE["ollama"]["stages"]["paper_consolidation"]
    batch = client.structured(stage="paper_consolidation", system=system.removeprefix("SYSTEM\n").strip(), user=user.format(paper_metadata=paper.model_dump_json(), candidate_pairs=json.dumps(candidates)), schema=ConsolidationBatch, model=PIPELINE["ollama"]["model"], temperature=cfg["temperature"], thinking=cfg["thinking"], artifact_dir=artifact_dir, paper_id=paper.id, input_block_ids=unique_in_order([block_id for x in candidates for side in ("left", "right") for block_id in x[side].get("evidence_block_ids", [])]), retries=cfg["retries"])
    received = {(x.object_type, x.left_id, x.right_id) for x in batch.decisions}
    if received != expected:
        raise ValueError("FAILED_REFERENCE_VALIDATION: consolidation decisions do not match candidate pairs")

    warnings = list(batch.unresolved_conflicts)
    same = defaultdict(list)
    parent_child = []
    for decision in batch.decisions:
        if decision.decision == "SAME":
            same[decision.object_type].append((decision.left_id, decision.right_id))
        elif decision.decision == "PARENT_CHILD" and decision.object_type == "context" and {decision.parent_id, decision.child_id} == {decision.left_id, decision.right_id}:
            parent_child.append((decision.parent_id, decision.child_id))
        elif decision.decision in {"UNCERTAIN", "PARENT_CHILD"}:
            warnings.append(f"{decision.object_type}:{decision.left_id}:{decision.right_id}:{decision.decision}")

    order = {x.id: x.order for x in blocks}
    contexts, context_redirect = _merge_objects(contexts, same["context"], order)
    for context in contexts:
        context.parent_ids = unique_in_order([context_redirect.get(x, x) for x in context.parent_ids if context_redirect.get(x, x) != context.id])
    for parent_id, child_id in parent_child:
        parent_id, child_id = context_redirect.get(parent_id, parent_id), context_redirect.get(child_id, child_id)
        child = next(x for x in contexts if x.id == child_id)
        child.parent_ids = unique_in_order([*child.parent_ids, parent_id])
    for transition in transitions:
        transition.from_context_id = context_redirect.get(transition.from_context_id, transition.from_context_id)
        transition.to_context_id = context_redirect.get(transition.to_context_id, transition.to_context_id)
    for facet in facets:
        facet.context_id = context_redirect.get(facet.context_id, facet.context_id)
    facets, facet_redirect = _merge_objects(facets, same["facet"], order)
    for claim in claims:
        if claim.scope_type == "context":
            claim.scope_id = context_redirect.get(claim.scope_id, claim.scope_id)
        claim.conditioning_facet_ids = unique_in_order([facet_redirect.get(x, x) for x in claim.conditioning_facet_ids])
    claims, _ = _merge_objects(claims, same["claim"], order)
    consolidated = {"status": "NEEDS_REVIEW" if warnings else "OK", "candidate_pairs": candidates, "decisions": batch.model_dump(), "unresolved_conflicts": warnings}
    write_json(paper_dir / "extraction" / "consolidated.json", consolidated)
    write_json(validated_path, {"contexts": [item.model_dump() for item in contexts], "facets": [item.model_dump() for item in facets], "transitions": [item.model_dump() for item in transitions], "claims": [item.model_dump(by_alias=True) for item in claims], "warnings": warnings})
    return contexts, facets, transitions, claims, warnings
