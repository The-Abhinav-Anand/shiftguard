"""Pure validation of paired probabilities and of the terminal condition grid.

No function here accepts labels or computes a metric.
"""

from __future__ import annotations

from functools import lru_cache
import math

from shiftguard.repeats.models import (
    PRIMARY_BUDGET,
    PRIMARY_SCENARIOS,
    PRIMARY_SOURCE_METHOD,
    PRIMARY_TARGET_METHOD,
    ConditionSlot,
    InventoryResult,
    MissingEvidence,
    PairContext,
    ProbabilityArray,
    RepeatContractError,
    RepeatPlan,
    RepeatSpec,
    TerminalCondition,
    ValidatedPair,
    canonical_digest,
    immutable_tuple,
)
from shiftguard.repeats.planning import ensure_planned


# Inherited normalization tolerance; applied before any clipping, never as a repair.
ROW_SUM_TOLERANCE = 1e-4
_PRIMARY_METHODS = (PRIMARY_TARGET_METHOD, PRIMARY_SOURCE_METHOD)


def _validated_rows(array: ProbabilityArray, row_count: int) -> str:
    rows = array.values
    if len(rows) != row_count or row_count < 1:
        raise RepeatContractError("PROBABILITY_SHAPE", array.requested_method)
    for row in rows:
        if type(row) is not tuple or len(row) != 2:
            raise RepeatContractError("PROBABILITY_SHAPE", array.requested_method)
        for value in row:
            if type(value) is not float or not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise RepeatContractError("INVALID_PROBABILITY", array.requested_method)
        if abs(row[0] + row[1] - 1.0) > ROW_SUM_TOLERANCE:
            raise RepeatContractError("PROBABILITY_NORMALIZATION", array.requested_method)
    return canonical_digest([array.requested_method, [list(row) for row in rows]])


def validate_probability_pair(
    left: ProbabilityArray,
    right: ProbabilityArray,
    pair: PairContext,
) -> ValidatedPair:
    """Check that the two primary strategies are comparable on identical rows."""
    if (
        type(left) is not ProbabilityArray
        or type(right) is not ProbabilityArray
        or type(pair) is not PairContext
    ):
        raise RepeatContractError("PAIR_SCHEMA", "left/right/pair")
    for side, array in (("left", left), ("right", right)):
        differing = pair.differing_fields(array.context)
        if differing:
            raise RepeatContractError("PAIR_CONTEXT_MISMATCH", f"{side}: {', '.join(differing)}")
    if (left.requested_method, right.requested_method) != _PRIMARY_METHODS:
        raise RepeatContractError(
            "PAIR_METHOD", f"{left.requested_method} / {right.requested_method}"
        )
    if pair.budget != PRIMARY_BUDGET:
        raise RepeatContractError("PAIR_BUDGET", str(pair.budget))
    if pair.scenario not in PRIMARY_SCENARIOS:
        raise RepeatContractError("PAIR_SCENARIO", pair.scenario)
    row_count = len(pair.evaluation_ids)
    return ValidatedPair(
        context=pair,
        row_count=row_count,
        target_digest=_validated_rows(left, row_count),
        source_digest=_validated_rows(right, row_count),
    )


@lru_cache(maxsize=1)
def expected_condition_slots(spec: RepeatSpec) -> tuple[ConditionSlot, ...]:
    """All 20,000 slots: 400 per repeat across the fifty execution coordinates."""
    return tuple(
        ConditionSlot(outer, inner, predictor, scenario, budget, method)
        for outer in spec.outer_seeds
        for inner in spec.inner_ids
        for predictor in spec.predictors
        for scenario in spec.scenarios
        for budget in spec.budgets
        for method in spec.methods
    )


def is_primary_slot(slot: ConditionSlot) -> bool:
    return (
        slot.budget == PRIMARY_BUDGET
        and slot.scenario in PRIMARY_SCENARIOS
        and slot.method in _PRIMARY_METHODS
    )


def validate_condition_accounting(plan: RepeatPlan, condition: TerminalCondition) -> None:
    """Bind one condition's resolution accounting to the plan's evaluation rows.

    A completed condition accounts for exactly the plan-bound evaluation rows of its outer
    repeat. A failed condition carries no resolution (enforced by the condition itself).
    """
    if type(condition) is not TerminalCondition:
        raise RepeatContractError("REPEAT_SCHEMA", "conditions")
    if condition.status == "failed":
        return
    expected = len(plan.roles(condition.outer_seed).evaluation_ids)
    if condition.row_count != expected:
        raise RepeatContractError(
            "RESOLUTION_ACCOUNTING",
            f"{tuple(condition.slot)}: {condition.row_count} rows accounted, {expected} evaluated",
        )


def validate_condition_inventory(
    plan: RepeatPlan,
    conditions: tuple[TerminalCondition, ...],
) -> InventoryResult:
    """Extra or duplicate cells are errors; absent cells become typed missing evidence."""
    ensure_planned(plan)
    slots = expected_condition_slots(plan.spec)
    expected = set(slots)
    present: dict[ConditionSlot, TerminalCondition] = {}
    condition_ids: set[str] = set()
    for condition in immutable_tuple(conditions, "conditions"):
        if type(condition) is not TerminalCondition:
            raise RepeatContractError("REPEAT_SCHEMA", "conditions")
        slot = condition.slot
        if slot not in expected:
            raise RepeatContractError("UNEXPECTED_CONDITION", repr(tuple(slot)))
        if slot in present or condition.condition_id in condition_ids:
            raise RepeatContractError("DUPLICATE_CONDITION", repr(tuple(slot)))
        if condition.repeat_id != plan.repeat(slot.outer_seed, slot.inner_id).repeat_id:
            raise RepeatContractError("REPEAT_ID_MISMATCH", repr(tuple(slot)))
        validate_condition_accounting(plan, condition)
        present[slot] = condition
        condition_ids.add(condition.condition_id)

    # Results follow the declared grid order, so input order never matters.
    missing, failures, unavailable, unavailable_primary, fallbacks = [], [], [], [], []
    for slot in slots:
        condition = present.get(slot)
        if condition is None:
            missing.append(slot)
            continue
        if condition.status == "failed":
            failures.append((slot, condition.reasons))
        if condition.qualification != "qualified":
            entry = (slot, condition.qualification, condition.reasons)
            unavailable.append(entry)
            if is_primary_slot(slot):
                unavailable_primary.append(entry)
        elif condition.fallback_rows:
            # Any row resolving away from the request counts, including a mixed binned condition.
            fallbacks.append(slot)
    missing_primary = tuple(slot for slot in missing if is_primary_slot(slot))
    complete = not missing and not unavailable
    return InventoryResult(
        expected_slots=len(slots),
        present_slots=len(present),
        primary_pairs_required=sum(map(is_primary_slot, slots)) // len(_PRIMARY_METHODS),
        missing=tuple(missing),
        missing_primary=missing_primary,
        terminal_failures=tuple(failures),
        unavailable_primary=tuple(unavailable_primary),
        fallback_slots=tuple(fallbacks),
        full_grid_complete=complete,
        primary_ready=not missing_primary and not unavailable_primary,
        missing_evidence=None if complete else MissingEvidence(
            code="CONDITION_INVENTORY_INCOMPLETE",
            missing=tuple(missing),
            unavailable=tuple(unavailable),
            reasons=tuple(sorted({reason for _, _, reasons in unavailable for reason in reasons})),
        ),
    )
