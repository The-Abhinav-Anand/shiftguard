from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from sklearn.pipeline import Pipeline

from shiftguard.calibration.base import CalibrationRecord, ProbabilityMap, validate_raw_probabilities
from shiftguard.calibration.sklearn_maps import CalibrationFit
from shiftguard.preprocessing.tabular import rows_to_features


class BetaCalibrationMap:
    def __init__(self, pipeline: Pipeline, a: float, b: float, c: float, clip_eps: float = 1e-15) -> None:
        self.pipeline = pipeline
        self.a = float(a)
        self.b = float(b)
        self.c = float(c)
        self.clip_eps = clip_eps

    def predict_proba(self, features) -> np.ndarray:
        raw = self.pipeline.predict_proba(features)
        raw_probs = validate_raw_probabilities(raw, expected_rows=len(features))
        p_clipped = np.clip(raw_probs, self.clip_eps, 1.0 - self.clip_eps)
        log_p = np.log(p_clipped)
        log_1_minus_p = np.log(1.0 - p_clipped)
        z = self.a * log_p - self.b * log_1_minus_p + self.c
        # Numerically stable sigmoid: 1 / (1 + exp(-z))
        pos_probs = np.where(z >= 0, 1.0 / (1.0 + np.exp(-z)), np.exp(z) / (1.0 + np.exp(z)))
        pos_probs = np.clip(pos_probs, self.clip_eps, 1.0 - self.clip_eps)
        return np.column_stack([1.0 - pos_probs, pos_probs])


def _beta_loss_and_grad(
    params: np.ndarray,
    log_p: np.ndarray,
    log_1_minus_p: np.ndarray,
    y: np.ndarray,
    l2_reg: float = 0.01,
) -> tuple[float, np.ndarray]:
    a, b, c = params
    z = a * log_p - b * log_1_minus_p + c

    # Stable BCE loss: max(z, 0) - z*y + log(1 + exp(-|z|))
    bce = np.maximum(z, 0.0) - z * y + np.log1p(np.exp(-np.abs(z)))
    reg = 0.5 * l2_reg * ((a - 1.0) ** 2 + (b - 1.0) ** 2 + c ** 2)
    loss = float(np.sum(bce) + reg)

    # Sigmoid prediction
    p_hat = np.where(z >= 0, 1.0 / (1.0 + np.exp(-z)), np.exp(z) / (1.0 + np.exp(z)))
    diff = p_hat - y

    grad_a = float(np.sum(diff * log_p) + l2_reg * (a - 1.0))
    grad_b = float(np.sum(diff * (-log_1_minus_p)) + l2_reg * (b - 1.0))
    grad_c = float(np.sum(diff) + l2_reg * c)
    return loss, np.array([grad_a, grad_b, grad_c])


def fit_beta_calibration(
    pipeline: Pipeline,
    rows: tuple[dict[str, str | int | None], ...],
    labels: tuple[int, ...],
    clip_eps: float = 1e-15,
    l2_reg: float = 0.01,
) -> CalibrationFit:
    requested_method = "target_beta"
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
        log_p = np.log(p_clipped)
        log_1_minus_p = np.log(1.0 - p_clipped)
        y = np.asarray(labels, dtype=float)

        # Initial guess: a=1, b=1, c=0 (identity map)
        init_params = np.array([1.0, 1.0, 0.0])
        bounds = [(0.0, None), (0.0, None), (None, None)]

        res = minimize(
            fun=_beta_loss_and_grad,
            x0=init_params,
            args=(log_p, log_1_minus_p, y, l2_reg),
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 500, "ftol": 1e-9},
        )

        if not res.success:
            raise ValueError(f"optimizer_failed: {res.message}")

        a, b, c = res.x
        if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(c) and a >= 0 and b >= 0):
            raise ValueError("degenerate_beta_parameters")

        prob_map = BetaCalibrationMap(pipeline, a, b, c, clip_eps)
        test_probs = prob_map.predict_proba(features)
        if not np.isfinite(test_probs).all():
            raise ValueError("nonfinite_beta_probabilities")
    except Exception as error:
        return CalibrationFit(
            pipeline,
            CalibrationRecord(requested_method, "raw", "not_fitted", f"{type(error).__name__}: {error}", len(labels), None),
        )
    return CalibrationFit(
        prob_map,
        CalibrationRecord(requested_method, requested_method, "fitted", None, len(labels), None),
    )
