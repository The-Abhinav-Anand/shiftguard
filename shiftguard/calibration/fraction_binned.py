from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.pipeline import Pipeline

from shiftguard.calibration.base import CalibrationRecord, ProbabilityMap
from shiftguard.calibration.sklearn_maps import CalibrationFit
from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.preprocessing.tabular import EXPLICIT_MISSING_CATEGORY, rows_to_features


def bin_index(fraction: float, n_bins: int = 10) -> int:
    """Map fraction in [0, 1] to bin index in {0, ..., n_bins - 1}."""
    if fraction >= 1.0:
        return n_bins - 1
    if fraction <= 0.0:
        return 0
    return min(n_bins - 1, max(0, int(math.floor(fraction * n_bins))))


def _calculate_row_missing_fractions(features: np.ndarray, eligible_count: int = len(BANK_FEATURES)) -> np.ndarray:
    """Calculate newly missing fraction for each row in the features array."""
    n_rows = len(features)
    fractions = np.zeros(n_rows, dtype=float)
    for i in range(n_rows):
        missing_count = 0
        for val in features[i]:
            if val == EXPLICIT_MISSING_CATEGORY:
                missing_count += 1
            elif isinstance(val, (float, np.floating)) and np.isnan(val):
                missing_count += 1
        fractions[i] = missing_count / eligible_count if eligible_count > 0 else 0.0
    return fractions


class FractionBinnedTemperatureMap:
    def __init__(
        self,
        pipeline: Pipeline,
        bin_temperatures: dict[int, float],
        global_temperature: float,
        bin_fallbacks: dict[int, str | None],
        bin_counts: dict[int, int],
        clip_eps: float = 1e-15,
        n_bins: int = 10,
    ) -> None:
        self.pipeline = pipeline
        self.bin_temperatures = dict(bin_temperatures)
        self.global_temperature = float(global_temperature)
        self.bin_fallbacks = dict(bin_fallbacks)
        self.bin_counts = dict(bin_counts)
        self.clip_eps = clip_eps
        self.n_bins = n_bins

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        raw_probs = self.pipeline.predict_proba(features)[:, 1]
        p_clipped = np.clip(raw_probs, self.clip_eps, 1.0 - self.clip_eps)
        # Log-odds z
        z = np.log(p_clipped / (1.0 - p_clipped))

        fractions = _calculate_row_missing_fractions(features)
        scaled_p = np.zeros_like(z)

        for i in range(len(z)):
            b = bin_index(fractions[i], self.n_bins)
            temp = self.bin_temperatures.get(b, self.global_temperature)
            scaled_z = z[i] / temp
            # Stable sigmoid
            if scaled_z >= 0:
                prob = 1.0 / (1.0 + math.exp(-scaled_z))
            else:
                prob = math.exp(scaled_z) / (1.0 + math.exp(scaled_z))
            scaled_p[i] = prob

        scaled_p = np.clip(scaled_p, self.clip_eps, 1.0 - self.clip_eps)
        return np.column_stack([1.0 - scaled_p, scaled_p])


def _fit_single_temperature(z: np.ndarray, y: np.ndarray) -> float | None:
    """Fit a single positive temperature T > 0 minimizing binary cross-entropy on log-odds z and labels y."""
    if len(z) < 2 or len(set(y)) < 2:
        return None

    def nll(t: float) -> float:
        scaled_z = z / t
        bce = np.maximum(scaled_z, 0.0) - scaled_z * y + np.log1p(np.exp(-np.abs(scaled_z)))
        return float(np.mean(bce))

    res = minimize_scalar(nll, bounds=(0.01, 20.0), method="bounded")
    if res.success and math.isfinite(res.x) and res.x > 0:
        return float(res.x)
    return None


def fit_source_fraction_binned_temperature(
    pipeline: Pipeline,
    remasked_rows: tuple[dict[str, str | int | None], ...],
    remasked_labels: tuple[int, ...],
    missing_fractions: np.ndarray,
    global_fit: CalibrationFit,
    n_bins: int = 10,
    min_bin_samples: int = 10,
    clip_eps: float = 1e-15,
) -> CalibrationFit:
    requested_method = "source_fraction_binned_temperature"
    global_temp = getattr(global_fit.record, "fitted_temperature", None) or 1.0

    try:
        features = rows_to_features(list(remasked_rows))
        raw_probs = pipeline.predict_proba(features)[:, 1]
        p_clipped = np.clip(raw_probs, clip_eps, 1.0 - clip_eps)
        z_all = np.log(p_clipped / (1.0 - p_clipped))
        y_all = np.asarray(remasked_labels, dtype=float)

        bin_temperatures: dict[int, float] = {}
        bin_fallbacks: dict[int, str | None] = {}
        bin_counts: dict[int, int] = {}

        bin_assignments = np.array([bin_index(f, n_bins) for f in missing_fractions])

        for b in range(n_bins):
            idx = np.where(bin_assignments == b)[0]
            bin_count = len(idx)
            bin_counts[b] = bin_count

            if bin_count < min_bin_samples or len(set(y_all[idx])) < 2:
                bin_temperatures[b] = global_temp
                bin_fallbacks[b] = "sparse_fraction_bin"
            else:
                t_b = _fit_single_temperature(z_all[idx], y_all[idx])
                if t_b is not None:
                    bin_temperatures[b] = t_b
                    bin_fallbacks[b] = None
                else:
                    bin_temperatures[b] = global_temp
                    bin_fallbacks[b] = "sparse_fraction_bin"

        prob_map = FractionBinnedTemperatureMap(
            pipeline=pipeline,
            bin_temperatures=bin_temperatures,
            global_temperature=global_temp,
            bin_fallbacks=bin_fallbacks,
            bin_counts=bin_counts,
            clip_eps=clip_eps,
            n_bins=n_bins,
        )

        test_probs = prob_map.predict_proba(features[:10])
        if not np.isfinite(test_probs).all():
            raise ValueError("nonfinite_fraction_binned_probabilities")

    except Exception as error:
        return CalibrationFit(
            pipeline,
            CalibrationRecord(requested_method, "source_remasked_temperature", "not_fitted", f"{type(error).__name__}: {error}", 0, None),
        )

    return CalibrationFit(
        prob_map,
        CalibrationRecord(requested_method, requested_method, "fitted", None, 0, None),
    )
