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


def bin_index(fraction: float, n_bins: int = 10) -> int:
    """Map fraction in [0, 1] to bin index in {0, ..., n_bins - 1}."""
    if not math.isfinite(fraction) or fraction <= 0.0:
        return 0
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
        if injected_fractions is None:
            fractions = np.zeros(n_samples, dtype=float)
        else:
            fractions = np.asarray(injected_fractions, dtype=float)
            if len(fractions) != n_samples:
                raise ValueError(f"expected {n_samples} injected fractions, got {len(fractions)}")

        scaled_p = np.zeros(n_samples, dtype=float)
        affected_fallback_rows = 0
        bin_eval_counts = {b: 0 for b in range(self.n_bins)}
        bin_fallback_counts = {b: 0 for b in range(self.n_bins)}
        bin_resolved_maps = {b: "fitted_bin_temperature" for b in range(self.n_bins)}

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
            else:
                affected_fallback_rows += 1
                bin_fallback_counts[b] += 1
                resolved = False

                # 1. Try global remasked map
                if self.global_remasked_map is not None:
                    try:
                        p_sub = self.global_remasked_map.predict_proba(features[i:i + 1])
                        validate_raw_probabilities(p_sub, expected_rows=1)
                        scaled_p[i] = float(p_sub[0, 1]) if p_sub.ndim == 2 else float(p_sub[0])
                        bin_resolved_maps[b] = "source_remasked_temperature"
                        resolved = True
                    except Exception as err:
                        failed_attempts.append({"bin": b, "fallback": "source_remasked_temperature", "error": str(err)})

                # 2. Try source map
                if not resolved and self.source_map is not None:
                    try:
                        p_sub = self.source_map.predict_proba(features[i:i + 1])
                        validate_raw_probabilities(p_sub, expected_rows=1)
                        scaled_p[i] = float(p_sub[0, 1]) if p_sub.ndim == 2 else float(p_sub[0])
                        bin_resolved_maps[b] = "source_temperature"
                        resolved = True
                    except Exception as err:
                        failed_attempts.append({"bin": b, "fallback": "source_temperature", "error": str(err)})

                # 3. Fallback to raw
                if not resolved:
                    scaled_p[i] = p_clipped[i]
                    bin_resolved_maps[b] = "raw"

        scaled_p = np.clip(scaled_p, self.clip_eps, 1.0 - self.clip_eps)
        self.last_diagnostics = {
            "affected_fallback_rows": affected_fallback_rows,
            "bin_support": self.bin_counts,
            "bin_eval_counts": bin_eval_counts,
            "bin_fallback_counts": bin_fallback_counts,
            "bin_resolved_maps": bin_resolved_maps,
            "failed_attempts": failed_attempts,
            "sparse_prediction_failures": len(failed_attempts),
        }
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

    try:
        features = rows_to_features(list(remasked_rows))
        raw = pipeline.predict_proba(features)
        raw_probs = validate_raw_probabilities(raw, expected_rows=len(remasked_rows))
        p_clipped = np.clip(raw_probs, clip_eps, 1.0 - clip_eps)
        z_all = np.log(p_clipped / (1.0 - p_clipped))
        y_all = np.asarray(remasked_labels, dtype=float)

        bin_temperatures: dict[int, float | None] = {}
        bin_fallbacks: dict[int, str | None] = {}
        bin_counts: dict[int, int] = {}

        bin_assignments = np.array([bin_index(f, n_bins) for f in missing_fractions])

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
