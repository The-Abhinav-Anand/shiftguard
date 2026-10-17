"""Gate 8 precondition 4 measurement: compact development-coordinate store vs naive serialization.

For one full-grid coordinate on each fabricated Bank-shaped fixture (default 500 profiles and the
high-cardinality ``row`` profile) this records compact vs naive artifact bytes, encode time, and
the restart-verification cost (reopen + byte verify + decode + validate) as wall time and peak
working set. The restart verification runs in a fresh child process that rebuilds only the dataset
and plan, so its memory is not hidden under the execution phase's peak. Fabricated rows only;
no real data is loaded; only sizes, times and counts are written, never a loss or label value.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling script: import, never edit
import gate8_resource_preflight as base  # noqa: E402  (also appends tests/repeats_adapter)

NOTE = "Fabricated Bank-shaped rows only; no real outcome accessed; storage resource measurement, not a result."
BINDING_NOTE = ("These fixtures use the synthetic_fabricated binding; a development (Bank) binding was "
                "not exercised, so its qualification strings and sums are not reflected in these sizes.")
MEMORY_NOTE = ("Sampled working-set rise is a LOWER bound (20 ms polling, and the process already holds the "
               "plan); the child process peak working set is the UPPER bound (it includes dataset "
               "generation and plan building). tracemalloc peak counts Python allocations only and was "
               "taken in a separate pass, so the phase timings above are not slowed by it.")
MIB = base.MIB
SAMPLE_SECONDS = 0.02


class _PeakSampler:
    """Polls the working set while a phase runs; the process-wide peak counter cannot isolate a phase."""

    def __init__(self) -> None:
        self.start = base._memory()["working_set_bytes"]
        self.peak = self.start
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, base._memory()["working_set_bytes"])
            self._stop.wait(SAMPLE_SECONDS)

    def __enter__(self) -> "_PeakSampler":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()
        self.peak = max(self.peak, base._memory()["working_set_bytes"])

    def report(self) -> dict:
        return {
            "working_set_before_bytes": self.start,
            "sampled_peak_working_set_bytes": self.peak,
            "sampled_peak_rise_bytes": self.peak - self.start,
            "sampled_peak_rise_mib": round((self.peak - self.start) / MIB, 1),
            "sample_interval_seconds": SAMPLE_SECONDS,
        }


def _timed(fn):
    start = time.perf_counter()
    value = fn()
    return value, round(time.perf_counter() - start, 4)


def _build(rows: int, profiles: str):
    from development_fixtures import fabricated_binding
    from shiftguard.repeats import development_adapter as adapter
    from shiftguard.repeats.models import RepeatSpec

    dataset = base._generate_dataset(rows, profiles)
    binding = fabricated_binding(dataset)
    plan = adapter.plan_development_repeats(dataset, binding, RepeatSpec())
    return dataset, plan


def _naive_bytes(result) -> int:
    """The previous full serialization: every context, cell and condition in canonical form."""
    from shiftguard.repeats.completion import serialize_artifact

    return len(serialize_artifact({
        "cells": [c.to_canonical() for c in result.pair_cells],
        "conditions": [c.to_canonical() for c in result.conditions],
        "contexts": [c.to_canonical() for c in result.contexts],
    }))


def _restart_child(args: argparse.Namespace) -> int:
    """Fresh process: rebuild dataset and plan, then reopen the store and verify the coordinate."""
    from shiftguard.repeats import development_store as store_module
    from shiftguard.repeats.development_adapter import validate_coordinate_result

    dataset, plan = _build(args.rows, args.profiles)
    rows_built = len(dataset.rows)
    del dataset
    gc.collect()
    repeat_id = args.repeat_id
    ws_before = base._memory()
    with _PeakSampler() as sampler:
        store, reopen_s = _timed(lambda: store_module.DevelopmentCoordinateStore(Path(args.store), plan))
        stored, byte_verify_s = _timed(lambda: store._read(repeat_id, deep=False))
        result, decode_s = _timed(lambda: store_module.decode_coordinate(plan, stored.artifact))
        _, validate_s = _timed(lambda: validate_coordinate_result(plan, result))
    # End to end as a restart would do it: the completed-id scan re-verifies everything.
    with _PeakSampler() as scan_sampler:
        completed, scan_s = _timed(store.completed_repeat_ids)
    # Separate pass: tracemalloc slows allocation-heavy code, so it never runs during the timed phases.
    del result, stored, store
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    traced_store = store_module.DevelopmentCoordinateStore(Path(args.store), plan)
    traced = traced_store._read(repeat_id, deep=False)
    traced_result = store_module.decode_coordinate(plan, traced.artifact)
    validate_coordinate_result(plan, traced_result)
    traced_current, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    payload = {
        "tracemalloc_restart_verify_peak_bytes": traced_peak,
        "tracemalloc_restart_verify_peak_mib": round(traced_peak / MIB, 1),
        "tracemalloc_restart_verify_retained_bytes": traced_current,
        "rows": rows_built,
        "reopen_store_seconds": reopen_s,
        "byte_verify_seconds": byte_verify_s,
        "decode_seconds": decode_s,
        "validate_seconds": validate_s,
        "restart_verification_seconds": round(reopen_s + byte_verify_s + decode_s + validate_s, 4),
        "completed_ids_scan_seconds": scan_s,
        "completed_ids_scan_found_coordinate": completed == (repeat_id,),
        "phases_memory": sampler.report(),
        "phases_memory_note": "sampled rise is a lower bound; see child_process_peak_working_set_bytes (upper bound)",
        "completed_ids_scan_memory": scan_sampler.report(),
        "child_working_set_before_verify_bytes": ws_before["working_set_bytes"],
        "child_process_peak_working_set_bytes": base._memory()["peak_working_set_bytes"],
        "child_process_peak_working_set_note": "includes dataset generation and plan building before verification",
    }
    Path(args.child_json).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return 0


def _measure(rows: int, profiles: str, outer: int, inner: int, say) -> dict:
    from shiftguard.repeats import development_adapter as adapter
    from shiftguard.repeats import development_store as store_module
    from shiftguard.repeats.models import BUDGETS, METHODS, SCENARIOS

    dataset, plan = _build(rows, profiles)
    prepared, prepare_s = _timed(lambda: adapter.prepare_outer(dataset, plan, outer))
    result, execute_s = _timed(lambda: adapter.execute_coordinate(
        prepared, inner, scenarios=SCENARIOS, budgets=BUDGETS, methods=METHODS))
    say(f"[{profiles}] prepare {prepare_s}s execute {execute_s}s; "
        f"{len(result.contexts)} contexts, {len(result.conditions)} conditions, {len(result.pair_cells)} cells")
    manifest = plan.roles(outer)
    naive = _naive_bytes(result)
    with _PeakSampler() as encode_sampler:
        (record, artifact), encode_s = _timed(lambda: store_module.encode_coordinate(plan, result))
    again, encode_again_s = _timed(lambda: store_module.encode_coordinate(plan, result))
    deterministic = again[1] == artifact
    tmp = Path(tempfile.mkdtemp(prefix="gate8-store-preflight-"))
    try:
        store_root = tmp / "store"
        store = store_module.DevelopmentCoordinateStore(store_root, plan)
        committed, commit_s = _timed(lambda: store.commit(result, attempt_id="preflight-1"))
        on_disk = sum(p.stat().st_size for p in (store_root / "artifacts").iterdir())
        del prepared, dataset
        del store
        gc.collect()
        child_json = tmp / "child.json"
        command = [
            sys.executable, "-B", str(Path(__file__).resolve()), "--restart-child",
            "--rows", str(rows), "--profiles", profiles, "--store", str(store_root),
            "--repeat-id", result.repeat_id, "--child-json", str(child_json), "--out", str(tmp),
        ]
        proc = subprocess.run(command, capture_output=True, text=True, timeout=3600)
        if proc.returncode != 0:
            raise RuntimeError(f"restart child failed: {proc.stderr[-2000:]}")
        restart = json.loads(child_json.read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    say(f"[{profiles}] compact {len(artifact)} B, naive {naive} B, ratio {len(artifact) / naive:.4f}; "
        f"encode {encode_s}s; restart verify {restart['restart_verification_seconds']}s")
    return {
        "profiles": profiles,
        "rows": rows,
        "outer": outer,
        "inner": inner,
        "grid": {
            "contexts": len(result.contexts), "conditions": len(result.conditions),
            "pair_cells": len(result.pair_cells), "validated_pairs": len(result.validated_pairs),
        },
        "groups": {
            "plan_group_universe": len(plan.group_universe),
            "outer_evaluation_rows": len(manifest.evaluation_ids),
            "outer_evaluation_groups": len(manifest.group_row_counts),
            "target_pool_rows": len(manifest.target_pool_ids),
        },
        "compact_artifact_bytes": len(artifact),
        "compact_artifact_mib": round(len(artifact) / MIB, 3),
        "naive_full_bytes": naive,
        "naive_full_mib": round(naive / MIB, 3),
        "compact_over_naive_ratio": round(len(artifact) / naive, 6),
        "naive_over_compact_factor": round(naive / len(artifact), 1),
        "stored_blob_bytes_on_disk": on_disk,
        "commit_decision": committed.decision.name,
        "encode_deterministic": deterministic,
        "encode_seconds_including_validation_and_self_decode": encode_s,
        "encode_repeat_seconds": encode_again_s,
        "encode_memory": encode_sampler.report(),
        "commit_seconds_including_encode_and_verification": commit_s,
        "execute_coordinate_seconds_for_comparison": execute_s,
        "restart_verification": restart,
        "record_versions": {
            "coordinate": store_module.COORDINATE_RECORD_VERSION,
            "cell": store_module.COMPACT_CELL_RECORD_VERSION,
            "store_schema": store_module.STORE_SCHEMA,
        },
    }


def _summary(payload: dict) -> str:
    lines = [payload["note"], payload["binding_note"], payload["memory_note"],
             f"script_sha256 {payload['script_sha256']}", ""]
    for item in payload["fixtures"]:
        restart = item["restart_verification"]
        lines += [
            f"profiles={item['profiles']}  rows={item['rows']}  groups={item['groups']['plan_group_universe']}",
            f"  compact {item['compact_artifact_bytes']:,} B ({item['compact_artifact_mib']} MiB)   "
            f"naive {item['naive_full_bytes']:,} B ({item['naive_full_mib']} MiB)   "
            f"compact/naive {item['compact_over_naive_ratio']}",
            f"  encode {item['encode_seconds_including_validation_and_self_decode']}s "
            f"(incl. validation + self-decode), peak WS rise {item['encode_memory']['sampled_peak_rise_mib']} MiB",
            f"  restart verify {restart['restart_verification_seconds']}s = reopen {restart['reopen_store_seconds']} "
            f"+ byte {restart['byte_verify_seconds']} + decode {restart['decode_seconds']} "
            f"+ validate {restart['validate_seconds']}; peak WS rise "
            f"{restart['phases_memory']['sampled_peak_rise_mib']} MiB (lower bound); "
            f"completed-id scan {restart['completed_ids_scan_seconds']}s",
            f"  restart memory: tracemalloc peak {restart['tracemalloc_restart_verify_peak_mib']} MiB; "
            f"child peak working set {round(restart['child_process_peak_working_set_bytes'] / MIB, 1)} MiB "
            f"(upper bound, includes dataset+plan build)",
            "",
        ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    from shiftguard.repeats.models import INNER_IDS, OUTER_SEEDS

    out = Path(args.out).resolve()
    refusal = base._prepare_out(out)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    log: list[str] = []

    def say(text: str) -> None:
        print(text, flush=True)
        log.append(text)

    outer = args.outer if args.outer is not None else OUTER_SEEDS[0]
    inner = args.inner if args.inner is not None else INNER_IDS[0]
    fixtures = [_measure(args.rows, profiles, outer, inner, say) for profiles in args.fixtures.split(",")]
    payload = {
        "note": NOTE,
        "binding_note": BINDING_NOTE,
        "memory_note": MEMORY_NOTE,
        "binding_exposure_status": "synthetic_fabricated",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "resource_preflight_script_sha256": hashlib.sha256(
            Path(base.__file__).read_bytes()).hexdigest(),
        "fixtures": fixtures,
        "versions": base._versions(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "argv": sys.argv,
    }
    (out / "store_preflight.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    summary = _summary(payload)
    (out / "summary.txt").write_text(summary, encoding="utf-8")
    (out / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print(summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=41188)
    parser.add_argument("--outer", type=int, default=None)
    parser.add_argument("--inner", type=int, default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fixtures", default="500,row", help="comma list of --profiles values to measure")
    parser.add_argument("--restart-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--profiles", default="500", help=argparse.SUPPRESS)
    parser.add_argument("--store", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--repeat-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--child-json", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.restart_child:
        return _restart_child(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
