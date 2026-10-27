from __future__ import annotations

from climatekg.models import Claim, ClaimEndpoint, Context, FinalPaper, Paper, SourceBlock, State
from climatekg.semantic_links import StateLinkDecision, generate_state_link_candidates, relation_from_entailment, structurally_supports_relation


def paper_with_states() -> FinalPaper:
    claim = Claim(
        id="P1_CL1",
        paper_id="P1",
        scope_type="context",
        scope_id="P1_C1",
        **{
            "from": ClaimEndpoint(concept="near-surface air temperature", state="increase"),
            "to": ClaimEndpoint(concept="deep convection", state="increase"),
        },
        relation="causal",
        description="Higher near-surface air temperature increases deep convection.",
        evidence_role="OWN_RESULT",
        evidence_block_ids=["P1:B1"],
    )
    return FinalPaper(
        paper=Paper(id="P1", title="Example", source_file="example.pdf"),
        source_blocks=[SourceBlock(id="P1:B1", paper_id="P1", order=1, page=1, block_type="paragraph", text="Example.", source_locator={})],
        contexts=[Context(id="P1_C1", paper_id="P1", label="example", evidence_block_ids=["P1:B1"])],
        facets=[],
        transitions=[],
        claims=[claim],
        states=[
            State(id="S1", concept="near-surface air temperature", state="increase", concept_embedding=[1.0, 0.0]),
            State(id="S2", concept="surface air temperature", state="increase", concept_embedding=[0.99, 0.01]),
            State(id="S3", concept="surface air temperature", state="decrease", concept_embedding=[1.0, 0.0]),
        ],
    )


def test_candidate_generation_uses_embeddings_but_rejects_opposite_directions() -> None:
    states, candidates = generate_state_link_candidates([paper_with_states()], top_k=3, minimum_similarity=0.8)

    assert set(states) == {"S1", "S2", "S3"}
    pairs = {frozenset((item.state_a_id, item.state_b_id)) for item in candidates}
    assert frozenset(("S1", "S2")) in pairs
    assert frozenset(("S1", "S3")) not in pairs
    candidate = next(item for item in candidates if frozenset((item.state_a_id, item.state_b_id)) == frozenset(("S1", "S2")))
    assert candidate.claim_ids_a or candidate.claim_ids_b


def test_candidate_generation_rejects_opposition_inside_qualified_states() -> None:
    paper = paper_with_states()
    paper.states = [
        State(id="S1", concept="extreme heat", state="higher in western region", concept_embedding=[1.0, 0.0]),
        State(id="S2", concept="extreme heat", state="lower in eastern region", concept_embedding=[1.0, 0.0]),
    ]

    _, candidates = generate_state_link_candidates([paper], top_k=2, minimum_similarity=0.8)

    assert candidates == []


def test_relation_is_derived_from_directional_entailment() -> None:
    decision = StateLinkDecision(
        pair_id="SL1",
        comparable=True,
        a_entails_b=True,
        b_entails_a=False,
        rationale="A adds a regional restriction.",
    )
    assert relation_from_entailment(decision) == "narrower_than"


def test_structural_review_rejects_quantity_and_optimum_mismatches() -> None:
    flux = State(id="S1", concept="surface latent heat flux", state="increase")
    heating = State(id="S2", concept="surface latent heating", state="increase")
    assert not structurally_supports_relation(flux, heating, "equivalent_to")[0]
    maximum = State(id="S3", concept="transition speed", state="maximized")
    accelerated = State(id="S4", concept="transition speed", state="accelerated")
    assert not structurally_supports_relation(maximum, accelerated, "equivalent_to")[0]


def test_structural_review_accepts_qualified_hierarchy() -> None:
    general = State(id="S1", concept="precipitation", state="increase")
    regional = State(id="S2", concept="precipitation", state="increase in southern india")
    assert structurally_supports_relation(general, regional, "broader_than") == (True, "supported")


def test_structural_review_rejects_component_to_whole_inference() -> None:
    component = State(id="S1", concept="root zone soil moisture", state="decrease")
    whole = State(id="S2", concept="soil moisture", state="decrease")
    assert not structurally_supports_relation(component, whole, "narrower_than")[0]
