import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel

from climatekg.config import PIPELINE, QUERY_PIPELINE
from climatekg.constants import (
    ALLOWED_REASONING_LEVELS,
    OLLAMA_GENERATION_GPU_LAYERS,
    REASONING_PROFILE,
)
from climatekg.ollama import OllamaClient


class _PayloadResult(BaseModel):
    value: str


class _CapturingOllamaClient(OllamaClient):
    def __init__(self) -> None:
        super().__init__()
        self.payload = None

    def _post(self, endpoint, payload, timeout=0):
        self.payload = payload
        return {"message": {"content": '{"value":"ok"}'}}


class ConstantsTests(unittest.TestCase):
    def test_all_llm_stages_use_selected_reasoning_profile(self) -> None:
        stages = {
            **PIPELINE["ollama"]["stages"],
            **QUERY_PIPELINE["ollama"]["stages"],
        }
        self.assertTrue(stages)
        self.assertTrue(all(config["thinking"] in ALLOWED_REASONING_LEVELS for config in stages.values()))
        if REASONING_PROFILE == "no":
            self.assertTrue(all(config["thinking"] == "no" for config in stages.values()))

    def test_indexing_and_query_models_are_consistent(self) -> None:
        self.assertEqual(PIPELINE["ollama"]["model"], QUERY_PIPELINE["ollama"]["model"])
        self.assertEqual(
            PIPELINE["ollama"]["generation_gpu_layers"],
            QUERY_PIPELINE["ollama"]["generation_gpu_layers"],
        )
        self.assertEqual(PIPELINE["ollama"]["generation_gpu_layers"], OLLAMA_GENERATION_GPU_LAYERS)
        self.assertEqual(PIPELINE["embeddings"], QUERY_PIPELINE["embeddings"] | {"block_embeddings": True})

    def test_generation_request_uses_configured_gpu_layers(self) -> None:
        client = _CapturingOllamaClient()
        with patch("climatekg.ollama.write_json"):
            client.structured(
                stage="test",
                system="system",
                user="user",
                schema=_PayloadResult,
                model="model",
                temperature=0.0,
                thinking="no",
                artifact_dir=Path("."),
                paper_id="P000001",
                input_block_ids=[],
                retries=0,
            )
        self.assertEqual(client.payload["options"]["num_gpu"], OLLAMA_GENERATION_GPU_LAYERS)

    def test_validated_profile_matches_selected_benchmark(self) -> None:
        if REASONING_PROFILE != "validated":
            self.skipTest("validated profile is not selected")
        stages = PIPELINE["ollama"]["stages"]
        self.assertEqual(stages["paper_map"]["thinking"], "medium")
        self.assertEqual(stages["map_consolidation"]["thinking"], "medium")
        self.assertEqual(stages["claim_extraction"]["thinking"], "no")
        self.assertEqual(stages["context_reconciliation"]["thinking"], "no")
        self.assertEqual(stages["paper_consolidation"]["thinking"], "no")
        self.assertEqual(QUERY_PIPELINE["ollama"]["stages"]["final_synthesis"]["thinking"], "low")
