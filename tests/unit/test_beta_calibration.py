from __future__ import annotations

import numpy as np
import pytest

from shiftguard.calibration.beta import fit_beta_calibration
from shiftguard.calibration.sklearn_maps import frozen_pipeline
from shiftguard.predictors.logistic import fit_initial_logistic_regression
from shiftguard.preprocessing.tabular import fit_train_preprocessor, rows_to_features


def _setup_pipeline_and_rows():
    train_rows = []
    for i in range(120):
        train_rows.append({
            "row_id": i + 1,
            "age": 28 + (i % 30),
            "job": "blue-collar" if i % 2 == 0 else "technician",
            "marital": "single",
            "education": "basic.9y",
            "default": "no",
            "housing": "no",
            "loan": "no",
            "pdays": 999,
            "previous": 0,
            "poutcome": "nonexistent",
            "y": 1 if (i % 4 == 0) else 0,
        })
    preprocessor = fit_train_preprocessor(train_rows)
    predictor = fit_initial_logistic_regression(preprocessor.transform(train_rows), [int(r["y"]) for r in train_rows], 101)
    pipeline = frozen_pipeline(preprocessor, predictor)
    return pipeline, tuple(train_rows)


def test_beta_calibration_fits_and_predicts():
    pipeline, rows = _setup_pipeline_and_rows()
    labels = tuple(int(r["y"]) for r in rows[:50])
    fit = fit_beta_calibration(pipeline, rows[:50], labels)

    assert fit.record.fit_status == "fitted"
    assert fit.record.requested_method == "target_beta"
    assert fit.record.resolved_method == "target_beta"
    assert fit.record.labels_consumed == 50

    feat_array = rows_to_features(list(rows[:15]))
    probs = fit.probability_map.predict_proba(feat_array)

    assert probs.shape == (15, 2)
    assert np.all(probs >= 0.0) and np.all(probs <= 1.0)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0)
    # Check bounds a >= 0, b >= 0
    assert fit.probability_map.a >= 0.0
    assert fit.probability_map.b >= 0.0


def test_beta_calibration_one_class_fallback():
    pipeline, rows = _setup_pipeline_and_rows()
    labels = tuple([1] * 25)
    fit = fit_beta_calibration(pipeline, rows[:25], labels)

    assert fit.record.fit_status == "not_fitted"
    assert fit.record.fallback_reason == "one_class_or_empty"
    assert fit.record.resolved_method == "raw"
