from __future__ import annotations

import numpy as np
from sklearn.pipeline import Pipeline

from shiftguard.calibration.base import CalibrationRecord
from shiftguard.calibration.sklearn_maps import CalibrationFit, fit_temperature
from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.missingness.block import HISTORY_FEATURES, history_block_mask
from shiftguard.missingness.mcar import generate_mcar_mask, generate_shared_uniforms


def generate_source_remasked_dataset(
    source_rows: tuple[dict[str, str | int], ...],
    source_labels: tuple[int, ...],
    seed: int,
    features: tuple[str, ...] = BANK_FEATURES,
) -> tuple[tuple[dict[str, str | int | None], ...], tuple[int, ...], np.ndarray]:
    """Generate source-calibration rows under simulated missingness conditions.

    Replicates source rows across 4 simulated regimes:
    1. clean (0% missing)
    2. 10% MCAR
    3. 30% MCAR
    4. 50% history block outage

    Returns remasked rows, replicated labels, and newly injected missing fraction per row.
    """
    rng = np.random.default_rng(seed)
    sub_seeds = rng.integers(0, 1_000_000, size=2)
    record_ids = tuple(int(r["row_id"]) for r in source_rows)

    mcar_uniforms = generate_shared_uniforms(len(record_ids), len(features), seed=int(sub_seeds[0]))
    mask_mcar_10 = generate_mcar_mask(record_ids, features, rate=0.10, shared_uniforms=mcar_uniforms)
    mask_mcar_30 = generate_mcar_mask(record_ids, features, rate=0.30, shared_uniforms=mcar_uniforms)
    mask_block = history_block_mask(record_ids, seed=int(sub_seeds[1]), row_probability=0.50)

    remasked_rows: list[dict[str, str | int | None]] = []
    remasked_labels: list[int] = []
    missing_fractions: list[float] = []

    eligible_count = len(features)

    # Helper to compute newly missing fraction for a row relative to original source row
    def calc_fractions(orig_rows, masked_rows):
        fracs = []
        for orig, masked in zip(orig_rows, masked_rows, strict=True):
            newly_missing = sum(
                orig.get(feat) not in (None, "") and masked.get(feat) in (None, "")
                for feat in features
            )
            fracs.append(newly_missing / eligible_count if eligible_count > 0 else 0.0)
        return fracs

    # 1. Clean
    remasked_rows.extend(dict(r) for r in source_rows)
    remasked_labels.extend(source_labels)
    missing_fractions.extend([0.0] * len(source_rows))

    # 2. MCAR 10%
    rows_mcar_10 = mask_mcar_10.apply(source_rows)
    remasked_rows.extend(rows_mcar_10)
    remasked_labels.extend(source_labels)
    missing_fractions.extend(calc_fractions(source_rows, rows_mcar_10))

    # 3. MCAR 30%
    rows_mcar_30 = mask_mcar_30.apply(source_rows)
    remasked_rows.extend(rows_mcar_30)
    remasked_labels.extend(source_labels)
    missing_fractions.extend(calc_fractions(source_rows, rows_mcar_30))

    # 4. Block 50%
    rows_block = mask_block.apply(source_rows)
    remasked_rows.extend(rows_block)
    remasked_labels.extend(source_labels)
    missing_fractions.extend(calc_fractions(source_rows, rows_block))

    return tuple(remasked_rows), tuple(remasked_labels), np.array(missing_fractions, dtype=float)


def fit_source_remasked_temperature(
    pipeline: Pipeline,
    remasked_rows: tuple[dict[str, str | int | None], ...],
    remasked_labels: tuple[int, ...],
) -> CalibrationFit:
    """Fit global temperature scaling on source-remasked calibration samples."""
    return fit_temperature(
        pipeline=pipeline,
        rows=remasked_rows,
        labels=remasked_labels,
        requested_method="source_remasked_temperature",
    )
