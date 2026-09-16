from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from shiftguard.calibration.base import CalibrationRecord, ProbabilityMap
from shiftguard.calibration.sklearn_maps import CalibrationFit
from shiftguard.preprocessing.tabular import rows_to_features


class PlattLogOddsMap:
    def __init__(self, pipeline: Pipeline, lr: LogisticRegression, clip_eps: float = 1e-15) -> None:
        self.pipeline = pipeline
        self.lr = lr
        self.clip_eps = clip_eps

    def predict_proba(self, features) -> np.ndarray:
        raw_probs = self.pipeline.predict_proba(features)[:, 1]
        p_clipped = np.clip(raw_probs, self.clip_eps, 1.0 - self.clip_eps)
        x = np.log(p_clipped / (1.0 - p_clipped)).reshape(-1, 1)
        return self.lr.predict_proba(x)


def fit_platt_logodds(
    pipeline: Pipeline,
    rows: tuple[dict[str, str | int | None], ...],
    labels: tuple[int, ...],
    clip_eps: float = 1e-15,
) -> CalibrationFit:
    requested_method = "target_platt_logodds"
    if not labels or len(set(labels)) < 2:
        return CalibrationFit(
            pipeline,
            CalibrationRecord(requested_method, "raw", "not_fitted", "one_class_or_empty", len(labels), None),
        )
    try:
        features = rows_to_features(list(rows))
        raw_probs = pipeline.predict_proba(features)[:, 1]
        p_clipped = np.clip(raw_probs, clip_eps, 1.0 - clip_eps)
        x = np.log(p_clipped / (1.0 - p_clipped)).reshape(-1, 1)
        lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
        lr.fit(x, list(labels))
        prob_map = PlattLogOddsMap(pipeline, lr, clip_eps)
        test_probs = prob_map.predict_proba(features)
        if not np.isfinite(test_probs).all():
            raise ValueError("nonfinite_platt_probabilities")
    except Exception as error:
        return CalibrationFit(
            pipeline,
            CalibrationRecord(requested_method, "raw", "not_fitted", f"{type(error).__name__}: {error}", len(labels), None),
        )
    return CalibrationFit(
        prob_map,
        CalibrationRecord(requested_method, requested_method, "fitted", None, len(labels), None),
    )
