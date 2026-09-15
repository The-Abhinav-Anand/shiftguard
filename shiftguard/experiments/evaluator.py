from __future__ import annotations

from shiftguard.metrics.probability import brier_score, log_loss
from shiftguard.metrics.reliability import reliability_bins


class FinalTestEvaluator:
    def __init__(self, labels: tuple[int, ...]) -> None:
        self._labels = labels

    def score(self, probabilities: list[float]) -> dict[str, object]:
        return {"brier_score": brier_score(self._labels, probabilities, scale_by_half=True), "log_loss": log_loss(self._labels, probabilities, clip=1e-15), "reliability": reliability_bins(self._labels, probabilities, bins=10)}
