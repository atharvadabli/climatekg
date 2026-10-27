import unittest

from climatekg.atomic_reextract import _scope_blocks
from climatekg.models import Claim, FinalPaper


class AtomicReextractTests(unittest.TestCase):
    def test_scope_blocks_keep_evidence_and_only_same_section_neighbours(self):
        paper = FinalPaper.model_validate(
            {
                "paper": {"id": "P1", "title": "Test", "year": 2020, "doi": None, "source_file": "x.pdf"},
                "source_blocks": [
                    {"id": "B1", "paper_id": "P1", "order": 1, "page": 1, "section_path": ["Results"], "block_type": "paragraph", "text": "a", "source_locator": {}},
                    {"id": "B2", "paper_id": "P1", "order": 2, "page": 1, "section_path": ["Results"], "block_type": "paragraph", "text": "b", "source_locator": {}},
                    {"id": "B3", "paper_id": "P1", "order": 3, "page": 2, "section_path": ["Discussion"], "block_type": "paragraph", "text": "c", "source_locator": {}},
                ],
                "contexts": [{"id": "C1", "paper_id": "P1", "label": "setting"}],
                "facets": [], "transitions": [],
                "claims": [{"id": "CL1", "paper_id": "P1", "scope_type": "context", "scope_id": "C1", "from": {"concept": "a", "state": "increase"}, "to": {"concept": "b", "state": "increase"}, "relation": "causal", "description": "a increases b", "evidence_role": "OWN_RESULT", "evidence_block_ids": ["B2"]}],
                "states": [],
            }
        )
        selected = _scope_blocks(paper, paper.claims)
        self.assertEqual([item.id for item in selected], ["B1", "B2"])


if __name__ == "__main__":
    unittest.main()
