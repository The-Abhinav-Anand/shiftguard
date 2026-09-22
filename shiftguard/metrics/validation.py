from __future__ import annotations

import numpy as np


def validate_metric_inputs(
    labels: list[int] | tuple[int, ...] | np.ndarray,
    probabilities: list[float] | tuple[float, ...] | np.ndarray,
    allow_empty: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Validate metric inputs for shape, length alignment, binary labels, and bounded probabilities.

    Parameters
    ----------
    labels : sequence of int
        Binary ground truth labels in {0, 1}.
    probabilities : sequence of float
        Predicted probabilities bounded in [0.0, 1.0].
    allow_empty : bool, default=True
        Whether empty sequences are permitted.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Validated 1D int array of labels and 1D float array of probabilities.
    """
    try:
        y_true = np.asarray(labels)
    except Exception as exc:
        raise ValueError(f"Failed to convert labels to numpy array: {exc}") from exc

    try:
        y_prob = np.asarray(probabilities)
    except Exception as exc:
        raise ValueError(f"Failed to convert probabilities to numpy array: {exc}") from exc

    if y_true.ndim != 1:
        raise ValueError(f"Labels must be 1-dimensional, got {y_true.ndim}D array with shape {y_true.shape}")
    if y_prob.ndim != 1:
        raise ValueError(f"Probabilities must be 1-dimensional, got {y_prob.ndim}D array with shape {y_prob.shape}")

    if len(y_true) != len(y_prob):
        raise ValueError(
            f"Mismatched sample counts: len(labels)={len(y_true)} != len(probabilities)={len(y_prob)}"
        )

    if len(y_true) == 0:
        if not allow_empty:
            raise ValueError("Sample count must be at least 1 (empty inputs not allowed)")
        return np.empty(0, dtype=int), np.empty(0, dtype=float)

    if y_true.dtype.kind not in ("i", "u", "b", "f"):
        raise ValueError(f"Labels must be numeric, got dtype {y_true.dtype}")

    if not np.all(np.isfinite(y_true)):
        raise ValueError("Labels must be finite numbers (no NaN or Inf)")

    if not np.all((y_true == 0) | (y_true == 1)):
        raise ValueError(f"Labels must be binary in {{0, 1}}, got unexpected values: {np.unique(y_true)}")

    y_true = y_true.astype(int)

    if y_prob.dtype.kind not in ("i", "u", "b", "f"):
        raise ValueError(f"Probabilities must be numeric, got dtype {y_prob.dtype}")

    y_prob = y_prob.astype(float)

    if not np.all(np.isfinite(y_prob)):
        raise ValueError("Probabilities must be finite numbers (no NaN or Inf)")

    if np.any((y_prob < 0.0) | (y_prob > 1.0)):
        raise ValueError("Probabilities must be bounded in [0.0, 1.0]")

    return y_true, y_prob


def validate_decision_costs(fp_cost: float, fn_cost: float) -> tuple[float, float]:
    """Validate decision costs are positive finite numbers."""
    if not isinstance(fp_cost, (int, float)) or not isinstance(fn_cost, (int, float)):
        raise TypeError(f"Costs must be numeric, got fp_cost={type(fp_cost).__name__}, fn_cost={type(fn_cost).__name__}")
    if isinstance(fp_cost, bool) or isinstance(fn_cost, bool):
        raise TypeError("Costs cannot be boolean")
    if not (np.isfinite(fp_cost) and np.isfinite(fn_cost)):
        raise ValueError(f"Costs must be finite numbers, got fp_cost={fp_cost}, fn_cost={fn_cost}")
    if fp_cost <= 0 or fn_cost <= 0:
        raise ValueError(f"Costs must be strictly positive, got fp_cost={fp_cost}, fn_cost={fn_cost}")
    return float(fp_cost), float(fn_cost)


def validate_cost_grid(
    cost_grid: tuple[tuple[float, float], ...] | list[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    """Validate that cost_grid is a non-empty sequence of positive finite cost pairs."""
    if not cost_grid:
        raise ValueError("Cost grid must not be empty")
    validated = []
    for idx, item in enumerate(cost_grid):
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError(f"Cost grid item at index {idx} must be a 2-tuple (fp_cost, fn_cost), got {item}")
        fp_c, fn_c = validate_decision_costs(item[0], item[1])
        validated.append((fp_c, fn_c))
    return tuple(validated)
