"""Run one fresh, source-bound offline Gate 7 public-regression campaign attempt."""

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
import time
from uuid import uuid4
import xml.etree.ElementTree as ET


APP = Path(__file__).resolve().parents[1]
OUTER = APP.parent
EVIDENCE_ROOT = OUTER / "verification" / "gate7-candidate-campaign"
MATRIX = APP / "tests" / "agent" / "fixtures" / "gate7_adversarial_matrix.json"
TEST_FILE = "tests/agent/test_gate7_adversarial_campaign.py"
OWNED_PATHS = (
    "tests/agent/test_gate7_adversarial_campaign.py",
    "tests/agent/fixtures/gate7_adversarial_matrix.json",
    "scripts/check_gate7_candidate.py",
    "docs/gate7-candidate-contract.md",
    "shiftguard/agent/provider.py",
    "shiftguard/settings.py",
    "scripts/preflight_nebius.py",
    "tests/agent/test_g7_live_provider_controls.py",
    "tests/agent/test_gate7_candidate_evidence.py",
    "tests/agent/test_gate7_execution_authority.py",
    "tests/agent/test_gate7_summary_oracle.py",
    "tests/agent/test_luna_g6_semantics.py",
    "tests/agent/test_g6_comprehensive_protocol.py",
)
BASELINE_SOURCE = OUTER / "verification" / "gate6-comprehensive-20261002" / "final-source.json"
PROTECTED_LIST = OUTER / "verification" / "product-recovery-20261002" / "protected-source-comparison.json"
SUPPLEMENT_SOURCE = OUTER / "verification" / "product-execution-20261001" / "frontend-cleanup-major-01" / "prior-source-review-binding.json"
POSTGRES_URL_PATTERN = re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s\"'<>]+", re.IGNORECASE)
BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_.-]{8,}")
KEY_PATTERN = re.compile(r"(?i)((?:api[_-]?key|token|password|passwd|pwd)\s*[=:]\s*)[^\s,;\"']+")


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_hashes(paths: tuple[str, ...] = OWNED_PATHS) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    runtime_paths = tuple(path.relative_to(APP).as_posix() for path in (APP / "shiftguard").rglob("*.py"))
    for relative in sorted(set(paths + runtime_paths)):
        path = APP / relative
        result[relative] = sha256_bytes(path.read_bytes()) if path.is_file() else None
    return result


def git_state() -> dict[str, object]:
    base = ["git", "-c", f"safe.directory={APP.as_posix()}", "-C", str(APP)]
    head_result = subprocess.run(base + ["rev-parse", "HEAD"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=20)
    status_result = subprocess.run(base + ["status", "--porcelain=v1", "--untracked-files=normal"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    if head_result.returncode or status_result.returncode:
        return {"available": False, "error": "git_state_unavailable"}
    status = status_result.stdout
    return {
        "available": True,
        "head": head_result.stdout.strip(),
        "dirty": bool(status.strip()),
        "status_sha256": sha256_bytes(status.encode("utf-8")),
    }


# Ordinary chat's only permitted settings addition: one default-off flag.
GENERAL_CHAT_FIELD = '''    general_chat_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("SHIFTGUARD_GENERAL_CHAT_ENABLED", "general_chat_enabled"),
    )
'''
# The app factory's only permitted changes, as (current text, baseline text): ordinary-chat
# wiring, exclusive ordinary-dispatch ownership around startup recovery (OR-02), a lifespan
# that releases that ownership after the provider closes, including on startup failure, and
# JSON-safe validation errors (OR-09). Everything else must reconstruct the baseline bytes.
_APP_FACTORY_VALIDATION_ERRORS = '''_MAX_VALIDATION_ERRORS = 20
_MAX_LOCATION_PARTS = 8
_MAX_LOCATION_PART_CHARS = 64
_MAX_ERROR_TEXT_CHARS = 200


def _public_validation_errors(errors) -> list[dict[str, object]]:
    """Project Pydantic errors onto JSON primitives; never echo input or exception objects."""
    public: list[dict[str, object]] = []
    for error in list(errors)[:_MAX_VALIDATION_ERRORS]:
        location: list[object] = []
        for part in tuple(error.get("loc", ()))[:_MAX_LOCATION_PARTS]:
            if type(part) is int:
                location.append(part)
            else:
                location.append(str(part)[:_MAX_LOCATION_PART_CHARS])
        public.append(
            {
                "loc": location,
                "type": str(error.get("type", "value_error"))[:_MAX_LOCATION_PART_CHARS],
                "msg": str(error.get("msg", "Invalid value"))[:_MAX_ERROR_TEXT_CHARS],
            }
        )
    return public


'''
_APP_FACTORY_LIFESPAN = '''    ordinary_owner: OrdinaryDispatchOwner | None = None
    try:
        check_database_connection(engine)
        app.state.engine = engine

        ordinary_budget = None
        if not test_harness and (settings.agent_enabled or settings.general_chat_enabled):
            # Own dispatch for this database before treating any open reservation as abandoned.
            ordinary_owner = OrdinaryDispatchOwner(engine)
            ordinary_owner.acquire()
            ordinary_budget = OrdinaryBudget(engine, owner=ordinary_owner)
            ordinary_budget.recover_unresolved()
        app.state.ordinary_budget = ordinary_budget

        agent_provider = getattr(app.state, "agent_provider", None)
        if agent_provider is None:
            agent_provider = AgentProvider(settings, ordinary_budget=ordinary_budget)
            app.state.agent_provider = agent_provider

        stop_event = threading.Event()
        worker_threads: list[threading.Thread] = []
        queue = None

        enable_worker = getattr(app.state, "enable_worker", None)
        if enable_worker is None:
            enable_worker = settings.embedded_worker

        if enable_worker:
            if test_worker_factory is not None:
                queue = test_worker_factory.create_queue(engine)
                worker = test_worker_factory.create_worker(settings)
            else:
                queue = JobQueue(engine)
                worker = ExperimentWorker(settings, heartbeat_interval=5, lease_seconds=30)

            def _worker_runner():
                worker.run_loop(queue, stop_event, poll_interval=settings.worker_poll_interval)

            def _recovery_runner():
                run_recovery_loop(engine, settings.artifact_root, stop_event, interval=settings.recovery_interval)

            t_worker = threading.Thread(target=_worker_runner, daemon=True, name="shiftguard-embedded-worker")
            t_recovery = threading.Thread(target=_recovery_runner, daemon=True, name="shiftguard-embedded-recovery")
            t_worker.start()
            t_recovery.start()
            worker_threads.extend([t_worker, t_recovery])

        try:
            yield
        finally:
            stop_event.set()
            if test_worker_factory is not None and queue is not None:
                test_worker_factory.shutdown(queue)
            for t in worker_threads:
                t.join(timeout=3.0)
    finally:
        try:
            if getattr(app.state, "agent_provider", None) is not None:
                await app.state.agent_provider.close()
        finally:
            # Dispatch has stopped (provider closed) before ownership is released,
            # on startup failure as well as normal shutdown.
            if ordinary_owner is not None:
                ordinary_owner.close()
            engine.dispose()
'''
_BASELINE_LIFESPAN = '''    check_database_connection(engine)
    app.state.engine = engine

    agent_provider = getattr(app.state, "agent_provider", None)
    if agent_provider is None:
        agent_provider = AgentProvider(settings)
        app.state.agent_provider = agent_provider

    stop_event = threading.Event()
    worker_threads: list[threading.Thread] = []
    queue = None

    enable_worker = getattr(app.state, "enable_worker", None)
    if enable_worker is None:
        enable_worker = settings.embedded_worker

    if enable_worker:
        if test_worker_factory is not None:
            queue = test_worker_factory.create_queue(engine)
            worker = test_worker_factory.create_worker(settings)
        else:
            queue = JobQueue(engine)
            worker = ExperimentWorker(settings, heartbeat_interval=5, lease_seconds=30)

        def _worker_runner():
            worker.run_loop(queue, stop_event, poll_interval=settings.worker_poll_interval)

        def _recovery_runner():
            run_recovery_loop(engine, settings.artifact_root, stop_event, interval=settings.recovery_interval)

        t_worker = threading.Thread(target=_worker_runner, daemon=True, name="shiftguard-embedded-worker")
        t_recovery = threading.Thread(target=_recovery_runner, daemon=True, name="shiftguard-embedded-recovery")
        t_worker.start()
        t_recovery.start()
        worker_threads.extend([t_worker, t_recovery])

    yield

    stop_event.set()
    if test_worker_factory is not None and queue is not None:
        test_worker_factory.shutdown(queue)
    for t in worker_threads:
        t.join(timeout=3.0)
    if hasattr(app.state, "agent_provider") and app.state.agent_provider is not None:
        await app.state.agent_provider.close()
    engine.dispose()
'''
APP_FACTORY_ORDINARY_CHAT = (
    (
        "from shiftguard.agent.ordinary_budget import OrdinaryBudget\n"
        "from shiftguard.agent.ordinary_owner import OrdinaryDispatchOwner\n"
        "from shiftguard.api.routes import agent, agent_requests, chat, experiments, health, jobs, metadata\n",
        "from shiftguard.api.routes import agent, agent_requests, experiments, health, jobs, metadata\n",
    ),
    (_APP_FACTORY_VALIDATION_ERRORS, ""),
    (_APP_FACTORY_LIFESPAN, _BASELINE_LIFESPAN),
    (
        '                    "details": {"errors": _public_validation_errors(exc.errors())},\n',
        '                    "details": {"errors": exc.errors()},\n',
    ),
    (
        "    app.include_router(agent_requests.router)\n    app.include_router(chat.router)\n",
        "    app.include_router(agent_requests.router)\n",
    ),
)


def _matches_baseline(restored: str, expected: str | None) -> bool:
    # The baseline's line-ending convention is kept; no other text is ignored.
    return any(sha256_bytes(value.encode("utf-8")) == expected for value in (restored, restored.replace("\n", "\r\n")))


def authorized_settings_delta(content: bytes, expected: str | None) -> bool:
    """Only the exact default-off provider and general-chat additions may differ from baseline."""
    field = '''    nebius_enable_thinking: bool = Field(
        default=False,
        validation_alias=AliasChoices("NEBIUS_ENABLE_THINKING", "nebius_enable_thinking"),
    )
'''
    property_block = '''    @property
    def nebius_chat_template_kwargs(self) -> dict[str, bool]:
        return {"enable_thinking": self.nebius_enable_thinking}


'''
    try:
        source = content.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return False
    if source.count(field) != 1 or source.count(property_block) != 1 or source.count(GENERAL_CHAT_FIELD) > 1:
        return False
    restored = source.replace(field, "").replace(property_block, "").replace(GENERAL_CHAT_FIELD, "")
    return _matches_baseline(restored, expected)


def authorized_app_factory_delta(content: bytes, expected: str | None) -> bool:
    """Only the exact ordinary-chat wiring may differ from the baseline app factory."""
    try:
        restored = content.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return False
    for current, baseline in APP_FACTORY_ORDINARY_CHAT:
        if restored.count(current) != 1:
            return False
        restored = restored.replace(current, baseline)
    return _matches_baseline(restored, expected)


def protected_comparison() -> dict[str, object]:
    if not BASELINE_SOURCE.is_file() or not PROTECTED_LIST.is_file() or not SUPPLEMENT_SOURCE.is_file():
        return {"status": "BLOCKED", "reason": "retained Gate 6 protected-file baseline is unavailable", "files": []}
    baseline = json.loads(BASELINE_SOURCE.read_text(encoding="utf-8-sig"))
    protected = json.loads(PROTECTED_LIST.read_text(encoding="utf-8-sig"))
    supplement = json.loads(SUPPLEMENT_SOURCE.read_text(encoding="utf-8-sig"))
    baseline_files = baseline.get("files")
    paths = protected.get("snapshot_matched_backend_contracts")
    if not isinstance(baseline_files, dict) or not isinstance(paths, list) or not paths:
        return {"status": "BLOCKED", "reason": "retained protected-file manifest is incomplete", "files": []}

    comparisons = []
    for relative in sorted(set(paths)):
        expected = baseline_files.get(relative)
        baseline_origin = "gate6-final-source"
        if expected is None:
            expected = supplement.get("file_hashes", {}).get(relative)
            baseline_origin = "prior-source-review-binding"
        path = APP / Path(relative)
        content = path.read_bytes() if path.is_file() else None
        actual = sha256_bytes(content) if content is not None else None
        permitted_delta = bool(relative == "shiftguard/settings.py" and content is not None
                               and authorized_settings_delta(content, expected))
        app_factory_delta = bool(relative == "shiftguard/api/main.py" and content is not None
                                 and authorized_app_factory_delta(content, expected))
        ordinary_chat_delta = app_factory_delta or bool(
            permitted_delta and GENERAL_CHAT_FIELD.encode("utf-8") in content.replace(b"\r\n", b"\n")
        )
        comparisons.append({
            "path": relative,
            "baseline_sha256": expected,
            "candidate_sha256": actual,
            "matches": bool(expected and actual and (expected == actual or permitted_delta or app_factory_delta)),
            "byte_identical": bool(expected and actual and expected == actual),
            "authorized_provider_only_delta": permitted_delta,
            "authorized_ordinary_chat_delta": ordinary_chat_delta,
            "baseline_origin": baseline_origin,
            "baseline_present": bool(expected),
            "candidate_present": actual is not None,
        })

    migration_paths = sorted(
        path for path in baseline_files
        if path.startswith("shiftguard/alembic/versions/")
        and Path(path).name[:4].isdigit()
    )
    migrations = []
    for relative in migration_paths:
        expected = baseline_files[relative]
        path = APP / Path(relative)
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        migrations.append({
            "path": relative,
            "baseline_sha256": expected,
            "candidate_sha256": actual,
            "matches": bool(actual and expected == actual),
        })

    complete = all(row["baseline_present"] and row["candidate_present"] for row in comparisons)
    unchanged = complete and all(row["matches"] for row in comparisons) and all(row["matches"] for row in migrations)
    return {
        "status": "MATCH" if unchanged else ("MISMATCH" if complete else "BLOCKED"),
        "baseline_source_digest": baseline.get("digest"),
        "baseline_manifest_sha256": sha256_bytes(BASELINE_SOURCE.read_bytes()),
        "supplement_manifest_sha256": sha256_bytes(SUPPLEMENT_SOURCE.read_bytes()),
        "protected_contract_count": len(comparisons),
        "protected_contract_matches": sum(row["matches"] for row in comparisons),
        "byte_identical_protected_contracts": sum(row["byte_identical"] for row in comparisons),
        "authorized_provider_only_deltas": sum(row["authorized_provider_only_delta"] for row in comparisons),
        "authorized_ordinary_chat_deltas": sum(row["authorized_ordinary_chat_delta"] for row in comparisons),
        "applied_migration_count": len(migrations),
        "applied_migration_matches": sum(row["matches"] for row in migrations),
        "files": comparisons,
        "applied_migrations": migrations,
    }


def redact_output(value: str, matrix: dict[str, object]) -> str:
    value = POSTGRES_URL_PATTERN.sub("postgresql://[REDACTED]", value)
    value = BEARER_PATTERN.sub(r"\1[REDACTED]", value)
    value = KEY_PATTERN.sub(r"\1[REDACTED]", value)
    for case in matrix.get("cases", []):
        marker = case.get("secret_marker") if isinstance(case, dict) else None
        if isinstance(marker, str) and marker:
            value = value.replace(marker, "[REDACTED_TEST_MARKER]")
    return value


def expected_execution_ids(matrix: dict[str, object]) -> list[str]:
    values: list[str] = []
    for case in matrix["cases"]:
        backends = case.get("backends", ["sqlite"])
        values.extend(f"{case['id']}--{backend}" for backend in backends)
    return sorted(values)


def parse_junit(path: Path, expected_ids: list[str]) -> dict[str, object]:
    if not path.is_file():
        return {"available": False, "tests": 0, "failures": 0, "errors": 0, "skipped": 0,
                "collected_ids": [], "missing_ids": expected_ids, "unexpected_ids": [],
                "accounting_complete": False}
    root = ET.parse(path).getroot()
    counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    collected = []
    for suite in root.iter("testsuite"):
        for key in counts:
            counts[key] += int(suite.get(key, "0"))
        for test in suite.findall("testcase"):
            name = test.get("name", "")
            prefix = "test_gate7_public_regression["
            if name.startswith(prefix) and name.endswith("]"):
                collected.append(name[len(prefix):-1])
    expected_set = set(expected_ids)
    collected_set = set(collected)
    duplicates = sorted(value for value in collected_set if collected.count(value) != 1)
    missing = sorted(expected_set - collected_set)
    unexpected = sorted(collected_set - expected_set)
    complete = not missing and not unexpected and not duplicates and counts["tests"] == len(expected_ids)
    return {
        "available": True,
        **counts,
        "collected_ids": sorted(collected),
        "missing_ids": missing,
        "unexpected_ids": unexpected,
        "duplicate_ids": duplicates,
        "accounting_complete": complete,
    }


def run_tests(attempt: Path) -> tuple[dict[str, object], str]:
    junit = attempt / "junit.xml"
    with tempfile.TemporaryDirectory(prefix="shiftguard-gate7-pytest-") as fresh_temp:
        basetemp = Path(fresh_temp) / "pytest"
        command = [
            sys.executable, "-B", "-m", "pytest", TEST_FILE,
            "-q", "-p", "no:cacheprovider", "--tb=short",
            "--basetemp", str(basetemp), "--junitxml", str(junit),
        ]
        started = time.monotonic()
        try:
            result = subprocess.run(
                command,
                cwd=APP,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            )
            output = result.stdout + result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "") + "\nGate 7 campaign exceeded 1800 seconds.\n"
            exit_code = 124
        duration = round(time.monotonic() - started, 3)

    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    output = redact_output(output, matrix)
    (attempt / "pytest.log").write_text(output, encoding="utf-8")
    if junit.is_file():
        xml_text = redact_output(junit.read_text(encoding="utf-8"), matrix)
        junit.write_text(xml_text, encoding="utf-8")
    accounting = parse_junit(junit, expected_execution_ids(matrix))
    return ({"exit_code": exit_code, "duration_seconds": duration, **accounting}, output)


def markdown_report(record: dict[str, object]) -> str:
    tests = record.get("tests", {})
    protected = record.get("protected_files", {})
    lines = [
        "# Gate 7 offline public-regression candidate attempt",
        "",
        f"- Attempt: `{record['attempt_id']}`",
        f"- Offline campaign status: **{record['status']}**",
        f"- Case accounting: {tests.get('tests', 0)} collected; {tests.get('failures', 0)} failures; "
        f"{tests.get('errors', 0)} errors; {tests.get('skipped', 0)} skipped; "
        f"complete={tests.get('accounting_complete', False)}",
        f"- Protected-file comparison: **{protected.get('status', 'BLOCKED')}** "
        f"({protected.get('protected_contract_matches', 0)}/{protected.get('protected_contract_count', 0)} "
        "contracts and "
        f"{protected.get('applied_migration_matches', 0)}/{protected.get('applied_migration_count', 0)} migrations match)",
        f"- PostgreSQL authority evidence: **{record.get('postgres_authority_evidence', 'NOT_RUN')}**",
        "- Gate 6 acceptance: **PENDING**",
        "- Gate 7 acceptance: **PENDING parent exact-source review and checkpoint**",
        "- Live-model quality / provider evidence: **NOT ESTABLISHED BY THIS OFFLINE CAMPAIGN**",
        "",
        "## Exact case IDs",
        "",
    ]
    lines.extend(f"- `{case_id}`" for case_id in tests.get("collected_ids", []))
    lines.extend(["", "## Blockers", ""])
    blockers = record.get("blockers", [])
    lines.extend(f"- {blocker}" for blocker in blockers)
    if not blockers:
        lines.append("- None for offline campaign execution.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    attempt_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:12]
    attempt = EVIDENCE_ROOT / f"attempt-{attempt_id}"
    attempt.mkdir(parents=False, exist_ok=False)
    record: dict[str, object] = {
        "attempt_id": attempt_id,
        "attempt_path": str(attempt),
        "classification": "PUBLIC_REGRESSION",
        "evidence_type": "offline_scripted_adversarial_regression",
        "status": "IN_PROGRESS",
        "gate6_acceptance": "PENDING",
        "gate7_acceptance": "PENDING",
        "live_model_quality": "NOT_ESTABLISHED",
        "live_provider_calls": False,
        "gate_accepted": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "blockers": [],
    }
    write_json(attempt / "report.json", record)
    write_json(EVIDENCE_ROOT / "current_attempt.json", {"attempt_id": attempt_id, "status": "IN_PROGRESS"})

    try:
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        if matrix.get("classification") != "PUBLIC_REGRESSION" or len(matrix.get("cases", [])) < int(matrix.get("minimum_cases", 25)):
            raise ValueError("public regression matrix classification or minimum case count is invalid")
        case_ids = [case.get("id") for case in matrix["cases"]]
        if any(not isinstance(case_id, str) or not case_id for case_id in case_ids) or len(set(case_ids)) != len(case_ids):
            raise ValueError("matrix case IDs are missing or duplicated")

        record["matrix_version"] = matrix.get("schema_version")
        record["matrix_case_count"] = len(case_ids)
        record["source_binding_before"] = {
            "git": git_state(),
            "owned_source_sha256": source_hashes(),
        }
        protected_before = protected_comparison()
        tests, _output = run_tests(attempt)
        record["tests"] = tests
        protected_after = protected_comparison()
        record["protected_files"] = {
            **protected_after,
            "unchanged_during_attempt": (
                protected_before.get("files") == protected_after.get("files")
                and protected_before.get("applied_migrations") == protected_after.get("applied_migrations")
            ),
        }
        record["source_binding_after"] = {
            "git": git_state(),
            "owned_source_sha256": source_hashes(),
        }
        record["owned_source_unchanged"] = (
            record["source_binding_before"]["owned_source_sha256"]
            == record["source_binding_after"]["owned_source_sha256"]
            and record["source_binding_before"]["git"] == record["source_binding_after"]["git"]
        )
        write_json(attempt / "source-binding.json", {
            "before": record["source_binding_before"],
            "after": record["source_binding_after"],
            "owned_source_unchanged": record["owned_source_unchanged"],
        })
        write_json(attempt / "protected-files.json", record["protected_files"])

        blockers: list[str] = []
        if not tests.get("accounting_complete"):
            blockers.append("test execution or exact matrix case-ID accounting is incomplete")
        if tests.get("exit_code") or tests.get("failures") or tests.get("errors"):
            record["status"] = "FAIL"
            blockers.append("targeted public-regression suite failed")
        if tests.get("skipped"):
            blockers.append("one or more required public-regression cases were skipped")
        postgres_required = bool(matrix.get("postgres_authority_cases_required"))
        postgres_configured = bool(os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL"))
        record["postgres_authority_evidence"] = "PENDING_TEST_RESULT" if postgres_configured else (
            "BLOCKED_URL_UNAVAILABLE" if postgres_required else "NOT_REQUIRED"
        )
        if postgres_required and not postgres_configured:
            blockers.append("required isolated PostgreSQL authority proof is missing; no URL value was read into evidence")
        protected_status = record["protected_files"].get("status")
        if protected_status != "MATCH" or not record["protected_files"].get("unchanged_during_attempt"):
            blockers.append(f"protected-file comparison is {protected_status}")
        if not record["owned_source_unchanged"]:
            blockers.append("owned source or Git state changed during the candidate attempt")

        if record.get("status") != "FAIL":
            record["status"] = "BLOCKED" if blockers else "OFFLINE_REGRESSION_PASS"
        if postgres_configured and tests.get("skipped") == 0 and record["status"] != "FAIL":
            record["postgres_authority_evidence"] = "CASES_EXECUTED; inspect exact JUnit case IDs"
        record["blockers"] = blockers
    except Exception as exc:
        record["status"] = "FAIL"
        record.setdefault("blockers", []).append(f"candidate checker failed ({type(exc).__name__})")

    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(attempt / "report.json", record)
    (attempt / "report.md").write_text(markdown_report(record), encoding="utf-8")
    write_json(EVIDENCE_ROOT / "current_attempt.json", {
        "attempt_id": attempt_id,
        "status": record["status"],
        "report": str(attempt / "report.json"),
    })
    print(json.dumps({
        "attempt_id": attempt_id,
        "status": record["status"],
        "classification": record.get("classification"),
        "tests": record.get("tests"),
        "protected_files": {
            key: value for key, value in record.get("protected_files", {}).items()
            if key not in {"files", "applied_migrations"}
        },
        "postgres_authority_evidence": record.get("postgres_authority_evidence"),
        "gate6_acceptance": "PENDING",
        "gate7_acceptance": "PENDING",
        "blockers": record.get("blockers", []),
        "evidence": str(attempt),
    }, indent=2))
    return 0 if record.get("status") == "OFFLINE_REGRESSION_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
