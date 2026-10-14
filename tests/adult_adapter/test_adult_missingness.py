"""Gate 9 Adult adapter: employment outage, MCAR nesting and the two denominators.

All rows are fabricated here. Nothing is scored, fitted or read from disk.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from shiftguard.adult_adapter.features import (
    ADULT_FEATURE_CONTRACT,
    AdultAdapterError,
    AdultRecord,
    record_from_raw_fields,
)
from shiftguard.adult_adapter.missingness import (
    EMPLOYMENT_BLOCK,
    EMPLOYMENT_ROW_PROBABILITY,
    EmploymentOutageMask,
    apply_mask,
    build_mcar_mask,
    employment_outage_mask,
    employment_outage_mask_pair,
    measure_new_missingness,
    shared_mcar_uniforms,
)
from shiftguard.datasets import adult as parser


FEATURES = ADULT_FEATURE_CONTRACT.features


@pytest.fixture(autouse=True)
def forbid_real_adult_paths(monkeypatch):
    def tripwire(name):
        def raiser(*_args, **_kwargs):
            raise AssertionError(f"adapter test reached {name}")
        return raiser

    for name in ("clean_adult_rows", "make_adult_role_splits", "acquire_adult_train_only", "execute_adult_confirmatory"):
        monkeypatch.setattr(parser, name, tripwire(name))


def record(i: int, **overrides: str) -> AdultRecord:
    fields = {
        "age": str(20 + i % 50), "workclass": "Private", "fnlwgt": str(100000 + i),
        "education-num": "9", "marital-status": "Never-married", "occupation": "Sales",
        "relationship": "Not-in-family", "race": "White", "sex": "Male",
        "capital-gain": "0", "capital-loss": "0", "hours-per-week": "40",
        "native-country": "United-States",
    }
    fields.update(overrides)
    return record_from_raw_fields(f"rel:adult.data:{i}", fields)


def many(n: int) -> tuple[AdultRecord, ...]:
    return tuple(record(i + 1) for i in range(n))


def value(rec: AdultRecord, feature: str):
    return rec.tokens[FEATURES.index(feature)]


def test_employment_block_and_probability_are_the_declared_ones():
    assert EMPLOYMENT_BLOCK == ("workclass", "occupation", "hours-per-week")
    assert EMPLOYMENT_ROW_PROBABILITY == 0.50
    mask = employment_outage_mask(tuple(r.row_id for r in many(5)), seed=1)
    assert mask.features == EMPLOYMENT_BLOCK
    assert mask.requested_row_probability == 0.50


def test_outage_masks_only_the_employment_block_on_raw_features():
    originals = many(400)
    mask = employment_outage_mask(tuple(r.row_id for r in originals), seed=11)
    result = apply_mask(originals, mask)
    assert 0 < sum(mask.selected) < len(originals)
    block_idx = {FEATURES.index(f) for f in EMPLOYMENT_BLOCK}
    for original, masked, selected in zip(originals, result.records, mask.selected, strict=True):
        assert masked.row_id == original.row_id
        for j, (before, after) in enumerate(zip(original.tokens, masked.tokens, strict=True)):
            if selected and j in block_idx:
                assert after is None
            else:
                assert after == before  # every other cell is untouched, including numerics
    # Masking is on raw tokens: the input records are not mutated.
    assert all(value(r, "workclass") == "Private" for r in originals)


def test_two_denominators_on_a_hand_checkable_example():
    # Four rows, 13 features each = 52 cells.
    rows = (
        record(1),                                           # selected, all three block cells observed -> 3 new
        record(2, occupation="?"),                           # selected, occupation already missing  -> 2 new
        record(3),                                           # not selected                          -> 0 new
        record(4, workclass="?", occupation="?", **{"hours-per-week": "?"}),  # selected, all natural -> 0 new
    )
    mask = EmploymentOutageMask(
        record_ids=tuple(r.row_id for r in rows),
        selected=(True, True, False, True),
        requested_row_probability=0.5,
    )
    counts = apply_mask(rows, mask).counts

    assert counts.row_count == 4
    assert counts.eligible_cells_total == 52
    assert counts.naturally_missing_cells == 4          # 1 + 3, excluded from numerator and denominator
    assert counts.originally_observed_cells == 48       # 52 - 4
    assert counts.newly_masked_cells == 5               # 3 + 2
    assert counts.rows_with_new_missingness == 2
    assert counts.injected_feature_counts == (3, 2, 0, 0)

    # (a) aggregate rate: new / ORIGINALLY OBSERVED cells over all 13 predictors.
    assert counts.aggregate_denominator == 48
    assert counts.aggregate_new_missing_rate == pytest.approx(5 / 48)
    # (b) fraction-bin routing value: per-row injected count / 13.
    assert counts.fraction_bin_denominator == 13
    assert counts.fraction_bin_values == pytest.approx((3 / 13, 2 / 13, 0.0, 0.0))
    # The two must not be conflated with each other or with the other plausible denominators.
    assert counts.aggregate_new_missing_rate != pytest.approx(5 / 52)
    assert counts.aggregate_new_missing_rate != pytest.approx(5 / 12)
    assert counts.aggregate_new_missing_rate != pytest.approx(sum(counts.fraction_bin_values) / 4)


def test_counts_are_persistable_and_include_every_number_used():
    rows = many(6)
    mask = EmploymentOutageMask(tuple(r.row_id for r in rows), (True,) * 6, 0.5)
    persisted = apply_mask(rows, mask).counts.as_record()
    for key in (
        "row_count", "eligible_cells_total", "originally_observed_cells", "naturally_missing_cells",
        "newly_masked_cells", "rows_with_new_missingness", "injected_feature_counts",
        "aggregate_denominator", "aggregate_denominator_name", "aggregate_new_missing_rate",
        "fraction_bin_denominator", "fraction_bin_values",
    ):
        assert key in persisted
    assert persisted["aggregate_denominator_name"] == "originally_observed_eligible_cells_across_13_predictors"
    assert persisted["newly_masked_cells"] == 18 and persisted["originally_observed_cells"] == 78
    assert persisted["fraction_bin_values"] == [3 / 13] * 6


def test_zero_originally_observed_cells_gives_no_rate_not_zero():
    rows = tuple(record(i, **{f: "?" for f in FEATURES if f != "age"}) for i in range(1, 3))
    rows = tuple(
        dataclasses.replace(r, tokens=(None,) * 13) for r in rows
    )
    mask = EmploymentOutageMask(tuple(r.row_id for r in rows), (True, True), 0.5)
    counts = apply_mask(rows, mask).counts
    assert counts.originally_observed_cells == 0
    assert counts.aggregate_new_missing_rate is None


def test_mcar_is_nested_across_rates_with_shared_uniforms():
    rows = many(300)
    ids = tuple(r.row_id for r in rows)
    uniforms = shared_mcar_uniforms(len(rows), seed=5)
    assert uniforms.shape == (300, 13)
    m10 = build_mcar_mask(ids, uniforms, 0.10)
    m30 = build_mcar_mask(ids, uniforms, 0.30)
    a = np.array(m10.cells)
    b = np.array(m30.cells)
    assert a.sum() > 0 and b.sum() > a.sum()
    assert not (a & ~b).any()  # every 0.10 cell is also a 0.30 cell
    assert build_mcar_mask(ids, uniforms, 0.0).cells == tuple((False,) * 13 for _ in ids)
    assert all(all(row) for row in build_mcar_mask(ids, uniforms, 1.0).cells)
    # Realized rates are close to the request on 300*13 cells.
    r10 = apply_mask(rows, m10).counts.aggregate_new_missing_rate
    r30 = apply_mask(rows, m30).counts.aggregate_new_missing_rate
    assert abs(r10 - 0.10) < 0.03 and abs(r30 - 0.30) < 0.04
    assert r10 < r30


def test_mcar_excludes_natural_missing_cells_from_both_terms():
    rows = (record(1, workclass="?"), record(2), record(3, race="?", sex="?"))
    uniforms = np.zeros((3, 13))  # rate 0.5 masks every cell
    counts = apply_mask(rows, build_mcar_mask(tuple(r.row_id for r in rows), uniforms, 0.5)).counts
    assert counts.naturally_missing_cells == 3
    assert counts.originally_observed_cells == 36
    assert counts.newly_masked_cells == 36
    assert counts.aggregate_new_missing_rate == 1.0
    assert counts.injected_feature_counts == (12, 13, 11)


def test_mcar_uniforms_are_reproducible_and_validated():
    assert np.array_equal(shared_mcar_uniforms(10, 3), shared_mcar_uniforms(10, 3))
    assert not np.array_equal(shared_mcar_uniforms(10, 3), shared_mcar_uniforms(10, 4))
    ids = tuple(r.row_id for r in many(4))
    for rate in (-0.1, 1.1, float("nan"), True, "0.1"):
        with pytest.raises(AdultAdapterError) as caught:
            build_mcar_mask(ids, shared_mcar_uniforms(4, 1), rate)
        assert caught.value.code == "RATE"
    with pytest.raises(AdultAdapterError) as caught:
        build_mcar_mask(ids, shared_mcar_uniforms(5, 1), 0.1)
    assert caught.value.code == "UNIFORMS_SHAPE"


def test_pool_and_test_streams_are_independent_functions_of_their_own_seed():
    pool_ids = tuple(r.row_id for r in many(250))
    test_ids = tuple(f"rel:adult.data:{1000 + i}" for i in range(250))
    pair = employment_outage_mask_pair(pool_ids, test_ids, pool_seed=71, test_seed=72)
    # Each stream is reproduced from its own seed alone.
    assert pair.pool == employment_outage_mask(pool_ids, 71)
    assert pair.test == employment_outage_mask(test_ids, 72)
    # Changing the test seed cannot move the pool stream, and vice versa.
    other = employment_outage_mask_pair(pool_ids, test_ids, pool_seed=71, test_seed=73)
    assert other.pool == pair.pool and other.test != pair.test
    other = employment_outage_mask_pair(pool_ids, test_ids, pool_seed=74, test_seed=72)
    assert other.test == pair.test and other.pool != pair.pool
    # Swapping seeds swaps the streams.
    assert employment_outage_mask(pool_ids, 72).selected == pair.test.selected
    assert pair.pool.mask_id != pair.test.mask_id
    # Identical seeds would make the streams one stream.
    with pytest.raises(AdultAdapterError) as caught:
        employment_outage_mask_pair(pool_ids, test_ids, pool_seed=5, test_seed=5)
    assert caught.value.code == "SEEDS_NOT_DISTINCT"


def test_selection_rate_follows_the_requested_row_probability():
    ids = tuple(r.row_id for r in many(2000))
    mask = employment_outage_mask(ids, seed=9)
    assert abs(sum(mask.selected) / 2000 - 0.5) < 0.05


@pytest.mark.parametrize("bad", [True, False, 1.0, 7.5, np.int64(3), "7", None, -1])
def test_seeds_must_be_strict_non_negative_ints(bad):
    ids = tuple(r.row_id for r in many(3))
    with pytest.raises(AdultAdapterError) as caught:
        employment_outage_mask(ids, bad)
    assert caught.value.code in {"SEED_TYPE", "SEED_RANGE"}
    with pytest.raises(AdultAdapterError):
        employment_outage_mask_pair(ids, ids, pool_seed=bad, test_seed=1)
    with pytest.raises(AdultAdapterError):
        employment_outage_mask_pair(ids, ids, pool_seed=1, test_seed=bad)
    with pytest.raises(AdultAdapterError):
        shared_mcar_uniforms(3, bad)
    if isinstance(bad, (bool, float, str)) or bad is None or isinstance(bad, np.integer):
        assert caught.value.code == "SEED_TYPE"


def test_row_probability_is_validated():
    ids = tuple(r.row_id for r in many(3))
    for bad in (-0.1, 1.5, float("inf"), True, "0.5"):
        with pytest.raises(AdultAdapterError) as caught:
            employment_outage_mask(ids, 1, row_probability=bad)
        assert caught.value.code == "RATE"


def test_mask_ids_must_match_the_records_applied():
    rows = many(3)
    mask = employment_outage_mask(tuple(r.row_id for r in rows), 1)
    with pytest.raises(AdultAdapterError) as caught:
        apply_mask(rows[:2], mask)
    assert caught.value.code == "MASK_RECORD_MISMATCH"
    with pytest.raises(AdultAdapterError) as caught:
        apply_mask(tuple(reversed(rows)), mask)
    assert caught.value.code == "MASK_RECORD_MISMATCH"
    with pytest.raises(AdultAdapterError) as caught:
        EmploymentOutageMask(("a:adult.data:1",), (True, False), 0.5)
    assert caught.value.code == "MASK_SHAPE"
    with pytest.raises(AdultAdapterError) as caught:
        EmploymentOutageMask(("a:adult.data:1",), (1,), 0.5)  # type: ignore[arg-type]
    assert caught.value.code == "MASK_SHAPE"


def test_measure_rejects_a_masked_set_that_restores_or_alters_cells():
    rows = many(2)
    restored = (dataclasses.replace(rows[0], tokens=(None,) + rows[0].tokens[1:]), rows[1])
    # Original side missing but masked side observed is impossible for masking.
    with pytest.raises(AdultAdapterError) as caught:
        measure_new_missingness(restored, rows)
    assert caught.value.code == "MASK_ALTERED_CELL"
    altered = (dataclasses.replace(rows[0], tokens=("99",) + rows[0].tokens[1:]), rows[1])
    with pytest.raises(AdultAdapterError) as caught:
        measure_new_missingness(rows, altered)
    assert caught.value.code == "MASK_ALTERED_CELL"
    with pytest.raises(AdultAdapterError) as caught:
        measure_new_missingness(rows, rows[:1])
    assert caught.value.code == "MASK_RECORD_MISMATCH"


def test_mask_id_is_a_stable_digest_of_the_mask_content():
    ids = tuple(r.row_id for r in many(20))
    a = employment_outage_mask(ids, 3)
    assert a.mask_id == employment_outage_mask(ids, 3).mask_id
    assert len(a.mask_id) == 64
    assert a.mask_id != employment_outage_mask(ids, 4).mask_id


# ---------------------------------------------------------------- OR-07: uniforms are validated, never cast

def _ids(n: int) -> tuple[str, ...]:
    return tuple(r.row_id for r in many(n))


def _uniform_matrix(value, n=2, dtype=np.float64) -> np.ndarray:
    return np.full((n, 13), value, dtype=dtype)


def _code_of(call) -> str:
    with pytest.raises(AdultAdapterError) as caught:
        call()
    return caught.value.code


def test_rejects_invalid_uniform_arrays():
    ids = _ids(2)
    for dtype in (np.float64, np.float32):
        # The review's reproductions: each value used to be accepted and hashed into a valid mask.
        for bad in (np.nan, np.inf, -np.inf, -1.0, -np.finfo(dtype).tiny, 1.0, 1.5, 2.0):
            assert _code_of(lambda: build_mcar_mask(ids, _uniform_matrix(bad, dtype=dtype), 0.10)) == (
                "UNIFORMS_RANGE"
            ), (dtype, bad)
        single = _uniform_matrix(0.5, dtype=dtype)
        single[1, 7] = np.nan  # one bad cell among valid ones is enough
        assert _code_of(lambda: build_mcar_mask(ids, single, 0.10)) == "UNIFORMS_RANGE"
        single[1, 7] = 1.0
        assert _code_of(lambda: build_mcar_mask(ids, single, 0.10)) == "UNIFORMS_RANGE"
    # The rate is irrelevant to the check: even a rate that would mask nothing sees invalid data.
    assert _code_of(lambda: build_mcar_mask(ids, _uniform_matrix(np.nan), 0.0)) == "UNIFORMS_RANGE"
    assert _code_of(lambda: build_mcar_mask(ids, _uniform_matrix(1.0), 1.0)) == "UNIFORMS_RANGE"

    for shape in ((2, 12), (2, 14), (1, 13), (3, 13), (26,), (2, 13, 1), (13, 2)):
        assert _code_of(lambda: build_mcar_mask(ids, np.zeros(shape), 0.1)) == "UNIFORMS_SHAPE", shape

    unsupported = {
        "int64": np.zeros((2, 13), dtype=np.int64),
        "int32": np.zeros((2, 13), dtype=np.int32),
        "uint8": np.zeros((2, 13), dtype=np.uint8),
        "bool": np.zeros((2, 13), dtype=bool),
        "object": np.full((2, 13), 0.5, dtype=object),
        "complex128": np.full((2, 13), 0.5, dtype=np.complex128),
        "complex64": np.full((2, 13), 0.5, dtype=np.complex64),
        "float16": np.full((2, 13), 0.5, dtype=np.float16),
        "longdouble": np.full((2, 13), 0.5, dtype=np.longdouble),
        "str": np.full((2, 13), "0.5"),
    }
    for name, array in unsupported.items():
        assert _code_of(lambda: build_mcar_mask(ids, array, 0.10)) == "UNIFORMS_DTYPE", name
    # Right dtype name, wrong container: lists, tuples, scalars, masked arrays and None are not arrays.
    valid = _uniform_matrix(0.5)
    for container in (valid.tolist(), tuple(map(tuple, valid.tolist())), 0.5, None, np.ma.masked_array(valid)):
        assert _code_of(lambda: build_mcar_mask(ids, container, 0.10)) == "UNIFORMS_TYPE"
    # A rate error still wins over uniform problems, as before.
    assert _code_of(lambda: build_mcar_mask(ids, _uniform_matrix(np.nan), 1.5)) == "RATE"


def test_valid_uniform_arrays_zero_and_the_largest_value_below_one_are_accepted():
    ids = _ids(3)
    for dtype in (np.float64, np.float32):
        largest = np.nextafter(dtype(1), dtype(0))
        assert largest < 1.0
        for value, masked_at_half in ((0.0, True), (float(largest), False)):
            array = np.full((3, 13), value, dtype=dtype)
            mask = build_mcar_mask(ids, array, 0.5)
            assert all(all(row) == masked_at_half and any(row) == masked_at_half for row in mask.cells)
        # u < rate is strict: a cell equal to the rate stays observed; rate 1 masks every valid cell.
        array = np.full((3, 13), largest, dtype=dtype)
        assert all(all(row) for row in build_mcar_mask(ids, array, 1.0).cells)
        assert not any(any(row) for row in build_mcar_mask(ids, np.zeros((3, 13), dtype=dtype), 0.0).cells)
        half = np.full((3, 13), 0.5, dtype=dtype)
        assert not any(any(row) for row in build_mcar_mask(ids, half, 0.5).cells)
    empty = build_mcar_mask((), np.zeros((0, 13)), 0.3)
    assert empty.cells == () and empty.record_ids == ()
    assert build_mcar_mask(ids, np.zeros((3, 13), dtype=np.float32), 0.1) == build_mcar_mask(
        ids, np.zeros((3, 13), dtype=np.float64), 0.1)


def test_float32_uniforms_compare_exactly_in_float64():
    # float32(0.7) is a hair below 0.7. Rounding the rate to float32 would call that cell "equal"
    # and leave it observed; the exact comparison masks it, exactly as a float64 matrix would.
    ids = _ids(1)
    exact = np.float32(0.7)
    assert float(exact) < 0.7
    array = np.full((1, 13), np.nextafter(exact, np.float32(1)), dtype=np.float32)
    array[0, 0] = exact
    mask = build_mcar_mask(ids, array, 0.7)
    assert mask.cells[0][0] is True and not any(mask.cells[0][1:])
    assert build_mcar_mask(ids, array.astype(np.float64), 0.7) == mask


def test_invalid_uniforms_are_rejected_before_any_mask_identity_exists(monkeypatch):
    built = []
    import shiftguard.adult_adapter.missingness as module

    original = module.McarMask
    monkeypatch.setattr(module, "McarMask", lambda *a, **k: built.append(a) or original(*a, **k))
    for bad in (np.nan, np.inf, -1.0, 1.0):
        with pytest.raises(AdultAdapterError):
            build_mcar_mask(_ids(2), _uniform_matrix(bad), 0.10)
    assert built == []


def test_existing_valid_mask_identities_are_unchanged():
    ids = _ids(40)
    uniforms = shared_mcar_uniforms(40, seed=5)
    assert uniforms.dtype == np.float64 and uniforms.min() >= 0.0 and uniforms.max() < 1.0
    from shiftguard.adult_adapter.features import canonical_digest

    # Pinned identities of the fabricated 40-row stream: validation must not move a valid mask.
    assert build_mcar_mask(ids, uniforms, 0.10).mask_id == (
        "01b3bfdf4302b20712e01273354512511e6539d2aa5b5ef42f7077a363ce7644")
    assert build_mcar_mask(ids, uniforms, 0.30).mask_id == (
        "12a26b47a4e2841f044e0e81ec30d91021649350a4e0981956918e0ffcb7d3d7")

    for rate in (0.0, 0.10, 0.30, 1.0):
        mask = build_mcar_mask(ids, uniforms, rate)
        cells = [[bool(u < rate) for u in row] for row in uniforms]
        reference = canonical_digest(["gate9-adult-mask-v1", "mcar", list(ids), cells, rate])
        assert mask.mask_id == reference
    # Nested masks stay nested: every cell masked at 0.10 is masked at 0.30, in both dtypes.
    for dtype in (np.float64, np.float32):
        low = np.array(build_mcar_mask(ids, uniforms.astype(dtype), 0.10).cells)
        high = np.array(build_mcar_mask(ids, uniforms.astype(dtype), 0.30).cells)
        assert low.sum() > 0 and high.sum() > low.sum() and not (low & ~high).any()


def test_observed_cell_handling_and_nested_masks_survive_validation():
    rows = (record(1, workclass="?"), record(2), record(3, race="?", sex="?"))
    ids = tuple(r.row_id for r in rows)
    uniforms = np.full((3, 13), 0.25, dtype=np.float32)
    uniforms[1, :6] = 0.05
    low = apply_mask(rows, build_mcar_mask(ids, uniforms, 0.10)).counts
    high = apply_mask(rows, build_mcar_mask(ids, uniforms, 0.30)).counts
    assert (low.naturally_missing_cells, high.naturally_missing_cells) == (3, 3)
    assert low.originally_observed_cells == high.originally_observed_cells == 36
    assert low.newly_masked_cells == 6 and high.newly_masked_cells == 36
    assert low.injected_feature_counts == (0, 6, 0)
    assert high.injected_feature_counts == (12, 13, 11)
    assert low.newly_masked_cells < high.newly_masked_cells
