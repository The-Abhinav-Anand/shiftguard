from __future__ import annotations

import numpy as np

from shiftguard.metrics.validation import validate_metric_inputs


def brier_score(
    labels: list[int] | tuple[int, ...] | np.ndarray,
    probabilities: list[float] | tuple[float, ...] | np.ndarray,
    scale_by_half: bool = True,
) -> float:
    """Match scikit-learn's binary ``brier_score_loss`` scaling contract."""
    y_true, y_prob = validate_metric_inputs(labels, probabilities, allow_empty=False)
    value = float(np.mean((y_prob - y_true) ** 2))
    return value if scale_by_half else value * 2


def log_loss(
    labels: list[int] | tuple[int, ...] | np.ndarray,
    probabilities: list[float] | tuple[float, ...] | np.ndarray,
    clip: float = 1e-15,
) -> float:
    y_true, y_prob = validate_metric_inputs(labels, probabilities, allow_empty=False)
    if not (isinstance(clip, (int, float)) and np.isfinite(clip) and 0 < clip < 0.5):
        raise ValueError(f"clip must be a finite float in (0, 0.5), got {clip}")
    values = np.clip(y_prob, clip, 1.0 - clip)
    return float(-np.mean(y_true * np.log(values) + (1.0 - y_true) * np.log(1.0 - values)))

