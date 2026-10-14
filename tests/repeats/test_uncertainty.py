from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from repeat_fixtures import packet_fixture_sums, primary_cells, synthetic_plan, varied_sums
from shiftguard.repeats.aggregation import prepare_group_sums, weighted_estimate
from shiftguard.repeats.models import MissingEvidence, RepeatContractError
from shiftguard.repeats.uncertainty import (
    IntervalResult,
    UncertaintySpec,
    draw_estimates,
    group_multiplicities,
    paired_group_interval,
)


GROUPS = ("synthetic-group-a", "synthetic-group-b")
PATTERN_VALUES = {(2, 0): 0.2, (1, 1): -0.1, (0, 2): -0.2}


def _code(call) -> str:
    with pytest.raises(RepeatContractError) as raised:
        call()
    return raised.value.code


def _prepared_with_plan(sizes=None, sums_for=packet_fixture_sums):
    plan = synthetic_plan(sizes)
    return plan, prepare_group_sums(plan, primary_cells(plan, sums_for))


def _prepared(sizes=None, sums_for=packet_fixture_sums):
    return _prepared_with_plan(sizes, sums_for)[1]


@pytest.fixture(scope="module")
def plan():
    return synthetic_plan()


@pytest.fixture(scope="module")
def prepared(plan):
    return prepare_group_sums(plan, primary_cells(plan, packet_fixture_sums))


def test_draw_uses_the_declared_namespace_and_one_multiplicity_per_sorted_group():
    spec = UncertaintySpec("fixed_external")
    groups = tuple(f"synthetic-group-{n}" for n in range(7))
    weights = group_multiplicities(groups, 19, spec)
    reference = np.bincount(
        np.random.Generator(np.random.PCG64(np.random.SeedSequence([61001, 8, 1, 19]))).integers(
            0, 7, size=7
        ),
        minlength=7,
    )
    assert weights == tuple(int(value) for value in reference)
    assert sum(weights) == 7 and all(type(value) is int for value in weights)
    assert group_multiplicities(groups, 19, spec) == weights
    assert group_multiplicities(groups, 20, spec) != weights
    assert (spec.draws, spec.root, spec.namespace) == (10_000, 61001, (8, 1))
    assert (spec.quantiles, spec.interpolation) == ((0.025, 0.975), "linear")


@pytest.mark.parametrize("groups, draw_id, code", [
    (("synthetic-group-b", "synthetic-group-a"), 0, "GROUP_ORDER"),
    (("synthetic-group-a", "synthetic-group-a"), 0, "GROUP_ORDER"),
    ((), 0, "GROUP_ORDER"),
    (["synthetic-group-a"], 0, "IMMUTABLE_TUPLE"),
    (GROUPS, True, "DRAW_SCHEMA"),
    (GROUPS, 1.0, "DRAW_SCHEMA"),
    (GROUPS, -1, "DRAW_SCHEMA"),
    (GROUPS, 10_000, "DRAW_SCHEMA"),
])
def test_multiplicity_inputs_are_strict(groups, draw_id, code):
    assert _code(lambda: group_multiplicities(groups, draw_id, UncertaintySpec("fixed_external"))) == code


@pytest.mark.parametrize("change, code", [
    ({"mode": "outer_first"}, "UNCERTAINTY_MODE"),
    ({"draws": 0}, "DRAW_COUNT"),
    ({"draws": True}, "DRAW_COUNT"),
    ({"draws": 100.0}, "DRAW_COUNT"),
    ({"root": 61002}, "UNCERTAINTY_SPEC"),
    ({"namespace": (8, 2)}, "UNCERTAINTY_SPEC"),
    ({"quantiles": (0.05, 0.95)}, "UNCERTAINTY_SPEC"),
    ({"interpolation": "nearest"}, "UNCERTAINTY_SPEC"),
])
def test_uncertainty_spec_admits_only_the_reviewed_procedure(change, code):
    values = {"mode": "fixed_external", **change}
    assert _code(lambda: UncertaintySpec(**values)) == code


def test_enumerated_two_group_draws_reuse_one_weight_for_every_occurrence(plan, prepared):
    spec = UncertaintySpec("fixed_external")
    estimates = draw_estimates(prepared, spec, 0, 200, plan=plan)
    seen = set()
    for estimate in estimates:
        weights = group_multiplicities(GROUPS, estimate.draw_id, spec)
        seen.add(weights)
        assert estimate.value == pytest.approx(PATTERN_VALUES[weights], abs=1e-12)
        assert estimate.value == pytest.approx(weighted_estimate(prepared, weights, plan=plan), abs=1e-12)
    assert seen == set(PATTERN_VALUES)
    assert [estimate.draw_id for estimate in estimates] == list(range(200))


def test_ten_thousand_draw_interval_for_the_packet_fixture(plan, prepared):
    result = paired_group_interval(prepared, UncertaintySpec("fixed_external"), plan=plan)
    assert isinstance(result, IntervalResult)
    assert (result.lower, result.upper) == pytest.approx((-0.2, 0.2), abs=1e-12)
    assert result.point_estimate == pytest.approx(-0.1, abs=1e-12)
    assert (result.mode, result.draws, result.group_count) == ("fixed_external", 10_000, 2)
    assert result.declared_procedure is True and result.degenerate is False
    assert result.hypothesis_decision is None and result.coverage_claim is False
    assert result.synthetic is True
    assert paired_group_interval(prepared, UncertaintySpec("fixed_external"), plan=plan) == result


def test_draws_resume_and_chunk_deterministically(plan, prepared):
    spec = UncertaintySpec("fixed_external", draws=120)
    whole = draw_estimates(prepared, spec, 0, 120, plan=plan)
    assert draw_estimates(prepared, spec, 0, 50, plan=plan) + draw_estimates(
        prepared, spec, 50, 120, plan=plan) == whole
    assert draw_estimates(prepared, spec, 73, 74, plan=plan) == whole[73:74]
    values = [estimate.value for estimate in whole]
    result = paired_group_interval(prepared, spec, plan=plan)
    expected = np.quantile(values, [0.025, 0.975], method="linear")
    assert (result.lower, result.upper) == pytest.approx(tuple(expected), abs=1e-15)
    assert result.draws == 120 and result.declared_procedure is False
    for start, stop in ((-1, 5), (5, 4), (0, 121), (True, 5)):
        assert _code(lambda: draw_estimates(prepared, spec, start, stop, plan=plan)) == "DRAW_SCHEMA"


def test_constant_adverse_effect_gives_a_reported_degenerate_interval():
    plan, prepared = _prepared_with_plan(
        sums_for=lambda _key, counts: tuple(count * 0.125 for count in counts))
    result = paired_group_interval(prepared, UncertaintySpec("fixed_external", draws=100), plan=plan)
    assert (result.lower, result.upper) == (0.125, 0.125)
    assert result.degenerate is True
    # Positive means the target strategy is worse; the evidence is returned, not filtered.
    assert result.lower > 0 and result.hypothesis_decision is None


def test_fixed_external_rejects_changing_evaluation_membership():
    plan, prepared = _prepared_with_plan({41001: (1, 0)})
    assert _code(
        lambda: paired_group_interval(prepared, UncertaintySpec("fixed_external", draws=20), plan=plan)
    ) == "VARYING_EXTERNAL_EVALUATION_MEMBERSHIP"
    resized_plan, resized = _prepared_with_plan({41003: (2, 3)})
    assert _code(
        lambda: paired_group_interval(
            resized, UncertaintySpec("fixed_external", draws=20), plan=resized_plan)
    ) == "VARYING_EXTERNAL_EVALUATION_MEMBERSHIP"


def test_zero_mass_draw_in_bank_overlap_makes_the_interval_unavailable_with_ids_retained():
    plan, prepared = _prepared_with_plan({41001: (1, 0)})
    spec = UncertaintySpec("bank_overlap_diagnostic", draws=20)
    expected_invalid = tuple(
        draw for draw in range(20) if group_multiplicities(GROUPS, draw, spec) == (0, 2)
    )
    assert expected_invalid
    evidence = paired_group_interval(prepared, spec, plan=plan)
    assert isinstance(evidence, MissingEvidence)
    assert evidence.code == "INVALID_DRAWS"
    assert evidence.invalid_draw_ids == expected_invalid
    assert evidence.interval is None and evidence.primary_estimate is None
    estimates = draw_estimates(prepared, spec, 0, 20, plan=plan)
    assert len(estimates) == 20
    assert tuple(e.draw_id for e in estimates if e.value is None) == expected_invalid


def test_bank_overlap_mode_is_a_diagnostic_without_a_coverage_or_hypothesis_claim():
    plan, prepared = _prepared_with_plan({41003: (2, 3)}, sums_for=varied_sums)
    result = paired_group_interval(
        prepared, UncertaintySpec("bank_overlap_diagnostic", draws=400), plan=plan)
    assert isinstance(result, IntervalResult)
    assert result.mode == "bank_overlap_diagnostic"
    assert result.coverage_claim is False and result.hypothesis_decision is None
    assert "diagnostic" in result.claim_scope
    assert result.lower <= result.point_estimate <= result.upper


def test_fewer_than_two_groups_is_unavailable_and_a_detached_massless_group_is_refused(plan, prepared):
    single_plan, single = _prepared_with_plan(
        {outer: (4, 0) for outer in (41001, 41002, 41003, 41004, 41005)})
    assert single.group_ids == ("synthetic-group-a",)
    for mode in ("fixed_external", "bank_overlap_diagnostic"):
        evidence = paired_group_interval(single, UncertaintySpec(mode, draws=20), plan=single_plan)
        assert isinstance(evidence, MissingEvidence) and evidence.code == "INSUFFICIENT_GROUPS"
        assert evidence.interval is None

    # A group with no mass anywhere cannot belong to a validated aggregate: the universe is the
    # union of the plan's evaluation groups, so a detached extra group would be invented.
    massless = dataclasses.replace(
        prepared,
        group_ids=prepared.group_ids + ("synthetic-group-c",),
        counts=tuple(row + (0,) for row in prepared.counts),
        collapsed_sums=tuple(row + (0.0,) for row in prepared.collapsed_sums),
    )
    assert _code(
        lambda: paired_group_interval(massless, UncertaintySpec("fixed_external", draws=20), plan=plan)
    ) == "GROUP_UNIVERSE_MISMATCH"


def test_missing_primary_evidence_passes_through_with_a_null_interval():
    plan = synthetic_plan()
    cells = primary_cells(plan, packet_fixture_sums)[:-1]
    missing = prepare_group_sums(plan, cells)
    result = paired_group_interval(missing, UncertaintySpec("fixed_external", draws=20), plan=plan)
    assert result is missing and result.interval is None


@pytest.mark.parametrize("change, code", [
    ({"synthetic": False}, "SYNTHETIC_ONLY"),
    ({"counts": ((1, 3),) * 4}, "PREPARED_SHAPE"),
    ({"counts": ((1, True),) * 5}, "STRICT_INTEGER"),
    ({"counts": ((1, -3),) * 5}, "NEGATIVE_COUNT"),
    ({"collapsed_sums": ((0.2, float("nan")),) * 5}, "INVALID_GROUP_SUM"),
    ({"collapsed_sums": ((0.2,),) * 5}, "PREPARED_SHAPE"),
    ({"group_ids": ("synthetic-group-b", "synthetic-group-a")}, "GROUP_ORDER"),
])
def test_interval_rejects_malformed_or_non_synthetic_prepared_sums(plan, prepared, change, code):
    broken = dataclasses.replace(prepared, **change)
    assert _code(
        lambda: paired_group_interval(broken, UncertaintySpec("fixed_external", draws=20), plan=plan)
    ) == code


# ---------------------------------------------------------------- OR-04 / OR-05 regressions

import hashlib  # noqa: E402
import inspect  # noqa: E402

from repeat_fixtures import synthetic_binding, synthetic_roles  # noqa: E402
from shiftguard.repeats.aggregation import (  # noqa: E402
    derived_point_estimate,
    validate_prepared_aggregate,
)
from shiftguard.repeats.models import OUTER_SEEDS, RepeatSpec, canonical_digest  # noqa: E402
from shiftguard.repeats.planning import plan_repeats  # noqa: E402


def _all_entry_points(prepared, plan):
    spec = UncertaintySpec("fixed_external", draws=10)
    return {
        "validate": lambda: validate_prepared_aggregate(prepared, plan),
        "weighted": lambda: weighted_estimate(prepared, (1, 1), plan=plan),
        "draws": lambda: draw_estimates(prepared, spec, 0, 3, plan=plan),
        "interval": lambda: paired_group_interval(prepared, spec, plan=plan),
    }


def test_the_entry_points_require_a_plan_keyword(plan, prepared):
    for function in (weighted_estimate, draw_estimates, paired_group_interval):
        parameter = inspect.signature(function).parameters["plan"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is parameter.empty
    with pytest.raises(TypeError):
        paired_group_interval(prepared, UncertaintySpec("fixed_external", draws=10))  # type: ignore[call-arg]
    assert validate_prepared_aggregate(prepared, plan) is None


def test_valid_aggregate_membership_and_point_are_derived_from_the_plan(plan, prepared):
    assert prepared.membership_by_outer == tuple(plan.roles(o).group_map for o in OUTER_SEEDS)
    assert all(type(pair) is tuple for pairs in prepared.membership_by_outer for pair in pairs)
    assert prepared.point_estimate == pytest.approx(-0.1, abs=1e-12)
    assert prepared.point_estimate == derived_point_estimate(prepared.counts, prepared.collapsed_sums)


@pytest.mark.parametrize("name, change, code", [
    # The review's exact reproduction: impossible sums and a made-up point estimate.
    ("probe", {"collapsed_sums": ((1000.0, 1000.0),) * 5, "point_estimate": 999.0}, "INVALID_GROUP_SUM"),
    ("sums only", {"collapsed_sums": ((1000.0, 1000.0),) * 5}, "INVALID_GROUP_SUM"),
    ("just above a bound", {"collapsed_sums": ((1.0000000005, 0.0),) * 5}, "INVALID_GROUP_SUM"),
    ("just below a bound", {"collapsed_sums": ((0.0, -3.0000000005),) * 5}, "INVALID_GROUP_SUM"),
    ("infinite sum", {"collapsed_sums": ((math.inf, 0.0),) * 5}, "INVALID_GROUP_SUM"),
    ("integer sum", {"collapsed_sums": ((1, 0.0),) * 5}, "INVALID_GROUP_SUM"),
    ("tampered point estimate", {"point_estimate": 999.0}, "POINT_ESTIMATE_MISMATCH"),
    ("slightly tampered point", {"point_estimate": -0.1000001}, "POINT_ESTIMATE_MISMATCH"),
    ("integer point", {"point_estimate": 0}, "POINT_ESTIMATE_MISMATCH"),
    ("int64 overflow count", {"counts": ((2**63, 3),) * 5}, "COUNT_OVERFLOW"),
    ("huge python int count", {"counts": ((1, 10**40),) * 5}, "COUNT_OVERFLOW"),
    ("count beyond exact float range", {"counts": ((1, 2**53),) * 5}, "COUNT_OVERFLOW"),
    ("counts disagree with membership", {"counts": ((2, 2),) * 5}, "GROUP_COUNT_MISMATCH"),
    ("zero row mass in one outer", {"counts": ((0, 0),) + ((1, 3),) * 4}, "GROUP_COUNT_MISMATCH"),
    ("float count", {"counts": ((1.0, 3),) * 5}, "STRICT_INTEGER"),
    ("bool count", {"counts": ((1, True),) * 5}, "STRICT_INTEGER"),
    ("foreign plan digest", {"plan_digest": "0" * 64}, "PLAN_DIGEST_MISMATCH"),
    ("altered claim scope", {"claim_scope": "confirmatory"}, "CLAIM_SCOPE"),
    ("not synthetic", {"synthetic": False}, "SYNTHETIC_ONLY"),
    ("duplicate group ids", {"group_ids": ("synthetic-group-a", "synthetic-group-a")}, "GROUP_ORDER"),
    ("other group ids", {"group_ids": ("synthetic-group-a", "synthetic-group-z")}, "GROUP_UNIVERSE_MISMATCH"),
    ("membership with a swapped group", {}, "MEMBERSHIP_MISMATCH"),
    ("membership list", {"membership_by_outer": []}, "IMMUTABLE_TUPLE"),
    ("membership too short", {"membership_by_outer": ()}, "PREPARED_SHAPE"),
    ("malformed pair", {"membership_by_outer": ((("a",),),) * 5}, "MEMBERSHIP_SCHEMA"),
])
def test_rejects_impossible_prepared_aggregate(plan, prepared, name, change, code):
    change = dict(change)
    if name == "membership with a swapped group":
        first = list(prepared.membership_by_outer[0])
        first[1] = (first[1][0], first[0][1])
        change["membership_by_outer"] = (tuple(first),) + prepared.membership_by_outer[1:]
    broken = dataclasses.replace(prepared, **change)
    # No interval, estimate or draw is produced by any entry point: each raises the same error.
    for entry, call in _all_entry_points(broken, plan).items():
        assert _code(call) == code, entry


def test_a_forged_or_foreign_plan_cannot_validate_an_aggregate(plan, prepared):
    forged = dataclasses.replace(plan, plan_digest="0" * 64)
    other_plan = synthetic_plan({41002: (2, 2)})
    assert _code(lambda: validate_prepared_aggregate(prepared, forged)) == "PLAN_INTEGRITY"
    assert _code(lambda: validate_prepared_aggregate(prepared, other_plan)) == "PLAN_DIGEST_MISMATCH"
    assert _code(lambda: validate_prepared_aggregate(None, plan)) == "REPEAT_SCHEMA"  # type: ignore[arg-type]
    assert _code(lambda: validate_prepared_aggregate(prepared, None)) == "REPEAT_SCHEMA"  # type: ignore[arg-type]


def test_absent_group_has_exactly_zero_sum_and_exact_extrema_are_legal_without_clipping():
    plan, prepared = _prepared_with_plan({41001: (1, 0)})
    assert prepared.counts[0] == (1, 0) and prepared.collapsed_sums[0][1] == 0.0
    nonzero = dataclasses.replace(
        prepared, collapsed_sums=((0.2, 1e-12),) + prepared.collapsed_sums[1:])
    assert _code(lambda: validate_prepared_aggregate(nonzero, plan)) == "INVALID_GROUP_SUM"
    # Exactly +/- count is a legal extreme; nothing is clipped or widened to allow it.
    sums = ((1.0, 0.0),) + ((1.0, -3.0),) * 4
    extremes = dataclasses.replace(
        prepared, collapsed_sums=sums, point_estimate=derived_point_estimate(prepared.counts, sums))
    assert validate_prepared_aggregate(extremes, plan) is None
    assert extremes.collapsed_sums[1] == (1.0, -3.0)
    assert extremes.point_estimate == pytest.approx((1.0 + 4 * (-2.0 / 4)) / 5, abs=1e-12)


def test_caller_weights_are_validated_before_any_arithmetic(plan, prepared):
    for weights in ((1,), (1, 2, 3), (True, 1), (1.0, 1), (-1, 1), (2**63, 1), (10**400, 1), (2**53 + 1, 1)):
        assert _code(lambda: weighted_estimate(prepared, weights, plan=plan)) == "MULTIPLICITY_SCHEMA", weights
    # The largest permitted weights keep exact integer denominators and a finite estimate.
    assert weighted_estimate(prepared, (2**53, 2**53), plan=plan) == pytest.approx(-0.1, abs=1e-12)
    assert weighted_estimate(prepared, (0, 0), plan=plan) is None
    assert weighted_estimate(prepared, (0, 2**53), plan=plan) == pytest.approx(-0.2, abs=1e-12)


def _plan_with_evaluation(ids_for_outer, groups_for_outer=None, group_sizes=(1, 3)):
    roles = []
    for outer in OUTER_SEEDS:
        ids = tuple(ids_for_outer(outer))
        overrides = {"evaluation_ids": ids, "evaluation_order_digest": canonical_digest(list(ids))}
        if groups_for_outer is not None:
            overrides["evaluation_groups"] = tuple(groups_for_outer(outer))
        roles.append(synthetic_roles(outer, group_sizes, **overrides))
    return plan_repeats(RepeatSpec(), synthetic_binding(), tuple(roles))


def test_fixed_external_requires_identical_row_membership():
    # The review's reproduction: five different cohorts with the same groups and the same counts.
    plan = _plan_with_evaluation(lambda outer: (f"outer:{outer}:{i}" for i in range(4)))
    prepared = prepare_group_sums(plan, primary_cells(plan, packet_fixture_sums))
    assert len({plan.roles(o).evaluation_ids for o in OUTER_SEEDS}) == 5
    assert len(set(prepared.counts)) == 1
    spec = UncertaintySpec("fixed_external", draws=10)
    assert _code(lambda: paired_group_interval(prepared, spec, plan=plan)) == (
        "VARYING_EXTERNAL_EVALUATION_MEMBERSHIP"
    )
    # Bank overlap keeps differing cohorts and its explicit nonconfirmatory label.
    diagnostic = paired_group_interval(
        prepared, UncertaintySpec("bank_overlap_diagnostic", draws=50), plan=plan)
    assert isinstance(diagnostic, IntervalResult)
    assert diagnostic.mode == "bank_overlap_diagnostic" and "diagnostic" in diagnostic.claim_scope
    assert diagnostic.coverage_claim is False and diagnostic.hypothesis_decision is None


def test_fixed_external_rejects_changed_grouping_with_identical_row_ids():
    same_ids = lambda outer: (f"fixed:{i}" for i in range(4))
    # Identical row IDs and identical group counts (1, 3), but outer 41003 regroups its rows.
    regroup = lambda outer: (
        ("synthetic-group-b", "synthetic-group-a", "synthetic-group-b", "synthetic-group-b")
        if outer == 41003 else
        ("synthetic-group-a", "synthetic-group-b", "synthetic-group-b", "synthetic-group-b")
    )
    plan = _plan_with_evaluation(same_ids, regroup)
    assert len({plan.roles(o).evaluation_ids for o in OUTER_SEEDS}) == 1
    assert len({plan.group_counts(o) for o in OUTER_SEEDS}) == 1
    prepared = prepare_group_sums(plan, primary_cells(plan, packet_fixture_sums))
    assert _code(
        lambda: paired_group_interval(prepared, UncertaintySpec("fixed_external", draws=10), plan=plan)
    ) == "VARYING_EXTERNAL_EVALUATION_MEMBERSHIP"
    assert isinstance(
        paired_group_interval(prepared, UncertaintySpec("bank_overlap_diagnostic", draws=10), plan=plan),
        IntervalResult)


def test_fixed_external_accepts_one_cohort_in_a_different_row_order():
    groups = {0: "synthetic-group-a", 1: "synthetic-group-b", 2: "synthetic-group-b", 3: "synthetic-group-b"}
    order = lambda outer: (3, 1, 0, 2) if outer == 41004 else (0, 1, 2, 3)
    plan = _plan_with_evaluation(
        lambda outer: (f"fixed:{i}" for i in order(outer)),
        lambda outer: (groups[i] for i in order(outer)),
    )
    prepared = prepare_group_sums(plan, primary_cells(plan, packet_fixture_sums))
    result = paired_group_interval(prepared, UncertaintySpec("fixed_external", draws=20), plan=plan)
    assert isinstance(result, IntervalResult) and result.mode == "fixed_external"


def test_tampered_membership_is_rejected_in_every_mode(plan, prepared):
    swapped = list(prepared.membership_by_outer[2])
    swapped[0], swapped[1] = swapped[1], swapped[0]
    broken = dataclasses.replace(
        prepared,
        membership_by_outer=prepared.membership_by_outer[:2] + (tuple(swapped),)
        + prepared.membership_by_outer[3:],
    )
    for mode in ("fixed_external", "bank_overlap_diagnostic"):
        assert _code(
            lambda: paired_group_interval(broken, UncertaintySpec(mode, draws=10), plan=plan)
        ) == "MEMBERSHIP_MISMATCH"


def test_large_group_counts_keep_exact_arithmetic_and_cannot_overflow():
    sizes = {outer: (1_500, 2_500) for outer in OUTER_SEEDS}
    plan, prepared = _prepared_with_plan(sizes, sums_for=lambda _key, counts: (0.2 * counts[0], -0.6 * counts[1]))
    assert prepared.counts[0] == (1_500, 2_500)
    result = paired_group_interval(prepared, UncertaintySpec("fixed_external", draws=30), plan=plan)
    assert isinstance(result, IntervalResult)
    assert result.point_estimate == pytest.approx((0.2 * 1_500 - 0.6 * 2_500) / 4_000, abs=1e-9)
    assert -1.0 <= result.lower <= result.upper <= 1.0
    # A tampered count near the integer limits is refused before NumPy sees it.
    broken = dataclasses.replace(prepared, counts=((2**62, 1),) + prepared.counts[1:])
    assert _code(lambda: paired_group_interval(
        broken, UncertaintySpec("fixed_external", draws=10), plan=plan)) == "COUNT_OVERFLOW"


def test_chunked_draws_remain_identical_after_validation(plan, prepared):
    spec = UncertaintySpec("bank_overlap_diagnostic", draws=90)
    whole = draw_estimates(prepared, spec, 0, 90, plan=plan)
    pieces = ()
    for start in range(0, 90, 7):
        pieces += draw_estimates(prepared, spec, start, min(start + 7, 90), plan=plan)
    assert pieces == whole
    assert [e.draw_id for e in whole] == list(range(90))
    assert hashlib.sha256(repr(whole).encode()).hexdigest() == hashlib.sha256(repr(pieces).encode()).hexdigest()


def test_chunked_draws_apply_the_fixed_external_cohort_rule_too():
    plan = _plan_with_evaluation(lambda outer: (f"outer:{outer}:{i}" for i in range(4)))
    prepared = prepare_group_sums(plan, primary_cells(plan, packet_fixture_sums))
    assert _code(lambda: draw_estimates(
        prepared, UncertaintySpec("fixed_external", draws=10), 0, 5, plan=plan)
    ) == "VARYING_EXTERNAL_EVALUATION_MEMBERSHIP"
    diagnostic = draw_estimates(
        prepared, UncertaintySpec("bank_overlap_diagnostic", draws=10), 0, 5, plan=plan)
    assert [e.draw_id for e in diagnostic] == [0, 1, 2, 3, 4]
