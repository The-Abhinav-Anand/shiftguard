from __future__ import annotations

import numpy as np
import pytest

from shiftguard.metrics.decision import compute_decision_loss_grid, single_decision_loss
from shiftguard.metrics.ranking import ranking_metrics
from shiftguard.metrics.reliability import expected_calibration_error, reliability_bins


def test_ranking_metrics_normal():
    labels = [0, 0, 1, 1, 0, 1]
    probs = [0.1, 0.2, 0.8, 0.9, 0.4, 0.7]

    res = ranking_metrics(labels, probs)
    assert res["roc_auc"] is not None
    assert 0.0 <= res["roc_auc"] <= 1.0
    assert res["average_precision"] is not None
    assert 0.0 <= res["average_precision"] <= 1.0
    assert res["prevalence"] == 0.5


def test_ranking_metrics_one_class():
    labels = [0, 0, 0, 0]
    probs = [0.1, 0.2, 0.3, 0.4]

    res = ranking_metrics(labels, probs)
    assert res["roc_auc"] is None
    assert res["average_precision"] is None
    assert res["prevalence"] == 0.0


def test_decision_loss_grid():
    labels = [0, 0, 1, 1]
    probs = [0.1, 0.6, 0.4, 0.9]

    grid = compute_decision_loss_grid(labels, probs)
    assert len(grid) == 5
    for item in grid:
        assert item["fp_cost"] > 0
        assert item["fn_cost"] > 0
        assert 0.0 < item["threshold"] < 1.0
        assert item["loss"] >= 0.0
        assert item["n_samples"] == 4
        assert item["fp_count"] + item["tn_count"] == 2
        assert item["fn_count"] + item["tp_count"] == 2


def test_ece_computation():
    labels = [0, 0, 1, 1]
    probs = [0.05, 0.15, 0.85, 0.95]
    ece = expected_calibration_error(labels, probs, bins=10)
    assert 0.0 <= ece <= 1.0
