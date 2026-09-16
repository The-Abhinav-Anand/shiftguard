from __future__ import annotations

import numpy as np
import pytest

from shiftguard.calibration.fraction_binned import (
    FractionBinnedTemperatureMap,
    bin_index,
    fit_source_fraction_binned_temperature,
)
from shiftguard.calibration.sklearn_maps import fit_temperature, frozen_pipeline
from shiftguard.calibration.source_remask import (
    fit_source_remasked_temperature,
    generate_source_remasked_dataset,
)
from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.predictors.logistic import fit_initial_logistic_regression
from shiftguard.preprocessing.tabular import fit_train_preprocessor, rows_to_features


def _setup():
    train_rows = []
    for i in range(150):
        train_rows.append({
            "row_id": i + 1,
            "age": 25 + (i % 35),
            "job": "management" if i % 2 == 0 else "technician",
            "marital": "married",
            "education": "university.degree",
            "default": "no",
            "housing": "yes",
            "loan": "no",
            "pdays": 999 if i % 3 != 0 else 6,
            "previous": 0 if i % 3 != 0 else 1,
            "poutcome": "nonexistent" if i % 3 != 0 else "success",
            "y": 1 if (i % 3 == 0) else 0,
        })
    preprocessor = fit_train_preprocessor(train_rows)
    predictor = fit_initial_logistic_regression(preprocessor.transform(train_rows), [int(r["y"]) for r in train_rows], 202)
    pipeline = frozen_pipeline(preprocessor, predictor)
    return pipeline, tuple(train_rows)


def test_bin_index_boundaries():
    assert bin_index(0.0) == 0
    assert bin_index(0.05) == 0
    assert bin_index(0.10) == 1
    assert bin_index(0.29) == 2
    assert bin_index(0.30) == 3
    assert bin_index(0.95) == 9
    assert bin_index(1.0) == 9


def test_fraction_binned_sparse_fallback():
    pipeline, source_rows = _setup()
    source_labels = tuple(int(r["y"]) for r in source_rows)

    remasked_rows, remasked_labels, fractions = generate_source_remasked_dataset(
        source_rows, source_labels, seed=31201, features=BANK_FEATURES,
    )
    global_fit = fit_source_remasked_temperature(pipeline, remasked_rows, remasked_labels)
    assert global_fit.record.fit_status == "fitted"

    # Fit fraction binned
    binned_fit = fit_source_fraction_binned_temperature(
        pipeline=pipeline,
        remasked_rows=remasked_rows,
        remasked_labels=remasked_labels,
        missing_fractions=fractions,
        global_fit=global_fit,
        n_bins=10,
        min_bin_samples=10,
    )

    assert binned_fit.record.fit_status == "fitted"
    assert binned_fit.record.requested_method == "source_fraction_binned_temperature"

    # Check that sparse bins (e.g. bins with no data or < 10 samples) fell back to sparse_fraction_bin
    b_map: FractionBinnedTemperatureMap = binned_fit.probability_map
    has_sparse = any(fb == "sparse_fraction_bin" for fb in b_map.bin_fallbacks.values())
    assert has_sparse, "Expected at least one sparse bin in [0, 1] range"

    # Predict on sample features
    feat_array = rows_to_features(list(source_rows[:20]))
    probs = b_map.predict_proba(feat_array)
    assert probs.shape == (20, 2)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0)
