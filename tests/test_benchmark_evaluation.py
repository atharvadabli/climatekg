from scripts.evaluate_three_system_benchmark import (
    CLAIM_ID_RE,
    PLAIN_CITATION_RE,
    condition_coverage,
    passage_supports_block,
    sentence_citation_coverage,
)


def test_source_block_match_accepts_contained_support() -> None:
    block = "Cross-patch circulation reduces the surface temperature contrast."
    passage = f"The study reports the following result: {block} This occurs under weak wind."
    assert passage_supports_block(passage, block)


def test_condition_coverage_uses_content_tokens() -> None:
    retained, total = condition_coverage(
        "The experiment uses 14.4 km dry and wet patches with zero background wind.",
        ["14.4 km", "dry and wet patches", "zero background wind"],
    )
    assert (retained, total) == (3, 3)


def test_sentence_citation_coverage_is_not_identifier_validity() -> None:
    answer = (
        "The supported experiment substantially changes local afternoon convective cloud depth [S1]. "
        "This second long scientific statement has no evidence identifier at all."
    )
    assert sentence_citation_coverage(answer, PLAIN_CITATION_RE) == 0.5
    assert CLAIM_ID_RE.search("R2_P000001:P000001_CL002")
