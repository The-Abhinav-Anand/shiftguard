from __future__ import annotations

import pytest

from shiftguard.experiments.evaluator import FinalTestEvaluator
from shiftguard.metrics.decision import (
    PREDECLARED_COST_GRID,
    DecisionLossItem,
    compute_decision_loss_grid,
    single_decision_loss,
)


def test_predeclared_cost_grid_thresholds():
    """Verify PREDECLARED_COST_GRID contains exactly 5 declared cost pairs and thresholds."""
    assert len(PREDECLARED_COST_GRID) == 5
    expected_thresholds = {
        (1.0, 1.0): 0.50,
        (1.0, 4.0): 0.20,
        (1.0, 9.0): 0.10,
        (4.0, 1.0): 0.80,
        (9.0, 1.0): 0.90,
    }
    for pair in PREDECLARED_COST_GRID:
        fp_c, fn_c = pair
        threshold = fp_c / (fp_c + fn_c)
        assert threshold == pytest.approx(expected_thresholds[pair])


def test_equality_at_threshold_convention():
    """Verify that predictions at exact threshold are classified as positive (y_prob >= threshold)."""
    # threshold for (1.0, 1.0) is 0.5
    # prob == 0.5, label == 0 -> should predict 1 -> False Positive
    item_fp = single_decision_loss([0], [0.5], fp_cost=1.0, fn_cost=1.0)
    assert item_fp.fp_count == 1
    assert item_fp.tn_count == 0
    assert item_fp.tp_count == 0
    assert item_fp.fn_count == 0
    assert item_fp.loss == pytest.approx(1.0)

    # prob == 0.5, label == 1 -> should predict 1 -> True Positive
    item_tp = single_decision_loss([1], [0.5], fp_cost=1.0, fn_cost=1.0)
    assert item_tp.tp_count == 1
    assert item_tp.fp_count == 0
    assert item_tp.tn_count == 0
    assert item_tp.fn_count == 0
    assert item_tp.loss == pytest.approx(0.0)


def test_confusion_cells_and_normalized_loss_hand_calculated():
    """Verify confusion matrix cells and normalized loss match hand calculations."""
    labels = [0, 0, 1, 1]
    probs = [0.1, 0.6, 0.4, 0.9]

    # At costs (1.0, 1.0), threshold = 0.5
    # y_pred = [0, 1, 0, 1]
    # Sample 0 (0, 0) -> TN
    # Sample 1 (0, 1) -> FP
    # Sample 2 (1, 0) -> FN
    # Sample 3 (1, 1) -> TP
    # TN=1, FP=1, FN=1, TP=1, N=4
    # loss = (1.0*1 + 1.0*1) / 4 = 0.5
    item = single_decision_loss(labels, probs, fp_cost=1.0, fn_cost=1.0)
    assert item == DecisionLossItem(
        fp_cost=1.0,
        fn_cost=1.0,
        threshold=0.5,
        fp_count=1,
        fn_count=1,
        tp_count=1,
        tn_count=1,
        n_samples=4,
        loss=0.5,
    )

    # At costs (1.0, 4.0), threshold = 0.2
    # y_pred = [0, 1, 1, 1]
    # TN=1, FP=1, FN=0, TP=2, N=4
    # loss = (1.0*1 + 4.0*0) / 4 = 0.25
    item_asym = single_decision_loss(labels, probs, fp_cost=1.0, fn_cost=4.0)
    assert item_asym.threshold == pytest.approx(0.2)
    assert item_asym.tn_count == 1
    assert item_asym.fp_count == 1
    assert item_asym.fn_count == 0
    assert item_asym.tp_count == 2
    assert item_asym.loss == pytest.approx(0.25)


def test_decision_loss_empty_inputs():
    """Empty inputs return zero counts and zero loss with declared threshold."""
    item = single_decision_loss([], [], fp_cost=1.0, fn_cost=1.0)
    assert item.n_samples == 0
    assert item.loss == 0.0
    assert item.threshold == 0.5
    assert item.fp_count == 0
    assert item.fn_count == 0
    assert item.tp_count == 0
    assert item.tn_count == 0


def test_decision_loss_rejection_of_invalid_inputs():
    """Reject non-positive costs, invalid cost grids, length mismatches, and invalid values."""
    # Non-positive costs
    with pytest.raises(ValueError, match="strictly positive"):
        single_decision_loss([0, 1], [0.2, 0.8], fp_cost=0.0, fn_cost=1.0)

    with pytest.raises(ValueError, match="strictly positive"):
        single_decision_loss([0, 1], [0.2, 0.8], fp_cost=-1.0, fn_cost=1.0)

    # Boolean costs
    with pytest.raises(TypeError, match="cannot be boolean"):
        single_decision_loss([0, 1], [0.2, 0.8], fp_cost=True, fn_cost=1.0)

    # Length mismatch
    with pytest.raises(ValueError, match="Mismatched sample counts"):
        single_decision_loss([0, 1, 0, 1], [0.5], fp_cost=1.0, fn_cost=1.0)

    # Empty cost grid
    with pytest.raises(ValueError, match="Cost grid must not be empty"):
        compute_decision_loss_grid([0, 1], [0.2, 0.8], cost_grid=())


def test_final_test_evaluator_entry_and_broadcasting_rejection():
    """A08 regression: verify evaluator entry rejects mismatched lengths and validates full metric suite."""
    evaluator = FinalTestEvaluator(labels=(0, 1, 0, 1), tier="stress")

    # Mismatched length (4 labels vs 1 probability)
    with pytest.raises(ValueError, match="Mismatched sample counts"):
        evaluator.score([0.5])

    # Valid score computation
    results = evaluator.score([0.1, 0.8, 0.3, 0.7])
    assert "brier_score" in results
    assert "log_loss" in results
    assert "reliability" in results
    assert "ece" in results
    assert "roc_auc" in results
    assert "average_precision" in results
    assert "prevalence" in results
    assert "decision_loss" in results
    assert len(results["decision_loss"]) == 5
