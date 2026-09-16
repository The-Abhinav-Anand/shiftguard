from __future__ import annotations

from dataclasses import dataclass
import numpy as np


# Predeclared cost ratios (FP_cost, FN_cost)
PREDECLARED_COST_GRID = (
    (1.0, 1.0),  # threshold = 0.50
    (1.0, 4.0),  # threshold = 0.20
    (1.0, 9.0),  # threshold = 0.10
    (4.0, 1.0),  # threshold = 0.80
    (9.0, 1.0),  # threshold = 0.90
)


@dataclass(frozen=True)
class DecisionLossItem:
    fp_cost: float
    fn_cost: float
    threshold: float
    fp_count: int
    fn_count: int
    tp_count: int
    tn_count: int
    n_samples: int
    loss: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "fp_cost": self.fp_cost,
            "fn_cost": self.fn_cost,
            "threshold": self.threshold,
            "fp_count": self.fp_count,
            "fn_count": self.fn_count,
            "tp_count": self.tp_count,
            "tn_count": self.tn_count,
            "n_samples": self.n_samples,
            "loss": self.loss,
        }


def single_decision_loss(
    labels: list[int] | tuple[int, ...] | np.ndarray,
    probabilities: list[float] | tuple[float, ...] | np.ndarray,
    fp_cost: float,
    fn_cost: float,
) -> DecisionLossItem:
    if fp_cost <= 0 or fn_cost <= 0:
        raise ValueError(f"Costs must be positive, got fp_cost={fp_cost}, fn_cost={fn_cost}")

    y_true = np.asarray(labels, dtype=int)
    y_prob = np.asarray(probabilities, dtype=float)
    n = len(y_true)

    if n == 0:
        return DecisionLossItem(
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            threshold=fp_cost / (fp_cost + fn_cost),
            fp_count=0,
            fn_count=0,
            tp_count=0,
            tn_count=0,
            n_samples=0,
            loss=0.0,
        )

    threshold = fp_cost / (fp_cost + fn_cost)
    y_pred = (y_prob >= threshold).astype(int)

    fp = int(np.sum((y_pred == 1) & (y_true == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true == 1)))
    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    tn = int(np.sum((y_pred == 0) & (y_true == 0)))

    loss = float((fp_cost * fp + fn_cost * fn) / n)

    return DecisionLossItem(
        fp_cost=fp_cost,
        fn_cost=fn_cost,
        threshold=threshold,
        fp_count=fp,
        fn_count=fn,
        tp_count=tp,
        tn_count=tn,
        n_samples=n,
        loss=loss,
    )


def compute_decision_loss_grid(
    labels: list[int] | tuple[int, ...] | np.ndarray,
    probabilities: list[float] | tuple[float, ...] | np.ndarray,
    cost_grid: tuple[tuple[float, float], ...] = PREDECLARED_COST_GRID,
) -> list[dict[str, float | int]]:
    """Compute decision losses across the predeclared cost grid."""
    return [
        single_decision_loss(labels, probabilities, fp_c, fn_c).to_dict()
        for fp_c, fn_c in cost_grid
    ]
