from __future__ import annotations

from shiftguard.metrics.decision import compute_decision_loss_grid
from shiftguard.metrics.probability import brier_score, log_loss
from shiftguard.metrics.ranking import ranking_metrics
from shiftguard.metrics.reliability import expected_calibration_error, reliability_bins
from shiftguard.metrics.validation import validate_metric_inputs


class FinalTestEvaluator:
    def __init__(
        self,
        labels: tuple[int, ...] | list[int],
        tier: str = "baseline",
        cost_grid: tuple[tuple[float, float], ...] | None = None,
    ) -> None:
        self._labels = tuple(labels)
        self._tier = tier
        self._cost_grid = cost_grid

    def score(
        self,
        probabilities: list[float] | tuple[float, ...],
        include_stress_metrics: bool | None = None,
        cost_grid: tuple[tuple[float, float], ...] | None = None,
    ) -> dict[str, object]:
        y_true, y_prob = validate_metric_inputs(self._labels, probabilities, allow_empty=False)
        metrics: dict[str, object] = {
            "brier_score": brier_score(y_true, y_prob, scale_by_half=True),
            "log_loss": log_loss(y_true, y_prob, clip=1e-15),
            "reliability": reliability_bins(y_true, y_prob, bins=10),
        }
        stress = include_stress_metrics if include_stress_metrics is not None else (self._tier == "stress")
        if stress:
            ranking = ranking_metrics(y_true, y_prob)
            metrics["ece"] = expected_calibration_error(y_true, y_prob, bins=10)
            metrics["roc_auc"] = ranking["roc_auc"]
            metrics["average_precision"] = ranking["average_precision"]
            metrics["prevalence"] = ranking["prevalence"]
            active_grid = cost_grid if cost_grid is not None else self._cost_grid
            kwargs = {"cost_grid": active_grid} if active_grid is not None else {}
            metrics["decision_loss"] = compute_decision_loss_grid(y_true, y_prob, **kwargs)
        return metrics

