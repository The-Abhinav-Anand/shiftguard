from __future__ import annotations

import numpy as np

from shiftguard.metrics.validation import validate_metric_inputs


def reliability_bins(
    labels: list[int] | tuple[int, ...] | np.ndarray,
    probabilities: list[float] | tuple[float, ...] | np.ndarray,
    bins: int = 10,
) -> list[dict[str, float | int | None]]:
    if not (isinstance(bins, int) and not isinstance(bins, bool) and bins > 0):
        raise ValueError(f"bins must be a positive integer, got {bins}")
    y_true, y_prob = validate_metric_inputs(labels, probabilities, allow_empty=True)
    result = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        mask = (y_prob >= lower) & ((y_prob < upper) if index < bins - 1 else (y_prob <= upper))
        selected_values, selected_targets = y_prob[mask], y_true[mask]
        result.append({
            "lower": lower,
            "upper": upper,
            "count": int(mask.sum()),
            "mean_probability": float(selected_values.mean()) if len(selected_values) else None,
            "positive_fraction": float(selected_targets.mean()) if len(selected_targets) else None,
        })
    return result


def expected_calibration_error(
    labels: list[int] | tuple[int, ...] | np.ndarray,
    probabilities: list[float] | tuple[float, ...] | np.ndarray,
    bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (ECE) with equal-width bins."""
    y_true, y_prob = validate_metric_inputs(labels, probabilities, allow_empty=True)
    n_total = len(y_true)
    if n_total == 0:
        return 0.0
    b_data = reliability_bins(y_true, y_prob, bins=bins)
    ece = 0.0
    for b in b_data:
        count = int(b["count"])
        if count > 0 and b["mean_probability"] is not None and b["positive_fraction"] is not None:
            weight = count / n_total
            gap = abs(float(b["mean_probability"]) - float(b["positive_fraction"]))
            ece += weight * gap
    return float(ece)

