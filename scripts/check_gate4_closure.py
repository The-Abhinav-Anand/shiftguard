"""Bounded Gate 4 evidence command. Test success is never automatic gate acceptance."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import uuid4
import xml.etree.ElementTree as ET

APP = Path(__file__).resolve().parents[1]
EVIDENCE = APP.parent / "verification/gate4-closure"
MATRIX = APP / "docs/gate4-acceptance.json"


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def snapshot():
    files = set()
    for name in ("shiftguard", "tests", "scripts", "configs", "alembic", "verification", ".agent", "frontend/src"):
        files.update(p for p in (APP / name).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix in (".py", ".json", ".yaml", ".yml", ".ini", ".md", ".tsx", ".ts", ".css", ".html"))
    files.update(APP / name for name in ("AGENTS.md", "pyproject.toml", "uv.lock", "Dockerfile", "docs/gate4-acceptance.json", "docs/gate4-closure.md", "docs/fix-ledger.md") if (APP / name).is_file())
    hashes = {p.relative_to(APP).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    return {"digest": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), "files": hashes}


def git_state():
    base = ["git", "-c", f"safe.directory={APP.as_posix()}", "-C", str(APP)]
    head = subprocess.run(base + ["rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    status = subprocess.run(base + ["status", "--porcelain"], capture_output=True, text=True, timeout=10, check=True).stdout
    return {"head": head, "dirty": bool(status.strip())}


def pytest_run(attempt, label, paths):
    report = attempt / f"{label}.xml"
    with tempfile.TemporaryDirectory(prefix="sg-closure-") as temp:
        cmd = [sys.executable, "-B", "-m", "pytest", *paths, "-q", "-p", "no:cacheprovider",
               "--basetemp", str(Path(temp) / "pytest"), "--tb=short", "--junitxml", str(report)]
        try:
            result = subprocess.run(cmd, cwd=APP, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=1800, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            output = result.stdout + result.stderr
            code = result.returncode
        except subprocess.TimeoutExpired:
            output, code = "Test phase exceeded 1800 seconds.\n", 124
    # Never publish a test connection URL from a traceback into review evidence.
    redact = lambda value: re.sub(r"postgres(?:ql)?(?:\+\w+)?://[^\s\"'<>]+", "postgresql://[REDACTED]", value)
    (attempt / f"{label}.txt").write_text(redact(output), encoding="utf-8")
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    if report.exists():
        xml = report.read_text(encoding="utf-8")
        # XML may contain credentials in failure text too.
        root = ET.fromstring(xml)
        for suite in root.iter("testsuite"):
            for key in counts:
                counts[key] += int(suite.get(key, "0"))
        report.write_text(redact(xml), encoding="utf-8")
    return {"exit_code": code, **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="store_true", help="After guards pass, run one full suite and check clean source identity")
    args = parser.parse_args()
    attempt = EVIDENCE / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:12])
    attempt.mkdir(parents=True, exist_ok=False)
    record = {"status": "IN_PROGRESS", "gate_accepted": False, "mode": "candidate" if args.candidate else "guards",
              "attempt": str(attempt), "started_at": datetime.now(timezone.utc).isoformat(), "blockers": []}
    # Publish this attempt before source/git/test work can fail. Older attempts stay intact.
    write_json(attempt / "summary.json", record)
    write_json(EVIDENCE / "current_attempt.json", {"attempt": str(attempt), "status": "IN_PROGRESS"})
    try:
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        before = snapshot()
        write_json(attempt / "source.json", before)
        record["git"] = git_state()
        record["matrix_version"] = matrix["version"]
        record["guards"] = pytest_run(attempt, "guards", [matrix["guard_file"]])
        guards = record["guards"]
        if guards["tests"] < matrix["minimum_guard_cases"]:
            record["blockers"].append("Acceptance cases missing or collection failed")
        if not os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL") or guards["skipped"]:
            record["blockers"].append("Required backend evidence missing/skipped")
        if guards["exit_code"] or guards["failures"] or guards["errors"]:
            record["status"] = "FAIL"
        elif record["blockers"]:
            record["status"] = "BLOCKED"
        elif not args.candidate:
            record["status"] = "GUARDS_PASSED"
        elif record["git"]["dirty"]:
            record["status"] = "BLOCKED"
            record["blockers"].append("Candidate source is not committed/clean; full suite not started")
        else:
            record["full_suite"] = pytest_run(attempt, "full-suite", ["tests"])
            full = record["full_suite"]
            if full["exit_code"] or full["failures"] or full["errors"] or not full["tests"]:
                record["status"] = "FAIL"
            elif full["skipped"]:
                record["status"] = "BLOCKED"
                record["blockers"].append("Full-suite skip needs explicit disposition")
            else:
                record["status"] = "TEST_EVIDENCE_READY"
        after = snapshot()
        record["source_unchanged"] = before["digest"] == after["digest"] and record["git"] == git_state()
        if not record["source_unchanged"]:
            record["status"] = "FAIL"
            record["blockers"].append("Source changed during verification")
        record["remaining_acceptance"] = ["coverage mapping for all eight contracts", "affected clean-source scientific reproduction", "one independent review and gate checkpoint"]
    except Exception as exc:
        record["status"] = "FAIL"
        record["blockers"].append(f"Verifier failed: {type(exc).__name__}")
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(attempt / "summary.json", record)
    write_json(EVIDENCE / "current_attempt.json", {"attempt": str(attempt), "status": record["status"]})
    print(json.dumps(record, indent=2))
    return 0 if record["status"] in ("GUARDS_PASSED", "TEST_EVIDENCE_READY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
