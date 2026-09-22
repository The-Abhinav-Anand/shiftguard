from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.pipeline import Pipeline

from shiftguard.calibration.base import CalibrationRecord, ProbabilityMap, validate_raw_probabilities
from shiftguard.calibration.sklearn_maps import CalibrationFit
from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.preprocessing.tabular import rows_to_features


def validate_fractions(
    fractions: np.ndarray | Sequence[float] | None,
    expected_rows: int,
) -> np.ndarray:
    """Validate that fractions are 1D, finite, in [0, 1], and exactly match expected length."""
    if fractions is None:
        return np.zeros(expected_rows, dtype=float)
    arr = np.asarray(fractions)
    if arr.ndim != 1:
        raise ValueError(f"fractions must be 1-dimensional, got shape {arr.shape}")
    if len(arr) != expected_rows:
        raise ValueError(f"expected {expected_rows} fractions, got {len(arr)}")
    if not np.issubdtype(arr.dtype, np.number):
        raise ValueError("fractions must be numeric")
    arr_float = arr.astype(float)
    if not np.isfinite(arr_float).all():
        raise ValueError("fractions must be finite and contain no NaN/Inf values")
    if (arr_float < 0.0).any() or (arr_float > 1.0).any():
        raise ValueError("fractions must be in range [0, 1]")
    return arr_float


def bin_index(fraction: float, n_bins: int = 10) -> int:
    """Map fraction in [0, 1] to bin index in {0, ..., n_bins - 1}."""
    if not math.isfinite(fraction):
        raise ValueError(f"fraction must be finite, got {fraction}")
    if fraction < 0.0 or fraction > 1.0:
        raise ValueError(f"fraction must be in [0, 1], got {fraction}")
    if fraction >= 1.0:
        return n_bins - 1
    return min(n_bins - 1, max(0, int(math.floor(fraction * n_bins))))


class FractionBinnedTemperatureMap:
    def __init__(
        self,
        pipeline: Pipeline,
        bin_temperatures: dict[int, float | None],
        bin_fallbacks: dict[int, str | None],
        bin_counts: dict[int, int],
        global_remasked_map: ProbabilityMap | None = None,
        source_map: ProbabilityMap | None = None,
        clip_eps: float = 1e-15,
        n_bins: int = 10,
    ) -> None:
        self.pipeline = pipeline
        self.bin_temperatures = dict(bin_temperatures)
        self.bin_fallbacks = dict(bin_fallbacks)
        self.bin_counts = dict(bin_counts)
        self.global_remasked_map = global_remasked_map
        self.source_map = source_map
        self.clip_eps = clip_eps
        self.n_bins = n_bins
        self.last_diagnostics: dict[str, object] = {}

    def predict_proba(
        self,
        features: np.ndarray,
        injected_fractions: np.ndarray | Sequence[float] | None = None,
    ) -> np.ndarray:
        raw = self.pipeline.predict_proba(features)
        raw_probs = validate_raw_probabilities(raw, expected_rows=len(features))
        p_clipped = np.clip(raw_probs, self.clip_eps, 1.0 - self.clip_eps)
        z = np.log(p_clipped / (1.0 - p_clipped))

        n_samples = len(z)
        fractions = validate_fractions(injected_fractions, expected_rows=n_samples)

        scaled_p = np.zeros(n_samples, dtype=float)
        affected_fallback_rows = 0
        bin_eval_counts = {b: 0 for b in range(self.n_bins)}
        bin_fallback_counts = {b: 0 for b in range(self.n_bins)}

        resolution_counts: dict[str, int] = {
            "fitted_bin_temperature": 0,
            "source_remasked_temperature": 0,
            "source_temperature": 0,
            "raw": 0,
        }
        bin_resolution_counts: dict[int, dict[str, int]] = {
            b: {
                "fitted_bin_temperature": 0,
                "source_remasked_temperature": 0,
                "source_temperature": 0,
                "raw": 0,
            }
            for b in range(self.n_bins)
        }

        failed_attempts: list[dict[str, object]] = []

        for i in range(n_samples):
            b = bin_index(fractions[i], self.n_bins)
            bin_eval_counts[b] += 1
            t_b = self.bin_temperatures.get(b)

            if t_b is not None:
                scaled_z = z[i] / t_b
                if scaled_z >= 0:
                    prob = 1.0 / (1.0 + math.exp(-scaled_z))
                else:
                    prob = math.exp(scaled_z) / (1.0 + math.exp(scaled_z))
                scaled_p[i] = prob
                res_map = "fitted_bin_temperature"
            else:
                affected_fallback_rows += 1
                bin_fallback_counts[b] += 1
                resolved = False
                res_map = "raw"

                # 1. Try global remasked map
                if self.global_remasked_map is not None:
                    try:
                        p_sub = self.global_remasked_map.predict_proba(features[i:i + 1])
                        validate_raw_probabilities(p_sub, expected_rows=1)
                        scaled_p[i] = float(p_sub[0, 1]) if p_sub.ndim == 2 else float(p_sub[0])
                        res_map = "source_remasked_temperature"
                        resolved = True
                    except Exception as err:
                        failed_attempts.append({
                            "sample_index": i,
                            "bin": b,
                            "row_fraction": float(fractions[i]),
                            "fallback": "source_remasked_temperature",
                            "error": str(err),
                        })

                # 2. Try source map
                if not resolved and self.source_map is not None:
                    try:
                        p_sub = self.source_map.predict_proba(features[i:i + 1])
                        validate_raw_probabilities(p_sub, expected_rows=1)
                        scaled_p[i] = float(p_sub[0, 1]) if p_sub.ndim == 2 else float(p_sub[0])
                        res_map = "source_temperature"
                        resolved = True
                    except Exception as err:
                        failed_attempts.append({
                            "sample_index": i,
                            "bin": b,
                            "row_fraction": float(fractions[i]),
                            "fallback": "source_temperature",
                            "error": str(err),
                        })

                # 3. Fallback to raw
                if not resolved:
                    scaled_p[i] = p_clipped[i]
                    res_map = "raw"

            resolution_counts[res_map] += 1
            bin_resolution_counts[b][res_map] += 1

        bin_resolved_maps: dict[int, str] = {}
        for b in range(self.n_bins):
            b_counts = bin_resolution_counts[b]
            active_maps = [k for k, v in b_counts.items() if v > 0]
            if len(active_maps) == 1:
                bin_resolved_maps[b] = active_maps[0]
            elif len(active_maps) > 1:
                bin_resolved_maps[b] = "mixed"
            else:
                bin_resolved_maps[b] = "empty"

        scaled_p = np.clip(scaled_p, self.clip_eps, 1.0 - self.clip_eps)
        self.last_diagnostics = {
            "affected_fallback_rows": affected_fallback_rows,
            "bin_support": self.bin_counts,
            "bin_eval_counts": bin_eval_counts,
            "bin_fallback_counts": bin_fallback_counts,
            "resolution_counts": resolution_counts,
            "bin_resolution_counts": bin_resolution_counts,
            "bin_resolved_maps": bin_resolved_maps,
            "failed_attempts": failed_attempts,
            "sparse_prediction_failures": len(failed_attempts),
        }
        return np.column_stack([1.0 - scaled_p, scaled_p])


def _fit_single_temperature(z: np.ndarray, y: np.ndarray) -> float | None:
    """Fit a single positive temperature T > 0 minimizing binary cross-entropy on log-odds z and labels y.

    Uses stable log-temperature parameterization theta = log(T).
    Declares failure (returns None) for anti-correlated, separable, boundary-pinned, or nonfinite cases.
    """
    if len(z) < 2 or len(set(y)) < 2:
        return None

    if not np.all(np.isfinite(z)) or not np.all(np.isfinite(y)):
        return None

    # Necessary condition for finite positive T: positive alignment between predictions and labels
    cov_signal = float(np.sum((y - 0.5) * z))
    if cov_signal <= 1e-9:
        # Anti-correlated or uncorrelated: pressure toward infinity, no finite optimum
        return None

    lower_t, upper_t = 0.01, 20.0
    lower_theta, upper_theta = math.log(lower_t), math.log(upper_t)

    def nll(theta: float) -> float:
        t = math.exp(theta)
        scaled_z = z / t
        bce = np.maximum(scaled_z, 0.0) - scaled_z * y + np.log1p(np.exp(-np.abs(scaled_z)))
        return float(np.mean(bce))

    res = minimize_scalar(nll, bounds=(lower_theta, upper_theta), method="bounded")
    if not res.success or not math.isfinite(res.x):
        return None

    opt_theta = float(res.x)
    # Check if pushed to boundary (within 1e-3 of bounds in log-temperature space)
    if opt_theta <= lower_theta + 1e-3 or opt_theta >= upper_theta - 1e-3:
        # Constrained boundary solution (pressure toward 0 or infinity), not an interior finite optimum
        return None

    opt_t = float(math.exp(opt_theta))

    # Gradient check for interior stationary point: dL/d(theta) == 0
    scaled_z = z / opt_t
    sigma = 1.0 / (1.0 + np.exp(-np.clip(scaled_z, -50.0, 50.0)))
    grad = -float(np.mean((sigma - y) * scaled_z))
    if abs(grad) > 5e-3:
        return None

    return opt_t


def fit_source_fraction_binned_temperature(
    pipeline: Pipeline,
    remasked_rows: tuple[dict[str, str | int | None], ...],
    remasked_labels: tuple[int, ...],
    missing_fractions: np.ndarray,
    global_fit: CalibrationFit | ProbabilityMap | None,
    source_fit: CalibrationFit | ProbabilityMap | None = None,
    n_bins: int = 10,
    min_bin_samples: int = 10,
    clip_eps: float = 1e-15,
) -> CalibrationFit:
    requested_method = "source_fraction_binned_temperature"

    global_remasked_map: ProbabilityMap | None = None
    if isinstance(global_fit, CalibrationFit):
        if global_fit.record.fit_status == "fitted":
            global_remasked_map = global_fit.probability_map
    elif global_fit is not None:
        global_remasked_map = global_fit

    source_map: ProbabilityMap | None = None
    if isinstance(source_fit, CalibrationFit):
        if source_fit.record.fit_status == "fitted":
            source_map = source_fit.probability_map
    elif source_fit is not None:
        source_map = source_fit

    remasked_rows_list = list(remasked_rows)
    y_all = np.asarray(remasked_labels, dtype=float)
    if len(remasked_rows_list) != len(y_all):
        return CalibrationFit(
            pipeline,
            CalibrationRecord(requested_method, "source_remasked_temperature", "not_fitted", "remasked_rows and labels length mismatch", 0, None),
        )

    try:
        clean_fractions = validate_fractions(missing_fractions, expected_rows=len(remasked_rows_list))
        features = rows_to_features(remasked_rows_list)
        raw = pipeline.predict_proba(features)
        raw_probs = validate_raw_probabilities(raw, expected_rows=len(remasked_rows_list))
        p_clipped = np.clip(raw_probs, clip_eps, 1.0 - clip_eps)
        z_all = np.log(p_clipped / (1.0 - p_clipped))

        bin_temperatures: dict[int, float | None] = {}
        bin_fallbacks: dict[int, str | None] = {}
        bin_counts: dict[int, int] = {}

        bin_assignments = np.array([bin_index(f, n_bins) for f in clean_fractions])

        for b in range(n_bins):
            idx = np.where(bin_assignments == b)[0]
            bin_count = len(idx)
            bin_counts[b] = bin_count

            if bin_count < min_bin_samples or len(set(y_all[idx])) < 2:
                bin_temperatures[b] = None
                bin_fallbacks[b] = "sparse_fraction_bin"
            else:
                t_b = _fit_single_temperature(z_all[idx], y_all[idx])
                if t_b is not None:
                    bin_temperatures[b] = t_b
                    bin_fallbacks[b] = None
                else:
                    bin_temperatures[b] = None
                    bin_fallbacks[b] = "sparse_fraction_bin"

        prob_map = FractionBinnedTemperatureMap(
            pipeline=pipeline,
            bin_temperatures=bin_temperatures,
            bin_fallbacks=bin_fallbacks,
            bin_counts=bin_counts,
            global_remasked_map=global_remasked_map,
            source_map=source_map,
            clip_eps=clip_eps,
            n_bins=n_bins,
        )

        test_probs = prob_map.predict_proba(features[:min(10, len(features))])
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
