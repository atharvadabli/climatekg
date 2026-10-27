from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from pydantic import Field

from .constants import INDEXING_PIPELINE, PROMPT_VERSIONS
from .models import FinalPaper, State, StateSemanticLink, StrictModel
from .ollama import OllamaClient
from .utils import cosine, normalize_text_key, write_json


class StateLinkCandidate(StrictModel):
    pair_id: str
    state_a_id: str
    state_b_id: str
    candidate_similarity: float
    evidence_a: list[str] = Field(default_factory=list)
    evidence_b: list[str] = Field(default_factory=list)
    claim_ids_a: list[str] = Field(default_factory=list)
    claim_ids_b: list[str] = Field(default_factory=list)


class StateLinkDecision(StrictModel):
    pair_id: str
    comparable: bool
    a_entails_b: bool
    b_entails_a: bool
    rationale: str


class StateLinkDecisionBatch(StrictModel):
    decisions: list[StateLinkDecision]


def relation_from_entailment(decision: StateLinkDecision) -> str:
    if not decision.comparable:
        return "unrelated"
    if decision.a_entails_b and decision.b_entails_a:
        return "equivalent_to"
    if decision.a_entails_b:
        return "narrower_than"
    if decision.b_entails_a:
        return "broader_than"
    return "uncertain"


def _tokens(value: str) -> set[str]:
    return set(normalize_text_key(value).replace("_", " ").split())


def structurally_supports_relation(left: State, right: State, relation: str) -> tuple[bool, str]:
    """Conservatively reject semantic links whose generated text contradicts the proposed relation."""
    left_concept, right_concept = _tokens(left.concept), _tokens(right.concept)
    left_state, right_state = _tokens(left.state), _tokens(right.state)
    concept_overlap = len(left_concept & right_concept) / max(1, len(left_concept | right_concept))
    state_overlap = len(left_state & right_state) / max(1, len(left_state | right_state))
    for marker in ("extreme", "mean", "median", "percentile", "anomaly"):
        if (marker in left_concept | left_state) != (marker in right_concept | right_state):
            return False, f"statistic_or_baseline_mismatch:{marker}"
    for marker in ("global", "root", "zone", "large-scale", "circulation", "surface"):
        if (marker in left_concept) != (marker in right_concept):
            return False, f"scope_or_component_mismatch:{marker}"
    if ("flux" in left_concept) != ("flux" in right_concept) and (
        "heating" in left_concept | right_concept or "temperature" in left_concept | right_concept
    ):
        return False, "physical_quantity_mismatch:flux"
    optimum = {"maximum", "maximized", "minimum", "minimized", "optimal", "earliest", "fastest"}
    if bool(left_state & optimum) != bool(right_state & optimum):
        return False, "optimum_vs_relative_change_mismatch"
    if relation == "equivalent_to":
        supported = (
            (left_concept == right_concept or concept_overlap >= 0.80)
            and (left_state == right_state or state_overlap >= 0.80)
        )
        return supported, "supported" if supported else "insufficient_bidirectional_lexical_support"
    specific_concept, general_concept = (
        (left_concept, right_concept) if relation == "narrower_than" else (right_concept, left_concept)
    )
    specific_state, general_state = (
        (left_state, right_state) if relation == "narrower_than" else (right_state, left_state)
    )
    concept_supported = general_concept <= specific_concept or concept_overlap >= 0.70
    state_supported = general_state <= specific_state or state_overlap >= 0.70
    supported = concept_supported and state_supported
    return supported, "supported" if supported else "insufficient_directional_lexical_support"


OPPOSITE_DIRECTIONS = {
    frozenset(("increase", "decrease")),
    frozenset(("strengthen", "weaken")),
    frozenset(("earlier", "later")),
    frozenset(("more_frequent", "less_frequent")),
}

DIRECTION_TOKENS = {
    "increase": {"increase", "increased", "increasing", "higher", "rise", "rising", "warming", "improvement", "improved", "stronger"},
    "decrease": {"decrease", "decreased", "decreasing", "lower", "decline", "reduced", "reduction", "cooling", "weaker"},
    "earlier": {"earlier", "advance", "advanced"},
    "later": {"later", "delay", "delayed"},
}
OPPOSITE_FAMILIES = {frozenset(("increase", "decrease")), frozenset(("earlier", "later"))}


def _direction_families(value: str) -> set[str]:
    tokens = set(normalize_text_key(value).replace("_", " ").split())
    return {family for family, words in DIRECTION_TOKENS.items() if tokens & words}


def _state_claim_evidence(papers: list[FinalPaper]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    evidence: dict[str, list[str]] = defaultdict(list)
    claim_ids: dict[str, list[str]] = defaultdict(list)
    for paper in papers:
        for claim in paper.claims:
            for endpoint, state in ((claim.from_, "source"), (claim.to, "target")):
                identifier = next(
                    (
                        item.id
                        for item in paper.states
                        if item.concept == endpoint.concept and item.state == endpoint.state
                    ),
                    None,
                )
                if identifier and claim.description not in evidence[identifier]:
                    evidence[identifier].append(f"{state}: {claim.description}")
                    claim_ids[identifier].append(claim.id)
    return evidence, claim_ids


def _directions_can_be_compared(left: str, right: str) -> bool:
    normalized = frozenset((normalize_text_key(left), normalize_text_key(right)))
    if normalized in OPPOSITE_DIRECTIONS:
        return False
    left_families, right_families = _direction_families(left), _direction_families(right)
    return not any(
        frozenset((left_family, right_family)) in OPPOSITE_FAMILIES
        for left_family in left_families
        for right_family in right_families
    )


def generate_state_link_candidates(
    papers: list[FinalPaper],
    *,
    top_k: int = 3,
    minimum_similarity: float = 0.82,
    examples_per_state: int = 3,
) -> tuple[dict[str, State], list[StateLinkCandidate]]:
    states = {state.id: state for paper in papers for state in paper.states}
    evidence, claim_ids = _state_claim_evidence(papers)
    candidates: dict[tuple[str, str], StateLinkCandidate] = {}
    ordered = sorted(states.values(), key=lambda item: item.id)
    for state in ordered:
        neighbours = sorted(
            (
                (max(0.0, cosine(state.concept_embedding or [], other.concept_embedding or [])), other)
                for other in ordered
                if other.id != state.id and _directions_can_be_compared(state.state, other.state)
            ),
            key=lambda item: (-item[0], item[1].id),
        )[:top_k]
        for similarity, other in neighbours:
            if similarity < minimum_similarity:
                continue
            left, right = sorted((state.id, other.id))
            key = (left, right)
            if key in candidates:
                continue
            pair_id = f"SL{len(candidates) + 1:06d}"
            candidates[key] = StateLinkCandidate(
                pair_id=pair_id,
                state_a_id=left,
                state_b_id=right,
                candidate_similarity=similarity,
                evidence_a=evidence.get(left, [])[:examples_per_state],
                evidence_b=evidence.get(right, [])[:examples_per_state],
                claim_ids_a=claim_ids.get(left, [])[:examples_per_state],
                claim_ids_b=claim_ids.get(right, [])[:examples_per_state],
            )
    return states, list(candidates.values())


def adjudicate_state_link_candidates(
    states: dict[str, State],
    candidates: list[StateLinkCandidate],
    client: OllamaClient,
    artifact_dir: Path,
    *,
    batch_size: int = 20,
) -> tuple[list[StateSemanticLink], list[dict]]:
    prompt = (Path(__file__).resolve().parents[1] / "prompts" / "state_semantic_link_adjudication.txt").read_text(encoding="utf-8")
    system, user = prompt.split("USER\n", 1)
    accepted: list[StateSemanticLink] = []
    audit: list[dict] = []
    by_id = {candidate.pair_id: candidate for candidate in candidates}
    cached_decisions: dict[str, StateLinkDecision] = {}
    for response_path in artifact_dir.rglob("*.attempt*.json") if artifact_dir.exists() else []:
        try:
            response = json.loads(response_path.read_text(encoding="utf-8"))
            cached_batch = StateLinkDecisionBatch.model_validate_json(response["message"]["content"])
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
        cached_decisions.update({decision.pair_id: decision for decision in cached_batch.decisions})
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset:offset + batch_size]
        batch_dir = artifact_dir / f"batch_{offset // batch_size + 1:04d}"
        payload = []
        for candidate in batch:
            left, right = states[candidate.state_a_id], states[candidate.state_b_id]
            payload.append(
                {
                    "pair_id": candidate.pair_id,
                    "state_a": {"concept": left.concept, "state": left.state},
                    "state_b": {"concept": right.concept, "state": right.state},
                    "evidence_a": candidate.evidence_a,
                    "evidence_b": candidate.evidence_b,
                }
            )
        missing = [candidate for candidate in batch if candidate.pair_id not in cached_decisions]
        if missing:
            missing_ids = {candidate.pair_id for candidate in missing}
            missing_payload = [item for item in payload if item["pair_id"] in missing_ids]
            result = client.structured(
                stage="state_semantic_link_adjudication",
                system=system.removeprefix("SYSTEM\n").strip(),
                user=user.format(candidate_pairs=json.dumps(missing_payload, ensure_ascii=False, indent=2)).strip(),
                schema=StateLinkDecisionBatch,
                model=INDEXING_PIPELINE["ollama"]["model"],
                temperature=0.0,
                thinking=INDEXING_PIPELINE["state_semantic_links"]["thinking"],
                artifact_dir=batch_dir,
                paper_id="CORPUS_STATE_LINKS",
                input_block_ids=[],
                retries=INDEXING_PIPELINE["ollama"]["retries"],
            )
            returned_missing = {decision.pair_id: decision for decision in result.decisions}
            if set(returned_missing) != missing_ids:
                raise ValueError(f"State-link adjudication returned mismatched pair IDs: expected={sorted(missing_ids)} returned={sorted(returned_missing)}")
            cached_decisions.update(returned_missing)
        returned = {candidate.pair_id: cached_decisions[candidate.pair_id] for candidate in batch}
        expected = {candidate.pair_id for candidate in batch}
        if set(returned) != expected:
            raise ValueError(f"State-link adjudication returned mismatched pair IDs: expected={sorted(expected)} returned={sorted(returned)}")
        for pair_id in sorted(expected):
            candidate, decision = by_id[pair_id], returned[pair_id]
            relation = relation_from_entailment(decision)
            left, right = states[candidate.state_a_id], states[candidate.state_b_id]
            structurally_supported, structural_reason = structurally_supports_relation(left, right, relation)
            accepted_relation = relation in {"equivalent_to", "narrower_than", "broader_than"} and structurally_supported
            row = {
                **candidate.model_dump(),
                **decision.model_dump(exclude={"pair_id"}),
                "relation": relation,
                "accepted": accepted_relation,
                "structural_review": structural_reason,
            }
            audit.append(row)
            if accepted_relation:
                accepted.append(
                    StateSemanticLink(
                        source_state_id=candidate.state_a_id,
                        target_state_id=candidate.state_b_id,
                        relation=relation,
                        candidate_similarity=candidate.candidate_similarity,
                        decision_method="llm_adjudicated",
                        rationale=decision.rationale,
                        source_claim_ids=candidate.claim_ids_a,
                        target_claim_ids=candidate.claim_ids_b,
                    )
                )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        artifact_dir / "decisions.json",
        {
            "prompt_version": PROMPT_VERSIONS["state_semantic_link_adjudication"],
            "candidate_count": len(candidates),
            "accepted_count": len(accepted),
            "decisions": audit,
        },
    )
    return accepted, audit
