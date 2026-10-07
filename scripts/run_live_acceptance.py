"""Isolated, aggregate-budgeted Gate 6/7 live acceptance runner.

The live path is deliberately opt-in and requires the existing local PostgreSQL
16 test service. Offline evidence and budget checks never construct a provider.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
OUTER_EVIDENCE_ROOT = ROOT.parent / "verification" / "gate67-acceptance-20261007-b3a81c57"
LIVE_EVIDENCE_SCHEMA = "shiftguard.live_acceptance.v2"
EXPECTED_MODEL = "nvidia/Nemotron-3_5-Lightning"
EXPECTED_PRESET = "bank-stress"
EXPECTED_SCENARIO = "history_block_0_50"
EXPECTED_PREDICTOR = "logistic_regression"
EXPECTED_BUDGET = 50
EXPECTED_CONDITION_KEY = "logistic_regression__history_block_0_50__b50__raw"
MAX_LIVE_CALLS = 10
MAX_LIVE_TOKENS = 50_000
DEFAULT_MAX_OUTPUT_TOKENS = 1024
_SCHEMA_RE = re.compile(r"^sg_live_acceptance_[a-z0-9_]{1,32}$")
_ID_RE = re.compile(r"^[a-f0-9]{24}$")
_REQUEST_ID_RE = re.compile(r"^req_[a-f0-9]{20}$")
_FORBIDDEN_EVIDENCE_KEYS = frozenset({
    "api_key", "authorization", "headers", "capability_token", "session_token",
    "resume_nonce", "nonce", "raw_body", "provider_body", "response_body",
})


class HarnessFailure(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _read_prompt(experiment_id: str) -> str:
    return f"Read experiment {experiment_id} condition {EXPECTED_CONDITION_KEY}"


def _compare_prompt(experiment_id: str) -> str:
    return (
        f"Compare experiment {experiment_id} calibrators predictor {EXPECTED_PREDICTOR} "
        f"scenario {EXPECTED_SCENARIO} budget {EXPECTED_BUDGET}"
    )


def _is_flagship_run_tool(entry: dict[str, Any]) -> bool:
    if entry.get("status") != "success" or not entry.get("job_id"):
        return False
    arguments = entry.get("arguments")
    if not isinstance(arguments, dict):
        return False
    if entry.get("tool_name") == "run_experiment":
        return arguments.get("preset_name") == EXPECTED_PRESET
    if entry.get("tool_name") == "run_stress_suite":
        return arguments.get("suite_name") in {"bank-stress", "flagship-stress"}
    return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_manifest(root: Path = ROOT) -> dict[str, Any]:
    """Bind executable code and locked non-Python inputs by relative path."""
    selected = {path.resolve() for path in (root / "shiftguard").rglob("*.py")}
    selected.add((root / "scripts" / "run_live_acceptance.py").resolve())
    selected.update(
        (root / relative).resolve()
        for relative in ("configs/bank-stress.yaml", "data/manifests/bank.json")
    )
    rows = []
    for path in sorted(selected, key=lambda item: item.relative_to(root.resolve()).as_posix()):
        relative = path.relative_to(root.resolve()).as_posix()
        rows.append({"path": relative, "sha256": _sha256_file(path)})
    digest = hashlib.sha256(_canonical_json(rows)).hexdigest()
    return {"sha256": digest, "files": rows}


def _snapshot_identity(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot.get("ledger_id"), snapshot.get("source_digest"),
        snapshot.get("max_calls"), snapshot.get("max_tokens"),
        snapshot.get("calls_used"), snapshot.get("tokens_committed"),
        snapshot.get("halted"), snapshot.get("halt_reason"),
        tuple(
            (row.get("attempt_no"), row.get("attempt_id"), row.get("status"),
             row.get("reserved_tokens"), row.get("total_tokens"),
             row.get("provider_request_id_sha256"))
            for row in snapshot.get("attempts", []) if isinstance(row, dict)
        ),
    )


def _acquire_state_lock(path: Path):
    """Prevent two resumed runners from recovering or continuing one ledger."""
    lock_path = path.with_name("live-state.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+b")
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        stream.close()
        raise HarnessFailure("LIVE_STATE_ALREADY_LOCKED") from None
    return stream


def _release_state_lock(stream) -> None:
    if stream is None:
        return
    try:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def _write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical_json(value) + b"\n"
    temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
    temporary.write_bytes(data)
    os.replace(temporary, path)
    digest = hashlib.sha256(data).hexdigest()
    sidecar = path.with_suffix(path.suffix + ".sha256")
    side_tmp = sidecar.with_name(sidecar.name + ".tmp-" + uuid4().hex)
    side_tmp.write_text(digest + "  " + path.name + "\n", encoding="ascii")
    os.replace(side_tmp, sidecar)
    return digest


def _assert_no_sensitive_evidence(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_EVIDENCE_KEYS:
                raise HarnessFailure("EVIDENCE_CONTAINS_SENSITIVE_FIELD")
            _assert_no_sensitive_evidence(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_sensitive_evidence(child)


def validate_evidence_document(
    document: dict[str, Any], *, current_source: dict[str, Any] | None = None,
) -> list[str]:
    """Validate redaction, source binding, ledger arithmetic, and live workflow claims."""
    if document.get("schema") != LIVE_EVIDENCE_SCHEMA:
        raise HarnessFailure("EVIDENCE_SCHEMA_INVALID")
    _assert_no_sensitive_evidence(document)
    checks: list[str] = []
    source = document.get("source_binding")
    if not isinstance(source, dict) or not isinstance(source.get("files"), list):
        raise HarnessFailure("SOURCE_BINDING_MISSING")
    source_rows = source["files"]
    if hashlib.sha256(_canonical_json(source_rows)).hexdigest() != source.get("sha256"):
        raise HarnessFailure("SOURCE_MANIFEST_HASH_INVALID")
    budget = document.get("budget")
    if not isinstance(budget, dict):
        raise HarnessFailure("BUDGET_EVIDENCE_MISSING")
    if budget and (
        source.get("sha256") != budget.get("source_digest")
        or document.get("ledger_id") != budget.get("ledger_id")
    ):
        raise HarnessFailure("SOURCE_OR_LEDGER_BINDING_MISMATCH")
    if document.get("status") == "PASS" and not budget:
        raise HarnessFailure("BUDGET_EVIDENCE_MISSING")
    checks.append("source_manifest_integrity")
    if current_source is not None:
        if source.get("sha256") != current_source.get("sha256"):
            raise HarnessFailure("SOURCE_BINDING_DIFFERS_FROM_CURRENT_TREE")
        checks.append("source_matches_current_tree")

    if not budget:
        checks.append("ledger_not_initialized")
    else:
        calls = budget.get("calls_used")
        max_calls = budget.get("max_calls")
        tokens = budget.get("tokens_committed")
        max_tokens = budget.get("max_tokens")
        attempts = budget.get("attempts")
        passing = document.get("status") == "PASS"
        if (
            type(calls) is not int or type(max_calls) is not int or not 1 <= max_calls <= MAX_LIVE_CALLS
            or type(tokens) is not int or type(max_tokens) is not int or not 1 <= max_tokens <= MAX_LIVE_TOKENS
            or not isinstance(attempts, list) or calls != len(attempts)
            or (passing and (calls > max_calls or tokens > max_tokens))
            or type(budget.get("halted")) is not bool
            or (budget.get("halted") is True) != bool(budget.get("halt_reason"))
        ):
            raise HarnessFailure("BUDGET_CEILING_OR_ACCOUNTING_INVALID")
        if passing and budget.get("halted"):
            raise HarnessFailure("BUDGET_LEDGER_HALTED")
        calculated = 0
        for expected_no, attempt in enumerate(attempts, 1):
            if not isinstance(attempt, dict) or attempt.get("attempt_no") != expected_no:
                raise HarnessFailure("BUDGET_ATTEMPT_INVALID")
            status = attempt.get("status")
            if status in {"settled", "over_bound"}:
                usage = attempt.get("total_tokens")
                prompt_tokens, completion_tokens = attempt.get("prompt_tokens"), attempt.get("completion_tokens")
                if (
                    type(usage) is not int or usage < 0
                    or type(prompt_tokens) is not int or type(completion_tokens) is not int
                    or prompt_tokens < 0 or completion_tokens < 0
                    or usage != prompt_tokens + completion_tokens
                ):
                    raise HarnessFailure("BUDGET_USAGE_INVALID")
                if status == "settled" and (
                    prompt_tokens > attempt.get("input_token_bound", -1)
                    or completion_tokens > attempt.get("output_token_bound", -1)
                    or usage > attempt.get("reserved_tokens", -1)
                ):
                    raise HarnessFailure("BUDGET_SETTLED_OVER_BOUND")
                calculated += usage
            elif status in {"closed_unknown", "reserved"}:
                reserved = attempt.get("reserved_tokens")
                if type(reserved) is not int or reserved < 1:
                    raise HarnessFailure("BUDGET_RESERVATION_INVALID")
                calculated += reserved
            else:
                raise HarnessFailure("BUDGET_ATTEMPT_STATUS_INVALID")
        if calculated != tokens:
            raise HarnessFailure("BUDGET_TOTAL_DOES_NOT_RECONCILE")
        if passing and any(item.get("status") != "settled" for item in attempts):
            raise HarnessFailure("BUDGET_HAS_UNRESOLVED_ATTEMPT")
        checks.append("aggregate_budget")
        if calls > max_calls or tokens > max_tokens:
            checks.append("budget_ceiling_overrun_recorded")

    runtime = document.get("runtime")
    if not isinstance(runtime, dict):
        raise HarnessFailure("LIVE_RUNTIME_BINDING_MISSING")
    if document.get("status") == "PASS":
        if runtime.get("provider") != "nebius" or runtime.get("model") != EXPECTED_MODEL:
            raise HarnessFailure("LIVE_PROVIDER_BINDING_INVALID")
        if runtime.get("database_major") != 16 or runtime.get("loopback_only") is not True:
            raise HarnessFailure("ISOLATED_RUNTIME_BINDING_INVALID")
        checks.append("isolated_runtime_binding")

    if document.get("status") == "PASS":
        requests = document.get("requests")
        publication = document.get("publication")
        if not isinstance(requests, dict) or not isinstance(publication, dict):
            raise HarnessFailure("WORKFLOW_EVIDENCE_MISSING")
        run = requests.get("run")
        read = requests.get("read")
        compare = requests.get("compare")
        if not all(isinstance(item, dict) for item in (run, read, compare)):
            raise HarnessFailure("WORKFLOW_STAGE_MISSING")
        startup = document.get("startup_budget")
        if (
            not isinstance(startup, dict)
            or _snapshot_identity(startup.get("before", {})) != _snapshot_identity(startup.get("after", {}))
            or startup.get("provider_calls_added") != 0
        ):
            raise HarnessFailure("STARTUP_BUDGET_DELTA_INVALID")
        checks.append("startup_budget_unchanged")
        previous_end = 0
        for stage_name, stage in (("run", run), ("read", read), ("compare", compare)):
            binding = stage.get("transcript_binding")
            trace = stage.get("tool_trace")
            if not isinstance(binding, dict) or not isinstance(trace, list):
                raise HarnessFailure("PERSISTED_TRANSCRIPT_BINDING_MISSING")
            trace_ids = [item.get("tool_call_id") for item in trace if isinstance(item, dict)]
            call_ids = binding.get("tool_call_ids")
            if (
                stage.get("status") != "COMPLETED"
                or not isinstance(stage.get("request_id"), str) or not _REQUEST_ID_RE.fullmatch(stage["request_id"])
                or not isinstance(document.get("session_id"), str) or not document["session_id"]
                or stage.get("session_id") != document.get("session_id")
                or not isinstance(stage.get("intent_key_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", stage["intent_key_sha256"])
                or binding.get("request_id") != stage.get("request_id")
                or binding.get("session_id") != stage.get("session_id")
                or binding.get("database_status") != "COMPLETED"
                or not isinstance(binding.get("message_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", binding["message_sha256"])
                or not isinstance(call_ids, list) or not call_ids or call_ids != trace_ids
                or binding.get("assistant_tool_call_ids") != call_ids
                or binding.get("tool_response_call_ids") != call_ids
                or binding.get("api_trace_sha256") != hashlib.sha256(_canonical_json(trace)).hexdigest()
                or binding.get("renderer_name") != "ResultRenderer.render_from_tool_results"
                or binding.get("renderer_claims_sha256") != hashlib.sha256(_canonical_json(stage.get("claims", []))).hexdigest()
                or not isinstance(binding.get("executions"), list)
                or [item.get("tool_call_id") for item in binding["executions"] if isinstance(item, dict)] != call_ids
                or any(
                    not isinstance(item, dict)
                    or not isinstance(item.get("execution_id"), str)
                    or not all(
                        isinstance(item.get(name), str) and re.fullmatch(r"[a-f0-9]{64}", item[name])
                        for name in ("arguments_sha256", "result_sha256")
                    )
                    for item in binding["executions"]
                )
            ):
                raise HarnessFailure("PERSISTED_TRANSCRIPT_BINDING_INVALID")
            before_stage, after_stage = stage.get("provider_calls_before_stage"), stage.get("provider_calls_after_stage")
            turns = stage.get("agent_turn_count")
            if (
                type(before_stage) is not int or type(after_stage) is not int
                or not previous_end <= before_stage < after_stage <= calls
                or type(turns) is not int or after_stage - before_stage != turns
                or type(binding.get("database_turn_count")) is not int
                or binding.get("database_turn_count") != turns
                or type(stage.get("agent_call_count")) is not int
                or stage["agent_call_count"] != len(trace)
                or binding.get("database_call_count") != stage["agent_call_count"]
                or type(binding.get("database_call_count")) is not int
                or binding.get("provider_attempt_ids") != [a.get("attempt_id") for a in attempts[before_stage:after_stage]]
                or binding.get("provider_input_sha256") != [a.get("input_sha256") for a in attempts[before_stage:after_stage]]
                or not all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)
                           for value in binding.get("provider_input_sha256", []))
            ):
                raise HarnessFailure("STAGE_PROVIDER_CALL_DELTA_INVALID")
            previous_end = after_stage
            for execution, entry in zip(binding["executions"], trace, strict=True):
                arguments = entry.get("arguments")
                if (
                    not isinstance(arguments, dict)
                    or _safe_trace_arguments(arguments) != arguments
                    or any(isinstance(v, str) and "[bounded]" in v for v in arguments.values())
                    or execution.get("arguments_sha256") != hashlib.sha256(_canonical_json(arguments)).hexdigest()
                    or execution.get("ordinal") != entry.get("ordinal")
                    or execution.get("tool_name") != entry.get("tool_name")
                    or execution.get("status") != entry.get("status")
                    or execution.get("job_id") != entry.get("job_id")
                    or execution.get("public_result_sha256") != hashlib.sha256(_canonical_json(entry.get("result"))).hexdigest()
                ):
                    raise HarnessFailure("PUBLIC_TRACE_EXECUTION_BINDING_INVALID")
            from shiftguard.agent.rendering import ResultRenderer

            expected_claims = ResultRenderer.render_from_tool_results(
                stage.get("prompt", ""), trace, stage.get("evidence_refs", [])
            )["claims"]
            if _canonical_json(stage.get("claims", [])) != _canonical_json(expected_claims):
                raise HarnessFailure("FINAL_CLAIMS_DIFFER_FROM_RESULT_RENDERER")
            replay_before, replay_after = stage.get("provider_calls_before_replay"), stage.get("provider_calls_after_replay")
            if (
                stage.get("idempotent_replay_zero_added_calls") is not True
                or replay_before != replay_after
                or stage.get("replay_request_id") != stage.get("request_id")
                or type(replay_before) is not int or type(replay_after) is not int
                or not after_stage <= replay_before <= calls <= max_calls
            ):
                raise HarnessFailure("IDEMPOTENT_REPLAY_ADDED_CALLS")
            if stage_name != "run" and stage.get("evidence_refs") is None:
                raise HarnessFailure("PUBLISHED_EVIDENCE_REFERENCE_MISSING")
        if document.get("provider_accounting") != _provider_accounting(document):
            raise HarnessFailure("PROVIDER_STAGE_LEDGER_ACCOUNTING_INVALID")
        checks.append("stage_dispatches_reconcile_with_ledger")
        run_events = run.get("resume_events")
        durable_waits = document.get("durable_waits")
        if (
            run.get("durable_wait_observed") is not True
            or not run.get("job_id")
            or not isinstance(durable_waits, list)
            or not any(
                isinstance(item, dict)
                and item.get("stage") == "run"
                and item.get("request_id") == run.get("request_id")
                and item.get("job_id") == run.get("job_id")
                and item.get("status") == "WAITING_FOR_JOB"
                for item in durable_waits
            )
            or not isinstance(run_events, list)
            or not any(
                isinstance(item, dict)
                and item.get("request_id") == run.get("request_id")
                and item.get("job_id") == run.get("job_id")
                and item.get("job_status") == "completed"
                and item.get("resume_status_code") in {200, 202}
                for item in run_events
            )
        ):
            raise HarnessFailure("DURABLE_WAIT_RESUME_NOT_PROVEN")
        run_trace = run.get("tool_trace")
        run_tools = [
            item for item in run_trace
            if isinstance(item, dict) and item.get("tool_name") in {"run_experiment", "run_stress_suite"}
        ]
        if (
            run.get("preset") != EXPECTED_PRESET or run.get("status") != "COMPLETED"
            or run.get("prompt") != "Run bank-stress"
            or len(run_tools) != 1 or not _is_flagship_run_tool(run_tools[0])
            or run_tools[0].get("job_id") != run.get("job_id")
            or publication.get("job_id") != run.get("job_id")
            or publication.get("job_status") != "completed"
        ):
            raise HarnessFailure("FLAGSHIP_RUN_NOT_COMPLETED")
        experiment_id = publication.get("experiment_id")
        if (
            not isinstance(experiment_id, str) or not _ID_RE.fullmatch(experiment_id)
            or publication.get("evaluation_tier") != "development"
            or publication.get("master_seed") != 31001
            or publication.get("condition_count") != 400
        ):
            raise HarnessFailure("PUBLISHED_DEVELOPMENT_RUN_INVALID")
        checks.append("published_development_run")

        read_trace = read.get("tool_trace")
        read_calls = [item for item in read_trace if item.get("tool_name") == "read_experiment_results"]
        if len(read_calls) != 1:
            raise HarnessFailure("MODEL_BOUNDED_READ_TOOL_MISSING")
        read_call = read_calls[0]
        read_args = read_call.get("arguments", {})
        read_data = (read_call.get("result") or {}).get("data") or {}
        if (
            read_call.get("status") != "success"
            or read.get("prompt") != _read_prompt(experiment_id)
            or read_args.get("experiment_id") != experiment_id
            or read_args.get("condition_key") != EXPECTED_CONDITION_KEY
            or read_data.get("experiment_id") != experiment_id
            or read_data.get("condition_key") != EXPECTED_CONDITION_KEY
            or not _ID_RE.fullmatch(str(read_data.get("condition_id", "")))
            or read_data.get("scenario") != EXPECTED_SCENARIO
            or read_data.get("predictor") != EXPECTED_PREDICTOR
            or read_data.get("budget") != EXPECTED_BUDGET
            or read_data.get("status") != "scored"
            or not _finite_metric_pair(read_data.get("metrics"))
            or experiment_id not in read.get("evidence_refs", [])
        ):
            raise HarnessFailure("MODEL_BOUNDED_READ_INVALID")
        condition_bindings = publication.get("condition_bindings")
        read_binding = condition_bindings.get("read") if isinstance(condition_bindings, dict) else None
        if (
            not isinstance(read_binding, dict)
            or read_binding.get("condition_key") != EXPECTED_CONDITION_KEY
            or read_binding.get("condition_id") != read_data.get("condition_id")
            or read_binding.get("status") != "scored"
            or read_binding.get("metrics") != read_data.get("metrics")
        ):
            raise HarnessFailure("READ_CONDITION_BINDING_NOT_PERSISTED")
        checks.append("model_bounded_published_read")

        compare_trace = compare.get("tool_trace")
        comparisons = [item for item in compare_trace if item.get("tool_name") == "compare_calibrators"]
        if len(comparisons) != 1:
            raise HarnessFailure("MODEL_COMPARISON_TOOL_MISSING")
        compare_call = comparisons[0]
        compare_args = compare_call.get("arguments", {})
        comparison_data = (compare_call.get("result") or {}).get("data") or {}
        methods = comparison_data.get("calibrator_comparisons")
        from shiftguard.agent.policy import APPROVED_CALIBRATORS

        qualified = []
        raw_comparison = methods.get("raw") if isinstance(methods, dict) else None
        raw_brier = raw_comparison.get("brier_score") if isinstance(raw_comparison, dict) else None
        if isinstance(methods, dict):
            qualified = [
                (method, item) for method, item in methods.items()
                if isinstance(item, dict)
                and item.get("comparison_qualified") is True
                and item.get("status") == "scored"
                and _ID_RE.fullmatch(str(item.get("condition_id", "")))
                and _finite_value(item.get("brier_score"))
                and _finite_value(item.get("log_loss"))
            ]
        if (
            compare_call.get("status") != "success"
            or compare.get("prompt") != _compare_prompt(experiment_id)
            or compare_args.get("experiment_id") != experiment_id
            or compare_args.get("scenario") != EXPECTED_SCENARIO
            or compare_args.get("predictor") != EXPECTED_PREDICTOR
            or compare_args.get("budget") != EXPECTED_BUDGET
            or comparison_data.get("experiment_id") != experiment_id
            or comparison_data.get("scenario") != EXPECTED_SCENARIO
            or comparison_data.get("predictor") != EXPECTED_PREDICTOR
            or comparison_data.get("budget") != EXPECTED_BUDGET
            or experiment_id not in compare.get("evidence_refs", [])
            or not _finite_value(raw_brier)
            or set(methods or {}) != set(APPROVED_CALIBRATORS)
            or len(qualified) != len(APPROVED_CALIBRATORS)
        ):
            raise HarnessFailure("MODEL_COMPARISON_NOT_QUALIFIED")
        context_fields = ("predictor_id", "dataset_id", "evaluation_rows_id", "source_map_id")
        if any(
            not isinstance(raw_comparison.get(field), str) or not raw_comparison.get(field)
            for field in context_fields
        ) or any(
            any(item.get(field) != raw_comparison.get(field) for field in context_fields)
            or item.get("scenario") != EXPECTED_SCENARIO
            or item.get("budget") != EXPECTED_BUDGET
            for method, item in qualified
        ):
            raise HarnessFailure("MODEL_COMPARISON_CONTEXT_MISMATCH")
        compare_claims = [
            claim for claim in compare.get("claims", [])
            if isinstance(claim, dict) and claim.get("claim_type") == "calibrator_comparison"
        ]
        claim_by_method = {claim.get("method"): claim for claim in compare_claims}
        if any(
            method not in claim_by_method
            or claim_by_method[method].get("condition_id") != item.get("condition_id")
            or claim_by_method[method].get("experiment_id") != experiment_id
            or claim_by_method[method].get("value") != item.get("brier_score")
            or claim_by_method[method].get("baseline_value") != raw_brier
            or claim_by_method[method].get("delta") != item.get("brier_score") - raw_brier
            or claim_by_method[method].get("metric_name") != "brier_score"
            or claim_by_method[method].get("comparison_qualified") is not True
            or claim_by_method[method].get("direction") != (
                "improved" if item.get("brier_score") - raw_brier < -1e-5
                else "degraded" if item.get("brier_score") - raw_brier > 1e-5
                else "unchanged"
            )
            for method, item in qualified
        ) or set(claim_by_method) != set(APPROVED_CALIBRATORS):
            raise HarnessFailure("PYTHON_RENDERED_CLAIMS_NOT_BOUND_TO_TOOL_OUTPUT")
        compared_bindings = condition_bindings.get("compare") if isinstance(condition_bindings, dict) else None
        if not isinstance(compared_bindings, dict) or set(compared_bindings) != set(APPROVED_CALIBRATORS) or any(
            not isinstance(compared_bindings.get(method), dict)
            or compared_bindings[method].get("condition_id") != item.get("condition_id")
            or compared_bindings[method].get("status") != item.get("status")
            or compared_bindings[method].get("condition_key") != f"{EXPECTED_PREDICTOR}__{EXPECTED_SCENARIO}__b{EXPECTED_BUDGET}__{method}"
            or compared_bindings[method].get("metrics") != {
                metric: item.get(metric) for metric in ("brier_score", "log_loss", "ece")
                if item.get(metric) is not None
            }
            for method, item in qualified
        ):
            raise HarnessFailure("COMPARISON_CONDITION_BINDING_NOT_PERSISTED")
        read_claims = [
            claim for claim in read.get("claims", [])
            if isinstance(claim, dict) and claim.get("claim_type") == "metric_observation"
        ]
        expected_read_claims = {
            metric: value for metric, value in read_data["metrics"].items()
            if _finite_value(value)
        }
        if any(
            claim.get("experiment_id") != experiment_id
            or claim.get("condition_id") != read_data.get("condition_id")
            or claim.get("condition_key") != EXPECTED_CONDITION_KEY
            or claim.get("value") != expected_read_claims.get(claim.get("metric_name"))
            for claim in read_claims
        ) or {claim.get("metric_name") for claim in read_claims} != set(expected_read_claims) or not {"brier_score", "log_loss"}.issubset(expected_read_claims):
            raise HarnessFailure("PYTHON_RENDERED_READ_CLAIMS_NOT_BOUND_TO_TOOL_OUTPUT")
        checks.extend(("model_qualified_comparison_and_claim_binding", "published_condition_ids_and_metrics_bound"))
        checks.append("idempotent_replay_zero_added_calls")
    return checks


def _finite_value(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _provider_accounting(document: dict[str, Any]) -> dict[str, Any]:
    """Describe the stage intervals and every remaining historical ledger charge."""
    attempts = document["budget"]["attempts"]
    stages = {
        name: list(range(item["provider_calls_before_stage"] + 1, item["provider_calls_after_stage"] + 1))
        for name, item in document["requests"].items() if name in {"run", "read", "compare"}
    }
    assigned = {number for numbers in stages.values() for number in numbers}
    historical = [row for row in attempts if row["attempt_no"] not in assigned]
    return {
        "stage_attempt_nos": stages,
        "historical_attempt_nos": [row["attempt_no"] for row in historical],
        "historical_calls": len(historical),
        "historical_tokens": sum(row["total_tokens"] if row["status"] in {"settled", "over_bound"}
                                 else row["reserved_tokens"] for row in historical),
    }


def _pass_candidate(evidence: dict[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(evidence)
    candidate["provider_accounting"] = _provider_accounting(candidate)
    candidate["status"] = "PASS"
    candidate["checks"] = validate_evidence_document(candidate, current_source=source_manifest())
    # Validate the complete object passed to the atomic evidence writer.
    candidate["checks"] = validate_evidence_document(candidate, current_source=source_manifest())
    return candidate


def _finite_metric_pair(metrics: Any) -> bool:
    return isinstance(metrics, dict) and all(
        _finite_value(metrics.get(name)) for name in ("brier_score", "log_loss")
    )


def _inspect_evidence(path: Path, *, require_current_source: bool) -> dict[str, Any]:
    raw = path.read_bytes()
    sidecar = path.with_suffix(path.suffix + ".sha256")
    expected_line = sidecar.read_text(encoding="ascii").strip().split()
    actual_digest = hashlib.sha256(raw).hexdigest()
    if not expected_line or expected_line[0] != actual_digest:
        raise HarnessFailure("EVIDENCE_FILE_HASH_MISMATCH")
    document = json.loads(raw)
    current = source_manifest() if require_current_source else None
    checks = validate_evidence_document(document, current_source=current)
    return {
        "status": document.get("status"),
        "evidence_sha256": actual_digest,
        "source_sha256": document.get("source_binding", {}).get("sha256"),
        "checks": checks,
        "calls_used": document.get("budget", {}).get("calls_used"),
        "max_calls": document.get("budget", {}).get("max_calls"),
        "tokens_committed": document.get("budget", {}).get("tokens_committed"),
        "max_tokens": document.get("budget", {}).get("max_tokens"),
    }


def _offline_check() -> dict[str, Any]:
    """Exercise atomic reservation/settlement in a temporary SQLite ledger only."""
    from sqlalchemy import create_engine
    from shiftguard.agent.budget import AttemptBudget, BudgetLimitExceeded

    with tempfile.TemporaryDirectory(prefix="shiftguard-offline-budget-") as temporary:
        engine = create_engine(f"sqlite:///{Path(temporary, 'ledger.sqlite').as_posix()}")
        budget = AttemptBudget(
            engine, ledger_id="offline-check", source_digest="b" * 64,
            max_calls=1, max_tokens=10_000,
        )
        reservation = budget.reserve(
            model=EXPECTED_MODEL,
            messages=[{"role": "user", "content": "offline validation"}],
            tools=[], max_output_tokens=32,
        )
        budget.settle(
            reservation,
            {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "offline-request-id",
        )
        try:
            budget.reserve(
                model=EXPECTED_MODEL,
                messages=[{"role": "user", "content": "must not reserve"}],
                tools=[], max_output_tokens=32,
            )
        except BudgetLimitExceeded as exc:
            if exc.limit != "calls":
                raise HarnessFailure("OFFLINE_BUDGET_CHECK_FAILED") from None
        else:
            raise HarnessFailure("OFFLINE_BUDGET_CHECK_FAILED")
        result = budget.snapshot()
        if result["calls_used"] != 1 or result["tokens_committed"] != 8:
            raise HarnessFailure("OFFLINE_BUDGET_CHECK_FAILED")
        engine.dispose()
    return {"offline_budget_guard": "PASS", "provider_calls": 0}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--live", action="store_true", help="run the real isolated HTTP/provider workflow")
    modes.add_argument("--offline-check", action="store_true", help="validate the SQLite budget guard without a provider")
    modes.add_argument("--inspect-evidence", type=Path, metavar="PATH", help="inspect evidence without a provider")
    modes.add_argument("--validate-evidence", type=Path, metavar="PATH", help="validate evidence and current-source binding offline")
    parser.add_argument("--max-calls", type=int, help="required live request ceiling, maximum 10")
    parser.add_argument("--max-tokens", type=int, default=MAX_LIVE_TOKENS, help="aggregate live token ceiling (default: 50000; maximum: 50000)")
    parser.add_argument("--schema", help="existing sg_live_acceptance_* schema for a resume")
    parser.add_argument("--ledger-id", help="existing attempt ledger ID for a resume")
    parser.add_argument("--resume-state", type=Path, help="resume a durable workflow from its redacted state file")
    parser.add_argument("--evidence-dir", type=Path, help="new attempt output under the parent verification directory")
    parser.add_argument("--run-timeout-seconds", type=int, default=10_800)
    return parser


def _validate_live_args(args: argparse.Namespace) -> None:
    if args.max_calls is None or type(args.max_calls) is not int or not 1 <= args.max_calls <= MAX_LIVE_CALLS:
        raise HarnessFailure("LIVE_MAX_CALLS_REQUIRED_AND_MUST_BE_AT_MOST_10")
    if type(args.max_tokens) is not int or not 1 <= args.max_tokens <= MAX_LIVE_TOKENS:
        raise HarnessFailure("LIVE_MAX_TOKENS_MUST_BE_1_TO_50000")
    if args.run_timeout_seconds < 60 or args.run_timeout_seconds > 86_400:
        raise HarnessFailure("RUN_TIMEOUT_OUT_OF_RANGE")
    if args.resume_state is None and (args.schema is not None or args.ledger_id is not None):
        raise HarnessFailure("SCHEMA_AND_LEDGER_ID_REQUIRE_RESUME_STATE")
    if args.resume_state is not None and args.evidence_dir is not None:
        raise HarnessFailure("RESUME_USES_STATE_DIRECTORY")


def _load_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HarnessFailure("RESUME_STATE_UNREADABLE") from None
    if (
        not isinstance(state, dict)
        or state.get("version") != 2
        or not isinstance(state.get("schema"), str)
        or not _SCHEMA_RE.fullmatch(state["schema"])
        or not isinstance(state.get("ledger_id"), str)
        or not isinstance(state.get("source_sha256"), str)
        or not isinstance(state.get("session_id"), str)
        or not isinstance(state.get("requests"), dict)
        or not isinstance(state.get("stage_evidence", {}), dict)
        or not isinstance(state.get("durable_waits", []), list)
    ):
        raise HarnessFailure("RESUME_STATE_INVALID")
    _assert_no_sensitive_evidence(state)
    return state


def _evidence_directory(args: argparse.Namespace, ledger_id: str | None = None) -> Path:
    if args.resume_state is not None:
        directory = args.resume_state.resolve().parent
    elif args.evidence_dir is not None:
        directory = args.evidence_dir.resolve()
    else:
        directory = OUTER_EVIDENCE_ROOT / "live-attempts" / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{ledger_id or uuid4().hex[:8]}"
    try:
        directory.relative_to(OUTER_EVIDENCE_ROOT.resolve())
    except ValueError:
        raise HarnessFailure("EVIDENCE_DIRECTORY_OUTSIDE_PARENT_VERIFICATION_ROOT") from None
    return directory


def _test_database_url(raw: str):
    from sqlalchemy.engine import make_url

    try:
        url = make_url(raw)
    except Exception:
        raise HarnessFailure("TEST_DATABASE_URL_INVALID") from None
    if (
        url.drivername not in {"postgresql", "postgresql+psycopg"}
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.port != 15432
        or url.database != "shiftguard_gate3"
        or url.username is None
    ):
        raise HarnessFailure("TEST_DATABASE_TARGET_NOT_ALLOWED")
    return url.set(drivername="postgresql+psycopg", query={k: v for k, v in url.query.items() if k != "options"})


def _prepare_schema(admin_url, schema: str, *, create: bool) -> tuple[str, int]:
    from sqlalchemy import create_engine, text

    engine = create_engine(admin_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            server_version = int(connection.execute(text("SELECT current_setting('server_version_num')::integer")).scalar_one())
            database_name = connection.execute(text("SELECT current_database()")).scalar_one()
            if database_name != "shiftguard_gate3" or server_version // 10_000 != 16:
                raise HarnessFailure("TEST_POSTGRESQL16_NOT_VERIFIED")
            exists = connection.execute(
                text("SELECT 1 FROM pg_namespace WHERE nspname = :schema"), {"schema": schema}
            ).first() is not None
            if create:
                if exists:
                    raise HarnessFailure("GENERATED_SCHEMA_ALREADY_EXISTS")
                connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            elif not exists:
                raise HarnessFailure("RESUME_SCHEMA_NOT_FOUND")
        return str(server_version // 10_000), server_version
    finally:
        engine.dispose()


def _scoped_url(admin_url, schema: str):
    query = dict(admin_url.query)
    query["options"] = f"-csearch_path={schema}"
    return admin_url.set(query=query)


def _server_thread(app):
    import uvicorn

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = int(sock.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", access_log=False,
        lifespan="on", timeout_graceful_shutdown=10,
    ))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True, name="shiftguard-live-acceptance")
    thread.start()
    deadline = time.monotonic() + 60
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=15)
        raise HarnessFailure("ISOLATED_SERVER_STARTUP_FAILED")
    return server, thread, port


def _json_response(response, accepted: tuple[int, ...]) -> dict[str, Any]:
    if response.status_code not in accepted:
        raise HarnessFailure("APPLICATION_HTTP_STATUS_UNEXPECTED")
    try:
        value = response.json()
    except (ValueError, json.JSONDecodeError):
        raise HarnessFailure("APPLICATION_HTTP_JSON_INVALID") from None
    if not isinstance(value, dict):
        raise HarnessFailure("APPLICATION_HTTP_OBJECT_INVALID")
    return value


def _api_get(client, path: str, headers: dict[str, str], accepted=(200,)) -> dict[str, Any]:
    return _json_response(client.get(path, headers=headers), accepted)


def _get_capability(engine, session_id: str) -> str:
    from sqlalchemy import text

    with engine.connect() as connection:
        token = connection.execute(
            text("SELECT capability_token FROM agent_sessions WHERE id = :id"),
            {"id": session_id},
        ).scalar_one_or_none()
    if not isinstance(token, str) or not token:
        raise HarnessFailure("SERVER_ISSUED_CAPABILITY_NOT_FOUND")
    return token


def _save_state(path: Path, state: dict[str, Any]) -> None:
    _assert_no_sensitive_evidence(state)
    _write_json(path, state)


def _request_key(state: dict[str, Any], stage: str, prompt: str) -> dict[str, Any]:
    requests = state["requests"]
    current = requests.get(stage)
    if current is None:
        current = {
            "prompt": prompt,
            "intent_key": f"live-{stage}-{uuid4().hex}",
            "request_id": None,
            "status": "NOT_SUBMITTED",
        }
        requests[stage] = current
    elif current.get("prompt") != prompt:
        raise HarnessFailure("RESUME_PROMPT_BINDING_MISMATCH")
    return current


def _public_tool_result(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise HarnessFailure("API_TOOL_RESULT_INVALID")
    # Projection retains absent/null/empty data and the actual compact job outcome.
    result = {key: copy.deepcopy(value[key]) for key in (
        "status", "data", "job_id", "experiment_id", "message"
    ) if key in value}
    if "error" in value:
        result["error_code"] = _error_code(value["error"])
    return result


def _public_tool_trace(response: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for entry in response.get("tool_trace", []):
        if not isinstance(entry, dict):
            continue
        item = {
            "ordinal": entry.get("ordinal"),
            "tool_name": entry.get("tool_name"),
            "tool_call_id": entry.get("tool_call_id"),
            "arguments": entry.get("arguments") if isinstance(entry.get("arguments"), dict) else {},
            "status": entry.get("status"),
            "job_id": entry.get("job_id"),
            "result": _public_tool_result(entry.get("result")),
        }
        _assert_no_sensitive_evidence(item)
        result.append(item)
    return result


def _error_code(error: Any) -> str | None:
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"][:48]
    if isinstance(error, str):
        candidate = error.split(":", 1)[0]
        return candidate[:48] if re.fullmatch(r"[A-Z0-9_]{1,48}", candidate) else "APPLICATION_ERROR"
    return None


def _public_claims(response: dict[str, Any]) -> list[dict[str, Any]]:
    final = response.get("final_response")
    claims = final.get("claims", []) if isinstance(final, dict) else []
    return [claim for claim in claims if isinstance(claim, dict)]


def _persisted_stage_binding(
    engine, response: dict[str, Any], *, request_id: str, prompt: str,
    session_id: str, public_trace: list[dict[str, Any]],
    budget_snapshot: dict[str, Any] | None = None, calls_before_stage: int | None = None,
) -> dict[str, Any]:
    """Cross-check API projections against the persisted request transcript and rows."""
    from shiftguard.agent.rendering import ResultRenderer
    from shiftguard.agent.store import AgentStore

    store = AgentStore(engine)
    request = store.get_request(request_id)
    executions = store.list_tool_executions(request_id)
    if (
        request is None or request.status not in {"COMPLETED", "FAILED", "CANCELLED"}
        or request.status != response.get("status")
        or request.session_id != session_id or request.prompt != prompt
        or response.get("request_id") != request_id
        or response.get("session_id") != session_id
        or response.get("prompt") != prompt
        or response.get("turn_count") != request.turn_count
        or response.get("call_count") != request.call_count
        or len(executions) != len(public_trace)
    ):
        raise HarnessFailure("PERSISTED_REQUEST_IDENTITY_MISMATCH")

    assistant_calls: dict[str, tuple[str, dict[str, Any]]] = {}
    tool_responses: dict[str, tuple[str, dict[str, Any]]] = {}
    for message in request.messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "assistant":
            for call in message.get("tool_calls", []):
                if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                    continue
                function = call["function"]
                try:
                    arguments = json.loads(function.get("arguments", "{}"))
                except (TypeError, json.JSONDecodeError):
                    raise HarnessFailure("PERSISTED_ASSISTANT_TOOL_CALL_INVALID") from None
                call_id, name = call.get("id"), function.get("name")
                if not isinstance(call_id, str) or not isinstance(name, str) or not isinstance(arguments, dict) or call_id in assistant_calls:
                    raise HarnessFailure("PERSISTED_ASSISTANT_TOOL_CALL_INVALID")
                assistant_calls[call_id] = (name, arguments)
        elif message.get("role") == "tool":
            call_id, name = message.get("tool_call_id"), message.get("name")
            try:
                result = json.loads(message.get("content", "{}"))
            except (TypeError, json.JSONDecodeError):
                raise HarnessFailure("PERSISTED_TOOL_RESPONSE_INVALID") from None
            if not isinstance(call_id, str) or not isinstance(name, str) or not isinstance(result, dict) or call_id in tool_responses:
                raise HarnessFailure("PERSISTED_TOOL_RESPONSE_INVALID")
            tool_responses[call_id] = (name, result)

    rows = []
    call_ids = []
    for execution, api_item in zip(executions, public_trace, strict=True):
        call_id = execution.tool_call_id
        assistant = assistant_calls.get(call_id)
        tool_reply = tool_responses.get(call_id)
        if (
            assistant is None or tool_reply is None
            or assistant != (execution.tool_name, execution.arguments)
            or tool_reply != (execution.tool_name, execution.result)
            or api_item.get("ordinal") != execution.ordinal
            or api_item.get("tool_name") != execution.tool_name
            or api_item.get("tool_call_id") != call_id
            or api_item.get("arguments") != _safe_trace_arguments(execution.arguments)
            or api_item.get("status") != execution.status
            or api_item.get("job_id") != execution.job_id
            or api_item.get("result") != _public_tool_result(execution.result)
        ):
            raise HarnessFailure("API_TRACE_DIFFERS_FROM_PERSISTED_TRANSCRIPT")
        call_ids.append(call_id)
        rows.append({
            "execution_id": execution.id,
            "ordinal": execution.ordinal,
            "tool_name": execution.tool_name,
            "tool_call_id": call_id,
            "arguments_sha256": hashlib.sha256(_canonical_json(execution.arguments)).hexdigest(),
            "result_sha256": hashlib.sha256(_canonical_json(execution.result)).hexdigest(),
            "public_result_sha256": hashlib.sha256(_canonical_json(api_item.get("result"))).hexdigest(),
            "status": execution.status,
            "job_id": execution.job_id,
        })
    if set(assistant_calls) != set(call_ids) or set(tool_responses) != set(call_ids):
        raise HarnessFailure("PERSISTED_TRANSCRIPT_TOOL_IDS_MISMATCH")
    renderer_trace = [
        {
            "ordinal": execution.ordinal,
            "tool_name": execution.tool_name,
            "tool_call_id": execution.tool_call_id,
            "arguments": execution.arguments,
            "status": execution.status,
            "result": execution.result,
            "error": None,
            "job_id": execution.job_id,
        }
        for execution in executions
    ]
    renderer_claims = ResultRenderer.render_from_tool_results(
        prompt, renderer_trace, request.evidence_refs
    )["claims"]
    actual_claims = _public_claims(response)
    if request.status == "COMPLETED" and _canonical_json(actual_claims) != _canonical_json(renderer_claims):
        raise HarnessFailure("FINAL_CLAIMS_DIFFER_FROM_RESULT_RENDERER")
    binding = {
        "request_id": request.id,
        "session_id": request.session_id,
        "database_status": request.status,
        "database_turn_count": request.turn_count,
        "database_call_count": request.call_count,
        "message_sha256": hashlib.sha256(_canonical_json(request.messages)).hexdigest(),
        "assistant_tool_call_ids": call_ids,
        "tool_response_call_ids": call_ids,
        "tool_call_ids": call_ids,
        "api_trace_sha256": hashlib.sha256(_canonical_json(public_trace)).hexdigest(),
        "renderer_name": "ResultRenderer.render_from_tool_results",
        "renderer_claims_sha256": hashlib.sha256(_canonical_json(actual_claims)).hexdigest(),
        "executions": rows,
    }
    if request.status == "COMPLETED" and budget_snapshot is not None and "attempts" in budget_snapshot:
        from shiftguard.agent.budget import input_token_upper_bound
        from shiftguard.agent.provider import _validate_messages, _validate_tools
        from shiftguard.agent.registry import ToolRegistry

        if type(calls_before_stage) is not int or calls_before_stage < 0:
            raise HarnessFailure("STAGE_PROVIDER_CALL_DELTA_INVALID")
        attempts = budget_snapshot["attempts"][calls_before_stage:calls_before_stage + request.turn_count]
        prefixes = [request.messages[:i] for i, message in enumerate(request.messages)
                    if message.get("role") == "assistant"]
        if len(prefixes) != request.turn_count or len(attempts) != request.turn_count:
            raise HarnessFailure("PERSISTED_PROVIDER_DISPATCH_COUNT_MISMATCH")
        tools = _validate_tools(ToolRegistry().get_openai_tool_definitions())
        inputs = [input_token_upper_bound(
            model=EXPECTED_MODEL, messages=_validate_messages(messages), tools=tools,
            max_output_tokens=attempt["output_token_bound"],
        )[1] for messages, attempt in zip(prefixes, attempts, strict=True)]
        if inputs != [attempt["input_sha256"] for attempt in attempts]:
            raise HarnessFailure("PERSISTED_PROVIDER_DISPATCH_LEDGER_MISMATCH")
        binding["provider_attempt_ids"] = [attempt["attempt_id"] for attempt in attempts]
        binding["provider_input_sha256"] = inputs
    return binding


def _safe_trace_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    from shiftguard.agent.controller import _sanitize_trace_arguments

    return _sanitize_trace_arguments(arguments)


def _poll_request(
    client,
    *,
    request_id: str,
    headers: dict[str, str],
    timeout_seconds: int,
    evidence: dict[str, Any],
    stage: str,
    state: dict[str, Any],
    state_path: Path,
    budget,
    engine,
    prompt: str,
    session_id: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    request_path = f"/api/v1/agent/requests/{request_id}"
    evidence.setdefault("durable_waits", [])
    item = evidence["requests"].setdefault(stage, {})
    durable_wait = item.get("durable_wait_observed") is True
    job_id: str | None = item.get("job_id")
    while time.monotonic() < deadline:
        current = _api_get(client, request_path, headers)
        status = current.get("status")
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            item["status"] = status
            item["request_id"] = request_id
            trace = _public_tool_trace(current)
            item["tool_trace"] = trace
            item["claims"] = _public_claims(current)
            item["evidence_refs"] = [ref for ref in current.get("evidence_refs", []) if isinstance(ref, str)]
            item["durable_wait_observed"] = durable_wait or item.get("durable_wait_observed") is True
            item["job_id"] = job_id or item.get("job_id")
            item["agent_call_count"] = current.get("call_count")
            item["agent_turn_count"] = current.get("turn_count")
            item["session_id"] = session_id
            snapshot = budget.snapshot()
            request_state = state.setdefault("requests", {}).setdefault(stage, {})
            before = request_state.get("provider_calls_before_stage", item.get("provider_calls_before_stage"))
            if type(before) is int:
                item["provider_calls_before_stage"] = before
                if status == "COMPLETED" and type(current.get("turn_count")) is int:
                    request_state.setdefault("provider_calls_after_stage", before + current["turn_count"])
                else:
                    request_state.setdefault("provider_calls_after_stage", snapshot["calls_used"])
                item["provider_calls_after_stage"] = request_state["provider_calls_after_stage"]
            request_state["status"] = status
            item["transcript_binding"] = _persisted_stage_binding(
                engine, current,
                request_id=request_id, prompt=prompt, session_id=session_id,
                public_trace=trace,
                budget_snapshot=snapshot, calls_before_stage=before,
            )
            if status != "COMPLETED":
                item.setdefault("failure_code", "AGENT_REQUEST_DID_NOT_COMPLETE")
            state.setdefault("stage_evidence", {})[stage] = copy.deepcopy(item)
            _save_state(state_path, state)
            if status != "COMPLETED":
                raise HarnessFailure(item.get("failure_code", "AGENT_REQUEST_DID_NOT_COMPLETE"))
            return current
        if status == "WAITING_FOR_JOB":
            active_job_id = current.get("active_job_id")
            nonce = current.get("resume_nonce")
            if not isinstance(active_job_id, str) or not isinstance(nonce, str) or not nonce:
                raise HarnessFailure("DURABLE_WAIT_STATE_INVALID")
            durable_wait = True
            job_id = active_job_id
            wait_list = state.setdefault("durable_waits", [])
            wait_record = {
                "stage": stage, "request_id": request_id, "job_id": active_job_id,
                "observed_at": _utc_now(), "status": "WAITING_FOR_JOB",
            }
            if not any(
                isinstance(existing, dict)
                and existing.get("stage") == stage
                and existing.get("request_id") == request_id
                and existing.get("job_id") == active_job_id
                for existing in wait_list
            ):
                wait_list.append(wait_record)
            evidence["durable_waits"] = copy.deepcopy(wait_list)
            item["durable_wait_observed"] = True
            item["job_id"] = active_job_id
            item.setdefault("resume_events", [])
            state.setdefault("stage_evidence", {})[stage] = copy.deepcopy(item)
            # This authenticated GET is a separate read of persisted WAITING state.
            durable = _api_get(client, request_path, headers)
            if durable.get("status") != "WAITING_FOR_JOB" or durable.get("active_job_id") != active_job_id:
                raise HarnessFailure("WAITING_STATE_NOT_DURABLE")
            _save_state(state_path, state)
            while time.monotonic() < deadline:
                job = _api_get(client, f"/api/v1/jobs/{active_job_id}", headers)
                job_status = job.get("status")
                if job_status in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(0.5)
            else:
                raise HarnessFailure("WORKER_JOB_TIMEOUT")
            calls_before_resume = budget.snapshot()["calls_used"]
            resume_response = client.post(
                f"{request_path}/resume", headers=headers,
                json={"nonce": nonce},
            )
            replay_status_code = resume_response.status_code
            replay = _json_response(resume_response, (200, 202, 500))
            calls_after_resume = budget.snapshot()["calls_used"]
            resume_record = {
                "request_id": request_id, "job_id": active_job_id,
                "job_status": job_status, "resume_status_code": replay_status_code,
                "provider_calls_before": calls_before_resume,
                "provider_calls_after": calls_after_resume,
            }
            resume_events = item.setdefault("resume_events", [])
            if resume_record not in resume_events:
                resume_events.append(resume_record)
            state.setdefault("stage_evidence", {})[stage] = copy.deepcopy(item)
            _save_state(state_path, state)
            if replay.get("status") == "FAILED" or replay.get("error"):
                # The next authenticated GET binds and saves the real terminal
                # request before reporting the resume failure.
                item["failure_code"] = "AGENT_RESUME_FAILED"
                state.setdefault("stage_evidence", {})[stage] = copy.deepcopy(item)
                _save_state(state_path, state)
            time.sleep(0.05)
            continue
        if status == "RUNNING":
            time.sleep(0.25)
            continue
        raise HarnessFailure("AGENT_REQUEST_STATUS_INVALID")
    raise HarnessFailure("AGENT_REQUEST_TIMEOUT")


def _submit_stage(
    client,
    *,
    state: dict[str, Any],
    state_path: Path,
    evidence: dict[str, Any],
    stage: str,
    prompt: str,
    headers: dict[str, str],
    budget,
    engine,
    timeout_seconds: int,
) -> dict[str, Any]:
    evidence.setdefault("requests", {})
    evidence.setdefault("durable_waits", copy.deepcopy(state.get("durable_waits", [])))
    evidence["requests"].setdefault(
        stage, copy.deepcopy(state.get("stage_evidence", {}).get(stage, {}))
    )
    request_state = _request_key(state, stage, prompt)
    _save_state(state_path, state)
    request_id = request_state.get("request_id")
    if request_id:
        initial = _api_get(client, f"/api/v1/agent/requests/{request_id}", headers)
    else:
        before = budget.snapshot()["calls_used"]
        request_state.setdefault("provider_calls_before_stage", before)
        request_state.setdefault("calls_before_submit", request_state["provider_calls_before_stage"])
        _save_state(state_path, state)
        submit_response = client.post(
            "/api/v1/agent/requests", headers=headers,
            json={"prompt": prompt, "idempotency_key": request_state["intent_key"]},
        )
        initial = _json_response(submit_response, (200, 202, 500))
        request_id = initial.get("request_id")
        if submit_response.status_code == 500 and (
            not isinstance(request_id, str) or not _REQUEST_ID_RE.fullmatch(request_id)
            or initial.get("status") not in {"FAILED", "CANCELLED"}
            or initial.get("session_id") != state["session_id"]
            or initial.get("prompt") != prompt
        ):
            raise HarnessFailure("HTTP_STATUS_500")
        if not isinstance(request_id, str):
            raise HarnessFailure("AGENT_REQUEST_ID_MISSING")
        request_state["request_id"] = request_id
        request_state["status"] = initial.get("status")
        request_state.setdefault("submit_http_status", submit_response.status_code)
        _save_state(state_path, state)
        if initial.get("status") not in {"COMPLETED", "FAILED", "CANCELLED", "RUNNING", "WAITING_FOR_JOB"}:
            raise HarnessFailure("AGENT_REQUEST_STATUS_INVALID")
        # Calls may not complete yet; idempotent replay is checked after terminal state.

    if not request_id:
        raise HarnessFailure("AGENT_REQUEST_ID_MISSING")
    if "provider_calls_before_stage" not in request_state:
        request_state["provider_calls_before_stage"] = budget.snapshot()["calls_used"]
    item = evidence["requests"].setdefault(stage, {})
    item.setdefault("prompt", prompt)
    item["request_id"] = request_id
    item["session_id"] = state["session_id"]
    if "submit_http_status" in request_state:
        item.setdefault("submit_http_status", request_state["submit_http_status"])
    item["intent_key_sha256"] = hashlib.sha256(request_state["intent_key"].encode("utf-8")).hexdigest()
    item.setdefault("resume_events", [])
    _save_state(state_path, state)
    completed = _poll_request(
        client,
        request_id=request_id,
        headers=headers,
        timeout_seconds=timeout_seconds,
        evidence=evidence,
        stage=stage,
        state=state,
        state_path=state_path,
        budget=budget,
        engine=engine,
        prompt=prompt,
        session_id=state["session_id"],
    )
    request_state["status"] = completed.get("status")
    request_state.setdefault("provider_calls_after_stage", budget.snapshot()["calls_used"])
    stage_item = evidence["requests"][stage]
    stage_item["provider_calls_before_stage"] = request_state["provider_calls_before_stage"]
    stage_item["provider_calls_after_stage"] = request_state["provider_calls_after_stage"]
    _save_state(state_path, state)

    calls_before_replay = budget.snapshot()["calls_used"]
    replay = _json_response(
        client.post(
            "/api/v1/agent/requests",
            headers=headers,
            json={"prompt": prompt, "idempotency_key": request_state["intent_key"]},
        ),
        (200, 202),
    )
    calls_after_replay = budget.snapshot()["calls_used"]
    if replay.get("request_id") != request_id or calls_after_replay != calls_before_replay:
        raise HarnessFailure("IDEMPOTENT_REPLAY_CHANGED_REQUEST_OR_BUDGET")
    evidence["requests"][stage]["idempotent_replay_zero_added_calls"] = True
    evidence["requests"][stage]["provider_calls_before_replay"] = calls_before_replay
    evidence["requests"][stage]["provider_calls_after_replay"] = calls_after_replay
    evidence["requests"][stage]["replay_request_id"] = replay.get("request_id")
    evidence["requests"][stage]["prompt"] = prompt
    state.setdefault("stage_evidence", {})[stage] = copy.deepcopy(evidence["requests"][stage])
    _save_state(state_path, state)
    return completed


def _published_experiment(engine, experiment_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from shiftguard.storage.repositories import ExperimentRepository

    published = ExperimentRepository(engine).get_published(experiment_id)
    if not published:
        raise HarnessFailure("PUBLISHED_EXPERIMENT_NOT_FOUND")
    stored, publication = published
    payload = getattr(stored, "deterministic_payload", None)
    if payload is None:
        payload = getattr(stored, "payload_json", None)
    if not isinstance(payload, dict):
        raise HarnessFailure("PUBLISHED_PAYLOAD_INVALID")
    return payload, {"status": getattr(publication, "status", "PUBLISHED")}


def _bind_results_to_publication(evidence: dict[str, Any], conditions: dict[str, Any], experiment_id: str) -> None:
    from shiftguard.agent.policy import APPROVED_CALIBRATORS

    read_calls = [item for item in evidence["requests"]["read"]["tool_trace"] if item.get("tool_name") == "read_experiment_results"]
    compare_calls = [item for item in evidence["requests"]["compare"]["tool_trace"] if item.get("tool_name") == "compare_calibrators"]
    if len(read_calls) != 1 or len(compare_calls) != 1:
        raise HarnessFailure("PUBLISHED_READ_OR_COMPARE_TOOL_MISSING")
    read_data = (read_calls[0].get("result") or {}).get("data") or {}
    key = EXPECTED_CONDITION_KEY
    persisted_read = conditions.get(key)
    if (
        not isinstance(persisted_read, dict)
        or read_data.get("experiment_id") != experiment_id
        or read_data.get("condition_key") != key
        or read_data.get("condition_id") != persisted_read.get("condition_id")
        or read_data.get("status") != persisted_read.get("status")
        or read_data.get("scenario") != EXPECTED_SCENARIO
        or read_data.get("predictor") != EXPECTED_PREDICTOR
        or read_data.get("budget") != EXPECTED_BUDGET
    ):
        raise HarnessFailure("READ_CONDITION_ID_DIFFERS_FROM_PUBLICATION")
    for metric, value in (read_data.get("metrics") or {}).items():
        if value != (persisted_read.get("metrics") or {}).get(metric):
            raise HarnessFailure("READ_METRICS_DIFFER_FROM_PUBLICATION")
    bindings = {
        "read": {
            "condition_key": key,
            "condition_id": persisted_read.get("condition_id"),
            "status": persisted_read.get("status"),
            "metrics": copy.deepcopy(read_data.get("metrics") or {}),
        },
        "compare": {},
    }

    comparisons = ((compare_calls[0].get("result") or {}).get("data") or {}).get("calibrator_comparisons")
    if not isinstance(comparisons, dict) or set(comparisons) != set(APPROVED_CALIBRATORS):
        raise HarnessFailure("COMPARISON_METHOD_GRID_DIFFERS_FROM_PUBLICATION")
    context_fields = ("predictor_id", "dataset_id", "evaluation_rows_id", "source_map_id")
    raw = comparisons.get("raw")
    if not isinstance(raw, dict):
        raise HarnessFailure("COMPARISON_RAW_BASELINE_MISSING")
    for method, result in comparisons.items():
        persisted = conditions.get(f"{EXPECTED_PREDICTOR}__{EXPECTED_SCENARIO}__b{EXPECTED_BUDGET}__{method}")
        if (
            not isinstance(result, dict) or not isinstance(persisted, dict)
            or result.get("condition_id") != persisted.get("condition_id")
            or result.get("status") != persisted.get("status")
            or result.get("comparison_qualified") is not True
            or result.get("status") != "scored"
            or any(result.get(field) != raw.get(field) for field in context_fields)
            or result.get("scenario") != EXPECTED_SCENARIO
            or result.get("budget") != EXPECTED_BUDGET
        ):
            raise HarnessFailure("COMPARISON_CONDITION_OR_CONTEXT_DIFFERS_FROM_PUBLICATION")
        for metric in ("brier_score", "log_loss", "ece"):
            if result.get(metric) != (persisted.get("metrics") or {}).get(metric):
                raise HarnessFailure("COMPARISON_METRICS_DIFFER_FROM_PUBLICATION")
        bindings["compare"][method] = {
            "condition_key": f"{EXPECTED_PREDICTOR}__{EXPECTED_SCENARIO}__b{EXPECTED_BUDGET}__{method}",
            "condition_id": persisted.get("condition_id"),
            "status": persisted.get("status"),
            "metrics": {
                metric: result.get(metric)
                for metric in ("brier_score", "log_loss", "ece")
                if result.get(metric) is not None
            },
        }
    evidence["publication"]["condition_bindings"] = bindings


def _run_live(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    _validate_live_args(args)
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from shiftguard.agent.budget import AttemptBudget, LIVE_BUDGET_ENV
    from shiftguard.api.main import create_app
    from shiftguard.settings import Settings

    source = source_manifest()
    resume_state = _load_state(args.resume_state) if args.resume_state is not None else None
    if resume_state:
        schema = resume_state["schema"]
        ledger_id = resume_state["ledger_id"]
        if args.schema not in {None, schema} or args.ledger_id not in {None, ledger_id}:
            raise HarnessFailure("RESUME_LEDGER_OR_SCHEMA_MISMATCH")
        if resume_state.get("source_sha256") != source["sha256"]:
            raise HarnessFailure("RESUME_SOURCE_BINDING_MISMATCH")
        if resume_state.get("max_calls") != args.max_calls or resume_state.get("max_tokens") != args.max_tokens:
            raise HarnessFailure("RESUME_BUDGET_CEILING_MISMATCH")
    else:
        suffix = f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
        schema = "sg_live_acceptance_" + suffix
        ledger_id = "live-" + uuid4().hex
    if not _SCHEMA_RE.fullmatch(schema):
        raise HarnessFailure("ISOLATED_SCHEMA_NAME_INVALID")
    evidence_dir = _evidence_directory(args, ledger_id)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.resume_state.resolve() if args.resume_state is not None else evidence_dir / "live-state.json"
    state_lock = _acquire_state_lock(state_path)

    evidence_number = 1
    while (evidence_dir / f"attempt-{evidence_number:04d}.json").exists():
        evidence_number += 1
    evidence_path = evidence_dir / f"attempt-{evidence_number:04d}.json"
    evidence: dict[str, Any] = {
        "schema": LIVE_EVIDENCE_SCHEMA,
        "status": "RUNNING",
        "started_at": _utc_now(),
        "source_binding": source,
        "runtime": {
            "provider": "nebius",
            "model": EXPECTED_MODEL,
            "database": "shiftguard_gate3",
            "database_major": None,
            "schema": schema,
            "loopback_only": True,
            "http_host": "127.0.0.1",
            "artifact_root": (evidence_dir / "artifacts").resolve().as_posix(),
        },
        "budget": {},
        "session_id": None,
        "requests": copy.deepcopy(resume_state.get("stage_evidence", {})) if resume_state else {},
        "durable_waits": copy.deepcopy(resume_state.get("durable_waits", [])) if resume_state else [],
        "startup_budget": {},
        "publication": {},
        "failure_code": None,
        "checks": [],
    }
    if resume_state:
        evidence["session_id"] = resume_state.get("session_id")
    live_server = None
    server_thread = None
    app_engine = None
    budget_engine = None
    monitor_budget = None
    previous_budget_env = os.environ.get(LIVE_BUDGET_ENV)
    status_code = 1
    try:
        if previous_budget_env is not None:
            raise HarnessFailure("LIVE_BUDGET_ENV_ALREADY_SET")
        raw_test_url = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
        if not raw_test_url:
            raise HarnessFailure("SHIFTGUARD_TEST_POSTGRES_URL_REQUIRED")
        admin_url = _test_database_url(raw_test_url)
        _major, version_num = _prepare_schema(
            admin_url, schema, create=resume_state is None
        )
        evidence["runtime"]["database_major"] = int(_major)

        scoped = _scoped_url(admin_url, schema)
        scoped_db_url = scoped.render_as_string(hide_password=False)
        base_settings = Settings()
        if (
            not base_settings.nebius_api_key or not base_settings.nebius_api_key.strip()
            or base_settings.nebius_model != EXPECTED_MODEL
            or base_settings.nebius_max_retries != 0
        ):
            raise HarnessFailure("LIVE_PROVIDER_CONFIGURATION_UNAVAILABLE_OR_UNSUPPORTED")
        live_settings = base_settings.model_copy(update={
            "db_url": scoped_db_url,
            "environment": "hosted",
            "artifact_root": (evidence_dir / "artifacts").resolve(),
            "embedded_worker": True,
            "agent_enabled": True,
        })
        binding = {
            "ledger_id": ledger_id,
            "source_digest": source["sha256"],
            "max_calls": args.max_calls,
            "max_tokens": args.max_tokens,
        }
        os.environ[LIVE_BUDGET_ENV] = json.dumps(binding, sort_keys=True, separators=(",", ":"))

        budget_engine = create_engine(scoped, pool_pre_ping=True)
        monitor_budget = AttemptBudget(
            budget_engine, ledger_id=ledger_id, source_digest=source["sha256"],
            max_calls=args.max_calls, max_tokens=args.max_tokens,
        )
        if resume_state:
            monitor_budget.recover_unresolved()
        startup_before = monitor_budget.snapshot()
        if startup_before["halted"]:
            raise HarnessFailure("LIVE_LEDGER_HALTED_ON_RESUME")

        # This app exists only in this process, uses the isolated schema, and is
        # bound to loopback. Its ordinary global app and settings are untouched.
        app = create_app(live_settings)
        live_server, server_thread, port = _server_thread(app)
        import httpx

        timeout = httpx.Timeout(connect=5, read=120, write=15, pool=15)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=timeout) as client:
            status = _api_get(client, "/api/v1/agent/status", {})
            if (
                status.get("enabled") is not True
                or status.get("available") is not True
                or status.get("provider_kind") != "nebius"
                or status.get("model") != EXPECTED_MODEL
            ):
                raise HarnessFailure("INVOCATION_PROVIDER_STATUS_INVALID")
            startup_after = monitor_budget.snapshot()
            if _snapshot_identity(startup_before) != _snapshot_identity(startup_after):
                raise HarnessFailure("STARTUP_MADE_PROVIDER_ATTEMPT")
            evidence["startup_budget"] = {
                "before": startup_before,
                "after": startup_after,
                "provider_calls_added": 0,
            }
            app_engine = app.state.engine
            if resume_state:
                resume_state.setdefault("startup_observations", []).append(evidence["startup_budget"])
                _save_state(state_path, resume_state)

            headers: dict[str, str]
            if resume_state:
                session_id = resume_state["session_id"]
                capability = _get_capability(app_engine, session_id)
            else:
                created = _json_response(
                    client.post("/api/v1/agent/sessions", json={}), (201,)
                )
                session_id = created.get("session_id")
                capability = created.get("capability_token")
                if not isinstance(session_id, str) or not isinstance(capability, str) or not capability:
                    raise HarnessFailure("SERVER_ISSUED_CAPABILITY_INVALID")
                evidence["session_id"] = session_id
                resume_state = {
                    "version": 2,
                    "schema": schema,
                    "ledger_id": ledger_id,
                    "source_sha256": source["sha256"],
                    "max_calls": args.max_calls,
                    "max_tokens": args.max_tokens,
                    "session_id": session_id,
                    "requests": {},
                    "stage_evidence": {},
                    "durable_waits": [],
                    "startup_observations": [evidence["startup_budget"]],
                }
                _save_state(state_path, resume_state)
            headers = {"X-Session-ID": session_id, "X-Session-Token": capability}
            _get_capability(app_engine, session_id)

            completed_run = _submit_stage(
                client, state=resume_state, state_path=state_path, evidence=evidence,
                stage="run", prompt="Run bank-stress", headers=headers,
                budget=monitor_budget, engine=app_engine,
                timeout_seconds=args.run_timeout_seconds,
            )
            run_trace = evidence["requests"]["run"]["tool_trace"]
            run_tools = [
                item for item in run_trace
                if item.get("tool_name") in {"run_experiment", "run_stress_suite"}
            ]
            if len(run_tools) != 1 or not _is_flagship_run_tool(run_tools[0]):
                raise HarnessFailure("MODEL_DID_NOT_RUN_EXACT_FLAGSHIP_PRESET")
            run_job_id = run_tools[0]["job_id"]
            evidence["requests"]["run"]["preset"] = EXPECTED_PRESET
            if evidence["requests"]["run"].get("job_id") not in {None, run_job_id}:
                raise HarnessFailure("DURABLE_JOB_ID_DIFFERS_FROM_RUN_TOOL")
            evidence["requests"]["run"]["job_id"] = run_job_id
            resume_state.setdefault("stage_evidence", {})["run"] = copy.deepcopy(evidence["requests"]["run"])
            _save_state(state_path, resume_state)
            job = _api_get(client, f"/api/v1/jobs/{run_job_id}", headers)
            experiment_id = job.get("experiment_id")
            if job.get("status") != "completed" or not isinstance(experiment_id, str) or not _ID_RE.fullmatch(experiment_id):
                raise HarnessFailure("FLAGSHIP_JOB_NOT_PUBLISHED")

            payload, publication = _published_experiment(app_engine, experiment_id)
            config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
            conditions = payload.get("conditions") if isinstance(payload.get("conditions"), dict) else {}
            if (
                config.get("master_seed") != 31001
                or config.get("evaluation_tier") != "development"
                or len(conditions) != 400
                or EXPECTED_CONDITION_KEY not in conditions
            ):
                raise HarnessFailure("FLAGSHIP_PUBLICATION_BINDING_INVALID")
            publication_evidence = {
                "experiment_id": experiment_id,
                "job_id": run_job_id,
                "job_status": job.get("status"),
                "status": publication["status"],
                "preset": EXPECTED_PRESET,
                "evaluation_tier": config.get("evaluation_tier"),
                "master_seed": config.get("master_seed"),
                "condition_count": len(conditions),
                "expected_condition_key": EXPECTED_CONDITION_KEY,
                "expected_condition_id": conditions[EXPECTED_CONDITION_KEY].get("condition_id"),
            }
            evidence["publication"] = publication_evidence

            read_prompt = _read_prompt(experiment_id)
            read_result = _submit_stage(
                client, state=resume_state, state_path=state_path, evidence=evidence,
                stage="read", prompt=read_prompt, headers=headers,
                budget=monitor_budget, engine=app_engine,
                timeout_seconds=args.run_timeout_seconds,
            )
            compare_prompt = _compare_prompt(experiment_id)
            compare_result = _submit_stage(
                client, state=resume_state, state_path=state_path, evidence=evidence,
                stage="compare", prompt=compare_prompt, headers=headers,
                budget=monitor_budget, engine=app_engine,
                timeout_seconds=args.run_timeout_seconds,
            )
            # Keep the API objects local; only projected tool traces and Python
            # claims are added to evidence.
            del completed_run, read_result, compare_result

            _bind_results_to_publication(evidence, conditions, experiment_id)
            evidence["budget"] = monitor_budget.snapshot()
            evidence["runtime"]["schema"] = schema
            evidence["runtime"]["server_port"] = port
            evidence["ledger_id"] = ledger_id
            evidence["completed_at"] = _utc_now()
            evidence["failure_code"] = None
            evidence = _pass_candidate(evidence)
            status_code = 0
    except HarnessFailure as exc:
        evidence["status"] = "FAIL"
        evidence["failure_code"] = exc.code
    except Exception as exc:
        evidence["status"] = "FAIL"
        evidence["failure_code"] = "HARNESS_INTERNAL_" + type(exc).__name__[:48].upper()
    finally:
        if live_server is not None:
            live_server.should_exit = True
        if server_thread is not None:
            server_thread.join(timeout=20)
        if app_engine is not None:
            app_engine.dispose()
        if monitor_budget is not None and evidence.get("status") != "PASS":
            try:
                evidence["budget"] = monitor_budget.snapshot()
            except Exception:
                pass
        if budget_engine is not None:
            budget_engine.dispose()
        if previous_budget_env is None:
            os.environ.pop(LIVE_BUDGET_ENV, None)
        else:
            os.environ[LIVE_BUDGET_ENV] = previous_budget_env
        if evidence.get("status") != "PASS":
            evidence["completed_at"] = _utc_now()
            evidence["ledger_id"] = ledger_id
            evidence["schema"] = LIVE_EVIDENCE_SCHEMA
        try:
            _assert_no_sensitive_evidence(evidence)
            digest = _write_json(evidence_path, evidence)
            print(json.dumps({
                "status": evidence["status"],
                "evidence": evidence_path.as_posix(),
                "evidence_sha256": digest,
                "ledger_id": ledger_id,
                "schema": schema,
                "calls_used": evidence.get("budget", {}).get("calls_used"),
                "max_calls": evidence.get("budget", {}).get("max_calls", args.max_calls),
                "tokens_committed": evidence.get("budget", {}).get("tokens_committed"),
                "max_tokens": evidence.get("budget", {}).get("max_tokens", args.max_tokens),
                "failure_code": evidence.get("failure_code"),
            }, sort_keys=True))
        except Exception:
            print(json.dumps({"status": "FAIL", "failure_code": "EVIDENCE_WRITE_FAILED"}, sort_keys=True))
            status_code = 1
        _release_state_lock(state_lock)
    return status_code, evidence


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.live:
            code, _evidence = _run_live(args)
            return code
        if args.offline_check:
            print(json.dumps(_offline_check(), sort_keys=True))
            return 0
        if args.inspect_evidence:
            print(json.dumps(_inspect_evidence(args.inspect_evidence, require_current_source=False), sort_keys=True))
            return 0
        if args.validate_evidence:
            print(json.dumps(_inspect_evidence(args.validate_evidence, require_current_source=True), sort_keys=True))
            return 0
    except HarnessFailure as exc:
        print(json.dumps({"status": "FAIL", "failure_code": exc.code}, sort_keys=True))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "failure_code": "HARNESS_INTERNAL_" + type(exc).__name__[:48].upper()}, sort_keys=True))
        return 2
    parser.error("choose exactly one execution mode")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
