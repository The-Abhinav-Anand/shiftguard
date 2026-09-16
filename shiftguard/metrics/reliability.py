from __future__ import annotations

import numpy as np


def reliability_bins(labels: list[int] | tuple[int, ...], probabilities: list[float] | tuple[float, ...], bins: int = 10) -> list[dict[str, float | int | None]]:
    result = []
    values = np.asarray(probabilities)
    targets = np.asarray(labels)
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        mask = (values >= lower) & ((values < upper) if index < bins - 1 else (values <= upper))
        selected_values, selected_targets = values[mask], targets[mask]
        result.append({"lower": lower, "upper": upper, "count": int(mask.sum()), "mean_probability": float(selected_values.mean()) if len(selected_values) else None, "positive_fraction": float(selected_targets.mean()) if len(selected_targets) else None})
    return result


def expected_calibration_error(
    labels: list[int] | tuple[int, ...],
    probabilities: list[float] | tuple[float, ...],
    bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (ECE) with 10 equal-width bins."""
    b_data = reliability_bins(labels, probabilities, bins=bins)
    n_total = len(labels)
    if n_total == 0:
        return 0.0
    ece = 0.0
    for b in b_data:
        count = int(b["count"])
        if count > 0 and b["mean_probability"] is not None and b["positive_fraction"] is not None:
            weight = count / n_total
            gap = abs(float(b["mean_probability"]) - float(b["positive_fraction"]))
            ece += weight * gap
    return float(ece)
