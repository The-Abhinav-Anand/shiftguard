"""Gate 8: restartable driver for the Bank development repeats, bound to a frozen run manifest.

Before anything else it applies the date gate (no run before 20 Oct 2026, Asia/Kolkata) and the
owner veto (OWNER_ACTIONS item 9), requires a clean source tree and, on the real-data path, a
manifest that is inside the repository, git-tracked and unchanged against HEAD. It then rebuilds
the plan from the verified dataset and verifies it against the manifest (source blobs, source
commit tree, dependency lock, Python and package versions). The date gate and the veto are
re-checked before every coordinate. The store root is always the manifest's
``store_root_relative``: there is no command-line override.

The manifest schedule is walked in order:

* a byte-verified completed coordinate is skipped;
* a coordinate with a recorded failed attempt is reported and never re-run to replace it;
* a corrupt completion stops the run and is never overwritten;
* every other coordinate is prepared (cached per outer seed), executed, checked against the
  full expected condition grid and committed. An exception becomes a typed failed attempt (a
  code only, no data) and the run continues. A failed outer preparation fails every remaining
  coordinate of that outer at once, so the outcome does not depend on ``--limit`` chunking.

A process crash leaves no completion and no failure record, so a restart re-runs that
coordinate: that is restart, not replacement.

One run at a time: an exclusive lock file ``<store>.run.lock`` sits next to the store inside
var/gate8-private. A run refuses when it exists. After a hard crash (kill, power loss) the file
stays; once you are sure no run is active, delete that file by hand.

Test seams (prepare, execute, scope, today, repo_root, store_root, protocol_paths) are refused
unless a dataset loader is injected, so none of them can touch a real run.

The run log (JSON lines, next to the store) holds only: timestamp, repeat_id, outer_seed,
inner_id, status, duration_seconds, error_code. Nothing printed or logged contains a loss, a
label, a paired sum or a row-level outcome.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shiftguard.repeats import run_manifest as rm  # noqa: E402
from shiftguard.repeats.completion import Conflict  # noqa: E402
from shiftguard.repeats.development_adapter import (  # noqa: E402
    execute_coordinate,
    plan_development_repeats,
    prepare_outer,
)
from shiftguard.repeats.development_store import (  # noqa: E402
    FORBIDDEN_ROOT_NAME,
    PRIVATE_SUBTREE,
    DevelopmentCoordinateStore,
)
from shiftguard.repeats.models import RepeatContractError  # noqa: E402
from shiftguard.repeats.validation import expected_condition_slots  # noqa: E402

LOG_FIELDS = (
    "timestamp", "repeat_id", "outer_seed", "inner_id", "status", "duration_seconds", "error_code",
)
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None, help="coordinates to attempt in this invocation")
    parser.add_argument("--date-gate", action=argparse.BooleanOptionalAction, default=True)
    return parser


def _error_code(error: BaseException) -> str:
    if isinstance(error, RepeatContractError):
        return _UNSAFE.sub("_", error.code)[:64] or "UNKNOWN"
    return "EXC_" + (_UNSAFE.sub("_", type(error).__name__)[:60] or "UNKNOWN")


def resolve_store_root(repo_root: Path, manifest: dict[str, Any], override: Path | None = None) -> Path:
    """The store root, strictly inside var/gate8-private/ and outside verification/.

    ``override`` is a test seam; the real run always uses the manifest's root.
    """
    candidate = Path(override) if override is not None else Path(manifest["store_root_relative"])
    candidate = candidate if candidate.is_absolute() else repo_root / candidate
    private = (repo_root / "var" / PRIVATE_SUBTREE).resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(private) or resolved == private:
        raise RepeatContractError("PRIVATE_ROOT_REQUIRED", f"store root must be inside var/{PRIVATE_SUBTREE}")
    if FORBIDDEN_ROOT_NAME in {part.lower() for part in resolved.parts}:
        raise RepeatContractError("PRIVATE_ROOT_FORBIDDEN", "store root must not be inside verification/")
    return resolved


class RunLock:
    """Exclusive O_EXCL lock file for the whole run (see the module docstring)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise RepeatContractError("RUN_LOCKED", str(self.path)) from None
        os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        os.close(descriptor)
        return self

    def __exit__(self, *exc: object) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


class RunLog:
    """Append-only JSON lines; the field set is fixed."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, repeat_id: str, outer_seed: int, inner_id: int, status: str,
              duration: float, error_code: str | None) -> None:
        line = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "repeat_id": repeat_id, "outer_seed": outer_seed, "inner_id": inner_id,
            "status": status, "duration_seconds": round(duration, 3), "error_code": error_code,
        }
        assert tuple(line) == LOG_FIELDS
        with open(self.path, "ab") as handle:
            handle.write((json.dumps(line, sort_keys=False) + "\n").encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())


def _attempts(store: DevelopmentCoordinateStore, repeat_id: str):
    try:
        return store.attempts(repeat_id)
    except (ValueError, KeyError, TypeError, OSError):
        raise RepeatContractError("ATTEMPT_RECORD_UNREADABLE", repeat_id) from None


def _failed_ids(store: DevelopmentCoordinateStore, repeat_ids: list[str], inventory: Any) -> set[str]:
    done = set(inventory.completed)
    failed = set(inventory.failed)
    for repeat_id in repeat_ids:
        if repeat_id not in done and any(
            attempt.outcome == "FAILED_ATTEMPT" for attempt in _attempts(store, repeat_id)
        ):
            failed.add(repeat_id)
    return failed


def _require_single_store(private: Path, store_root: Path) -> None:
    """No other store (STORE.json marker) may exist under var/gate8-private."""
    for marker in private.rglob("STORE.json"):
        if marker.parent.resolve() != store_root:
            raise RepeatContractError("OTHER_STORE_PRESENT", marker.parent.name)


def expected_slots(plan: Any, outer: int, inner: int, scope: dict[str, Any]) -> tuple:
    """The condition slots a coordinate must hold: the full grid, narrowed only by a test scope."""
    fields = {"scenarios": "scenario", "budgets": "budget", "methods": "method"}
    return tuple(
        slot for slot in expected_condition_slots(plan.spec)
        if (slot.outer_seed, slot.inner_id) == (outer, inner)
        and all(getattr(slot, field) in scope[name] for name, field in fields.items() if name in scope)
    )


def main(
    argv: list[str] | None = None,
    *,
    dataset_loader: Callable[[Path], tuple[object, str]] | None = None,
    today: date | None = None,
    repo_root: Path | None = None,
    prepare: Callable[..., Any] | None = None,
    execute: Callable[..., Any] | None = None,
    scope: dict[str, Any] | None = None,
    store_root: Path | None = None,
    protocol_paths: tuple[Path, ...] | None = None,
) -> int:
    """Test seams, all refused unless ``dataset_loader(repo_root) -> (dataset, manifest_file_sha256)``
    is injected: today, repo_root, prepare(dataset, plan, outer_seed), execute(prepared, inner_id,
    **scope), scope, store_root and protocol_paths."""
    args = _parser().parse_args(argv)
    seams_used = any(item is not None for item in (
        today, repo_root, prepare, execute, store_root, protocol_paths)) or bool(scope)
    root = Path(ROOT if repo_root is None else repo_root)
    prepare = prepare_outer if prepare is None else prepare
    execute = execute_coordinate if execute is None else execute
    scope = dict(scope or {})
    try:
        if args.limit is not None and args.limit < 0:
            raise RepeatContractError("LIMIT", "must not be negative")
        if dataset_loader is None:
            if not args.date_gate:
                raise RepeatContractError("DATE_GATE_REQUIRED", "the real dataset is never loaded without it")
            if seams_used:
                raise RepeatContractError("SEAM_REQUIRES_LOADER", "test seams need an injected dataset loader")
        rm.require_run_permitted(root, today=today, date_gate=args.date_gate)
        rm.require_clean_source(root)
        if dataset_loader is None:
            rm.require_tracked_unmodified(root, args.manifest)
        manifest = rm.load_manifest(args.manifest)
        resolved_root = resolve_store_root(root, manifest, store_root)
        dataset, dataset_manifest_sha256 = (dataset_loader or rm.load_verified_bank_dataset)(root)
        protocol = protocol_paths if protocol_paths is not None else rm.default_protocol_paths(root)
        binding = rm.build_development_binding(dataset, repo_root=root, protocol_paths=protocol)
        plan = plan_development_repeats(dataset, binding)
        rm.verify_run_manifest(
            manifest, plan, repo_root=root, dataset_manifest_sha256=dataset_manifest_sha256)
        return _run(
            args, root, manifest, plan, dataset, resolved_root, prepare, execute, scope, today)
    except RepeatContractError as error:
        print(f"refused: {error.code}")
        if error.code == "RUN_LOCKED":
            print(f"lock {error.detail}")
        return 2
    except Exception as error:  # noqa: BLE001  type name only; never a message that could carry data
        print(f"error: {type(error).__name__}")
        return 1


def _run(args, root, manifest, plan, dataset, store_root, prepare, execute, scope, today) -> int:
    private = (root / "var" / PRIVATE_SUBTREE).resolve()
    with RunLock(store_root.parent / f"{store_root.name}.run.lock"):
        _require_single_store(private, store_root)
        store = DevelopmentCoordinateStore(store_root, plan)
        log = RunLog(store_root.parent / f"{store_root.name}.run-log.jsonl")
        schedule = manifest["schedule"]
        repeat_ids = [item["repeat_id"] for item in schedule]
        inventory = store.inventory()  # the one deep scan of this run
        done = set(inventory.completed)
        corrupt = set(inventory.corrupt)
        failed = _failed_ids(store, repeat_ids, inventory)
        if corrupt:
            for repeat_id in sorted(corrupt):
                owner = next((i for i in schedule if i["repeat_id"] == repeat_id), None)
                log.write(repeat_id, owner["outer_seed"] if owner else -1,
                          owner["inner_id"] if owner else -1, "stopped_corrupt", 0.0,
                          "CORRUPT_COMPLETION")
            print(f"stopped: {len(corrupt)} corrupt completion(s); none was overwritten")
            _summary(repeat_ids, done, failed, corrupt, 0)
            return 3

        def fail(item: dict, phase: str, code: str, started: float) -> str:
            """Record one typed failure unless a completion exists; returns the logged status."""
            repeat_id = item["repeat_id"]
            try:
                if store.load(repeat_id) is not None:
                    status, logged = "completed", "warning:COMPLETION_EXISTS"
                    done.add(repeat_id)
                else:
                    store.record_failed_attempt(
                        repeat_id, f"run-{len(_attempts(store, repeat_id)) + 1:03d}",
                        f"{phase}:{code}",
                        {"outer_seed": item["outer_seed"], "inner_id": item["inner_id"], "phase": phase})
                    status, logged = "failed", f"{phase}:{code}"
                    failed.add(repeat_id)
            except RepeatContractError as error:
                if error.code != "CORRUPT_COMPLETION":
                    raise
                corrupt.add(repeat_id)
                status, logged = "stopped_corrupt", "CORRUPT_COMPLETION"
            log.write(repeat_id, item["outer_seed"], item["inner_id"], status,
                      time.perf_counter() - started, logged)
            return status

        executed = 0
        exit_code = 0
        prepared: tuple[int, Any] | None = None
        for item in schedule:
            repeat_id, outer, inner = item["repeat_id"], item["outer_seed"], item["inner_id"]
            if repeat_id in done or repeat_id in failed:
                continue
            if args.limit is not None and executed >= args.limit:
                break
            try:
                rm.require_run_permitted(root, today=today, date_gate=args.date_gate)
            except RepeatContractError as error:
                print(f"stopped: {error.code}")
                exit_code = 2
                break
            executed += 1
            started = time.perf_counter()
            if prepared is None or prepared[0] != outer:
                prepared = None  # release the previous outer before fitting the next
                try:
                    prepared = (outer, prepare(dataset, plan, outer))
                except Exception as error:  # noqa: BLE001
                    code = _error_code(error)
                    # Every remaining coordinate of this outer fails now, whatever --limit says.
                    for other in schedule:
                        if other["outer_seed"] == outer and other["repeat_id"] not in done \
                                and other["repeat_id"] not in failed:
                            if fail(other, "prepare", code, started) == "stopped_corrupt":
                                exit_code = 3
                    if exit_code:
                        print("stopped: a completion failed verification; it was not overwritten")
                        break
                    continue
            phase = "execute"
            try:
                result = execute(prepared[1], inner, **scope)
                if getattr(result, "repeat_id", None) != repeat_id:
                    raise RepeatContractError("RESULT_IDENTITY", "result is for another coordinate")
                phase = "validate"
                if tuple(c.slot for c in result.conditions) != expected_slots(plan, outer, inner, scope):
                    raise RepeatContractError("INCOMPLETE_GRID", "conditions differ from the expected grid")
                phase = "commit"
                committed = store.commit(
                    result, attempt_id=f"run-{len(_attempts(store, repeat_id)) + 1:03d}",
                    audit={"outer_seed": outer, "inner_id": inner})
                done.add(repeat_id)
                conflict = isinstance(committed.decision, Conflict)
                log.write(repeat_id, outer, inner, "conflict" if conflict else "completed",
                          time.perf_counter() - started, "commit:COMMIT_CONFLICT" if conflict else None)
            except Exception as error:  # noqa: BLE001
                if isinstance(error, RepeatContractError) and error.code == "CORRUPT_COMPLETION":
                    corrupt.add(repeat_id)
                    log.write(repeat_id, outer, inner, "stopped_corrupt",
                              time.perf_counter() - started, "CORRUPT_COMPLETION")
                    exit_code = 3
                elif fail(item, phase, _error_code(error), started) == "stopped_corrupt":
                    exit_code = 3
            if exit_code == 3:
                print("stopped: a completion failed verification; it was not overwritten")
                break
        _summary(repeat_ids, done, failed - done, corrupt, executed)
        return exit_code


def _summary(repeat_ids: list[str], done: set, failed: set, corrupt: set, executed: int) -> None:
    remaining = [i for i in repeat_ids if i not in done and i not in failed and i not in corrupt]
    print(
        f"completed {len(done)} failed {len(failed)} corrupt {len(corrupt)} "
        f"remaining {len(remaining)} attempted_this_run {executed}")


if __name__ == "__main__":
    raise SystemExit(main())
