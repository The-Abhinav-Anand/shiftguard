"""Adult raw-feature missingness: employment outage block, nested MCAR, two denominators.

Masks act on RAW tokens before any imputation. This is an engineering adapter for
fabricated rows; it injects, counts and persists, and claims nothing about results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from shiftguard.adult_adapter.features import (
    ADULT_FEATURE_CONTRACT,
    FEATURE_COUNT,
    AdultAdapterError,
    AdultRecord,
    canonical_digest,
    immutable_tuple,
    parse_row_id,
    strict_int,
)


EMPLOYMENT_BLOCK = ("workclass", "occupation", "hours-per-week")
EMPLOYMENT_ROW_PROBABILITY = 0.50
AGGREGATE_DENOMINATOR_NAME = "originally_observed_eligible_cells_across_13_predictors"
_BLOCK_COLUMNS = tuple(ADULT_FEATURE_CONTRACT.features.index(name) for name in EMPLOYMENT_BLOCK)
_MASK_VERSION = "gate9-adult-mask-v1"


def seed_field(value: Any, name: str) -> int:
    # numpy rejects negative seeds late and bool/float would alias integers, so refuse both here.
    seed = strict_int(value, name, code="SEED_TYPE")
    if seed < 0:
        raise AdultAdapterError("SEED_RANGE", name)
    return seed


def probability_field(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdultAdapterError("RATE", name)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise AdultAdapterError("RATE", name)
    return float(value)


def _record_ids(value: Any) -> tuple[str, ...]:
    ids = immutable_tuple(value, "record_ids")
    for row_id in ids:
        parse_row_id(row_id)
    if len(set(ids)) != len(ids):
        raise AdultAdapterError("DUPLICATE_ROW_ID", "record_ids")
    return ids


class CellMask(Protocol):
    record_ids: tuple[str, ...]

    @property
    def cells(self) -> tuple[tuple[bool, ...], ...]: ...


@dataclass(frozen=True)
class EmploymentOutageMask:
    """Row-level selection; a selected row loses all of ``EMPLOYMENT_BLOCK`` together."""

    record_ids: tuple[str, ...]
    selected: tuple[bool, ...]
    requested_row_probability: float
    features: tuple[str, ...] = EMPLOYMENT_BLOCK
    seed: int | None = None  # provenance only; excluded from mask_id so identity is content-based

    def __post_init__(self) -> None:
        _record_ids(self.record_ids)
        immutable_tuple(self.selected, "selected")
        if len(self.selected) != len(self.record_ids) or any(type(x) is not bool for x in self.selected):
            raise AdultAdapterError("MASK_SHAPE", "selected")
        if self.features != EMPLOYMENT_BLOCK:
            raise AdultAdapterError("MASK_SHAPE", "features")
        probability_field(self.requested_row_probability, "requested_row_probability")

    @property
    def cells(self) -> tuple[tuple[bool, ...], ...]:
        on = tuple(j in _BLOCK_COLUMNS for j in range(FEATURE_COUNT))
        off = (False,) * FEATURE_COUNT
        return tuple(on if chosen else off for chosen in self.selected)

    @property
    def mask_id(self) -> str:
        return canonical_digest([
            _MASK_VERSION, "employment_outage", list(self.record_ids), list(self.features),
            list(self.selected), self.requested_row_probability,
        ])


def employment_outage_mask(
    record_ids: tuple[str, ...], seed: Any, row_probability: Any = EMPLOYMENT_ROW_PROBABILITY
) -> EmploymentOutageMask:
    """One uniform per row in row order; the stream depends only on ``seed`` and the row count."""
    ids = _record_ids(record_ids)
    stream_seed = seed_field(seed, "seed")
    probability = probability_field(row_probability, "row_probability")
    draws = np.random.default_rng(stream_seed).random(len(ids))
    return EmploymentOutageMask(
        ids, tuple(bool(u < probability) for u in draws), probability, EMPLOYMENT_BLOCK, stream_seed
    )


@dataclass(frozen=True)
class OutageMaskPair:
    pool: EmploymentOutageMask
    test: EmploymentOutageMask


def employment_outage_mask_pair(
    pool_record_ids: tuple[str, ...],
    test_record_ids: tuple[str, ...],
    *,
    pool_seed: Any,
    test_seed: Any,
    row_probability: Any = EMPLOYMENT_ROW_PROBABILITY,
) -> OutageMaskPair:
    """Independent pool and test streams from caller-supplied seeds; equal seeds would be one stream."""
    pool = seed_field(pool_seed, "pool_seed")
    test = seed_field(test_seed, "test_seed")
    if pool == test:
        raise AdultAdapterError("SEEDS_NOT_DISTINCT", "pool_seed,test_seed")
    return OutageMaskPair(
        employment_outage_mask(pool_record_ids, pool, row_probability),
        employment_outage_mask(test_record_ids, test, row_probability),
    )


def shared_mcar_uniforms(n_rows: Any, seed: Any) -> np.ndarray:
    """Cell uniforms shared by every MCAR rate so a lower rate is nested in a higher one."""
    rows = strict_int(n_rows, "n_rows")
    if rows < 0:
        raise AdultAdapterError("STRICT_INTEGER", "n_rows")
    return np.random.default_rng(seed_field(seed, "seed")).random((rows, FEATURE_COUNT))


@dataclass(frozen=True)
class McarMask:
    record_ids: tuple[str, ...]
    cells: tuple[tuple[bool, ...], ...]
    requested_rate: float

    def __post_init__(self) -> None:
        _record_ids(self.record_ids)
        immutable_tuple(self.cells, "cells")
        if len(self.cells) != len(self.record_ids) or any(
            type(row) is not tuple or len(row) != FEATURE_COUNT or any(type(x) is not bool for x in row)
            for row in self.cells
        ):
            raise AdultAdapterError("MASK_SHAPE", "cells")
        probability_field(self.requested_rate, "requested_rate")

    @property
    def mask_id(self) -> str:
        return canonical_digest([
            _MASK_VERSION, "mcar", list(self.record_ids), [list(r) for r in self.cells], self.requested_rate,
        ])


_UNIFORM_DTYPES = (np.float32, np.float64)


def _validated_uniforms(uniforms: Any, shape: tuple[int, int]) -> np.ndarray:
    """Accept only an ndarray of finite floats in [0, 1) of the declared shape; never cast.

    A NaN, an infinity or an out-of-range value would otherwise compare as "not masked"
    (or "masked") and hide invalid upstream random data behind a valid mask identity.
    """
    if type(uniforms) is not np.ndarray:
        raise AdultAdapterError("UNIFORMS_TYPE", "uniforms")
    if uniforms.shape != shape:
        raise AdultAdapterError("UNIFORMS_SHAPE", "uniforms")
    if uniforms.dtype.type not in _UNIFORM_DTYPES:
        raise AdultAdapterError("UNIFORMS_DTYPE", str(uniforms.dtype))
    if not np.isfinite(uniforms).all():
        raise AdultAdapterError("UNIFORMS_RANGE", "non-finite uniform")
    if (uniforms < 0.0).any() or (uniforms >= 1.0).any():
        raise AdultAdapterError("UNIFORMS_RANGE", "uniform outside [0, 1)")
    return uniforms.astype(np.float64, copy=False)


def build_mcar_mask(record_ids: tuple[str, ...], uniforms: np.ndarray, rate: Any) -> McarMask:
    ids = _record_ids(record_ids)
    requested = probability_field(rate, "rate")
    values = _validated_uniforms(uniforms, (len(ids), FEATURE_COUNT))
    # Strict less-than on shared uniforms: cell masked at 0.10 is masked at every higher rate.
    # float32 widens to float64 losslessly, so the comparison is exact for either dtype.
    flags = values < requested
    return McarMask(ids, tuple(tuple(bool(x) for x in row) for row in flags), requested)


@dataclass(frozen=True)
class NewMissingnessCounts:
    """Every number behind both rates; the two denominators are separate fields on purpose."""

    row_count: int
    eligible_cells_total: int  # row_count * 13
    originally_observed_cells: int
    naturally_missing_cells: int
    newly_masked_cells: int
    rows_with_new_missingness: int
    injected_feature_counts: tuple[int, ...]  # per row, newly injected cells only
    fraction_bin_denominator: int = FEATURE_COUNT

    @property
    def aggregate_denominator(self) -> int:
        return self.originally_observed_cells

    @property
    def aggregate_new_missing_rate(self) -> float | None:
        """New / originally observed cells; ``None`` (not 0.0) when nothing was observable."""
        if self.originally_observed_cells == 0:
            return None
        return self.newly_masked_cells / self.originally_observed_cells

    @property
    def fraction_bin_values(self) -> tuple[float, ...]:
        """Per-row routing value: newly injected feature count / 13."""
        return tuple(count / self.fraction_bin_denominator for count in self.injected_feature_counts)

    def as_record(self) -> dict[str, object]:
        return {
            "row_count": self.row_count,
            "eligible_cells_total": self.eligible_cells_total,
            "originally_observed_cells": self.originally_observed_cells,
            "naturally_missing_cells": self.naturally_missing_cells,
            "newly_masked_cells": self.newly_masked_cells,
            "rows_with_new_missingness": self.rows_with_new_missingness,
            "injected_feature_counts": list(self.injected_feature_counts),
            "aggregate_denominator_name": AGGREGATE_DENOMINATOR_NAME,
            "aggregate_denominator": self.aggregate_denominator,
            "aggregate_new_missing_rate": self.aggregate_new_missing_rate,
            "fraction_bin_denominator": self.fraction_bin_denominator,
            "fraction_bin_values": list(self.fraction_bin_values),
        }


def measure_new_missingness(
    original: tuple[AdultRecord, ...], masked: tuple[AdultRecord, ...]
) -> NewMissingnessCounts:
    """Count from the before/after tokens so naturally missing cells never enter either term."""
    immutable_tuple(original, "original")
    immutable_tuple(masked, "masked")
    if tuple(r.row_id for r in original) != tuple(r.row_id for r in masked):
        raise AdultAdapterError("MASK_RECORD_MISMATCH", "records")
    observed = natural = new_total = rows_new = 0
    per_row: list[int] = []
    for before, after in zip(original, masked, strict=True):
        injected = 0
        for old, new in zip(before.tokens, after.tokens, strict=True):
            if old is None:
                if new is not None:
                    raise AdultAdapterError("MASK_ALTERED_CELL", before.row_id)
                natural += 1
                continue
            observed += 1
            if new is None:
                injected += 1
            elif new != old:
                raise AdultAdapterError("MASK_ALTERED_CELL", before.row_id)
        per_row.append(injected)
        new_total += injected
        rows_new += injected > 0
    return NewMissingnessCounts(
        row_count=len(original),
        eligible_cells_total=len(original) * FEATURE_COUNT,
        originally_observed_cells=observed,
        naturally_missing_cells=natural,
        newly_masked_cells=new_total,
        rows_with_new_missingness=rows_new,
        injected_feature_counts=tuple(per_row),
    )


@dataclass(frozen=True)
class MaskedRows:
    records: tuple[AdultRecord, ...]
    counts: NewMissingnessCounts
    mask_id: str


def apply_mask(records: tuple[AdultRecord, ...], mask: CellMask) -> MaskedRows:
    """Null the masked cells of raw records and measure what was newly lost."""
    immutable_tuple(records, "records")
    if tuple(r.row_id for r in records) != mask.record_ids:
        raise AdultAdapterError("MASK_RECORD_MISMATCH", "records")
    masked = tuple(
        AdultRecord(
            record.row_id,
            tuple(None if hit else token for token, hit in zip(record.tokens, row, strict=True)),
        )
        for record, row in zip(records, mask.cells, strict=True)
    )
    return MaskedRows(masked, measure_new_missingness(records, masked), mask.mask_id)
