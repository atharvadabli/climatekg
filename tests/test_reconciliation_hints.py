from climatekg.models import SourceBlock
from climatekg.reconcile import _explicit_hint_block_ids


def _block(block_id: str, order: int) -> SourceBlock:
    return SourceBlock(
        id=block_id,
        paper_id="P000008",
        page=3,
        order=order,
        section_path=["Results"],
        block_type="paragraph",
        text="evidence",
        source_locator={"page": 3},
    )


def test_explicit_hint_block_ids_retain_only_known_ids() -> None:
    blocks = [_block("P000008:S02:P0020", 20), _block("P000008:S02:P0025", 25)]
    text = "Compare P000008:S02:P0020 and P000008:S02:P0025, not P000008:S02:P9999."
    assert _explicit_hint_block_ids(text, blocks) == ["P000008:S02:P0020", "P000008:S02:P0025"]
