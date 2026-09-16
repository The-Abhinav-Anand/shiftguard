from __future__ import annotations

import numpy as np
import pytest

from shiftguard.calibration.platt_logodds import fit_platt_logodds
from shiftguard.calibration.sklearn_maps import frozen_pipeline
from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.predictors.logistic import fit_initial_logistic_regression
from shiftguard.preprocessing.tabular import fit_train_preprocessor


def _setup_pipeline_and_rows():
    train_rows = []
    for i in range(100):
        train_rows.append({
            "row_id": i + 1,
            "age": 30 + (i % 25),
            "job": "admin.",
            "marital": "married",
            "education": "university.degree",
            "default": "no",
            "housing": "yes",
            "loan": "no",
            "pdays": 999 if i % 2 == 0 else 5,
            "previous": 0 if i % 2 == 0 else 1,
            "poutcome": "nonexistent" if i % 2 == 0 else "success",
            "y": i % 2,
        })
    preprocessor = fit_train_preprocessor(train_rows)
    predictor = fit_initial_logistic_regression(preprocessor.transform(train_rows), [int(r["y"]) for r in train_rows], 42)
    pipeline = frozen_pipeline(preprocessor, predictor)
    return pipeline, tuple(train_rows)


def test_platt_logodds_fits_and_predicts():
    pipeline, rows = _setup_pipeline_and_rows()
    labels = tuple(int(r["y"]) for r in rows[:40])
    fit = fit_platt_logodds(pipeline, rows[:40], labels)

    assert fit.record.fit_status == "fitted"
    assert fit.record.requested_method == "target_platt_logodds"
    assert fit.record.resolved_method == "target_platt_logodds"
    assert fit.record.labels_consumed == 40

    from shiftguard.preprocessing.tabular import rows_to_features
    feat_array = rows_to_features(list(rows[:10]))
    probs = fit.probability_map.predict_proba(feat_array)

    assert probs.shape == (10, 2)
    assert np.all(probs >= 0.0) and np.all(probs <= 1.0)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0)


def test_platt_logodds_one_class_fallback():
    pipeline, rows = _setup_pipeline_and_rows()
    # All 0s
    labels = tuple([0] * 30)
    fit = fit_platt_logodds(pipeline, rows[:30], labels)

    assert fit.record.fit_status == "not_fitted"
    assert fit.record.fallback_reason == "one_class_or_empty"
    assert fit.record.resolved_method == "raw"
