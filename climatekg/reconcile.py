from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .canonicalize import canonical_direction
from .config import PIPELINE, ROOT
from .extract import _render_blocks, _split_prompt, effective_facet_ids, evidence_bundle
from .extraction_models import ClaimBatch, ContextReconciliationBatch, FacetBatch
from .models import Claim, Context, Facet, Paper, SourceBlock, Transition
from .ollama import OllamaClient
from .utils import normalize_text_key, unique_in_order, write_json


POLARITY = {"increase": 1, "higher": 1, "warming": 1, "decrease": -1, "lower": -1, "cooling": -1, "no_detectable_change": 0}


def _context_component(scope_id: str, scope_type: str, contexts: list[Context], transitions: list[Transition]) -> list[str]:
    context_ids = {item.id for item in contexts}
    if scope_type == "transition":
        transition = next((item for item in transitions if item.id == scope_id), None)
        seeds = {transition.from_context_id, transition.to_context_id} if transition else set()
    else:
        seeds = {scope_id} if scope_id in context_ids else set()
    neighbors: dict[str, set[str]] = defaultdict(set)
    for context in contexts:
        for parent_id in context.parent_ids:
            if parent_id in context_ids:
                neighbors[context.id].add(parent_id)
                neighbors[parent_id].add(context.id)
    pending = list(seeds)
    component = set(seeds)
    while pending:
        for neighbor in neighbors[pending.pop()]:
            if neighbor not in component:
                component.add(neighbor)
                pending.append(neighbor)
    return sorted(component)


def reversal_hints(claims: list[Claim], contexts: list[Context] | None = None, transitions: list[Transition] | None = None) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[Claim]] = defaultdict(list)
    for claim in claims:
        key = (claim.scope_id, claim.relation, normalize_text_key(claim.from_.concept), normalize_text_key(claim.to.concept))
        groups[key].append(claim)
    hints = []
    for group in groups.values():
        polarities = {POLARITY.get(canonical_direction(item.to.state), POLARITY.get(normalize_text_key(item.to.state))) for item in group}
        polarities.discard(None)
        if not ({1, -1} <= polarities or (0 in polarities and len(polarities) > 1)):
            continue
        for claim in group:
            hint = {"hint_id": f"RH{len(hints)+1:03d}", "text": f"Distinct outcome regime for Claim {claim.id}: {claim.description}", "affected_claim_ids": [claim.id], "evidence_block_ids": claim.evidence_block_ids}
            if contexts is not None and transitions is not None:
                hint["allowed_context_ids"] = _context_component(claim.scope_id, claim.scope_type, contexts, transitions)
            hints.append(hint)
    return hints


def _next_context_id(paper_id: str, contexts: list[Context]) -> str:
    used = {item.id for item in contexts}
    number = 1
    while f"{paper_id}_C{number:03d}" in used:
        number += 1
    return f"{paper_id}_C{number:03d}"


def _hint_bundle(hint: dict[str, Any], blocks: list[SourceBlock]) -> list[SourceBlock]:
    orders = {item.order for item in blocks if item.id in hint["evidence_block_ids"]}
    orders.update(order + delta for order in list(orders) for delta in (-1, 1))
    return [item for item in blocks if item.order in orders and item.block_type != "reference"]


def _validate_reconciliation_batch(batch: ContextReconciliationBatch, hints: list[dict[str, Any]], context_ids: set[str]) -> None:
    hint_by_id = {item["hint_id"]: item for item in hints}
    if {item.hint_id for item in batch.decisions} != set(hint_by_id):
        raise ValueError("decisions do not cover every hint exactly once")
    for decision in batch.decisions:
        hint = hint_by_id[decision.hint_id]
        allowed_claims = set(hint["affected_claim_ids"])
        if not set(decision.affected_claim_ids) <= allowed_claims or not set(decision.evidence_block_ids) <= set(hint["evidence_block_ids"]):
            raise ValueError(f"invalid Claim or evidence references for {decision.hint_id}")
        if decision.action in ("ATTACH_TO_EXISTING_CONTEXT", "ADD_CHILD_CONTEXT", "ADD_INDEPENDENT_CONTEXT", "UNRESOLVED") and set(decision.affected_claim_ids) != allowed_claims:
            raise ValueError(f"affected Claims are incomplete for {decision.hint_id}")
        if decision.hint_id.startswith("RH") and decision.action == "IGNORE_AS_NOT_A_CONTEXT":
            raise ValueError(f"detected outcome reversal cannot be ignored ({decision.hint_id})")
        if decision.action == "ATTACH_TO_EXISTING_CONTEXT":
            if decision.existing_context_id not in context_ids:
                raise ValueError(f"unknown Context {decision.existing_context_id}")
            if decision.hint_id.startswith("RH") and decision.existing_context_id not in hint["allowed_context_ids"]:
                raise ValueError(f"Context branch mismatch for {decision.hint_id}")
        if decision.action in ("ADD_CHILD_CONTEXT", "ADD_INDEPENDENT_CONTEXT"):
            if decision.action == "ADD_CHILD_CONTEXT" and decision.parent_context_id not in context_ids:
                raise ValueError(f"unknown parent for {decision.hint_id}")
            if decision.hint_id.startswith("RH") and (decision.action == "ADD_INDEPENDENT_CONTEXT" or decision.parent_context_id not in hint["allowed_context_ids"]):
                raise ValueError(f"Context branch mismatch for {decision.hint_id}")


def _extract_new_scope(paper: Paper, context: Context, contexts: list[Context], transitions: list[Transition], facets: list[Facet], blocks: list[SourceBlock], bundle: list[SourceBlock], paper_dir: Path, client: OllamaClient) -> tuple[list[Facet], list[Claim]]:
    registry = {item.id: {"label": item.label, "parent_ids": item.parent_ids, "aliases": item.aliases} for item in contexts}
    parent_facets = [item for item in effective_facet_ids(context.id, contexts, facets) if item.context_id != context.id]
    facet_system, facet_user = _split_prompt((ROOT / "prompts" / "facet_extraction.txt").read_text(encoding="utf-8"))
    facet_request = facet_user.format(paper_id=paper.id, target_context=context.model_dump_json(), context_registry=json.dumps(registry), parent_facets=json.dumps([item.model_dump() for item in parent_facets]), existing_target_facets="[]", evidence_blocks=_render_blocks(bundle))
    facet_cfg = PIPELINE["ollama"]["stages"]["facet_extraction"]
    facet_batch = client.structured(stage="reconciliation_facet_extraction", system=facet_system, user=facet_request, schema=FacetBatch, model=PIPELINE["ollama"]["model"], temperature=facet_cfg["temperature"], thinking=facet_cfg["thinking"], artifact_dir=paper_dir / "extraction" / "reconciliation" / context.id / "facets", paper_id=paper.id, input_block_ids=[item.id for item in bundle], retries=facet_cfg["retries"])
    allowed_blocks = {item.id for item in bundle}
    if facet_batch.context_id != context.id or any(not set(item.evidence_block_ids) <= allowed_blocks for item in facet_batch.facets):
        raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: invalid Facet references for {context.id}")
    new_facets = [Facet(id=f"{paper.id}_F{len(facets)+index:03d}", context_id=context.id, domain=item.domain, notion=item.notion, description=item.description, origin="reported", source={"type": "paper", "id": paper.id}, evidence_block_ids=item.evidence_block_ids) for index, item in enumerate(facet_batch.facets, 1)]
    available = effective_facet_ids(context.id, contexts, [*facets, *new_facets])
    claim_system, claim_user = _split_prompt((ROOT / "prompts" / "claim_extraction.txt").read_text(encoding="utf-8"))
    claim_request = claim_user.format(paper_id=paper.id, context_registry=json.dumps(registry), transitions=json.dumps([item.model_dump() for item in transitions]), available_scope_facets=json.dumps([item.model_dump() for item in available]), target_scope=context.model_dump_json(), evidence_blocks=_render_blocks(bundle))
    claim_cfg = PIPELINE["ollama"]["stages"]["claim_extraction"]
    claim_batch = client.structured(stage="reconciliation_claim_extraction", system=claim_system, user=claim_request, schema=ClaimBatch, model=PIPELINE["ollama"]["model"], temperature=claim_cfg["temperature"], thinking=claim_cfg["thinking"], artifact_dir=paper_dir / "extraction" / "reconciliation" / context.id / "claims", paper_id=paper.id, input_block_ids=[item.id for item in bundle], retries=claim_cfg["retries"])
    reachable = {item.id for item in available}
    if claim_batch.scope_id != context.id or any(not set(item.evidence_block_ids) <= allowed_blocks for item in claim_batch.claims):
        raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: invalid Claim references for {context.id}")
    new_claims = []
    for item in claim_batch.claims:
        if item.evidence_role not in ("OWN_RESULT", "AUTHORS_INTERPRETATION_OF_OWN_RESULT"):
            continue
        new_claims.append(Claim(id=f"{paper.id}_CL{len(new_claims)+1:03d}", paper_id=paper.id, scope_type="context", scope_id=context.id, **{"from": item.from_.model_dump()}, to=item.to, relation=item.relation, description=item.description, evidence_role=item.evidence_role, conditioning_facet_ids=[value for value in item.conditioning_facet_ids if value in reachable], evidence_block_ids=item.evidence_block_ids))
    return new_facets, new_claims


def reconcile_contexts(paper: Paper, contexts: list[Context], transitions: list[Transition], facets: list[Facet], claims: list[Claim], explicit_hints: list[str], blocks: list[SourceBlock], paper_dir: Path, client: OllamaClient) -> tuple[list[Context], list[Facet], list[Claim], list[dict[str, Any]]]:
    validated_path = paper_dir / "extraction" / "reconciliation" / "validated.json"
    if validated_path.exists():
        cached = json.loads(validated_path.read_text(encoding="utf-8"))
        return (
            [Context.model_validate(item) for item in cached["contexts"]],
            [Facet.model_validate(item) for item in cached["facets"]],
            [Claim.model_validate(item) for item in cached["claims"]],
            cached["unresolved"],
        )
    hints = reversal_hints(claims, contexts, transitions)
    for text in explicit_hints:
        bundle = evidence_bundle(blocks, [text], [], [], client)
        hints.append({"hint_id": f"EH{len(hints)+1:03d}", "text": text, "affected_claim_ids": [], "evidence_block_ids": [item.id for item in bundle]})
    if not hints:
        write_json(paper_dir / "extraction" / "reconciliation" / "report.json", {"status": "NOT_REQUIRED", "hints": []})
        return contexts, facets, claims, []
    by_block = {item.id: item for item in blocks}
    evidence_ids = unique_in_order([block_id for hint in hints for block_id in hint["evidence_block_ids"]])
    evidence = [by_block[block_id] for block_id in evidence_ids if block_id in by_block]
    system, user = _split_prompt((ROOT / "prompts" / "context_reconciliation.txt").read_text(encoding="utf-8"))
    registry = {item.id: {"label": item.label, "parent_ids": item.parent_ids, "aliases": item.aliases} for item in contexts}
    request = user.format(context_registry=json.dumps(registry), hints=json.dumps(hints), hint_evidence_blocks=_render_blocks(evidence))
    cfg = PIPELINE["ollama"]["stages"]["context_reconciliation"]
    batch = client.structured(stage="context_reconciliation", system=system, user=request, schema=ContextReconciliationBatch, model=PIPELINE["ollama"]["model"], temperature=cfg["temperature"], thinking=cfg["thinking"], artifact_dir=paper_dir / "extraction" / "reconciliation", paper_id=paper.id, input_block_ids=evidence_ids, retries=cfg["retries"])
    hint_by_id = {item["hint_id"]: item for item in hints}
    context_ids = {item.id for item in contexts}
    try:
        _validate_reconciliation_batch(batch, hints, context_ids)
    except ValueError as exc:
        valid_references = [{"hint_id": item["hint_id"], "affected_claim_ids": item["affected_claim_ids"], "evidence_block_ids": item["evidence_block_ids"], "allowed_context_ids": item.get("allowed_context_ids", sorted(context_ids))} for item in hints]
        repair_request = (
            f"{request}\n\n"
            "CORRECTION TASK\n\n"
            "The returned decisions used IDs outside the values allowed for their evidence hints. "
            "Return the complete JSON object again. Keep each decision action unchanged and correct only its reference fields.\n\n"
            f"VALIDATION ERROR\n{exc}\n\n"
            f"ALLOWED REFERENCES FOR EACH HINT\n{json.dumps(valid_references)}\n\n"
            f"PREVIOUS JSON OBJECT\n{batch.model_dump_json()}"
        )
        repair_cfg = PIPELINE["ollama"]["stages"]["context_reconciliation_reference_repair"]
        batch = client.structured(stage="context_reconciliation_reference_repair", system=system, user=repair_request, schema=ContextReconciliationBatch, model=PIPELINE["ollama"]["model"], temperature=repair_cfg["temperature"], thinking=repair_cfg["thinking"], artifact_dir=paper_dir / "extraction" / "reconciliation" / "reference_repair", paper_id=paper.id, input_block_ids=evidence_ids, retries=PIPELINE["ollama"]["final_repair_retries"])
        try:
            _validate_reconciliation_batch(batch, hints, context_ids)
        except ValueError as repair_exc:
            raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: {repair_exc}") from repair_exc
    unresolved: list[dict[str, Any]] = []
    remove_claim_ids: set[str] = set()
    for decision in batch.decisions:
        hint = hint_by_id[decision.hint_id]
        allowed_claims = set(hint["affected_claim_ids"])
        if not set(decision.affected_claim_ids) <= allowed_claims or not set(decision.evidence_block_ids) <= set(hint["evidence_block_ids"]):
            raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: invalid decision references for {decision.hint_id}")
        if decision.action in ("ATTACH_TO_EXISTING_CONTEXT", "ADD_CHILD_CONTEXT", "ADD_INDEPENDENT_CONTEXT", "UNRESOLVED") and set(decision.affected_claim_ids) != allowed_claims:
            raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: affected Claims are incomplete for {decision.hint_id}")
        if decision.hint_id.startswith("RH") and decision.action == "IGNORE_AS_NOT_A_CONTEXT":
            raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: a detected outcome reversal cannot be ignored ({decision.hint_id})")
        if decision.action == "ATTACH_TO_EXISTING_CONTEXT":
            if decision.existing_context_id not in context_ids:
                raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: unknown Context {decision.existing_context_id}")
            if decision.hint_id.startswith("RH") and decision.existing_context_id not in hint["allowed_context_ids"]:
                raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: Context branch mismatch for {decision.hint_id}")
            for claim in claims:
                if claim.id in decision.affected_claim_ids:
                    claim.scope_type, claim.scope_id = "context", decision.existing_context_id
        elif decision.action in ("ADD_CHILD_CONTEXT", "ADD_INDEPENDENT_CONTEXT"):
            if not decision.new_context_label or not decision.evidence_block_ids:
                raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: incomplete new Context {decision.hint_id}")
            parents = [decision.parent_context_id] if decision.action == "ADD_CHILD_CONTEXT" else []
            if any(parent not in context_ids for parent in parents):
                raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: unknown parent for {decision.hint_id}")
            if decision.hint_id.startswith("RH"):
                if decision.action == "ADD_INDEPENDENT_CONTEXT" or decision.parent_context_id not in hint["allowed_context_ids"]:
                    raise ValueError(f"FAILED_CONTEXT_RECONCILIATION: Context branch mismatch for {decision.hint_id}")
            context = Context(id=_next_context_id(paper.id, contexts), paper_id=paper.id, parent_ids=parents, label=decision.new_context_label, aliases=decision.aliases, evidence_block_ids=decision.evidence_block_ids)
            contexts.append(context)
            context_ids.add(context.id)
            bundle = _hint_bundle(hint, blocks)
            new_facets, new_claims = _extract_new_scope(paper, context, contexts, transitions, facets, blocks, bundle, paper_dir, client)
            facets.extend(new_facets)
            remove_claim_ids.update(decision.affected_claim_ids)
            if new_claims:
                for index, claim in enumerate(new_claims, 1):
                    claim.id = f"{paper.id}_RCL{len(claims)+index:03d}"
                claims.extend(new_claims)
            else:
                unresolved.append({"type": "reconciliation_empty_scope", "hint_id": decision.hint_id, "context_id": context.id})
        elif decision.action == "UNRESOLVED":
            remove_claim_ids.update(decision.affected_claim_ids)
            unresolved.append({"type": "unresolved_context_hint", "hint_id": decision.hint_id, "text": hint["text"]})
    claims = [item for item in claims if item.id not in remove_claim_ids]
    for index, claim in enumerate(claims, 1):
        claim.id = f"{paper.id}_CL{index:03d}"
    write_json(paper_dir / "extraction" / "reconciliation" / "report.json", {"status": "NEEDS_REVIEW" if unresolved else "OK", "hints": hints, "decisions": batch.model_dump(), "unresolved": unresolved})
    write_json(validated_path, {"contexts": [item.model_dump() for item in contexts], "facets": [item.model_dump() for item in facets], "claims": [item.model_dump(by_alias=True) for item in claims], "unresolved": unresolved})
    return contexts, facets, claims, unresolved
