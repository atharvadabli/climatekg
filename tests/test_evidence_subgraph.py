from __future__ import annotations

from climatekg.evidence_subgraph import (
    assemble_subgraph_evidence_paths,
    query_requirements,
    select_balanced_compound_paths,
    select_evidence_subgraph,
)
from climatekg.models import Claim, ClaimEndpoint, QueryContext, QuerySpec


def claim(identifier: str, paper_id: str, source: str, target: str, embedding: list[float]) -> Claim:
    return Claim(
        id=identifier,
        paper_id=paper_id,
        scope_type="context",
        scope_id=f"{paper_id}_C1",
        **{
            "from": ClaimEndpoint(concept=source, state="increase"),
            "to": ClaimEndpoint(concept=target, state="increase"),
        },
        relation="causal",
        description=f"{source} increases {target}.",
        evidence_role="OWN_RESULT",
        evidence_block_ids=[f"{paper_id}:B1"],
        claim_embedding=embedding,
    )


def test_evidence_subgraph_preserves_diverse_relevant_claims_without_inventing_edges() -> None:
    claims = {
        "C1": claim("C1", "P1", "surface contrast", "secondary circulation", [1.0, 0.0, 0.0]),
        "C2": claim("C2", "P1", "secondary circulation", "moisture transport", [0.7, 0.7, 0.0]),
        "C3": claim("C3", "P2", "moisture pooling", "deep convection", [0.0, 1.0, 0.0]),
        "C4": claim("C4", "P3", "surface albedo", "surface temperature", [0.0, 0.0, 1.0]),
    }
    ranked = [
        {"claim_id": identifier, "R_claim": score, "A_claim": 0.8, "applicability_status": "compatible_candidate"}
        for identifier, score in (("C1", 0.9), ("C4", 0.85), ("C2", 0.8), ("C3", 0.75))
    ]
    spec = QuerySpec(
        query_id="Q1",
        mode="a_to_b",
        context=QueryContext(),
        source=ClaimEndpoint(concept="surface contrast", state="increase"),
        target=ClaimEndpoint(concept="deep convection", state="increase"),
        user_question="How does surface contrast lead to moisture transport and deep convection?",
    )
    requirements = query_requirements(spec)
    vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.7, 0.7, 0.0]]
    config = {
        "max_claims": 3,
        "relevance_seed_claims": 1,
        "per_requirement_seed_claims": 1,
        "per_seed_paper_claims": 3,
        "seed_paper_relevance_margin": 0.2,
        "exact_path_relevance_margin": 0.2,
        "minimum_requirement_similarity": 0.3,
        "best_match_margin": 0.08,
    }

    paths, report = select_evidence_subgraph(spec, claims, ranked, requirements, vectors, [], config)

    assert {path["claim_ids"][0] for path in paths} == {"C1", "C2", "C3"}
    assert report["exact_connections"] == [
        {
            "from_claim_id": "C1",
            "to_claim_id": "C2",
            "state_id": "state::secondary_circulation::increase",
            "connection_type": "exact_state",
        }
    ]
    assert ["C3"] in report["components"]
    assert "C4" not in report["claim_ids"]


def test_incompatible_claim_is_never_selected() -> None:
    claims = {
        "C1": claim("C1", "P1", "forest", "cloud cover", [1.0, 0.0]),
        "C2": claim("C2", "P2", "forest", "rainfall", [1.0, 0.0]),
    }
    ranked = [
        {"claim_id": "C1", "R_claim": 0.7, "A_claim": 0.8, "applicability_status": "compatible_candidate"},
        {"claim_id": "C2", "R_claim": 0.99, "A_claim": 0.1, "applicability_status": "incompatible"},
    ]
    spec = QuerySpec(query_id="Q2", mode="global", context=QueryContext(), user_question="How do forests affect clouds?")
    requirements = query_requirements(spec)
    paths, report = select_evidence_subgraph(
        spec,
        claims,
        ranked,
        requirements,
        [[1.0, 0.0]],
        [],
        {
            "max_claims": 2,
            "relevance_seed_claims": 1,
            "per_requirement_seed_claims": 1,
            "per_seed_paper_claims": 2,
            "seed_paper_relevance_margin": 0.2,
            "exact_path_relevance_margin": 0.2,
            "minimum_requirement_similarity": 0.3,
            "best_match_margin": 0.08,
        },
    )
    assert [path["claim_ids"] for path in paths] == [["C1"]]
    assert report["claim_ids"] == ["C1"]


def test_same_paper_mechanism_steps_are_not_displaced_by_paper_novelty() -> None:
    claims = {
        "C1": claim("C1", "P1", "surface contrast", "secondary circulation", [1.0, 0.0]),
        "C2": claim("C2", "P1", "secondary circulation", "moisture transport", [0.95, 0.05]),
        "C3": claim("C3", "P1", "moisture pooling", "deep convection", [0.9, 0.1]),
        "N1": claim("N1", "P2", "forest", "temperature", [0.8, 0.2]),
        "N2": claim("N2", "P3", "irrigation", "humidity", [0.75, 0.25]),
    }
    ranked = [
        {"claim_id": identifier, "R_claim": score, "A_claim": 0.8, "applicability_status": "compatible_candidate"}
        for identifier, score in (("C1", 0.9), ("C2", 0.86), ("C3", 0.82), ("N1", 0.81), ("N2", 0.80))
    ]
    spec = QuerySpec(query_id="Q3", mode="global", context=QueryContext(), user_question="surface contrast moisture transport deep convection")
    paths, report = select_evidence_subgraph(
        spec,
        claims,
        ranked,
        query_requirements(spec),
        [[1.0, 0.0]],
        [],
        {
            "max_claims": 3,
            "relevance_seed_claims": 1,
            "per_requirement_seed_claims": 1,
            "per_seed_paper_claims": 3,
            "seed_paper_relevance_margin": 0.12,
            "exact_path_relevance_margin": 0.12,
            "minimum_requirement_similarity": 0.3,
            "best_match_margin": 0.08,
        },
    )

    assert [path["claim_ids"] for path in paths] == [["C1"], ["C2"], ["C3"]]
    assert [row["reason"] for row in report["selections"]] == [
        "query_relevance_seed",
        "seed_paper_expansion",
        "seed_paper_expansion",
    ]


def test_exact_and_single_claim_paths_share_relevance_order() -> None:
    graph = [{"claim_ids": ["C1", "C2"], "M_path": 0.8, "R_path": 0.8}]
    claims = [
        {"claim_ids": ["C1"], "M_path": 0.7, "R_path": 0.7},
        {"claim_ids": ["C2"], "M_path": 0.9, "R_path": 0.45},
        {"claim_ids": ["C3"], "M_path": 0.75, "R_path": 0.75},
        {"claim_ids": ["C4"], "M_path": 0.6, "R_path": 0.6},
    ]

    assembled = assemble_subgraph_evidence_paths(graph, claims, graph_limit=1, claim_limit=3)

    assert [item["claim_ids"] for item in assembled] == [["C2"], ["C1", "C2"], ["C3"], ["C1"]]
    assert [item["evidence_lane"] for item in assembled] == ["evidence_subgraph", "graph", "evidence_subgraph", "evidence_subgraph"]


def test_compound_path_packing_is_balanced_and_bounded() -> None:
    paths = [
        [{"claim_ids": [f"Q{query}C{rank}"], "R_path": 1.0 - rank / 10} for rank in range(4)]
        for query in range(3)
    ]

    selected = select_balanced_compound_paths(paths, max_claims=6, max_paths_per_subquery=3)

    assert [[path["claim_ids"][0] for path in group] for group in selected] == [
        ["Q0C0", "Q0C1"],
        ["Q1C0", "Q1C1"],
        ["Q2C0", "Q2C1"],
    ]
