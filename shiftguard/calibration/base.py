from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProbabilityMap(Protocol):
    def predict_proba(self, features): ...


@dataclass(frozen=True)
class CalibrationRecord:
    requested_method: str
    resolved_method: str
    fit_status: str
    fallback_reason: str | None
    labels_consumed: int
    fitted_temperature: float | None


def validate_raw_probabilities(
    raw_probs: object,
    expected_rows: int | None = None,
) -> np.ndarray:
    """Validate binary classification raw probabilities before calibration or clipping.

    Checks:
    - Array conversion and finiteness (no NaN, inf, -inf)
    - Valid binary shape: (N, 2) or (N,)
    - Bounds: all values in [0.0, 1.0]
    - Row normalization: if 2D (N, 2), p_0 + p_1 == 1.0 +/- 1e-4
    - Expected row count if provided

    Returns:
    - 1D positive-class probability array of shape (N,) as float.

    Raises:
    - ValueError if validation fails.
    """
    import numpy as np

    arr = np.asarray(raw_probs, dtype=float)
    if not np.isfinite(arr).all():
        raise ValueError("raw probabilities contain NaN or infinite values")
    if arr.ndim == 2:
        if arr.shape[1] != 2:
            raise ValueError(f"expected binary 2-column probability array, got shape {arr.shape}")
        if (arr < 0.0).any() or (arr > 1.0).any():
            raise ValueError("raw probabilities outside [0.0, 1.0]")
        row_sums = arr.sum(axis=1)
        if not np.allclose(row_sums, 1.0, atol=1e-4):
            raise ValueError("raw probability rows do not sum to 1.0")
        p_pos = arr[:, 1]
    elif arr.ndim == 1:
        if (arr < 0.0).any() or (arr > 1.0).any():
            raise ValueError("raw probabilities outside [0.0, 1.0]")
        p_pos = arr
    else:
        raise ValueError(f"unexpected raw probability dimensions: {arr.ndim}")

    if expected_rows is not None and len(p_pos) != expected_rows:
        raise ValueError(f"expected {expected_rows} rows, got {len(p_pos)}")
    return p_pos
