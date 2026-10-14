from __future__ import annotations

import dataclasses
import json
import inspect
import math

import pytest

from repeat_fixtures import fake_digest, primary_context, synthetic_plan
from shiftguard.repeats.models import (
    BUDGETS,
    INNER_IDS,
    METHODS,
    OUTER_SEEDS,
    PREDICTORS,
    PRIMARY_SOURCE_METHOD,
    PRIMARY_TARGET_METHOD,
    SCENARIOS,
    ConditionSlot,
    ProbabilityArray,
    RepeatContractError,
    TerminalCondition,
)
from shiftguard.repeats.validation import (
    expected_condition_slots,
    validate_condition_inventory,
    validate_probability_pair,
)


VALID_ROWS = ((0.4, 0.6), (0.25, 0.75), (1.0, 0.0), (0.5, 0.5))


def _code(call) -> str:
    with pytest.raises(RepeatContractError) as raised:
        call()
    return raised.value.code


@pytest.fixture(scope="module")
def plan():
    return synthetic_plan()


@pytest.fixture
def context(plan):
    return primary_context(plan, 41001, 51001, "logistic_regression", "mcar_0_10")


def _pair(context, left_rows=VALID_ROWS, right_rows=VALID_ROWS, left_context=None,
          left_method=PRIMARY_TARGET_METHOD, right_method=PRIMARY_SOURCE_METHOD):
    left = ProbabilityArray(left_context or context, left_method, left_rows)
    right = ProbabilityArray(context, right_method, right_rows)
    return left, right


def test_valid_pair_is_bound_to_its_context_without_labels_or_scores(context):
    left, right = _pair(context)
    validated = validate_probability_pair(left, right, context)
    assert validated.context == context
    assert validated.row_count == 4
    assert len(validated.target_digest) == len(validated.source_digest) == 64
    assert list(inspect.signature(validate_probability_pair).parameters) == ["left", "right", "pair"]
    assert not {"labels", "loss", "brier", "score"} & {
        field.name for field in dataclasses.fields(validated)
    }


def test_row_sums_are_checked_before_any_clipping_or_repair(context):
    near = ((0.40004, 0.6),) + VALID_ROWS[1:]
    left, right = _pair(context, left_rows=near)
    accepted = validate_probability_pair(left, right, context)
    assert left.values == near
    assert accepted.target_digest != accepted.source_digest
    off = ((0.4002, 0.6),) + VALID_ROWS[1:]
    assert _code(lambda: validate_probability_pair(*_pair(context, left_rows=off), context)) == (
        "PROBABILITY_NORMALIZATION"
    )


@pytest.mark.parametrize("bad_row, code", [
    ((math.nan, 0.5), "INVALID_PROBABILITY"),
    ((math.inf, 0.0), "INVALID_PROBABILITY"),
    ((-0.1, 1.1), "INVALID_PROBABILITY"),
    ((1.0000001, 0.0), "INVALID_PROBABILITY"),
    ((True, 0.0), "INVALID_PROBABILITY"),
    (("0.4", 0.6), "INVALID_PROBABILITY"),
    ((0.2, 0.3, 0.5), "PROBABILITY_SHAPE"),
    ((1.0,), "PROBABILITY_SHAPE"),
    ((0.2, 0.2), "PROBABILITY_NORMALIZATION"),
])
def test_invalid_probabilities_are_rejected_not_repaired(context, bad_row, code):
    rows = (bad_row,) + VALID_ROWS[1:]
    assert _code(lambda: validate_probability_pair(*_pair(context, left_rows=rows), context)) == code
    assert _code(lambda: validate_probability_pair(*_pair(context, right_rows=rows), context)) == code


def test_row_count_must_match_the_evaluation_order(context):
    assert _code(
        lambda: validate_probability_pair(*_pair(context, left_rows=VALID_ROWS[:3]), context)
    ) == "PROBABILITY_SHAPE"
    assert _code(lambda: ProbabilityArray(context, PRIMARY_TARGET_METHOD, list(VALID_ROWS))) == (
        "IMMUTABLE_TUPLE"
    )


@pytest.mark.parametrize("field, value", [
    ("test_mask", fake_digest("another-test-mask")),
    ("pool_mask", fake_digest("another-pool-mask")),
    ("acquisition_order", fake_digest("another-order")),
    ("predictor_id", fake_digest("another-predictor")),
    ("seed_map", fake_digest("another-seed-map")),
    ("source_binding", fake_digest("another-source")),
    ("inner", 51002),
    ("release", "fabricated-v2"),
])
def test_mismatched_pair_context_is_rejected_and_named(context, field, value):
    other = dataclasses.replace(context, **{field: value})
    with pytest.raises(RepeatContractError) as raised:
        validate_probability_pair(*_pair(context, left_context=other), context)
    assert raised.value.code == "PAIR_CONTEXT_MISMATCH"
    assert field in str(raised.value)


def test_mismatched_row_order_and_acquired_prefix_are_rejected(plan, context):
    reordered = dataclasses.replace(
        context,
        evaluation_ids=tuple(reversed(context.evaluation_ids)),
        group_map=tuple(reversed(context.group_map)),
    )
    with pytest.raises(RepeatContractError) as raised:
        validate_probability_pair(*_pair(context, left_context=reordered), context)
    assert raised.value.code == "PAIR_CONTEXT_MISMATCH" and "evaluation_ids" in str(raised.value)

    pool = plan.roles(41001).target_pool_ids
    other_prefix = dataclasses.replace(context, acquired_prefix=pool[1:51])
    assert _code(
        lambda: validate_probability_pair(*_pair(context, left_context=other_prefix), context)
    ) == "PAIR_CONTEXT_MISMATCH"


def test_only_the_declared_primary_strategies_budget_and_scenarios_pair(plan, context):
    swapped = _pair(context, left_method=PRIMARY_SOURCE_METHOD, right_method=PRIMARY_TARGET_METHOD)
    assert _code(lambda: validate_probability_pair(*swapped, context)) == "PAIR_METHOD"
    assert _code(
        lambda: validate_probability_pair(*_pair(context, left_method="target_isotonic"), context)
    ) == "PAIR_METHOD"
    assert _code(lambda: ProbabilityArray(context, "invented", VALID_ROWS)) == "UNDECLARED_VALUE"

    pool = plan.roles(41001).target_pool_ids
    other_budget = dataclasses.replace(context, budget=25, acquired_prefix=pool[:25])
    assert _code(
        lambda: validate_probability_pair(*_pair(other_budget), other_budget)
    ) == "PAIR_BUDGET"
    baseline = dataclasses.replace(context, scenario="baseline")
    assert _code(lambda: validate_probability_pair(*_pair(baseline), baseline)) == "PAIR_SCENARIO"


@pytest.mark.parametrize("change, code", [
    ({"outer": True}, "STRICT_INTEGER"),
    ({"budget": 50.0}, "STRICT_INTEGER"),
    ({"budget": 51}, "UNDECLARED_VALUE"),
    ({"outer": 41006}, "UNDECLARED_REPEAT"),
    ({"predictor": "gradient_boosting"}, "UNDECLARED_VALUE"),
    ({"scenario": "mcar_0_50"}, "UNDECLARED_VALUE"),
    ({"group_map": (("synthetic:eval:other", "synthetic-group-a"),)}, "GROUP_MAP"),
    ({"acquired_prefix": ("synthetic:pool:41001:0",)}, "ACQUIRED_PREFIX"),
    ({"test_mask": "short"}, "DIGEST"),
    ({"evaluation_ids": []}, "IMMUTABLE_TUPLE"),
])
def test_pair_context_rejects_malformed_fields(context, change, code):
    assert _code(lambda: dataclasses.replace(context, **change)) == code


def _condition(plan, slot: ConditionSlot, **overrides) -> TerminalCondition:
    values = {
        "condition_id": fake_digest(f"condition:{tuple(slot)}"),
        "repeat_id": plan.repeat(slot.outer_seed, slot.inner_id).repeat_id,
        "outer_seed": slot.outer_seed,
        "inner_id": slot.inner_id,
        "predictor": slot.predictor,
        "scenario": slot.scenario,
        "budget": slot.budget,
        "requested_method": slot.method,
        "resolved_method": slot.method,
        "resolution_counts": ((slot.method, 4),),
        "status": "completed",
        "metrics_available": True,
        "qualification": "qualified",
        "reasons": (),
        "fit_id": fake_digest(f"fit:{tuple(slot)}"),
    }
    values.update(overrides)
    return TerminalCondition(**values)


@pytest.fixture(scope="module")
def full_inventory(plan):
    return tuple(_condition(plan, slot) for slot in expected_condition_slots(plan.spec))


PRIMARY_SLOT = ConditionSlot(41002, 51004, "random_forest", "mcar_0_30", 50, PRIMARY_TARGET_METHOD)
SECONDARY_SLOT = ConditionSlot(41002, 51004, "random_forest", "baseline", 200, "target_beta")


def _replace(inventory, slot, replacement):
    return tuple(
        replacement if ConditionSlot(
            item.outer_seed, item.inner_id, item.predictor, item.scenario,
            item.budget, item.requested_method,
        ) == slot else item
        for item in inventory
    )


def test_expected_grid_is_four_hundred_slots_per_repeat_and_twenty_thousand(plan):
    slots = expected_condition_slots(plan.spec)
    assert len(slots) == len(set(slots)) == 20_000
    assert len(OUTER_SEEDS) * len(INNER_IDS) == 50
    assert len(PREDICTORS) * len(SCENARIOS) * len(BUDGETS) * len(METHODS) == 400
    per_repeat = [slot for slot in slots if (slot.outer_seed, slot.inner_id) == (41001, 51001)]
    assert len(per_repeat) == 400


def test_complete_inventory_is_ready(plan, full_inventory):
    result = validate_condition_inventory(plan, full_inventory)
    assert (result.expected_slots, result.present_slots) == (20_000, 20_000)
    assert result.primary_pairs_required == 400
    assert result.missing == () and result.terminal_failures == ()
    assert result.full_grid_complete is True and result.primary_ready is True
    assert result.missing_evidence is None
    reordered = validate_condition_inventory(plan, tuple(reversed(full_inventory)))
    assert reordered == result


def test_absent_secondary_slot_is_typed_missing_evidence_not_an_error(plan, full_inventory):
    partial = tuple(item for item in full_inventory if item.condition_id != fake_digest(
        f"condition:{tuple(SECONDARY_SLOT)}"
    ))
    result = validate_condition_inventory(plan, partial)
    assert result.missing == (SECONDARY_SLOT,)
    assert result.full_grid_complete is False
    assert result.primary_ready is True
    assert result.missing_evidence.code == "CONDITION_INVENTORY_INCOMPLETE"
    assert result.missing_evidence.missing == (SECONDARY_SLOT,)
    assert result.missing_evidence.primary_estimate is None
    assert result.missing_evidence.interval is None


def test_absent_or_unqualified_primary_condition_blocks_the_primary(plan, full_inventory):
    absent = tuple(item for item in full_inventory if item.condition_id != fake_digest(
        f"condition:{tuple(PRIMARY_SLOT)}"
    ))
    result = validate_condition_inventory(plan, absent)
    assert result.primary_ready is False and result.missing_primary == (PRIMARY_SLOT,)

    for qualification in ("unqualified", "unknown_authority"):
        changed = _replace(full_inventory, PRIMARY_SLOT, _condition(
            plan, PRIMARY_SLOT, qualification=qualification, reasons=("SCI-03 scope not approved",),
        ))
        result = validate_condition_inventory(plan, changed)
        assert result.primary_ready is False and result.full_grid_complete is False
        assert result.unavailable_primary == ((PRIMARY_SLOT, qualification, ("SCI-03 scope not approved",)),)


def test_terminal_failures_are_retained_and_secondary_failure_keeps_primary(plan, full_inventory):
    failed = _condition(
        plan, SECONDARY_SLOT, status="failed", metrics_available=False, resolved_method=None,
        resolution_counts=(), qualification="failed", reasons=("raw prediction failed",), fit_id=None,
    )
    result = validate_condition_inventory(plan, _replace(full_inventory, SECONDARY_SLOT, failed))
    assert result.terminal_failures == ((SECONDARY_SLOT, ("raw prediction failed",)),)
    assert result.present_slots == 20_000 and result.missing == ()
    assert result.full_grid_complete is False and result.primary_ready is True

    primary_failed = _condition(
        plan, PRIMARY_SLOT, status="failed", metrics_available=False, resolved_method=None,
        resolution_counts=(), qualification="failed", reasons=("calibration fit failed",), fit_id=None,
    )
    result = validate_condition_inventory(plan, _replace(full_inventory, PRIMARY_SLOT, primary_failed))
    assert result.primary_ready is False
    assert result.unavailable_primary == ((PRIMARY_SLOT, "failed", ("calibration fit failed",)),)


def test_valid_fallback_keeps_the_requested_strategy_slot(plan, full_inventory):
    fallback = _condition(
        plan, PRIMARY_SLOT, resolved_method="source_temperature",
        resolution_counts=(("source_temperature", 4),),
    )
    result = validate_condition_inventory(plan, _replace(full_inventory, PRIMARY_SLOT, fallback))
    assert result.primary_ready is True and result.full_grid_complete is True
    assert result.fallback_slots == (PRIMARY_SLOT,)


def test_duplicate_extra_and_foreign_conditions_are_rejected(plan, full_inventory):
    assert _code(
        lambda: validate_condition_inventory(plan, full_inventory + (full_inventory[0],))
    ) == "DUPLICATE_CONDITION"
    same_id = _condition(plan, SECONDARY_SLOT, condition_id=full_inventory[0].condition_id)
    assert _code(
        lambda: validate_condition_inventory(plan, _replace(full_inventory, SECONDARY_SLOT, same_id))
    ) == "DUPLICATE_CONDITION"
    for change in ({"requested_method": "invented"}, {"budget": 51}, {"scenario": "mcar_0_50"},
                   {"outer_seed": 41006}):
        slot = ConditionSlot(41001, 51001, "logistic_regression", "baseline", 0, "raw")
        extra = dataclasses.replace(_condition(plan, slot), **change)
        assert _code(
            lambda: validate_condition_inventory(plan, full_inventory[1:] + (extra,))
        ) == "UNEXPECTED_CONDITION"
    foreign = _condition(plan, SECONDARY_SLOT, repeat_id=plan.repeat(41001, 51001).repeat_id)
    assert _code(
        lambda: validate_condition_inventory(plan, _replace(full_inventory, SECONDARY_SLOT, foreign))
    ) == "REPEAT_ID_MISMATCH"
    assert _code(lambda: validate_condition_inventory(plan, list(full_inventory))) == "IMMUTABLE_TUPLE"


@pytest.mark.parametrize("change, code", [
    ({"status": "running"}, "TERMINAL_STATUS"),
    ({"status": "failed"}, "TERMINAL_STATUS"),
    ({"status": "failed", "metrics_available": False, "qualification": "failed"}, "TERMINAL_STATUS"),
    ({"qualification": "probably"}, "QUALIFICATION"),
    ({"metrics_available": 1}, "STRICT_BOOLEAN"),
    ({"budget": True}, "STRICT_INTEGER"),
    ({"reasons": ["text"]}, "IMMUTABLE_TUPLE"),
    ({"condition_id": ""}, "IDENTIFIER"),
])
def test_terminal_condition_rejects_inconsistent_state(plan, change, code):
    assert _code(lambda: _condition(plan, SECONDARY_SLOT, **change)) == code


# ---------------------------------------------------------------- OR-06: terminal accounting

BINNED = "source_fraction_binned_temperature"
BINNED_SLOT = ConditionSlot(41003, 51002, "logistic_regression", "mcar_0_10", 50, BINNED)


def test_inventory_rejects_invalid_resolution_accounting(plan):
    # The review's fixture: all 20,000 declared slots, four evaluation rows per outer repeat,
    # but every condition claims 999,999 resolved rows. It must never read as complete or ready.
    conditions = tuple(
        _condition(plan, slot, resolution_counts=((slot.method, 999_999),))
        for slot in expected_condition_slots(plan.spec)
    )
    assert len(conditions) == 20_000
    with pytest.raises(RepeatContractError) as raised:
        validate_condition_inventory(plan, conditions)
    assert raised.value.code == "RESOLUTION_ACCOUNTING"
    # Individually, too: the plan-bound row count is four, so one inflated slot is enough.
    one = _replace(
        tuple(_condition(plan, slot) for slot in expected_condition_slots(plan.spec)),
        PRIMARY_SLOT, _condition(plan, PRIMARY_SLOT, resolution_counts=((PRIMARY_TARGET_METHOD, 999_999),)),
    )
    assert _code(lambda: validate_condition_inventory(plan, one)) == "RESOLUTION_ACCOUNTING"


@pytest.mark.parametrize("resolved, counts", [
    (PRIMARY_TARGET_METHOD, ((PRIMARY_TARGET_METHOD, 3),)),
    (PRIMARY_TARGET_METHOD, ((PRIMARY_TARGET_METHOD, 5),)),
    ("source_temperature", (("source_temperature", 3),)),
    ("source_temperature", (("source_temperature", 1_000_000),)),
])
def test_completed_condition_must_account_for_exactly_the_plan_row_count(plan, full_inventory, resolved, counts):
    # These tallies are individually valid; they simply do not add up to the four evaluation rows.
    condition = _condition(plan, PRIMARY_SLOT, resolved_method=resolved, resolution_counts=counts)
    assert _code(
        lambda: validate_condition_inventory(plan, _replace(full_inventory, PRIMARY_SLOT, condition))
    ) == "RESOLUTION_ACCOUNTING"


def test_accounting_uses_the_row_count_of_that_conditions_own_outer_repeat():
    plan = synthetic_plan({41002: (2, 3)})  # outer 41002 evaluates five rows, the others four

    def rows(slot):
        return len(plan.roles(slot.outer_seed).evaluation_ids)

    inventory = tuple(
        _condition(plan, slot, resolution_counts=((slot.method, rows(slot)),))
        for slot in expected_condition_slots(plan.spec)
    )
    result = validate_condition_inventory(plan, inventory)
    assert result.full_grid_complete is True and result.primary_ready is True
    other = ConditionSlot(41002, 51001, "logistic_regression", "baseline", 0, "raw")
    wrong = _replace(inventory, other, _condition(plan, other, resolution_counts=(("raw", 4),)))
    assert _code(lambda: validate_condition_inventory(plan, wrong)) == "RESOLUTION_ACCOUNTING"


@pytest.mark.parametrize("counts, code", [
    # duplicate method entries (the same method twice) and out-of-order entries
    ((("raw", 2), ("raw", 2)), "RESOLUTION_ACCOUNTING"),
    ((("target_temperature", 2), ("source_temperature", 2)), "RESOLUTION_ACCOUNTING"),
    # empty or zero-only accounting cannot describe a completed condition
    ((), "RESOLUTION_ACCOUNTING"),
    ((("target_temperature", 0),), "RESOLUTION_ACCOUNTING"),
    ((("source_temperature", 0), ("target_temperature", 0)), "RESOLUTION_ACCOUNTING"),
    ((("target_temperature", True),), "STRICT_INTEGER"),
    ((("target_temperature", -4),), "NEGATIVE_COUNT"),
    ((("target_temperature", 2.0),), "STRICT_INTEGER"),
    ((("invented", 4),), "UNDECLARED_VALUE"),
    ((["target_temperature", 4],), "IMMUTABLE_TUPLE"),
])
def test_completed_condition_rejects_malformed_resolution_entries(plan, counts, code):
    assert _code(lambda: _condition(plan, PRIMARY_SLOT, resolution_counts=counts)) == code


def test_failed_condition_has_no_resolution_counts_or_scored_metrics(plan):
    failed = dict(status="failed", metrics_available=False, qualification="failed",
                  reasons=("calibration fit failed",), fit_id=None)
    assert _condition(plan, PRIMARY_SLOT, resolved_method=None, resolution_counts=(), **failed).resolved_method is None
    # failed-but-resolved, and failed with a count tally, are contradictions
    assert _code(lambda: _condition(plan, PRIMARY_SLOT, resolution_counts=(), **failed)) == (
        "RESOLUTION_ACCOUNTING")
    assert _code(lambda: _condition(
        plan, PRIMARY_SLOT, resolved_method=None, resolution_counts=((PRIMARY_TARGET_METHOD, 4),), **failed
    )) == "RESOLUTION_ACCOUNTING"
    assert _code(lambda: _condition(plan, PRIMARY_SLOT, **failed)) == "RESOLUTION_ACCOUNTING"
    # completed-but-unresolved is the other half of the same contradiction
    assert _code(lambda: _condition(plan, PRIMARY_SLOT, resolved_method=None)) == "RESOLUTION_ACCOUNTING"
    assert _code(lambda: _condition(plan, PRIMARY_SLOT, resolved_method=None, resolution_counts=())) == (
        "TERMINAL_STATUS")


@pytest.mark.parametrize("requested, resolved", [
    ("raw", "source_temperature"),
    ("source_temperature", "target_temperature"),
    ("source_remasked_temperature", "source_fraction_binned_temperature"),
    ("target_isotonic", "target_beta"),          # a sibling, not an ancestor
    ("target_beta", "target_isotonic"),
    ("target_temperature", "source_remasked_temperature"),
    ("source_fraction_binned_temperature", "target_temperature"),
])
def test_forbidden_fallback_edges_are_rejected(plan, requested, resolved):
    slot = ConditionSlot(41001, 51001, "logistic_regression", "baseline", 100, requested)
    assert _code(lambda: _condition(
        plan, slot, resolved_method=resolved, resolution_counts=((resolved, 4),)
    )) == "FORBIDDEN_FALLBACK"


@pytest.mark.parametrize("requested, chain", [
    ("raw", ("raw",)),
    ("target_isotonic", ("target_isotonic", "target_temperature", "source_temperature", "raw")),
    ("target_beta", ("target_beta", "target_platt_logodds", "target_temperature", "source_temperature", "raw")),
    ("source_fraction_binned_temperature", (
        "source_fraction_binned_temperature", "source_remasked_temperature", "source_temperature", "raw")),
])
def test_every_edge_of_a_requested_chain_is_allowed_for_whole_condition_fallbacks(plan, requested, chain):
    from shiftguard.repeats.models import fallback_chain

    assert fallback_chain(requested) == chain
    slot = ConditionSlot(41001, 51001, "logistic_regression", "baseline", 100, requested)
    for resolved in chain:
        assert _condition(plan, slot, resolved_method=resolved, resolution_counts=((resolved, 4),))


def test_only_the_binned_strategy_may_mix_resolutions_and_the_mixture_is_kept(plan, full_inventory):
    mixed_counts = (("source_temperature", 1), ("source_remasked_temperature", 1), (BINNED, 2))
    mixed = _condition(plan, BINNED_SLOT, resolved_method=BINNED, resolution_counts=mixed_counts)
    assert mixed.fallback_rows == 2 and mixed.row_count == 4
    assert mixed.resolution_counts == mixed_counts
    result = validate_condition_inventory(plan, _replace(full_inventory, BINNED_SLOT, mixed))
    assert result.full_grid_complete is True
    # The top-level label says "binned", yet the slot is reported as a fallback slot.
    assert result.fallback_slots == (BINNED_SLOT,)
    clean = _condition(plan, BINNED_SLOT, resolution_counts=((BINNED, 4),))
    assert validate_condition_inventory(plan, _replace(full_inventory, BINNED_SLOT, clean)).fallback_slots == ()
    # No other strategy may claim a mixture; a whole-condition fallback has a single entry.
    for method, counts in (
        ("target_temperature", (("source_temperature", 1), ("target_temperature", 3))),
        ("source_remasked_temperature", (("raw", 1), ("source_temperature", 3))),
        ("target_beta", (("target_temperature", 2), ("target_beta", 2))),
    ):
        slot = ConditionSlot(41001, 51001, "logistic_regression", "baseline", 100, method)
        assert _code(lambda: _condition(
            plan, slot, resolved_method=method, resolution_counts=counts)) == "RESOLUTION_ACCOUNTING"


def test_binned_mixture_is_checked_against_the_binned_chain_only(plan):
    bad = (("raw", 1), (BINNED, 2), ("target_temperature", 1))
    assert _code(lambda: _condition(
        plan, BINNED_SLOT, resolved_method=BINNED, resolution_counts=bad)) == "FORBIDDEN_FALLBACK"
    unordered = ((BINNED, 2), ("raw", 2))
    assert _code(lambda: _condition(
        plan, BINNED_SLOT, resolved_method=BINNED, resolution_counts=unordered)) == "RESOLUTION_ACCOUNTING"
    # A whole-condition fallback of the binned strategy names only its fallback.
    assert _code(lambda: _condition(
        plan, BINNED_SLOT, resolved_method="source_temperature",
        resolution_counts=(("source_temperature", 3), (BINNED, 1)))) == "RESOLUTION_ACCOUNTING"


def test_unavailable_completed_conditions_are_accounted_too(plan, full_inventory):
    unqualified = _condition(
        plan, PRIMARY_SLOT, qualification="unqualified", reasons=("SCI-03 scope not approved",),
        resolution_counts=((PRIMARY_TARGET_METHOD, 7),))
    assert _code(lambda: validate_condition_inventory(
        plan, _replace(full_inventory, PRIMARY_SLOT, unqualified))) == "RESOLUTION_ACCOUNTING"


def test_terminal_condition_canonical_form_round_trips_with_its_accounting(plan):
    mixed = _condition(
        plan, BINNED_SLOT, resolved_method=BINNED,
        resolution_counts=(("source_temperature", 1), (BINNED, 3)))
    stored = json.loads(json.dumps(mixed.to_canonical(), sort_keys=True))
    assert TerminalCondition.from_canonical(stored) == mixed
    failed = _condition(
        plan, PRIMARY_SLOT, status="failed", metrics_available=False, resolved_method=None,
        resolution_counts=(), qualification="failed", reasons=("calibration fit failed",), fit_id=None)
    assert TerminalCondition.from_canonical(json.loads(json.dumps(failed.to_canonical()))) == failed
    # The constructor re-applies every rule: tampered stored accounting cannot be reopened.
    stored["resolution_counts"] = [["source_temperature", 400], [BINNED, 3]]
    assert TerminalCondition.from_canonical(stored).row_count == 403  # the shape is valid ...
    with pytest.raises(RepeatContractError) as raised:  # ... but the plan-bound total is not
        from shiftguard.repeats.validation import validate_condition_accounting

        validate_condition_accounting(plan, TerminalCondition.from_canonical(stored))
    assert raised.value.code == "RESOLUTION_ACCOUNTING"
    for broken in ({**stored, "record_version": "gate8-terminal-condition-v0"},
                   {k: v for k, v in stored.items() if k != "record_version"}):
        assert _code(lambda: TerminalCondition.from_canonical(broken)) == "RECORD_VERSION"
    assert _code(lambda: TerminalCondition.from_canonical(
        {k: v for k, v in stored.items() if k != "fit_id"})) == "RECORD_FIELDS"
