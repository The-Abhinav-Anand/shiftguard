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
