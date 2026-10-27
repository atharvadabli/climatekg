from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .canonicalize import canonicalize_claim_states
from .config import PIPELINE, ROOT
from .embeddings import effective_facets, embed_claims_and_states
from .extract import (
    _render_blocks,
    _split_prompt,
    compact_claim_facets,
    exact_deduplicate_claims,
    partition_claim_blocks,
    relevant_claim_contexts,
)
from .extraction_models import ClaimBatch
from .models import Claim, FinalPaper, SourceBlock
from .ollama import OllamaClient
from .utils import unique_in_order, write_json


def _scope_blocks(paper: FinalPaper, claims: list[Claim], neighbours: int = 1) -> list[SourceBlock]:
    """Return existing Claim evidence plus nearby passages from the same section."""
    ordered = sorted(paper.source_blocks, key=lambda item: item.order)
    positions = {block.id: index for index, block in enumerate(ordered)}
    selected: set[str] = {block_id for claim in claims for block_id in claim.evidence_block_ids}
    for block_id in list(selected):
        if block_id not in positions:
            continue
        position = positions[block_id]
        section = ordered[position].section_path
        for index in range(max(0, position - neighbours), min(len(ordered), position + neighbours + 1)):
            if ordered[index].section_path == section and ordered[index].block_type != "reference":
                selected.add(ordered[index].id)
    return [block for block in ordered if block.id in selected]


def _claim_from_candidate(
    paper_id: str,
    scope_type: str,
    scope_id: str,
    candidate,
    reachable_facets: set[str],
    block_order: dict[str, int],
) -> Claim:
    case_evidence = [block_id for case in candidate.analysis_cases for block_id in case.evidence_block_ids]
    return Claim(
        id=f"{paper_id}_CL_NEW",
        paper_id=paper_id,
        scope_type=scope_type,
        scope_id=scope_id,
        **{"from": candidate.from_.model_dump()},
        to=candidate.to,
        relation=candidate.relation,
        description=candidate.description,
        evidence_role=candidate.evidence_role,
        conditioning_facet_ids=[item for item in candidate.conditioning_facet_ids if item in reachable_facets],
        analysis_cases=[case.model_dump() for case in candidate.analysis_cases],
        analysis_comparison=candidate.analysis_comparison.model_dump() if candidate.analysis_comparison else None,
        evidence_block_ids=unique_in_order(candidate.evidence_block_ids + case_evidence, block_order),
    )


def reextract_atomic_claims(
    paper: FinalPaper,
    output_dir: Path,
    client: OllamaClient,
) -> tuple[FinalPaper, dict]:
    """Add atomic Claim decompositions without removing previously accepted Claims."""
    system, user = _split_prompt((ROOT / "prompts" / "claim_extraction.txt").read_text(encoding="utf-8"))
    config = PIPELINE["ollama"]["stages"]["claim_extraction"]
    by_scope: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for claim in paper.claims:
        by_scope[(claim.scope_type, claim.scope_id)].append(claim)
    block_order = {block.id: block.order for block in paper.source_blocks}
    new_claims: list[Claim] = []
    scope_metrics: list[dict] = []

    for (scope_type, scope_id), old_claims in sorted(by_scope.items()):
        available = (
            effective_facets(scope_id, paper.contexts, paper.facets)
            if scope_type == "context"
            else unique_facets_for_transition(paper, scope_id)
        )
        reachable_facets = {facet.id for facet in available}
        target = next(
            item.model_dump(exclude={"transition_embedding"})
            for item in paper.transitions
            if scope_type == "transition" and item.id == scope_id
        ) if scope_type == "transition" else next(
            item.model_dump(exclude={"retrieval_embedding"})
            for item in paper.contexts
            if item.id == scope_id
        )
        blocks = _scope_blocks(paper, old_claims)
        parts = partition_claim_blocks(blocks, PIPELINE["evidence_retrieval"]["claim_bundle_target_tokens"])
        scope_batches: list[ClaimBatch] = []
        for part_number, part in enumerate(parts, 1):
            part_dir = output_dir / paper.paper.id / "claims" / scope_id / "parts" / f"part{part_number:03d}"
            validated_path = part_dir / "validated.json"
            allowed = {block.id for block in part}
            if validated_path.exists():
                batch = ClaimBatch.model_validate_json(validated_path.read_text(encoding="utf-8"))
            else:
                request = user.format(
                    paper_id=paper.paper.id,
                    relevant_contexts=json.dumps(
                        relevant_claim_contexts(scope_id, scope_type, paper.contexts, paper.transitions),
                        ensure_ascii=False,
                    ),
                    available_scope_facets=json.dumps(compact_claim_facets(available), ensure_ascii=False),
                    target_scope=json.dumps(target, ensure_ascii=False),
                    evidence_blocks=_render_blocks(part),
                )
                batch = client.structured(
                    stage="claim_extraction",
                    system=system,
                    user=request,
                    schema=ClaimBatch,
                    model=PIPELINE["ollama"]["model"],
                    temperature=config["temperature"],
                    thinking=config["thinking"],
                    artifact_dir=part_dir,
                    paper_id=paper.paper.id,
                    input_block_ids=sorted(allowed),
                    retries=config["retries"],
                )
                write_json(validated_path, batch.model_dump(by_alias=True))
            if batch.scope_id != scope_id:
                raise ValueError(f"Atomic Claim batch used wrong scope: {batch.scope_id} != {scope_id}")
            for candidate in batch.claims:
                evidence = set(candidate.evidence_block_ids)
                evidence.update(block_id for case in candidate.analysis_cases for block_id in case.evidence_block_ids)
                if not evidence <= allowed:
                    raise ValueError(f"Atomic Claim batch used evidence outside its input: {scope_id}")
                if candidate.evidence_role in {"OWN_RESULT", "AUTHORS_INTERPRETATION_OF_OWN_RESULT"}:
                    new_claims.append(
                        _claim_from_candidate(
                            paper.paper.id,
                            scope_type,
                            scope_id,
                            candidate,
                            reachable_facets,
                            block_order,
                        )
                    )
            scope_batches.append(batch)
        scope_metrics.append(
            {
                "scope_id": scope_id,
                "scope_type": scope_type,
                "old_claim_count": len(old_claims),
                "new_candidate_count": sum(len(batch.claims) for batch in scope_batches),
                "input_block_ids": [block.id for block in blocks],
                "part_count": len(parts),
            }
        )

    combined = exact_deduplicate_claims([*paper.claims, *new_claims])
    states = canonicalize_claim_states(combined)
    embed_claims_and_states(client, combined, states)
    evidence_links = [
        {"object_id": item.id, "source_block_id": block_id}
        for items in (paper.contexts, paper.facets, paper.transitions, combined)
        for item in items
        for block_id in item.evidence_block_ids
    ]
    updated = paper.model_copy(
        update={
            "claims": combined,
            "states": states,
            "evidence_links": evidence_links,
            "metadata": {
                **paper.metadata,
                "atomic_claim_reextraction": {
                    "prompt_version": "claim_extraction_v7",
                    "strategy": "additive_existing_evidence_plus_same_section_neighbours",
                },
            },
        }
    )
    updated = FinalPaper.model_validate(updated.model_dump(by_alias=True))
    metrics = {
        "paper_id": paper.paper.id,
        "old_claim_count": len(paper.claims),
        "new_extracted_count": len(new_claims),
        "combined_claim_count": len(updated.claims),
        "scope_count": len(scope_metrics),
        "scopes": scope_metrics,
    }
    write_json(output_dir / paper.paper.id / "summary.json", metrics)
    return updated, metrics


def unique_facets_for_transition(paper: FinalPaper, transition_id: str):
    transition = next(item for item in paper.transitions if item.id == transition_id)
    facets = [
        *effective_facets(transition.from_context_id, paper.contexts, paper.facets),
        *effective_facets(transition.to_context_id, paper.contexts, paper.facets),
    ]
    return list({facet.id: facet for facet in facets}.values())
