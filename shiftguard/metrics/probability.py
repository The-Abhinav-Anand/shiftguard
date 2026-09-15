from __future__ import annotations

import numpy as np


def brier_score(labels: list[int], probabilities: list[float], scale_by_half: bool = True) -> float:
    """Match scikit-learn's binary ``brier_score_loss`` scaling contract."""
    value = float(np.mean((np.asarray(probabilities) - np.asarray(labels)) ** 2))
    return value if scale_by_half else value * 2


def log_loss(labels: list[int], probabilities: list[float], clip: float = 1e-15) -> float:
    values = np.clip(np.asarray(probabilities), clip, 1 - clip)
    targets = np.asarray(labels)
    return float(-np.mean(targets * np.log(values) + (1 - targets) * np.log(1 - values)))
