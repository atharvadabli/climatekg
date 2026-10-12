from pathlib import Path
import shutil
import uuid

import pytest

from climatekg.models import AnalysisCase, Claim, Context, Facet, FinalPaper, Paper, SourceBlock, State
from climatekg.parquet_graph import ParquetGraph
from climatekg.query import Corpus
from climatekg.vector_index import _collections


def _paper() -> FinalPaper:
    block = SourceBlock(id="P1:B1", paper_id="P1", order=0, page=1, block_type="paragraph", text="Forest cooling increased.", source_locator={"page": 1})
    context = Context(id="P1:C1", paper_id="P1", label="forest case", evidence_block_ids=[block.id], retrieval_embedding=[1.0, 0.0])
    facet = Facet(id="P1:F1", context_id=context.id, domain="land_surface", notion="forest cover", description="forested land", origin="reported", evidence_block_ids=[block.id], notion_embedding=[1.0, 0.0], content_embedding=[0.8, 0.2])
    claim = Claim(id="P1:CL1", paper_id="P1", scope_type="context", scope_id=context.id, **{"from": {"concept": "forest cover", "state": "increase"}}, to={"concept": "surface temperature", "state": "decrease"}, relation="causal", description="Increased forest cover decreased surface temperature.", evidence_role="OWN_RESULT", conditioning_facet_ids=[facet.id], analysis_cases=[AnalysisCase(label="dry years", description="driest years", evidence_block_ids=[block.id], embedding=[0.0, 1.0]), AnalysisCase(label="wet years", description="wettest years", evidence_block_ids=[block.id], embedding=[1.0, 0.0])], analysis_comparison={"dimension": "year class", "case_labels": ["dry years", "wet years"], "description": "The result differed between dry and wet years."}, evidence_block_ids=[block.id], claim_embedding=[0.7, 0.3])
    states = [
        State(id="state::forest_cover::increase", concept="forest cover", state="increase", concept_embedding=[1.0, 0.0]),
        State(id="state::surface_temperature::decrease", concept="surface temperature", state="decrease", concept_embedding=[0.0, 1.0]),
    ]
    return FinalPaper(paper=Paper(id="P1", title="Test", source_file="test.pdf"), source_blocks=[block], contexts=[context], facets=[facet], transitions=[], claims=[claim], states=states, evidence_links=[{"object_id": claim.id, "source_block_id": block.id}], metadata={"nested": {"value": 1}})


def test_parquet_graph_round_trip_and_edges() -> None:
    original = _paper()
    root = Path("climatekg/runtime/cache/test_artifacts") / f"parquet_{uuid.uuid4().hex}"
    try:
        graph = ParquetGraph(root)
        counts = graph.write_corpus([original])
        restored = graph.read_corpus()

        assert restored == [original]
        assert counts["relationships"] == 11
        assert graph.table_counts()["claims"] == 1
        corpus = Corpus(restored)
        assert corpus.claims["P1:CL1"].conditioning_facet_ids == ["P1:F1"]
        assert corpus.claims["P1:CL1"].analysis_cases[0].label == "dry years"
        assert corpus.claims["P1:CL1"].analysis_comparison.dimension == "year class"
        indexes = graph.read_indexes()
        assert indexes.search("contexts", [1.0, 0.0], 1)[0][0] == "P1:C1"
        assert indexes.search("claims", [0.7, 0.3], 1)[0][0] == "P1:CL1"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_vector_collections_merge_shared_canonical_state_deterministically() -> None:
    first = _paper()
    second = first.model_copy(deep=True)
    second.paper.id = "P2"
    second.states[0].concept = "forest-cover"
    second.states[0].concept_embedding = [0.999, 0.001]

    collections = _collections([second, first])

    assert dict(collections["states"])["state::forest_cover::increase"] == [1.0, 0.0]


def test_vector_collections_reject_shared_state_with_different_payload() -> None:
    first = _paper()
    second = first.model_copy(deep=True)
    second.paper.id = "P2"
    second.states[0].concept = "different concept"
    second.states[0].concept_embedding = [0.999, 0.001]

    with pytest.raises(ValueError, match="Conflicting canonical State payload"):
        _collections([first, second])
