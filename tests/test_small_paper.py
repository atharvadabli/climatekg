from __future__ import annotations

import pytest

from climatekg.combined_extraction import EvidenceCatalog, flatten_small_paper_v4, render_evidence_catalog
from climatekg.extraction_models import SmallPaperExtraction, SmallPaperExtractionV4, constrained_small_paper_v4_schema
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


def _nested_result(conditioning_context: str = "C1") -> SmallPaperExtractionV4:
    return SmallPaperExtractionV4.model_validate({
        "contexts": [
            {
                "temp_id": "C1", "label": "shared setting", "parent_temp_ids": [], "split_reason": None,
                "aliases": [], "spatial_support": None, "evidence_handles": ["E001"],
                "facet_seed_handles": ["E001"],
                "facets": [{"facet_key": "land_cover", "domain": "land_surface", "notion": "land cover", "description": "The shared land cover condition.", "evidence_handles": ["E001"]}],
                "claims": [],
            },
            {
                "temp_id": "C2", "label": "treated setting", "parent_temp_ids": ["C1"],
                "split_reason": "explicit_transition_state", "aliases": [], "spatial_support": None,
                "evidence_handles": ["E002"], "facet_seed_handles": ["E002"], "facets": [],
                "claims": [{
                    "from": {"concept": "land treatment", "state": "applied"},
                    "to": {"concept": "temperature", "state": "increased"}, "relation": "causal",
                    "description": "The treatment increased temperature.", "evidence_role": "OWN_RESULT",
                    "conditioning_facets": [{"context_temp_id": conditioning_context, "facet_key": "land_cover"}],
                    "evidence_handles": ["E002"],
                }],
            },
        ],
        "transitions": [{
            "temp_id": "T1", "from_context_temp_id": "C1", "to_context_temp_id": "C2",
            "label": "land treatment", "aliases": [], "description": "The treatment changes the land surface.",
            "evidence_handles": ["E002"], "claim_seed_handles": ["E002"],
            "claims": [{
                "from": {"concept": "land treatment", "state": "applied"},
                "to": {"concept": "temperature", "state": "increased"}, "relation": "causal",
                "description": "The treatment increased temperature.", "evidence_role": "OWN_RESULT",
                "conditioning_facets": [{"context_temp_id": "C1", "facet_key": "land_cover"}],
                "evidence_handles": ["E002"],
            }],
        }],
        "ambiguities": [],
    })


def test_evidence_catalog_uses_short_handles_and_exact_mapping() -> None:
    blocks = [_block("B1"), _block("B2")]
    catalog = EvidenceCatalog.from_blocks(blocks)
    rendered = render_evidence_catalog(blocks, catalog)
    assert catalog.handle_to_block_id == {"E001": "B1", "E002": "B2"}
    assert "[E001]" in rendered and "[E002]" in rendered
    assert "[B1]" not in rendered and "[B2]" not in rendered


def test_evidence_catalog_rejects_empty_cleaned_input() -> None:
    with pytest.raises(ValueError, match="at least one cleaned non-reference SourceBlock"):
        EvidenceCatalog.from_blocks([])


def test_request_schema_enumerates_only_available_evidence_handles() -> None:
    schema = constrained_small_paper_v4_schema(["E001", "E002"]).model_json_schema()
    evidence_fields = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for name, child in value.items():
                if name in {"evidence_handles", "facet_seed_handles", "claim_seed_handles"}:
                    evidence_fields.append(child)
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(schema)
    assert evidence_fields
    assert all(field["items"]["enum"] == ["E001", "E002"] for field in evidence_fields)


def test_nested_claims_receive_containing_scope_and_flatten_exact_evidence() -> None:
    blocks = [_block("B1"), _block("B2")]
    flattened = flatten_small_paper_v4(_nested_result(), EvidenceCatalog.from_blocks(blocks))
    assert [(claim.scope_type, claim.scope_temp_id) for claim in flattened.claims] == [
        ("context", "C2"), ("transition", "T1")
    ]
    assert all(claim.evidence_block_ids == ["B2"] for claim in flattened.claims)
    _validate_combined(flattened, blocks)


def test_flattening_rejects_unknown_evidence_handle() -> None:
    result = _nested_result()
    result.contexts[0].evidence_handles = ["E999"]
    with pytest.raises(ValueError, match="unknown evidence handles"):
        flatten_small_paper_v4(result, EvidenceCatalog.from_blocks([_block("B1"), _block("B2")]))


def test_flattened_claim_still_rejects_unreachable_conditioning_facet() -> None:
    result = _nested_result()
    result.contexts.append(result.contexts[0].model_copy(update={"temp_id": "C3", "parent_temp_ids": []}))
    result.contexts[1].claims[0].conditioning_facets[0].context_temp_id = "C3"
    flattened = flatten_small_paper_v4(result, EvidenceCatalog.from_blocks([_block("B1"), _block("B2")]))
    with pytest.raises(ValueError, match="unreachable conditioning Facet"):
        _validate_combined(flattened, [_block("B1"), _block("B2")])
