"""Gate 8 read-only development report, on fabricated rows and throwaway repositories.

Nothing here touches var/datasets, a real Bank file or the real repository var/. The stores are
built by the real run driver inside a temporary git repository, as in test_run_driver.py.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys

import pytest

from shiftguard.repeats import run_manifest as rm
from test_run_driver import (  # noqa: F401  (ctx is a fixture)
    RUN_DAY,
    SCRIPTS,
    coord,
    ctx,
    lock_path,
    open_store,
    repeat_id,
)
from test_run_manifest import OWNER_TEXT, owner_file, protocol_paths

sys.path.insert(0, str(SCRIPTS))
report_script = importlib.import_module("gate8_report_development")

LABEL = "development; Bank outcomes previously inspected; not confirmatory"


def report(ctx, out, *argv, **seams):
    options = dict(
        dataset_loader=ctx.world.loader, today=RUN_DAY, repo_root=ctx.world.repo)
    options.update(seams)
    return report_script.main(
        ["--manifest", str(ctx.manifest_path), "--out", str(out), *argv], **options)


@pytest.fixture
def out(tmp_path):
    folder = tmp_path / "reports"
    folder.mkdir()
    return folder / "report.json"


def load(out) -> dict:
    return json.loads(out.read_text(encoding="ascii"))


def snapshot(root) -> dict[str, str]:
    """Every file under a tree, by relative path, with its content hash."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix() + ("" if path.is_file() else "/"):
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        for path in sorted(root.rglob("*"))
    }


def damage_blob(ctx, index: int) -> None:
    marker = json.loads((ctx.root / "completions" / f"{repeat_id(ctx, index)}.json").read_text("ascii"))
    blob = ctx.root / "artifacts" / f"{marker['artifact_byte_hashes'][0][1]}.json"
    blob.write_bytes(blob.read_bytes() + b" ")


def populate(ctx, failing: int = 1, completed: int = 3) -> None:
    """The first ``completed`` coordinates run through the real driver; ``failing`` fails with a typed code."""
    from test_run_driver import RepeatContractError, real_result

    def execute(outer, inner, **scope):
        if (outer, inner) == coord(ctx, failing):
            raise RepeatContractError("SOME_TYPED_CODE", "detail 0.123456 that must not be reported")
        return real_result(ctx.world, outer, inner)

    assert ctx.run("--limit", str(completed), execute=execute) == 0


# ---------------------------------------------------------------- inventory

def test_inventory_lists_all_fifty_coordinates_with_completed_failed_corrupt_and_missing(ctx, out):
    populate(ctx, failing=1, completed=4)  # coordinates 0, 2, 3 complete; 1 fails
    damage_blob(ctx, 3)
    assert report(ctx, out) == 0
    data = load(out)
    assert data["label"] == LABEL
    assert data["execution_tier"] == "development"
    assert data["split_profile"] == "bank_overlap_diagnostic"
    assert data["manifest_digest"] == ctx.world.manifest["manifest_digest"]
    assert data["plan_digest"] == ctx.world.plan.plan_digest
    assert data["claim_scope"] == ctx.world.manifest["claim_scope"]
    inventory = data["inventory"]
    assert [(e["outer_seed"], e["inner_id"], e["repeat_id"]) for e in inventory] == [
        (i["outer_seed"], i["inner_id"], i["repeat_id"]) for i in ctx.schedule]
    status = [e["status"] for e in inventory]
    assert status[:4] == ["completed", "failed", "completed", "corrupt"]
    assert set(status[4:]) == {"missing"}
    assert inventory[1]["failure_code"] == "execute:SOME_TYPED_CODE"
    assert all(e["failure_code"] is None for i, e in enumerate(inventory) if i not in (1, 3))
    assert data["totals"] == {
        "scheduled": 50, "completed": 2, "failed": 1, "corrupt": 1, "missing": 46,
        "completed_with_prior_failed_attempt": 0, "unscheduled_completion_files": 0}
    assert inventory[3]["failure_code"] == "CORRUPT_COMPLETION"
    assert data["accounting_scope"] == "completed coordinates only"
    assert data["script_sha256"] == hashlib.sha256(
        (SCRIPTS / "gate8_report_development.py").read_bytes()).hexdigest()
    assert inventory[0]["cells_with_fallback"] is not None and inventory[1]["cells_with_fallback"] is None
    assert data["primary"]["interval_code"] == "INTERVAL_REQUIRES_PRIMARY_ESTIMATE"
    assert "0.123456" not in out.read_text("ascii")


def test_an_absent_store_is_all_missing_and_is_not_created(ctx, out):
    assert report(ctx, out) == 0
    data = load(out)
    assert data["totals"]["missing"] == 50 and data["totals"]["completed"] == 0
    assert data["primary"]["status"] == "missing_evidence"
    assert not ctx.root.exists() and not (ctx.world.repo / "var").exists()
    assert not lock_path(ctx).exists()


def test_a_half_created_store_is_refused_not_completed(ctx, out, capsys):
    ctx.root.mkdir(parents=True)
    (ctx.root / "STORE.json").write_bytes(b"{}\n")
    before = snapshot(ctx.root)
    assert report(ctx, out) == 2
    assert "STORE_INCOMPLETE" in capsys.readouterr().out
    assert snapshot(ctx.root) == before and not out.exists()


# ---------------------------------------------------------------- accounting and the primary result

def test_accounting_counts_and_primary_is_typed_missing_evidence_with_null_estimate(ctx, out):
    populate(ctx, failing=1, completed=3)
    store = open_store(ctx)
    cells = [c for i in (0, 2) for c in store.load(repeat_id(ctx, i)).result.pair_cells]
    assert report(ctx, out) == 0
    data = load(out)
    pair = data["accounting"]["pair_cells"]
    assert pair["total"] == len(cells) > 0
    assert pair["by_qualification"] == {"unknown_authority": len(cells)}
    assert sum(pair["by_reason_code"].values()) >= len(cells)
    assert pair["with_fallback"] == sum(1 for c in cells if c.has_fallback)
    conditions = data["accounting"]["conditions"]
    assert set(conditions["by_qualification"]) <= {"unknown_authority", "failed", "qualified"}
    assert conditions["total"] == sum(conditions["by_qualification"].values()) > 0
    primary = data["primary"]
    assert primary["status"] == "missing_evidence"
    assert primary["code"] == "PRIMARY_EVIDENCE_UNAVAILABLE"
    assert primary["estimate"] is None and primary["interval"] is None
    assert primary["required_cell_count"] == 400
    assert primary["missing_cell_count"] + primary["unavailable_cell_count"] == 400
    assert primary["unavailable_cell_count"] == len(cells)
    assert primary["reasons"] and all(re.fullmatch(r"[A-Za-z0-9_.:-]+", r) for r in primary["reasons"])
    assert pair["by_reason_code"].keys() >= set(primary["reasons"])


def test_the_primary_comes_from_the_frozen_aggregation_path_and_is_never_defaulted(ctx, out, monkeypatch):
    populate(ctx, failing=1, completed=2)
    calls = []
    original = report_script.aggregate_primary

    def spy(plan, cells):
        calls.append((plan, len(cells)))
        return original(plan, cells)

    monkeypatch.setattr(report_script, "aggregate_primary", spy)
    assert report(ctx, out) == 0
    assert len(calls) == 1 and calls[0][0] is not None and calls[0][1] > 0
    # A summary (or anything numeric) from the aggregation path is never written.
    from shiftguard.repeats.aggregation import PrimarySummary

    monkeypatch.setattr(report_script, "aggregate_primary", lambda plan, cells: object.__new__(PrimarySummary))
    second = out.with_name("second.json")
    assert report(ctx, second) == 0
    primary = load(second)["primary"]
    assert primary["status"] == "refused" and primary["code"] == "PRIMARY_SUMMARY_NOT_REPORTED"
    assert primary["estimate"] is None and primary["interval"] is None


def test_a_typed_refusal_of_the_aggregation_is_recorded_as_the_primary(ctx, out, monkeypatch):
    populate(ctx, failing=1, completed=2)

    def refuse(plan, cells):
        raise report_script.RepeatContractError("QUALIFICATION_UPGRADE", "(1, 2, 'x', 'y') 0.5")

    monkeypatch.setattr(report_script, "aggregate_primary", refuse)
    assert report(ctx, out) == 0
    primary = load(out)["primary"]
    assert primary["status"] == "refused" and primary["code"] == "QUALIFICATION_UPGRADE"
    assert primary["estimate"] is None and primary["interval"] is None
    assert "0.5" not in out.read_text("ascii")


# ---------------------------------------------------------------- nothing label-equivalent leaves

def test_no_row_group_sum_or_float_appears_in_the_report_or_stdout(ctx, out, capsys):
    populate(ctx, failing=1, completed=3)
    store = open_store(ctx)
    results = [store.load(repeat_id(ctx, i)).result for i in (0, 2)]
    sums = {
        value for result in results for cell in result.pair_cells
        for value in (cell.paired_loss_sum_by_group or ()) if value != 0.0
    }
    assert sums
    capsys.readouterr()
    assert report(ctx, out) == 0
    stdout = capsys.readouterr().out
    text = out.read_text("ascii")
    plan = ctx.world.plan

    def floats(value):
        if isinstance(value, float):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from floats(item)
        elif isinstance(value, list):
            for item in value:
                yield from floats(item)

    assert list(floats(load(out))) == []
    for group in plan.group_universe:
        assert group not in text and group not in stdout
    for value in sums:
        assert repr(value) not in text and repr(value) not in stdout
    for outer in plan.outer_roles:
        for row_id in outer.evaluation_ids[:50]:
            assert str(row_id) not in set(re.findall(r'"([^"]+)"', text))
    assert not re.search(r"\d+\.\d+", stdout)
    for word in ("loss", "brier", "label", "row_id", "prob", "group_id"):
        assert word not in stdout.lower()
    keys = set(re.findall(r'"([a-z_]+)":', text))
    for word in ("loss", "sums", "row_id", "group_id", "prediction", "paired", "y"):
        assert word not in keys
    lines = stdout.strip().splitlines()
    assert lines[0].startswith("report written: scheduled 50 completed 2 failed 1 corrupt 0 missing 47")
    assert lines[1] == "primary: missing_evidence PRIMARY_EVIDENCE_UNAVAILABLE"
    assert {line.split()[0] for line in lines[2:]} == {"manifest_digest", "plan_digest", "report_digest"}


def test_the_report_is_read_only_for_the_store_and_leaves_no_lock(ctx, out):
    populate(ctx, failing=1, completed=3)
    before = snapshot(ctx.root.parent)
    assert report(ctx, out) == 0
    assert snapshot(ctx.root.parent) == before
    assert not lock_path(ctx).exists()
    assert load(out)["report_digest"] == report_script.canonical_digest(
        {k: v for k, v in load(out).items() if k != "report_digest"})


# ---------------------------------------------------------------- refusals

def test_a_held_run_lock_refuses_with_run_in_progress_and_reads_nothing(ctx, out, capsys, monkeypatch):
    populate(ctx, failing=1, completed=2)
    lock_path(ctx).write_text("4242\n", encoding="ascii")
    opened = []
    monkeypatch.setattr(report_script, "_open_store", lambda *a: opened.append(a))
    assert report(ctx, out) == 2
    assert "RUN_IN_PROGRESS" in capsys.readouterr().out
    assert opened == [] and not out.exists()
    assert lock_path(ctx).read_text("ascii") == "4242\n"  # a foreign lock is never touched


def test_a_lock_that_appears_while_reading_invalidates_the_report(ctx, out, capsys, monkeypatch):
    populate(ctx, failing=1, completed=2)
    original = report_script.build_report

    def racing(*args):
        built = original(*args)
        lock_path(ctx).write_text("4242\n", encoding="ascii")
        return built

    monkeypatch.setattr(report_script, "build_report", racing)
    assert report(ctx, out) == 2
    assert "RUN_IN_PROGRESS" in capsys.readouterr().out and not out.exists()


def test_an_existing_out_is_never_overwritten(ctx, out, capsys):
    out.write_text("precious\n", encoding="ascii")
    assert report(ctx, out) == 2
    assert "OUT_EXISTS" in capsys.readouterr().out
    assert out.read_text("ascii") == "precious\n"


def test_out_inside_the_repository_the_private_tree_or_a_missing_folder_is_refused(ctx, tmp_path, capsys):
    repo = ctx.world.repo
    for bad, code in (
        (repo / "shiftguard" / "repeats" / "report.json", "OUT_INSIDE_REPO"),
        (repo / "scripts" / "report.json", "OUT_INSIDE_REPO"),
        (repo / "report.json", "OUT_INSIDE_REPO"),
        (repo / "var" / "report.json", "OUT_INSIDE_REPO"),
        (repo / "var" / "gate8-private" / "report.json", "OUT_INSIDE_PRIVATE"),
        (ctx.root / "report.json", "OUT_INSIDE_PRIVATE"),
        (repo / "var" / "gate8-private" / ".." / "gate8-private" / "x" / "r.json", "OUT_INSIDE_PRIVATE"),
        (tmp_path / "no-such-folder" / "report.json", "OUT_PARENT_MISSING"),
    ):
        assert report(ctx, bad) == 2, bad
        assert code in capsys.readouterr().out
        assert not bad.exists(), bad
    assert not (repo / "var").exists()
    assert not (tmp_path / "no-such-folder").exists()


def test_a_manifest_that_does_not_verify_is_refused(ctx, out, capsys):
    schedule = list(reversed(ctx.world.manifest["schedule"]))
    for tampered, expected in (
        ({**ctx.world.manifest, "schedule": schedule}, "MANIFEST_DIGEST"),
        (rm.seal_manifest({**ctx.world.manifest, "schedule": schedule}), "MANIFEST_SCHEDULE"),
    ):
        ctx.manifest_path.write_bytes(rm.dump_manifest(tampered))
        assert report(ctx, out) == 2
        assert expected in capsys.readouterr().out
    ctx.manifest_path.write_bytes(b"not a manifest")
    assert report(ctx, out) == 2
    assert "MANIFEST_UNREADABLE" in capsys.readouterr().out
    assert not out.exists() and not (ctx.world.repo / "var").exists()


def test_the_driver_gates_apply_date_veto_dirty_tree_and_seams(ctx, out, capsys):
    from datetime import date

    assert report(ctx, out, today=date(2026, 10, 19)) == 2
    assert "DATE_GATE" in capsys.readouterr().out
    (ctx.world.repo / ".agent/OWNER_ACTIONS.md").write_text(owner_file("no"), encoding="utf-8")
    assert report(ctx, out) == 2 and "OWNER_VETO" in capsys.readouterr().out
    (ctx.world.repo / ".agent/OWNER_ACTIONS.md").write_bytes(OWNER_TEXT)
    (ctx.world.repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 7\n")
    assert report(ctx, out) == 2 and "SOURCE_DIRTY" in capsys.readouterr().out
    (ctx.world.repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 1\n")
    base = ["--manifest", str(ctx.manifest_path), "--out", str(out)]
    for seams in (dict(today=RUN_DAY), dict(repo_root=ctx.world.repo),
                  dict(protocol_paths=protocol_paths(ctx.world.repo))):
        assert report_script.main(base, **seams) == 2
        assert "SEAM_REQUIRES_LOADER" in capsys.readouterr().out
    assert report_script.main([*base, "--no-date-gate"], today=None) == 2
    assert "DATE_GATE_REQUIRED" in capsys.readouterr().out
    assert not out.exists() and not (ctx.world.repo / "var").exists()


def test_the_script_stays_outside_the_frozen_source_scope():
    assert not rm.is_source_path("scripts/gate8_report_development.py")
    assert not rm.is_source_path("tests/repeats_adapter/test_report_development.py")


# ---------------------------------------------------------------- review corrections

def test_a_completion_next_to_a_failed_attempt_stays_visible_as_replaced_failure(ctx, out):
    from test_run_driver import real_result

    populate(ctx, failing=1, completed=1)  # coordinate 0 completes
    store = open_store(ctx)
    store.record_failed_attempt(repeat_id(ctx, 5), "earlier", "execute:SOME_TYPED_CODE")
    store.commit(real_result(ctx.world, *coord(ctx, 5)), attempt_id="later")
    assert report(ctx, out) == 0
    data = load(out)
    entry = data["inventory"][5]
    assert entry["status"] == "completed"
    assert entry["failure_code"] == "REPLACED_FAILURE" and entry["prior_failed_attempts"] == 1
    assert data["inventory"][0]["failure_code"] is None and data["inventory"][0]["prior_failed_attempts"] == 0
    assert data["totals"]["completed"] == 2 and data["totals"]["completed_with_prior_failed_attempt"] == 1


def test_a_store_change_while_reading_is_refused_as_store_changed(ctx, out, capsys, monkeypatch):
    populate(ctx, failing=1, completed=2)
    log = ctx.root.parent / f"{ctx.root.name}.run-log.jsonl"
    original = report_script.build_report

    def appending(*args):
        built = original(*args)
        with open(log, "ab") as handle:
            handle.write(b'{"late": 1}\n')
        return built

    monkeypatch.setattr(report_script, "build_report", appending)
    assert report(ctx, out) == 2
    assert "STORE_CHANGED" in capsys.readouterr().out and not out.exists()
    # A new attempt directory or completion file appearing mid-read is caught the same way.
    monkeypatch.setattr(report_script, "build_report", original)

    def adding(*args):
        built = original(*args)
        (ctx.root / "attempts" / ("f" * 64)).mkdir()
        return built

    monkeypatch.setattr(report_script, "build_report", adding)
    assert report(ctx, out) == 2
    assert "STORE_CHANGED" in capsys.readouterr().out and not out.exists()


def test_an_untyped_exception_prints_only_its_type_name(ctx, out, capsys, monkeypatch):
    def boom(*args):
        raise ValueError("secret 0.4821 label=1 row 77")

    monkeypatch.setattr(report_script, "build_report", boom)
    assert report(ctx, out) == 1
    captured = capsys.readouterr()
    assert captured.out == "error: ValueError\n" and captured.err == ""
    assert not out.exists()


def test_an_unreadable_attempt_record_is_corrupt_with_its_code(ctx, out):
    populate(ctx, failing=1, completed=2)
    next((ctx.root / "attempts" / repeat_id(ctx, 1)).iterdir()).write_bytes(b"not json")
    assert report(ctx, out) == 0
    entry = load(out)["inventory"][1]
    assert (entry["status"], entry["failure_code"]) == ("corrupt", "ATTEMPT_RECORD_UNREADABLE")


def test_a_completion_with_an_unreadable_attempt_record_stays_completed(ctx, out):
    populate(ctx, failing=1, completed=2)  # coordinate 0 completes, 1 fails
    (ctx.root / "attempts" / repeat_id(ctx, 0) / "000001-run-002.json").write_bytes(b"")
    assert report(ctx, out) == 0
    data = load(out)
    entry = data["inventory"][0]
    assert (entry["status"], entry["failure_code"]) == ("completed", "ATTEMPT_RECORD_UNREADABLE")
    assert entry["cells_with_fallback"] is not None
    assert data["totals"]["completed"] == 1


def test_completion_files_outside_the_schedule_are_counted(ctx, out):
    populate(ctx, failing=1, completed=2)
    source = ctx.root / "completions" / f"{repeat_id(ctx, 0)}.json"
    (ctx.root / "completions" / f"{'a' * 64}.json").write_bytes(source.read_bytes())
    assert report(ctx, out) == 0
    assert load(out)["totals"]["unscheduled_completion_files"] == 1


def test_only_letter_led_code_segments_are_reported_and_anything_else_is_unrecognized(ctx, out):
    safe = report_script._safe_code
    for good in ("execute:SOME_TYPED_CODE", "PRIMARY_EVIDENCE_UNAVAILABLE", "a.b-c:D_e",
                 "prediction:m:_ArrayMemoryError"):
        assert safe(good) == good
    for bad in ("0.4821", "fit:x:0.4821", "execute:0.4821", "_0.48", "a:_0.48", "", "a:", ":a", "a b", "x" * 81, 7, None):
        assert safe(bad) == "UNRECOGNIZED_CODE", bad
    populate(ctx, failing=1, completed=1)
    open_store(ctx).record_failed_attempt(repeat_id(ctx, 6), "odd", "fit:x:0.4821")
    assert report(ctx, out) == 0
    text = out.read_text("ascii")
    assert load(out)["inventory"][6]["failure_code"] == "UNRECOGNIZED_CODE" and "0.4821" not in text
