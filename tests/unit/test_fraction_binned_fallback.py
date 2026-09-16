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


def test_fraction_binned_natural_missingness_routing():
    pipeline, source_rows = _setup()
    source_labels = tuple(int(r["y"]) for r in source_rows)

    remasked_rows, remasked_labels, fractions = generate_source_remasked_dataset(
        source_rows, source_labels, seed=31201, features=BANK_FEATURES,
    )
    global_fit = fit_source_remasked_temperature(pipeline, remasked_rows, remasked_labels)
    binned_fit = fit_source_fraction_binned_temperature(
        pipeline=pipeline,
        remasked_rows=remasked_rows,
        remasked_labels=remasked_labels,
        missing_fractions=fractions,
        global_fit=global_fit,
        n_bins=10,
        min_bin_samples=10,
    )
    b_map: FractionBinnedTemperatureMap = binned_fit.probability_map
    feat_array = rows_to_features(list(source_rows[:10]))

    # Without injected fractions (or zeros), must route to bin 0 (not a non-zero bin from natural missingness)
    _ = b_map.predict_proba(feat_array)
    assert b_map.last_diagnostics["bin_eval_counts"][0] == 10
    assert sum(b_map.last_diagnostics["bin_eval_counts"][b] for b in range(1, 10)) == 0

    # With injected fraction 0.25, must route to bin 2
    injected_25 = [0.25] * 10
    _ = b_map.predict_proba(feat_array, injected_fractions=injected_25)
    assert b_map.last_diagnostics["bin_eval_counts"][2] == 10
    assert b_map.last_diagnostics["bin_eval_counts"][0] == 0


def test_fraction_binned_cascade_with_nonidentity_source_map():
    pipeline, source_rows = _setup()
    source_labels = tuple(int(r["y"]) for r in source_rows)

    remasked_rows, remasked_labels, fractions = generate_source_remasked_dataset(
        source_rows, source_labels, seed=31201, features=BANK_FEATURES,
    )

    # Fit a real, nonidentity source temperature calibrator
    source_temp_fit = fit_temperature(pipeline, source_rows, source_labels, "source_temperature")
    assert source_temp_fit.record.fit_status == "fitted"
    assert source_temp_fit.record.fitted_temperature is not None

    feat_array = rows_to_features(list(source_rows[:20]))
    raw_p = pipeline.predict_proba(feat_array)[:, 1]
    source_p = source_temp_fit.probability_map.predict_proba(feat_array)[:, 1]

    # When remasked calibration fails (global_fit is None or not_fitted)
    binned_fit = fit_source_fraction_binned_temperature(
        pipeline=pipeline,
        remasked_rows=remasked_rows,
        remasked_labels=remasked_labels,
        missing_fractions=fractions,
        global_fit=None,
        source_fit=source_temp_fit,
        n_bins=10,
        min_bin_samples=1000,  # force all bins to be sparse
    )
    assert binned_fit.record.fit_status == "fitted"
    b_map: FractionBinnedTemperatureMap = binned_fit.probability_map

    # Predict with injected fractions - sparse rows must cascade to source_temperature, NOT raw
    injected = [0.50] * 20
    cal_p = b_map.predict_proba(feat_array, injected_fractions=injected)[:, 1]

    # Verify sparse bin resolved to source_temperature
    diag = b_map.last_diagnostics
    assert diag["bin_resolved_maps"][5] == "source_temperature"
    np.testing.assert_allclose(cal_p, source_p, atol=1e-6)
    # Confirm it did NOT fall back to raw
    assert not np.allclose(cal_p, raw_p, atol=1e-5)
