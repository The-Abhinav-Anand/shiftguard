from __future__ import annotations

import numpy as np
import pytest

from shiftguard.calibration.base import validate_raw_probabilities


def test_validate_raw_probabilities_valid_2d():
    probs = np.array([[0.8, 0.2], [0.3, 0.7]])
    p1 = validate_raw_probabilities(probs, expected_rows=2)
    np.testing.assert_allclose(p1, [0.2, 0.7])


def test_validate_raw_probabilities_valid_1d():
    probs = np.array([0.2, 0.7])
    p1 = validate_raw_probabilities(probs, expected_rows=2)
    np.testing.assert_allclose(p1, [0.2, 0.7])


def test_validate_raw_probabilities_expected_rows_mismatch():
    probs = np.array([[0.8, 0.2]])
    with pytest.raises(ValueError, match="expected 2 rows, got 1"):
        validate_raw_probabilities(probs, expected_rows=2)


def test_validate_raw_probabilities_nan():
    probs = np.array([[0.5, np.nan], [0.3, 0.7]])
    with pytest.raises(ValueError, match="NaN or infinite"):
        validate_raw_probabilities(probs)


def test_validate_raw_probabilities_inf():
    probs = np.array([[0.5, np.inf], [0.3, 0.7]])
    with pytest.raises(ValueError, match="NaN or infinite"):
        validate_raw_probabilities(probs)


def test_validate_raw_probabilities_negative():
    probs = np.array([[-0.1, 1.1], [0.3, 0.7]])
    with pytest.raises(ValueError, match="outside \\[0\\.0, 1\\.0\\]"):
        validate_raw_probabilities(probs)


def test_validate_raw_probabilities_greater_than_one():
    probs = np.array([[0.2, 1.2], [0.3, 0.7]])
    with pytest.raises(ValueError, match="outside \\[0\\.0, 1\\.0\\]"):
        validate_raw_probabilities(probs)


def test_validate_raw_probabilities_row_sum_not_one():
    probs = np.array([[0.4, 0.4], [0.3, 0.7]])
    with pytest.raises(ValueError, match="do not sum to 1\\.0"):
        validate_raw_probabilities(probs)


def test_baseline_config_immutability():
    from shiftguard.experiments.config import BaselineConfig

    config = BaselineConfig(master_seed=31001)
    with pytest.raises(TypeError):
        config.role_fractions["train"] = 0.1  # MappingProxyType prevents in-place mutation

    # to_dict returns a decoupled copy
    d = config.to_dict()
    d["role_fractions"]["train"] = 0.1
    assert config.role_fractions["train"] == 0.55


def test_stress_config_dimension_validations():
    from shiftguard.experiments.config import StressConfig

    # Duplicate predictors
    with pytest.raises(ValueError, match="predictors must not contain duplicates"):
        StressConfig(master_seed=31001, predictors=("logistic_regression", "logistic_regression"))

    # Invalid history probability
    with pytest.raises(ValueError, match="history_row_probability is frozen at 0.50"):
        StressConfig(master_seed=31001, history_row_probability=2.0)

    with pytest.raises(ValueError, match="history_row_probability is frozen at 0.50"):
        StressConfig(master_seed=31001, history_row_probability=0.20)

    # Boolean budget rejected
    with pytest.raises(ValueError, match="budgets must be strict integers"):
        StressConfig(master_seed=31001, budgets=(True, 50))

    # Duplicate budgets
    with pytest.raises(ValueError, match="budgets must not contain duplicates"):
        StressConfig(master_seed=31001, budgets=(0, 50, 50))

    # Duplicate MCAR rates
    with pytest.raises(ValueError, match="mcar_rates must not contain duplicates"):
        StressConfig(master_seed=31001, mcar_rates=(0.0, 0.1, 0.1))

    # Duplicate calibration methods
    with pytest.raises(ValueError, match="calibration_methods must not contain duplicates"):
        StressConfig(master_seed=31001, calibration_methods=("raw", "raw"))

    # Duplicate cost grid
    with pytest.raises(ValueError, match="cost_grid must not contain duplicates"):
        StressConfig(master_seed=31001, cost_grid=((1.0, 1.0), (1.0, 1.0)))
