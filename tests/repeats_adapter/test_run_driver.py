"""Gate 8 restartable run driver, on fabricated rows and throwaway repositories.

Nothing here reads var/datasets, a real Bank file or the real repository var/: the driver runs
against a temporary git repository whose var/gate8-private is the evaluator-private root. The
loop logic is tested with injected prepare/execute stubs that return real fabricated coordinate
results; a couple of coordinates run through the real adapter on a reduced grid.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from development_fixtures import fake_digest
from shiftguard.repeats import development_store as store_module
from shiftguard.repeats import run_manifest as rm
from shiftguard.repeats.development_adapter import execute_coordinate, prepare_outer
from shiftguard.repeats.development_store import DevelopmentCoordinateStore
from shiftguard.repeats.models import (
    OUTER_SEEDS,
    PRIMARY_BUDGET,
    PRIMARY_SCENARIOS,
    PRIMARY_SOURCE_METHOD,
    PRIMARY_TARGET_METHOD,
    RepeatContractError,
)
from test_run_manifest import OWNER_TEXT, SCRIPTS, build_world, git, owner_file, protocol_paths

sys.path.insert(0, str(SCRIPTS))
driver = importlib.import_module("gate8_run_development")

SCOPE = {
    "scenarios": PRIMARY_SCENARIOS, "budgets": (0, PRIMARY_BUDGET),
    "methods": (PRIMARY_SOURCE_METHOD, PRIMARY_TARGET_METHOD),
}
FIRST = OUTER_SEEDS[0]
RUN_DAY = date(2026, 10, 20)
STORE_RELATIVE = rm.DEFAULT_STORE_ROOT_RELATIVE


class SimulatedCrash(BaseException):
    pass


_PREPARED: dict = {}
_RESULTS: dict = {}


def real_result(world, outer: int, inner: int):
    """A real fabricated coordinate, computed once per (plan, coordinate) for the whole module."""
    plan_id = world.plan.plan_digest
    if (plan_id, outer, inner) not in _RESULTS:
        if (plan_id, outer) not in _PREPARED:
            _PREPARED[(plan_id, outer)] = prepare_outer(world.dataset, world.plan, outer)
        _RESULTS[(plan_id, outer, inner)] = execute_coordinate(
            _PREPARED[(plan_id, outer)], inner, **SCOPE)
    return _RESULTS[(plan_id, outer, inner)]


@pytest.fixture
def ctx(tmp_path, monkeypatch) -> SimpleNamespace:
    world = build_world(tmp_path, monkeypatch)
    monkeypatch.setattr(store_module, "REPO_ROOT", world.repo)
    monkeypatch.setattr(store_module, "PRIVATE_VAR_ROOT", world.repo / "var")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(rm.dump_manifest(world.manifest))
    calls: list = []
    prepares: list = []

    def prepare(dataset, plan, outer):
        prepares.append(outer)
        return outer

    def execute(outer, inner, **scope):
        calls.append((outer, inner))
        return real_result(world, outer, inner)

    def run(*argv, **seams):
        options = dict(
            dataset_loader=world.loader, today=RUN_DAY, repo_root=world.repo,
            prepare=prepare, execute=execute, scope=SCOPE)
        options.update(seams)
        return driver.main(["--manifest", str(manifest_path), *argv], **options)

    return SimpleNamespace(
        world=world, manifest_path=manifest_path, calls=calls, prepares=prepares, run=run,
        prepare=prepare, execute=execute, root=world.repo / "var" / "gate8-private" / "bank-development-v1",
        schedule=world.manifest["schedule"])


def lock_path(ctx) -> Path:
    return ctx.root.parent / f"{ctx.root.name}.run.lock"


def open_store(ctx) -> DevelopmentCoordinateStore:
    return DevelopmentCoordinateStore(ctx.root, ctx.world.plan)


def coord(ctx, index: int) -> tuple[int, int]:
    item = ctx.schedule[index]
    return item["outer_seed"], item["inner_id"]


def repeat_id(ctx, index: int) -> str:
    return ctx.schedule[index]["repeat_id"]


def run_log(ctx) -> list[dict]:
    path = ctx.root.parent / f"{ctx.root.name}.run-log.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="ascii").splitlines()]


def summary(out: str) -> dict[str, int]:
    match = re.search(
        r"completed (\d+) failed (\d+) corrupt (\d+) remaining (\d+) attempted_this_run (\d+)", out)
    assert match, out
    return dict(zip(("completed", "failed", "corrupt", "remaining", "attempted"), map(int, match.groups())))


# ---------------------------------------------------------------- restart and skip

def test_limit_then_resume_skips_completed_coordinates_in_schedule_order(ctx, capsys):
    assert ctx.run("--limit", "1") == 0
    assert ctx.calls == [coord(ctx, 0)]
    assert summary(capsys.readouterr().out) == {
        "completed": 1, "failed": 0, "corrupt": 0, "remaining": 49, "attempted": 1}
    ctx.calls.clear()
    assert ctx.run("--limit", "2") == 0
    assert ctx.calls == [coord(ctx, 1), coord(ctx, 2)]
    assert summary(capsys.readouterr().out) == {
        "completed": 3, "failed": 0, "corrupt": 0, "remaining": 47, "attempted": 2}
    store = open_store(ctx)
    assert set(store.completed_repeat_ids()) == {repeat_id(ctx, i) for i in range(3)}
    for index in range(3):
        assert store.load(repeat_id(ctx, index)).result == real_result(ctx.world, *coord(ctx, index))


def test_limit_zero_runs_nothing_and_reports_the_inventory(ctx, capsys):
    assert ctx.run("--limit", "0") == 0
    assert ctx.calls == [] and ctx.prepares == []
    assert summary(capsys.readouterr().out)["remaining"] == 50
    assert run_log(ctx) == []


def test_outer_preparation_is_cached_per_outer_seed(ctx):
    assert ctx.run("--limit", "3") == 0
    assert ctx.prepares == [FIRST]


def test_a_process_crash_before_the_coordinate_commits_leaves_nothing_and_is_rerun(ctx):
    seen = []

    def crashing(outer, inner, **scope):
        seen.append((outer, inner))
        if len(seen) == 2:
            raise SimulatedCrash()
        return real_result(ctx.world, outer, inner)

    with pytest.raises(SimulatedCrash):
        ctx.run("--limit", "3", execute=crashing)
    store = open_store(ctx)
    assert store.completed_repeat_ids() == (repeat_id(ctx, 0),)
    assert _attempts_of(store, repeat_id(ctx, 1)) == ()  # a crash is not a recorded failure
    assert len(run_log(ctx)) == 1
    assert not lock_path(ctx).exists()  # the lock is released even by an exception unwinding
    assert ctx.run("--limit", "1") == 0
    assert ctx.calls == [coord(ctx, 1)]  # re-run: restart, not replacement


def _attempts_of(store, rid):
    return store.attempts(rid)


@pytest.mark.parametrize("seam, rerun", [
    ("before_stage", True), ("after_stage_artifact", True), ("after_publish_artifact", True),
    ("before_commit", True), ("after_commit", False),
])
def test_a_crash_at_every_persistence_seam_restarts_correctly(ctx, monkeypatch, seam, rerun):
    assert ctx.run("--limit", "1") == 0
    original = DevelopmentCoordinateStore._fault

    def fault(self, name):
        if name == seam:
            raise SimulatedCrash()
        return original(self, name)

    monkeypatch.setattr(DevelopmentCoordinateStore, "_fault", fault)
    with pytest.raises(SimulatedCrash):
        ctx.run("--limit", "1")
    monkeypatch.setattr(DevelopmentCoordinateStore, "_fault", original)
    completed = set(open_store(ctx).completed_repeat_ids())
    # Only the last seam is after the commit point: there the coordinate already counts.
    assert completed == ({repeat_id(ctx, 0)} if rerun else {repeat_id(ctx, 0), repeat_id(ctx, 1)})
    ctx.calls.clear()
    assert ctx.run("--limit", "1") == 0
    assert ctx.calls == ([coord(ctx, 1)] if rerun else [coord(ctx, 2)])
    assert not lock_path(ctx).exists()
    assert repeat_id(ctx, 1) in open_store(ctx).completed_repeat_ids()


# ---------------------------------------------------------------- failures

def test_a_failure_is_recorded_once_with_a_typed_code_and_never_rerun(ctx, capsys):
    def flaky(outer, inner, **scope):
        ctx.calls.append((outer, inner))
        if (outer, inner) == coord(ctx, 1):
            raise RepeatContractError("SOME_TYPED_CODE", "detail that must not be stored 0.123456")
        if (outer, inner) == coord(ctx, 2):
            raise ValueError("secret free-text 0.987654 label=1")
        return real_result(ctx.world, outer, inner)

    assert ctx.run("--limit", "3", execute=flaky) == 0
    assert summary(capsys.readouterr().out) == {
        "completed": 1, "failed": 2, "corrupt": 0, "remaining": 47, "attempted": 3}
    store = open_store(ctx)
    first, second = store.attempts(repeat_id(ctx, 1)), store.attempts(repeat_id(ctx, 2))
    assert [(a.outcome, a.reason) for a in first] == [("FAILED_ATTEMPT", "execute:SOME_TYPED_CODE")]
    assert [(a.outcome, a.reason) for a in second] == [("FAILED_ATTEMPT", "execute:EXC_ValueError")]
    assert "0.123456" not in first[0].audit_json and "0.987654" not in second[0].audit_json
    assert store.completed_repeat_ids() == (repeat_id(ctx, 0),)

    ctx.calls.clear()

    def always_fails(outer, inner, **scope):
        ctx.calls.append((outer, inner))
        raise RepeatContractError("LATER_FAILURE")

    assert ctx.run("--limit", "2", execute=always_fails) == 0
    assert ctx.calls == [coord(ctx, 3), coord(ctx, 4)]  # the recorded failures were not retried
    store = open_store(ctx)
    assert len(store.attempts(repeat_id(ctx, 1))) == 1 and len(store.attempts(repeat_id(ctx, 2))) == 1
    assert [a.outcome for a in store.attempts(repeat_id(ctx, 3))] == ["FAILED_ATTEMPT"]
    assert store.completed_repeat_ids() == (repeat_id(ctx, 0),)


def test_a_failed_outer_preparation_fails_every_remaining_coordinate_whatever_the_limit(ctx):
    seen = []

    def broken(dataset, plan, outer):
        seen.append(outer)
        raise MemoryError("out of memory 123.456")

    assert ctx.run("--limit", "1", prepare=broken) == 0
    assert seen == [FIRST]
    assert ctx.calls == []
    store = open_store(ctx)
    in_outer = [i for i, item in enumerate(ctx.schedule) if item["outer_seed"] == FIRST]
    assert len(in_outer) == 10
    for index in in_outer:
        assert [(a.outcome, a.reason) for a in store.attempts(repeat_id(ctx, index))] == [
            ("FAILED_ATTEMPT", "prepare:EXC_MemoryError")]
    other_outer = next(i for i, item in enumerate(ctx.schedule) if item["outer_seed"] != FIRST)
    assert store.attempts(repeat_id(ctx, other_outer)) == ()
    assert "123.456" not in json.dumps(run_log(ctx))
    assert len(run_log(ctx)) == 10
    # The next chunk moves on to the next outer; the failed ones are not retried.
    assert ctx.run("--limit", "0") == 0
    ctx.prepares.clear()
    ctx.calls.clear()
    assert ctx.run("--limit", "1", execute=lambda *a, **k: (_ for _ in ()).throw(
        RepeatContractError("ANY_CODE"))) == 0
    assert ctx.prepares == [ctx.schedule[other_outer]["outer_seed"]]


def test_a_result_for_the_wrong_coordinate_is_a_recorded_failure(ctx):
    def wrong(outer, inner, **scope):
        return real_result(ctx.world, outer, coord(ctx, 1)[1])

    assert ctx.run("--limit", "1", execute=wrong) == 0
    attempts = open_store(ctx).attempts(repeat_id(ctx, 0))
    assert [(a.outcome, a.reason) for a in attempts] == [("FAILED_ATTEMPT", "execute:RESULT_IDENTITY")]


# ---------------------------------------------------------------- corruption

def test_a_corrupt_completion_stops_the_run_and_is_never_overwritten(ctx, capsys):
    assert ctx.run("--limit", "2") == 0
    capsys.readouterr()
    blobs = sorted((ctx.root / "artifacts").iterdir())
    victim = blobs[0]
    victim.write_bytes(victim.read_bytes() + b" ")
    damaged = victim.read_bytes()
    ctx.calls.clear()
    assert ctx.run("--limit", "5") == 3
    out = capsys.readouterr().out
    assert "stopped" in out and summary(out)["corrupt"] == 1
    assert ctx.calls == []
    assert victim.read_bytes() == damaged
    assert run_log(ctx)[-1]["status"] == "stopped_corrupt"
    assert run_log(ctx)[-1]["error_code"] == "CORRUPT_COMPLETION"


# ---------------------------------------------------------------- gates and refusals

def test_date_gate_veto_and_dirty_tree_refuse_before_anything_runs(ctx, capsys):
    assert ctx.run(today=date(2026, 10, 19)) == 2 and "DATE_GATE" in capsys.readouterr().out
    assert ctx.run("--limit", "0", today=date(2026, 10, 20)) == 0
    capsys.readouterr()
    ctx.calls.clear()
    (ctx.world.repo / ".agent/OWNER_ACTIONS.md").write_text(owner_file("no"), encoding="utf-8")
    assert ctx.run("--limit", "1") == 2 and "OWNER_VETO" in capsys.readouterr().out
    (ctx.world.repo / ".agent/OWNER_ACTIONS.md").write_bytes(OWNER_TEXT)
    (ctx.world.repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 7\n")
    assert ctx.run("--limit", "1") == 2 and "SOURCE_DIRTY" in capsys.readouterr().out
    assert ctx.calls == []


def test_nothing_is_created_when_the_gate_refuses(ctx):
    assert ctx.run(today=date(2026, 10, 19)) == 2
    assert not (ctx.world.repo / "var").exists()


def test_the_date_gate_cannot_be_disabled_on_the_real_dataset(ctx, capsys):
    assert driver.main(
        ["--manifest", str(ctx.manifest_path), "--no-date-gate"], today=date(2026, 1, 1),
        repo_root=ctx.world.repo) == 2
    assert "DATE_GATE_REQUIRED" in capsys.readouterr().out
    assert ctx.run("--no-date-gate", "--limit", "0", today=date(2026, 1, 1)) == 0  # injected loader only
    assert ctx.run("--limit", "-1") == 2


def test_store_roots_outside_the_private_subtree_are_refused(ctx, capsys, tmp_path):
    repo = ctx.world.repo
    private = repo / "var" / "gate8-private"
    for bad, code in (
        (tmp_path / "elsewhere", "PRIVATE_ROOT_REQUIRED"),
        (repo / "var" / "store", "PRIVATE_ROOT_REQUIRED"),
        (repo / "var" / "artifacts" / "store", "PRIVATE_ROOT_REQUIRED"),
        (repo / "var", "PRIVATE_ROOT_REQUIRED"),
        (private, "PRIVATE_ROOT_REQUIRED"),
        (private / ".." / "store", "PRIVATE_ROOT_REQUIRED"),
        (repo / "store", "PRIVATE_ROOT_REQUIRED"),
        (Path("var") / "store", "PRIVATE_ROOT_REQUIRED"),
        (private / "verification" / "store", "PRIVATE_ROOT_FORBIDDEN"),
    ):
        assert ctx.run("--limit", "1", store_root=bad) == 2, bad
        assert code in capsys.readouterr().out
        # Nothing was created at (or through) any refused root, checked for every value.
        target = bad if Path(bad).is_absolute() else repo / bad
        assert not Path(target).resolve().exists(), bad
    assert ctx.calls == []
    assert not (tmp_path / "elsewhere").exists()


def test_the_store_root_cannot_be_chosen_on_the_command_line(ctx):
    with pytest.raises(SystemExit):
        driver.main(["--manifest", str(ctx.manifest_path), "--store-root", "var/gate8-private/x"])
    assert not (ctx.world.repo / "var").exists()


def test_test_seams_are_refused_without_an_injected_loader(ctx, capsys):
    base = ["--manifest", str(ctx.manifest_path)]
    for seams in (
        dict(scope=SCOPE), dict(today=RUN_DAY), dict(repo_root=ctx.world.repo),
        dict(prepare=ctx.prepare), dict(execute=ctx.execute), dict(store_root=Path("var/gate8-private/x")),
        dict(protocol_paths=protocol_paths(ctx.world.repo)),
    ):
        assert driver.main(base, **seams) == 2
        assert "SEAM_REQUIRES_LOADER" in capsys.readouterr().out
    assert not (ctx.world.repo / "var").exists()


def test_a_store_root_override_inside_the_private_subtree_is_accepted(ctx, capsys):
    assert ctx.run("--limit", "0", store_root=Path("var/gate8-private/alt")) == 0
    assert (ctx.world.repo / "var/gate8-private/alt/STORE.json").is_file()
    assert not ctx.root.exists()


def test_another_store_under_the_private_subtree_is_refused(ctx, capsys):
    assert ctx.run("--limit", "1") == 0
    capsys.readouterr()
    ctx.calls.clear()
    # A failure recorded in this store cannot be dodged by pointing at a fresh store root.
    assert ctx.run("--limit", "1", store_root=Path("var/gate8-private/alt")) == 2
    assert "OTHER_STORE_PRESENT" in capsys.readouterr().out
    assert ctx.calls == [] and not (ctx.world.repo / "var/gate8-private/alt").exists()


def test_a_second_run_is_refused_while_the_lock_file_exists(ctx, capsys):
    lock_path(ctx).parent.mkdir(parents=True)
    lock_path(ctx).write_text("4242\n", encoding="ascii")
    assert ctx.run("--limit", "1") == 2
    out = capsys.readouterr().out
    assert "RUN_LOCKED" in out and str(lock_path(ctx).resolve()) in out
    assert ctx.calls == [] and lock_path(ctx).exists()  # a foreign lock is never removed
    lock_path(ctx).unlink()
    assert ctx.run("--limit", "1") == 0
    assert not lock_path(ctx).exists()


def test_a_manifest_naming_a_root_outside_the_private_subtree_is_refused(ctx, capsys):
    forged = rm.seal_manifest({**ctx.world.manifest, "store_root_relative": "var/artifacts/x"})
    ctx.manifest_path.write_bytes(rm.dump_manifest(forged))
    assert ctx.run("--limit", "1") == 2
    assert "PRIVATE_ROOT_REQUIRED" in capsys.readouterr().out
    assert ctx.calls == []


def test_a_tampered_or_drifted_manifest_is_refused(ctx, capsys):
    schedule = list(reversed(ctx.world.manifest["schedule"]))
    for tampered, expected in (
        ({**ctx.world.manifest, "schedule": schedule}, "MANIFEST_DIGEST"),
        (rm.seal_manifest({**ctx.world.manifest, "schedule": schedule}), "MANIFEST_SCHEDULE"),
    ):
        ctx.manifest_path.write_bytes(rm.dump_manifest(tampered))
        assert ctx.run("--limit", "1") == 2
        assert expected in capsys.readouterr().out
    ctx.manifest_path.write_bytes(rm.dump_manifest(ctx.world.manifest))
    # Source changed and committed after the freeze: the tree is clean but no longer the frozen one.
    (ctx.world.repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 8\n")
    git(ctx.world.repo, "commit", "-q", "-am", "source change")
    assert ctx.run("--limit", "1") == 2
    assert re.search(r"MANIFEST_(BINDING|SOURCE_DRIFT)", capsys.readouterr().out)
    assert ctx.calls == []


def test_a_changed_protocol_file_or_dataset_manifest_is_refused(ctx, capsys):
    protocol_paths(ctx.world.repo)[0].write_bytes(b"decisions v2\n")
    assert ctx.run("--limit", "1") == 2
    assert "MANIFEST_BINDING" in capsys.readouterr().out
    protocol_paths(ctx.world.repo)[0].write_bytes(b"decisions v1\n")
    wrong = lambda root: (ctx.world.dataset, fake_digest("a different manifest file"))  # noqa: E731
    assert ctx.run("--limit", "1", dataset_loader=wrong) == 2
    assert "MANIFEST_DATASET" in capsys.readouterr().out
    assert ctx.calls == []


# ---------------------------------------------------------------- the log and what is printed

def test_run_log_and_output_carry_only_ids_statuses_counts_and_timings(ctx, capsys):
    def mixed(outer, inner, **scope):
        if (outer, inner) == coord(ctx, 1):
            raise RepeatContractError("SOME_TYPED_CODE")
        return real_result(ctx.world, outer, inner)

    assert ctx.run("--limit", "3", execute=mixed) == 0
    out = capsys.readouterr().out
    log = run_log(ctx)
    assert len(log) == 3
    assert [entry["status"] for entry in log] == ["completed", "failed", "completed"]
    for entry in log:
        assert tuple(entry) == driver.LOG_FIELDS
        assert re.fullmatch(r"[0-9a-f]{64}", entry["repeat_id"])
        assert isinstance(entry["duration_seconds"], float) and entry["duration_seconds"] >= 0
        assert entry["error_code"] is None or isinstance(entry["error_code"], str)
        assert (entry["outer_seed"], entry["inner_id"]) in [coord(ctx, i) for i in range(3)]
    assert log[1]["error_code"] == "execute:SOME_TYPED_CODE"
    text = (ctx.root.parent / f"{ctx.root.name}.run-log.jsonl").read_text(encoding="ascii")
    for word in ("loss", "brier", "sum", "label", "prob", "estimate"):
        assert word not in text.lower()
    assert ctx.root.parent == ctx.world.repo / "var" / "gate8-private"
    assert not re.search(r"\d+\.\d+", out)  # no float of any kind is printed
    for word in ("loss", "brier", "label", "row_id"):
        assert word not in out.lower()


# ---------------------------------------------------------------- the real adapter, reduced grid

def test_two_real_coordinates_run_commit_and_resume(ctx, capsys):
    real_calls = []

    def counting(prepared, inner, **scope):
        real_calls.append(inner)
        return execute_coordinate(prepared, inner, **scope)

    assert driver.main(
        ["--manifest", str(ctx.manifest_path), "--limit", "1"], dataset_loader=ctx.world.loader,
        today=RUN_DAY, repo_root=ctx.world.repo, execute=counting, scope=SCOPE) == 0
    assert real_calls == [coord(ctx, 0)[1]]
    assert summary(capsys.readouterr().out)["completed"] == 1
    store = open_store(ctx)
    stored = store.load(repeat_id(ctx, 0))
    assert stored.result == real_result(ctx.world, *coord(ctx, 0))
    # Resume: the first coordinate is byte-verified and skipped; the second is the one executed.
    assert driver.main(
        ["--manifest", str(ctx.manifest_path), "--limit", "1"], dataset_loader=ctx.world.loader,
        today=RUN_DAY, repo_root=ctx.world.repo, execute=counting, scope=SCOPE) == 0
    assert real_calls == [coord(ctx, 0)[1], coord(ctx, 1)[1]]
    assert set(open_store(ctx).completed_repeat_ids()) == {repeat_id(ctx, 0), repeat_id(ctx, 1)}
    assert open_store(ctx).load(repeat_id(ctx, 1)).result == real_result(ctx.world, *coord(ctx, 1))


# ---------------------------------------------------------------- grid completeness, races, conflicts

def raising(code: str):
    def execute(outer, inner, **scope):
        raise RepeatContractError(code)
    return execute


def _other_content(result):
    """Same repeat, a valid coordinate, one paired sum changed."""
    cells = list(result.pair_cells)
    cell = next(c for c in cells if c.paired_loss_sum_by_group is not None)
    sums = list(cell.paired_loss_sum_by_group)
    position = next(i for i, value in enumerate(sums) if value != 0.0)
    sums[position] = sums[position] / 2
    cells[cells.index(cell)] = dataclasses.replace(cell, paired_loss_sum_by_group=tuple(sums))
    return dataclasses.replace(result, pair_cells=tuple(cells))


def test_the_expected_grid_is_the_full_grid_unless_a_test_scope_narrows_it(ctx):
    plan = ctx.world.plan
    assert len(driver.expected_slots(plan, FIRST, 51001, {})) == 400
    narrowed = driver.expected_slots(plan, FIRST, 51001, SCOPE)
    assert 0 < len(narrowed) < 400
    assert all(s.method in SCOPE["methods"] and s.budget in SCOPE["budgets"] for s in narrowed)


def test_an_incomplete_condition_grid_is_a_typed_failure_before_commit(ctx):
    def truncated(outer, inner, **scope):
        result = real_result(ctx.world, outer, inner)
        return dataclasses.replace(result, conditions=result.conditions[:-1])

    assert ctx.run("--limit", "1", execute=truncated) == 0
    store = open_store(ctx)
    assert [(a.outcome, a.reason) for a in store.attempts(repeat_id(ctx, 0))] == [
        ("FAILED_ATTEMPT", "validate:INCOMPLETE_GRID")]
    assert store.completed_repeat_ids() == ()


def test_a_failure_is_never_recorded_over_an_existing_completion(ctx, capsys):
    def racing(outer, inner, **scope):
        result = real_result(ctx.world, outer, inner)
        open_store(ctx).commit(result, attempt_id="side")  # another writer completes it first
        raise RuntimeError("late failure after the completion landed")

    assert ctx.run("--limit", "1", execute=racing) == 0
    store = open_store(ctx)
    assert store.completed_repeat_ids() == (repeat_id(ctx, 0),)
    assert all(a.outcome != "FAILED_ATTEMPT" for a in store.attempts(repeat_id(ctx, 0)))
    entry = run_log(ctx)[-1]
    assert (entry["status"], entry["error_code"]) == ("completed", "warning:COMPLETION_EXISTS")
    assert summary(capsys.readouterr().out)["failed"] == 0


def test_a_conflicting_commit_is_logged_and_never_overwrites(ctx, capsys):
    original = real_result(ctx.world, *coord(ctx, 0))

    def different(outer, inner, **scope):
        open_store(ctx).commit(original, attempt_id="side")
        return _other_content(original)

    assert ctx.run("--limit", "1", execute=different) == 0
    entry = run_log(ctx)[-1]
    assert (entry["status"], entry["error_code"]) == ("conflict", "commit:COMMIT_CONFLICT")
    store = open_store(ctx)
    assert store.completed_repeat_ids() == (repeat_id(ctx, 0),)
    assert store.load(repeat_id(ctx, 0)).result == original
    assert summary(capsys.readouterr().out)["completed"] == 1


def test_an_unparseable_attempt_record_is_a_typed_refusal(ctx, capsys):
    assert ctx.run("--limit", "1", execute=raising("ANY_CODE")) == 0
    attempt = next((ctx.root / "attempts" / repeat_id(ctx, 0)).iterdir())
    attempt.write_bytes(b"not json at all")
    capsys.readouterr()
    assert ctx.run("--limit", "1") == 2
    assert "ATTEMPT_RECORD_UNREADABLE" in capsys.readouterr().out
    assert not lock_path(ctx).exists()


def test_the_veto_is_rechecked_before_every_coordinate(ctx, capsys):
    def vetoing(outer, inner, **scope):
        ctx.calls.append((outer, inner))
        (ctx.world.repo / ".agent/OWNER_ACTIONS.md").write_text(owner_file("stop"), encoding="utf-8")
        return real_result(ctx.world, outer, inner)

    assert ctx.run("--limit", "3", execute=vetoing) == 2
    out = capsys.readouterr().out
    assert "stopped: OWNER_VETO" in out and summary(out)["completed"] == 1
    assert ctx.calls == [coord(ctx, 0)]


def test_the_manifest_environment_must_match_the_running_one(ctx, capsys, monkeypatch):
    env = rm.current_environment()
    monkeypatch.setattr(rm, "current_environment", lambda: {**env, "python": "2.7.18"})
    assert ctx.run("--limit", "1") == 2
    assert "MANIFEST_ENVIRONMENT" in capsys.readouterr().out
    assert ctx.calls == []


def test_the_real_data_path_requires_a_tracked_unmodified_manifest(ctx, capsys, monkeypatch):
    repo = ctx.world.repo
    monkeypatch.setattr(driver, "ROOT", repo)  # the real path, pointed at the throwaway repository
    monkeypatch.setattr(rm, "kolkata_today", lambda now=None: RUN_DAY)
    argv = ["--manifest", str(ctx.manifest_path)]
    assert driver.main(argv) == 2 and "MANIFEST_OUTSIDE_REPO" in capsys.readouterr().out
    inside = repo / rm.DEFAULT_MANIFEST_RELATIVE
    inside.parent.mkdir(parents=True)
    inside.write_bytes(rm.dump_manifest(ctx.world.manifest))
    argv = ["--manifest", str(inside)]
    assert driver.main(argv) == 2 and "MANIFEST_UNTRACKED" in capsys.readouterr().out
    (repo / ".gitattributes").write_text("docs/research/*.json text eol=lf\n", encoding="ascii")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "manifest")
    inside.write_bytes(rm.dump_manifest(ctx.world.manifest) + b" ")
    assert driver.main(argv) == 2 and "MANIFEST_MODIFIED" in capsys.readouterr().out
    # Tracked and unchanged: the checks pass and the real loader is reached (the throwaway repo
    # has no dataset, so it stops there, before any plan or coordinate).
    git(repo, "checkout", "--", rm.DEFAULT_MANIFEST_RELATIVE)
    assert driver.main(argv) == 1 and "FileNotFoundError" in capsys.readouterr().out
    assert not (repo / "var").exists()
