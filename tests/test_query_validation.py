from climatekg.query_validation import QueryCase, verify_query_report


def _report() -> dict:
    return {
        "query_id": "Q1",
        "query_spec": {"mode": "a_to_b", "context": {"facets": [{"id": "Q1_F001"}]}},
        "context_gate_disabled_reason": None,
        "state_mapping": {"source_seeds": [["S1", 1.0]], "target_seeds": [["S2", 1.0]]},
        "claim_candidates": [{"claim_id": "CL1"}],
        "paths": [{"claim_ids": ["CL1"], "A_path": 0.72}],
        "source_blocks": {"CL1": [{"id": "B1"}]},
        "synthesis": {"items": [{"text": "Supported."}], "provenance": {"CL1": {"source_block_ids": ["B1"]}}},
        "answer": "Supported. [Paper, Claim CL1]",
        "warnings": [],
    }


def test_query_report_verification_accepts_grounded_report() -> None:
    case = QueryCase(query_id="Q1", category="context_dependent", question="question", expected_mode="a_to_b", expect_context_facets=True, scientific_purpose="test")
    checks = verify_query_report(case, _report())
    assert checks and all(item["passed"] for item in checks)


def test_query_report_verification_rejects_unsupported_path_claim() -> None:
    case = QueryCase(query_id="Q1", category="context_dependent", question="question", expected_mode="a_to_b", expect_context_facets=True, scientific_purpose="test")
    report = _report()
    report["paths"] = [{"claim_ids": ["CL2"]}]
    checks = {item["name"]: item for item in verify_query_report(case, report)}
    assert not checks["paths_use_ranked_claims"]["passed"]


def test_context_query_rejects_unknown_path_applicability() -> None:
    case = QueryCase(query_id="Q1", category="context_dependent", question="question", expected_mode="a_to_b", expect_context_facets=True, scientific_purpose="test")
    report = _report()
    report["paths"][0]["A_path"] = None
    checks = {item["name"]: item for item in verify_query_report(case, report)}
    assert not checks["known_path_applicability"]["passed"]


def test_required_scientific_claim_groups_must_reach_grounded_answer() -> None:
    case = QueryCase(query_id="Q1", category="context_dependent", question="question", expected_mode="a_to_b", expect_context_facets=True, scientific_purpose="test", required_claim_groups=[["CL1"], ["CL2", "CL3"]])
    checks = {item["name"]: item for item in verify_query_report(case, _report())}
    assert checks["required_claim_group_1"]["passed"]
    assert not checks["required_claim_group_2"]["passed"]


def test_unspecified_query_state_is_compatible() -> None:
    from climatekg.query import _compatible

    assert _compatible("", "increase")


def test_query_spec_payload_excludes_runtime_embeddings() -> None:
    from climatekg.models import QueryContext, QueryFacet, QuerySpec
    from climatekg.query import _query_spec_payload

    facet = QueryFacet(id="Q_F1", domain="climate", notion="humid", description="humid climate", origin="user", notion_embedding=[1.0], content_embedding=[1.0])
    spec = QuerySpec(query_id="Q", mode="global", context=QueryContext(facets=[facet]), user_question="question")
    payload = _query_spec_payload(spec)
    assert "notion_embedding" not in payload["context"]["facets"][0]
    assert "content_embedding" not in payload["context"]["facets"][0]


def test_reporting_and_relation_words_are_not_target_states() -> None:
    from climatekg.query import _is_unspecified_target_state

    assert _is_unspecified_target_state("reported")
    assert _is_unspecified_target_state("effects")
    assert not _is_unspecified_target_state("increase")


def test_where_relation_is_not_a_canonical_target_state() -> None:
    from climatekg.models import ClaimEndpoint
    from climatekg.query import _is_spatial_relation_target

    endpoint = ClaimEndpoint(concept="convection initiation location", state="relative to dry and wet patch edges")
    assert _is_spatial_relation_target(endpoint, "Where relative to patch edges does convection initiate?")
    assert not _is_spatial_relation_target(endpoint, "Does convection initiate?")


def test_alternatives_are_not_one_endpoint_state() -> None:
    from climatekg.models import ClaimEndpoint
    from climatekg.query import _is_comparative_endpoint

    assert _is_comparative_endpoint(ClaimEndpoint(concept="soil moisture", state="drier or wetter"))
    assert not _is_comparative_endpoint(ClaimEndpoint(concept="soil moisture", state="drier"))


def test_comparison_query_detection_uses_intervention_text() -> None:
    from climatekg.models import QueryContext, QuerySpec
    from climatekg.query import _is_comparison_query

    comparison = QuerySpec(query_id="Q", mode="global", context=QueryContext(), intervention_description="drier versus wetter patches", user_question="Which?")
    ordinary = QuerySpec(query_id="Q", mode="global", context=QueryContext(), intervention_description="irrigation expansion", user_question="What changes?")
    assert _is_comparison_query(comparison)
    assert not _is_comparison_query(ordinary)
