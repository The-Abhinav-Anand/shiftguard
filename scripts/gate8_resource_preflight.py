"""Gate 8 repeat-adapter resource preflight (plan item R1).

Runs the synthetic-gated development adapter on fabricated Bank-shaped rows at one declared
coordinate and records wall time, memory, artifact size and evaluator overhead. Fabricated
rows only; no real outcome is accessed. Only resource figures and counts are printed or
written; no loss, calibration or label-derived value ever leaves this process.

Environment note: sklearn's is_pandas_na retries a failed pandas import on each call, which
inflates profiled time (about a quarter of it in the first preflight); the unprofiled timing
pass is the one to trust for wall time.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import os
import platform
import pstats
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# shiftguard is an editable install; only the fixtures folder is appended (never prepended).
sys.path.append(str(ROOT / "tests" / "repeats_adapter"))

NOTE = "Fabricated Bank-shaped rows only; no real outcome accessed; resource measurement, not a result."
ENV_NOTE = ("sklearn is_pandas_na retries a failed pandas import on every call; this environment cost "
            "(about 25% of profiled time in the first preflight) is present in the profile pass only "
            "in proportion to profiler overhead; trust the unprofiled timing pass for wall time.")
MIB = 1024 * 1024


# ----------------------------------------------------------------------------- memory

def _memory() -> dict:
    """Current and peak memory of this process in bytes (Windows ctypes, else getrusage)."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class _ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return {
            "source": "GetProcessMemoryInfo",
            "working_set_bytes": counters.WorkingSetSize,
            "peak_working_set_bytes": counters.PeakWorkingSetSize,
            "private_commit_bytes": counters.PagefileUsage,
            "peak_private_commit_bytes": counters.PeakPagefileUsage,
        }
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    return {"source": "getrusage.ru_maxrss", "working_set_bytes": None,
            "peak_working_set_bytes": peak, "private_commit_bytes": None, "peak_private_commit_bytes": None}


# ----------------------------------------------------------------------------- fixtures

def _generate_dataset(rows: int, profiles: str):
    import numpy as np
    from development_fixtures import FIXTURE_SEED, fabricated_bank_dataset, fake_digest
    from shiftguard.datasets.bank import BANK_FEATURES, BankDataset

    if profiles == "500":
        return fabricated_bank_dataset(rows, FIXTURE_SEED)

    per_row = profiles == "row"
    base_count = rows if per_row else int(profiles)
    rng = np.random.default_rng(FIXTURE_SEED)
    jobs = ("admin.", "blue-collar", "technician", "services", "retired", "unknown")
    marital = ("married", "single", "divorced")
    education = ("basic.9y", "high.school", "university.degree")
    flags = ("no", "yes", "unknown")
    outcomes = ("failure", "success")
    ages = tuple(range(18, 96)) if per_row else (22, 28, 34, 41, 47, 55, 63)
    prev_values = (0, 0, 0, 1, 2, 3, 4, 5, 6, 7) if per_row else (0, 0, 0, 1, 2)
    pdays_values = tuple(range(0, 28)) if per_row else (3, 6, 12)

    bases = []
    for _ in range(base_count):
        previous = int(rng.choice(prev_values))
        bases.append({
            "age": str(int(rng.choice(ages))),
            "job": str(rng.choice(jobs, p=(0.3, 0.25, 0.2, 0.1, 0.1, 0.05))),
            "marital": str(rng.choice(marital, p=(0.55, 0.3, 0.15))),
            "education": str(rng.choice(education)),
            "default": str(rng.choice(flags, p=(0.8, 0.05, 0.15))),
            "housing": str(rng.choice(flags, p=(0.45, 0.5, 0.05))),
            "loan": str(rng.choice(flags, p=(0.8, 0.15, 0.05))),
            "pdays": "999" if previous == 0 else str(int(rng.choice(pdays_values))),
            "previous": str(previous),
            "poutcome": "nonexistent" if previous == 0 else str(rng.choice(outcomes)),
        })
    if per_row:
        picks = range(rows)
    else:
        weights = 1.0 / (np.arange(base_count) + 3.0)
        weights /= weights.sum()
        picks = rng.choice(base_count, size=rows, p=weights)
    out = []
    for row_id, pick in enumerate(picks, start=1):
        base = bases[int(pick)]
        logit = (
            -1.7 + 1.9 * (base["poutcome"] == "success") + 0.8 * (int(base["previous"]) > 0)
            + 0.6 * (base["job"] == "retired") + 0.015 * (int(base["age"]) - 40)
        )
        label = int(rng.random() < 1.0 / (1.0 + np.exp(-logit)))
        out.append({"row_id": row_id, **{name: base[name] for name in BANK_FEATURES}, "y": label})
    return BankDataset(out, raw_hash=fake_digest("raw"), clean_hash=fake_digest("clean"))


# ----------------------------------------------------------------------------- helpers

def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-c", "safe.directory=*", *args], cwd=ROOT,
                             capture_output=True, text=True, timeout=60)
        return out.stdout
    except Exception:
        return None


def _versions() -> dict:
    import numpy
    import sklearn
    return {"python": sys.version.split()[0], "numpy": numpy.__version__, "sklearn": sklearn.__version__}


def _component_bytes(value) -> int:
    from shiftguard.repeats.completion import serialize_artifact
    return len(serialize_artifact(value))


def _artifact_full(plan, result) -> dict:
    """build_completion over the full content (cells, conditions, contexts); bytes held in memory only."""
    from shiftguard.repeats.completion import build_completion
    content = {
        "synthetic": True,
        "cells": [c.to_canonical() for c in result.pair_cells],
        "conditions": [c.to_canonical() for c in result.conditions],
        "contexts": [c.to_canonical() for c in result.contexts],
    }
    _record, artifact = build_completion(plan, result.repeat_id, content, "completed")
    return {"bytes": len(artifact), "content": content}


def _artifact_breakdown(plan, result, content: dict) -> dict:
    from shiftguard.repeats.completion import build_completion
    contexts = result.contexts
    breakdown = {
        "cells_bytes": _component_bytes(content["cells"]),
        "conditions_bytes": _component_bytes(content["conditions"]),
        "contexts_bytes": _component_bytes(content["contexts"]),
        "contexts_evaluation_ids_bytes": sum(_component_bytes(list(c.evaluation_ids)) for c in contexts),
        "contexts_group_map_bytes": sum(_component_bytes([list(p) for p in c.group_map]) for c in contexts),
        "contexts_acquired_prefix_bytes": sum(_component_bytes(list(c.acquired_prefix)) for c in contexts),
    }
    _r, a = build_completion(plan, result.repeat_id, {
        "synthetic": True, "cells": content["cells"], "conditions": content["conditions"]}, "completed")
    breakdown["variant_a_cells_conditions_only_envelope_bytes"] = len(a)
    _r, b = build_completion(plan, result.repeat_id, {
        "synthetic": True, "cells": content["cells"], "conditions": content["conditions"],
        "contexts": [c.digest for c in contexts]}, "completed")
    breakdown["variant_b_contexts_by_digest_envelope_bytes"] = len(b)
    return breakdown


def _fn_rows(stats: pstats.Stats, limit: int = 30) -> list[str]:
    rows = sorted(stats.stats.items(), key=lambda kv: kv[1][3], reverse=True)[:limit]
    lines = [f"{'ncalls':>10} {'tottime':>10} {'cumtime':>10}  function"]
    for (fname, line, name), (_, nc, tt, ct, _callers) in rows:
        lines.append(f"{nc:>10} {tt:>10.3f} {ct:>10.3f}  {Path(fname).name}:{line}({name})")
    return lines


def _scorer_span() -> tuple[int, int]:
    import inspect
    from shiftguard.repeats import development_adapter as adapter
    lines, start = inspect.getsourcelines(adapter._EvaluatorPrivateGroupScorer)
    return start, start + len(lines) - 1


def _evaluator_attribution(stats: pstats.Stats, seconds: float) -> dict:
    start, end = _scorer_span()
    sums_cum = init_cum = evaluator_self = score_cum = 0.0
    entries = []
    for (fname, line, name), (_, nc, tt, ct, _callers) in stats.stats.items():
        base = Path(fname).name
        if base == "development_adapter.py" and start <= line <= end:
            entries.append({"name": name, "line": line, "calls": nc, "cumulative_seconds": round(ct, 4)})
            if name == "evaluator_private_paired_group_sums":
                sums_cum += ct
            elif name == "__init__":
                init_cum += ct
        if base == "evaluator.py":
            evaluator_self += tt
            if name == "score":
                score_cum += ct

    def frac(value: float) -> float | None:
        return round(value / seconds, 6) if seconds else None

    return {
        "phase_seconds_profiled_wall": round(seconds, 4),
        "scorer_paired_sums_cumulative_seconds": round(sums_cum, 4),
        "scorer_paired_sums_fraction_of_profiled": frac(sums_cum),
        "scorer_init_cumulative_seconds": round(init_cum, 4),
        "scorer_init_fraction_of_profiled": frac(init_cum),
        "final_test_evaluator_score_cumulative_seconds": round(score_cum, 4),
        "final_test_evaluator_score_fraction_of_profiled": frac(score_cum),
        "evaluator_py_total_self_seconds": round(evaluator_self, 4),
        "scorer_method_entries": sorted(entries, key=lambda e: (e["line"], e["name"])),
    }


def _prepare_out(path: Path) -> str | None:
    if path.exists():
        if not path.is_dir():
            return f"refusing: {path} exists and is not a directory"
        if any(path.iterdir()):
            return f"refusing: {path} exists and is non-empty"
        return None
    path.mkdir(parents=True, exist_ok=False)
    return None


# ----------------------------------------------------------------------------- main

def run(args: argparse.Namespace) -> int:
    from shiftguard.repeats import development_adapter as adapter
    from shiftguard.repeats.models import BUDGETS, INNER_IDS, METHODS, OUTER_SEEDS, RepeatSpec, SCENARIOS
    from development_fixtures import fabricated_binding

    if args.profiles != "row" and not args.profiles.isdigit():
        print("--profiles must be an integer or 'row'", file=sys.stderr)
        return 2
    outer = args.outer if args.outer is not None else OUTER_SEEDS[0]
    inner = args.inner if args.inner is not None else INNER_IDS[0]
    out = Path(args.out).resolve()
    refusal = _prepare_out(out)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    log: list[str] = []

    def say(text: str) -> None:
        print(text, flush=True)
        log.append(text)

    # Unbiased evaluator timing: wrap the scorer method in this process only (timing pass only).
    evaluator_acc = {"seconds": 0.0, "calls": 0}
    if not args.profile:
        original = adapter._EvaluatorPrivateGroupScorer.evaluator_private_paired_group_sums

        def timed(self, *a, **k):
            t = time.perf_counter()
            try:
                return original(self, *a, **k)
            finally:
                evaluator_acc["seconds"] += time.perf_counter() - t
                evaluator_acc["calls"] += 1

        adapter._EvaluatorPrivateGroupScorer.evaluator_private_paired_group_sums = timed

    phases: dict[str, dict] = {}
    memory_per_phase: dict[str, dict] = {}
    profilers: dict[str, cProfile.Profile] = {}
    mem_start = _memory()

    def phase(name: str, fn, profiled: bool = False):
        before = _memory()
        prof = cProfile.Profile() if (args.profile and profiled) else None
        t0 = time.perf_counter()
        if prof:
            prof.enable()
        value = fn()
        if prof:
            prof.disable()
            profilers[name] = prof
        seconds = time.perf_counter() - t0
        after = _memory()
        phases[name] = {"seconds": round(seconds, 4)}
        memory_per_phase[name] = {"before": before, "after": after}
        say(f"phase {name}: {seconds:.2f}s  working_set {before['working_set_bytes']} -> "
            f"{after['working_set_bytes']}  peak_ws {after['peak_working_set_bytes']} "
            f"peak_commit {after['peak_private_commit_bytes']}")
        return value

    say(f"gate8 resource preflight rows={args.rows} profiles={args.profiles} outer={outer} inner={inner} "
        f"profile={args.profile}")
    dataset = phase("generate_dataset", lambda: _generate_dataset(args.rows, args.profiles))
    binding = fabricated_binding(dataset)
    spec = RepeatSpec()
    plan = phase("plan", lambda: adapter.plan_development_repeats(dataset, binding, spec))
    prepared = phase("prepare_outer", lambda: adapter.prepare_outer(dataset, plan, outer), profiled=True)
    result = phase("execute_coordinate", lambda: adapter.execute_coordinate(
        prepared, inner, scenarios=SCENARIOS, budgets=BUDGETS, methods=METHODS), profiled=True)
    phase("validate_coordinate_result", lambda: adapter.validate_coordinate_result(plan, result))
    full = phase("artifact_serialize", lambda: _artifact_full(plan, result))
    breakdown = phase("artifact_breakdown", lambda: _artifact_breakdown(plan, result, full["content"]))
    artifact_bytes = full["bytes"]
    del full
    final_mem = _memory()

    roles = plan.roles(outer)
    group_counts = {
        "profiles_setting": args.profiles,
        "plan_group_universe": len(plan.group_universe),
        "dataset_distinct_feature_tuples": len({
            tuple(r[f] for f in ("age", "job", "marital", "education", "default", "housing", "loan",
                                 "pdays", "previous", "poutcome")) for r in dataset.rows}),
        "outer_evaluation_rows": len(roles.evaluation_ids),
        "outer_evaluation_groups": len(roles.group_row_counts),
        "outer_largest_evaluation_group_rows": max(roles.group_row_counts.values()),
    }

    prepare_s = phases["prepare_outer"]["seconds"]
    execute_s = phases["execute_coordinate"]["seconds"]
    n_outer, n_inner = len(OUTER_SEEDS), len(INNER_IDS)
    total_s = n_outer * prepare_s + n_outer * n_inner * execute_s
    total_bytes = n_outer * n_inner * artifact_bytes
    peak_ws = final_mem["peak_working_set_bytes"]
    peak_commit = final_mem["peak_private_commit_bytes"]
    payload = {
        "note": NOTE,
        "environment_note": ENV_NOTE,
        "profile_pass": bool(args.profile),
        "timing_valid": not args.profile,
        "rows": args.rows, "profiles": args.profiles, "outer": outer, "inner": inner,
        "groups": group_counts,
        "grid": {
            "scenarios": len(SCENARIOS), "budgets": len(BUDGETS), "methods": len(METHODS),
            "conditions_in_result": len(result.conditions),
            "pair_cells_in_result": len(result.pair_cells),
            "contexts_in_result": len(result.contexts),
            "validated_pairs_in_result": len(result.validated_pairs),
        },
        "phase_seconds": phases,
        "memory": {
            "at_start": mem_start, "per_phase": memory_per_phase, "at_end": final_mem,
            "peak_after_execute_working_set_bytes":
                memory_per_phase["execute_coordinate"]["after"]["peak_working_set_bytes"],
            "peak_after_execute_private_commit_bytes":
                memory_per_phase["execute_coordinate"]["after"]["peak_private_commit_bytes"],
            "peak_after_serialization_working_set_bytes":
                memory_per_phase["artifact_serialize"]["after"]["peak_working_set_bytes"],
            "peak_after_serialization_private_commit_bytes":
                memory_per_phase["artifact_serialize"]["after"]["peak_private_commit_bytes"],
            "process_peak_working_set_bytes": peak_ws,
            "process_peak_working_set_mib": round(peak_ws / MIB, 1),
            "process_peak_private_commit_bytes": peak_commit,
            "process_peak_private_commit_mib": round(peak_commit / MIB, 1) if peak_commit else None,
        },
        "artifact": {
            "bytes": artifact_bytes,
            "mib": round(artifact_bytes / MIB, 3),
            "method": "completion.build_completion(plan, repeat_id, {synthetic, cells, conditions, contexts}, "
                      "'completed') bytes; held in memory only; excludes ValidatedPair probability arrays "
                      "(no canonical form in the store path)",
            "breakdown_bytes": breakdown,
        },
        "extrapolation_ESTIMATE": None if args.profile else {
            "label": "ESTIMATE only, fixture-specific (this fabricated profiles setting; real Bank group "
                     "cardinality and feature variety may differ): 5 outer x 10 inner sequential = "
                     "5*prepare + 50*execute; ignores dataset/plan/validate/serialization and "
                     "coordinate-to-coordinate variation",
            "seconds": round(total_s, 1),
            "hours": round(total_s / 3600, 2),
            "artifact_total_bytes": total_bytes,
            "artifact_total_mib": round(total_bytes / MIB, 1),
            "artifact_total_gb_decimal": round(total_bytes / 1e9, 3),
        },
        "versions": _versions(), "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "git_head": (_git("rev-parse", "HEAD") or "").strip() or None,
        "provenance": {
            "argv": sys.argv,
            "output_path": str(out),
            "git_status_porcelain_sha256": hashlib.sha256((_git("status", "--porcelain") or "").encode()).hexdigest(),
            "git_dirty": bool((_git("status", "--porcelain") or "").strip()),
            "len_sys_path": len(sys.path),
        },
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "binding_exposure_status": binding.exposure_status,
    }
    if not args.profile:
        payload["evaluator_unprofiled"] = {
            "method": "perf_counter accumulator around _EvaluatorPrivateGroupScorer."
                      "evaluator_private_paired_group_sums (monkeypatched in this process only)",
            "calls": evaluator_acc["calls"],
            "seconds": round(evaluator_acc["seconds"], 4),
            "fraction_of_execute": round(evaluator_acc["seconds"] / execute_s, 6) if execute_s else None,
        }
        say(f"evaluator unprofiled: {evaluator_acc['seconds']:.2f}s over {evaluator_acc['calls']} calls "
            f"= {evaluator_acc['seconds'] / execute_s:.4f} of execute")

    if args.profile:
        buf = io.StringIO()
        for name in ("prepare_outer", "execute_coordinate"):
            stats = pstats.Stats(profilers[name], stream=buf)
            buf.write(f"== {name}: top 30 by cumulative time ==\n")
            buf.write("\n".join(_fn_rows(stats)) + "\n\n")
            attribution = _evaluator_attribution(stats, phases[name]["seconds"])
            buf.write(f"== {name}: evaluator attribution ==\n{json.dumps(attribution, indent=2)}\n\n")
            payload.setdefault("evaluator_overhead", {})[name] = attribution
        (out / "profile.txt").write_text(buf.getvalue(), encoding="utf-8")
        ex = payload["evaluator_overhead"]["execute_coordinate"]
        say(f"evaluator fraction of profiled execute: scorer={ex['scorer_paired_sums_fraction_of_profiled']}")

    say(f"groups: {json.dumps(group_counts)}")
    say(f"artifact bytes={artifact_bytes}; breakdown={json.dumps(breakdown)}")
    (out / "preflight.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    say(f"wrote {out}")
    (out / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=41188)
    parser.add_argument("--outer", type=int, default=None)
    parser.add_argument("--inner", type=int, default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--profiles", default="500", help="N base profiles, or 'row' for one base per row")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
