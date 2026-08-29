from __future__ import annotations

import pytest

from climatekg.extraction_models import SmallPaperExtraction
from climatekg.models import SourceBlock
from climatekg.small_paper import _validate_combined, cleaned_paper_blocks, combined_extraction_token_count
from climatekg.indexer import current_prompt_versions


def _block(block_id: str, block_type: str = "paragraph", text: str = "evidence") -> SourceBlock:
    return SourceBlock(
        id=block_id,
        paper_id="P1",
        order=int(block_id[-1]),
        page=1,
        section_path=["Results"],
        block_type=block_type,
        text=text,
        source_locator={"page": 1},
    )


def _result(conditioning: list[str] | None = None) -> SmallPaperExtraction:
    return SmallPaperExtraction.model_validate({
        "contexts": [
            {"temp_id": "C1", "label": "shared setting", "parent_temp_ids": [], "split_reason": None, "aliases": [], "spatial_support": None, "evidence_block_ids": ["B1"], "facet_seed_block_ids": ["B1"]},
            {"temp_id": "C2", "label": "treated setting", "parent_temp_ids": ["C1"], "split_reason": "explicit_transition_state", "aliases": [], "spatial_support": None, "evidence_block_ids": ["B2"], "facet_seed_block_ids": ["B2"]},
            {"temp_id": "C3", "label": "unrelated setting", "parent_temp_ids": [], "split_reason": None, "aliases": [], "spatial_support": None, "evidence_block_ids": ["B3"], "facet_seed_block_ids": ["B3"]},
        ],
        "facets": [
            {"temp_id": "F1", "context_temp_id": "C1", "domain": "land_surface", "notion": "land cover", "description": "The shared land cover.", "evidence_block_ids": ["B1"]},
            {"temp_id": "F2", "context_temp_id": "C3", "domain": "climate", "notion": "season", "description": "An unrelated season.", "evidence_block_ids": ["B3"]},
        ],
        "transitions": [
            {"temp_id": "T1", "from_context_temp_id": "C1", "to_context_temp_id": "C2", "label": "land treatment", "aliases": [], "description": "The treatment changes the land surface.", "evidence_block_ids": ["B2"], "claim_seed_block_ids": ["B2"]}
        ],
        "claims": [
            {"temp_id": "CL1", "scope_type": "transition", "scope_temp_id": "T1", "from": {"concept": "land treatment", "state": "applied"}, "to": {"concept": "temperature", "state": "increased"}, "relation": "causal", "description": "The treatment increased temperature.", "evidence_role": "OWN_RESULT", "conditioning_facet_temp_ids": conditioning or ["F1"], "evidence_block_ids": ["B2"]}
        ],
        "ambiguities": [],
    })


def test_cleaned_input_excludes_reference_blocks() -> None:
    blocks = [_block("B1", text="one"), _block("B2", "reference", "a cited reference")]
    assert [item.id for item in cleaned_paper_blocks(blocks)] == ["B1"]
    assert combined_extraction_token_count(blocks) == 1


def test_experimental_prompt_version_does_not_invalidate_staged_papers() -> None:
    assert "small_paper_extraction" not in current_prompt_versions()
    assert "small_paper_extraction" in current_prompt_versions(combined_route=True)


def test_combined_extraction_accepts_reachable_conditioning_facet() -> None:
    _validate_combined(_result(), [_block("B1"), _block("B2"), _block("B3")])


def test_combined_extraction_rejects_unreachable_conditioning_facet() -> None:
    with pytest.raises(ValueError, match="unreachable conditioning Facet"):
        _validate_combined(_result(["F2"]), [_block("B1"), _block("B2"), _block("B3")])


def test_combined_extraction_rejects_reference_evidence() -> None:
    result = _result()
    result.claims[0].evidence_block_ids = ["B4"]
    with pytest.raises(ValueError, match="invalid evidence"):
        _validate_combined(result, [_block("B1"), _block("B2"), _block("B3"), _block("B4", "reference")])
