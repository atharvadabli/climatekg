from __future__ import annotations

import json
from pathlib import Path
import shutil
from string import Formatter
import uuid

from pydantic import BaseModel

from climatekg.ollama import OllamaClient
from climatekg.extraction_models import PaperMap, SectionScout


ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIR = ROOT / "prompts"

EXPECTED_PLACEHOLDERS = {
    "paper_map.txt": {"paper_id", "paper_text"},
    "section_scout.txt": {"paper_id", "section_path", "section_blocks"},
    "map_consolidation.txt": {"paper_metadata", "scout_outputs", "selected_blocks"},
    "facet_extraction.txt": {"paper_id", "target_context", "context_registry", "parent_facets", "existing_target_facets", "evidence_blocks"},
    "claim_extraction.txt": {"paper_id", "context_registry", "transitions", "available_scope_facets", "target_scope", "evidence_blocks"},
    "context_reconciliation.txt": {"context_registry", "hints", "hint_evidence_blocks"},
    "paper_consolidation.txt": {"paper_metadata", "candidate_pairs"},
    "query_parse.txt": {"user_question"},
    "final_synthesis.txt": {"question", "query_spec", "query_context", "selected_paths", "contradictions", "source_blocks"},
    "state_adjudication.txt": {"concept_a", "examples_a", "concept_b", "examples_b"},
    "conditioning_facet_adjudication.txt": {"claim", "facet", "claim_evidence", "facet_evidence"},
}


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def test_prompt_templates_are_standalone_and_renderable() -> None:
    for name, expected in EXPECTED_PLACEHOLDERS.items():
        template = (PROMPT_DIR / name).read_text(encoding="utf-8")
        assert template.startswith("SYSTEM\n")
        delimiter = "\nUSER QUESTION\n" if name == "final_synthesis.txt" else "\nUSER\n"
        assert template.count(delimiter) == 1
        assert "TASK\n" in template
        assert "INPUT\n" in template
        assert "OUTPUT\n" in template
        assert _fields(template) == expected
        rendered = template.format(**{field: f"<{field}>" for field in expected})
        assert all(f"<{field}>" in rendered for field in expected)


def test_prompts_avoid_pipeline_dependent_phrasing() -> None:
    banned = (
        "in the usual format",
        "from this stage",
        "later global mapping step",
        "do not extract facets",
        "you are not performing new scientific extraction",
    )
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in PROMPT_DIR.glob("*.txt"))
    for phrase in banned:
        assert phrase not in combined


def test_complete_setting_v11_candidates_are_standalone_and_consistent() -> None:
    candidate_dir = PROMPT_DIR / "experiments" / "complete_setting_v11"
    cases = {
        "paper_map_v11.txt": {"paper_id", "paper_text"},
        "map_consolidation_v11.txt": {"paper_metadata", "scout_outputs", "selected_blocks"},
    }
    for name, placeholders in cases.items():
        text = (candidate_dir / name).read_text(encoding="utf-8")
        assert text.startswith("SYSTEM\n")
        assert text.count("\nUSER\n") == 1
        assert _fields(text) == placeholders
        assert "Settings are defined by their conditions" in text
        assert "Do not construct a full cross-product" in text
        assert "similar or null results" in text
        assert "A leaf that still contains several individually evaluated values is incomplete" in text
        assert "only when the paper analyzes that group as a setting for multiple findings" not in text
    assert (PROMPT_DIR / "paper_map.txt").read_bytes() == (candidate_dir / "paper_map_v11.txt").read_bytes()
    assert (PROMPT_DIR / "map_consolidation.txt").read_bytes() == (candidate_dir / "map_consolidation_v11.txt").read_bytes()


def test_paper_map_structured_schema_requires_every_declared_field() -> None:
    schema = PaperMap.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
    for name in ("MapContext", "MapTransition"):
        item_schema = schema["$defs"][name]
        assert set(item_schema["required"]) == set(item_schema["properties"])
    scout_schema = SectionScout.model_json_schema()
    assert set(scout_schema["required"]) == set(scout_schema["properties"])


class _ExampleOutput(BaseModel):
    value: str


class _FakeOllama(OllamaClient):
    def _post(self, endpoint: str, payload: dict, timeout: int = 1800) -> dict:
        assert endpoint == "/api/chat"
        return {"message": {"content": '{"value":"ok"}'}}


def test_structured_call_saves_exact_request() -> None:
    artifact_dir = ROOT / "climatekg" / "runtime" / "test_artifacts" / f"prompt_capture_{uuid.uuid4().hex}"
    try:
        result = _FakeOllama().structured(
            stage="example",
            system="TASK\nReturn one value.",
            user="INPUT\nexample",
            schema=_ExampleOutput,
            model="qwen3.6:27b",
            temperature=0.0,
            thinking="no",
            artifact_dir=artifact_dir,
            paper_id="P1",
            input_block_ids=["B1"],
            retries=0,
        )
        assert result.value == "ok"
        envelope = json.loads(next(artifact_dir.glob("*.envelope.json")).read_text(encoding="utf-8"))
        request = json.loads(Path(envelope["request_path"]).read_text(encoding="utf-8"))
        assert request["messages"] == [
            {"role": "system", "content": "TASK\nReturn one value."},
            {"role": "user", "content": "INPUT\nexample"},
        ]
        assert request["format"] == _ExampleOutput.model_json_schema()
        assert envelope["prompt_version"] == "example_v2"
    finally:
        shutil.rmtree(artifact_dir, ignore_errors=True)
