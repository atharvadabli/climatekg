from pathlib import Path
import shutil
import uuid

from climatekg.canonicalize import canonical_concept, canonical_direction, state_id
from climatekg.extract import _apply_map_repair, _validate_map, _validate_map_references, _validate_map_repair, _validate_reference_only_repair, remove_internal_inventory_aliases, render_paper_map_tree, scout_setting_inventory, select_map_consolidation_blocks, validate_context_mention_resolution
from climatekg.extraction_models import ContextHintDecision, ContextReconciliationBatch, MapContext, MapTransition, PaperMap, ScoutMention, SectionScout
from climatekg.graph import _flatten, _inflate
from climatekg.indexer import _clear_derived_artifacts, current_prompt_versions, index_pdf, indexing_derivation_fingerprint
import json

import pytest

from climatekg.models import Claim, ClaimEndpoint, Context, Facet, FinalPaper, Paper, QueryContext, QueryFacet, QuerySpec, SourceBlock, Transition
from climatekg.pdf import _split_text, _validated_parse_cache, clean_parse
from climatekg.query import Corpus, _is_compound_unspecified_target, context_similarity, trim_evidence_package
from climatekg.reconcile import _validate_reconciliation_batch, reversal_hints
from climatekg.retrieval import bm25
from climatekg.utils import normalize_text_key
from climatekg.utils import sha256_file


def test_normative_normalization() -> None:
    assert normalize_text_key("  Low–level  moisture flux! ") == "low-level moisture flux"
    assert canonical_concept("ET") == "evapotranspiration"
    assert canonical_direction("no significant change") == "no_detectable_change"


def test_compound_unspecified_target_becomes_forward_candidate() -> None:
    assert _is_compound_unspecified_target(ClaimEndpoint(concept="circulation and moisture", state=""))
    assert not _is_compound_unspecified_target(ClaimEndpoint(concept="circulation", state="increase"))
    assert state_id("surface temperature", "increase") == "state::surface_temperature::increase"


def test_corpus_verified_endpoint_normalization() -> None:
    assert canonical_concept("afternoon convective precipitation") == "convective precipitation"
    assert canonical_direction("increased likelihood of occurrence") == "more_frequent"
    assert canonical_concept("surface albedo north of 18 n") == "surface albedo"
    assert canonical_direction("increased from 0.14 to 0.35") == "increase"
    assert canonical_concept("sahel precipitation") == "precipitation"
    assert canonical_direction("decreased by 40%") == "decrease"


def test_oversize_split_preserves_text() -> None:
    text = "One sentence with words. " * 100
    pieces = _split_text(text, max_tokens=40, target_tokens=30)
    assert len(pieces) > 1
    assert all(piece for piece, _ in pieces)


def test_bm25_prefers_matching_scientific_block() -> None:
    blocks = [
        SourceBlock(id="P:S00:P0001", paper_id="P", order=0, page=1, block_type="paragraph", text="forest irrigation reduced extreme heat", source_locator={"page": 1}),
        SourceBlock(id="P:S00:P0002", paper_id="P", order=1, page=1, block_type="paragraph", text="bibliographic publishing details", source_locator={"page": 1}),
    ]
    assert bm25(blocks, ["irrigation heat"], 2)[0].block.id == blocks[0].id


def test_context_similarity_separates_missing_from_mismatch() -> None:
    query = QueryFacet(id="Q_F001", domain="climate", notion="heat regime", description="hot daytime conditions", origin="user", notion_embedding=[1.0, 0.0], content_embedding=[1.0, 0.0])
    candidate = Facet(id="P_F001", context_id="P_C001", domain="climate", notion="temperature regime", description="hot daytime climate", origin="reported", evidence_block_ids=["b"], notion_embedding=[1.0, 0.0], content_embedding=[0.8, 0.6])
    matched = context_similarity([query], [candidate])
    missing = context_similarity([query], [])
    assert matched["coverage"] == 1.0
    assert missing["coverage"] == 0.0
    assert missing["domain_scores"]["climate"]["status"] == "missing_in_candidate"


def test_context_similarity_uses_domain_wise_maxsim() -> None:
    query = [
        QueryFacet(id="Q_PATTERN", domain="spatial_configuration", notion="patch arrangement", description="alternating patches", origin="user", notion_embedding=[1.0, 0.0], content_embedding=[1.0, 0.0]),
        QueryFacet(id="Q_SCALE", domain="spatial_configuration", notion="patch size", description="large patches", origin="user", notion_embedding=[0.9, 0.1], content_embedding=[0.9, 0.1]),
    ]
    candidates = [
        Facet(id="F_GENERIC", context_id="C", domain="spatial_configuration", notion="heterogeneous patches", description="patch configuration", origin="reported", evidence_block_ids=["B"], notion_embedding=[1.0, 0.0], content_embedding=[1.0, 0.0]),
        Facet(id="F_SIZE", context_id="C", domain="spatial_configuration", notion="large patch scale", description="large patch size", origin="reported", evidence_block_ids=["B"], notion_embedding=[0.8, 0.2], content_embedding=[0.8, 0.2]),
    ]
    report = context_similarity(query, candidates)
    assert [item["query_facet_id"] for item in report["facet_matches"]] == ["Q_PATTERN", "Q_SCALE"]
    assert [item["candidate_facet_id"] for item in report["facet_matches"]] == ["F_GENERIC", "F_GENERIC"]
    assert report["missing_query_facets"] == []


def test_derivation_fingerprint_changes_with_scientific_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from climatekg.config import PIPELINE

    baseline = indexing_derivation_fingerprint(False)
    assert baseline == indexing_derivation_fingerprint(False)
    assert baseline != indexing_derivation_fingerprint(True)
    monkeypatch.setitem(PIPELINE["ollama"]["stages"]["paper_map"], "thinking", "low")
    assert baseline != indexing_derivation_fingerprint(False)


def _test_artifact_dir(name: str) -> Path:
    path = Path("climatekg/runtime/cache/test_artifacts") / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_clean_parse_removes_explicit_page_furniture() -> None:
    raw = {"pages": [{"page": 1, "width": 100, "height": 100, "elements": [
        {"text": "Journal footer 1", "semantic_class": "Page-footer", "near_top": False, "near_bottom": True},
        {"text": "Supported result text.", "semantic_class": "Text", "near_top": False, "near_bottom": False},
    ]}]}
    cleaned = clean_parse(raw, _test_artifact_dir("clean_parse"))
    assert [item["text"] for item in cleaned[0]["elements"]] == ["Supported result text."]


def test_validated_parse_cache_requires_complete_exact_parser() -> None:
    tmp_path = _test_artifact_dir("parse_cache")
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    manifest = tmp_path / "pages.json"
    output = tmp_path / "raw.json"
    manifest.write_text(json.dumps({"renderer": "PDFium", "pages": [{"page": 1, "path": str(image)}]}), encoding="utf-8")
    output.write_text(json.dumps({"parser": "nvidia/NVIDIA-Nemotron-Parse-v1.2", "page_count": 1, "pages": [{"page": 1}], "validation_flags": []}), encoding="utf-8")
    assert _validated_parse_cache(manifest, output) is not None
    parsed = json.loads(output.read_text(encoding="utf-8"))
    parsed["parser"] = "another-parser"
    output.write_text(json.dumps(parsed), encoding="utf-8")
    assert _validated_parse_cache(manifest, output) is None


def test_final_paper_rejects_context_cycle() -> None:
    paper = Paper(id="P", title="Paper", source_file="paper.pdf")
    contexts = [Context(id="C1", paper_id="P", parent_ids=["C2"], label="one"), Context(id="C2", paper_id="P", parent_ids=["C1"], label="two")]
    with pytest.raises(ValueError, match="cycle"):
        FinalPaper(paper=paper, source_blocks=[], contexts=contexts, facets=[], transitions=[], claims=[], states=[])


def test_final_paper_validates_transition_scoped_claim() -> None:
    paper = Paper(id="P", title="Paper", source_file="paper.pdf")
    block = SourceBlock(id="B1", paper_id="P", order=0, page=1, block_type="paragraph", text="Direct result.", source_locator={"page": 1})
    contexts = [Context(id="C1", paper_id="P", label="control"), Context(id="C2", paper_id="P", label="changed")]
    transition = Transition(id="T1", paper_id="P", from_context_id="C1", to_context_id="C2", label="change", description="change", evidence_block_ids=["B1"])
    claim = Claim(id="CL1", paper_id="P", scope_type="transition", scope_id="T1", **{"from": {"concept": "land cover", "state": "changed"}}, to={"concept": "temperature", "state": "increase"}, relation="causal", description="Temperature increased.", evidence_role="OWN_RESULT", evidence_block_ids=["B1"])
    final = FinalPaper(paper=paper, source_blocks=[block], contexts=contexts, facets=[], transitions=[transition], claims=[claim], states=[])
    assert final.claims[0].scope_id == "T1"


def test_map_repair_cannot_flatten_existing_hierarchy() -> None:
    parent = MapContext(temp_id="parent", label="parent", evidence_block_ids=["B1"])
    child = MapContext(temp_id="child", label="child", parent_temp_ids=["parent"], split_reason="separate_reported_finding", evidence_block_ids=["B1"])
    invalid = MapTransition(temp_id="T", from_context_temp_id="parent", to_context_temp_id="parent", label="comparison", description="comparison", evidence_block_ids=["B1"])
    original = PaperMap(contexts=[parent, child], transitions=[invalid])
    flattened_child = child.model_copy(update={"parent_temp_ids": [], "split_reason": None})
    added = MapContext(temp_id="other", label="other", evidence_block_ids=["B1"])
    fixed = invalid.model_copy(update={"to_context_temp_id": "other"})
    repaired = PaperMap(contexts=[parent, flattened_child, added], transitions=[fixed])
    with pytest.raises(ValueError, match="immutable Context"):
        _validate_map_repair(original, repaired, {"B1"})


def test_map_repair_applies_only_new_endpoint_children() -> None:
    anchor = MapContext(temp_id="anchor", label="anchor", evidence_block_ids=["B1"])
    existing_child = MapContext(temp_id="existing", label="existing", parent_temp_ids=["anchor"], split_reason="separate_reported_finding", evidence_block_ids=["B1"])
    invalid = MapTransition(temp_id="T", from_context_temp_id="anchor", to_context_temp_id="anchor", label="comparison", description="comparison", evidence_block_ids=["B1"])
    original = PaperMap(contexts=[anchor, existing_child], transitions=[invalid])
    left = MapContext(temp_id="left", label="left", evidence_block_ids=["B1"])
    right = MapContext(temp_id="right", label="right", evidence_block_ids=["B1"])
    replacement = invalid.model_copy(update={"from_context_temp_id": "left", "to_context_temp_id": "right"})
    proposed = PaperMap(contexts=[anchor.model_copy(update={"label": "rewritten"}), existing_child.model_copy(update={"parent_temp_ids": []}), left, right], transitions=[replacement])
    applied = _apply_map_repair(original, proposed, {"B1"})
    by_id = {item.temp_id: item for item in applied.contexts}
    assert by_id["existing"].parent_temp_ids == ["anchor"]
    assert by_id["left"].parent_temp_ids == ["anchor"]
    assert by_id["right"].parent_temp_ids == ["anchor"]
    assert by_id["left"].evidence_block_ids == ["B1"]
    assert by_id["left"].facet_seed_block_ids == ["B1"]
    assert applied.transitions[0].from_context_temp_id == "left"


def test_map_reference_repair_can_only_change_evidence_ids() -> None:
    original = PaperMap(contexts=[MapContext(temp_id="C", label="context", evidence_block_ids=["P0007"])], transitions=[])
    repaired = PaperMap(contexts=[MapContext(temp_id="C", label="context", evidence_block_ids=["P:S00:P0007"])], transitions=[])
    _validate_reference_only_repair(original, repaired, {"P:S00:P0007"})
    with pytest.raises(ValueError, match="Context semantics"):
        _validate_reference_only_repair(original, PaperMap(contexts=[MapContext(temp_id="C", label="changed", evidence_block_ids=["P:S00:P0007"])], transitions=[]), {"P:S00:P0007"})
    with pytest.raises(ValueError, match="Context evidence"):
        _validate_map_references(original, {"P:S00:P0007"})


def test_map_selector_uses_scout_evidence_without_keyword_sweep() -> None:
    blocks = [
        SourceBlock(id="TITLE", paper_id="P", order=0, page=1, block_type="title", text="Paper title", source_locator={"page": 1}),
        SourceBlock(id="CASE", paper_id="P", order=1, page=2, block_type="paragraph", text="The named control and treatment settings.", source_locator={"page": 2}),
        SourceBlock(id="RESULT", paper_id="P", order=2, page=3, block_type="paragraph", text="The treatment changed temperature.", source_locator={"page": 3}),
        SourceBlock(id="UNRELATED", paper_id="P", order=3, page=4, block_type="paragraph", text="The word case appears in unrelated discussion.", source_locator={"page": 4}),
    ]
    scout = SectionScout(
        context_mentions=[ScoutMention(name="treatment", description="A reported treatment setting.", block_ids=["CASE"])],
        claim_seed_block_ids=["RESULT"],
    )
    selected, report = select_map_consolidation_blocks(blocks, [scout], 1000)
    assert [block.id for block in selected] == ["TITLE", "CASE", "RESULT"]
    assert "UNRELATED" not in report["selected_block_ids"]


def test_scout_setting_inventory_checks_coverage_without_string_matching() -> None:
    scouts = [
        SectionScout(context_mentions=[ScoutMention(name="RUN-A", description="First mention.", block_ids=["B1"])]),
        SectionScout(context_mentions=[
            ScoutMention(name="RUN-A", description="Repeated mention.", block_ids=["B2"]),
            ScoutMention(name="RUN-B", description="Different forcing.", block_ids=["B3"]),
        ]),
    ]
    inventory = scout_setting_inventory(scouts)
    assert [(item["mention_id"], item["name"]) for item in inventory] == [("CM001", "RUN-A"), ("CM002", "RUN-B")]
    mapped = PaperMap(
        contexts=[
            MapContext(temp_id="A", label="first run", evidence_block_ids=["B1"]),
            MapContext(temp_id="B", label="second run", evidence_block_ids=["B3"]),
        ],
        transitions=[],
        context_mention_resolution={"CM001": "A", "CM002": "B"},
    )
    validate_context_mention_resolution(mapped, inventory)
    validate_context_mention_resolution(mapped.model_copy(update={"context_mention_resolution": {"CM001": "A", "CM002": "A"}}), inventory)
    with pytest.raises(ValueError, match="unknown Context"):
        validate_context_mention_resolution(mapped.model_copy(update={"context_mention_resolution": {"CM001": "A", "CM002": "missing"}}), inventory)


def test_internal_inventory_ids_are_not_scientific_aliases() -> None:
    mapped = PaperMap(
        contexts=[MapContext(temp_id="A", label="first run", aliases=["RUN-A", "CM001", "CM01"], evidence_block_ids=["B1"])],
        transitions=[],
        context_mention_resolution={"CM001": "A"},
    )
    cleaned = remove_internal_inventory_aliases(mapped)
    assert cleaned.contexts[0].aliases == ["RUN-A", "CM01"]
    assert cleaned.context_mention_resolution == {"CM001": "A"}


def test_map_tree_renders_complete_setting_hierarchy() -> None:
    mapped = PaperMap(
        contexts=[
            MapContext(temp_id="root", label="shared model setup", evidence_block_ids=["B1"]),
            MapContext(temp_id="treatment", label="treated experiments", parent_temp_ids=["root"], split_reason="separate_reported_finding", evidence_block_ids=["B2"]),
            MapContext(temp_id="run", label="low forcing run", parent_temp_ids=["treatment"], split_reason="separate_reported_finding", aliases=["RUN-L"], evidence_block_ids=["B3"]),
        ],
        transitions=[],
    )
    tree = render_paper_map_tree(mapped)
    assert "- shared model setup [root]" in tree
    assert "  - treated experiments [treatment]" in tree
    assert "    - low forcing run [run]; aliases: RUN-L" in tree


def test_map_validation_checks_only_internal_structure() -> None:
    root = MapContext(temp_id="root", label="generated wording", evidence_block_ids=["B1"])
    invalid_child = MapContext(temp_id="child", label="different generated wording", parent_temp_ids=["root"], evidence_block_ids=["B1"])
    with pytest.raises(ValueError, match="parent/split_reason"):
        _validate_map(PaperMap(contexts=[root, invalid_child], transitions=[]), {"B1"})

    duplicate = PaperMap(contexts=[root, root], transitions=[])
    with pytest.raises(ValueError, match="duplicate Context IDs"):
        _validate_map(duplicate, {"B1"})


def test_explicit_derived_rebuild_retains_parse_and_blocks() -> None:
    data_root = Path("climatekg/runtime/cache/test_artifacts") / f"derived_rebuild_{uuid.uuid4().hex}"
    paper_dir = data_root / "P000001"
    try:
        for name in ("parse", "blocks", "extraction", "final"):
            target = paper_dir / name
            target.mkdir(parents=True)
            (target / "artifact.txt").write_text(name, encoding="utf-8")
        _clear_derived_artifacts(paper_dir, data_root)
        assert (paper_dir / "parse" / "artifact.txt").exists()
        assert (paper_dir / "blocks" / "artifact.txt").exists()
        assert not (paper_dir / "extraction").exists()
        assert not (paper_dir / "final").exists()
        assert current_prompt_versions()["map_consolidation"] == "v13"
        assert current_prompt_versions()["section_scout"] == "v4"
    finally:
        shutil.rmtree(data_root, ignore_errors=True)


def test_cached_index_return_preserves_completed_timing(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"benchmark fixture")
    data_root = tmp_path / "data"
    paper_dir = data_root / "P000001"
    final_dir = paper_dir / "final"
    metrics_dir = paper_dir / "metrics"
    final_dir.mkdir(parents=True)
    metrics_dir.mkdir(parents=True)
    manifest = {"paper_id": "P000001", "pdf_sha256": sha256_file(pdf_path), "status": "complete"}
    (paper_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    final = FinalPaper(paper=Paper(id="P000001", title="Fixture", source_file="paper.pdf"), source_blocks=[], contexts=[], facets=[], transitions=[], claims=[], states=[], metadata={"prompt_versions": current_prompt_versions()})
    final_path = final_dir / "final_paper.json"
    final_path.write_text(final.model_dump_json(by_alias=True), encoding="utf-8")
    timing_path = metrics_dir / "indexing_timing.json"
    timing_path.write_text('{"status":"complete","wall_elapsed_seconds":123.0}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="derivation_fingerprint"):
        index_pdf(pdf_path, data_root, "P000001")

    current = final.model_copy(update={"metadata": {**final.metadata, "derivation_fingerprint": indexing_derivation_fingerprint(False)}})
    final_path.write_text(current.model_dump_json(by_alias=True), encoding="utf-8")
    index_pdf(pdf_path, data_root, "P000001")

    assert json.loads(timing_path.read_text(encoding="utf-8"))["wall_elapsed_seconds"] == 123.0


def test_neo4j_property_round_trip_preserves_nested_values() -> None:
    value = {"id": "B1", "source_locator": {"page": 2}, "section_path": ["Results"], "embedding": [0.1, 0.2], "optional": None}
    assert _inflate(_flatten(value)) == value


def test_opposite_outcomes_create_late_context_hints() -> None:
    common = {"paper_id": "P", "scope_type": "context", "scope_id": "C", "from": {"concept": "land cover", "state": "changed"}, "relation": "causal", "evidence_role": "OWN_RESULT", "evidence_block_ids": ["B1"]}
    warmer = Claim(id="CL1", to={"concept": "temperature", "state": "increase"}, description="Warmer at night.", **common)
    cooler = Claim(id="CL2", to={"concept": "temperature", "state": "decrease"}, description="Cooler by day.", **common)
    hints = reversal_hints([warmer, cooler])
    assert [item["affected_claim_ids"] for item in hints] == [["CL1"], ["CL2"]]


def test_reversal_hint_is_limited_to_original_context_branch() -> None:
    contexts = [
        Context(id="C_OBS", paper_id="P", label="observations"),
        Context(id="C_DOWN", paper_id="P", parent_ids=["C_OBS"], label="downwind"),
        Context(id="C_SIM", paper_id="P", label="simulation"),
    ]
    transition = Transition(id="T_OBS", paper_id="P", from_context_id="C_OBS", to_context_id="C_DOWN", label="observed change", description="observed change", evidence_block_ids=["B1"])
    common = {"paper_id": "P", "scope_type": "transition", "scope_id": "T_OBS", "from": {"concept": "land cover", "state": "changed"}, "relation": "causal", "evidence_role": "OWN_RESULT", "evidence_block_ids": ["B1"]}
    claims = [
        Claim(id="CL1", to={"concept": "temperature", "state": "increase"}, description="Warmer at night.", **common),
        Claim(id="CL2", to={"concept": "temperature", "state": "decrease"}, description="Cooler by day.", **common),
    ]
    hints = reversal_hints(claims, contexts, [transition])
    assert hints[0]["allowed_context_ids"] == ["C_DOWN", "C_OBS"]


def test_reconciliation_action_requires_its_conditional_fields() -> None:
    with pytest.raises(ValueError, match="new_context_label"):
        ContextHintDecision(action="ADD_CHILD_CONTEXT", hint_id="RH001", parent_context_id="C1", evidence_block_ids=["B1"])
    with pytest.raises(ValueError, match="existing_context_id"):
        ContextHintDecision(action="ATTACH_TO_EXISTING_CONTEXT", hint_id="RH002")


def test_reconciliation_references_must_preserve_affected_claims() -> None:
    batch = ContextReconciliationBatch(decisions=[ContextHintDecision(hint_id="RH001", action="ADD_CHILD_CONTEXT", parent_context_id="C1", new_context_label="night", affected_claim_ids=[], evidence_block_ids=["B1"])])
    hints = [{"hint_id": "RH001", "affected_claim_ids": ["CL1"], "evidence_block_ids": ["B1"], "allowed_context_ids": ["C1"]}]
    with pytest.raises(ValueError, match="affected Claims are incomplete"):
        _validate_reconciliation_batch(batch, hints, {"C1"})


def test_evidence_budget_never_retains_an_unsupported_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    from climatekg.config import QUERY_PIPELINE

    paper = Paper(id="P", title="Paper", source_file="paper.pdf")
    blocks = [SourceBlock(id=f"B{i}", paper_id="P", order=i, page=1, block_type="paragraph", text="supported result " * 20, source_locator={"page": 1}) for i in (1, 2)]
    context = Context(id="C1", paper_id="P", label="study")
    claims = [Claim(id=f"CL{i}", paper_id="P", scope_type="context", scope_id="C1", **{"from": {"concept": "land cover", "state": "changed"}}, to={"concept": "temperature", "state": "increase"}, relation="causal", description="Temperature increased.", evidence_role="OWN_RESULT", evidence_block_ids=[f"B{i}"]) for i in (1, 2)]
    corpus = Corpus([FinalPaper(paper=paper, source_blocks=blocks, contexts=[context], facets=[], transitions=[], claims=claims, states=[])])
    spec = QuerySpec(query_id="Q", mode="global", user_question="What changes?", context=QueryContext())
    monkeypatch.setitem(QUERY_PIPELINE["synthesis"], "evidence_input_budget_tokens", 1)
    monkeypatch.setitem(QUERY_PIPELINE["synthesis"], "hard_llm_input_budget_tokens", 10000)
    monkeypatch.setitem(QUERY_PIPELINE["synthesis"], "max_claims", 1)
    paths, _, selected, warnings = trim_evidence_package(spec, [{"claim_ids": ["CL1", "CL2"], "R_path": 1.0}], [], {"CL1": [blocks[0].model_dump()], "CL2": [blocks[1].model_dump()]}, corpus)
    assert warnings == ["SOURCEBLOCK_BUDGET_TRUNCATED"]
    assert paths[0]["claim_ids"] == ["CL1"]
    assert selected["CL1"]
