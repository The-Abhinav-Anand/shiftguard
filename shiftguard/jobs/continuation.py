"""Agent session continuation service with single-use nonces and durable dependency tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import hmac
import secrets
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from shiftguard.jobs.models import SessionStatus, utc_now_str
from shiftguard.jobs.queue import JobQueue


@dataclass(frozen=True)
class AgentSessionRecord:
    id: str
    status: SessionStatus
    active_nonce: str
    required_job_ids: list[str]
    state: dict[str, Any]
    result: dict[str, Any] | None
    created_at: str
    updated_at: str
    capability_token: str | None = None
    raw_required_job_ids_json: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AgentSessionRecord:
        req_raw = row.get("required_job_ids_json")
        req_jobs = json.loads(req_raw) if isinstance(req_raw, str) else (req_raw or [])
        state_raw = row.get("state_json")
        state = json.loads(state_raw) if isinstance(state_raw, str) else (state_raw or {})
        res_raw = row.get("result_json")
        res = json.loads(res_raw) if isinstance(res_raw, str) and res_raw else None

        return cls(
            id=row["id"],
            status=SessionStatus(row["status"]),
            active_nonce=row["active_nonce"],
            required_job_ids=req_jobs,
            state=state,
            result=res,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            capability_token=row.get("capability_token"),
            raw_required_job_ids_json=req_raw if isinstance(req_raw, str) else json.dumps(req_jobs),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "active_nonce": self.active_nonce,
            "required_job_ids": self.required_job_ids,
            "state": self.state,
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "capability_token": self.capability_token,
        }


class ContinuationService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.is_sqlite = engine.dialect.name == "sqlite"

    def create_session(self, initial_state: dict[str, Any] | None = None) -> AgentSessionRecord:
        """Create a new agent session with an active nonce and capability token."""
        session_id = str(uuid4())
        nonce = uuid4().hex
        capability_token = secrets.token_hex(32)
        now = utc_now_str()
        state = initial_state or {}

        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO agent_sessions (
                        id, status, active_nonce, capability_token, required_job_ids_json, state_json, created_at, updated_at
                    ) VALUES (
                        :id, :status, :active_nonce, :capability_token, :required_job_ids_json, :state_json, :created_at, :updated_at
                    )
                """),
                {
                    "id": session_id,
                    "status": SessionStatus.ACTIVE.value,
                    "active_nonce": nonce,
                    "capability_token": capability_token,
                    "required_job_ids_json": json.dumps([]),
                    "state_json": json.dumps(state, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            row = conn.execute(
                text("SELECT * FROM agent_sessions WHERE id = :id"),
                {"id": session_id},
            ).mappings().fetchone()
            return AgentSessionRecord.from_row(dict(row))

    def get_session(self, session_id: str) -> AgentSessionRecord | None:
        """Retrieve an agent session by ID."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM agent_sessions WHERE id = :id"),
                {"id": session_id},
            ).mappings().fetchone()
            return AgentSessionRecord.from_row(dict(row)) if row else None


    def bind_jobs_to_session(
        self,
        session_id: str,
        job_ids: list[str],
        updated_state: dict[str, Any] | None = None,
    ) -> AgentSessionRecord:
        """Bind blocking jobs to session and transition to WAITING_FOR_JOB."""
        now = utc_now_str()
        with self.engine.begin() as conn:
            if self.is_sqlite:
                conn.execute(text("BEGIN IMMEDIATE"))
                row = conn.execute(
                    text("SELECT * FROM agent_sessions WHERE id = :id"),
                    {"id": session_id},
                ).mappings().fetchone()
            else:
                row = conn.execute(
                    text("SELECT * FROM agent_sessions WHERE id = :id FOR UPDATE"),
                    {"id": session_id},
                ).mappings().fetchone()

            if not row:
                raise ValueError(f"Session {session_id} not found")

            current_status = row["status"]
            if str(current_status).upper() in ("COMPLETED", "FAILED", "EXPIRED", "CANCELLED"):
                raise ValueError(f"Cannot bind jobs to terminal session in status '{current_status}'")

            # Validate that each job in job_ids belongs to this session
            if job_ids:
                for jid in job_ids:
                    job_row = conn.execute(
                        text("SELECT session_id FROM jobs WHERE id = :job_id"),
                        {"job_id": jid},
                    ).mappings().fetchone()
                    if not job_row:
                        raise ValueError(f"Job {jid} not found")
                    if job_row["session_id"] is not None and job_row["session_id"] != session_id:
                        raise ValueError(f"Job {jid} does not belong to session {session_id}")
                    if job_row["session_id"] is None:
                        conn.execute(
                            text("UPDATE jobs SET session_id = :session_id WHERE id = :job_id"),
                            {"session_id": session_id, "job_id": jid},
                        )

            state = json.loads(row["state_json"]) if isinstance(row["state_json"], str) else (row["state_json"] or {})
            if updated_state:
                state.update(updated_state)

            raw_req = row.get("required_job_ids_json")
            existing_jobs = json.loads(raw_req) if isinstance(raw_req, str) else (raw_req or [])
            # Deduplicate preserving order
            merged_jobs = list(dict.fromkeys(existing_jobs + list(job_ids)))

            res = conn.execute(
                text("""
                    UPDATE agent_sessions SET
                        status = :status,
                        required_job_ids_json = :required_job_ids_json,
                        state_json = :state_json,
                        updated_at = :now
                    WHERE id = :id AND status NOT IN ('completed', 'failed', 'expired', 'cancelled')
                """),
                {
                    "status": SessionStatus.WAITING_FOR_JOB.value,
                    "required_job_ids_json": json.dumps(merged_jobs),
                    "state_json": json.dumps(state, ensure_ascii=False),
                    "now": now,
                    "id": session_id,
                },
            )
            if res.rowcount == 0:
                raise ValueError(f"Failed to bind jobs: session {session_id} transitioned concurrently")

            updated_row = conn.execute(
                text("SELECT * FROM agent_sessions WHERE id = :id"),
                {"id": session_id},
            ).mappings().fetchone()
            return AgentSessionRecord.from_row(dict(updated_row))

    def resume(
        self,
        session_id: str,
        nonce: str,
        queue: JobQueue,
    ) -> tuple[int, dict[str, Any]]:
        """Attempt to resume a session using single-use nonce with durable replay receipt.
        
        Returns (http_status_code, response_payload).
        """
        # Step 0: Check if a replay receipt exists for this nonce
        with self.engine.connect() as conn:
            receipt = conn.execute(
                text("SELECT status_code, response_json FROM continuation_receipts WHERE session_id = :session_id AND nonce = :nonce"),
                {"session_id": session_id, "nonce": nonce},
            ).mappings().fetchone()
            if receipt:
                return receipt["status_code"], json.loads(receipt["response_json"])

        session = self.get_session(session_id)
        if not session:
            return 404, {"error": {"code": "SESSION_NOT_FOUND", "message": f"Session {session_id} not found"}}

        if session.active_nonce != nonce:
            # Re-check receipts in case of concurrent commit
            with self.engine.connect() as conn:
                receipt = conn.execute(
                    text("SELECT status_code, response_json FROM continuation_receipts WHERE session_id = :session_id AND nonce = :nonce"),
                    {"session_id": session_id, "nonce": nonce},
                ).mappings().fetchone()
                if receipt:
                    return receipt["status_code"], json.loads(receipt["response_json"])
            return 403, {"error": {"code": "INVALID_NONCE", "message": "Supplied nonce does not match active session nonce"}}

        if session.status == SessionStatus.EXPIRED:
            return 401, {"error": {"code": "SESSION_EXPIRED", "message": f"Session '{session_id}' has expired"}}

        # If already completed or failed, return deterministic cached result
        if session.status in (SessionStatus.COMPLETED, SessionStatus.FAILED):
            return 200, {
                "session_id": session_id,
                "status": session.status.value,
                "nonce": session.active_nonce,
                "result": session.result,
            }

        # If active without pending jobs
        if session.status == SessionStatus.ACTIVE:
            return 200, {
                "session_id": session_id,
                "status": SessionStatus.ACTIVE.value,
                "nonce": session.active_nonce,
                "state": session.state,
            }

        # WAITING_FOR_JOB: check job statuses
        job_records = [queue.get_job(jid) for jid in session.required_job_ids]
        pending_jobs = []
        job_results = {}
        has_failure = False

        for jid, jrec in zip(session.required_job_ids, job_records):
            if not jrec:
                has_failure = True
                job_results[jid] = {"status": "not_found"}
            elif jrec.status.value in ("queued", "running"):
                pending_jobs.append(jid)
            elif jrec.status.value in ("failed", "cancelled"):
                has_failure = True
                job_results[jid] = {"status": jrec.status.value, "error": jrec.error}
            else:
                job_results[jid] = {"status": jrec.status.value, "result": jrec.result}

        # If any job is still pending, return 202 Accepted without changing state
        if pending_jobs:
            return 202, {
                "session_id": session_id,
                "status": SessionStatus.WAITING_FOR_JOB.value,
                "nonce": session.active_nonce,
                "pending_job_ids": pending_jobs,
                "message": f"Waiting for {len(pending_jobs)} job(s) to finish",
            }

        # All jobs have completed: transition atomically
        new_status = SessionStatus.FAILED if has_failure else SessionStatus.COMPLETED
        new_nonce = uuid4().hex
        now = utc_now_str()
        final_result = {
            "jobs": job_results,
            "completed_at": now,
            "overall_status": "success" if not has_failure else "error",
        }

        payload = {
            "session_id": session_id,
            "status": new_status.value,
            "nonce": new_nonce,
            "result": final_result,
        }

        expected_required_jobs = session.raw_required_job_ids_json or json.dumps(session.required_job_ids)
        expected_status = session.status.value

        with self.engine.begin() as conn:
            res = conn.execute(
                text("""
                    UPDATE agent_sessions SET
                        status = :status,
                        active_nonce = :new_nonce,
                        result_json = :result_json,
                        updated_at = :now
                    WHERE id = :id 
                      AND active_nonce = :old_nonce
                      AND required_job_ids_json = :expected_required_jobs
                      AND status = :expected_status
                """),
                {
                    "status": new_status.value,
                    "new_nonce": new_nonce,
                    "result_json": json.dumps(final_result, ensure_ascii=False),
                    "now": now,
                    "id": session_id,
                    "old_nonce": nonce,
                    "expected_required_jobs": expected_required_jobs,
                    "expected_status": expected_status,
                },
            )
            if res.rowcount > 0:
                conn.execute(
                    text("""
                        INSERT INTO continuation_receipts (session_id, nonce, status_code, response_json, created_at)
                        VALUES (:session_id, :nonce, 200, :response_json, :created_at)
                    """),
                    {
                        "session_id": session_id,
                        "nonce": nonce,
                        "response_json": json.dumps(payload, ensure_ascii=False),
                        "created_at": now,
                    },
                )
                return 200, payload
            else:
                # Concurrent transaction won: fetch their receipt if already completed
                receipt = conn.execute(
                    text("SELECT status_code, response_json FROM continuation_receipts WHERE session_id = :session_id AND nonce = :nonce"),
                    {"session_id": session_id, "nonce": nonce},
                ).mappings().fetchone()
                if receipt:
                    return receipt["status_code"], json.loads(receipt["response_json"])

                # Check if dependencies or status changed concurrently
                cur_row = conn.execute(
                    text("SELECT status, active_nonce, required_job_ids_json FROM agent_sessions WHERE id = :id"),
                    {"id": session_id},
                ).mappings().fetchone()
                if cur_row:
                    cur_req = json.loads(cur_row["required_job_ids_json"]) if isinstance(cur_row["required_job_ids_json"], str) else (cur_row["required_job_ids_json"] or [])
                    if cur_req != session.required_job_ids or cur_row["status"] != expected_status:
                        return 409, {
                            "error": {
                                "code": "DEPENDENCY_GENERATION_CONFLICT",
                                "message": "Session dependencies or status changed concurrently during resume evaluation",
                            }
                        }
                return 409, {"error": {"code": "CONCURRENT_TRANSITION_CONFLICT", "message": "Concurrent continuation transition in progress"}}
