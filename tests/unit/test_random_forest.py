from __future__ import annotations

import numpy as np
import pytest

from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.predictors.random_forest import (
    fit_initial_random_forest,
    fitted_rf_state,
    random_forest_identity,
)
from shiftguard.preprocessing.tabular import (
    fit_tree_preprocessor,
    preprocessing_config,
    rows_to_features,
)


def _synthetic_train_rows(n: int = 150) -> list[dict[str, str | int]]:
    rows = []
    for i in range(n):
        rows.append({
            "row_id": i + 1,
            "age": 25 + (i % 40),
            "job": "services" if i % 3 == 0 else "technician",
            "marital": "single" if i % 2 == 0 else "married",
            "education": "high.school" if i % 2 == 0 else "university.degree",
            "default": "no",
            "housing": "yes" if i % 4 == 0 else "no",
            "loan": "no",
            "pdays": 999 if i % 2 == 0 else 10,
            "previous": 0 if i % 2 == 0 else 2,
            "poutcome": "nonexistent" if i % 2 == 0 else "success",
            "y": 1 if (i % 5 == 0) else 0,
        })
    return rows


def test_random_forest_fit_and_determinism():
    train_rows = _synthetic_train_rows(120)
    preprocessor = fit_tree_preprocessor(train_rows)
    X = preprocessor.transform(train_rows)
    y = [int(r["y"]) for r in train_rows]

    # Two fits with identical seed must produce identical predictions
    model1 = fit_initial_random_forest(X, y, seed=31101)
    model2 = fit_initial_random_forest(X, y, seed=31101)

    preds1 = model1.predict_proba(X)[:, 1]
    preds2 = model2.predict_proba(X)[:, 1]
    np.testing.assert_array_equal(preds1, preds2)

    # Check n_jobs=1
    assert model1.n_jobs == 1
    assert model1.n_estimators == 100

    identity = random_forest_identity(model1)
    assert identity["model_type"] == "sklearn.ensemble.RandomForestClassifier"
    assert identity["resolved_hyperparameters"]["n_jobs"] == 1
    assert identity["resolved_hyperparameters"]["random_state"] == 31101

    state = fitted_rf_state(preprocessor, model1)
    assert state["n_estimators"] == 100
    assert state["classes"] == [0, 1]


def test_tree_preprocessing_config():
    cfg = preprocessing_config("tree")
    assert cfg["model_family"] == "tree"
    assert cfg["numeric"]["scaler"] is None
    assert cfg["numeric"]["imputer"] == "median"
