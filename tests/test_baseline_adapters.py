from __future__ import annotations

from pathlib import Path

from baselines.climatekg_comparison.corpus import CorpusPaper, usable_blocks
from baselines.climatekg_comparison.graphrag_adapter import build_tables
from baselines.climatekg_comparison.run import json_default, valid_plain_index


def sample_paper() -> CorpusPaper:
    data = {
        "paper": {"id": "P1", "title": "Test", "doi": None},
        "source_blocks": [
            {"id": "B1", "page": 1, "section_path": ["Results"], "block_type": "paragraph", "text": "Evidence."},
            {"id": "B2", "page": 9, "section_path": ["References"], "block_type": "paragraph", "text": "Citation."},
        ],
        "states": [
            {"id": "state::forest::increase", "concept": "forest", "state": "increase", "aliases": []},
            {"id": "state::temperature::decrease", "concept": "temperature", "state": "decrease", "aliases": []},
        ],
        "contexts": [{"id": "C1", "name": "summer"}],
        "facets": [{"id": "F1", "domain": "climate", "notion": "season", "description": "summer"}],
        "claims": [
            {
                "id": "CL1",
                "from": {"concept": "forest", "state": "increase"},
                "to": {"concept": "temperature", "state": "decrease"},
                "description": "More forest lowered temperature.",
                "relation": "causal",
                "evidence_role": "OWN_RESULT",
                "scope_type": "context",
                "scope_id": "C1",
                "conditioning_facet_ids": ["F1"],
                "evidence_block_ids": ["B1"],
            }
        ],
    }
    return CorpusPaper("R1_P1", Path("paper.json"), data)


def test_references_are_not_exported_as_baseline_evidence() -> None:
    assert [block["id"] for block in usable_blocks(sample_paper().data)] == ["B1"]


def test_graphrag_adapter_preserves_claim_and_provenance() -> None:
    entities, relationships, text_units = build_tables([sample_paper()])
    assert set(entities["id"]) == {"state::forest::increase", "state::temperature::decrease"}
    row = relationships.iloc[0]
    assert row["source"] == "state::forest::increase"
    assert row["target"] == "state::temperature::decrease"
    assert row["conditioning_facets"] == ["climate: season = summer"]
    assert row["text_unit_ids"] == ["R1_P1:B1"]
    assert text_units.iloc[0]["block_id"] == "B1"


def test_plain_index_resume_rejects_corrupt_jsonl(tmp_path: Path) -> None:
    index = tmp_path / "index"
    index.mkdir()
    (index / "meta.json").write_text("{}", encoding="utf-8")
    (index / "chunks.jsonl").write_text('{"id": "one"}\n', encoding="utf-8")
    assert valid_plain_index(index)
    (index / "chunks.jsonl").write_text('{"id":\n', encoding="utf-8")
    assert not valid_plain_index(index)


def test_json_default_converts_parquet_array_types() -> None:
    import numpy as np

    assert json_default(np.array(["a", "b"])) == ["a", "b"]
    assert json_default(np.float64(0.5)) == 0.5
