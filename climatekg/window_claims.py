"""Text-first Claim extraction with an unchanged study-setting registry."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .config import PIPELINE, ROOT
from .constants import OLLAMA_CONTEXT_TOKENS
from .extract import (
    _render_blocks, _split_prompt, effective_facet_ids, exact_deduplicate_claims,
    partition_claim_blocks,
)
from .extraction_models import WindowClaimBatch, window_claim_schema
from .models import Claim
from .utils import token_count, unique_in_order, write_json


def window_registry(contexts, transitions, facets):
    return {
        "contexts": [item.model_dump(include={"id", "label", "parent_ids", "aliases", "spatial_support"}) for item in contexts],
        "transitions": [item.model_dump(include={"id", "label", "description", "aliases", "from_context_id", "to_context_id"}) for item in transitions],
        "facets": [item.model_dump(include={"id", "context_id", "domain", "notion", "description"})
                   for item in facets if item.origin == "reported"],
    }


def scope_facets(contexts, transitions, facets):
    allowed = {
        ("context", item.id): {facet.id for facet in effective_facet_ids(item.id, contexts, facets)
                              if facet.origin == "reported"}
        for item in contexts
    }
    for item in transitions:
        allowed[("transition", item.id)] = (
            allowed[("context", item.from_context_id)] | allowed[("context", item.to_context_id)]
        )
    return allowed


def validate_window_batch(batch, allowed_blocks, allowed_scopes):
    """Check identities, not scientific wording; never silently discard bad records."""
    for claim in batch.claims:
        scope = (claim.scope_type, claim.scope_id)
        if scope not in allowed_scopes:
            raise ValueError(f"Unknown study scope: {scope}")
        evidence = set(claim.evidence_block_ids)
        if not evidence:
            raise ValueError("Claim has no supporting passage")
        for case in claim.analysis_cases:
            if not case.evidence_block_ids:
                raise ValueError(f"Analysis case has no supporting passage: {case.label}")
            evidence.update(case.evidence_block_ids)
        if not evidence <= allowed_blocks:
            raise ValueError(f"Evidence outside supplied window: {sorted(evidence - allowed_blocks)}")
        if claim.analysis_comparison:
            labels = {case.label for case in claim.analysis_cases}
            if not set(claim.analysis_comparison.case_labels) <= labels:
                raise ValueError("Comparison refers to an unknown analysis case")


def extract_window_claims(paper, contexts, transitions, facets, blocks, paper_dir: Path, client):
    """Replace the Claim pass; existing Claims are neither inputs nor retained outputs."""
    started = time.perf_counter()
    output = paper_dir / "extraction" / "window_claims"
    system, template = _split_prompt((ROOT / "prompts/window_claim_extraction.txt").read_text(encoding="utf-8"))
    registry = json.dumps(window_registry(contexts, transitions, facets), ensure_ascii=False)
    config = PIPELINE["evidence_retrieval"]
    generation = PIPELINE["ollama"]["stages"]["claim_extraction"]
    schema_text = json.dumps(WindowClaimBatch.model_json_schema())
    overhead = token_count(system + template.format(paper_id=paper.id, registry=registry, evidence_blocks="") + schema_text)
    budget = min(config["window_claim_target_tokens"],
                 OLLAMA_CONTEXT_TOKENS - config["window_claim_response_reserve_tokens"] - overhead)
    if budget <= 0:
        raise ValueError("Study registry exceeds window input budget; no passages were truncated")
    eligible = [block for block in blocks if block.block_type not in {"reference", "title", "heading"}]
    parts = partition_claim_blocks(eligible, budget) if eligible else []
    if any(token_count(_render_blocks(part)) > budget for part in parts):
        raise ValueError("SourceBlock exceeds window budget; split the SourceBlock before extraction")
    allowed_scopes = scope_facets(contexts, transitions, facets)
    order = {block.id: block.order for block in blocks}
    report = {"paper_id": paper.id, "status": "running", "budget_tokens": budget,
              "token_counter": "o200k_base (budget estimate, not Qwen native)",
              "eligible_block_ids": [block.id for block in eligible],
              "excluded_blocks": [{"id": b.id, "reason": b.block_type} for b in blocks if b not in eligible],
              "windows": [], "ambiguities": []}
    write_json(output / "coverage.json", report)
    claims, hints = [], []
    for number, part in enumerate(parts, 1):
        folder = output / f"window{number:03d}"
        request = template.format(paper_id=paper.id, registry=registry, evidence_blocks=_render_blocks(part))
        schema = window_claim_schema([b.id for b in part])
        schema_text = json.dumps(schema.model_json_schema())
        if token_count(system + request + schema_text) + config["window_claim_response_reserve_tokens"] > OLLAMA_CONTEXT_TOKENS:
            raise ValueError("Complete request exceeds input budget; no content was truncated")
        fingerprint = hashlib.sha256(json.dumps({"system": system, "user": request,
            "schema": schema_text, "generation": generation, "model": PIPELINE["ollama"]["model"],
            "num_ctx": OLLAMA_CONTEXT_TOKENS}, sort_keys=True).encode()).hexdigest()
        cache = folder / "validated.json"
        signature = folder / "fingerprint.json"
        cached = cache.exists() and signature.exists() and json.loads(signature.read_text()) == fingerprint
        window_started = time.perf_counter()
        print(f"{paper.id} window {number}/{len(parts)}: {len(part)} blocks; cached={cached}", flush=True)
        try:
            if cached:
                batch = schema.model_validate_json(cache.read_text(encoding="utf-8"))
            else:
                batch = client.structured(stage="window_claim_extraction", system=system, user=request,
                    schema=schema, model=PIPELINE["ollama"]["model"],
                    temperature=generation["temperature"], thinking=generation["thinking"],
                    artifact_dir=folder, paper_id=paper.id, input_block_ids=[b.id for b in part],
                    retries=generation["retries"])
            write_json(folder / "candidate.json", batch.model_dump(by_alias=True))
            validate_window_batch(batch, {b.id for b in part}, allowed_scopes)
        except Exception as exc:
            write_json(folder / f"failure_{time.time_ns()}.json", {"error": str(exc), "window": number})
            report.update(status="failed", failed_window=number, error=str(exc))
            write_json(output / "coverage.json", report)
            raise
        write_json(cache, batch.model_dump(by_alias=True))
        write_json(signature, fingerprint)
        removed_links = []
        for candidate_number, candidate in enumerate(batch.claims, 1):
            if candidate.evidence_role not in {"OWN_RESULT", "AUTHORS_INTERPRETATION_OF_OWN_RESULT"}:
                continue
            values = candidate.model_dump(by_alias=True)
            reachable = allowed_scopes[(candidate.scope_type, candidate.scope_id)]
            # Spec 96.9 removes invalid conditioning links, not the supported Claim.
            values["conditioning_facet_ids"] = [fid for fid in candidate.conditioning_facet_ids if fid in reachable]
            removed_links.extend({"candidate_number": candidate_number, "scope_id": candidate.scope_id,
                                  "facet_id": fid, "reason": "not_reachable_from_scope"}
                                 for fid in candidate.conditioning_facet_ids if fid not in reachable)
            values["evidence_block_ids"] = unique_in_order(candidate.evidence_block_ids +
                [bid for case in candidate.analysis_cases for bid in case.evidence_block_ids], order)
            claims.append(Claim(id=f"{paper.id}_CL{len(claims)+1:03d}", paper_id=paper.id, **values))
        hints.extend(batch.unmapped_context_hints)
        report["ambiguities"].extend(batch.ambiguities)
        report["windows"].append({"number": number, "block_ids": [b.id for b in part],
            "cached": cached, "elapsed_seconds": time.perf_counter() - window_started,
            "candidate_count": len(batch.claims), "unmapped_context_hints": batch.unmapped_context_hints,
            "removed_conditioning_links": removed_links})
        write_json(output / "coverage.json", report)
    claims = exact_deduplicate_claims(claims)
    report.update(status="complete", claim_count=len(claims), elapsed_seconds=time.perf_counter() - started)
    report["saved_llm_attempt_seconds"] = sum(
        json.loads(path.read_text(encoding="utf-8")).get("elapsed_seconds", 0)
        for path in output.glob("window*/*.metrics.json")
    )
    write_json(output / "coverage.json", report)
    write_json(output / "claims.json", [claim.model_dump(by_alias=True) for claim in claims])
    return claims, unique_in_order(hints)
