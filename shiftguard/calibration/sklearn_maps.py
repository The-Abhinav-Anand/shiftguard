from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.pipeline import Pipeline

from shiftguard.calibration.base import CalibrationRecord, ProbabilityMap, validate_raw_probabilities
from shiftguard.preprocessing.tabular import TrainOnlyPreprocessor, rows_to_features


@dataclass(frozen=True)
class CalibrationFit:
    probability_map: ProbabilityMap
    record: CalibrationRecord


@dataclass(frozen=True)
class PredictionResolution:
    probabilities: list[float] | None
    resolved_method: str | None
    failures: tuple[dict[str, str], ...]


def predict_with_fallback(
    raw: ProbabilityMap,
    source: CalibrationFit,
    target: CalibrationFit | None,
    rows: tuple[dict[str, str | int | None], ...],
) -> tuple[dict[str, PredictionResolution], dict[str, dict[str, str]]]:
    """Resolve once per map on this feature set, without any evaluator or labels.

    The source result is reused by the target chain, including a cached failure.
    `attempts` counts unique prediction attempts; fit failures have no attempt.
    """
    features = rows_to_features(list(rows))
    resolutions: dict[str, PredictionResolution] = {}
    attempts: dict[str, dict[str, str]] = {}

    def resolve(method: str, probability_map: ProbabilityMap, fit: CalibrationFit | None, fallback: str | None) -> None:
        if fit is not None and fit.record.fit_status != "fitted":
            failure = {"method": method, "phase": "fit", "reason": fit.record.fallback_reason or "not_fitted"}
        else:
            try:
                values = np.asarray(probability_map.predict_proba(features), dtype=float)
                if values.shape != (len(rows), 2):
                    raise ValueError("invalid_probability_shape")
                if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
                    raise ValueError("invalid_probability_values")
                if not np.allclose(values.sum(axis=1), 1.0):
                    raise ValueError("probability_rows_do_not_sum_to_one")
            except Exception as error:
                # Estimator failures are recorded; evaluator errors never enter this boundary.
                failure = {"method": method, "phase": "prediction", "reason": f"{type(error).__name__}: {error}"}
                attempts[method] = {"status": "failed", "reason": failure["reason"]}
            else:
                attempts[method] = {"status": "succeeded"}
                resolutions[method] = PredictionResolution(values[:, 1].tolist(), method, ())
                return
        previous = resolutions[fallback] if fallback is not None else PredictionResolution(None, None, ())
        resolutions[method] = PredictionResolution(previous.probabilities, previous.resolved_method, (failure, *previous.failures))

    resolve("raw", raw, None, None)
    resolve("source_temperature", source.probability_map, source, "raw")
    if target is not None:
        resolve("target_temperature", target.probability_map, target, "source_temperature")
    return resolutions, attempts


def frozen_pipeline(preprocessor: TrainOnlyPreprocessor, predictor) -> Pipeline:
    return Pipeline([("preprocessor", preprocessor.transformer), ("predictor", predictor)])


def _temperature(calibrator: CalibratedClassifierCV) -> float | None:
    try:
        for estimator in getattr(calibrator, "calibrated_classifiers_", []):
            scale = getattr(estimator, "scale_", None)
            if scale is not None:
                value = float(np.asarray(scale).squeeze())
                if math.isfinite(value) and value > 0:
                    return value
            calibrators = getattr(estimator, "calibrators", None)
            if calibrators and hasattr(calibrators[0], "beta_"):
                inv_temp = float(calibrators[0].beta_)
                if math.isfinite(inv_temp) and inv_temp > 0:
                    return 1.0 / inv_temp
    except Exception:
        return None
    return None


def fit_temperature_calibration(
    pipeline: Pipeline,
    rows: tuple[dict[str, str | int | None], ...],
    labels: tuple[int, ...],
    requested_method: str,
) -> CalibrationFit:
    if not labels or len(set(labels)) < 2:
        return CalibrationFit(pipeline, CalibrationRecord(requested_method, "raw", "not_fitted", "one_class_or_empty", len(labels), None))
    try:
        features = rows_to_features(list(rows))
        raw = pipeline.predict_proba(features)
        validate_raw_probabilities(raw, expected_rows=len(rows))
        calibrator = CalibratedClassifierCV(FrozenEstimator(pipeline), method="temperature")
        calibrator.fit(features, list(labels))
        temperature = _temperature(calibrator)
        probabilities = calibrator.predict_proba(features)[:, 1]
        if temperature is None or not np.isfinite(probabilities).all():
            raise ValueError("invalid_temperature_or_prediction")
    except Exception as error:
        return CalibrationFit(pipeline, CalibrationRecord(requested_method, "raw", "not_fitted", f"{type(error).__name__}: {error}", len(labels), None))
    return CalibrationFit(calibrator, CalibrationRecord(requested_method, requested_method, "fitted", None, len(labels), temperature))


fit_temperature = fit_temperature_calibration


class IsotonicCalibrationMap:
    def __init__(self, pipeline: Pipeline, iso, clip_eps: float = 1e-15) -> None:
        self.pipeline = pipeline
        self.iso = iso
        self.clip_eps = clip_eps

    def predict_proba(self, features) -> np.ndarray:
        raw = self.pipeline.predict_proba(features)
        raw_probs = validate_raw_probabilities(raw, expected_rows=len(features))
        p_clipped = np.clip(raw_probs, self.clip_eps, 1.0 - self.clip_eps)
        cal_probs = self.iso.predict(p_clipped)
        cal_probs = np.clip(cal_probs, self.clip_eps, 1.0 - self.clip_eps)
        return np.column_stack([1.0 - cal_probs, cal_probs])


def fit_isotonic_calibration(
    pipeline: Pipeline,
    rows: tuple[dict[str, str | int | None], ...],
    labels: tuple[int, ...],
    clip_eps: float = 1e-15,
) -> CalibrationFit:
    from sklearn.isotonic import IsotonicRegression

    requested_method = "target_isotonic"
    if not labels or len(set(labels)) < 2:
        return CalibrationFit(
            pipeline,
            CalibrationRecord(requested_method, "raw", "not_fitted", "one_class_or_empty", len(labels), None),
        )
    try:
        features = rows_to_features(list(rows))
        raw = pipeline.predict_proba(features)
        raw_probs = validate_raw_probabilities(raw, expected_rows=len(rows))
        p_clipped = np.clip(raw_probs, clip_eps, 1.0 - clip_eps)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(p_clipped, list(labels))
        prob_map = IsotonicCalibrationMap(pipeline, iso, clip_eps)
        test_probs = prob_map.predict_proba(features)
        if not np.isfinite(test_probs).all():
            raise ValueError("nonfinite_isotonic_probabilities")
    except Exception as error:
        return CalibrationFit(
            pipeline,
            CalibrationRecord(requested_method, "raw", "not_fitted", f"{type(error).__name__}: {error}", len(labels), None),
        )
    return CalibrationFit(
        prob_map,
        CalibrationRecord(requested_method, requested_method, "fitted", None, len(labels), None),
    )


def predict_conditions_with_fallback(
    fits: dict[str, CalibrationFit | ProbabilityMap],
    fallback_graph: dict[str, str | None],
    rows: tuple[dict[str, str | int | None], ...],
    injected_fractions: np.ndarray | None = None,
) -> tuple[dict[str, PredictionResolution], dict[str, dict[str, str]]]:
    """Resolve predictions and fallbacks across arbitrary condition graphs before evaluator scoring."""
    features = rows_to_features(list(rows))
    resolutions: dict[str, PredictionResolution] = {}
    attempts: dict[str, dict[str, str]] = {}

    def resolve(method: str) -> None:
        if method in resolutions:
            return
        fallback = fallback_graph.get(method)
        if fallback is not None and fallback not in resolutions:
            resolve(fallback)

        fit = fits.get(method)
        if fit is None:
            previous = resolutions[fallback] if fallback is not None else PredictionResolution(None, None, ())
            resolutions[method] = previous
            return

        prob_map = fit.probability_map if isinstance(fit, CalibrationFit) else fit
        if isinstance(fit, CalibrationFit) and fit.record.fit_status != "fitted":
            failure = {"method": method, "phase": "fit", "reason": fit.record.fallback_reason or "not_fitted"}
        else:
            try:
                if hasattr(prob_map, "bin_temperatures"):
                    values = np.asarray(prob_map.predict_proba(features, injected_fractions=injected_fractions), dtype=float)
                else:
                    values = np.asarray(prob_map.predict_proba(features), dtype=float)
                if values.shape != (len(rows), 2):
                    raise ValueError("invalid_probability_shape")
                if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
                    raise ValueError("invalid_probability_values")
                if not np.allclose(values.sum(axis=1), 1.0):
                    raise ValueError("probability_rows_do_not_sum_to_one")
            except Exception as error:
                failure = {"method": method, "phase": "prediction", "reason": f"{type(error).__name__}: {error}"}
                attempts[method] = {"status": "failed", "reason": failure["reason"]}
            else:
                attempts[method] = {"status": "succeeded"}
                resolutions[method] = PredictionResolution(values[:, 1].tolist(), method, ())
                return

        previous = resolutions[fallback] if fallback is not None else PredictionResolution(None, None, ())
        resolutions[method] = PredictionResolution(previous.probabilities, previous.resolved_method, (failure, *previous.failures))

    for m in fits:
        resolve(m)
    return resolutions, attempts
