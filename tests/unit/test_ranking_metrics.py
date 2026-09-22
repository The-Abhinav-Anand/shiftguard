from __future__ import annotations

import pytest
from sklearn.metrics import average_precision_score, roc_auc_score

from shiftguard.metrics.ranking import ranking_metrics


def test_ranking_metrics_hand_calculated_auroc_and_ap():
    """Verify AUROC and AP match hand-calculated analytical values."""
    labels = [0, 0, 1, 1]
    probs = [0.1, 0.4, 0.35, 0.8]

    # Hand-calculation for AUROC:
    # Positives: {0.35, 0.8}, Negatives: {0.1, 0.4}
    # Concordant pairs: (0.35 > 0.1: 1), (0.35 > 0.4: 0), (0.8 > 0.1: 1), (0.8 > 0.4: 1)
    # Sum = 3 -> AUC = 3 / (2 * 2) = 0.75
    expected_auroc = 0.75

    # Hand-calculation for Average Precision (scikit-learn step function):
    # Ranked: 0.8 (pos), 0.4 (neg), 0.35 (pos), 0.1 (neg)
    # Precision at pos 0.8: 1/1 = 1.0, recall step = 0.5
    # Precision at pos 0.35: 2/3, recall step = 0.5
    # AP = 1.0 * 0.5 + (2/3) * 0.5 = 5/6 ≈ 0.8333333333333333
    expected_ap = 5.0 / 6.0
    expected_prevalence = 0.5

    metrics = ranking_metrics(labels, probs)
    assert metrics["roc_auc"] == pytest.approx(expected_auroc, abs=1e-12)
    assert metrics["average_precision"] == pytest.approx(expected_ap, abs=1e-12)
    assert metrics["prevalence"] == pytest.approx(expected_prevalence, abs=1e-12)

    # Double check against scikit-learn
    assert metrics["roc_auc"] == pytest.approx(roc_auc_score(labels, probs), abs=1e-12)
    assert metrics["average_precision"] == pytest.approx(average_precision_score(labels, probs), abs=1e-12)


def test_ranking_metrics_perfect_and_inverted():
    """Verify perfect discrimination and complete inversion."""
    labels = [0, 0, 1, 1]
    perfect_probs = [0.1, 0.2, 0.8, 0.9]
    res_perfect = ranking_metrics(labels, perfect_probs)
    assert res_perfect["roc_auc"] == pytest.approx(1.0)
    assert res_perfect["average_precision"] == pytest.approx(1.0)

    inverted_probs = [0.9, 0.8, 0.2, 0.1]
    res_inverted = ranking_metrics(labels, inverted_probs)
    assert res_inverted["roc_auc"] == pytest.approx(0.0)
    assert res_inverted["average_precision"] == pytest.approx(5.0 / 12.0)


def test_ranking_metrics_single_class_preserves_none():
    """Single-class inputs return None for AUROC/AP and do not fabricate 0.0."""
    all_zeros = ranking_metrics([0, 0, 0], [0.1, 0.2, 0.3])
    assert all_zeros["roc_auc"] is None
    assert all_zeros["average_precision"] is None
    assert all_zeros["prevalence"] == pytest.approx(0.0)

    all_ones = ranking_metrics([1, 1, 1], [0.7, 0.8, 0.9])
    assert all_ones["roc_auc"] is None
    assert all_ones["average_precision"] is None
    assert all_ones["prevalence"] == pytest.approx(1.0)


def test_ranking_metrics_empty_inputs():
    """Empty inputs return None for all fields."""
    res = ranking_metrics([], [])
    assert res["roc_auc"] is None
    assert res["average_precision"] is None
    assert res["prevalence"] is None


def test_ranking_metrics_input_validation():
    """Mismatched sample counts, NaN, and non-binary labels must be rejected."""
    with pytest.raises(ValueError, match="Mismatched sample counts"):
        ranking_metrics([0, 1, 0, 1], [0.5])

    with pytest.raises(ValueError, match="binary"):
        ranking_metrics([0, 2], [0.3, 0.7])

    with pytest.raises(ValueError, match="finite"):
        ranking_metrics([0, 1], [float("nan"), 0.5])
