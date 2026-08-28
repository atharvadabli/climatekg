import unittest

from climatekg.config import PIPELINE, QUERY_PIPELINE
from climatekg.constants import ALLOWED_REASONING_LEVELS, REASONING_PROFILE


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
        self.assertEqual(PIPELINE["embeddings"], QUERY_PIPELINE["embeddings"] | {"block_embeddings": True})
