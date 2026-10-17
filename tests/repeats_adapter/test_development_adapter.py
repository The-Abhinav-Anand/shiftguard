"""Development-tier adapter: one (outer, inner) coordinate on fabricated Bank-shaped rows.

These tests need the real splitter, predictors, calibrators and evaluator, so they live
outside tests/repeats, whose autouse tripwires forbid exactly those paths. Nothing here
reads var/datasets, a real Bank file or any Adult file.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from development_fixtures import (
    Lab,
    development_standin_binding,
    development_standin_dataset,
    fabricated_bank_dataset,
    fabricated_binding,
    pin_verified_bank,
)
from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.protocol.splits import make_role_splits
from shiftguard.repeats import development_adapter as adapter
from shiftguard.repeats import planning as adapter_planning
from shiftguard.repeats.aggregation import PrimarySummary, aggregate_primary, prepare_group_sums
from shiftguard.repeats.models import (
    BUDGETS,
    EXPOSURE_STATUSES,
    INNER_IDS,
    METHODS,
    OUTER_SEEDS,
    PREDICTORS,
    PRIMARY_BUDGET,
    PRIMARY_SCENARIOS,
    PRIMARY_SOURCE_METHOD,
    PRIMARY_TARGET_METHOD,
    SCENARIOS,
    BANK_DEVELOPMENT_CLAIM_SCOPE,
    SCI03_UNRESOLVED_REASON,
    SYNTHETIC_CLAIM_SCOPE,
    MissingEvidence,
    PairedGroupLossCell,
    RepeatContractError,
    RepeatKey,
    RepeatSpec,
    TerminalCondition,
    canonical_digest,
)
from shiftguard.repeats.seeds import derive_repeat_seed_map
from shiftguard.repeats.validation import expected_condition_slots, validate_condition_inventory
from shiftguard.calibration.sklearn_maps import CalibrationFit, PredictionResolution
from shiftguard.calibration.base import CalibrationRecord


OUTER = OUTER_SEEDS[0]
INNER_A, INNER_B = INNER_IDS[0], INNER_IDS[1]
FAST = {"scenarios": ("baseline", "history_block_0_50"), "budgets": (0, 50)}
PRIMARY_ONLY = {"scenarios": PRIMARY_SCENARIOS, "budgets": (PRIMARY_BUDGET,), "methods": (
    PRIMARY_SOURCE_METHOD, PRIMARY_TARGET_METHOD,
)}
OTHER_STATUSES = tuple(status for status in EXPOSURE_STATUSES if status != "synthetic_fabricated")


@pytest.fixture(scope="module")
def lab() -> Lab:
    return Lab()


@pytest.fixture(scope="module")
def _dev_lab_cache() -> Lab:
    """Built once under a scoped pin that is undone before any test runs."""
    dataset = development_standin_dataset()
    with pytest.MonkeyPatch.context() as patch:
        pin_verified_bank(patch, development_standin_binding(dataset))
        return Lab(dataset, development=True)


@pytest.fixture
def dev_lab(_dev_lab_cache, monkeypatch) -> Lab:
    """The stand-in for the verified Bank release, pinned for this one test only."""
    pin_verified_bank(monkeypatch, _dev_lab_cache.binding)
    return _dev_lab_cache


def _code(call) -> str:
    with pytest.raises(RepeatContractError) as caught:
        call()
    return caught.value.code


def _seeds(outer: int, inner: int) -> dict[str, int]:
    return dict(derive_repeat_seed_map(RepeatKey(outer, inner), RepeatSpec()).seeds)


def _contexts_by_cell(result):
    return {(c.predictor, c.scenario, c.budget): c for c in result.contexts}


# ---------------------------------------------------------------- grouping and roles

def test_feature_group_id_is_the_label_blind_canonical_digest(lab):
    schema = lab.binding.feature_schema_sha256
    row = {name: "x" for name in BANK_FEATURES}
    row["job"] = "unknown"
    expected = canonical_digest(["gate8-feature-group-v1", schema, ["x" if n != "job" else "unknown"
                                                                     for n in BANK_FEATURES]])
    assert adapter.feature_group_id({**row, "row_id": 7, "y": 0}, schema) == expected
    # Row ID and label never enter the key; a literal sentinel stays a distinct value.
    assert adapter.feature_group_id({**row, "row_id": 9, "y": 1}, schema) == expected
    assert adapter.feature_group_id({**row, "job": None}, schema) != expected
    assert adapter.feature_group_id({**row, "job": "Unknown"}, schema) != expected
    assert adapter.feature_group_id(row, "0" * 64) != expected


def test_feature_group_id_rejects_non_token_values(lab):
    row = {name: "x" for name in BANK_FEATURES}
    assert _code(lambda: adapter.feature_group_id({**row, "age": 30}, lab.binding.feature_schema_sha256)) \
        == "FEATURE_TOKEN"


def test_fabricated_data_has_duplicate_groups_with_conflicting_labels(lab):
    schema = lab.binding.feature_schema_sha256
    members: dict[str, list[int]] = {}
    for row in lab.dataset.rows:
        members.setdefault(adapter.feature_group_id(row, schema), []).append(row["y"])
    assert len(members) < len(lab.dataset.rows) // 2
    assert any(len(set(labels)) == 2 for labels in members.values())


def test_outer_roles_follow_the_legacy_split_with_the_derived_split_seed(lab):
    schema = lab.binding.feature_schema_sha256
    groups = {int(r["row_id"]): adapter.feature_group_id(r, schema) for r in lab.dataset.rows}
    for outer in OUTER_SEEDS:
        manifest = lab.plan.roles(outer)
        seeds = _seeds(outer, INNER_A)
        legacy = make_role_splits(lab.dataset.rows, seeds["split"])
        qualify = lambda ids: tuple(adapter.source_row_id(lab.binding, i) for i in ids)
        assert manifest.train_ids == qualify(legacy["train"])
        assert manifest.source_cal_ids == qualify(legacy["source_cal"])
        assert manifest.target_pool_ids == qualify(legacy["target_pool"])
        assert manifest.evaluation_ids == qualify(legacy["final_test"])
        assert manifest.evaluation_groups == tuple(groups[i] for i in legacy["final_test"])
        assert manifest.support_status == "supported"
        assert manifest.split_profile == "bank_overlap_diagnostic"
        assert seeds["split_stage_2"] == seeds["split"] + 1 and seeds["split_stage_3"] == seeds["split"] + 2
        # Roles differ between outer repeats because the split stream does.
    assert len({lab.plan.roles(o).digest for o in OUTER_SEEDS}) == len(OUTER_SEEDS)


def test_plan_is_the_reviewed_fifty_coordinate_plan(lab):
    assert len(lab.plan.repeats) == 50
    assert lab.plan.binding.exposure_status == "synthetic_fabricated"


# ---------------------------------------------------------------- determinism and sharing

def test_one_coordinate_replays_bit_identically_from_a_fresh_preparation(lab):
    first = adapter.execute_coordinate(
        adapter.prepare_outer(lab.dataset, lab.plan, OUTER), INNER_A, **FAST)
    second = adapter.execute_coordinate(
        adapter.prepare_outer(lab.dataset, lab.plan, OUTER), INNER_A, **FAST)
    assert first == second
    assert first.repeat_id == lab.plan.repeat(OUTER, INNER_A).repeat_id
    assert first.seed_map == lab.plan.repeat(OUTER, INNER_A).seed_map
    assert first.claim_scope == SYNTHETIC_CLAIM_SCOPE and first.execution_tier == "development"
    assert [c.slot for c in first.conditions] == [
        s for s in expected_condition_slots(lab.spec)
        if (s.outer_seed, s.inner_id) == (OUTER, INNER_A)
        and s.scenario in FAST["scenarios"] and s.budget in FAST["budgets"]
    ]


def test_outer_split_and_models_are_shared_while_inner_streams_differ(lab):
    a_seeds, b_seeds = _seeds(OUTER, INNER_A), _seeds(OUTER, INNER_B)
    shared = ("split", "model", "model_logistic_regression", "model_random_forest")
    inner = ("mask", "pool_block", "test_block", "pool_mcar", "test_mcar",
             "acquisition", "source_remask", "source_mcar", "source_block")
    assert all(a_seeds[name] == b_seeds[name] for name in shared)
    assert all(a_seeds[name] != b_seeds[name] for name in inner)

    a, b = lab.run(OUTER, INNER_A, **FAST), lab.run(OUTER, INNER_B, **FAST)
    ca, cb = _contexts_by_cell(a), _contexts_by_cell(b)
    assert ca.keys() == cb.keys()
    for cell, context_a in ca.items():
        context_b = cb[cell]
        assert context_a.evaluation_ids == context_b.evaluation_ids
        assert context_a.group_map == context_b.group_map
        assert context_a.predictor_id == context_b.predictor_id
        assert context_a.seed_map != context_b.seed_map
        assert context_a.acquisition_order != context_b.acquisition_order
        assert context_a.pool_mask != context_b.pool_mask or cell[1] == "baseline"
        assert (context_a.test_mask != context_b.test_mask) == (cell[1] != "baseline")
    # The acquisition order is inner-specific; the pool it permutes is not.
    assert a.acquisition_order != b.acquisition_order
    assert sorted(a.acquisition_order) == sorted(b.acquisition_order)
    fits_a = {(c.predictor, c.scenario, c.budget, c.requested_method): c.fit_id for c in a.conditions}
    fits_b = {(c.predictor, c.scenario, c.budget, c.requested_method): c.fit_id for c in b.conditions}
    for predictor in PREDICTORS:
        for method in ("raw", "source_temperature"):
            assert fits_a[(predictor, "baseline", 50, method)] == fits_b[(predictor, "baseline", 50, method)]
        for method in ("source_remasked_temperature", "source_fraction_binned_temperature"):
            assert fits_a[(predictor, "baseline", 50, method)] != fits_b[(predictor, "baseline", 50, method)]


def test_masks_are_shared_within_a_scenario_and_distinct_between_partitions(lab):
    result = lab.run(OUTER, INNER_A, **FAST)
    by_scenario: dict[str, set[tuple[str, str]]] = {}
    for context in result.contexts:
        by_scenario.setdefault(context.scenario, set()).add((context.test_mask, context.pool_mask))
    # Every predictor and budget of a scenario sees the identical test and pool mask.
    assert all(len(masks) == 1 for masks in by_scenario.values())
    (test_masked, pool_masked), = by_scenario["history_block_0_50"]
    (test_clean, pool_clean), = by_scenario["baseline"]
    assert len({test_masked, pool_masked, test_clean, pool_clean}) == 4


def test_source_remask_children_come_from_the_seed_map(lab):
    seeds = _seeds(OUTER, INNER_A)
    children = np.random.default_rng(seeds["source_remask"]).integers(0, 1_000_000, size=2)
    assert (int(children[0]), int(children[1])) == (seeds["source_mcar"], seeds["source_block"])


# ---------------------------------------------------------------- acquisition

def test_budgets_are_nested_prefixes_of_one_label_blind_order(lab):
    result = lab.run(OUTER, INNER_A, scenarios=("baseline", "mcar_matched_history"),
                     budgets=BUDGETS, methods=("raw",))
    manifest = lab.plan.roles(OUTER)
    order = result.acquisition_order
    assert sorted(order) == sorted(manifest.target_pool_ids)
    # The order is exactly the seeded permutation of the sorted pool, not a label-dependent one.
    pool = sorted(int(identifier.rsplit(":", 1)[1]) for identifier in manifest.target_pool_ids)
    permuted = np.random.default_rng(_seeds(OUTER, INNER_A)["acquisition"]).permutation(pool)
    assert order == tuple(adapter.source_row_id(lab.binding, int(i)) for i in permuted)
    contexts = _contexts_by_cell(result)
    assert {c.acquisition_order for c in result.contexts} == {canonical_digest(
        ["gate8-acquisition-order-v1", list(order)])}
    for predictor in PREDICTORS:
        for scenario in ("baseline", "mcar_matched_history"):
            prefixes = [contexts[(predictor, scenario, budget)].acquired_prefix for budget in BUDGETS]
            assert prefixes == [order[:budget] for budget in BUDGETS]
    for smaller, larger in zip(BUDGETS, BUDGETS[1:]):
        assert order[:larger][:smaller] == order[:smaller]


def test_acquired_prefixes_never_touch_evaluation_rows(lab):
    result = lab.run(OUTER, INNER_A, **FAST)
    evaluation = set(lab.plan.roles(OUTER).evaluation_ids)
    assert all(not evaluation.intersection(c.acquired_prefix) for c in result.contexts)


# ---------------------------------------------------------------- pairs and cells

def test_both_primary_strategies_are_validated_on_one_identical_context(lab, monkeypatch):
    seen = []
    original = adapter.validate_probability_pair

    def spy(left, right, pair):
        seen.append((left, right, pair))
        return original(left, right, pair)

    monkeypatch.setattr(adapter, "validate_probability_pair", spy)
    result = adapter.execute_coordinate(lab.prepared(OUTER), INNER_A, **PRIMARY_ONLY)
    assert len(seen) == len(result.pair_cells) == len(PREDICTORS) * len(PRIMARY_SCENARIOS)
    for left, right, pair in seen:
        assert left.context == right.context == pair
        assert (left.requested_method, right.requested_method) == (
            PRIMARY_TARGET_METHOD, PRIMARY_SOURCE_METHOD)
    for cell, validated in zip(result.pair_cells, result.validated_pairs):
        assert validated.context == cell.context
        assert validated.row_count == len(lab.plan.roles(OUTER).evaluation_ids)
        assert validated.target_digest != validated.source_digest
        assert cell.context.budget == PRIMARY_BUDGET
        assert cell.context in result.contexts


def test_primary_conditions_share_everything_but_the_requested_method(lab):
    result = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    for cell in result.pair_cells:
        target = next(c for c in result.conditions if c.condition_id == cell.target_condition_id)
        source = next(c for c in result.conditions if c.condition_id == cell.source_condition_id)
        assert (target.requested_method, source.requested_method) == (
            PRIMARY_TARGET_METHOD, PRIMARY_SOURCE_METHOD)
        for name in ("repeat_id", "outer_seed", "inner_id", "predictor", "scenario", "budget"):
            assert getattr(target, name) == getattr(source, name)
        assert target.condition_id != source.condition_id
        assert target.resolved_method == cell.target_resolved_method
        assert source.resolved_method == cell.source_resolved_method


def test_group_sums_are_bounded_by_counts_and_match_independent_arithmetic(lab, monkeypatch):
    captured = {}
    original = adapter.predict_conditions_with_fallback

    def spy(fits, graph, rows, injected_fractions=None):
        resolutions, attempts = original(fits, graph, rows, injected_fractions=injected_fractions)
        captured.setdefault("calls", []).append({
            m: None if r.probabilities is None else tuple(r.probabilities)
            for m, r in resolutions.items()})
        return resolutions, attempts

    monkeypatch.setattr(adapter, "predict_conditions_with_fallback", spy)
    result = adapter.execute_coordinate(lab.prepared(OUTER), INNER_B, **PRIMARY_ONLY)
    manifest = lab.plan.roles(OUTER)
    labels = {adapter.source_row_id(lab.binding, r["row_id"]): r["y"] for r in lab.dataset.rows}
    y = np.array([labels[i] for i in manifest.evaluation_ids], dtype=float)
    groups = np.array(manifest.evaluation_groups)
    # One resolution call per predictor x scenario at the single budget, in execution order.
    assert len(captured["calls"]) == len(result.pair_cells)
    for cell, probabilities in zip(result.pair_cells, captured["calls"]):
        assert cell.qualification == "qualified" and cell.reasons == ()
        assert cell.group_ids == lab.plan.group_universe
        assert cell.n_by_group == lab.plan.group_counts(OUTER)
        assert sum(cell.n_by_group) == len(manifest.evaluation_ids)
        target = np.array(probabilities[PRIMARY_TARGET_METHOD])
        source = np.array(probabilities[PRIMARY_SOURCE_METHOD])
        difference = (target - y) ** 2 - (source - y) ** 2
        for group, count, total in zip(cell.group_ids, cell.n_by_group, cell.paired_loss_sum_by_group):
            assert type(total) is float and abs(total) <= count
            expected = float(difference[groups == group].sum()) if count else 0.0
            assert total == pytest.approx(expected, abs=1e-10)
            if count == 0:
                assert total == 0.0


def test_all_four_hundred_primary_cells_are_accepted_by_the_aggregators(lab):
    cells: list[PairedGroupLossCell] = []
    for outer in OUTER_SEEDS:
        for inner in INNER_IDS:
            cells.extend(lab.run(outer, inner, **PRIMARY_ONLY).pair_cells)
    assert len(cells) == 400
    summary = aggregate_primary(lab.plan, tuple(cells))
    assert isinstance(summary, PrimarySummary), summary
    assert summary.cell_count == 400 and summary.execution_coordinates == 50
    assert summary.claim_scope == SYNTHETIC_CLAIM_SCOPE and summary.seed_count_is_sample_size is False
    assert abs(summary.theta) <= 1.0
    assert prepare_group_sums(lab.plan, tuple(cells)).point_estimate == pytest.approx(summary.theta)
    # Request order must not matter to the reducer.
    assert aggregate_primary(lab.plan, tuple(reversed(cells))) == summary


def test_full_condition_grid_of_one_coordinate_is_accepted_by_the_inventory(lab):
    result = lab.run(OUTER, INNER_A)
    assert len(result.conditions) == 400
    inventory = validate_condition_inventory(lab.plan, result.conditions)
    assert inventory.present_slots == 400 and inventory.expected_slots == 20_000
    assert inventory.terminal_failures == ()
    expected = [s for s in expected_condition_slots(lab.spec)
                if (s.outer_seed, s.inner_id) == (OUTER, INNER_A)]
    assert [c.slot for c in result.conditions] == expected
    assert len(result.pair_cells) == len(PREDICTORS) * len(PRIMARY_SCENARIOS)
    assert len({c.condition_id for c in result.conditions}) == 400

    by_slot = {c.slot: c for c in result.conditions}
    for predictor in PREDICTORS:
        for method in ("target_temperature", "target_platt_logodds", "target_beta", "target_isotonic"):
            unattempted = by_slot[(OUTER, INNER_A, predictor, "baseline", 0, method)]
            # Budget zero is unattempted, not a failure; the requested strategy is kept.
            assert unattempted.requested_method == method
            assert unattempted.fit_id is None and unattempted.status == "completed"
            assert unattempted.resolved_method == "source_temperature"
            assert all(reason.startswith("unattempted:") for reason in unattempted.reasons)
        raw = by_slot[(OUTER, INNER_A, predictor, "baseline", 0, "raw")]
        assert raw.resolved_method == "raw" and raw.resolution_counts == (
            ("raw", len(lab.plan.roles(OUTER).evaluation_ids)),)
    for condition in result.conditions:
        assert sum(count for _, count in condition.resolution_counts) in (
            0, len(lab.plan.roles(OUTER).evaluation_ids))
        assert condition.qualification == "qualified"  # synthetic binding only


# ---------------------------------------------------------------- failures and fallbacks

def test_failed_raw_prediction_gives_failed_conditions_and_null_cells(lab, monkeypatch):
    original = adapter.predict_conditions_with_fallback
    broken = {"fits": 0}

    def failing_for_first_predictor(fits, graph, rows, injected_fractions=None):
        resolutions, attempts = original(fits, graph, rows, injected_fractions=injected_fractions)
        broken["fits"] += 1
        if broken["fits"] <= 1:  # logistic regression, first scenario only
            failure = {"method": "raw", "phase": "prediction", "reason": "RuntimeError: forced\nfailure"}
            resolutions = {m: PredictionResolution(None, None, (failure,)) for m in resolutions}
            attempts = {**attempts, "raw": {"status": "failed", "reason": failure["reason"]}}
        return resolutions, attempts

    monkeypatch.setattr(adapter, "predict_conditions_with_fallback", failing_for_first_predictor)
    result = adapter.execute_coordinate(
        lab.prepared(OUTER), INNER_A, scenarios=("history_block_0_50",), budgets=(PRIMARY_BUDGET,))
    failed = [c for c in result.conditions if c.status == "failed"]
    assert {(c.predictor, c.scenario) for c in failed} == {("logistic_regression", "history_block_0_50")}
    assert len(failed) == len(METHODS)
    for condition in failed:
        assert not condition.metrics_available and condition.qualification == "failed"
        assert condition.resolved_method is None and condition.resolution_counts == ()
        assert condition.reasons and all("\n" not in reason for reason in condition.reasons)
    cell = next(c for c in result.pair_cells if c.context.predictor == "logistic_regression")
    assert cell.paired_loss_sum_by_group is None and cell.qualification == "failed"
    assert cell.reasons and cell.target_resolved_method is None and cell.source_resolved_method is None
    healthy = next(c for c in result.pair_cells if c.context.predictor == "random_forest")
    assert healthy.qualification == "qualified" and healthy.paired_loss_sum_by_group is not None
    assert len(result.validated_pairs) == 1  # no pair validation without two probability arrays
    # The reducer withholds the primary estimate rather than reweighting survivors.
    outcome = aggregate_primary(lab.plan, result.pair_cells)
    assert isinstance(outcome, MissingEvidence) and outcome.primary_estimate is None


def test_valid_fallback_keeps_the_requested_strategy(lab, monkeypatch):
    original = adapter.fit_temperature

    def failing_target(pipeline, rows, labels, requested_method):
        if requested_method == "target_temperature":
            return CalibrationFit(pipeline, CalibrationRecord(
                requested_method, "raw", "not_fitted", "forced_fit_failure", len(labels), None))
        return original(pipeline, rows, labels, requested_method)

    monkeypatch.setattr(adapter, "fit_temperature", failing_target)
    result = adapter.execute_coordinate(
        lab.prepared(OUTER), INNER_A, scenarios=("history_block_0_50",), budgets=(PRIMARY_BUDGET,),
        methods=(PRIMARY_SOURCE_METHOD, PRIMARY_TARGET_METHOD))
    for cell in result.pair_cells:
        target = next(c for c in result.conditions if c.condition_id == cell.target_condition_id)
        assert target.requested_method == "target_temperature"
        assert target.resolved_method == cell.target_resolved_method == "source_temperature"
        assert target.status == "completed" and target.qualification == "qualified"
        assert "fit:target_temperature:forced_fit_failure" in target.reasons
        assert target.fit_id is not None  # an attempted fit that failed keeps its identity
        assert cell.qualification == "qualified" and cell.paired_loss_sum_by_group is not None
        assert all(type(v) is float for v in cell.paired_loss_sum_by_group)


# ---------------------------------------------------------------- gating and boundaries

@pytest.mark.parametrize("status", OTHER_STATUSES)
def test_every_non_synthetic_exposure_status_is_refused_before_any_work(lab, status):
    binding = fabricated_binding(lab.dataset, exposure_status=status)
    # The refusal precedes touching the dataset, so even a missing dataset reports SYNTHETIC_ONLY.
    assert _code(lambda: adapter.build_outer_roles(None, binding, lab.spec)) == "SYNTHETIC_ONLY"
    assert _code(lambda: adapter.plan_development_repeats(lab.dataset, binding, lab.spec)) == "SYNTHETIC_ONLY"
    foreign_plan = dataclasses.replace(lab.plan, binding=binding)
    assert _code(lambda: adapter.prepare_outer(lab.dataset, foreign_plan, OUTER)) == "SYNTHETIC_ONLY"
    foreign = dataclasses.replace(lab.prepared(OUTER), plan=foreign_plan)
    assert _code(lambda: adapter.execute_coordinate(foreign, INNER_A, **FAST)) == "SYNTHETIC_ONLY"


def test_dataset_must_match_the_source_binding(lab):
    other = fabricated_binding(lab.dataset, clean_sha256="f" * 64)
    assert _code(lambda: adapter.build_outer_roles(lab.dataset, other, lab.spec)) == "SOURCE_BINDING_MISMATCH"
    shifted = fabricated_bank_dataset(seed=1)
    assert _code(lambda: adapter.prepare_outer(shifted, lab.plan, OUTER)) == "PLAN_DATASET_MISMATCH"


@pytest.mark.parametrize("scope", [
    {"scenarios": ("history_block_0_50", "baseline")},
    {"scenarios": ("mcar_0_20",)},
    {"budgets": (50, 0)},
    {"budgets": (10,)},
    {"methods": ("target_temperature", "raw")},
    {"methods": ()},
])
def test_scope_must_be_an_ordered_subset_of_the_declared_grid(lab, scope):
    assert _code(lambda: adapter.execute_coordinate(lab.prepared(OUTER), INNER_A, **scope)) == "ALTERED_GRID"


def test_undeclared_coordinates_are_refused(lab):
    assert _code(lambda: adapter.execute_coordinate(lab.prepared(OUTER), 99999, **FAST)) == "UNDECLARED_REPEAT"
    assert _code(lambda: adapter.prepare_outer(lab.dataset, lab.plan, 31001)) == "UNDECLARED_REPEAT"


def test_no_row_level_label_derived_value_is_returned_or_logged(lab, caplog):
    with caplog.at_level(logging.DEBUG):
        result = adapter.execute_coordinate(lab.prepared(OUTER), INNER_A, **FAST)
    assert caplog.records == []
    count = len(lab.plan.roles(OUTER).evaluation_ids)

    def walk(value):
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            for field in dataclasses.fields(value):
                yield from walk(getattr(value, field.name))
        elif isinstance(value, (tuple, list)):
            yield value
            for item in value:
                yield from walk(item)

    for sequence in walk(result):
        # Nothing row-aligned to the evaluation rows may be numeric; only IDs and group keys are.
        if len(sequence) == count:
            assert all(type(item) in (str, tuple) for item in sequence)
    prepared = lab.prepared(OUTER)
    assert repr(prepared) == f"PreparedOuter(outer_seed={OUTER})"
    assert "evaluator" in repr(prepared._scorer)
    labels_text = "".join(str(r["y"]) for r in lab.dataset.rows[:50])
    assert labels_text not in repr(prepared._scorer)


def test_probabilities_are_resolved_before_each_final_outcome_access(lab, monkeypatch):
    events: list[str] = []
    resolve = adapter.predict_conditions_with_fallback
    score = adapter.FinalTestEvaluator.score

    def resolving(*args, **kwargs):
        events.append("resolve")
        return resolve(*args, **kwargs)

    def scoring(self, *args, **kwargs):
        events.append("score")
        return score(self, *args, **kwargs)

    monkeypatch.setattr(adapter, "predict_conditions_with_fallback", resolving)
    monkeypatch.setattr(adapter.FinalTestEvaluator, "score", scoring)
    adapter.execute_coordinate(lab.prepared(OUTER), INNER_A, scenarios=("history_block_0_50",),
                               budgets=(PRIMARY_BUDGET,))
    assert events[0] == "resolve" and "score" in events
    # Each predictor's resolution precedes every score call that follows it.
    first_score = events.index("score")
    assert events[:first_score].count("resolve") >= 1
    assert events.count("resolve") == len(PREDICTORS)


def test_fallback_graph_is_the_stress_runner_graph():
    from shiftguard.experiments.stress_runner import STRESS_FALLBACK_GRAPH

    assert adapter.FALLBACK_GRAPH == STRESS_FALLBACK_GRAPH


def test_adapter_imports_no_agent_api_runner_storage_or_adult_module():
    script = (
        "import sys\n"
        "import shiftguard.repeats.development_adapter\n"
        "forbidden = ('shiftguard.agent', 'shiftguard.api', 'shiftguard.jobs', 'shiftguard.storage',\n"
        "             'shiftguard.experiments.runner', 'shiftguard.experiments.stress_runner',\n"
        "             'shiftguard.experiments.outage_runner', 'shiftguard.experiments.publication',\n"
        "             'shiftguard.datasets.adult', 'shiftguard.adult_adapter')\n"
        "loaded = sorted(n for n in sys.modules if n.startswith(forbidden))\n"
        "print(loaded)\n"
        "raise SystemExit(1 if loaded else 0)\n"
    )
    completed = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True,
                               text=True, timeout=180, cwd=Path(__file__).resolve().parents[2])
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_adapter_source_names_no_dataset_path_or_adult_artifact():
    source = Path(adapter.__file__).read_text(encoding="utf-8").lower()
    for token in ("var/datasets", "adult", "from_clean_csv", "from_synthetic_csv", "read_csv", "open("):
        assert token not in source


# ---------------------------------------------------------------- OR-08: the scorer never repairs a value

class _FixedScoreEvaluator:
    """Stands in for the central evaluator: returns the first scripted score, then the second."""

    def __init__(self, first, second=0.0):
        self.scores = [first, second]

    def score(self, _probabilities):
        return {"brier_score": self.scores.pop(0)}


def _scorer_with(first, members=(0,), second=0.0):
    scorer = adapter._EvaluatorPrivateGroupScorer((0,), ("g",))
    scorer._groups = (("g", members, _FixedScoreEvaluator(first, second)),)
    return scorer


def _group_sums(scorer, rows):
    return scorer.evaluator_private_paired_group_sums(("g",), [1.0] * rows, [0.0] * rows)


def test_out_of_bound_group_loss_is_not_clamped():
    # The review's fault injection: a one-row group sum just beyond the exact bound.
    assert not hasattr(adapter, "_ROUNDING_SLACK")
    assert _code(lambda: _group_sums(_scorer_with(1.0000000005), 1)) == "INVALID_GROUP_SUM"
    assert _code(lambda: _group_sums(_scorer_with(-1.0000000005), 1)) == "INVALID_GROUP_SUM"
    # Multi-row groups use the same exact bound of plus or minus the row count.
    members = (0, 1, 2)
    assert _code(lambda: _group_sums(_scorer_with(1.0000000005, members), 3)) == "INVALID_GROUP_SUM"
    assert _code(lambda: _group_sums(_scorer_with(0.0, members, 1.0000000005), 3)) == "INVALID_GROUP_SUM"
    for bad in (float("nan"), float("inf"), float("-inf"), 2.0, -2.0, 1e300):
        assert _code(lambda: _group_sums(_scorer_with(bad), 1)) == "INVALID_GROUP_SUM"
    # The exact extrema and zero stay valid and unchanged.
    for value in (-1.0, 0.0, 1.0):
        assert _group_sums(_scorer_with(value), 1) == (value,)
    assert _group_sums(_scorer_with(1.0, (0, 1, 2)), 3) == (3.0,)
    assert _group_sums(_scorer_with(0.0, (0, 1, 2), 1.0), 3) == (-3.0,)
    assert type(_group_sums(_scorer_with(0.5), 1)[0]) is float


def test_real_evaluator_extremes_are_exactly_at_the_group_bounds():
    scorer = adapter._EvaluatorPrivateGroupScorer((0, 1, 0, 1), ("g", "g", "h", "h"))
    # Target maximally wrong, source maximally right: each row contributes +1; reversed gives -1.
    worst = scorer.evaluator_private_paired_group_sums(
        ("g", "h"), [1.0, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, 1.0])
    best = scorer.evaluator_private_paired_group_sums(
        ("g", "h"), [0.0, 1.0, 0.0, 1.0], [1.0, 0.0, 1.0, 0.0])
    assert worst == (2.0, 2.0) and best == (-2.0, -2.0)
    tie = scorer.evaluator_private_paired_group_sums(("g", "h"), [0.3] * 4, [0.3] * 4)
    assert tie == (0.0, 0.0)
    assert scorer.evaluator_private_paired_group_sums(("g", "h", "absent"), [0.3] * 4, [0.3] * 4)[2] == 0.0


# ---------------------------------------------------------------- OR-06: resolution accounting per row

BINNED = PRIMARY_SOURCE_METHOD


def _resolution(method):
    return PredictionResolution([0.5], method, ())


def test_mixed_binned_resolutions_map_to_declared_names_in_declared_order():
    # The binned map names its fitted-bin resolution differently from the declared method, so the
    # source map is not the identity: "fitted_bin_temperature" must become the binned method.
    diagnostics = {"resolution_counts": {
        "fitted_bin_temperature": 5, "source_remasked_temperature": 2, "source_temperature": 0, "raw": 1}}
    binned = SimpleNamespace(probability_map=SimpleNamespace(last_diagnostics=diagnostics))
    counts = adapter._resolution_counts(BINNED, _resolution(BINNED), binned, 8)
    assert counts == (("raw", 1), ("source_remasked_temperature", 2), (BINNED, 5))
    assert sum(count for _, count in counts) == 8
    # A whole-condition fallback of the binned strategy is a single entry for its fallback.
    assert adapter._resolution_counts(
        BINNED, _resolution("source_temperature"), binned, 8) == (("source_temperature", 8),)
    # Every other strategy resolves its entire condition to one method; failure leaves no counts.
    assert adapter._resolution_counts(
        PRIMARY_TARGET_METHOD, _resolution("source_temperature"), binned, 8) == (("source_temperature", 8),)
    assert adapter._resolution_counts(
        PRIMARY_TARGET_METHOD, PredictionResolution(None, None, ()), binned, 8) == ()


def _by_id(result):
    return {condition.condition_id: condition for condition in result.conditions}


def _swap(result, **changes):
    return dataclasses.replace(result, **changes)


def _with_condition(result, old, new):
    return tuple(new if condition is old else condition for condition in result.conditions)


def _mixed_source_result(result, index=0, counts=None):
    """Replace a primary pair's binned condition by a consistent mixed-resolution one."""
    cell = result.pair_cells[index]
    source = _by_id(result)[cell.source_condition_id]
    counts = counts or (("raw", 1), ("source_remasked_temperature", 2), (BINNED, source.row_count - 3))
    mixed = dataclasses.replace(
        source,
        resolution_counts=counts,
        condition_id=adapter.condition_identity(
            result.repeat_id, cell.context, BINNED, source.fit_id, BINNED, counts, source.status),
    )
    new_cell = dataclasses.replace(
        cell, source_condition_id=mixed.condition_id, source_resolution_counts=counts)
    cells = result.pair_cells[:index] + (new_cell,) + result.pair_cells[index + 1:]
    return _swap(result, conditions=_with_condition(result, source, mixed), pair_cells=cells), mixed, new_cell


def test_every_primary_pair_carries_the_accounting_of_its_two_terminal_conditions(lab):
    result = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    rows = len(lab.plan.roles(OUTER).evaluation_ids)
    by_id = _by_id(result)
    assert len(result.pair_cells) == len(PREDICTORS) * len(PRIMARY_SCENARIOS)
    for cell in result.pair_cells:
        target, source = by_id[cell.target_condition_id], by_id[cell.source_condition_id]
        assert cell.target_resolution_counts == target.resolution_counts
        assert cell.source_resolution_counts == source.resolution_counts
        assert sum(count for _, count in cell.target_resolution_counts) == rows
        assert sum(count for _, count in cell.source_resolution_counts) == rows
        assert cell.has_fallback == bool(target.fallback_rows or source.fallback_rows)
    adapter.validate_coordinate_result(lab.plan, result)


def test_execute_coordinate_validates_the_joined_result_before_returning_it(lab, monkeypatch):
    seen = []
    original = adapter.validate_coordinate_result

    def spy(plan, result):
        seen.append((plan, result))
        return original(plan, result)

    monkeypatch.setattr(adapter, "validate_coordinate_result", spy)
    result = adapter.execute_coordinate(lab.prepared(OUTER), INNER_A, **PRIMARY_ONLY)
    assert len(seen) == 1 and seen[0][0] is lab.plan and seen[0][1] is result

    def refuse(plan, result):
        raise RepeatContractError("PAIR_BINDING", "forced")

    monkeypatch.setattr(adapter, "validate_coordinate_result", refuse)
    assert _code(lambda: adapter.execute_coordinate(lab.prepared(OUTER), INNER_A, **PRIMARY_ONLY)) == (
        "PAIR_BINDING")


def test_a_full_and_a_partial_coordinate_validate_against_the_plan(lab):
    adapter.validate_coordinate_result(lab.plan, lab.run(OUTER, INNER_A))
    adapter.validate_coordinate_result(lab.plan, lab.run(OUTER, INNER_A, **FAST))
    adapter.validate_coordinate_result(lab.plan, lab.run(OUTER, INNER_B, **PRIMARY_ONLY))
    assert _code(lambda: adapter.validate_coordinate_result(lab.plan, None)) == "COORDINATE_SCHEMA"
    forged = dataclasses.replace(lab.plan, plan_digest="0" * 64)
    assert _code(lambda: adapter.validate_coordinate_result(forged, lab.run(OUTER, INNER_A, **FAST))) == (
        "PLAN_INTEGRITY")


def test_condition_accounting_that_disagrees_with_the_plan_rows_is_refused(lab):
    result = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    condition = result.conditions[0]
    inflated = dataclasses.replace(condition, resolution_counts=((condition.resolved_method, 999_999),))
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, conditions=_with_condition(result, condition, inflated)))
    ) == "RESOLUTION_ACCOUNTING"
    short = dataclasses.replace(condition, resolution_counts=((condition.resolved_method, condition.row_count - 1),))
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, conditions=_with_condition(result, condition, short)))
    ) == "RESOLUTION_ACCOUNTING"


def test_accounting_bound_into_the_condition_id_cannot_be_rewritten(lab):
    result = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    cell = result.pair_cells[0]
    source = _by_id(result)[cell.source_condition_id]
    rows = source.row_count
    # Valid-looking accounting with an unchanged condition ID: the ID no longer matches.
    other = "raw" if source.resolved_method == "source_temperature" else "source_temperature"
    relabelled = dataclasses.replace(source, resolution_counts=((other, rows),), resolved_method=other)
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, conditions=_with_condition(result, source, relabelled)))
    ) == "COORDINATE_CONDITION"
    wrong_fit = dataclasses.replace(source, fit_id=canonical_digest(["another", "fit"]))
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, conditions=_with_condition(result, source, wrong_fit)))
    ) == "COORDINATE_FIT"


def test_a_primary_pair_copied_from_another_condition_is_refused(lab):
    result = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    first, second, last = result.pair_cells[0], result.pair_cells[1], result.pair_cells[-1]
    assert len({first.context.predictor, last.context.predictor}) == 2
    # Same coordinate, but pointing at the neighbouring scenario's terminal condition.
    copied = dataclasses.replace(first, target_condition_id=second.target_condition_id)
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, pair_cells=(copied,) + result.pair_cells[1:]))) == "PAIR_BINDING"
    # ... or at another predictor's condition.
    copied = dataclasses.replace(first, source_condition_id=last.source_condition_id)
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, pair_cells=(copied,) + result.pair_cells[1:]))) == "PAIR_BINDING"
    # ... or at an unknown condition; a pair cannot reference one condition on both sides at all.
    copied = dataclasses.replace(first, target_condition_id=canonical_digest(["unknown"]))
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, pair_cells=(copied,) + result.pair_cells[1:]))) == "PAIR_BINDING"
    assert _code(lambda: dataclasses.replace(
        first, source_condition_id=first.target_condition_id)) == "DUPLICATE_VALUE"


def test_a_primary_pair_from_another_coordinate_is_refused(lab):
    here, there = lab.run(OUTER, INNER_A, **PRIMARY_ONLY), lab.run(OUTER, INNER_B, **PRIMARY_ONLY)
    foreign = (there.pair_cells[0],) + here.pair_cells[1:]
    assert _code(lambda: adapter.validate_coordinate_result(lab.plan, _swap(here, pair_cells=foreign))) == (
        "PAIR_BINDING")
    mixed_conditions = _swap(here, conditions=here.conditions[:-1] + (there.conditions[-1],))
    assert _code(lambda: adapter.validate_coordinate_result(lab.plan, mixed_conditions)) in {
        "COORDINATE_CONDITION", "PAIR_BINDING"}


def test_pair_accounting_must_equal_its_conditions_and_no_pair_may_go_missing(lab):
    result = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    cell = result.pair_cells[0]
    rows = sum(cell.n_by_group)
    shifted = dataclasses.replace(cell, source_resolution_counts=(("source_temperature", 1), (BINNED, rows - 1)))
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, pair_cells=(shifted,) + result.pair_cells[1:]))) == "PAIR_BINDING"
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, pair_cells=result.pair_cells[1:]))) == "PAIR_BINDING"
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, pair_cells=result.pair_cells + result.pair_cells[:1]))) == "PAIR_BINDING"
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, validated_pairs=result.validated_pairs[1:]))) == "PAIR_BINDING"
    unscored = dataclasses.replace(
        cell, paired_loss_sum_by_group=None, qualification="failed", reasons=("forced",))
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, pair_cells=(unscored,) + result.pair_cells[1:]))) == "PAIR_BINDING"


def test_shared_context_identity_must_hold_across_the_coordinate(lab):
    result = lab.run(OUTER, INNER_A, **FAST)
    contexts = list(result.contexts)
    index = next(i for i, c in enumerate(contexts) if c.predictor == "random_forest" and c.scenario == "history_block_0_50")
    for field in ("test_mask", "pool_mask"):
        contexts[index] = dataclasses.replace(result.contexts[index], **{field: canonical_digest(["x", field])})
        assert _code(lambda: adapter.validate_coordinate_result(
            lab.plan, _swap(result, contexts=tuple(contexts)))) == "COORDINATE_CONTEXT"
    contexts[index] = dataclasses.replace(result.contexts[index], predictor_id=canonical_digest(["other"]))
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, contexts=tuple(contexts)))) == "COORDINATE_CONTEXT"
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, acquisition_order=tuple(reversed(result.acquisition_order))))
    ) == "COORDINATE_CONTEXT"
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, acquisition_order=result.acquisition_order[:-1]))) == "COORDINATE_ACQUISITION"
    other_inner = lab.run(OUTER, INNER_B, **FAST)
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, contexts=other_inner.contexts))) == "COORDINATE_CONTEXT"
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, repeat_id=other_inner.repeat_id))) == "COORDINATE_IDENTITY"
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, claim_scope="confirmatory"))) == "COORDINATE_IDENTITY"
    reordered = tuple(reversed(result.conditions))
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, conditions=reordered))) == "COORDINATE_CONDITION"


def test_mixed_binned_condition_with_a_nonidentity_source_map_is_kept_and_counted_as_fallback(lab):
    result = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    mixed_result, mixed, cell = _mixed_source_result(result)
    adapter.validate_coordinate_result(lab.plan, mixed_result)
    assert mixed.resolved_method == BINNED  # the top-level label still says binned ...
    assert mixed.fallback_rows == 3 and len(mixed.resolution_counts) == 3  # ... the mixture says more
    assert cell.source_resolved_method == BINNED and cell.source_fallback_rows == 3 and cell.has_fallback
    assert cell.target_fallback_rows == 0
    # A mixture on the forbidden edge (a target method inside the binned chain) cannot be built.
    assert _code(lambda: _mixed_source_result(
        result, counts=(("raw", 1), (BINNED, mixed.row_count - 3), ("target_temperature", 2)))
    ) == "FORBIDDEN_FALLBACK"
    # An ID that does not follow the rewritten accounting is caught by the coordinate join.
    stale = dataclasses.replace(mixed, condition_id=_by_id(result)[result.pair_cells[0].source_condition_id].condition_id)
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(result, conditions=_with_condition(mixed_result, mixed, stale)))) in {
            "COORDINATE_CONDITION", "PAIR_BINDING"}


def test_full_grid_inventory_reports_the_mixed_binned_slot_as_a_fallback(lab):
    result = lab.run(OUTER, INNER_A)
    mixed_result, mixed, _ = _mixed_source_result(result)
    inventory = validate_condition_inventory(lab.plan, mixed_result.conditions)
    assert inventory.present_slots == 400 and mixed.slot in inventory.fallback_slots


def test_pair_metadata_survives_store_reopen_with_the_real_adapter_output(lab, tmp_path):
    from shiftguard.repeats.completion import build_completion
    from shiftguard.repeats.synthetic_store import SyntheticRepeatStore

    result = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    mixed_result, _, mixed_cell = _mixed_source_result(result)
    content = {
        "synthetic": True,
        "cells": [cell.to_canonical() for cell in mixed_result.pair_cells],
        "conditions": [condition.to_canonical() for condition in mixed_result.conditions],
    }
    record, artifact = build_completion(lab.plan, mixed_result.repeat_id, content, "completed")
    SyntheticRepeatStore(tmp_path / "store").commit(record, artifact, attempt_id="attempt-1")
    stored = SyntheticRepeatStore(tmp_path / "store").load(record.repeat_id)
    envelope = json.loads(stored.artifact.decode("ascii"))
    cells = tuple(PairedGroupLossCell.from_canonical(item) for item in envelope["content"]["cells"])
    conditions = tuple(TerminalCondition.from_canonical(item) for item in envelope["content"]["conditions"])
    assert cells == mixed_result.pair_cells and conditions == mixed_result.conditions
    assert cells[0] == mixed_cell and cells[0].source_resolution_counts == mixed_cell.source_resolution_counts
    # The reopened pieces still join: nothing was defaulted on the way through the store.
    adapter.validate_coordinate_result(lab.plan, _swap(mixed_result, pair_cells=cells, conditions=conditions))


# ---------------------------------------------------------------- verified Bank development binding

def _dev_code(dev_lab, result, **changes):
    return _code(lambda: adapter.validate_coordinate_result(dev_lab.plan, _swap(result, **changes)))


def test_development_binding_runs_end_to_end_unknown_authority_with_the_sci03_reason(dev_lab):
    assert dev_lab.plan.binding.exposure_status == "development_exposed"
    assert adapter.claim_scope_for(dev_lab.binding) == BANK_DEVELOPMENT_CLAIM_SCOPE
    result = dev_lab.run(OUTER, INNER_A, **FAST)  # execute_coordinate validates before returning
    assert result.claim_scope == BANK_DEVELOPMENT_CLAIM_SCOPE and result.execution_tier == "development"
    completed = [c for c in result.conditions if c.status == "completed"]
    assert completed and all(
        c.qualification == "unknown_authority" and c.reasons[0] == SCI03_UNRESOLVED_REASON
        and c.reasons.count(SCI03_UNRESOLVED_REASON) == 1 for c in completed)
    # Budget-zero unattempted fallbacks keep their own codes after the SCI-03 reason.
    assert any(len(c.reasons) > 1 and c.reasons[1].startswith("unattempted:") for c in completed)
    assert [c for c in result.conditions if c.status == "failed"] == []
    primary = dev_lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    assert primary.pair_cells and all(
        cell.qualification == "unknown_authority" and cell.reasons == (SCI03_UNRESOLVED_REASON,)
        and cell.paired_loss_sum_by_group is not None for cell in primary.pair_cells)
    adapter.validate_coordinate_result(dev_lab.plan, result)
    # The aggregator's MissingEvidence handling of unknown_authority is intended, not bypassed.
    outcome = aggregate_primary(dev_lab.plan, primary.pair_cells)
    assert isinstance(outcome, MissingEvidence) and outcome.primary_estimate is None
    assert outcome.code == "PRIMARY_EVIDENCE_UNAVAILABLE"
    cell_keys = tuple(cell.key for cell in primary.pair_cells)
    assert len(cell_keys) == len(PREDICTORS) * len(PRIMARY_SCENARIOS) == 8
    assert outcome.unavailable == tuple(
        (key, "unknown_authority", (SCI03_UNRESOLVED_REASON,)) for key in cell_keys)
    assert len(outcome.missing) == 400 - 8  # the other 49 coordinates were not run here
    assert SCI03_UNRESOLVED_REASON in outcome.reasons


def test_development_binding_is_accepted_by_every_entry_point_when_pinned(dev_lab):
    manifests = adapter.build_outer_roles(dev_lab.dataset, dev_lab.binding, dev_lab.spec)
    assert len(manifests) == len(OUTER_SEEDS)
    assert adapter.plan_development_repeats(dev_lab.dataset, dev_lab.binding, dev_lab.spec) == dev_lab.plan
    prepared = adapter.prepare_outer(dev_lab.dataset, dev_lab.plan, OUTER)
    assert adapter.execute_coordinate(prepared, INNER_A, **FAST) == dev_lab.run(OUTER, INNER_A, **FAST)


def test_synthetic_path_is_unchanged_by_the_development_reconciliation(lab):
    result = lab.run(OUTER, INNER_A, **FAST)
    assert result.claim_scope == SYNTHETIC_CLAIM_SCOPE
    assert adapter.claim_scope_for(lab.binding) == SYNTHETIC_CLAIM_SCOPE
    assert all(SCI03_UNRESOLVED_REASON not in c.reasons for c in result.conditions)
    assert all(c.qualification == "qualified" for c in result.conditions if c.status == "completed")
    primary = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    assert all(cell.qualification == "qualified" and cell.reasons == () for cell in primary.pair_cells)


def _assert_refused_everywhere(lab, binding, code="SYNTHETIC_ONLY"):
    # Refusal precedes touching the dataset, so a missing dataset still reports the gate's code.
    assert _code(lambda: adapter.build_outer_roles(None, binding, lab.spec)) == code
    assert _code(lambda: adapter.plan_development_repeats(None, binding, lab.spec)) == code
    assert _code(lambda: adapter.plan_development_repeats(None, binding)) == code
    foreign_plan = dataclasses.replace(lab.plan, binding=binding)
    assert _code(lambda: adapter.prepare_outer(None, foreign_plan, OUTER)) == code
    foreign = dataclasses.replace(lab.prepared(OUTER), plan=foreign_plan)
    assert _code(lambda: adapter.execute_coordinate(foreign, INNER_A, **FAST)) == code
    assert _code(lambda: adapter.claim_scope_for(binding)) == code


@pytest.mark.parametrize("field", ("dataset", "release", "raw_sha256", "clean_sha256"))
def test_development_binding_with_any_unverified_field_is_refused(lab, dev_lab, field):
    other = "other-value" if field in ("dataset", "release") else "f" * 64
    _assert_refused_everywhere(lab, dataclasses.replace(dev_lab.binding, **{field: other}))


@pytest.mark.parametrize("status", ("unknown", "custodian_attested"))
def test_other_statuses_are_refused_even_with_the_verified_values(lab, dev_lab, status):
    _assert_refused_everywhere(lab, dataclasses.replace(dev_lab.binding, exposure_status=status))


def test_development_binding_with_unpinned_digests_is_refused(lab, _dev_lab_cache):
    # No pin is active here: the planning constants are the dataset owner's real values.
    from shiftguard.datasets import bank

    assert adapter_planning.VERIFIED_BANK_DATASET == bank.FROZEN_BANK_SOURCE["dataset_id"]
    assert adapter_planning.VERIFIED_BANK_RELEASE == bank.FROZEN_BANK_SOURCE["source_version"]
    assert adapter_planning.VERIFIED_BANK_RAW_SHA256 == bank.FROZEN_BANK_SOURCE["raw_member_sha256"]
    assert adapter_planning.VERIFIED_BANK_CLEAN_SHA256 == bank.FROZEN_CLEAN_DIGEST
    _assert_refused_everywhere(lab, _dev_lab_cache.binding)


@pytest.mark.parametrize("field", ("dataset", "release", "raw_sha256", "clean_sha256"))
def test_a_synthetic_binding_may_not_carry_any_verified_bank_identity(lab, field):
    real = {
        "dataset": adapter_planning.VERIFIED_BANK_DATASET,
        "release": adapter_planning.VERIFIED_BANK_RELEASE,
        "raw_sha256": adapter_planning.VERIFIED_BANK_RAW_SHA256,
        "clean_sha256": adapter_planning.VERIFIED_BANK_CLEAN_SHA256,
    }
    binding = dataclasses.replace(lab.binding, **{field: real[field]})
    assert binding.exposure_status == "synthetic_fabricated"
    _assert_refused_everywhere(lab, binding, "SYNTHETIC_MISLABEL")
    roles = tuple(lab.plan.roles(outer) for outer in OUTER_SEEDS)
    assert _code(lambda: adapter_planning.plan_repeats(lab.spec, binding, roles)) == "SYNTHETIC_MISLABEL"


def test_execution_mode_follows_the_binding_and_never_crosses(lab, dev_lab):
    from shiftguard.repeats.models import BANK_DEVELOPMENT_MODE

    assert lab.plan.spec.execution_mode == "synthetic_only"
    assert dev_lab.plan.spec.execution_mode == BANK_DEVELOPMENT_MODE
    # The default spec of plan_development_repeats is chosen from the binding.
    assert adapter.plan_development_repeats(dev_lab.dataset, dev_lab.binding) == dev_lab.plan
    roles = tuple(dev_lab.plan.roles(outer) for outer in OUTER_SEEDS)
    assert _code(lambda: adapter_planning.plan_repeats(RepeatSpec(), dev_lab.binding, roles)) == "EXECUTION_MODE"
    synthetic_roles = tuple(lab.plan.roles(outer) for outer in OUTER_SEEDS)
    assert _code(lambda: adapter_planning.plan_repeats(
        RepeatSpec(execution_mode=BANK_DEVELOPMENT_MODE), lab.binding, synthetic_roles)) == "EXECUTION_MODE"
    assert dev_lab.plan.plan_digest != lab.plan.plan_digest
    assert not {r.repeat_id for r in dev_lab.plan.repeats} & {r.repeat_id for r in lab.plan.repeats}


def test_a_development_dataset_whose_rows_do_not_hash_to_the_bound_clean_digest_is_refused(dev_lab):
    rows = [dict(row) for row in dev_lab.dataset.rows]
    rows[0]["y"] = 1 - rows[0]["y"]
    tampered = dataclasses.replace(dev_lab.dataset, rows=rows)
    assert _code(lambda: adapter.build_outer_roles(tampered, dev_lab.binding, dev_lab.spec)) == (
        "SOURCE_BINDING_MISMATCH")
    assert _code(lambda: adapter.prepare_outer(tampered, dev_lab.plan, OUTER)) == "SOURCE_BINDING_MISMATCH"


def test_development_fallback_slots_are_the_conditions_with_fallback_rows(dev_lab):
    result = dev_lab.run(OUTER, INNER_A)
    inventory = validate_condition_inventory(dev_lab.plan, result.conditions)
    expected = tuple(c.slot for c in result.conditions if c.fallback_rows)
    assert inventory.fallback_slots == expected and expected  # budget-zero targets fall back
    assert all(c.qualification == "unknown_authority" for c in result.conditions)


def test_unscored_pair_reasons_must_follow_its_failed_conditions(lab, monkeypatch):
    original = adapter.predict_conditions_with_fallback
    state = {"n": 0}

    def failing_first(fits, graph, rows, injected_fractions=None):
        resolutions, attempts = original(fits, graph, rows, injected_fractions=injected_fractions)
        state["n"] += 1
        if state["n"] == 1:
            failure = {"method": "raw", "phase": "prediction", "reason": "RuntimeError: forced"}
            resolutions = {m: PredictionResolution(None, None, (failure,)) for m in resolutions}
        return resolutions, attempts

    monkeypatch.setattr(adapter, "predict_conditions_with_fallback", failing_first)
    result = adapter.execute_coordinate(
        lab.prepared(OUTER), INNER_A, scenarios=("history_block_0_50",), budgets=(PRIMARY_BUDGET,))
    monkeypatch.undo()
    cell = next(c for c in result.pair_cells if c.paired_loss_sum_by_group is None)
    assert cell.reasons == ("target_prediction_failed", "source_prediction_failed")
    for reasons in (("target_prediction_failed",), ("source_prediction_failed", "target_prediction_failed"),
                    ("forced",)):
        changed = dataclasses.replace(cell, reasons=reasons)
        pairs = tuple(changed if c is cell else c for c in result.pair_cells)
        assert _code(lambda: adapter.validate_coordinate_result(
            lab.plan, _swap(result, pair_cells=pairs))) == "PAIR_BINDING"


def test_validator_rejects_development_scored_cell_reason_and_qualification_tampering(dev_lab):
    result = dev_lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    cell = result.pair_cells[0]

    def with_cell(new):
        return (new,) + result.pair_cells[1:]

    # An unknown_authority cell without a reason cannot even be constructed.
    assert _code(lambda: dataclasses.replace(cell, reasons=())) == "QUALIFICATION"
    relabelled = dataclasses.replace(cell, qualification="qualified", reasons=())
    assert _dev_code(dev_lab, result, pair_cells=with_cell(relabelled)) == "PAIR_BINDING"
    qualified_with_reason = dataclasses.replace(cell, qualification="qualified")
    assert _dev_code(dev_lab, result, pair_cells=with_cell(qualified_with_reason)) == "PAIR_BINDING"
    extra = dataclasses.replace(cell, reasons=(SCI03_UNRESOLVED_REASON, "extra_reason"))
    assert _dev_code(dev_lab, result, pair_cells=with_cell(extra)) == "PAIR_BINDING"
    other_reason = dataclasses.replace(cell, reasons=("some_other_reason",))
    assert _dev_code(dev_lab, result, pair_cells=with_cell(other_reason)) == "PAIR_BINDING"


def test_validator_rejects_development_condition_reason_and_qualification_tampering(dev_lab):
    result = dev_lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    condition = result.conditions[0]
    assert condition.reasons[0] == SCI03_UNRESOLVED_REASON

    def code(**changes):
        new = dataclasses.replace(condition, **changes)
        return _dev_code(dev_lab, result, conditions=_with_condition(result, condition, new))

    # Condition IDs do not cover qualification or reasons, so these reach the new check directly.
    assert code(reasons=("some_other_reason",)) == "COORDINATE_QUALIFICATION"
    assert code(reasons=("some_other_reason", SCI03_UNRESOLVED_REASON)) == "COORDINATE_QUALIFICATION"
    assert code(reasons=(SCI03_UNRESOLVED_REASON, SCI03_UNRESOLVED_REASON)) == "COORDINATE_QUALIFICATION"
    assert code(qualification="qualified", reasons=()) == "COORDINATE_QUALIFICATION"
    assert code(qualification="qualified", reasons=(SCI03_UNRESOLVED_REASON,)) == "COORDINATE_QUALIFICATION"


def test_validator_rejects_unknown_authority_labels_on_a_synthetic_result(lab):
    result = lab.run(OUTER, INNER_A, **PRIMARY_ONLY)
    condition, cell = result.conditions[0], result.pair_cells[0]

    def code(**changes):
        return _code(lambda: adapter.validate_coordinate_result(lab.plan, _swap(result, **changes)))

    relabelled = dataclasses.replace(
        condition, qualification="unknown_authority", reasons=(SCI03_UNRESOLVED_REASON,))
    assert code(conditions=_with_condition(result, condition, relabelled)) == "COORDINATE_QUALIFICATION"
    tagged = dataclasses.replace(condition, reasons=(*condition.reasons, SCI03_UNRESOLVED_REASON))
    assert code(conditions=_with_condition(result, condition, tagged)) == "COORDINATE_QUALIFICATION"
    unknown_cell = dataclasses.replace(
        cell, qualification="unknown_authority", reasons=(SCI03_UNRESOLVED_REASON,))
    assert code(pair_cells=(unknown_cell,) + result.pair_cells[1:]) == "PAIR_BINDING"


def test_validator_binds_the_claim_scope_to_the_source_binding(lab, dev_lab):
    synthetic = lab.run(OUTER, INNER_A, **FAST)
    development = dev_lab.run(OUTER, INNER_A, **FAST)
    assert _code(lambda: adapter.validate_coordinate_result(
        lab.plan, _swap(synthetic, claim_scope=BANK_DEVELOPMENT_CLAIM_SCOPE))) == "COORDINATE_IDENTITY"
    assert _dev_code(dev_lab, development, claim_scope=SYNTHETIC_CLAIM_SCOPE) == "COORDINATE_IDENTITY"
    assert _dev_code(dev_lab, development, claim_scope="confirmatory") == "COORDINATE_IDENTITY"


def test_an_explicit_spec_must_match_the_binding_mode_before_the_dataset_is_touched(lab, dev_lab):
    assert _code(lambda: adapter.plan_development_repeats(None, lab.binding, RepeatSpec(
        execution_mode="bank_development"))) == "EXECUTION_MODE"
    assert _code(lambda: adapter.plan_development_repeats(None, dev_lab.binding, RepeatSpec())) == (
        "EXECUTION_MODE")


def test_rows_must_have_exactly_the_clean_fields_before_they_are_hashed(dev_lab):
    for change in ("extra", "missing"):
        rows = [dict(row) for row in dev_lab.dataset.rows]
        if change == "extra":
            rows[3]["note"] = "x"
        else:
            del rows[3]["job"]
        odd = dataclasses.replace(dev_lab.dataset, rows=rows)
        assert _code(lambda: adapter.build_outer_roles(odd, dev_lab.binding, dev_lab.spec)) == "DATASET_SCHEMA"
        assert _code(lambda: adapter.prepare_outer(odd, dev_lab.plan, OUTER)) == "DATASET_SCHEMA"


def test_synthetic_rows_that_hash_to_the_verified_clean_digest_are_refused(lab, monkeypatch):
    from shiftguard.datasets.bank import hash_clean_rows

    monkeypatch.setattr(adapter_planning, "VERIFIED_BANK_CLEAN_SHA256", hash_clean_rows(lab.dataset.rows))
    assert _code(lambda: adapter.build_outer_roles(lab.dataset, lab.binding, lab.spec)) == "SYNTHETIC_MISLABEL"
    assert _code(lambda: adapter.prepare_outer(lab.dataset, lab.plan, OUTER)) == "SYNTHETIC_MISLABEL"
