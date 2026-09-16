from __future__ import annotations

import numpy as np
import pytest

from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.missingness.block import history_block_mask
from shiftguard.missingness.mcar import (
    CellwiseFeatureMask,
    compute_matched_mcar,
    generate_mcar_mask,
    generate_shared_uniforms,
)


def _sample_rows(n: int = 100) -> tuple[dict[str, str | int], ...]:
    rows = []
    for i in range(n):
        rows.append({
            "row_id": i + 1,
            "age": 30 + (i % 30),
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
    return tuple(rows)


def test_mcar_zero_rate_identity():
    rows = _sample_rows(50)
    record_ids = tuple(int(r["row_id"]) for r in rows)
    mask = generate_mcar_mask(record_ids=record_ids, features=BANK_FEATURES, rate=0.0, seed=12345)
    masked_rows = mask.apply(rows)
    for orig, masked in zip(rows, masked_rows, strict=True):
        assert orig == masked
    rates = mask.rates(rows)
    assert rates["newly_missing_cells"] == 0
    assert rates["observed_all_feature_cells_new_missing_rate"] == 0.0


def test_mcar_shared_uniforms_monotone_nesting():
    rows = _sample_rows(100)
    record_ids = tuple(int(r["row_id"]) for r in rows)
    uniforms = generate_shared_uniforms(len(record_ids), len(BANK_FEATURES), seed=42)

    mask_00 = generate_mcar_mask(record_ids, BANK_FEATURES, rate=0.00, shared_uniforms=uniforms)
    mask_10 = generate_mcar_mask(record_ids, BANK_FEATURES, rate=0.10, shared_uniforms=uniforms)
    mask_30 = generate_mcar_mask(record_ids, BANK_FEATURES, rate=0.30, shared_uniforms=uniforms)

    m00 = np.array(mask_00.mask_matrix)
    m10 = np.array(mask_10.mask_matrix)
    m30 = np.array(mask_30.mask_matrix)

    assert not m00.any()
    # Any cell masked at 0.10 MUST be masked at 0.30 (monotone nesting)
    assert np.all((m10 & ~m30) == False)
    assert m10.sum() < m30.sum()


def test_mcar_rates_denominators():
    rows = _sample_rows(50)
    record_ids = tuple(int(r["row_id"]) for r in rows)
    mask = generate_mcar_mask(record_ids, BANK_FEATURES, rate=0.20, seed=999)
    rates = mask.rates(rows)

    assert rates["row_count"] == 50
    assert rates["all_feature_cells"] == 50 * 10
    assert rates["observed_all_feature_cells"] == 50 * 10
    assert rates["newly_missing_cells"] > 0
    assert rates["observed_all_feature_cells_new_missing_rate"] == rates["newly_missing_cells"] / rates["observed_all_feature_cells"]
    assert rates["total_missing_cells"] == rates["newly_missing_cells"]


def test_matched_mcar_to_block_reporting():
    rows = _sample_rows(200)
    record_ids = tuple(int(r["row_id"]) for r in rows)
    # Block outage on history features with 50% row outage
    block_mask = history_block_mask(record_ids, seed=777, row_probability=0.50)
    block_rates = block_mask.rates(rows)

    mcar_mask, report = compute_matched_mcar(
        record_ids=record_ids,
        rows=rows,
        block_rates=block_rates,
        seed=888,
        features=BANK_FEATURES,
    )

    assert report["matching_strategy"] == "exact_realized_rate"
    assert report["block_realized_rate"] == block_rates["observed_all_feature_cells_new_missing_rate"]
    assert report["mcar_requested_rate"] == report["block_realized_rate"]
    assert "residual_mismatch" in report
    assert report["residual_mismatch"] >= 0.0
    assert report["residual_mismatch"] < 0.05  # Within reasonable sampling tolerance
    assert report["block_numerator"] == block_rates["newly_missing_cells"]
    assert report["block_denominator"] == block_rates["observed_all_feature_cells"]
