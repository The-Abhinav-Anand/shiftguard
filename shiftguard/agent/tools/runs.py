"""Execution tool handlers: run_experiment, run_stress_suite."""

from __future__ import annotations

from sqlalchemy import text

from shiftguard.agent.policy import (
    APPROVED_PRESETS,
    APPROVED_STRESS_SUITES,
    AgentErrorCode,
)
from shiftguard.agent.schemas import (
    RunExperimentParams,
    RunStressSuiteParams,
    ToolResult,
)
from shiftguard.agent.tools import ToolContext
from shiftguard.jobs.models import JobRecord
from shiftguard.jobs.queue import IdempotencyConflictError, JobQueue, QuotaExceededError
from shiftguard.agent.execution_authority import EXECUTION_DENIED_MESSAGE


def _admit_job(ctx: ToolContext, request_params: dict[str, str], idempotency_key: str):
    """Use the controller's fenced admission transaction for request-bound work."""
    if request_params.get("preset_name") not in ctx.authorized_run_presets:
        raise PermissionError(EXECUTION_DENIED_MESSAGE)
    if ctx.request_id is not None:
        if ctx.admit_job is None:
            raise PermissionError("request-bound enqueue requires fenced admission")
        job = ctx.admit_job(dict(request_params))
        if not isinstance(job, JobRecord):
            raise TypeError("admission callback did not return a canonical job")
        return job

    # Direct/ad-hoc use locks current authority and admits through the existing
    # queue on the same connection, so expiry cannot race a separate enqueue.
    queue = JobQueue(ctx.engine)
    with queue.admission_transaction() as conn:
        session_sql = "SELECT status FROM agent_sessions WHERE id = :sid"
        if ctx.engine.dialect.name == "postgresql":
            session_sql += " FOR UPDATE"
        row = conn.execute(text(session_sql), {"sid": ctx.session_id}).mappings().fetchone()
        if not row or str(row["status"]).upper() != "ACTIVE":
            raise PermissionError("session is not active")
        return queue.enqueue_in_transaction(
            conn,
            request_params=dict(request_params),
            session_id=ctx.session_id,
            idempotency_key=idempotency_key,
        )


def _admission_error(tool_name: str, tool_call_id: str, err: Exception) -> ToolResult:
    if isinstance(err, PermissionError):
        if str(err) == EXECUTION_DENIED_MESSAGE:
            return ToolResult(tool_name=tool_name, tool_call_id=tool_call_id, status="error",
                              error=EXECUTION_DENIED_MESSAGE)
        code = AgentErrorCode.UNAUTHORIZED_SESSION
        message = "Request-bound enqueue requires fenced admission." if "fenced admission" in str(err) else "Session is not active."
        return ToolResult(tool_name=tool_name, tool_call_id=tool_call_id, status="error", error=f"{code}: {message}")
    if isinstance(err, IdempotencyConflictError):
        code, message = AgentErrorCode.JOB_ENQUEUE_FAILED, "Idempotency conflict."
    elif isinstance(err, QuotaExceededError):
        code, message = AgentErrorCode.BUDGET_EXCEEDED, "Session job quota exceeded."
    else:
        code, message = AgentErrorCode.JOB_ENQUEUE_FAILED, "Job admission failed."
    return ToolResult(tool_name=tool_name, tool_call_id=tool_call_id, status="error", error=f"{code}: {message}")


def run_experiment(params: RunExperimentParams, ctx: ToolContext, tool_call_id: str) -> ToolResult:
    """Compile supported intent into an approved Bank preset and enqueue via JobQueue."""
    preset = params.preset_name.strip().lower()
    if preset not in APPROVED_PRESETS:
        return ToolResult(
            tool_name="run_experiment",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Preset '{params.preset_name}' is not approved. Permitted presets: {sorted(list(APPROVED_PRESETS))}",
        )

    idempotency_key = f"agent:{ctx.request_id}:{ctx.ordinal}" if ctx.request_id else f"agent-adhoc:{preset}"

    try:
        job = _admit_job(ctx, {"preset_name": preset}, idempotency_key)
    except Exception as err:
        return _admission_error("run_experiment", tool_call_id, err)

    return ToolResult(
        tool_name="run_experiment",
        tool_call_id=tool_call_id,
        status="success",
        is_side_effect=True,
        job_id=job.id,
        data={
            "job_id": job.id,
            "status": job.status.value,
            "preset_name": preset,
            "master_seed": 31001,
            "created_at": job.created_at,
            "notes": f"Job {job.id} enqueued for preset '{preset}'. Controller will wait for durable worker execution.",
        },
    )


def run_stress_suite(params: RunStressSuiteParams, ctx: ToolContext, tool_call_id: str) -> ToolResult:
    """Map a declared stress suite intent to the bounded Bank stress preset and enqueue."""
    suite = params.suite_name.strip().lower()
    if suite not in APPROVED_STRESS_SUITES:
        return ToolResult(
            tool_name="run_stress_suite",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Stress suite '{params.suite_name}' is not approved. Permitted suites: {sorted(list(APPROVED_STRESS_SUITES))}",
        )

    target_preset = "bank-stress"
    idempotency_key = f"agent:{ctx.request_id}:{ctx.ordinal}" if ctx.request_id else f"agent-adhoc:{suite}"

    try:
        job = _admit_job(ctx, {"preset_name": target_preset}, idempotency_key)
    except Exception as err:
        return _admission_error("run_stress_suite", tool_call_id, err)

    return ToolResult(
        tool_name="run_stress_suite",
        tool_call_id=tool_call_id,
        status="success",
        is_side_effect=True,
        job_id=job.id,
        data={
            "job_id": job.id,
            "status": job.status.value,
            "suite_name": suite,
            "mapped_preset": target_preset,
            "master_seed": 31001,
            "created_at": job.created_at,
            "notes": f"Stress suite mapped to preset '{target_preset}' (Job {job.id}). Controller will wait for durable worker execution.",
        },
    )
