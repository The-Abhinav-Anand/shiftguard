"""Transactional job queue with atomic claims, fencing tokens, and lease management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import threading
import time
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from shiftguard.experiments.ids import stable_hash
from shiftguard.jobs.models import JobEventType, JobRecord, JobStatus, utc_now_str


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a different payload."""
    pass


class QuotaExceededError(Exception):
    """Raised when a session exceeds its active job quota."""
    pass


class JobQueue:
    _admission_lock = threading.Lock()

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.is_sqlite = engine.dialect.name == "sqlite"

    def enqueue(
        self,
        request_params: dict[str, Any],
        session_id: str | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        max_active_per_session: int = 2,
        payload_hash: str | None = None,
    ) -> JobRecord:
        """Enqueue a new job with optional session-scoped idempotency key and admission quota.
        
        Serializes admission and idempotency across processes using a write-reserving transaction
        (BEGIN IMMEDIATE on SQLite with busy retry; row-level lock on PostgreSQL).
        Checks idempotency FIRST to return existing winning records without quota consumption or duplicate jobs.
        """
        payload_json = json.dumps(request_params, sort_keys=True, ensure_ascii=False)
        if not payload_hash:
            payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        job_id = str(uuid4())
        now = utc_now_str()
        scope = session_id or "global"

        with self._admission_lock:
            conn = self.engine.connect()
            try:
                # 1. Acquire write-reserving lock before any reads
                if self.is_sqlite:
                    for retry in range(50):
                        try:
                            conn.execute(text("BEGIN IMMEDIATE"))
                            break
                        except Exception as exc:
                            if "locked" in str(exc).lower() and retry < 49:
                                time.sleep(0.05)
                            else:
                                raise
                else:
                    conn.execute(text("BEGIN"))
                    if session_id:
                        conn.execute(
                            text("SELECT id FROM agent_sessions WHERE id = :session_id FOR UPDATE"),
                            {"session_id": session_id},
                        )

                # 2. Check idempotency FIRST
                if idempotency_key:
                    existing = conn.execute(
                        text("SELECT scope, key, payload_hash, job_id, response_code, response_json FROM idempotency_records WHERE scope = :scope AND key = :key"),
                        {"scope": scope, "key": idempotency_key},
                    ).mappings().fetchone()

                    if existing:
                        if existing["payload_hash"] != payload_hash:
                            conn.rollback()
                            raise IdempotencyConflictError(
                                f"Idempotency key '{idempotency_key}' is already associated with a different payload"
                            )
                        # Return winning existing job record without consuming quota or inserting duplicate job
                        winning_id = existing["job_id"]
                        job_row = conn.execute(
                            text("SELECT * FROM jobs WHERE id = :job_id"),
                            {"job_id": winning_id},
                        ).mappings().fetchone()
                        conn.rollback()
                        if job_row:
                            return JobRecord.from_row(dict(job_row))
                        raise RuntimeError(f"Idempotency record references non-existent job {winning_id}")

                # 3. Admission quota check per session SECOND
                if session_id:
                    active_count = conn.execute(
                        text("SELECT COUNT(*) FROM jobs WHERE session_id = :session_id AND status IN ('queued', 'running', 'claimed')"),
                        {"session_id": session_id},
                    ).scalar() or 0
                    if active_count >= max_active_per_session:
                        conn.rollback()
                        raise QuotaExceededError(
                            f"Session '{session_id}' exceeded active job quota ({active_count}/{max_active_per_session})"
                        )

                # 4. Insert job
                conn.execute(
                    text("""
                        INSERT INTO jobs (
                            id, session_id, idempotency_key, payload_hash, status,
                            request_params_json, attempt, max_attempts, cancel_requested, created_at
                        ) VALUES (
                            :id, :session_id, :idempotency_key, :payload_hash, :status,
                            :request_params_json, 0, :max_attempts, :cancel_requested, :created_at
                        )
                    """),
                    {
                        "id": job_id,
                        "session_id": session_id,
                        "idempotency_key": idempotency_key,
                        "payload_hash": payload_hash,
                        "status": JobStatus.QUEUED.value,
                        "request_params_json": payload_json,
                        "max_attempts": max_attempts,
                        "cancel_requested": False,
                        "created_at": now,
                    },
                )

                # 5. Insert idempotency record
                if idempotency_key:
                    conn.execute(
                        text("""
                            INSERT INTO idempotency_records (
                                scope, key, payload_hash, job_id, response_code, response_json, created_at
                            ) VALUES (
                                :scope, :key, :payload_hash, :job_id, 202, :response_json, :created_at
                            )
                        """),
                        {
                            "scope": scope,
                            "key": idempotency_key,
                            "payload_hash": payload_hash,
                            "job_id": job_id,
                            "response_json": json.dumps({"job_id": job_id, "status": JobStatus.QUEUED.value}),
                            "created_at": now,
                        },
                    )

                # 6. Log enqueued event
                conn.execute(
                    text("""
                        INSERT INTO job_events (job_id, event_type, details_json, created_at)
                        VALUES (:job_id, :event_type, :details_json, :created_at)
                    """),
                    {
                        "job_id": job_id,
                        "event_type": JobEventType.ENQUEUED.value,
                        "details_json": json.dumps({"session_id": session_id}),
                        "created_at": now,
                    },
                )
                conn.commit()

                job_row = conn.execute(
                    text("SELECT * FROM jobs WHERE id = :job_id"),
                    {"job_id": job_id},
                ).mappings().fetchone()
                return JobRecord.from_row(dict(job_row))
            finally:
                conn.close()

    def get_job(self, job_id: str) -> JobRecord | None:
        """Retrieve a job by ID."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM jobs WHERE id = :job_id"),
                {"job_id": job_id},
            ).mappings().fetchone()
            return JobRecord.from_row(dict(row)) if row else None

    def claim_next_job(
        self,
        worker_id: str,
        lease_seconds: int = 90,
    ) -> JobRecord | None:
        """Atomically claim the next queued job with a fresh fencing token."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        lease_expires_str = (now + timedelta(seconds=lease_seconds)).isoformat()
        fencing_token = uuid4().hex

        if self.is_sqlite:
            # SQLite: acquire immediate lock and claim conditionally
            with self.engine.begin() as conn:
                conn.execute(text("BEGIN IMMEDIATE"))
                candidate = conn.execute(
                    text("""
                        SELECT id, attempt, max_attempts FROM jobs
                        WHERE status = 'queued' AND cancel_requested = :not_cancelled
                        ORDER BY created_at ASC, id ASC
                        LIMIT 1
                    """),
                    {"not_cancelled": False},
                ).mappings().fetchone()

                if not candidate:
                    return None

                job_id = candidate["id"]
                new_attempt = int(candidate["attempt"]) + 1

                res = conn.execute(
                    text("""
                        UPDATE jobs SET
                            status = 'running',
                            worker_id = :worker_id,
                            fencing_token = :fencing_token,
                            attempt = :attempt,
                            lease_expires_at = :lease_expires_at,
                            heartbeat_at = :heartbeat_at,
                            started_at = COALESCE(started_at, :started_at)
                        WHERE id = :job_id AND status = 'queued'
                    """),
                    {
                        "worker_id": worker_id,
                        "fencing_token": fencing_token,
                        "attempt": new_attempt,
                        "lease_expires_at": lease_expires_str,
                        "heartbeat_at": now_str,
                        "started_at": now_str,
                        "job_id": job_id,
                    },
                )
                if res.rowcount == 0:
                    return None

                conn.execute(
                    text("""
                        INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                        VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                    """),
                    {
                        "job_id": job_id,
                        "event_type": JobEventType.CLAIMED.value,
                        "fencing_token": fencing_token,
                        "details_json": json.dumps({"worker_id": worker_id, "attempt": new_attempt}),
                        "created_at": now_str,
                    },
                )

                job_row = conn.execute(
                    text("SELECT * FROM jobs WHERE id = :job_id"),
                    {"job_id": job_id},
                ).mappings().fetchone()
                return JobRecord.from_row(dict(job_row))
        else:
            # PostgreSQL: SELECT ... FOR UPDATE SKIP LOCKED
            with self.engine.begin() as conn:
                candidate = conn.execute(
                    text("""
                        SELECT id, attempt, max_attempts FROM jobs
                        WHERE status = 'queued' AND cancel_requested = :not_cancelled
                        ORDER BY created_at ASC, id ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    """),
                    {"not_cancelled": False},
                ).mappings().fetchone()

                if not candidate:
                    return None

                job_id = candidate["id"]
                new_attempt = int(candidate["attempt"]) + 1

                res = conn.execute(
                    text("""
                        UPDATE jobs SET
                            status = 'running',
                            worker_id = :worker_id,
                            fencing_token = :fencing_token,
                            attempt = :attempt,
                            lease_expires_at = :lease_expires_at,
                            heartbeat_at = :heartbeat_at,
                            started_at = COALESCE(started_at, :started_at)
                        WHERE id = :job_id AND status = 'queued'
                    """),
                    {
                        "worker_id": worker_id,
                        "fencing_token": fencing_token,
                        "attempt": new_attempt,
                        "lease_expires_at": lease_expires_str,
                        "heartbeat_at": now_str,
                        "started_at": now_str,
                        "job_id": job_id,
                    },
                )
                if res.rowcount == 0:
                    return None

                conn.execute(
                    text("""
                        INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                        VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                    """),
                    {
                        "job_id": job_id,
                        "event_type": JobEventType.CLAIMED.value,
                        "fencing_token": fencing_token,
                        "details_json": json.dumps({"worker_id": worker_id, "attempt": new_attempt}),
                        "created_at": now_str,
                    },
                )

                job_row = conn.execute(
                    text("SELECT * FROM jobs WHERE id = :job_id"),
                    {"job_id": job_id},
                ).mappings().fetchone()
                return JobRecord.from_row(dict(job_row))

    def heartbeat(
        self,
        job_id: str,
        fencing_token: str,
        lease_seconds: int = 90,
    ) -> bool:
        """Extend lease for an active worker if fencing token matches, lease has not expired, and cancellation not requested."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        lease_expires_str = (now + timedelta(seconds=lease_seconds)).isoformat()

        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE jobs SET
                        heartbeat_at = :heartbeat_at,
                        lease_expires_at = :lease_expires_at
                    WHERE id = :job_id 
                      AND fencing_token = :fencing_token 
                      AND status = 'running'
                      AND cancel_requested = :not_cancelled
                      AND lease_expires_at >= :heartbeat_at
                """),
                {
                    "heartbeat_at": now_str,
                    "lease_expires_at": lease_expires_str,
                    "job_id": job_id,
                    "fencing_token": fencing_token,
                    "not_cancelled": False,
                },
            )
            if result.rowcount > 0:
                conn.execute(
                    text("""
                        INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                        VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                    """),
                    {
                        "job_id": job_id,
                        "event_type": JobEventType.HEARTBEAT.value,
                        "fencing_token": fencing_token,
                        "details_json": json.dumps({"lease_expires_at": lease_expires_str}),
                        "created_at": now_str,
                    },
                )
                return True
            return False

    def is_cancellation_requested(self, job_id: str, fencing_token: str) -> bool:
        """Check if cancellation has been requested for this running job/token."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT cancel_requested FROM jobs WHERE id = :job_id AND fencing_token = :fencing_token"),
                {"job_id": job_id, "fencing_token": fencing_token},
            ).fetchone()
            if row:
                return bool(row[0])
            return False

    def request_cancellation(self, job_id: str, session_id: str | None = None) -> tuple[bool, str]:
        """Request cancellation for a job, optionally enforcing session ownership.
        
        Returns: (success: bool, resolution: str)
          - (True, "cancelled") if was queued and cancelled immediately.
          - (True, "cancel_requested") if currently running.
          - (False, "forbidden") if caller session does not own the job.
          - (False, "terminal") if already completed, failed, or cancelled.
        """
        now = utc_now_str()
        with self.engine.begin() as conn:
            for _ in range(3):
                row = conn.execute(
                    text("SELECT status, session_id, cancel_requested FROM jobs WHERE id = :job_id"),
                    {"job_id": job_id},
                ).mappings().fetchone()

                if not row:
                    return False, "not_found"

                if row["session_id"]:
                    if not session_id or row["session_id"] != session_id:
                        return False, "forbidden"

                status = row["status"]
                if status == JobStatus.QUEUED.value:
                    # Cancel immediately
                    res = conn.execute(
                        text("""
                            UPDATE jobs SET
                                status = 'cancelled',
                                cancel_requested = :cancel_requested,
                                completed_at = :now
                            WHERE id = :job_id AND status = 'queued'
                        """),
                        {"job_id": job_id, "cancel_requested": True, "now": now},
                    )
                    if res.rowcount > 0:
                        conn.execute(
                            text("""
                                INSERT INTO job_events (job_id, event_type, created_at)
                                VALUES (:job_id, :event_type, :created_at)
                            """),
                            {
                                "job_id": job_id,
                                "event_type": JobEventType.CANCELLED.value,
                                "created_at": now,
                            },
                        )
                        return True, "cancelled"
                    # Lost update race to worker claim; recheck status
                    continue
                elif status == JobStatus.RUNNING.value:
                    if row["cancel_requested"]:
                        return True, "cancel_requested"
                    res = conn.execute(
                        text("UPDATE jobs SET cancel_requested = :cancel_requested WHERE id = :job_id AND status = 'running'"),
                        {"job_id": job_id, "cancel_requested": True},
                    )
                    if res.rowcount > 0:
                        conn.execute(
                            text("""
                                INSERT INTO job_events (job_id, event_type, created_at)
                                VALUES (:job_id, :event_type, :created_at)
                            """),
                            {
                                "job_id": job_id,
                                "event_type": JobEventType.CANCEL_REQUESTED.value,
                                "created_at": now,
                            },
                        )
                        return True, "cancel_requested"
                    # Lost race to job completion/failure; recheck status
                    continue
                else:
                    return False, "terminal"
            return False, "terminal"

    def mark_completed(
        self,
        job_id: str,
        fencing_token: str,
        experiment_id: str,
        result_data: dict[str, Any],
    ) -> bool:
        """Mark job completed under matching fencing token if lease is valid and not cancelled."""
        now = utc_now_str()
        with self.engine.begin() as conn:
            res = conn.execute(
                text("""
                    UPDATE jobs SET
                        status = 'completed',
                        experiment_id = :experiment_id,
                        result_json = :result_json,
                        completed_at = :completed_at
                    WHERE id = :job_id 
                      AND fencing_token = :fencing_token 
                      AND status = 'running'
                      AND cancel_requested = :not_cancelled
                      AND lease_expires_at >= :completed_at
                """),
                {
                    "experiment_id": experiment_id,
                    "result_json": json.dumps(result_data, ensure_ascii=False),
                    "completed_at": now,
                    "job_id": job_id,
                    "fencing_token": fencing_token,
                    "not_cancelled": False,
                },
            )
            if res.rowcount > 0:
                conn.execute(
                    text("""
                        INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                        VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                    """),
                    {
                        "job_id": job_id,
                        "event_type": JobEventType.COMPLETED.value,
                        "fencing_token": fencing_token,
                        "details_json": json.dumps({"experiment_id": experiment_id}),
                        "created_at": now,
                    },
                )
                return True

            # Check if job was already marked completed in the atomic publication transaction
            already = conn.execute(
                text("""
                    SELECT id FROM jobs
                    WHERE id = :job_id
                      AND fencing_token = :fencing_token
                      AND status = 'completed'
                      AND experiment_id = :experiment_id
                """),
                {
                    "job_id": job_id,
                    "fencing_token": fencing_token,
                    "experiment_id": experiment_id,
                },
            ).fetchone()
            if already:
                conn.execute(
                    text("""
                        UPDATE jobs SET result_json = COALESCE(result_json, :result_json)
                        WHERE id = :job_id AND fencing_token = :fencing_token
                    """),
                    {
                        "job_id": job_id,
                        "fencing_token": fencing_token,
                        "result_json": json.dumps(result_data, ensure_ascii=False),
                    },
                )
                return True
            return False

    def mark_cancelled_by_worker(
        self,
        job_id: str,
        fencing_token: str,
    ) -> bool:
        """Mark job cancelled by the executing worker upon cooperative cancellation check."""
        now = utc_now_str()
        with self.engine.begin() as conn:
            res = conn.execute(
                text("""
                    UPDATE jobs SET
                        status = 'cancelled',
                        completed_at = :completed_at
                    WHERE id = :job_id 
                      AND fencing_token = :fencing_token 
                      AND status = 'running'
                      AND lease_expires_at >= :completed_at
                """),
                {
                    "completed_at": now,
                    "job_id": job_id,
                    "fencing_token": fencing_token,
                },
            )
            if res.rowcount > 0:
                conn.execute(
                    text("""
                        INSERT INTO job_events (job_id, event_type, fencing_token, created_at)
                        VALUES (:job_id, :event_type, :fencing_token, :created_at)
                    """),
                    {
                        "job_id": job_id,
                        "event_type": JobEventType.CANCELLED.value,
                        "fencing_token": fencing_token,
                        "created_at": now,
                    },
                )
                return True
            return False

    def record_stage(
        self,
        job_id: str,
        fencing_token: str,
        stage: JobEventType,
        details: dict[str, Any] | None = None,
    ) -> bool:
        """Record stage transition event if lease valid and not cancelled."""
        now = utc_now_str()
        with self.engine.begin() as conn:
            res = conn.execute(
                text("""
                    UPDATE jobs SET
                        heartbeat_at = :now
                    WHERE id = :job_id 
                      AND fencing_token = :fencing_token 
                      AND status = 'running'
                      AND cancel_requested = :not_cancelled
                      AND lease_expires_at >= :now
                """),
                {
                    "job_id": job_id,
                    "fencing_token": fencing_token,
                    "now": now,
                    "not_cancelled": False,
                },
            )
            if res.rowcount > 0:
                conn.execute(
                    text("""
                        INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                        VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                    """),
                    {
                        "job_id": job_id,
                        "event_type": stage.value,
                        "fencing_token": fencing_token,
                        "details_json": json.dumps(details or {}, ensure_ascii=False),
                        "created_at": now,
                    },
                )
                return True
            return False

    def mark_failed(
        self,
        job_id: str,
        fencing_token: str,
        error_envelope: dict[str, Any],
        retryable: bool = False,
    ) -> bool:
        """Mark job failed or requeue if retryable and attempts remain."""
        now = utc_now_str()
        with self.engine.begin() as conn:
            job = conn.execute(
                text("SELECT attempt, max_attempts FROM jobs WHERE id = :job_id AND fencing_token = :fencing_token"),
                {"job_id": job_id, "fencing_token": fencing_token},
            ).mappings().fetchone()

            if not job:
                return False

            attempt = int(job["attempt"])
            max_attempts = int(job["max_attempts"])

            if retryable and attempt < max_attempts:
                # Requeue
                res = conn.execute(
                    text("""
                        UPDATE jobs SET
                            status = 'queued',
                            worker_id = NULL,
                            fencing_token = NULL,
                            lease_expires_at = NULL,
                            heartbeat_at = NULL,
                            error_json = :error_json
                        WHERE id = :job_id 
                          AND fencing_token = :fencing_token 
                          AND status = 'running'
                          AND lease_expires_at >= :now
                    """),
                    {
                        "error_json": json.dumps(error_envelope, ensure_ascii=False),
                        "job_id": job_id,
                        "fencing_token": fencing_token,
                        "now": now,
                    },
                )
                if res.rowcount > 0:
                    conn.execute(
                        text("""
                            INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                            VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                        """),
                        {
                            "job_id": job_id,
                            "event_type": JobEventType.REQUEUED.value,
                            "fencing_token": fencing_token,
                            "details_json": json.dumps(error_envelope),
                            "created_at": now,
                        },
                    )
                    return True
                return False
            else:
                # Terminal failure
                res = conn.execute(
                    text("""
                        UPDATE jobs SET
                            status = 'failed',
                            error_json = :error_json,
                            completed_at = :completed_at
                        WHERE id = :job_id 
                          AND fencing_token = :fencing_token 
                          AND status = 'running'
                          AND lease_expires_at >= :completed_at
                    """),
                    {
                        "error_json": json.dumps(error_envelope, ensure_ascii=False),
                        "completed_at": now,
                        "job_id": job_id,
                        "fencing_token": fencing_token,
                    },
                )
                if res.rowcount > 0:
                    conn.execute(
                        text("""
                            INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                            VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                        """),
                        {
                            "job_id": job_id,
                            "event_type": JobEventType.FAILED.value,
                            "fencing_token": fencing_token,
                            "details_json": json.dumps(error_envelope),
                            "created_at": now,
                        },
                    )
                    return True
                return False
