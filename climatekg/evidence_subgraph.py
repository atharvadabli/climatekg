from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from .canonicalize import state_id
from .models import Claim, QuerySpec, StateSemanticLink
from .utils import cosine


def query_requirements(spec: QuerySpec) -> list[dict[str, str]]:
    """Return independently matchable parts of a parsed question."""
    requirements: list[dict[str, str]] = []

    def add(identifier: str, kind: str, text: str | None) -> None:
        if text and text.strip():
            requirements.append({"id": identifier, "kind": kind, "text": text.strip()})

    if spec.source:
        add("source", "source", f"{spec.source.concept} {spec.source.state}")
    if spec.target:
        add("target", "target", f"{spec.target.concept} {spec.target.state}")
    add("intervention", "intervention", spec.intervention_description)
    for case in spec.analysis_cases:
        add(f"case:{case.id}", "analysis_case", case.label)
    for facet in spec.context.facets:
        add(f"facet:{facet.id}", "context", f"{facet.notion}. {facet.description}")
    add("question", "question", spec.user_question)
    return requirements


def _claim_state_ids(claim: Claim) -> tuple[str, str]:
    return (
        state_id(claim.from_.concept, claim.from_.state),
        state_id(claim.to.concept, claim.to.state),
    )


def _exact_connections(claim_ids: list[str], claims: dict[str, Claim]) -> list[dict[str, str]]:
    endpoints = {claim_id: _claim_state_ids(claims[claim_id]) for claim_id in claim_ids}
    connections = []
    for left_id in claim_ids:
        left_to = endpoints[left_id][1]
        for right_id in claim_ids:
            if left_id != right_id and left_to == endpoints[right_id][0]:
                connections.append(
                    {
                        "from_claim_id": left_id,
                        "to_claim_id": right_id,
                        "state_id": left_to,
                        "connection_type": "exact_state",
                    }
                )
    return connections


def _semantic_connections(
    claim_ids: list[str],
    claims: dict[str, Claim],
    links: list[StateSemanticLink],
) -> list[dict[str, str]]:
    endpoints = {claim_id: _claim_state_ids(claims[claim_id]) for claim_id in claim_ids}
    by_pair: dict[frozenset[str], StateSemanticLink] = {
        frozenset((link.source_state_id, link.target_state_id)): link for link in links
    }
    connections = []
    for left_id in claim_ids:
        left_to = endpoints[left_id][1]
        for right_id in claim_ids:
            if left_id == right_id or left_to == endpoints[right_id][0]:
                continue
            right_from = endpoints[right_id][0]
            link = by_pair.get(frozenset((left_to, right_from)))
            if link is not None:
                connections.append(
                    {
                        "from_claim_id": left_id,
                        "to_claim_id": right_id,
                        "source_state_id": left_to,
                        "target_state_id": right_from,
                        "connection_type": link.relation,
                    }
                )
    return connections


def _components(claim_ids: list[str], connections: list[dict[str, str]]) -> list[list[str]]:
    neighbours: dict[str, set[str]] = defaultdict(set)
    for edge in connections:
        neighbours[edge["from_claim_id"]].add(edge["to_claim_id"])
        neighbours[edge["to_claim_id"]].add(edge["from_claim_id"])
    remaining = set(claim_ids)
    components = []
    while remaining:
        root = min(remaining)
        pending = deque([root])
        component = []
        while pending:
            claim_id = pending.popleft()
            if claim_id not in remaining:
                continue
            remaining.remove(claim_id)
            component.append(claim_id)
            pending.extend(sorted(neighbours[claim_id] & remaining))
        components.append(sorted(component))
    return sorted(components, key=lambda item: (-len(item), item))


def select_evidence_subgraph(
    spec: QuerySpec,
    claims: dict[str, Claim],
    ranked: list[dict[str, Any]],
    requirements: list[dict[str, str]],
    requirement_vectors: list[list[float]],
    exact_paths: list[dict[str, Any]],
    config: dict[str, Any],
    semantic_links: list[StateSemanticLink] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a compact evidence set without treating similarity as causality."""
    eligible = [
        row
        for row in ranked
        if row.get("applicability_status") != "incompatible"
        and row["claim_id"] in claims
    ]
    by_id = {row["claim_id"]: row for row in eligible}
    requirement_scores: dict[str, dict[str, float]] = {}
    requirement_thresholds: dict[str, float] = {}
    for requirement, vector in zip(requirements, requirement_vectors):
        scores = {
            row["claim_id"]: max(0.0, cosine(vector, claims[row["claim_id"]].claim_embedding or []))
            for row in eligible
        }
        requirement_scores[requirement["id"]] = scores
        best = max(scores.values(), default=0.0)
        requirement_thresholds[requirement["id"]] = max(
            config["minimum_requirement_similarity"],
            best - config["best_match_margin"],
        )

    selected: list[str] = []
    selection_rows: list[dict[str, Any]] = []
    covered: set[str] = set()
    max_claims = config["max_claims"]

    def add(claim_id: str, reason: str, **details: Any) -> None:
        if claim_id in by_id and claim_id not in selected and len(selected) < max_claims:
            selected.append(claim_id)
            selection_rows.append({"claim_id": claim_id, "reason": reason, **details})

    def newly_covered(claim_id: str) -> list[str]:
        return [
            requirement["id"]
            for requirement in requirements
            if requirement["id"] not in covered
            and requirement_scores[requirement["id"]].get(claim_id, 0.0)
            >= requirement_thresholds[requirement["id"]]
        ]

    # Start with the strongest query matches. Atomic mechanism steps from one paper are
    # often semantically similar; rewarding novelty here can displace the actual chain.
    for row in eligible[: config.get("relevance_seed_claims", 4)]:
        add(row["claim_id"], "query_relevance_seed", R_claim=row["R_claim"])

    # Give every independently requested part at least one opportunity to contribute
    # evidence. This is a ranking operation, not a claim that the parts are connected.
    for requirement in requirements:
        identifier = requirement["id"]
        candidates = sorted(
            (
                (score, claim_id)
                for claim_id, score in requirement_scores[identifier].items()
                if score >= requirement_thresholds[identifier]
            ),
            key=lambda item: (-item[0], -by_id[item[1]]["R_claim"], item[1]),
        )
        for score, claim_id in candidates[: config.get("per_requirement_seed_claims", 1)]:
            add(claim_id, "requirement_seed", requirement_id=identifier, similarity=score)

    # Exact paths are useful only when their Claims remain close to the query. Generic
    # paths must not reserve evidence slots merely because their endpoint strings join.
    best_relevance = eligible[0]["R_claim"] if eligible else 0.0
    exact_floor = best_relevance - config.get("exact_path_relevance_margin", 0.12)
    for path in exact_paths:
        path_ids = [claim_id for claim_id in path.get("claim_ids", []) if claim_id in by_id]
        if path_ids and min(by_id[claim_id]["R_claim"] for claim_id in path_ids) >= exact_floor:
            for claim_id in path_ids:
                add(claim_id, "relevant_exact_path", R_claim=by_id[claim_id]["R_claim"])

    # Expand within papers that supplied a strong seed. This preserves neighboring
    # atomic steps without assuming a causal edge between merely similar States.
    seed_papers = {claims[claim_id].paper_id for claim_id in selected}
    paper_floor = best_relevance - config.get("seed_paper_relevance_margin", 0.12)
    per_paper = config.get("per_seed_paper_claims", 6)
    for paper_id in sorted(seed_papers):
        retained = 0
        for row in eligible:
            claim_id = row["claim_id"]
            if claims[claim_id].paper_id != paper_id or row["R_claim"] < paper_floor:
                continue
            add(claim_id, "seed_paper_expansion", R_claim=row["R_claim"])
            retained += 1
            if retained >= per_paper or len(selected) >= max_claims:
                break

    for claim_id in selected:
        covered.update(newly_covered(claim_id))

    connections = _exact_connections(selected, claims)
    semantic_connections = _semantic_connections(selected, claims, semantic_links or [])
    requirement_report = []
    for requirement in requirements:
        identifier = requirement["id"]
        matches = sorted(
            (
                {"claim_id": claim_id, "similarity": requirement_scores[identifier].get(claim_id, 0.0)}
                for claim_id in selected
                if requirement_scores[identifier].get(claim_id, 0.0) >= requirement_thresholds[identifier]
            ),
            key=lambda item: (-item["similarity"], item["claim_id"]),
        )
        requirement_report.append(
            {
                **requirement,
                "threshold": requirement_thresholds[identifier],
                "covered": bool(matches),
                "matches": matches,
            }
        )

    paths = []
    for claim_id in selected:
        row = by_id[claim_id]
        paths.append(
            {
                "claim_ids": [claim_id],
                "state_ids": list(_claim_state_ids(claims[claim_id])),
                "evidence_lane": "evidence_subgraph",
                "A_path": row.get("A_claim"),
                "C_path": 1.0,
                "M_path": row["R_claim"],
                "length_factor": 1.0,
                "R_path": row["R_claim"] * (row["A_claim"] if row.get("A_claim") is not None else 1.0),
                "context_unknown": row.get("A_claim") is None,
                "coherence_unknown": False,
            }
        )
    report = {
        "claim_ids": selected,
        "selections": selection_rows,
        "exact_connections": connections,
        "semantic_connections": semantic_connections,
        "components": _components(selected, [*connections, *semantic_connections]),
        "requirements": requirement_report,
        "uncovered_requirement_ids": [item["id"] for item in requirement_report if not item["covered"]],
    }
    return paths, report


def assemble_subgraph_evidence_paths(
    exact_paths: list[dict[str, Any]],
    claim_paths: list[dict[str, Any]],
    *,
    graph_limit: int,
    claim_limit: int,
) -> list[dict[str, Any]]:
    """Combine exact chains and atomic evidence in query-relevance order."""
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for lane, source_paths, limit in (
        ("graph", exact_paths, graph_limit),
        ("evidence_subgraph", claim_paths, claim_limit),
    ):
        retained = 0
        for path in source_paths:
            key = tuple(path["claim_ids"])
            if key in seen:
                continue
            candidates.append({**path, "evidence_lane": lane})
            seen.add(key)
            retained += 1
            if retained >= limit:
                break
    return sorted(candidates, key=evidence_path_sort_key)


def evidence_path_sort_key(path: dict[str, Any]) -> tuple[Any, ...]:
    """Order accepted evidence without collapsing relevance into applicability."""
    return (
        -path.get("M_path", path.get("R_path", 0.0)),
        -path.get("R_path", 0.0),
        len(path["claim_ids"]),
        tuple(path["claim_ids"]),
    )


def select_balanced_compound_paths(
    paths_by_subquery: list[list[dict[str, Any]]],
    *,
    max_claims: int,
    max_paths_per_subquery: int,
) -> list[list[dict[str, Any]]]:
    """Pack compound evidence fairly without concatenating every child result."""
    selected: list[list[dict[str, Any]]] = [[] for _ in paths_by_subquery]
    selected_claims: set[str] = set()
    for depth in range(max_paths_per_subquery):
        for number, paths in enumerate(paths_by_subquery):
            if depth >= len(paths):
                continue
            path = paths[depth]
            key = tuple(path.get("claim_ids", []))
            if not key:
                continue
            new_claims = set(key) - selected_claims
            if len(selected_claims) + len(new_claims) > max_claims:
                continue
            selected[number].append(path)
            selected_claims.update(new_claims)
    return selected
