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


def test_generic_spatial_scale_is_not_a_named_location() -> None:
    from climatekg.query import _is_generic_spatial_reference

    assert _is_generic_spatial_reference("regional")
    assert _is_generic_spatial_reference("local")
    assert not _is_generic_spatial_reference("East Asia")


def test_query_spec_payload_excludes_runtime_embeddings() -> None:
    from climatekg.models import QueryAnalysisCase, QueryContext, QueryFacet, QuerySpec
    from climatekg.query import _query_spec_payload

    facet = QueryFacet(id="Q_F1", domain="climate", notion="humid", description="humid climate", origin="user", notion_embedding=[1.0], content_embedding=[1.0])
    case = QueryAnalysisCase(id="Q_AC1", label="dry years", supporting_text_span="dry years", embedding=[1.0])
    spec = QuerySpec(query_id="Q", mode="global", context=QueryContext(facets=[facet]), analysis_cases=[case], user_question="question")
    payload = _query_spec_payload(spec)
    assert "notion_embedding" not in payload["context"]["facets"][0]
    assert "content_embedding" not in payload["context"]["facets"][0]
    assert "embedding" not in payload["analysis_cases"][0]


def test_analysis_cases_match_separately_from_context() -> None:
    from climatekg.models import AnalysisCase, Claim, QueryAnalysisCase, QueryContext, QuerySpec
    from climatekg.query import _analysis_case_match

    claim = Claim(
        id="CL1", paper_id="P1", scope_type="context", scope_id="C1",
        **{"from": {"concept": "irrigated evaporation", "state": "increase"}},
        to={"concept": "rainfall contribution", "state": "increase"},
        relation="associative", description="Contribution differs by year class.",
        evidence_role="OWN_RESULT", evidence_block_ids=["B1"],
        analysis_cases=[
            AnalysisCase(label="wet years", description="wettest years", evidence_block_ids=["B1"], embedding=[1.0, 0.0]),
            AnalysisCase(label="dry years", description="driest years", evidence_block_ids=["B1"], embedding=[0.0, 1.0]),
        ],
        analysis_comparison={"dimension": "rainfall-year class", "case_labels": ["wet years", "dry years"], "description": "The contribution is higher in dry years."},
    )
    spec = QuerySpec(
        query_id="Q1", mode="a_to_b", context=QueryContext(), user_question="compare wet and dry years",
        analysis_cases=[
            QueryAnalysisCase(id="Q1_AC1", label="wet years", supporting_text_span="wet", embedding=[1.0, 0.0]),
            QueryAnalysisCase(id="Q1_AC2", label="dry years", supporting_text_span="dry", embedding=[0.0, 1.0]),
        ],
    )

    report = _analysis_case_match(claim, spec)

    assert report["score"] == 1.0
    assert report["availability_coverage"] == 1.0
    assert [item["claim_case_label"] for item in report["matches"]] == ["wet years", "dry years"]


def test_planning_answer_groups_mechanism_with_its_recommendation() -> None:
    from climatekg.extraction_models import SynthesisItem
    from climatekg.query import render_planning_answer

    recommendation = SynthesisItem(text="Preserve tree cover.", support_claim_ids=["CL1"], support_query_facet_ids=[], kind="transfer_inference")
    mechanism = SynthesisItem(text="Trees increase latent cooling.", support_claim_ids=["CL1"], support_query_facet_ids=[], kind="mechanism")
    limitation = SynthesisItem(text="Local water availability is unknown.", support_claim_ids=[], support_query_facet_ids=[], kind="limitation")
    sections = {
        "direct_answer": [recommendation],
        "mechanisms": [mechanism],
        "spatial_guidance": [],
        "conditions_and_limitations": [limitation],
        "contradictory_evidence": [],
    }
    rendered = {
        id(recommendation): "Preserve tree cover. [Claim CL1]",
        id(mechanism): "Trees increase latent cooling. [Claim CL1]",
        id(limitation): limitation.text,
    }

    answer = render_planning_answer(sections, rendered)

    assert "### Recommendation 1" in answer
    assert "**What change:** Preserve tree cover." in answer
    assert "**Why it may help:** Trees increase latent cooling." in answer
    assert answer.index("Why it may help") < answer.index("Limitations and other important notes")


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


def _direct_evidence_test_corpus():
    from climatekg.models import Claim, Context, FinalPaper, Paper, SourceBlock
    from climatekg.query import Corpus

    paper = Paper(id="P", title="Paper", source_file="paper.pdf")
    block = SourceBlock(id="B", paper_id="P", order=1, page=1, block_type="paragraph", text="Supported result.", source_locator={"page": 1})
    context = Context(id="C", paper_id="P", label="study")
    claims = [
        Claim(
            id=claim_id,
            paper_id="P",
            scope_type="context",
            scope_id="C",
            **{"from": {"concept": source, "state": "changed"}},
            to={"concept": "rainfall", "state": "decrease"},
            relation="causal",
            description="Rainfall decreased.",
            evidence_role="OWN_RESULT",
            evidence_block_ids=["B"],
        )
        for claim_id, source in (("CL_ENDPOINT", "deforestation"), ("CL_KNOWN", "land-cover pattern"), ("CL_UNKNOWN", "forest loss"))
    ]
    claims.append(
        Claim(
            id="CL_NEXT",
            paper_id="P",
            scope_type="context",
            scope_id="C",
            **{"from": {"concept": "rainfall", "state": "decrease"}},
            to={"concept": "cloud cover", "state": "decrease"},
            relation="causal",
            description="Reduced rainfall was followed by reduced cloud cover.",
            evidence_role="OWN_RESULT",
            evidence_block_ids=["B"],
        )
    )
    return Corpus([FinalPaper(paper=paper, source_blocks=[block], contexts=[context], facets=[], transitions=[], claims=claims, states=[])])


def test_direct_evidence_lane_uses_semantic_retrieval_not_endpoint_only() -> None:
    from climatekg.models import QueryContext, QuerySpec
    from climatekg.query import select_direct_evidence_paths

    spec = QuerySpec(query_id="Q", mode="forward", context=QueryContext(), source={"concept": "deforestation", "state": ""}, user_question="What changed?")
    ranked = [
        {"claim_id": "CL_ENDPOINT", "R_claim": 0.99, "A_claim": None, "channels": ["source_endpoint"]},
        {"claim_id": "CL_KNOWN", "R_claim": 0.80, "A_claim": 0.70, "channels": ["claim_ann"]},
    ]

    paths = select_direct_evidence_paths(spec, _direct_evidence_test_corpus(), ranked)

    assert [path["claim_ids"] for path in paths] == [["CL_KNOWN"]]


def test_direct_evidence_lane_keeps_unknown_applicability_for_context_query() -> None:
    from climatekg.models import QueryContext, QueryFacet, QuerySpec
    from climatekg.query import select_direct_evidence_paths

    facet = QueryFacet(id="Q_F1", domain="climate", notion="rainy season", description="rainy season", origin="user")
    spec = QuerySpec(query_id="Q", mode="forward", context=QueryContext(facets=[facet]), source={"concept": "deforestation", "state": ""}, user_question="What changed in the rainy season?")
    ranked = [
        {"claim_id": "CL_UNKNOWN", "R_claim": 0.90, "A_claim": None, "channels": ["claim_ann"]},
        {"claim_id": "CL_KNOWN", "R_claim": 0.80, "A_claim": 0.70, "channels": ["transition_ann"]},
    ]

    paths = select_direct_evidence_paths(spec, _direct_evidence_test_corpus(), ranked)

    assert [path["claim_ids"] for path in paths] == [["CL_UNKNOWN"], ["CL_KNOWN"]]


def test_source_block_retrieval_adds_claim_candidate_independently() -> None:
    from climatekg.models import QueryContext, QuerySpec
    from climatekg.query import rank_claims

    corpus = _direct_evidence_test_corpus()
    corpus.blocks["B"].embedding = [1.0, 0.0]
    for claim in corpus.claims.values():
        claim.claim_embedding = [0.0, 1.0]
    spec = QuerySpec(query_id="Q", mode="global", context=QueryContext(), user_question="Supported result")

    rows = rank_claims(
        spec,
        {"claim": [1.0, 0.0], "context": None, "intervention": None},
        corpus,
        {},
        [],
        [],
    )

    assert rows
    assert all("source_block_ann" in row["channels"] for row in rows)
    assert all(row["S_source_block"] == 1.0 for row in rows)
    assert all(row["applicability_status"] == "unknown" for row in rows)


def test_forward_graph_search_starts_from_query_focused_claim() -> None:
    from climatekg.models import QueryContext, QuerySpec
    from climatekg.query import search_paths

    spec = QuerySpec(query_id="Q", mode="forward", context=QueryContext(), source={"concept": "deforestation", "state": ""}, user_question="What changed?")
    ranked = [
        {"claim_id": "CL_ENDPOINT", "R_claim": 0.99, "A_claim": None, "channels": ["source_endpoint"]},
        {"claim_id": "CL_KNOWN", "R_claim": 0.80, "A_claim": 0.70, "channels": ["claim_ann"]},
        {"claim_id": "CL_NEXT", "R_claim": 0.70, "A_claim": 0.65, "channels": ["claim_ann"]},
    ]

    paths = search_paths(
        spec,
        _direct_evidence_test_corpus(),
        ranked,
        [("state::deforestation::changed", 1.0)],
        [],
        ["CL_KNOWN"],
    )

    claim_paths = [path["claim_ids"] for path in paths]
    assert ["CL_KNOWN", "CL_NEXT"] in claim_paths
    assert ["CL_KNOWN"] not in claim_paths
    assert all("CL_ENDPOINT" not in path for path in claim_paths)


def test_context_evidence_comparisons_keep_user_and_derived_wind_separate() -> None:
    from climatekg.models import QueryContext, QueryFacet, QuerySpec
    from climatekg.query import context_evidence_comparisons

    facets = [
        QueryFacet(id="Q_F1", domain="atmosphere", notion="weak background wind", description="Weak background wind is assumed.", origin="user"),
        QueryFacet(id="Q_F2", domain="atmosphere", notion="seasonal wind regime", description="Mean wind speed is 3.1 m/s.", origin="derived"),
        QueryFacet(id="Q_F3", domain="atmosphere", notion="daytime heating", description="Strong daytime heating is assumed.", origin="user"),
    ]
    spec = QuerySpec(query_id="Q", mode="global", context=QueryContext(facets=facets), user_question="question")

    comparisons = context_evidence_comparisons(spec)

    assert comparisons == [
        {
            "user_facet_id": "Q_F1",
            "derived_facet_id": "Q_F2",
            "shared_variables": ["wind"],
            "status": "coexisting_not_adjudicated",
            "user_description": "Weak background wind is assumed.",
            "derived_description": "Mean wind speed is 3.1 m/s.",
        }
    ]


def test_context_comparison_limitation_is_grouped_and_traceable() -> None:
    from climatekg.query import context_comparison_limitations

    items = context_comparison_limitations([
        {"user_facet_id": "Q_F1", "derived_facet_id": "Q_F2", "shared_variables": ["wind"], "status": "coexisting_not_adjudicated", "user_description": "Weak monsoon wind is assumed.", "derived_description": "DJF wind is 1.0 m/s."},
        {"user_facet_id": "Q_F1", "derived_facet_id": "Q_F3", "shared_variables": ["wind"], "status": "coexisting_not_adjudicated", "user_description": "Weak monsoon wind is assumed.", "derived_description": "JJA wind is 3.1 m/s."},
    ])

    assert len(items) == 1
    item = items[0]
    assert item.kind == "limitation"
    assert item.support_claim_ids == []
    assert item.support_query_facet_ids == ["Q_F1", "Q_F2", "Q_F3"]
    assert "DJF wind is 1.0 m/s" in item.text
    assert "JJA wind is 3.1 m/s" in item.text
    assert "was not adjudicated" in item.text
