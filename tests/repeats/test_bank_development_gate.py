"""The verified-Bank development plan may reach only typed missing evidence downstream.

Everything here is fabricated: roles and cells come from repeat_fixtures, and the verified
release is replaced by a stand-in through a per-test pin of the planning constants.
"""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from repeat_fixtures import (
    fake_digest,
    packet_fixture_sums,
    primary_cell,
    primary_cells,
    primary_keys,
    synthetic_binding,
    synthetic_plan,
    synthetic_roles,
)
from shiftguard.repeats import planning
from shiftguard.repeats.aggregation import (
    PreparedAggregate,
    aggregate_primary,
    prepare_group_sums,
    validate_prepared_aggregate,
    weighted_estimate,
)
from shiftguard.repeats.completion import (
    ARTIFACT_NAME,
    CompletionRecord,
    build_completion,
    serialize_artifact,
)
from shiftguard.repeats.models import (
    BANK_DEVELOPMENT_MODE,
    OUTER_SEEDS,
    SCI03_UNRESOLVED_REASON,
    MissingEvidence,
    RepeatContractError,
    RepeatSpec,
)
from shiftguard.repeats.synthetic_store import SyntheticRepeatStore
from shiftguard.repeats.validation import validate_condition_inventory
from shiftguard.repeats.uncertainty import UncertaintySpec, draw_estimates, paired_group_interval


def _code(call) -> str:
    with pytest.raises(RepeatContractError) as raised:
        call()
    return raised.value.code


@pytest.fixture
def dev_plan(monkeypatch):
    binding = synthetic_binding(
        exposure_status="development_exposed", dataset="dev-standin", release="dev-v1",
        raw_sha256=fake_digest("dev-raw"), clean_sha256=fake_digest("dev-clean"))
    monkeypatch.setattr(planning, "VERIFIED_BANK_DATASET", binding.dataset)
    monkeypatch.setattr(planning, "VERIFIED_BANK_RELEASE", binding.release)
    monkeypatch.setattr(planning, "VERIFIED_BANK_RAW_SHA256", binding.raw_sha256)
    monkeypatch.setattr(planning, "VERIFIED_BANK_CLEAN_SHA256", binding.clean_sha256)
    roles = tuple(synthetic_roles(outer) for outer in OUTER_SEEDS)
    return planning.plan_repeats(RepeatSpec(execution_mode=BANK_DEVELOPMENT_MODE), binding, roles)


def _unknown_cells(plan):
    return tuple(
        primary_cell(
            plan, key, sums=packet_fixture_sums(key, plan.group_counts(key[0])),
            qualification="unknown_authority", reasons=(SCI03_UNRESOLVED_REASON,))
        for key in primary_keys())


def test_four_hundred_unknown_authority_cells_give_typed_missing_evidence(dev_plan):
    cells = _unknown_cells(dev_plan)
    outcome = aggregate_primary(dev_plan, cells)
    assert isinstance(outcome, MissingEvidence)
    assert outcome.code == "PRIMARY_EVIDENCE_UNAVAILABLE"
    assert outcome.missing == () and len(outcome.unavailable) == 400
    assert all(entry[1:] == ("unknown_authority", (SCI03_UNRESOLVED_REASON,))
               for entry in outcome.unavailable)
    assert outcome.reasons == (SCI03_UNRESOLVED_REASON,)
    assert outcome.primary_estimate is None and outcome.interval is None
    # Order of the input never matters.
    assert aggregate_primary(dev_plan, tuple(reversed(cells))) == outcome


def test_a_qualified_cell_on_a_development_plan_is_an_upgrade_and_raises(dev_plan):
    cells = list(_unknown_cells(dev_plan))
    cells[0] = primary_cell(
        dev_plan, primary_keys()[0], sums=packet_fixture_sums(None, dev_plan.group_counts(OUTER_SEEDS[0])))
    assert cells[0].qualification == "qualified"
    assert _code(lambda: aggregate_primary(dev_plan, tuple(cells))) == "QUALIFICATION_UPGRADE"
    # All qualified is the same upgrade; no PrimarySummary is ever built for a Bank plan.
    assert _code(lambda: aggregate_primary(dev_plan, primary_cells(dev_plan))) == "QUALIFICATION_UPGRADE"


def test_the_synthetic_only_paths_refuse_a_development_plan(dev_plan, tmp_path):
    assert _code(lambda: build_completion(
        dev_plan, dev_plan.repeats[0].repeat_id, {"synthetic": True}, "completed")) == "SYNTHETIC_ONLY"
    assert _code(lambda: prepare_group_sums(dev_plan, _unknown_cells(dev_plan))) == "SYNTHETIC_ONLY"
    # A prepared aggregate built on the synthetic plan cannot be re-pointed at the development plan.
    synthetic = synthetic_plan()
    prepared = prepare_group_sums(synthetic, primary_cells(synthetic, packet_fixture_sums))
    assert isinstance(prepared, PreparedAggregate)
    repointed = dataclasses.replace(prepared, plan_digest=dev_plan.plan_digest)
    assert _code(lambda: validate_prepared_aggregate(repointed, dev_plan)) == "SYNTHETIC_ONLY"
    assert _code(lambda: weighted_estimate(repointed, (1, 1), plan=dev_plan)) == "SYNTHETIC_ONLY"
    spec = UncertaintySpec("bank_overlap_diagnostic")
    assert _code(lambda: paired_group_interval(repointed, spec, plan=dev_plan)) == "SYNTHETIC_ONLY"
    assert _code(lambda: draw_estimates(repointed, spec, 0, 1, plan=dev_plan)) == "SYNTHETIC_ONLY"
    # The same prepared aggregate remains valid on its own synthetic plan.
    validate_prepared_aggregate(prepared, synthetic)


def test_the_store_gates_on_the_content_synthetic_flag_only(dev_plan, tmp_path):
    # The store never sees a plan or binding: it refuses content not flagged synthetic, nothing more.
    artifact = serialize_artifact({
        "content": {"synthetic": False}, "plan_digest": dev_plan.plan_digest,
        "repeat_id": dev_plan.repeats[0].repeat_id, "terminal_status": "completed",
    })
    record = CompletionRecord(
        repeat_id=dev_plan.repeats[0].repeat_id,
        logical_content_sha256=hashlib.sha256(artifact.rstrip(b"\n")).hexdigest(),
        artifact_byte_hashes=((ARTIFACT_NAME, hashlib.sha256(artifact).hexdigest()),),
        terminal_status="completed",
    )
    store = SyntheticRepeatStore(tmp_path / "store")
    assert _code(lambda: store.commit(record, artifact, attempt_id="attempt-1")) == "SYNTHETIC_ONLY"
    assert store.completed_repeat_ids() == ()
    # Documented limit: a hand-built envelope flagged synthetic is accepted even though it names a
    # development plan. build_completion cannot produce it, but the store would not notice; the
    # precondition 4 store must bind the plan's binding before any non-synthetic persistence.
    flagged = serialize_artifact({
        "content": {"synthetic": True}, "plan_digest": dev_plan.plan_digest,
        "repeat_id": dev_plan.repeats[0].repeat_id, "terminal_status": "completed",
    })
    flagged_record = dataclasses.replace(
        record, logical_content_sha256=hashlib.sha256(flagged.rstrip(b"\n")).hexdigest(),
        artifact_byte_hashes=((ARTIFACT_NAME, hashlib.sha256(flagged).hexdigest()),))
    store.commit(flagged_record, flagged, attempt_id="attempt-2")
    assert store.completed_repeat_ids() == (record.repeat_id,)


def test_a_development_inventory_never_accepts_a_qualified_condition(dev_plan):
    # Condition inventory mirrors the aggregator: a non-synthetic plan cannot hold qualified evidence.
    assert _code(lambda: validate_condition_inventory(dev_plan, (_qualified_condition(dev_plan),))) == (
        "QUALIFICATION_UPGRADE")


def _qualified_condition(plan):
    from shiftguard.repeats.models import TerminalCondition
    from shiftguard.repeats.validation import expected_condition_slots

    slot = expected_condition_slots(plan.spec)[0]
    rows = len(plan.roles(slot.outer_seed).evaluation_ids)
    return TerminalCondition(
        condition_id=fake_digest("condition"), repeat_id=plan.repeat(slot.outer_seed, slot.inner_id).repeat_id,
        outer_seed=slot.outer_seed, inner_id=slot.inner_id, predictor=slot.predictor,
        scenario=slot.scenario, budget=slot.budget, requested_method=slot.method,
        resolved_method="raw", resolution_counts=(("raw", rows),), status="completed",
        metrics_available=True, qualification="qualified", reasons=(), fit_id=fake_digest("fit"))
