from __future__ import annotations

import dataclasses
import json
import math
import random
import statistics

import pytest

from repeat_fixtures import (
    fake_digest,
    packet_fixture_sums,
    primary_cell,
    primary_cells,
    primary_context,
    primary_keys,
    synthetic_plan,
    varied_sums,
)
from shiftguard.repeats.aggregation import (
    PrimarySummary,
    aggregate_primary,
    prepare_group_sums,
    weighted_estimate,
)
from shiftguard.repeats.models import (
    INNER_IDS,
    OUTER_SEEDS,
    PREDICTORS,
    PRIMARY_SCENARIOS,
    SYNTHETIC_CLAIM_SCOPE,
    MissingEvidence,
    PairedGroupLossCell,
    RepeatContractError,
)


FIRST = (41001, 51001, "logistic_regression", "history_block_0_50")
OTHER = (41004, 51009, "random_forest", "mcar_matched_history")


def _code(call) -> str:
    with pytest.raises(RepeatContractError) as raised:
        call()
    return raised.value.code


@pytest.fixture(scope="module")
def plan():
    return synthetic_plan()


@pytest.fixture(scope="module")
def fixture_cells(plan):
    return primary_cells(plan, packet_fixture_sums)


def _with(cells, replacement):
    return tuple(replacement if cell.key == replacement.key else cell for cell in cells)


def test_row_mass_within_a_cell_is_preserved_instead_of_equal_group_means(plan, fixture_cells):
    summary = aggregate_primary(plan, fixture_cells)
    assert isinstance(summary, PrimarySummary)
    # Counts [1, 3] with sums [.2, -.6]: (0.2 - 0.6) / 4, not the group-mean average 0.
    assert summary.theta == pytest.approx(-0.1, abs=1e-12)
    assert statistics.fmean((0.2 / 1, -0.6 / 3)) == pytest.approx(0.0, abs=1e-12)
    assert summary.outer_values == pytest.approx((-0.1,) * 5, abs=1e-12)
    assert len(summary.inner_values) == 5 and all(len(row) == 10 for row in summary.inner_values)
    assert summary.inner_sd_by_outer == pytest.approx((0.0,) * 5, abs=1e-12)
    assert summary.outer_sd == pytest.approx(0.0, abs=1e-12)


def test_one_effect_in_one_of_four_hundred_cells_uses_the_declared_equal_weights(plan):
    def sums(key, counts):
        return tuple(count * (0.8 if key == FIRST else 0.0) for count in counts)

    summary = aggregate_primary(plan, primary_cells(plan, sums))
    # 0.8 * (1/8 cells) * (1/10 inner repeats) * (1/5 outer repeats)
    assert summary.theta == pytest.approx(0.002, abs=1e-15)
    assert summary.inner_values[0][0] == pytest.approx(0.1, abs=1e-15)
    assert summary.outer_values == pytest.approx((0.01, 0.0, 0.0, 0.0, 0.0), abs=1e-15)
    assert summary.cell_count == 400 == len(primary_keys())


def test_missing_required_pair_nulls_the_primary_without_renormalizing(plan, fixture_cells):
    survivors = tuple(cell for cell in fixture_cells if cell.key != OTHER)
    evidence = aggregate_primary(plan, survivors)
    assert isinstance(evidence, MissingEvidence)
    assert evidence.code == "PRIMARY_EVIDENCE_UNAVAILABLE"
    assert evidence.missing == (OTHER,)
    assert evidence.primary_estimate is None and evidence.interval is None
    assert isinstance(prepare_group_sums(plan, survivors), MissingEvidence)


def test_failed_unqualified_and_unknown_authority_pairs_keep_every_reason(plan, fixture_cells):
    failed = primary_cell(
        plan, FIRST, paired_loss_sum_by_group=None, qualification="failed",
        reasons=("raw prediction failed",), target_resolved_method=None,
    )
    unknown = primary_cell(
        plan, OTHER, sums=packet_fixture_sums(OTHER, plan.group_counts(OTHER[0])),
        qualification="unknown_authority", reasons=("SCI-03 scope not approved",),
    )
    for qualification in ("unqualified", "unknown_authority", "failed"):
        single = failed if qualification == "failed" else dataclasses.replace(
            unknown, qualification=qualification
        )
        evidence = aggregate_primary(plan, _with(fixture_cells, single))
        assert isinstance(evidence, MissingEvidence)
        assert evidence.unavailable == ((single.key, qualification, single.reasons),)
        assert evidence.primary_estimate is None and evidence.interval is None

    cells = tuple(
        cell for cell in _with(_with(fixture_cells, failed), unknown)
        if cell.key != (41002, 51002, "logistic_regression", "mcar_0_10")
    )
    evidence = aggregate_primary(plan, cells)
    assert evidence.missing == ((41002, 51002, "logistic_regression", "mcar_0_10"),)
    assert evidence.unavailable == (
        (FIRST, "failed", ("raw prediction failed",)),
        (OTHER, "unknown_authority", ("SCI-03 scope not approved",)),
    )
    assert evidence.reasons == ("SCI-03 scope not approved", "raw prediction failed")


def test_valid_fallback_stays_inside_the_requested_complete_strategy(plan, fixture_cells):
    fallback = primary_cell(
        plan, FIRST, sums=packet_fixture_sums(FIRST, plan.group_counts(FIRST[0])),
        target_resolved_method="source_temperature",
    )
    summary = aggregate_primary(plan, _with(fixture_cells, fallback))
    assert isinstance(summary, PrimarySummary)
    assert summary.theta == pytest.approx(-0.1, abs=1e-12)
    assert summary.fallback_cells == 1
    assert summary.contrast == ("target_temperature", "source_fraction_binned_temperature")
    assert (summary.budget, summary.metric, summary.direction) == (
        50, "binary_brier_mse", "target_minus_source",
    )


def test_spread_is_a_sensitivity_diagnostic_and_repeats_are_not_samples(plan):
    effects = dict(zip(OUTER_SEEDS, (0.10, -0.20, 0.30, 0.0, 0.05)))

    def sums(key, counts):
        inner_shift = 0.01 * (key[1] - INNER_IDS[0])
        return tuple(count * (effects[key[0]] + inner_shift) for count in counts)

    summary = aggregate_primary(plan, primary_cells(plan, sums))
    expected_inner = [[effects[outer] + 0.01 * step for step in range(10)] for outer in OUTER_SEEDS]
    expected_outer = [statistics.fmean(row) for row in expected_inner]
    assert summary.outer_values == pytest.approx(expected_outer, abs=1e-12)
    assert summary.theta == pytest.approx(statistics.fmean(expected_outer), abs=1e-12)
    assert summary.outer_sd == pytest.approx(statistics.stdev(expected_outer), abs=1e-12)
    assert summary.inner_sd_by_outer == pytest.approx(
        [statistics.stdev(row) for row in expected_inner], abs=1e-12
    )
    assert summary.outer_sd != pytest.approx(statistics.stdev(expected_outer) / math.sqrt(50))

    assert (summary.execution_coordinates, summary.source_releases) == (50, 1)
    assert summary.seed_count_is_sample_size is False
    assert summary.rows_by_outer == (4,) * 5 and summary.groups_by_outer == (2,) * 5
    assert (summary.unique_evaluation_rows, summary.unique_groups) == (4, 2)
    assert summary.total_row_appearances == 20
    assert summary.synthetic is True and summary.claim_scope == SYNTHETIC_CLAIM_SCOPE
    names = {field.name for field in dataclasses.fields(summary)}
    assert not {name for name in names if "standard_error" in name or "p_value" in name}


def test_result_is_identical_for_any_input_order_or_chunking(plan):
    cells = primary_cells(plan, varied_sums)
    expected = aggregate_primary(plan, cells)
    shuffled = list(cells)
    random.Random(7).shuffle(shuffled)
    chunks = [cells[start:start + 37] for start in range(0, len(cells), 37)]
    rechunked = tuple(cell for chunk in reversed(chunks) for cell in chunk)
    assert aggregate_primary(plan, tuple(reversed(cells))) == expected
    assert aggregate_primary(plan, tuple(shuffled)) == expected
    assert aggregate_primary(plan, rechunked) == expected
    assert prepare_group_sums(plan, tuple(shuffled)) == prepare_group_sums(plan, cells)


def test_collapsed_group_sums_equal_the_full_four_hundred_cell_arithmetic(plan):
    cells = primary_cells(plan, varied_sums)
    summary = aggregate_primary(plan, cells)
    prepared = prepare_group_sums(plan, cells)
    assert prepared.group_ids == plan.group_universe
    assert prepared.counts == tuple(plan.group_counts(outer) for outer in OUTER_SEEDS)
    assert prepared.point_estimate == pytest.approx(summary.theta, abs=1e-12)
    assert prepared.synthetic is True and prepared.plan_digest == plan.plan_digest

    by_key = {cell.key: cell for cell in cells}
    for weights in ((1, 1), (3, 1), (2, 0), (0, 2), (5, 7)):
        outers = []
        for outer in OUTER_SEEDS:
            inners = []
            for inner in INNER_IDS:
                deltas = []
                for predictor in PREDICTORS:
                    for scenario in PRIMARY_SCENARIOS:
                        cell = by_key[(outer, inner, predictor, scenario)]
                        numerator = sum(w * s for w, s in zip(weights, cell.paired_loss_sum_by_group))
                        denominator = sum(w * n for w, n in zip(weights, cell.n_by_group))
                        deltas.append(numerator / denominator)
                inners.append(statistics.fmean(deltas))
            outers.append(statistics.fmean(inners))
        assert weighted_estimate(prepared, weights, plan=plan) == pytest.approx(
            statistics.fmean(outers), abs=1e-12
        )
    assert weighted_estimate(prepared, (0, 0), plan=plan) is None


def test_packet_fixture_group_multiplicities(plan, fixture_cells):
    prepared = prepare_group_sums(plan, fixture_cells)
    assert [weighted_estimate(prepared, w, plan=plan) for w in ((2, 0), (1, 1), (0, 2))] == pytest.approx(
        [0.2, -0.1, -0.2], abs=1e-12
    )


@pytest.mark.parametrize("overrides, code", [
    ({"paired_loss_sum_by_group": (math.nan, 0.0)}, "INVALID_GROUP_SUM"),
    ({"paired_loss_sum_by_group": (math.inf, 0.0)}, "INVALID_GROUP_SUM"),
    ({"paired_loss_sum_by_group": (1.5, 0.0)}, "INVALID_GROUP_SUM"),
    ({"paired_loss_sum_by_group": (0, 0.0)}, "INVALID_GROUP_SUM"),
    ({"paired_loss_sum_by_group": (0.0,)}, "GROUP_SHAPE"),
    ({"n_by_group": (0, 3), "paired_loss_sum_by_group": (0.1, 0.0)}, "INVALID_GROUP_SUM"),
    ({"n_by_group": (True, 3)}, "STRICT_INTEGER"),
    ({"n_by_group": (1.0, 3)}, "STRICT_INTEGER"),
    ({"n_by_group": (-1, 3), "paired_loss_sum_by_group": (0.0, 0.0)}, "NEGATIVE_COUNT"),
    ({"group_ids": ("synthetic-group-b", "synthetic-group-a")}, "GROUP_ORDER"),
    ({"qualification": "unknown_authority"}, "QUALIFICATION"),
    ({"qualification": "failed", "reasons": ("failed",)}, "INVALID_GROUP_SUM"),
    ({"paired_loss_sum_by_group": None}, "INVALID_GROUP_SUM"),
    ({"n_by_group": [1, 3]}, "IMMUTABLE_TUPLE"),
])
def test_cell_rejects_invalid_counts_sums_and_states(plan, overrides, code):
    assert _code(lambda: primary_cell(plan, FIRST, **overrides)) == code


def test_aggregation_rejects_cells_outside_or_inconsistent_with_the_plan(plan, fixture_cells):
    assert _code(lambda: aggregate_primary(plan, fixture_cells + (fixture_cells[0],))) == (
        "DUPLICATE_PRIMARY_CELL"
    )
    assert _code(lambda: aggregate_primary(plan, list(fixture_cells))) == "IMMUTABLE_TUPLE"

    pool = plan.roles(FIRST[0]).target_pool_ids
    context = fixture_cells[0].context
    for change in ({"budget": 25, "acquired_prefix": pool[:25]}, {"scenario": "baseline"}):
        outside = dataclasses.replace(
            fixture_cells[0], context=dataclasses.replace(context, **change)
        )
        assert _code(lambda: aggregate_primary(plan, fixture_cells[1:] + (outside,))) == (
            "UNEXPECTED_PRIMARY_CELL"
        )

    wrong_counts = dataclasses.replace(
        fixture_cells[0], n_by_group=(2, 2), paired_loss_sum_by_group=(0.2, -0.6)
    )
    assert _code(lambda: aggregate_primary(plan, _with(fixture_cells, wrong_counts))) == (
        "GROUP_COUNT_MISMATCH"
    )
    wrong_universe = dataclasses.replace(
        fixture_cells[0], group_ids=("synthetic-group-a", "synthetic-group-z")
    )
    assert _code(lambda: aggregate_primary(plan, _with(fixture_cells, wrong_universe))) == (
        "GROUP_UNIVERSE_MISMATCH"
    )
    for field in ("seed_map", "source_binding"):
        foreign = dataclasses.replace(
            fixture_cells[0],
            context=dataclasses.replace(context, **{field: fake_digest("foreign")}),
        )
        assert _code(lambda: aggregate_primary(plan, _with(fixture_cells, foreign))) == (
            "PAIR_CONTEXT_MISMATCH"
        )
    forged = dataclasses.replace(plan, plan_digest="0" * 64)
    assert _code(lambda: aggregate_primary(forged, fixture_cells)) == "PLAN_INTEGRITY"


@pytest.mark.parametrize("field", ["test_mask", "pool_mask", "acquisition_order", "predictor_id"])
def test_paired_cells_must_share_masks_acquisition_and_fitted_predictor(plan, fixture_cells, field):
    target = fixture_cells[0]
    drifted = dataclasses.replace(
        target, context=dataclasses.replace(target.context, **{field: fake_digest("drifted")})
    )
    assert _code(lambda: aggregate_primary(plan, _with(fixture_cells, drifted))) == (
        "SHARED_CONTEXT_MISMATCH"
    )


def test_acquired_prefix_must_be_shared_and_drawn_from_the_pool(plan, fixture_cells):
    target = fixture_cells[0]
    pool = plan.roles(FIRST[0]).target_pool_ids
    other_prefix = dataclasses.replace(
        target, context=dataclasses.replace(target.context, acquired_prefix=pool[1:51])
    )
    assert _code(lambda: aggregate_primary(plan, _with(fixture_cells, other_prefix))) == (
        "SHARED_CONTEXT_MISMATCH"
    )
    outside = tuple(f"synthetic:not-in-pool:{n}" for n in range(50))
    foreign = dataclasses.replace(
        target, context=dataclasses.replace(target.context, acquired_prefix=outside)
    )
    assert _code(lambda: aggregate_primary(plan, _with(fixture_cells, foreign))) == (
        "PAIR_CONTEXT_MISMATCH"
    )


def test_bank_overlap_membership_keeps_absent_groups_at_zero_mass():
    plan = synthetic_plan({41001: (1, 0)})
    assert plan.group_counts(41001) == (1, 0) and plan.group_counts(41002) == (1, 3)
    cells = primary_cells(plan, packet_fixture_sums)
    summary = aggregate_primary(plan, cells)
    # Outer 41001 only has the single-row group: 0.2 / 1; the others stay at -0.1.
    assert summary.outer_values == pytest.approx((0.2, -0.1, -0.1, -0.1, -0.1), abs=1e-12)
    assert summary.rows_by_outer == (1, 4, 4, 4, 4) and summary.groups_by_outer == (1, 2, 2, 2, 2)
    assert (summary.unique_evaluation_rows, summary.total_row_appearances) == (4, 17)
    absent_with_mass = dataclasses.replace(cells[0], paired_loss_sum_by_group=(0.2, 0.0))
    assert absent_with_mass == cells[0]
    assert _code(
        lambda: dataclasses.replace(cells[0], paired_loss_sum_by_group=(0.2, -0.1))
    ) == "INVALID_GROUP_SUM"


def test_primary_is_available_while_the_full_grid_is_still_incomplete(plan, fixture_cells):
    from test_repeat_validation import SECONDARY_SLOT, _condition
    from shiftguard.repeats.validation import expected_condition_slots, validate_condition_inventory

    inventory = tuple(
        _condition(plan, slot) for slot in expected_condition_slots(plan.spec)
        if slot != SECONDARY_SLOT
    )
    result = validate_condition_inventory(plan, inventory)
    assert result.full_grid_complete is False and result.primary_ready is True
    assert isinstance(aggregate_primary(plan, fixture_cells), PrimarySummary)


# ---------------------------------------------------------------- OR-06: pair-level resolution accounting

BINNED = "source_fraction_binned_temperature"
FIRST_SUMS = packet_fixture_sums(FIRST, (1, 3))


def _first_cell(plan, **overrides):
    return primary_cell(plan, FIRST, sums=FIRST_SUMS, **overrides)


def test_valid_cell_carries_target_and_source_resolution_counts(plan):
    cell = _first_cell(plan)
    assert cell.target_resolution_counts == (("target_temperature", 4),)
    assert cell.source_resolution_counts == ((BINNED, 4),)
    assert (cell.target_fallback_rows, cell.source_fallback_rows, cell.has_fallback) == (0, 0, False)


def test_mixed_binned_resolution_is_a_fallback_cell_despite_the_top_level_label(plan, fixture_cells):
    mixed = _first_cell(
        plan,
        source_resolution_counts=(("source_temperature", 1), ("source_remasked_temperature", 1), (BINNED, 2)),
    )
    # The top-level label still says "binned"; the per-row accounting is what reveals the fallback.
    assert mixed.source_resolved_method == BINNED
    assert (mixed.source_fallback_rows, mixed.target_fallback_rows, mixed.has_fallback) == (2, 0, True)
    summary = aggregate_primary(plan, _with(fixture_cells, mixed))
    assert isinstance(summary, PrimarySummary) and summary.fallback_cells == 1
    assert summary.theta == pytest.approx(-0.1, abs=1e-12)
    # Fully fitted-bin and wholly fallen-back cells are told apart as well.
    clean = aggregate_primary(plan, fixture_cells)
    assert clean.fallback_cells == 0
    wholly = _first_cell(plan, source_resolved_method="source_remasked_temperature",
                         source_resolution_counts=(("source_remasked_temperature", 4),))
    assert aggregate_primary(plan, _with(fixture_cells, wholly)).fallback_cells == 1
    both = _first_cell(plan, target_resolved_method="source_temperature",
                       target_resolution_counts=(("source_temperature", 4),),
                       source_resolution_counts=(("source_temperature", 4),),
                       source_resolved_method="source_temperature")
    assert aggregate_primary(plan, _with(fixture_cells, both)).fallback_cells == 1  # cells, not sides


@pytest.mark.parametrize("overrides, code", [
    ({"source_resolution_counts": ((BINNED, 2), (BINNED, 2))}, "RESOLUTION_ACCOUNTING"),
    ({"source_resolution_counts": (("source_temperature", 2), ("source_remasked_temperature", 1),
                                   ("raw", 1), (BINNED, 0))}, "RESOLUTION_ACCOUNTING"),
    ({"source_resolution_counts": ((BINNED, 2), ("source_temperature", 2))}, "RESOLUTION_ACCOUNTING"),
    ({"source_resolution_counts": ((BINNED, 0),)}, "RESOLUTION_ACCOUNTING"),
    ({"source_resolution_counts": ((BINNED, 3),)}, "RESOLUTION_ACCOUNTING"),
    ({"target_resolution_counts": (("target_temperature", 5),)}, "RESOLUTION_ACCOUNTING"),
    ({"target_resolution_counts": ()}, "RESOLUTION_ACCOUNTING"),
    ({"target_resolution_counts": (("source_temperature", 2), ("target_temperature", 2))},
     "RESOLUTION_ACCOUNTING"),
    ({"target_resolved_method": "source_temperature",
      "target_resolution_counts": (("source_temperature", 4),),
      "source_resolution_counts": (("target_temperature", 4),)}, "FORBIDDEN_FALLBACK"),
    ({"source_resolved_method": "target_temperature",
      "source_resolution_counts": (("target_temperature", 4),)}, "FORBIDDEN_FALLBACK"),
    ({"target_resolved_method": "source_remasked_temperature",
      "target_resolution_counts": (("source_remasked_temperature", 4),)}, "FORBIDDEN_FALLBACK"),
    ({"source_resolution_counts": ((BINNED, True),)}, "STRICT_INTEGER"),
    ({"source_resolution_counts": ((BINNED, -4),)}, "NEGATIVE_COUNT"),
    ({"source_resolution_counts": (("invented", 4),)}, "UNDECLARED_VALUE"),
    ({"source_resolution_counts": [(BINNED, 4)]}, "IMMUTABLE_TUPLE"),
    ({"source_resolved_method": None, "source_resolution_counts": ()}, "RESOLUTION_ACCOUNTING"),
])
def test_cell_rejects_invalid_resolution_accounting(plan, overrides, code):
    assert _code(lambda: _first_cell(plan, **overrides)) == code


def test_unscored_cell_keeps_empty_accounting_for_an_unresolved_side(plan):
    failed = primary_cell(
        plan, FIRST, paired_loss_sum_by_group=None, qualification="failed",
        reasons=("raw prediction failed",), target_resolved_method=None, source_resolved_method=None)
    assert failed.target_resolution_counts == () and failed.source_resolution_counts == ()
    assert failed.has_fallback is False
    # A resolution without counts, or counts without a resolution, is refused even when unscored.
    assert _code(lambda: primary_cell(
        plan, FIRST, paired_loss_sum_by_group=None, qualification="failed", reasons=("failed",),
        target_resolved_method=None, target_resolution_counts=(("raw", 4),))) == "RESOLUTION_ACCOUNTING"


def test_cell_canonical_form_round_trips_and_keeps_the_mixture(plan):
    mixed = _first_cell(
        plan, source_resolution_counts=(("source_temperature", 1), (BINNED, 3)))
    stored = json.loads(json.dumps(mixed.to_canonical(), sort_keys=True))
    assert stored["record_version"] == "gate8-paired-cell-v2"
    reopened = PairedGroupLossCell.from_canonical(stored)
    assert reopened == mixed and reopened.has_fallback and reopened.source_fallback_rows == 1
    failed = primary_cell(
        plan, FIRST, paired_loss_sum_by_group=None, qualification="failed", reasons=("x",),
        target_resolved_method=None, source_resolved_method=None)
    assert PairedGroupLossCell.from_canonical(json.loads(json.dumps(failed.to_canonical()))) == failed


def test_old_or_unknown_cell_versions_fail_with_a_version_error_and_never_default(plan):
    stored = json.loads(json.dumps(_first_cell(plan).to_canonical()))
    # The earlier record shape had no accounting fields; it must not be read as "all rows resolved".
    old = {key: value for key, value in stored.items()
           if key not in ("target_resolution_counts", "source_resolution_counts")}
    old["record_version"] = "gate8-paired-cell-v1"
    assert _code(lambda: PairedGroupLossCell.from_canonical(old)) == "RECORD_VERSION"
    unversioned = {key: value for key, value in old.items() if key != "record_version"}
    assert _code(lambda: PairedGroupLossCell.from_canonical(unversioned)) == "RECORD_VERSION"
    assert _code(lambda: PairedGroupLossCell.from_canonical({**stored, "record_version": "v3"})) == (
        "RECORD_VERSION"
    )
    stripped = {key: value for key, value in stored.items() if key != "source_resolution_counts"}
    assert _code(lambda: PairedGroupLossCell.from_canonical(stripped)) == "RECORD_FIELDS"
    assert _code(lambda: PairedGroupLossCell.from_canonical([stored])) == "RECORD_VERSION"


def test_malformed_stored_cells_fail_as_typed_record_errors(plan):
    stored = json.loads(json.dumps(_first_cell(plan).to_canonical()))
    for field, bad in (("source_resolution_counts", 7), ("group_ids", 7), ("n_by_group", None)):
        assert _code(lambda: PairedGroupLossCell.from_canonical({**stored, field: bad})) in {
            "RECORD_FIELDS", "IMMUTABLE_TUPLE"}
    assert _code(lambda: PairedGroupLossCell.from_canonical(
        {**stored, "context": {**stored["context"], "group_map": 7}})) == "RECORD_FIELDS"
