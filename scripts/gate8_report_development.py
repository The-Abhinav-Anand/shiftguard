"""Gate 8: read-only, label-free report of the Bank development repeats.

It reuses the run driver's own gates and verification: the same date gate and owner veto, a clean
source tree, a tracked unmodified manifest on the real path, the plan rebuilt from the verified
dataset and ``verify_run_manifest``. It refuses when the manifest does not verify.

It never takes the run lock. If the store's ``<store>.run.lock`` exists it refuses with
``RUN_IN_PROGRESS`` instead of reading, and checks again after reading. It writes nothing into the
store (an absent store is reported as all-missing and is not created; a half-created store is
refused). The report goes to ``--out``: never overwritten, never inside the repository (so never
inside the frozen source scope or var/gate8-private).

The report holds only: the development label and plan identifiers, a status (and typed failure code)
for each scheduled coordinate, counts per qualification state, reason code and fallback, and the
primary result exactly as the frozen aggregation path returns it for this binding (typed
``MissingEvidence`` or a typed refusal, estimate and interval null). Nothing numeric is derived from
the paired sums, and no row id, group id, sum, loss, prediction or label is written or printed.
"""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from datetime import date
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate8_run_development as driver  # noqa: E402
from shiftguard.repeats import run_manifest as rm  # noqa: E402
from shiftguard.repeats.aggregation import PrimarySummary, aggregate_primary, primary_keys  # noqa: E402
from shiftguard.repeats.development_adapter import plan_development_repeats  # noqa: E402
from shiftguard.repeats.development_store import (  # noqa: E402
    PRIVATE_SUBTREE,
    DevelopmentCoordinateStore,
)
from shiftguard.repeats.models import (  # noqa: E402
    MissingEvidence,
    RepeatContractError,
    canonical_digest,
)

REPORT_SCHEMA = "gate8-dev-report-v1"
_STORE_DIRECTORIES = ("staging", "artifacts", "completions", "attempts")
# Every ':'-separated segment starts with a letter, so a number such as 0.4821 is never a code.
_CODE = re.compile(r"_*[A-Za-z][A-Za-z0-9_.-]*(?::_*[A-Za-z][A-Za-z0-9_.-]*)*")
SCRIPT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new report file, outside the repository")
    parser.add_argument("--date-gate", action=argparse.BooleanOptionalAction, default=True)
    return parser


def _safe_code(value: Any) -> str:
    return value if type(value) is str and len(value) <= 80 and _CODE.fullmatch(value) else "UNRECOGNIZED_CODE"


def _check_out(root: Path, out: Path) -> None:
    """Fail before anything is read or created."""
    if os.path.lexists(out):
        raise RepeatContractError("OUT_EXISTS", out.name)
    resolved = Path(out).resolve()
    if resolved.is_relative_to((root / "var" / PRIVATE_SUBTREE).resolve()):
        raise RepeatContractError("OUT_INSIDE_PRIVATE", out.name)
    if resolved.is_relative_to(root.resolve()):
        raise RepeatContractError("OUT_INSIDE_REPO", out.name)
    if not resolved.parent.is_dir():
        raise RepeatContractError("OUT_PARENT_MISSING", out.name)


def _lock_path(store_root: Path) -> Path:
    return store_root.parent / f"{store_root.name}.run.lock"


def _require_no_run(store_root: Path) -> None:
    if _lock_path(store_root).exists():
        raise RepeatContractError("RUN_IN_PROGRESS", "the run lock exists; nothing was read")


def _open_store(store_root: Path, plan: Any) -> DevelopmentCoordinateStore | None:
    """None when there is no store yet. Never creates or completes one."""
    if not store_root.exists():
        return None
    if not (store_root / "STORE.json").is_file() or any(
        not (store_root / name).is_dir() for name in _STORE_DIRECTORIES
    ):
        raise RepeatContractError("STORE_INCOMPLETE", "store root exists without a complete layout")
    return DevelopmentCoordinateStore(store_root, plan)


def _classify(store: DevelopmentCoordinateStore | None, item: dict[str, Any]):
    """(status, failure_code, prior_failed_attempts, decoded result or None) of one coordinate."""
    rid = item["repeat_id"]
    if store is None:
        return "missing", None, 0, None
    try:
        stored = store.load(rid)
    except RepeatContractError:
        return "corrupt", "CORRUPT_COMPLETION", 0, None
    try:
        attempts = store.attempts(rid)
    except (ValueError, KeyError, TypeError, OSError):
        if stored is not None:
            # A crash between publishing a completion and writing its attempt record leaves an
            # unreadable attempt file; the driver still counts the coordinate as completed.
            return "completed", "ATTEMPT_RECORD_UNREADABLE", 0, stored.result
        return "corrupt", "ATTEMPT_RECORD_UNREADABLE", 0, None
    failures = [attempt for attempt in attempts if attempt.outcome == "FAILED_ATTEMPT"]
    if stored is not None:
        # A completion next to a failed attempt stays visible, not read as a clean success.
        return "completed", ("REPLACED_FAILURE" if failures else None), len(failures), stored.result
    if failures:
        return "failed", _safe_code(failures[-1].reason), len(failures), None
    return "missing", None, 0, None


def _primary(plan: Any, cells: tuple) -> dict[str, Any]:
    """The frozen aggregation path, called as the contract allows; never bypassed."""
    required = len(primary_keys(plan))
    base = {
        "estimate": None, "interval": None,
        "interval_code": "INTERVAL_REQUIRES_PRIMARY_ESTIMATE", "required_cell_count": required,
    }
    try:
        outcome = aggregate_primary(plan, cells)
    except RepeatContractError as error:
        return {**base, "status": "refused", "code": _safe_code(error.code), "reasons": []}
    if isinstance(outcome, MissingEvidence):
        return {
            **base, "status": "missing_evidence", "code": _safe_code(outcome.code),
            "reasons": sorted(_safe_code(reason) for reason in outcome.reasons),
            "missing_cell_count": len(outcome.missing),
            "unavailable_cell_count": len(outcome.unavailable),
        }
    # A summary would be numeric; this report never carries one.
    kind = "PRIMARY_SUMMARY" if isinstance(outcome, PrimarySummary) else "UNEXPECTED_OUTCOME"
    return {**base, "status": "refused", "code": f"{kind}_NOT_REPORTED", "reasons": []}


class _Accounting:
    """Counts only, accumulated one coordinate at a time so no decoded result is retained."""

    def __init__(self) -> None:
        self.cell_total = 0
        self.cell_fallback = 0
        self.cell_states: Counter = Counter()
        self.cell_reasons: Counter = Counter()
        self.cond_states: Counter = Counter()
        self.cond_reasons: Counter = Counter()
        self.cond_fallback: Counter = Counter()
        self.cond_failed: Counter = Counter()

    def add(self, result: Any) -> tuple[int, int]:
        """Adds one coordinate; returns its (cells with fallback, conditions with fallback)."""
        cells_fb = conds_fb = 0
        for cell in result.pair_cells:
            self.cell_total += 1
            self.cell_states[cell.qualification] += 1
            self.cell_reasons.update(_safe_code(reason) for reason in cell.reasons)
            cells_fb += 1 if cell.has_fallback else 0
        for condition in result.conditions:
            self.cond_states[condition.qualification] += 1
            self.cond_reasons.update(_safe_code(reason) for reason in condition.reasons)
            if condition.fallback_rows > 0:
                conds_fb += 1
                self.cond_fallback[condition.requested_method] += 1
            if condition.status == "failed":
                self.cond_failed[condition.requested_method] += 1
        self.cell_fallback += cells_fb
        return cells_fb, conds_fb

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_cells": {
                "total": self.cell_total, "by_qualification": dict(sorted(self.cell_states.items())),
                "by_reason_code": dict(sorted(self.cell_reasons.items())),
                "with_fallback": self.cell_fallback,
            },
            "conditions": {
                "total": sum(self.cond_states.values()),
                "by_qualification": dict(sorted(self.cond_states.items())),
                "by_reason_code": dict(sorted(self.cond_reasons.items())),
                "with_fallback_by_requested_method": dict(sorted(self.cond_fallback.items())),
                "failed_by_requested_method": dict(sorted(self.cond_failed.items())),
            },
        }


def _store_state(store_root: Path) -> tuple:
    """Run log size and mtime plus every name (directories too) under completions/ and attempts/."""
    log = store_root.parent / f"{store_root.name}.run-log.jsonl"
    try:
        stat = log.stat()
        log_state: tuple | None = (stat.st_size, stat.st_mtime_ns)
    except OSError:
        log_state = None
    names = sorted(
        path.relative_to(store_root).as_posix()
        for name in ("completions", "attempts") if (store_root / name).is_dir()
        for path in (store_root / name).rglob("*"))
    return log_state, tuple(names)


def build_report(manifest: dict[str, Any], plan: Any, store: DevelopmentCoordinateStore | None) -> dict[str, Any]:
    inventory, cells, accounting = [], [], _Accounting()
    scheduled = {item["repeat_id"] for item in manifest["schedule"]}
    for item in manifest["schedule"]:
        status, code, prior, result = _classify(store, item)
        entry = {
            "outer_seed": item["outer_seed"], "inner_id": item["inner_id"],
            "repeat_id": item["repeat_id"], "status": status, "failure_code": code,
            "prior_failed_attempts": prior, "cells_with_fallback": None,
            "conditions_with_fallback": None,
        }
        if result is not None:
            entry["cells_with_fallback"], entry["conditions_with_fallback"] = accounting.add(result)
            cells.extend(result.pair_cells)  # only what aggregate_primary reads; the result is dropped
        inventory.append(entry)
    unscheduled = 0
    if store is not None:
        unscheduled = sum(
            1 for path in (store.root / "completions").iterdir()
            if path.suffix == ".json" and path.stem not in scheduled)
    totals = Counter(entry["status"] for entry in inventory)
    body = {
        "schema": REPORT_SCHEMA,
        "label": manifest["label"],
        "execution_tier": manifest["execution_tier"],
        "claim_scope": manifest["claim_scope"],
        "split_profile": manifest["split_profile"],
        "manifest_digest": manifest["manifest_digest"],
        "plan_digest": manifest["plan_digest"],
        "script_sha256": SCRIPT_SHA256,
        "inventory": inventory,
        "totals": {
            "scheduled": len(inventory),
            **{name: totals.get(name, 0) for name in ("completed", "failed", "corrupt", "missing")},
            "completed_with_prior_failed_attempt": sum(
                1 for e in inventory if e["status"] == "completed" and e["prior_failed_attempts"]),
            "unscheduled_completion_files": unscheduled,
        },
        "accounting_scope": "completed coordinates only",
        "accounting": accounting.to_dict(),
        "primary": _primary(plan, tuple(cells)),
    }
    return {**body, "report_digest": canonical_digest(body)}


def _write_new(path: Path, report: dict[str, Any]) -> None:
    data = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("ascii")
    try:
        with open(path, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise RepeatContractError("OUT_EXISTS", Path(path).name) from None


def main(
    argv: list[str] | None = None,
    *,
    dataset_loader: Callable[[Path], tuple[object, str]] | None = None,
    today: date | None = None,
    repo_root: Path | None = None,
    store_root: Path | None = None,
    protocol_paths: tuple[Path, ...] | None = None,
) -> int:
    """Test seams are refused unless ``dataset_loader`` is injected, as in the run driver."""
    args = _parser().parse_args(argv)
    seams_used = any(item is not None for item in (today, repo_root, store_root, protocol_paths))
    root = Path(ROOT if repo_root is None else repo_root)
    try:
        if dataset_loader is None:
            if not args.date_gate:
                raise RepeatContractError("DATE_GATE_REQUIRED", "the real dataset is never loaded without it")
            if seams_used:
                raise RepeatContractError("SEAM_REQUIRES_LOADER", "test seams need an injected dataset loader")
        _check_out(root, args.out)
        rm.require_run_permitted(root, today=today, date_gate=args.date_gate)
        rm.require_clean_source(root)
        if dataset_loader is None:
            rm.require_tracked_unmodified(root, args.manifest)
        manifest = rm.load_manifest(args.manifest)
        resolved_root = driver.resolve_store_root(root, manifest, store_root)
        dataset, dataset_manifest_sha256 = (dataset_loader or rm.load_verified_bank_dataset)(root)
        protocol = protocol_paths if protocol_paths is not None else rm.default_protocol_paths(root)
        binding = rm.build_development_binding(dataset, repo_root=root, protocol_paths=protocol)
        plan = plan_development_repeats(dataset, binding)
        rm.verify_run_manifest(
            manifest, plan, repo_root=root, dataset_manifest_sha256=dataset_manifest_sha256)
        if Path(args.out).resolve().is_relative_to(resolved_root):
            raise RepeatContractError("OUT_INSIDE_PRIVATE", "inside the store")
        _require_no_run(resolved_root)
        state = _store_state(resolved_root)
        report = build_report(manifest, plan, _open_store(resolved_root, plan))
        _require_no_run(resolved_root)  # a run that began while reading invalidates what was read
        if _store_state(resolved_root) != state:
            raise RepeatContractError("STORE_CHANGED", "the store changed while it was read")
        _write_new(args.out, report)
    except RepeatContractError as error:
        print(f"refused: {_safe_code(error.code)}")
        return 2
    except Exception as error:  # noqa: BLE001  type name only; never a message that could carry data
        print(f"error: {type(error).__name__}")
        return 1
    totals, primary = report["totals"], report["primary"]
    print(
        f"report written: scheduled {totals['scheduled']} completed {totals['completed']} "
        f"failed {totals['failed']} corrupt {totals['corrupt']} missing {totals['missing']}")
    print(f"primary: {primary['status']} {primary['code']}")
    print(f"manifest_digest {report['manifest_digest']}")
    print(f"plan_digest {report['plan_digest']}")
    print(f"report_digest {report['report_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
