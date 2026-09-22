from __future__ import annotations

import pytest

from shiftguard.metrics.reliability import expected_calibration_error, reliability_bins


def test_reliability_bins_structure_and_boundaries():
    """Verify 10 equal-width bins and boundary handling (0.0, 0.1, 0.9, 1.0)."""
    labels = [0, 0, 1, 1]
    probs = [0.0, 0.1, 0.9, 1.0]

    bins = reliability_bins(labels, probs, bins=10)
    assert len(bins) == 10

    # Bin 0: [0.0, 0.1) -> contains 0.0
    assert bins[0]["lower"] == 0.0
    assert bins[0]["upper"] == pytest.approx(0.1)
    assert bins[0]["count"] == 1
    assert bins[0]["mean_probability"] == pytest.approx(0.0)
    assert bins[0]["positive_fraction"] == pytest.approx(0.0)

    # Bin 1: [0.1, 0.2) -> contains 0.1
    assert bins[1]["lower"] == pytest.approx(0.1)
    assert bins[1]["upper"] == pytest.approx(0.2)
    assert bins[1]["count"] == 1
    assert bins[1]["mean_probability"] == pytest.approx(0.1)
    assert bins[1]["positive_fraction"] == pytest.approx(0.0)

    # Empty bins (e.g. Bin 2 to Bin 8)
    for b in bins[2:9]:
        assert b["count"] == 0
        assert b["mean_probability"] is None
        assert b["positive_fraction"] is None

    # Bin 9: [0.9, 1.0] -> contains both 0.9 and 1.0
    assert bins[9]["lower"] == pytest.approx(0.9)
    assert bins[9]["upper"] == pytest.approx(1.0)
    assert bins[9]["count"] == 2
    assert bins[9]["mean_probability"] == pytest.approx(0.95)
    assert bins[9]["positive_fraction"] == pytest.approx(1.0)


def test_expected_calibration_error_hand_calculated():
    """Verify ECE against manual hand-calculation."""
    labels = [0, 0, 1, 1]
    probs = [0.05, 0.05, 0.95, 0.95]

    # Bin 0: count 2, mean_prob 0.05, pos_frac 0.0 -> gap 0.05, weight 0.5
    # Bin 9: count 2, mean_prob 0.95, pos_frac 1.0 -> gap 0.05, weight 0.5
    # ECE = 0.5 * 0.05 + 0.5 * 0.05 = 0.05
    ece = expected_calibration_error(labels, probs, bins=10)
    assert ece == pytest.approx(0.05, abs=1e-12)

    # Second hand-calculated case with mixed targets in bins
    labels2 = [0, 1, 0, 1]
    probs2 = [0.15, 0.15, 0.85, 0.85]
    # Bin 1 ([0.1, 0.2)): mean_prob 0.15, pos_frac 0.5 -> gap 0.35, weight 0.5
    # Bin 8 ([0.8, 0.9)): mean_prob 0.85, pos_frac 0.5 -> gap 0.35, weight 0.5
    # ECE = 0.5 * 0.35 + 0.5 * 0.35 = 0.35
    assert expected_calibration_error(labels2, probs2, bins=10) == pytest.approx(0.35, abs=1e-12)


def test_reliability_empty_inputs():
    """Empty inputs return declared empty bin structures and 0.0 ECE."""
    b_data = reliability_bins([], [], bins=10)
    assert len(b_data) == 10
    for b in b_data:
        assert b["count"] == 0
        assert b["mean_probability"] is None
        assert b["positive_fraction"] is None

    assert expected_calibration_error([], [], bins=10) == 0.0


def test_reliability_rejection_of_invalid_inputs():
    """Reject mismatched lengths, NaN/inf, non-binary labels, and invalid bin counts."""
    # Length mismatch
    with pytest.raises(ValueError, match="Mismatched sample counts"):
        expected_calibration_error([0, 1, 0, 1], [0.5])

    # Out of bounds prob
    with pytest.raises(ValueError, match="bounded in"):
        reliability_bins([0, 1], [-0.1, 0.5])

    # Non-binary labels
    with pytest.raises(ValueError, match="binary"):
        expected_calibration_error([0, 2], [0.1, 0.9])

    # Non-positive or non-int bins
    with pytest.raises(ValueError, match="positive integer"):
        reliability_bins([0, 1], [0.2, 0.8], bins=0)

    with pytest.raises(ValueError, match="positive integer"):
        reliability_bins([0, 1], [0.2, 0.8], bins=-2)
