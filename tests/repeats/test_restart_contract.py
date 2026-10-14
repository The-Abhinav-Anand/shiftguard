from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import shiftguard
from crash_driver import CRASH_EXIT_CODE, DRIVER_CONTENT
from repeat_fixtures import fake_digest, synthetic_plan
from shiftguard.repeats.completion import (
    IDEMPOTENT_REUSE,
    INSERT,
    CompletionRecord,
    Conflict,
    build_completion,
    completion_action,
    serialize_artifact,
)
from shiftguard.repeats.models import RepeatContractError
from shiftguard.repeats.synthetic_store import SEAMS, SyntheticRepeatStore


DRIVER = Path(__file__).with_name("crash_driver.py")
REPO_ROOT = Path(shiftguard.__file__).resolve().parents[1]
CONTENT = {"synthetic": True, "summary": {"theta": -0.1, "cells": 400}}


class SimulatedCrash(BaseException):
    pass


def _code(call) -> str:
    with pytest.raises(RepeatContractError) as raised:
        call()
    return raised.value.code


@pytest.fixture(scope="module")
def plan():
    return synthetic_plan()


def _build(plan, index=0, content=None, status="completed"):
    return build_completion(plan, plan.repeats[index].repeat_id, content or CONTENT, status)


def _record(**overrides) -> CompletionRecord:
    values = {
        "repeat_id": fake_digest("repeat"),
        "logical_content_sha256": fake_digest("logical"),
        "artifact_byte_hashes": (("completion.json", fake_digest("bytes")),),
        "terminal_status": "completed",
    }
    values.update(overrides)
    return CompletionRecord(**values)


def _crash_in_subprocess(root: Path, seam: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "-B", str(DRIVER), str(root), seam],
        capture_output=True, text=True, timeout=180, cwd=str(REPO_ROOT), env=environment,
    )


def test_logical_contract_inserts_reuses_and_conflicts():
    record = _record()
    assert completion_action(None, record) is INSERT
    assert completion_action(record, _record()) is IDEMPOTENT_REUSE

    other_content = _record(logical_content_sha256=fake_digest("other-logical"))
    conflict = completion_action(record, other_content)
    assert isinstance(conflict, Conflict)
    assert conflict.reason == "logical_content_differs"
    assert (conflict.existing_logical_sha256, conflict.incoming_logical_sha256) == (
        record.logical_content_sha256, other_content.logical_content_sha256,
    )
    other_bytes = _record(artifact_byte_hashes=(("completion.json", fake_digest("other-bytes")),))
    assert completion_action(record, other_bytes).reason == "artifact_bytes_differ"
    other_status = _record(terminal_status="failed")
    assert completion_action(record, other_status).reason == "terminal_status_differs"
    assert _code(
        lambda: completion_action(record, _record(repeat_id=fake_digest("another-repeat")))
    ) == "REPEAT_ID_MISMATCH"


@pytest.mark.parametrize("overrides, code", [
    ({"repeat_id": fake_digest("repeat")[:24]}, "DIGEST"),
    ({"repeat_id": "../" + fake_digest("repeat")[:61]}, "DIGEST"),
    ({"logical_content_sha256": "not-a-digest"}, "DIGEST"),
    ({"artifact_byte_hashes": ()}, "EMPTY_VALUE"),
    ({"artifact_byte_hashes": [("completion.json", fake_digest("bytes"))]}, "IMMUTABLE_TUPLE"),
    ({"artifact_byte_hashes": (("completion.json", "short"),)}, "DIGEST"),
    ({"terminal_status": "running"}, "TERMINAL_STATUS"),
])
def test_completion_record_rejects_malformed_identity(overrides, code):
    assert _code(lambda: _record(**overrides)) == code


def test_identity_ignores_scheduling_but_binds_plan_repeat_content_and_status(plan):
    record, artifact = _build(plan)
    again, again_bytes = _build(plan)
    assert (record, artifact) == (again, again_bytes)
    assert record.artifact_byte_hashes == (
        ("completion.json", hashlib.sha256(artifact).hexdigest()),
    )
    assert artifact.endswith(b"\n") and b"\r" not in artifact and artifact.isascii()
    assert artifact == serialize_artifact({
        "content": CONTENT, "plan_digest": plan.plan_digest,
        "repeat_id": plan.repeats[0].repeat_id, "terminal_status": "completed",
    })
    reordered = {"summary": {"cells": 400, "theta": -0.1}, "synthetic": True}
    assert _build(plan, content=reordered)[0] == record

    assert _build(plan, index=1)[0].logical_content_sha256 != record.logical_content_sha256
    changed = {"synthetic": True, "summary": {"theta": -0.2, "cells": 400}}
    assert _build(plan, content=changed)[0].logical_content_sha256 != record.logical_content_sha256
    assert _build(plan, status="failed")[0].logical_content_sha256 != record.logical_content_sha256


@pytest.mark.parametrize("content, code", [
    ({"summary": {"theta": -0.1}}, "SYNTHETIC_ONLY"),
    ({"synthetic": False, "summary": {}}, "SYNTHETIC_ONLY"),
    ({"synthetic": True, "attempt_id": "a1"}, "RUNTIME_METADATA_IN_IDENTITY"),
    ({"synthetic": True, "summary": {"completed_at": "2026-10-12T00:00:00Z"}}, "RUNTIME_METADATA_IN_IDENTITY"),
    ({"synthetic": True, "summary": {"host_path": "C:/tmp"}}, "RUNTIME_METADATA_IN_IDENTITY"),
    ({"synthetic": True, "value": float("nan")}, "CONTENT_NOT_CANONICAL"),
    ({"synthetic": True, "value": {1, 2}}, "CONTENT_NOT_CANONICAL"),
])
def test_completion_content_must_be_fabricated_canonical_and_free_of_runtime_metadata(
    plan, content, code,
):
    assert _code(lambda: _build(plan, content=content)) == code


def test_completion_requires_a_repeat_of_the_plan_and_a_terminal_status(plan):
    assert _code(
        lambda: build_completion(plan, fake_digest("not-in-plan"), CONTENT, "completed")
    ) == "UNDECLARED_REPEAT"
    assert _code(lambda: _build(plan, status="running")) == "TERMINAL_STATUS"
    forged = dataclasses.replace(plan, plan_digest="0" * 64)
    assert _code(lambda: _build(forged)) == "PLAN_INTEGRITY"


def test_commit_then_retry_returns_the_identical_immutable_content(plan, tmp_path):
    record, artifact = _build(plan)
    store = SyntheticRepeatStore(tmp_path / "store")
    first = store.commit(record, artifact, attempt_id="attempt-1", audit={"scheduled_order": 7})
    assert first.decision is INSERT and first.record == record

    restarted = SyntheticRepeatStore(tmp_path / "store")
    stored = restarted.load(record.repeat_id)
    assert (stored.record, stored.artifact) == (record, artifact)
    retry = restarted.commit(
        record, artifact, attempt_id="attempt-2",
        audit={"scheduled_order": 1, "worker": "another-process"},
    )
    assert retry.decision is IDEMPOTENT_REUSE and retry.record == record
    assert restarted.completed_repeat_ids() == (record.repeat_id,)
    assert restarted.load(record.repeat_id).artifact == artifact
    assert [attempt.attempt_id for attempt in restarted.attempts(record.repeat_id)] == [
        "attempt-1", "attempt-2",
    ]


def test_different_digest_under_the_same_repeat_conflicts_and_never_overwrites(plan, tmp_path):
    record, artifact = _build(plan)
    store = SyntheticRepeatStore(tmp_path / "store")
    store.commit(record, artifact, attempt_id="attempt-1")
    changed, changed_artifact = _build(
        plan, content={"synthetic": True, "summary": {"theta": 0.3, "cells": 400}}
    )
    assert changed.repeat_id == record.repeat_id
    result = store.commit(changed, changed_artifact, attempt_id="attempt-2")
    assert isinstance(result.decision, Conflict)
    assert result.decision.reason == "logical_content_differs"
    assert result.record == record
    stored = SyntheticRepeatStore(tmp_path / "store").load(record.repeat_id)
    assert (stored.record, stored.artifact) == (record, artifact)
    assert store.completed_repeat_ids() == (record.repeat_id,)
    assert [attempt.outcome for attempt in store.attempts(record.repeat_id)] == [
        "INSERT", "CONFLICT",
    ]


@pytest.mark.parametrize("seam", [seam for seam in SEAMS if seam != "after_commit"])
def test_injected_crash_before_the_atomic_commit_counts_no_completion(plan, tmp_path, seam):
    record, artifact = _build(plan)

    def crash(name):
        if name == seam:
            raise SimulatedCrash(name)

    with pytest.raises(SimulatedCrash):
        SyntheticRepeatStore(tmp_path / "store", fault=crash).commit(
            record, artifact, attempt_id="crashed"
        )
    restarted = SyntheticRepeatStore(tmp_path / "store")
    assert restarted.load(record.repeat_id) is None
    assert restarted.completed_repeat_ids() == ()
    result = restarted.commit(record, artifact, attempt_id="after-restart")
    assert result.decision is INSERT
    assert restarted.completed_repeat_ids() == (record.repeat_id,)


def test_injected_crash_after_the_atomic_commit_is_recovered_as_reuse(plan, tmp_path):
    record, artifact = _build(plan)

    def crash(name):
        if name == "after_commit":
            raise SimulatedCrash(name)

    with pytest.raises(SimulatedCrash):
        SyntheticRepeatStore(tmp_path / "store", fault=crash).commit(
            record, artifact, attempt_id="crashed"
        )
    restarted = SyntheticRepeatStore(tmp_path / "store")
    assert restarted.completed_repeat_ids() == (record.repeat_id,)
    assert restarted.commit(record, artifact, attempt_id="retry").decision is IDEMPOTENT_REUSE
    assert restarted.load(record.repeat_id).artifact == artifact


@pytest.mark.parametrize("seam", ["after_stage_artifact", "before_commit"])
def test_killed_process_before_commit_leaves_no_counted_repeat(plan, tmp_path, seam):
    root = tmp_path / "store"
    completed = _crash_in_subprocess(root, seam)
    assert completed.returncode == CRASH_EXIT_CODE, completed.stdout + completed.stderr

    record, artifact = _build(plan, content=DRIVER_CONTENT)
    restarted = SyntheticRepeatStore(root)
    assert restarted.load(record.repeat_id) is None
    assert restarted.completed_repeat_ids() == ()
    assert restarted.orphaned_staging()
    assert restarted.commit(record, artifact, attempt_id="after-kill").decision is INSERT
    assert restarted.completed_repeat_ids() == (record.repeat_id,)
    # Interrupted staging files are evidence of the failed attempt and are kept.
    assert restarted.orphaned_staging()


def test_killed_process_after_commit_is_reused_by_the_restarted_store(plan, tmp_path):
    root = tmp_path / "store"
    completed = _crash_in_subprocess(root, "after_commit")
    assert completed.returncode == CRASH_EXIT_CODE, completed.stdout + completed.stderr

    record, artifact = _build(plan, content=DRIVER_CONTENT)
    restarted = SyntheticRepeatStore(root)
    stored = restarted.load(record.repeat_id)
    assert (stored.record, stored.artifact) == (record, artifact)
    assert restarted.commit(record, artifact, attempt_id="retry").decision is IDEMPOTENT_REUSE
    assert restarted.completed_repeat_ids() == (record.repeat_id,)

    clean = _crash_in_subprocess(root, "never")
    assert clean.returncode == 0 and clean.stdout.strip() == "IDEMPOTENT_REUSE"


def test_failed_attempts_and_terminal_failures_are_retained_and_not_counted(plan, tmp_path):
    record, artifact = _build(plan)
    failure, failure_artifact = _build(
        plan, index=1, status="failed",
        content={"synthetic": True, "reasons": ["raw prediction failed"]},
    )
    store = SyntheticRepeatStore(tmp_path / "store")
    store.record_failed_attempt(record.repeat_id, "attempt-1", "worker lost its lease")
    store.record_failed_attempt(record.repeat_id, "attempt-2", "interrupted write")
    assert store.completed_repeat_ids() == ()
    store.commit(record, artifact, attempt_id="attempt-3")
    store.commit(failure, failure_artifact, attempt_id="attempt-1")

    restarted = SyntheticRepeatStore(tmp_path / "store")
    attempts = restarted.attempts(record.repeat_id)
    assert [(a.attempt_id, a.outcome) for a in attempts] == [
        ("attempt-1", "FAILED_ATTEMPT"), ("attempt-2", "FAILED_ATTEMPT"), ("attempt-3", "INSERT"),
    ]
    assert attempts[0].reason == "worker lost its lease"
    # Completions come from committed records, never from the number of attempts.
    assert restarted.completed_repeat_ids() == (record.repeat_id,)
    assert restarted.terminal_failure_ids() == (failure.repeat_id,)
    assert _code(
        lambda: restarted.record_failed_attempt(record.repeat_id, "attempt-1", "again")
    ) == "DUPLICATE_ATTEMPT"


def test_identifiers_sharing_a_truncated_prefix_never_overwrite_each_other(tmp_path):
    prefix = fake_digest("shared-prefix")[:24]
    first_id, second_id = prefix + "a" * 40, prefix + "b" * 40
    store = SyntheticRepeatStore(tmp_path / "store")
    committed = {}
    for repeat_id in (first_id, second_id):
        artifact = serialize_artifact({
            "content": {"synthetic": True, "marker": repeat_id[-1]},
            "plan_digest": fake_digest("plan"), "repeat_id": repeat_id,
            "terminal_status": "completed",
        })
        record = CompletionRecord(
            repeat_id=repeat_id,
            logical_content_sha256=hashlib.sha256(artifact.rstrip(b"\n")).hexdigest(),
            artifact_byte_hashes=(("completion.json", hashlib.sha256(artifact).hexdigest()),),
            terminal_status="completed",
        )
        assert store.commit(record, artifact, attempt_id="attempt-1").decision is INSERT
        committed[repeat_id] = (record, artifact)
    for repeat_id, (record, artifact) in committed.items():
        stored = store.load(repeat_id)
        assert (stored.record, stored.artifact) == (record, artifact)
    assert store.completed_repeat_ids() == tuple(sorted(committed))
    assert _code(lambda: store.load(prefix)) == "DIGEST"


def test_store_rejects_bytes_that_do_not_match_their_record(plan, tmp_path):
    record, artifact = _build(plan)
    store = SyntheticRepeatStore(tmp_path / "store")
    assert _code(
        lambda: store.commit(record, artifact + b" ", attempt_id="attempt-1")
    ) == "ARTIFACT_HASH_MISMATCH"
    crlf = artifact.replace(b"\n", b"\r\n")
    crlf_record = dataclasses.replace(
        record, artifact_byte_hashes=(("completion.json", hashlib.sha256(crlf).hexdigest()),)
    )
    assert _code(
        lambda: store.commit(crlf_record, crlf, attempt_id="attempt-2")
    ) == "ARTIFACT_NOT_CANONICAL"
    relabelled = dataclasses.replace(record, logical_content_sha256=fake_digest("other"))
    assert _code(
        lambda: store.commit(relabelled, artifact, attempt_id="attempt-3")
    ) == "LOGICAL_HASH_MISMATCH"
    real = serialize_artifact({
        "content": {"synthetic": False}, "plan_digest": plan.plan_digest,
        "repeat_id": record.repeat_id, "terminal_status": "completed",
    })
    real_record = CompletionRecord(
        repeat_id=record.repeat_id,
        logical_content_sha256=hashlib.sha256(real.rstrip(b"\n")).hexdigest(),
        artifact_byte_hashes=(("completion.json", hashlib.sha256(real).hexdigest()),),
        terminal_status="completed",
    )
    assert _code(lambda: store.commit(real_record, real, attempt_id="attempt-4")) == "SYNTHETIC_ONLY"
    assert store.completed_repeat_ids() == ()


def test_damaged_completion_is_reported_and_never_counted(plan, tmp_path):
    record, artifact = _build(plan)
    other, other_artifact = _build(plan, index=1)
    store = SyntheticRepeatStore(tmp_path / "store")
    store.commit(record, artifact, attempt_id="attempt-1")
    store.commit(other, other_artifact, attempt_id="attempt-1")
    marker = tmp_path / "store" / "completions" / f"{record.repeat_id}.json"
    marker.write_bytes(marker.read_bytes()[:40])

    restarted = SyntheticRepeatStore(tmp_path / "store")
    assert restarted.completed_repeat_ids() == (other.repeat_id,)
    assert restarted.corrupt_completion_ids() == (record.repeat_id,)
    assert _code(lambda: restarted.load(record.repeat_id)) == "CORRUPT_COMPLETION"
    assert _code(
        lambda: restarted.commit(record, artifact, attempt_id="attempt-2")
    ) == "CORRUPT_COMPLETION"


def test_store_refuses_a_directory_it_did_not_create(tmp_path):
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "results.csv").write_text("not a synthetic store", encoding="utf-8")
    assert _code(lambda: SyntheticRepeatStore(foreign)) == "STORE_IDENTITY"
    assert (foreign / "results.csv").read_text(encoding="utf-8") == "not a synthetic store"
    assert _code(
        lambda: SyntheticRepeatStore(tmp_path / "store").load("../escape")
    ) == "DIGEST"
    store = SyntheticRepeatStore(tmp_path / "store")
    assert _code(
        lambda: store.record_failed_attempt(fake_digest("repeat"), "../attempt", "reason")
    ) == "IDENTIFIER"


def test_repeat_store_is_not_reachable_from_the_public_api():
    script = (
        "import sys\n"
        "import shiftguard.api.main as main\n"
        "loaded = sorted(name for name in sys.modules if name.startswith('shiftguard.repeats'))\n"
        "routes = sorted(path for path in main.app.openapi()['paths'] if 'repeat' in path.lower())\n"
        "print(loaded, routes)\n"
        "raise SystemExit(1 if loaded or routes else 0)\n"
    )
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script], capture_output=True, text=True,
        timeout=180, cwd=str(REPO_ROOT), env=environment,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


# ---------------------------------------------------------------- OR-06: accounting survives the store

def _accounting_content(plan):
    from repeat_fixtures import primary_cell
    from test_repeat_validation import BINNED_SLOT, _condition

    key = (41001, 51001, "logistic_regression", "history_block_0_50")
    mixed = primary_cell(
        plan, key, sums=(0.2, -0.6),
        source_resolution_counts=(("source_temperature", 1), ("source_remasked_temperature", 1),
                                  ("source_fraction_binned_temperature", 2)),
    )
    condition = _condition(
        plan, BINNED_SLOT, resolved_method="source_fraction_binned_temperature",
        resolution_counts=mixed.source_resolution_counts)
    content = {"synthetic": True, "cells": [mixed.to_canonical()], "conditions": [condition.to_canonical()]}
    return mixed, condition, content


def test_resolution_accounting_survives_serialization_and_store_reopen(plan, tmp_path):
    from shiftguard.repeats.models import PairedGroupLossCell, TerminalCondition

    mixed, condition, content = _accounting_content(plan)
    record, artifact = _build(plan, content=content)
    SyntheticRepeatStore(tmp_path / "store").commit(record, artifact, attempt_id="first")

    reopened = SyntheticRepeatStore(tmp_path / "store")  # a fresh process would see the same bytes
    stored = reopened.load(record.repeat_id)
    assert stored.artifact == artifact
    envelope = json.loads(stored.artifact.decode("ascii"))
    cell = PairedGroupLossCell.from_canonical(envelope["content"]["cells"][0])
    again = TerminalCondition.from_canonical(envelope["content"]["conditions"][0])
    assert (cell, again) == (mixed, condition)
    # The per-row mixture and the derived fallback flag are intact after the round trip.
    assert cell.source_resolution_counts == mixed.source_resolution_counts
    assert cell.has_fallback and cell.source_fallback_rows == 2
    assert cell.source_resolved_method == "source_fraction_binned_temperature"
    assert again.fallback_rows == 2 and again.row_count == 4


def test_a_stored_cell_from_the_earlier_record_version_is_refused_not_defaulted(plan, tmp_path):
    from shiftguard.repeats.models import PairedGroupLossCell

    mixed, _, content = _accounting_content(plan)
    old = dict(content["cells"][0])
    del old["target_resolution_counts"], old["source_resolution_counts"]
    old["record_version"] = "gate8-paired-cell-v1"
    legacy = {"synthetic": True, "cells": [old]}
    record, artifact = _build(plan, index=1, content=legacy)
    SyntheticRepeatStore(tmp_path / "store").commit(record, artifact, attempt_id="legacy")
    stored = SyntheticRepeatStore(tmp_path / "store").load(record.repeat_id)
    envelope = json.loads(stored.artifact.decode("ascii"))
    # The immutable bytes stay readable as bytes; interpreting them under the new schema fails clearly.
    assert envelope["content"]["cells"][0]["record_version"] == "gate8-paired-cell-v1"
    assert _code(lambda: PairedGroupLossCell.from_canonical(envelope["content"]["cells"][0])) == "RECORD_VERSION"
    # The original completion was not rewritten by the failed read.
    assert SyntheticRepeatStore(tmp_path / "store").load(record.repeat_id).artifact == artifact
