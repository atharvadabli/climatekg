from scripts.run_profile_benchmark import _percentile


def test_percentile_interpolates_sorted_values() -> None:
    assert _percentile([30.0, 10.0, 20.0], 0.5) == 20.0
    assert _percentile([10.0, 20.0], 0.9) == 19.0
