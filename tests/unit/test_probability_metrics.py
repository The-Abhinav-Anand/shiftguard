from __future__ import annotations

import math
import numpy as np
import pytest
from sklearn.metrics import brier_score_loss

from shiftguard.metrics.probability import brier_score, log_loss


def test_brier_score_hand_calculated_and_scaled():
    """Verify Brier score hand-calculated exact value and scaling."""
    labels = [0, 1, 1, 0]
    probs = [0.1, 0.8, 0.4, 0.2]

    # Hand-calculation:
    # (0.1 - 0)^2 = 0.01
    # (0.8 - 1)^2 = 0.04
    # (0.4 - 1)^2 = 0.36
    # (0.2 - 0)^2 = 0.04
    # Mean = 0.45 / 4 = 0.1125
    expected_half = 0.1125
    expected_full = 0.225

    actual_half = brier_score(labels, probs, scale_by_half=True)
    actual_full = brier_score(labels, probs, scale_by_half=False)

    assert actual_half == pytest.approx(expected_half, abs=1e-12)
    assert actual_full == pytest.approx(expected_full, abs=1e-12)
    # Check scikit-learn match
    assert actual_half == pytest.approx(brier_score_loss(labels, probs), abs=1e-12)


def test_log_loss_hand_calculated():
    """Verify log-loss against analytical negative log-likelihood."""
    labels = [0, 1]
    probs = [0.2, 0.7]

    # Hand-calculation:
    # -(ln(1 - 0.2) + ln(0.7)) / 2 = -(ln(0.8) + ln(0.7)) / 2
    # ln(0.8) = -0.22314355131420976, ln(0.7) = -0.35667494393873245
    # sum = -0.5798184952529422 -> mean = 0.2899092476264711
    expected = -(math.log(0.8) + math.log(0.7)) / 2.0
    assert log_loss(labels, probs) == pytest.approx(expected, abs=1e-12)


def test_log_loss_extreme_clipping():
    """Verify 1e-15 clipping prevents log(0) domain errors."""
    labels = [0, 1]
    probs = [0.0, 1.0]
    loss_perfect = log_loss(labels, probs, clip=1e-15)
    # -ln(1 - 1e-15) ≈ 1e-15
    assert loss_perfect == pytest.approx(1e-15, abs=1e-14)

    # Inverted: 100% confident errors
    probs_inverted = [1.0, 0.0]
    loss_worst = log_loss(labels, probs_inverted, clip=1e-15)
    # -ln(1e-15) ≈ 34.538776; in float64, 1.0 - (1.0 - 1e-15) has rounding at 1e-16
    assert loss_worst == pytest.approx(-math.log(1e-15), rel=1e-4)


def test_reject_silent_broadcasting():
    """A08 regression: reject broadcastable length mismatches (e.g. 4 labels vs 1 prob)."""
    labels = [0, 1, 0, 1]
    probs = [0.5]

    with pytest.raises(ValueError, match="Mismatched sample counts"):
        brier_score(labels, probs)

    with pytest.raises(ValueError, match="Mismatched sample counts"):
        log_loss(labels, probs)


def test_reject_multidimensional_inputs():
    """Inputs must be strictly 1-dimensional."""
    labels_2d = np.array([[0, 1], [1, 0]])
    probs_2d = np.array([[0.2, 0.8], [0.7, 0.3]])

    with pytest.raises(ValueError, match="1-dimensional"):
        brier_score(labels_2d, probs_2d)

    with pytest.raises(ValueError, match="1-dimensional"):
        log_loss(labels_2d, probs_2d)


def test_reject_nonbinary_and_nonfinite_labels():
    """Labels must be finite binary {0, 1}."""
    probs = [0.3, 0.7]

    with pytest.raises(ValueError, match="binary"):
        brier_score([0, 2], probs)

    with pytest.raises(ValueError, match="binary"):
        brier_score([-1, 1], probs)

    with pytest.raises(ValueError, match="binary"):
        brier_score([0.5, 0.5], probs)

    with pytest.raises(ValueError, match="finite"):
        brier_score([float("nan"), 1], probs)


def test_reject_invalid_probabilities():
    """Probabilities must be finite in [0.0, 1.0]."""
    labels = [0, 1]

    with pytest.raises(ValueError, match="bounded in"):
        brier_score(labels, [-0.01, 0.5])

    with pytest.raises(ValueError, match="bounded in"):
        brier_score(labels, [0.5, 1.01])

    with pytest.raises(ValueError, match="finite"):
        brier_score(labels, [float("nan"), 0.5])

    with pytest.raises(ValueError, match="finite"):
        brier_score(labels, [float("inf"), 0.5])


def test_reject_empty_inputs():
    """Brier and log loss require at least 1 sample."""
    with pytest.raises(ValueError, match="at least 1"):
        brier_score([], [])

    with pytest.raises(ValueError, match="at least 1"):
        log_loss([], [])
