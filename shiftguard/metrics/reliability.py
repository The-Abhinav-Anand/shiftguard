from __future__ import annotations

import numpy as np


def reliability_bins(labels: list[int], probabilities: list[float], bins: int = 10) -> list[dict[str, float | int | None]]:
    result = []
    values = np.asarray(probabilities)
    targets = np.asarray(labels)
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        mask = (values >= lower) & ((values < upper) if index < bins - 1 else (values <= upper))
        selected_values, selected_targets = values[mask], targets[mask]
        result.append({"lower": lower, "upper": upper, "count": int(mask.sum()), "mean_probability": float(selected_values.mean()) if len(selected_values) else None, "positive_fraction": float(selected_targets.mean()) if len(selected_targets) else None})
    return result
