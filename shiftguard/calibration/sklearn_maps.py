from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.pipeline import Pipeline

from shiftguard.calibration.base import CalibrationRecord, ProbabilityMap
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
        inverse_temperature = float(calibrator.calibrated_classifiers_[0].calibrators[0].beta_)
    except (AttributeError, IndexError, TypeError, ValueError):
        return None
    return 1 / inverse_temperature if math.isfinite(inverse_temperature) and inverse_temperature > 0 else None


def fit_temperature(
    pipeline: Pipeline,
    rows: tuple[dict[str, str | int | None], ...],
    labels: tuple[int, ...],
    requested_method: str,
) -> CalibrationFit:
    if not labels or len(set(labels)) < 2:
        return CalibrationFit(pipeline, CalibrationRecord(requested_method, "raw", "not_fitted", "one_class_or_empty", len(labels), None))
    try:
        calibrator = CalibratedClassifierCV(FrozenEstimator(pipeline), method="temperature")
        calibrator.fit(rows_to_features(list(rows)), list(labels))
        temperature = _temperature(calibrator)
        probabilities = calibrator.predict_proba(rows_to_features(list(rows)))[:, 1]
        if temperature is None or not np.isfinite(probabilities).all():
            raise ValueError("invalid_temperature_or_prediction")
    except Exception as error:
        return CalibrationFit(pipeline, CalibrationRecord(requested_method, "raw", "not_fitted", f"{type(error).__name__}: {error}", len(labels), None))
    return CalibrationFit(calibrator, CalibrationRecord(requested_method, requested_method, "fitted", None, len(labels), temperature))
