import pytest

from climatekg.extract import partition_claim_blocks
from climatekg.extraction_models import WindowClaimBatch
from climatekg.models import SourceBlock
from climatekg.window_claims import validate_window_batch


def batch(**updates):
    claim = {"scope_type": "context", "scope_id": "C1",
             "from": {"concept": "evaporation", "state": "increase"},
             "to": {"concept": "rainfall", "state": "increase"},
             "relation": "associative", "description": "An association reported by the study.",
             "evidence_role": "OWN_RESULT", "evidence_block_ids": ["B1"]}
    claim.update(updates)
    return WindowClaimBatch.model_validate({"claims": [claim]})


def test_valid_window_claim():
    validate_window_batch(batch(), {"B1"}, {("context", "C1"): set()})


def test_schema_constrains_copied_evidence_ids():
    from climatekg.extraction_models import window_claim_schema
    schema = window_claim_schema(["B1"])
    schema.model_validate(batch().model_dump(by_alias=True))
    with pytest.raises(ValueError):
        schema.model_validate(batch(evidence_block_ids=["B2"]).model_dump(by_alias=True))


@pytest.mark.parametrize("updates", [
    {"scope_id": "C2"}, {"evidence_block_ids": ["B2"]},
    {"evidence_block_ids": []},
    {"analysis_cases": [{"label": "dry", "description": "Dry years", "evidence_block_ids": ["B2"]}]},
    {"analysis_comparison": {"dimension": "year", "case_labels": ["wet", "dry"], "description": "Different"}},
])
def test_reject_invalid_references(updates):
    with pytest.raises(ValueError):
        validate_window_batch(batch(**updates), {"B1"}, {("context", "C1"): set()})


def test_partition_preserves_all_passages_and_order():
    blocks = [SourceBlock(id=f"B{i}", paper_id="P", order=i, section_path=[f"section{i // 3}"],
                          block_type="paragraph", text="A reported finding. " * 20, source_locator={})
              for i in range(12)]
    parts = partition_claim_blocks(blocks, 150)
    assert len(parts) > 1
    assert [b.id for part in parts for b in part] == [b.id for b in blocks]


def test_full_pass_covers_text_without_old_claim_seeds(tmp_path):
    from climatekg.models import Context, Paper
    from climatekg.window_claims import extract_window_claims

    class Client:
        def __init__(self):
            self.calls = []

        def structured(self, **kwargs):
            self.calls.append(kwargs)
            return batch(conditioning_facet_ids=["F2"])

    paper = Paper(id="P", title="Study", source_file="study.pdf")
    context = Context(id="C1", paper_id="P", label="Study setting")
    blocks = [SourceBlock(id=bid, paper_id="P", order=i, block_type=kind,
                          text="A reported finding.", source_locator={})
              for i, (bid, kind) in enumerate([("B1", "paragraph"), ("B2", "table"), ("B3", "reference")])]
    client = Client()
    claims, _ = extract_window_claims(paper, [context], [], [], blocks, tmp_path, client)
    assert len(claims) == 1
    assert claims[0].conditioning_facet_ids == []
    import json
    report = json.loads((tmp_path / "extraction/window_claims/coverage.json").read_text())
    assert report["windows"][0]["removed_conditioning_links"][0]["facet_id"] == "F2"
    assert client.calls[0]["input_block_ids"] == ["B1", "B2"]
    extract_window_claims(paper, [context], [], [], blocks, tmp_path, client)
    assert len(client.calls) == 1
    blocks[0].text = "Changed evidence."
    extract_window_claims(paper, [context], [], [], blocks, tmp_path, client)
    assert len(client.calls) == 2
