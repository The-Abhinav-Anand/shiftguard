from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from shiftguard.datasets.bank import BANK_FEATURES


def stable_cell_mask_hash(
    record_ids: tuple[int, ...],
    features: tuple[str, ...],
    mask_matrix: tuple[tuple[bool, ...], ...],
    requested_rate: float,
) -> str:
    payload = json.dumps(
        {
            "record_ids": record_ids,
            "features": features,
            "mask_matrix": mask_matrix,
            "requested_rate": requested_rate,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CellwiseFeatureMask:
    record_ids: tuple[int, ...]
    features: tuple[str, ...]
    mask_matrix: tuple[tuple[bool, ...], ...]
    requested_rate: float

    @property
    def mask_id(self) -> str:
        return stable_cell_mask_hash(self.record_ids, self.features, self.mask_matrix, self.requested_rate)

    def apply(self, rows: tuple[dict[str, str | int], ...]) -> tuple[dict[str, str | int | None], ...]:
        by_id = {rid: i for i, rid in enumerate(self.record_ids)}
        feat_idx = {feat: j for j, feat in enumerate(self.features)}
        transformed = []
        for row in rows:
            copy = dict(row)
            rid = int(row["row_id"])
            if rid in by_id:
                row_idx = by_id[rid]
                for feature in self.features:
                    col_idx = feat_idx[feature]
                    if self.mask_matrix[row_idx][col_idx]:
                        copy[feature] = None
            transformed.append(copy)
        return tuple(transformed)

    def rates(self, rows: tuple[dict[str, str | int], ...]) -> dict[str, float | int]:
        by_id = {rid: i for i, rid in enumerate(self.record_ids)}
        feat_idx = {feat: j for j, feat in enumerate(self.features)}
        observed_all = observed_eligible = newly_missing = rows_newly_missing = 0
        natural_missing = 0
        all_cells = len(rows) * len(BANK_FEATURES)

        for row in rows:
            rid = int(row["row_id"])
            row_idx = by_id.get(rid)
            newly_missing_for_row = False
            for feature in BANK_FEATURES:
                raw_val = row.get(feature)
                is_observed = raw_val not in (None, "")
                if is_observed:
                    observed_all += 1
                else:
                    natural_missing += 1

                if feature in feat_idx and is_observed:
                    observed_eligible += 1
                    if row_idx is not None and self.mask_matrix[row_idx][feat_idx[feature]]:
                        newly_missing += 1
                        newly_missing_for_row = True
            rows_newly_missing += int(newly_missing_for_row)

        return {
            "requested_rate": self.requested_rate,
            "row_count": len(rows),
            "all_feature_cells": all_cells,
            "observed_all_feature_cells": observed_all,
            "observed_eligible_cells": observed_eligible,
            "newly_missing_cells": newly_missing,
            "rows_with_new_missingness": rows_newly_missing,
            "rows_with_new_missingness_fraction": rows_newly_missing / len(rows) if rows else 0.0,
            "observed_eligible_cells_new_missing_rate": newly_missing / observed_eligible if observed_eligible else 0.0,
            "observed_all_feature_cells_new_missing_rate": newly_missing / observed_all if observed_all else 0.0,
            "natural_missing_cells": natural_missing,
            "total_missing_cells": natural_missing + newly_missing,
            "total_missing_rate_over_all_feature_cells": (natural_missing + newly_missing) / all_cells if all_cells else 0.0,
        }


def generate_shared_uniforms(n_rows: int, n_features: int, seed: int) -> np.ndarray:
    """Generate uniform random matrix U ~ Uniform(0, 1) of shape (n_rows, n_features)."""
    return np.random.default_rng(seed).random((n_rows, n_features))


def generate_mcar_mask(
    record_ids: tuple[int, ...],
    features: tuple[str, ...] = BANK_FEATURES,
    rate: float = 0.0,
    seed: int | None = None,
    shared_uniforms: np.ndarray | None = None,
) -> CellwiseFeatureMask:
    """Generate cellwise MCAR mask.

    If shared_uniforms is provided, masks cell (i, j) if uniforms[i, j] < rate,
    guaranteeing strict monotone nesting across severities (0.00 <= 0.10 <= 0.30).
    """
    if not (0.0 <= rate <= 1.0):
        raise ValueError(f"MCAR rate must be in [0, 1], got {rate}")

    n_rows = len(record_ids)
    n_features = len(features)

    if shared_uniforms is not None:
        if shared_uniforms.shape != (n_rows, n_features):
            raise ValueError(f"shared_uniforms shape {shared_uniforms.shape} does not match ({n_rows}, {n_features})")
        uniforms = shared_uniforms
    else:
        if seed is None:
            raise ValueError("Must provide either seed or shared_uniforms")
        uniforms = generate_shared_uniforms(n_rows, n_features, seed)

    bool_array = uniforms < rate
    mask_matrix = tuple(tuple(bool(x) for x in row) for row in bool_array)
    return CellwiseFeatureMask(record_ids, features, mask_matrix, rate)


def compute_matched_mcar(
    record_ids: tuple[int, ...],
    rows: tuple[dict[str, str | int], ...],
    block_rates: dict[str, float | int],
    seed: int,
    features: tuple[str, ...] = BANK_FEATURES,
    shared_uniforms: np.ndarray | None = None,
) -> tuple[CellwiseFeatureMask, dict[str, object]]:
    """Construct cellwise MCAR mask matched to the realized eligible cell missingness of a block outage.

    Reports requested rate, realized numerator/denominator, matching strategy, and residual mismatch.
    """
    # The block outage realized overall observed-cell missing rate
    target_rate = float(block_rates["observed_all_feature_cells_new_missing_rate"])
    mcar_mask = generate_mcar_mask(
        record_ids=record_ids,
        features=features,
        rate=target_rate,
        seed=seed,
        shared_uniforms=shared_uniforms,
    )
    mcar_rates = mcar_mask.rates(rows)
    realized_mcar_rate = float(mcar_rates["observed_all_feature_cells_new_missing_rate"])
    residual = abs(realized_mcar_rate - target_rate)

    report = {
        "matching_strategy": "exact_realized_rate",
        "target_rate": target_rate,
        "block_realized_rate": target_rate,
        "mcar_requested_rate": target_rate,
        "mcar_realized_rate": realized_mcar_rate,
        "residual_mismatch": residual,
        "matched_within_tolerance": bool(residual < 0.02),
        "block_numerator": block_rates["newly_missing_cells"],
        "block_denominator": block_rates["observed_all_feature_cells"],
        "mcar_numerator": mcar_rates["newly_missing_cells"],
        "mcar_denominator": mcar_rates["observed_all_feature_cells"],
    }
    return mcar_mask, report
