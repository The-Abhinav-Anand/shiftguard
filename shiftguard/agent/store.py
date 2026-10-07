"""Durable database store for Gate 6 agent requests, tool executions, and continuation receipts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from shiftguard.agent.policy import APPROVED_PRESETS, APPROVED_STRESS_SUITES
from shiftguard.jobs.models import JobRecord, JobStatus, utc_now_str


class IdempotencyConflictError(Exception):
    """Raised when an intent key is submitted with a different request payload."""


class LeaseLostError(RuntimeError):
    """Raised when a fenced request write no longer owns the active lease."""


class RequestAuthorityError(RuntimeError):
    """Raised when the request's original active-session authority is absent or changed."""


class InvalidContinuationNonce(RuntimeError):
    """Raised when a resume nonce was not issued for this request/session generation."""


_UNSET = object()


@dataclass(frozen=True)
class AgentRequestRecord:
    id: str
    session_id: str
    intent_key: str
    canonical_body_hash: str
    prompt: str
    status: str
    generation: int
    lease_expires_at: str | None
    worker_id: str | None
    turn_count: int
    call_count: int
    repair_count: int
    active_job_id: str | None
    active_tool_call_id: str | None
    active_nonce: str | None
    active_nonce_generation: int | None
    authority_token_hash: str | None
    accepted_decision: dict[str, Any] | None
    pending_cursor: int
    repair_ledger: dict[str, int]
    pending_tool_calls: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    evidence_refs: list[str]
    final_response: dict[str, Any] | None
    error: dict[str, Any] | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AgentRequestRecord:
        msgs_raw = row.get("messages_json")
        msgs = json.loads(msgs_raw) if isinstance(msgs_raw, str) and msgs_raw else []
        refs_raw = row.get("evidence_refs_json")
        refs = json.loads(refs_raw) if isinstance(refs_raw, str) and refs_raw else []
        final_raw = row.get("final_response_json")
        final = json.loads(final_raw) if isinstance(final_raw, str) and final_raw else None
        err_raw = row.get("error_json")
        err = json.loads(err_raw) if isinstance(err_raw, str) and err_raw else None
        repairs_raw = row.get("repair_ledger_json")
        repairs = json.loads(repairs_raw) if isinstance(repairs_raw, str) and repairs_raw else {}
        pending_raw = row.get("pending_tool_calls_json")
        pending = json.loads(pending_raw) if isinstance(pending_raw, str) and pending_raw else []
        decision_raw = row.get("accepted_decision_json")
        decision = json.loads(decision_raw) if isinstance(decision_raw, str) and decision_raw else None

        return cls(
            id=row["id"],
            session_id=row["session_id"],
            intent_key=row["intent_key"],
            canonical_body_hash=row["canonical_body_hash"],
            prompt=row["prompt"],
            status=row["status"],
            generation=int(row["generation"]),
            lease_expires_at=row.get("lease_expires_at"),
            worker_id=row.get("worker_id"),
            turn_count=int(row.get("turn_count", 0)),
            call_count=int(row.get("call_count", 0)),
            repair_count=int(row.get("repair_count", 0)),
            active_job_id=row.get("active_job_id"),
            active_tool_call_id=row.get("active_tool_call_id"),
            active_nonce=row.get("active_nonce"),
            active_nonce_generation=(int(row["active_nonce_generation"]) if row.get("active_nonce_generation") is not None else None),
            authority_token_hash=row.get("authority_token_hash"),
            accepted_decision=decision,
            pending_cursor=int(row.get("pending_cursor") or 0),
            repair_ledger=repairs,
            pending_tool_calls=pending,
            messages=msgs,
            evidence_refs=refs,
            final_response=final,
            error=err,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass(frozen=True)
class AgentToolExecutionRecord:
    id: str
    request_id: str
    ordinal: int
    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    status: str
    idempotency_key: str
    job_id: str | None
    result: dict[str, Any] | None
    created_at: str
    completed_at: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AgentToolExecutionRecord:
        args_raw = row.get("arguments_json")
        args = json.loads(args_raw) if isinstance(args_raw, str) and args_raw else {}
        res_raw = row.get("result_json")
        res = json.loads(res_raw) if isinstance(res_raw, str) and res_raw else None

        return cls(
            id=row["id"],
            request_id=row["request_id"],
            ordinal=int(row["ordinal"]),
            tool_name=row["tool_name"],
            tool_call_id=row["tool_call_id"],
            arguments=args,
            status=row["status"],
            idempotency_key=row["idempotency_key"],
            job_id=row.get("job_id"),
            result=res,
            created_at=row["created_at"],
            completed_at=row.get("completed_at"),
        )


@dataclass(frozen=True)
class AgentContinuationReceiptRecord:
    id: str
    request_id: str
    nonce: str
    status_code: int
    response: dict[str, Any]
    created_at: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AgentContinuationReceiptRecord:
        resp_raw = row.get("response_json")
        resp = json.loads(resp_raw) if isinstance(resp_raw, str) and resp_raw else {}
        return cls(
            id=row["id"],
            request_id=row["request_id"],
            nonce=row["nonce"],
            status_code=int(row["status_code"]),
            response=resp,
            created_at=row["created_at"],
        )


class AgentStore:
    """Atomic repository for agent durable persistence on SQLite and PostgreSQL."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def authority_hash(session_token: str | None) -> str | None:
        if not session_token or not session_token.strip():
            return None
        return hashlib.sha256(session_token.strip().encode("utf-8")).hexdigest()

    @contextmanager
    def _write_connection(self):
        conn = self.engine.connect()
        try:
            if self.engine.dialect.name == "sqlite":
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
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _owned_request(
        self,
        conn: Any,
        request_id: str,
        expected_generation: int,
        worker_id: str,
        session_token: str | None = None,
        require_authority: bool = False,
        require_bound_authority: bool = False,
    ) -> dict[str, Any]:
        # PostgreSQL lock order is session, then request, then queue/idempotency.
        preview = conn.execute(
            text("SELECT session_id FROM agent_requests WHERE id = :id"), {"id": request_id}
        ).mappings().fetchone()
        if not preview:
            raise LeaseLostError(f"Request '{request_id}' no longer exists")
        session = None
        if require_authority or require_bound_authority:
            session_sql = "SELECT status, capability_token FROM agent_sessions WHERE id = :id"
            if self.engine.dialect.name == "postgresql":
                session_sql += " FOR UPDATE"
            session = conn.execute(text(session_sql), {"id": preview["session_id"]}).mappings().fetchone()
            if not session or str(session["status"]).upper() != "ACTIVE":
                raise RequestAuthorityError("The request session is no longer active")

        request_sql = "SELECT * FROM agent_requests WHERE id = :id"
        if self.engine.dialect.name == "postgresql":
            request_sql += " FOR UPDATE"
        row = conn.execute(text(request_sql), {"id": request_id}).mappings().fetchone()
        if not row:
            raise LeaseLostError(f"Request '{request_id}' no longer exists")
        now = utc_now_str()
        if (
            int(row["generation"]) != expected_generation
            or row["worker_id"] != worker_id
            or ((require_authority or require_bound_authority) and row["session_id"] != preview["session_id"])
            or not row["lease_expires_at"]
            or row["lease_expires_at"] <= now
        ):
            raise LeaseLostError(f"Request '{request_id}' lease ownership was lost")
        if require_authority or require_bound_authority:
            # Read the immutable binding from the locked request, with the
            # session held first. A trusted lease owner still cannot publish
            # success after the browser capability has expired or rotated.
            stored_hash = row["authority_token_hash"]
            current_hash = self.authority_hash(session["capability_token"])
            if not stored_hash or not current_hash or not hmac.compare_digest(stored_hash, current_hash):
                raise RequestAuthorityError("The request's bound session authority is no longer current")
            if require_authority:
                supplied_hash = self.authority_hash(session_token)
                if not supplied_hash or not hmac.compare_digest(supplied_hash, stored_hash):
                    raise RequestAuthorityError("The request is not bound to the supplied session authority")
        return dict(row)

    def create_or_get_request(
        self,
        session_id: str,
        intent_key: str,
        canonical_body_hash: str,
        prompt: str,
        initial_messages: list[dict[str, Any]] | None = None,
        authority_token_hash: str | None = None,
    ) -> tuple[AgentRequestRecord, bool]:
        """Create new agent request or return existing matching request.

        Raises IdempotencyConflictError if intent_key exists with a different canonical_body_hash.
        Handles concurrent race conditions safely without raising raw IntegrityError.
        """
        now = utc_now_str()
        req_id = f"req_{uuid4().hex[:20]}"
        msgs_json = json.dumps(initial_messages or [])

        # Check existing first
        existing = self.get_request_by_session_and_intent(session_id, intent_key)
        if existing:
            if existing.canonical_body_hash != canonical_body_hash:
                raise IdempotencyConflictError(
                    f"Intent key '{intent_key}' already used with different payload."
                )
            return existing, False

        # Attempt insert with conflict handling
        insert_stmt = text(
            """
            INSERT INTO agent_requests (
                id, session_id, intent_key, canonical_body_hash, prompt,
                status, generation, turn_count, call_count, repair_count,
                repair_ledger_json, pending_tool_calls_json, active_nonce_generation,
                accepted_decision_json, pending_cursor, authority_token_hash,
                messages_json, evidence_refs_json, created_at, updated_at
            ) VALUES (
                :id, :session_id, :intent_key, :canonical_body_hash, :prompt,
                'RUNNING', 1, 0, 0, 0,
                '{}', '[]', NULL, NULL, 0, :authority_token_hash,
                :messages_json, '[]', :created_at, :updated_at
            )
            """
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    insert_stmt,
                    {
                        "id": req_id,
                        "session_id": session_id,
                        "intent_key": intent_key,
                        "canonical_body_hash": canonical_body_hash,
                        "prompt": prompt,
                        "authority_token_hash": authority_token_hash,
                        "messages_json": msgs_json,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
        except IntegrityError:
            # Concurrent insert won race: load winner record
            winner = self.get_request_by_session_and_intent(session_id, intent_key)
            if winner:
                if winner.canonical_body_hash != canonical_body_hash:
                    raise IdempotencyConflictError(
                        f"Intent key '{intent_key}' already used with different payload."
                    )
                return winner, False
            raise

        req = self.get_request(req_id)
        if not req:
            raise RuntimeError(f"Failed to load newly created request '{req_id}'")
        return req, True

    create_request = create_or_get_request

    def get_request(self, request_id: str) -> AgentRequestRecord | None:
        with self.engine.connect() as conn:
            stmt = text("SELECT * FROM agent_requests WHERE id = :id")
            row = conn.execute(stmt, {"id": request_id}).mappings().fetchone()
            return AgentRequestRecord.from_row(dict(row)) if row else None

    def get_request_by_session_and_intent(self, session_id: str, intent_key: str) -> AgentRequestRecord | None:
        with self.engine.connect() as conn:
            stmt = text(
                "SELECT * FROM agent_requests WHERE session_id = :sid AND intent_key = :ikey"
            )
            row = conn.execute(stmt, {"sid": session_id, "ikey": intent_key}).mappings().fetchone()
            return AgentRequestRecord.from_row(dict(row)) if row else None

    def verify_request_authority(self, request_id: str, session_token: str | None) -> bool:
        request = self.get_request(request_id)
        if not request or not request.authority_token_hash or not session_token:
            return False
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT status, capability_token FROM agent_sessions WHERE id = :id
            """), {"id": request.session_id}).mappings().fetchone()
        supplied = self.authority_hash(session_token)
        current = self.authority_hash(row["capability_token"]) if row else None
        return bool(
            row and str(row["status"]).upper() == "ACTIVE" and supplied and current
            and hmac.compare_digest(supplied, current)
            and hmac.compare_digest(supplied, request.authority_token_hash)
        )

    def bind_legacy_request_authority(
        self, request_id: str, session_id: str, session_token: str | None,
    ) -> AgentRequestRecord | None:
        """Bind an unbound pre-0010 request only when its active session authenticates it.

        This is intentionally request-time rather than migration-time: old rows do not
        contain enough information to infer which current capability, if any, remains
        authorized. The session and request are locked in the same order used by fenced
        writes, and only the NULL hash is ever filled.
        """
        supplied_hash = self.authority_hash(session_token)
        if not request_id or not session_id or not supplied_hash:
            return None

        with self._write_connection() as conn:
            preview = conn.execute(
                text("SELECT session_id FROM agent_requests WHERE id = :id"),
                {"id": request_id},
            ).mappings().fetchone()
            if not preview or preview["session_id"] != session_id:
                return None

            session_sql = "SELECT status, capability_token FROM agent_sessions WHERE id = :id"
            request_sql = "SELECT * FROM agent_requests WHERE id = :id"
            if self.engine.dialect.name == "postgresql":
                session_sql += " FOR UPDATE"
                request_sql += " FOR UPDATE"
            session = conn.execute(text(session_sql), {"id": session_id}).mappings().fetchone()
            if (
                not session
                or str(session["status"]).upper() != "ACTIVE"
                or not session["capability_token"]
            ):
                return None
            current_hash = self.authority_hash(session["capability_token"])
            if not current_hash or not hmac.compare_digest(supplied_hash, current_hash):
                return None

            row = conn.execute(text(request_sql), {"id": request_id}).mappings().fetchone()
            if not row or row["session_id"] != session_id:
                return None
            if row["status"] not in {"RUNNING", "WAITING_FOR_JOB", "COMPLETED", "FAILED", "CANCELLED"}:
                return None
            stored_hash = row.get("authority_token_hash")
            if stored_hash is not None:
                if not hmac.compare_digest(supplied_hash, stored_hash):
                    return None
                return AgentRequestRecord.from_row(dict(row))

            result = conn.execute(text("""
                UPDATE agent_requests
                SET authority_token_hash = :authority_hash
                WHERE id = :id AND session_id = :session_id
                  AND authority_token_hash IS NULL
            """), {
                "authority_hash": supplied_hash,
                "id": request_id,
                "session_id": session_id,
            })
            if result.rowcount != 1:
                return None
            updated = conn.execute(text(request_sql), {"id": request_id}).mappings().fetchone()
            return AgentRequestRecord.from_row(dict(updated)) if updated else None

    def claim_lease(
        self,
        request_id: str,
        worker_id: str,
        lease_seconds: int = 60,
    ) -> tuple[bool, AgentRequestRecord | None]:
        """Atomically claim execution lease using CAS generation increment.

        Succeeds if current lease has expired, is unassigned, or belongs to the same worker.
        """
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        expires_str = (now + timedelta(seconds=lease_seconds)).isoformat()

        with self._write_connection() as conn:
            stmt = text("SELECT * FROM agent_requests WHERE id = :id")
            if self.engine.dialect.name == "postgresql":
                stmt = text("SELECT * FROM agent_requests WHERE id = :id FOR UPDATE")
            row = conn.execute(stmt, {"id": request_id}).mappings().fetchone()
            if not row:
                return False, None

            req = AgentRequestRecord.from_row(dict(row))
            if req.status in ("COMPLETED", "FAILED", "CANCELLED"):
                return False, req

            # Check if lease is claimable
            current_expiry = req.lease_expires_at
            is_expired = current_expiry is None or current_expiry < now_str
            is_same_worker = req.worker_id == worker_id

            if not (is_expired or is_same_worker):
                return False, req

            update_stmt = text(
                """
                UPDATE agent_requests
                SET generation = generation + 1,
                    worker_id = :worker_id,
                    lease_expires_at = :expires_at,
                    updated_at = :now
                WHERE id = :id AND generation = :expected_gen
                  AND (lease_expires_at IS NULL OR lease_expires_at <= :now OR worker_id = :worker_id)
                """
            )
            res = conn.execute(
                update_stmt,
                {
                    "worker_id": worker_id,
                    "expires_at": expires_str,
                    "now": now_str,
                    "id": request_id,
                    "expected_gen": req.generation,
                },
            )
            if res.rowcount != 1:
                # Concurrent update conflict
                return False, None

        updated_req = self.get_request(request_id)
        return True, updated_req

    def release_lease(self, request_id: str, expected_generation: int, worker_id: str | None = None) -> bool:
        """Release execution lease so another worker (or HTTP resume) can claim without waiting."""
        now = utc_now_str()
        worker_clause = ""
        params: dict[str, Any] = {"id": request_id, "expected_gen": expected_generation, "now": now}
        if worker_id is not None:
            worker_clause = "AND worker_id = :worker_id"
            params["worker_id"] = worker_id
        stmt = text(
            """
            UPDATE agent_requests
            SET worker_id = NULL,
                lease_expires_at = NULL,
                updated_at = :now
            WHERE id = :id AND generation = :expected_gen
              AND (lease_expires_at IS NULL OR lease_expires_at >= :now)
              """ + worker_clause + """
            """
        )
        with self._write_connection() as conn:
            res = conn.execute(stmt, params)
            return res.rowcount == 1

    def verify_lease(
        self,
        request_id: str,
        expected_generation: int,
        worker_id: str,
    ) -> tuple[bool, AgentRequestRecord | None]:
        """Verify that worker currently holds an unexpired lease for the given generation."""
        now_str = utc_now_str()
        req = self.get_request(request_id)
        if not req:
            return False, None
        if req.generation != expected_generation:
            return False, req
        if req.worker_id != worker_id:
            return False, req
        if not req.lease_expires_at or req.lease_expires_at <= now_str:
            return False, req
        return True, req

    def renew_lease(
        self,
        request_id: str,
        expected_generation: int,
        worker_id: str,
        lease_seconds: int = 120,
    ) -> bool:
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        expires = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._write_connection() as conn:
            res = conn.execute(
                text("""
                    UPDATE agent_requests
                    SET lease_expires_at = :expires, updated_at = :now
                    WHERE id = :id AND generation = :generation AND worker_id = :worker
                      AND lease_expires_at IS NOT NULL AND lease_expires_at > :now
                      AND status IN ('RUNNING', 'WAITING_FOR_JOB')
                """),
                {"id": request_id, "generation": expected_generation, "worker": worker_id,
                 "expires": expires, "now": now_str},
            )
            return res.rowcount == 1

    def update_request(
        self,
        request_id: str,
        expected_generation: int,
        status: str | None = None,
        turn_count: int | None = None,
        call_count: int | None = None,
        repair_count: int | None = None,
        active_job_id: str | None = None,
        active_tool_call_id: str | None = None,
        active_nonce: str | None = None,
        repair_ledger: dict[str, int] | None = None,
        pending_tool_calls: list[dict[str, Any]] | None = None,
        messages: list[dict[str, Any]] | None = None,
        evidence_refs: list[str] | None = None,
        final_response: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        worker_id: str | None = None,
        accepted_decision: Any = _UNSET,
        pending_cursor: int | None = None,
        active_nonce_generation: int | None | object = _UNSET,
        clear_error: bool = False,
    ) -> bool:
        """Atomically update request state conditional on generation match and unexpired lease."""
        now = utc_now_str()
        updates = ["updated_at = :now"]
        params: dict[str, Any] = {
            "id": request_id,
            "expected_gen": expected_generation,
            "now": now,
        }

        if status is not None:
            updates.append("status = :status")
            params["status"] = status
        if turn_count is not None:
            updates.append("turn_count = :turn_count")
            params["turn_count"] = turn_count
        if call_count is not None:
            updates.append("call_count = :call_count")
            params["call_count"] = call_count
        if repair_count is not None:
            updates.append("repair_count = :repair_count")
            params["repair_count"] = repair_count
        if active_job_id is not None:
            updates.append("active_job_id = :active_job_id")
            params["active_job_id"] = active_job_id if active_job_id != "" else None
        if active_tool_call_id is not None:
            updates.append("active_tool_call_id = :active_tool_call_id")
            params["active_tool_call_id"] = active_tool_call_id if active_tool_call_id != "" else None
        if active_nonce is not None:
            updates.append("active_nonce = :active_nonce")
            params["active_nonce"] = active_nonce if active_nonce != "" else None
        if active_nonce_generation is not _UNSET:
            updates.append("active_nonce_generation = :active_nonce_generation")
            params["active_nonce_generation"] = active_nonce_generation
        if accepted_decision is not _UNSET:
            updates.append("accepted_decision_json = :accepted_decision_json")
            params["accepted_decision_json"] = (
                json.dumps(accepted_decision, ensure_ascii=False) if accepted_decision is not None else None
            )
        if pending_cursor is not None:
            updates.append("pending_cursor = :pending_cursor")
            params["pending_cursor"] = pending_cursor
        if repair_ledger is not None:
            updates.append("repair_ledger_json = :repair_ledger_json")
            params["repair_ledger_json"] = json.dumps(repair_ledger)
        if pending_tool_calls is not None:
            updates.append("pending_tool_calls_json = :pending_tool_calls_json")
            params["pending_tool_calls_json"] = json.dumps(pending_tool_calls)
        if messages is not None:
            updates.append("messages_json = :messages_json")
            params["messages_json"] = json.dumps(messages)
        if evidence_refs is not None:
            updates.append("evidence_refs_json = :evidence_refs_json")
            params["evidence_refs_json"] = json.dumps(evidence_refs)
        if final_response is not None:
            updates.append("final_response_json = :final_response_json")
            params["final_response_json"] = json.dumps(final_response)
        if error is not None:
            updates.append("error_json = :error_json")
            params["error_json"] = json.dumps(error, ensure_ascii=False)
        elif clear_error:
            updates.append("error_json = NULL")

        worker_clause = ""
        if worker_id is not None:
            worker_clause = "AND worker_id = :worker_id AND lease_expires_at IS NOT NULL AND lease_expires_at > :now"
            params["worker_id"] = worker_id

        set_clause = ", ".join(updates)
        stmt = text(
            f"""
            UPDATE agent_requests
            SET {set_clause}
            WHERE id = :id AND generation = :expected_gen
              AND (lease_expires_at IS NULL OR lease_expires_at >= :now)
              {worker_clause}
            """
        )

        with self._write_connection() as conn:
            res = conn.execute(stmt, params)
            return res.rowcount == 1

    def record_tool_execution(
        self,
        request_id: str,
        ordinal: int,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
        idempotency_key: str,
        status: str = "PENDING",
        job_id: str | None = None,
        expected_generation: int | None = None,
        worker_id: str | None = None,
        session_token: str | None = None,
        decision_index: int | None = None,
        call_count: int | None = None,
        repair_ledger: dict[str, int] | None = None,
        repair_count: int | None = None,
    ) -> AgentToolExecutionRecord:
        """Persist an immutable tool intent and its budget reservation under the lease."""
        now = utc_now_str()
        exec_id = f"ate_{uuid4().hex[:20]}"
        arguments_json = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        with self._write_connection() as conn:
            if expected_generation is not None and worker_id is not None:
                req_row = self._owned_request(
                    conn, request_id, expected_generation, worker_id,
                    session_token, bool(session_token),
                )
                if decision_index is not None:
                    decision = json.loads(req_row["accepted_decision_json"] or "null")
                    calls = decision.get("tool_calls", []) if isinstance(decision, dict) else []
                    if int(req_row["pending_cursor"] or 0) != decision_index or decision_index >= len(calls):
                        raise LeaseLostError("Accepted tool cursor changed before intent persistence")
                    accepted = calls[decision_index]
                    if accepted.get("id") != tool_call_id or accepted.get("name") != tool_name:
                        raise IdempotencyConflictError("Tool intent does not match the saved provider decision")
                    if accepted.get("arguments") != arguments:
                        raise IdempotencyConflictError("Tool arguments do not match the saved provider decision")

            select = text("""
                SELECT * FROM agent_tool_executions
                WHERE request_id = :request_id AND ordinal = :ordinal
            """)
            existing = conn.execute(select, {"request_id": request_id, "ordinal": ordinal}).mappings().fetchone()
            if existing:
                same = (
                    existing["tool_name"] == tool_name
                    and existing["tool_call_id"] == tool_call_id
                    and json.loads(existing["arguments_json"] or "{}") == arguments
                    and existing["idempotency_key"] == idempotency_key
                )
                if not same:
                    raise IdempotencyConflictError("Saved ordinal conflicts with the accepted immutable tool intent")
                record = AgentToolExecutionRecord.from_row(dict(existing))
            else:
                conn.execute(text("""
                    INSERT INTO agent_tool_executions (
                        id, request_id, ordinal, tool_name, tool_call_id,
                        arguments_json, status, idempotency_key, job_id, created_at
                    ) VALUES (
                        :id, :request_id, :ordinal, :tool_name, :tool_call_id,
                        :arguments_json, :status, :idempotency_key, :job_id, :created_at
                    )
                """), {
                    "id": exec_id,
                    "request_id": request_id,
                    "ordinal": ordinal,
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "arguments_json": arguments_json,
                    "status": status,
                    "idempotency_key": idempotency_key,
                    "job_id": job_id,
                    "created_at": now,
                })
                record = AgentToolExecutionRecord(
                    id=exec_id, request_id=request_id, ordinal=ordinal, tool_name=tool_name,
                    tool_call_id=tool_call_id, arguments=arguments, status=status,
                    idempotency_key=idempotency_key, job_id=job_id, result=None,
                    created_at=now, completed_at=None,
                )

            if expected_generation is not None and worker_id is not None:
                updates = ["updated_at = :now"]
                params: dict[str, Any] = {
                    "id": request_id, "generation": expected_generation, "worker": worker_id,
                    "now": now,
                }
                if call_count is not None:
                    updates.append("call_count = :call_count")
                    params["call_count"] = call_count
                if repair_count is not None:
                    updates.append("repair_count = :repair_count")
                    params["repair_count"] = repair_count
                if repair_ledger is not None:
                    updates.append("repair_ledger_json = :ledger")
                    params["ledger"] = json.dumps(repair_ledger, sort_keys=True)
                result = conn.execute(text(f"""
                    UPDATE agent_requests SET {', '.join(updates)}
                    WHERE id = :id AND generation = :generation AND worker_id = :worker
                      AND lease_expires_at IS NOT NULL AND lease_expires_at > :now
                """), params)
                if result.rowcount != 1:
                    raise LeaseLostError("Request lease changed while recording a tool intent")
        return record

    def update_tool_execution(
        self,
        request_id: str,
        ordinal: int,
        status: str,
        result: dict[str, Any] | None = None,
        job_id: str | None = None,
        expected_generation: int | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Compatibility update; controller paths use atomic commit_tool_step."""
        now = utc_now_str()
        params: dict[str, Any] = {
            "request_id": request_id, "ordinal": ordinal, "status": status, "now": now,
        }
        updates = ["status = :status", "completed_at = :now"]
        if result is not None:
            updates.append("result_json = :result_json")
            params["result_json"] = json.dumps(result, ensure_ascii=False)
        if job_id is not None:
            updates.append("job_id = :job_id")
            params["job_id"] = job_id
        where = "request_id = :request_id AND ordinal = :ordinal"
        with self._write_connection() as conn:
            if expected_generation is not None and worker_id is not None:
                self._owned_request(conn, request_id, expected_generation, worker_id)
                where += " AND EXISTS (SELECT 1 FROM agent_requests r WHERE r.id = :request_id "                          "AND r.generation = :generation AND r.worker_id = :worker "                          "AND r.lease_expires_at IS NOT NULL AND r.lease_expires_at > :now)"
                params["generation"] = expected_generation
                params["worker"] = worker_id
            changed = conn.execute(
                text(f"UPDATE agent_tool_executions SET {', '.join(updates)} WHERE {where}"), params
            )
            if changed.rowcount != 1:
                raise LeaseLostError("Tool trace row was missing or request ownership changed")

    def checkpoint_decision(
        self,
        request_id: str,
        expected_generation: int,
        worker_id: str,
        session_token: str,
        decision: dict[str, Any],
        messages: list[dict[str, Any]],
        turn_count: int,
    ) -> None:
        now = utc_now_str()
        with self._write_connection() as conn:
            self._owned_request(conn, request_id, expected_generation, worker_id, session_token, True)
            call_ids = {
                call.get("id") for call in decision.get("tool_calls", [])
                if isinstance(call, dict) and isinstance(call.get("id"), str)
            }
            if call_ids:
                persisted_ids = set(conn.execute(
                    text("SELECT tool_call_id FROM agent_tool_executions WHERE request_id = :id"),
                    {"id": request_id},
                ).scalars().all())
                if call_ids & persisted_ids:
                    raise IdempotencyConflictError(
                        "Provider reused a tool call identifier from an earlier turn"
                    )
            changed = conn.execute(text("""
                UPDATE agent_requests
                SET accepted_decision_json = :decision, pending_cursor = 0,
                    pending_tool_calls_json = '[]', messages_json = :messages,
                    turn_count = :turn_count, updated_at = :now
                WHERE id = :id AND generation = :generation AND worker_id = :worker
                  AND lease_expires_at IS NOT NULL AND lease_expires_at > :now
            """), {
                "decision": json.dumps(decision, ensure_ascii=False),
                "messages": json.dumps(messages, ensure_ascii=False),
                "turn_count": turn_count, "now": now, "id": request_id,
                "generation": expected_generation, "worker": worker_id,
            })
            if changed.rowcount != 1:
                raise LeaseLostError("Lease changed while checkpointing an accepted provider decision")

    def reserve_provider_turn(
        self,
        request_id: str,
        expected_generation: int,
        worker_id: str,
        session_token: str,
        expected_turn_count: int,
    ) -> int:
        now = utc_now_str()
        with self._write_connection() as conn:
            self._owned_request(conn, request_id, expected_generation, worker_id, session_token, True)
            changed = conn.execute(text("""
                UPDATE agent_requests
                SET turn_count = :next_turn, updated_at = :now
                WHERE id = :id AND generation = :generation AND worker_id = :worker
                  AND turn_count = :prior_turn AND lease_expires_at IS NOT NULL
                  AND lease_expires_at > :now
            """), {
                "next_turn": expected_turn_count + 1, "prior_turn": expected_turn_count,
                "now": now, "id": request_id, "generation": expected_generation,
                "worker": worker_id,
            })
            if changed.rowcount != 1:
                raise LeaseLostError("Provider turn budget changed before turn reservation")
            return expected_turn_count + 1

    def advance_tool_cursor(
        self,
        request_id: str,
        expected_generation: int,
        worker_id: str,
        session_token: str,
        messages: list[dict[str, Any]],
        pending_cursor: int,
        complete_decision: bool = False,
    ) -> None:
        now = utc_now_str()
        with self._write_connection() as conn:
            self._owned_request(conn, request_id, expected_generation, worker_id, session_token, True)
            changed = conn.execute(text("""
                UPDATE agent_requests
                SET messages_json = :messages, pending_cursor = :cursor,
                    accepted_decision_json = :decision,
                    pending_tool_calls_json = :pending, updated_at = :now
                WHERE id = :id AND generation = :generation AND worker_id = :worker
                  AND lease_expires_at IS NOT NULL AND lease_expires_at > :now
            """), {
                "messages": json.dumps(messages, ensure_ascii=False),
                "cursor": 0 if complete_decision else pending_cursor,
                "decision": None if complete_decision else conn.execute(
                    text("SELECT accepted_decision_json FROM agent_requests WHERE id = :id"),
                    {"id": request_id},
                ).scalar_one_or_none(),
                "pending": "[]" if complete_decision else conn.execute(
                    text("SELECT pending_tool_calls_json FROM agent_requests WHERE id = :id"),
                    {"id": request_id},
                ).scalar_one_or_none() or "[]",
                "now": now, "id": request_id, "generation": expected_generation,
                "worker": worker_id,
            })
            if changed.rowcount != 1:
                raise LeaseLostError("Lease changed while advancing the accepted tool cursor")

    def commit_tool_step(
        self,
        request_id: str,
        ordinal: int,
        expected_generation: int,
        worker_id: str,
        session_token: str,
        status: str,
        result: dict[str, Any],
        messages: list[dict[str, Any]],
        pending_cursor: int,
        repair_ledger: dict[str, int],
        repair_count: int,
        complete_decision: bool = False,
    ) -> None:
        now = utc_now_str()
        with self._write_connection() as conn:
            self._owned_request(conn, request_id, expected_generation, worker_id, session_token, True)
            changed_exec = conn.execute(text("""
                UPDATE agent_tool_executions
                SET status = :status, result_json = :result, completed_at = :now
                WHERE request_id = :request_id AND ordinal = :ordinal
                  AND status = 'PENDING'
            """), {
                "status": status,
                "result": json.dumps(result, ensure_ascii=False),
                "now": now, "request_id": request_id, "ordinal": ordinal,
            })
            if changed_exec.rowcount != 1:
                raise LeaseLostError("Tool intent changed before its result was committed")
            current = conn.execute(
                text("SELECT accepted_decision_json, pending_tool_calls_json FROM agent_requests WHERE id = :id"),
                {"id": request_id},
            ).mappings().one()
            changed_req = conn.execute(text("""
                UPDATE agent_requests
                SET messages_json = :messages, pending_cursor = :cursor,
                    accepted_decision_json = :decision, pending_tool_calls_json = :pending,
                    repair_ledger_json = :ledger, repair_count = :repair_count,
                    updated_at = :now
                WHERE id = :id AND generation = :generation AND worker_id = :worker
                  AND lease_expires_at IS NOT NULL AND lease_expires_at > :now
            """), {
                "messages": json.dumps(messages, ensure_ascii=False),
                "cursor": 0 if complete_decision else pending_cursor,
                "decision": None if complete_decision else current["accepted_decision_json"],
                "pending": "[]" if complete_decision else current["pending_tool_calls_json"] or "[]",
                "ledger": json.dumps(repair_ledger, sort_keys=True),
                "repair_count": repair_count,
                "now": now, "id": request_id, "generation": expected_generation,
                "worker": worker_id,
            })
            if changed_req.rowcount != 1:
                raise LeaseLostError("Request lease changed before its tool result was committed")

    def admit_agent_job(
        self,
        conn: Any,
        queue: Any,
        request_params: dict[str, Any],
        request_id: str,
        expected_generation: int,
        worker_id: str,
        session_token: str,
        ordinal: int,
        decision_index: int,
        tool_name: str,
        tool_call_id: str,
        idempotency_key: str,
        next_cursor: int,
        continuation_nonce: str | None,
        response_factory: Any,
    ):
        """Admit and link one owned job, pausing its request in the same transaction."""
        owned = self._owned_request(conn, request_id, expected_generation, worker_id, session_token, True)
        if continuation_nonce and (
            owned["active_nonce"] != continuation_nonce
            or owned["active_nonce_generation"] is None
            or int(owned["active_nonce_generation"]) > expected_generation
        ):
            raise InvalidContinuationNonce("Continuation nonce was not issued for this request")
        expected_key = f"agent:{request_id}:{ordinal}"
        if idempotency_key != expected_key:
            raise IdempotencyConflictError("Agent job key does not match the durable request ordinal")
        execution = conn.execute(text("""
            SELECT * FROM agent_tool_executions
            WHERE request_id = :request_id AND ordinal = :ordinal
        """), {"request_id": request_id, "ordinal": ordinal}).mappings().fetchone()
        if (
            not execution or execution["status"] != "PENDING"
            or execution["tool_name"] != tool_name
            or execution["tool_call_id"] != tool_call_id
            or execution["idempotency_key"] != expected_key
        ):
            raise LeaseLostError("Saved pending tool intent does not authorize queue admission")

        saved_arguments = json.loads(execution["arguments_json"] or "{}")
        if not isinstance(request_params, dict) or set(request_params) != {"preset_name"}:
            raise IdempotencyConflictError("Queue parameters do not match an approved agent job intent")
        preset = request_params.get("preset_name")
        if tool_name == "run_experiment":
            if (
                preset not in APPROVED_PRESETS
                or saved_arguments != {"preset_name": preset}
            ):
                raise IdempotencyConflictError("Experiment preset does not match the saved provider intent")
        elif tool_name == "run_stress_suite":
            if (
                preset != "bank-stress"
                or set(saved_arguments) != {"suite_name"}
                or saved_arguments.get("suite_name") not in APPROVED_STRESS_SUITES
            ):
                raise IdempotencyConflictError("Stress suite does not match its approved job mapping")
        else:
            raise IdempotencyConflictError("This saved tool intent cannot admit a background job")

        from shiftguard.agent.execution_authority import authorized_execution_presets, EXECUTION_DENIED_MESSAGE
        if preset not in authorized_execution_presets(owned["prompt"]):
            raise PermissionError(EXECUTION_DENIED_MESSAGE)

        job = queue.enqueue_in_transaction(
            conn,
            request_params,
            session_id=owned["session_id"],
            idempotency_key=expected_key,
            session_locked=self.engine.dialect.name == "postgresql",
        )
        queued_result = {
            "status": "success", "tool_name": tool_name, "tool_call_id": tool_call_id,
            "is_side_effect": True, "job_id": job.id,
            "data": {"status": job.status.value, "job_id": job.id, "request_params": request_params},
        }
        changed_exec = conn.execute(text("""
            UPDATE agent_tool_executions
            SET status = 'success', result_json = :result, job_id = :job_id,
                completed_at = :now
            WHERE request_id = :request_id AND ordinal = :ordinal
              AND tool_call_id = :tool_call_id AND status = 'PENDING'
        """), {
            "result": json.dumps(queued_result, ensure_ascii=False), "job_id": job.id,
            "now": utc_now_str(), "request_id": request_id, "ordinal": ordinal,
            "tool_call_id": tool_call_id,
        })
        if changed_exec.rowcount != 1:
            raise LeaseLostError("Tool trace lost ownership during queue admission")

        nonce = secrets.token_urlsafe(24)
        now = utc_now_str()
        changed_req = conn.execute(text("""
            UPDATE agent_requests
            SET status = 'WAITING_FOR_JOB', active_job_id = :job_id,
                active_tool_call_id = :call_id, active_nonce = :nonce,
                active_nonce_generation = :generation, pending_cursor = :cursor,
                worker_id = NULL, lease_expires_at = NULL, updated_at = :now
            WHERE id = :id AND generation = :generation AND worker_id = :worker
              AND lease_expires_at IS NOT NULL AND lease_expires_at > :now
        """), {
            "job_id": job.id, "call_id": tool_call_id, "nonce": nonce,
            "generation": expected_generation, "cursor": next_cursor,
            "worker": worker_id, "now": now, "id": request_id,
        })
        if changed_req.rowcount != 1:
            raise LeaseLostError("Request lease changed during queue admission")

        if continuation_nonce:
            current, executions = self._records_for_response(conn, request_id)
            response = response_factory(current, executions, None)
            self._insert_receipt(conn, request_id, continuation_nonce, 202, response)
        return job

    def _records_for_response(self, conn: Any, request_id: str):
        req_row = conn.execute(
            text("SELECT * FROM agent_requests WHERE id = :id"), {"id": request_id}
        ).mappings().one()
        exec_rows = conn.execute(text("""
            SELECT * FROM agent_tool_executions
            WHERE request_id = :request_id ORDER BY ordinal ASC
        """), {"request_id": request_id}).mappings().all()
        return (
            AgentRequestRecord.from_row(dict(req_row)),
            [AgentToolExecutionRecord.from_row(dict(row)) for row in exec_rows],
        )

    def _insert_receipt(
        self, conn: Any, request_id: str, nonce: str, status_code: int, response: dict[str, Any]
    ) -> AgentContinuationReceiptRecord:
        existing = conn.execute(text("""
            SELECT * FROM agent_continuation_receipts
            WHERE request_id = :request_id AND nonce = :nonce
        """), {"request_id": request_id, "nonce": nonce}).mappings().fetchone()
        if existing:
            return AgentContinuationReceiptRecord.from_row(dict(existing))
        receipt_id = f"rcp_{uuid4().hex[:20]}"
        now = utc_now_str()
        conn.execute(text("""
            INSERT INTO agent_continuation_receipts (
                id, request_id, nonce, status_code, response_json, created_at
            ) VALUES (:id, :request_id, :nonce, :status_code, :response, :created_at)
        """), {
            "id": receipt_id, "request_id": request_id, "nonce": nonce,
            "status_code": status_code, "response": json.dumps(response, ensure_ascii=False),
            "created_at": now,
        })
        return AgentContinuationReceiptRecord(
            id=receipt_id, request_id=request_id, nonce=nonce, status_code=status_code,
            response=response, created_at=now,
        )

    def claim_continuation(
        self, request_id: str, nonce: str, worker_id: str, session_token: str, lease_seconds: int = 120
    ):
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        expires = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._write_connection() as conn:
            preview = conn.execute(
                text("SELECT session_id FROM agent_requests WHERE id = :id"), {"id": request_id}
            ).mappings().fetchone()
            if not preview:
                return "missing", None, None
            session_sql = "SELECT status, capability_token FROM agent_sessions WHERE id = :id"
            if self.engine.dialect.name == "postgresql":
                session_sql += " FOR UPDATE"
            session = conn.execute(text(session_sql), {"id": preview["session_id"]}).mappings().fetchone()
            request_sql = "SELECT * FROM agent_requests WHERE id = :id"
            if self.engine.dialect.name == "postgresql":
                request_sql += " FOR UPDATE"
            row = conn.execute(text(request_sql), {"id": request_id}).mappings().fetchone()
            if not row:
                return "missing", None, None
            req = AgentRequestRecord.from_row(dict(row))
            request_hash = self.authority_hash(session_token)
            session_hash = self.authority_hash(session["capability_token"]) if session else None
            if (
                not session or str(session["status"]).upper() != "ACTIVE"
                or req.session_id != preview["session_id"]
                or not request_hash or not session_hash or not req.authority_token_hash
                or not hmac.compare_digest(request_hash, session_hash)
                or not hmac.compare_digest(request_hash, req.authority_token_hash)
            ):
                raise RequestAuthorityError("Continuation is not bound to the current active session authority")

            receipt = conn.execute(text("""
                SELECT * FROM agent_continuation_receipts
                WHERE request_id = :request_id AND nonce = :nonce
            """), {"request_id": request_id, "nonce": nonce}).mappings().fetchone()
            if receipt:
                return "receipt", req, AgentContinuationReceiptRecord.from_row(dict(receipt))
            if (
                nonce != req.active_nonce
                or req.active_nonce_generation is None
                or req.active_nonce_generation > req.generation
                or req.status not in ("WAITING_FOR_JOB", "RUNNING")
            ):
                return "invalid", req, None

            busy = bool(req.lease_expires_at and req.lease_expires_at > now_str and req.worker_id != worker_id)
            if busy:
                return "busy", req, None
            changed = conn.execute(text("""
                UPDATE agent_requests
                SET generation = generation + 1, worker_id = :worker,
                    lease_expires_at = :expires, updated_at = :now
                WHERE id = :id AND generation = :generation AND active_nonce = :nonce
                  AND active_nonce_generation IS NOT NULL
                  AND (lease_expires_at IS NULL OR lease_expires_at <= :now OR worker_id = :worker)
            """), {
                "worker": worker_id, "expires": expires, "now": now_str,
                "id": request_id, "generation": req.generation, "nonce": nonce,
            })
            if changed.rowcount != 1:
                latest = conn.execute(text("SELECT * FROM agent_requests WHERE id = :id"), {"id": request_id}).mappings().one()
                return "busy", AgentRequestRecord.from_row(dict(latest)), None
            latest = conn.execute(text("SELECT * FROM agent_requests WHERE id = :id"), {"id": request_id}).mappings().one()
            return "claimed", AgentRequestRecord.from_row(dict(latest)), None

    def finish_request(
        self,
        request_id: str,
        expected_generation: int,
        worker_id: str,
        status: str,
        final_response: dict[str, Any] | None,
        error: dict[str, Any] | None,
        continuation_nonce: str | None,
        response_factory: Any,
    ):
        if status not in ("COMPLETED", "FAILED", "CANCELLED"):
            raise ValueError(f"Illegal terminal request status: {status}")
        with self._write_connection() as conn:
            owned = self._owned_request(
                conn, request_id, expected_generation, worker_id,
                require_bound_authority=status != "FAILED",
            )
            if continuation_nonce and (
                owned["active_nonce"] != continuation_nonce
                or owned["active_nonce_generation"] is None
                or int(owned["active_nonce_generation"]) > expected_generation
            ):
                raise InvalidContinuationNonce("Continuation nonce was not issued for this request")
            now = utc_now_str()
            changed = conn.execute(text("""
                UPDATE agent_requests
                SET status = :status, final_response_json = :final_response,
                    error_json = :error, active_job_id = NULL, active_tool_call_id = NULL,
                    active_nonce = NULL, active_nonce_generation = NULL,
                    accepted_decision_json = NULL, pending_cursor = 0,
                    pending_tool_calls_json = '[]', worker_id = NULL,
                    lease_expires_at = NULL, updated_at = :now
                WHERE id = :id AND generation = :generation AND worker_id = :worker
                  AND lease_expires_at IS NOT NULL AND lease_expires_at > :now
            """), {
                "status": status,
                "final_response": json.dumps(final_response, ensure_ascii=False) if final_response is not None else None,
                "error": json.dumps(error, ensure_ascii=False) if error is not None else None,
                "now": now, "id": request_id, "generation": expected_generation,
                "worker": worker_id,
            })
            if changed.rowcount != 1:
                raise LeaseLostError("Request lease changed before terminal state publication")
            current, executions = self._records_for_response(conn, request_id)
            status_code = 500 if status == "FAILED" else 200
            response = response_factory(current, executions, None)
            if continuation_nonce:
                self._insert_receipt(conn, request_id, continuation_nonce, status_code, response)
            return status_code, response, current

    def process_active_job(
        self,
        request_id: str,
        expected_generation: int,
        worker_id: str,
        session_token: str,
        continuation_nonce: str,
        response_factory: Any,
        safe_error: Any,
    ):
        """Resolve an attached job and advance the durable tool transcript atomically."""
        now = utc_now_str()
        with self._write_connection() as conn:
            req_row = self._owned_request(
                conn, request_id, expected_generation, worker_id, session_token, True
            )
            if (
                req_row["active_nonce"] != continuation_nonce
                or req_row["active_nonce_generation"] is None
                or int(req_row["active_nonce_generation"]) > expected_generation
            ):
                raise InvalidContinuationNonce("Continuation nonce was not issued for this request")
            job_sql = "SELECT * FROM jobs WHERE id = :id"
            if self.engine.dialect.name == "postgresql":
                job_sql += " FOR UPDATE"
            job_row = conn.execute(text(job_sql), {"id": req_row["active_job_id"]}).mappings().fetchone()
            if not job_row:
                job_status = "missing"
                job = None
            else:
                job = JobRecord.from_row(dict(job_row))
                job_status = job.status.value

            if job_status in (JobStatus.QUEUED.value, JobStatus.RUNNING.value):
                nonce = secrets.token_urlsafe(24)
                changed = conn.execute(text("""
                    UPDATE agent_requests
                    SET active_nonce = :new_nonce, active_nonce_generation = :generation,
                        worker_id = NULL, lease_expires_at = NULL, updated_at = :now
                    WHERE id = :id AND generation = :generation AND worker_id = :worker
                      AND lease_expires_at IS NOT NULL AND lease_expires_at > :now
                      AND active_nonce = :old_nonce
                """), {
                    "new_nonce": nonce, "generation": expected_generation,
                    "now": now, "id": request_id, "worker": worker_id,
                    "old_nonce": continuation_nonce,
                })
                if changed.rowcount != 1:
                    raise LeaseLostError("Request lease changed while issuing the next poll nonce")
                current, executions = self._records_for_response(conn, request_id)
                response = response_factory(current, executions, {"job_status": job_status})
                self._insert_receipt(conn, request_id, continuation_nonce, 202, response)
                return "waiting", 202, response, current

            if job is None:
                outcome = {
                    "status": "error", "job_id": req_row["active_job_id"],
                    "error": {"code": "JOB_NOT_FOUND", "message": "Attached job no longer exists."},
                }
                tool_status = "error"
            elif job.session_id != req_row["session_id"] or job.idempotency_key != f"agent:{request_id}:" + str(
                conn.execute(text("""
                    SELECT ordinal FROM agent_tool_executions
                    WHERE request_id = :request_id AND job_id = :job_id
                """), {"request_id": request_id, "job_id": job.id}).scalar_one_or_none()
            ):
                outcome = {
                    "status": "error", "job_id": job.id,
                    "error": {"code": "JOB_LINK_MISMATCH", "message": "Attached job does not match its durable request intent."},
                }
                tool_status = "error"
            elif job.status == JobStatus.COMPLETED:
                result = job.result or {}
                result_experiment_id = result.get("experiment_id") if isinstance(result, dict) else None
                experiment_id = job.experiment_id
                membership = None
                if experiment_id:
                    membership = conn.execute(text("""
                        SELECT p.execution_id
                        FROM experiment_publications p
                        JOIN experiment_executions e ON e.execution_id = p.execution_id
                        JOIN experiments x ON x.id = p.experiment_id
                        WHERE p.experiment_id = :experiment_id AND p.job_id = :job_id
                          AND p.status = 'PUBLISHED' AND e.experiment_id = p.experiment_id
                    """), {"experiment_id": experiment_id, "job_id": job.id}).mappings().first()
                if (
                    not experiment_id or (result_experiment_id and result_experiment_id != experiment_id)
                    or not membership
                ):
                    outcome = {
                        "status": "error", "job_id": job.id,
                        "error": {"code": "PUBLISHED_RESULT_UNVERIFIED", "message": "Completed job has no consistent published experiment and execution record."},
                    }
                    tool_status = "error"
                else:
                    outcome = {
                        "status": "success", "job_id": job.id,
                        "experiment_id": experiment_id,
                        "message": f"Job {job.id} completed; published experiment {experiment_id} is linked to execution {membership['execution_id']}.",
                    }
                    tool_status = "success"
            elif job.status == JobStatus.FAILED:
                outcome = {"status": "error", "job_id": job.id,
                           "error": safe_error(job.error or {"code": "JOB_FAILED", "message": "The job failed."})}
                tool_status = "error"
            else:
                outcome = {"status": "cancelled", "job_id": job.id,
                           "error": safe_error({"code": "JOB_CANCELLED", "message": "The job was cancelled."})}
                tool_status = "cancelled"

            active_call_id = req_row["active_tool_call_id"]
            exec_row = conn.execute(text("""
                SELECT * FROM agent_tool_executions
                WHERE request_id = :request_id AND tool_call_id = :call_id AND job_id = :job_id
            """), {"request_id": request_id, "call_id": active_call_id,
                  "job_id": req_row["active_job_id"]}).mappings().fetchone()
            if not exec_row:
                raise LeaseLostError("Attached job has no matching durable tool trace")
            changed_exec = conn.execute(text("""
                UPDATE agent_tool_executions
                SET status = :status, result_json = :result, completed_at = :now
                WHERE request_id = :request_id AND ordinal = :ordinal AND job_id = :job_id
                  AND tool_call_id = :call_id
            """), {
                "status": tool_status, "result": json.dumps(outcome, ensure_ascii=False),
                "now": now, "request_id": request_id, "ordinal": exec_row["ordinal"],
                "job_id": req_row["active_job_id"], "call_id": active_call_id,
            })
            if changed_exec.rowcount != 1:
                raise LeaseLostError("Attached job trace lost ownership")

            messages = json.loads(req_row["messages_json"] or "[]")
            if not any(m.get("role") == "tool" and m.get("tool_call_id") == active_call_id for m in messages):
                messages.append({
                    "role": "tool", "name": exec_row["tool_name"],
                    "tool_call_id": active_call_id, "content": json.dumps(outcome, ensure_ascii=False),
                })
            refs = json.loads(req_row["evidence_refs_json"] or "[]")
            if tool_status == "success" and outcome.get("experiment_id") not in refs:
                refs.append(outcome["experiment_id"])

            decision_json = req_row["accepted_decision_json"]
            pending_calls = json.loads(req_row["pending_tool_calls_json"] or "[]")
            if not decision_json and pending_calls:
                normalized_calls = []
                for call in pending_calls:
                    function = call.get("function", {})
                    arguments = function.get("arguments", {})
                    if isinstance(arguments, str):
                        arguments = json.loads(arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError("Saved tool arguments must be a JSON object")
                    normalized_calls.append({
                        "id": call.get("id"), "name": function.get("name"),
                        "arguments": arguments,
                    })
                decision_json = json.dumps({
                    "content": None, "tool_calls": normalized_calls,
                    "first_ordinal": int(req_row["call_count"]) + 1,
                }, ensure_ascii=False)
                cursor = 0
            else:
                cursor = int(req_row["pending_cursor"] or 0)
            changed_req = conn.execute(text("""
                UPDATE agent_requests
                SET status = 'RUNNING', active_job_id = NULL, active_tool_call_id = NULL,
                    messages_json = :messages, evidence_refs_json = :refs,
                    accepted_decision_json = :decision, pending_cursor = :cursor,
                    pending_tool_calls_json = '[]', error_json = NULL, updated_at = :now
                WHERE id = :id AND generation = :generation AND worker_id = :worker
                  AND lease_expires_at IS NOT NULL AND lease_expires_at > :now
                  AND active_job_id = :job_id AND active_nonce = :nonce
            """), {
                "messages": json.dumps(messages, ensure_ascii=False), "refs": json.dumps(refs),
                "decision": decision_json, "cursor": cursor, "now": now,
                "id": request_id, "generation": expected_generation, "worker": worker_id,
                "job_id": req_row["active_job_id"], "nonce": continuation_nonce,
            })
            if changed_req.rowcount != 1:
                raise LeaseLostError("Request lease changed while resolving its attached job")
            current, _ = self._records_for_response(conn, request_id)
            return "ready", 200, None, current

    def list_tool_executions(self, request_id: str) -> list[AgentToolExecutionRecord]:
        with self.engine.connect() as conn:
            stmt = text(
                """
                SELECT * FROM agent_tool_executions
                WHERE request_id = :request_id
                ORDER BY ordinal ASC
                """
            )
            rows = conn.execute(stmt, {"request_id": request_id}).mappings().fetchall()
            return [AgentToolExecutionRecord.from_row(dict(r)) for r in rows]

    def store_receipt(
        self,
        request_id: str,
        nonce: str,
        status_code: int,
        response_dict: dict[str, Any],
    ) -> AgentContinuationReceiptRecord:
        """Store or retrieve existing receipt for single-use nonce replay.

        Conflict-safe: does not raise IntegrityError on concurrent duplicate inserts.
        """
        existing = self.get_receipt(request_id, nonce)
        if existing:
            return existing

        now = utc_now_str()
        receipt_id = f"rcp_{uuid4().hex[:20]}"
        stmt = text(
            """
            INSERT INTO agent_continuation_receipts (
                id, request_id, nonce, status_code, response_json, created_at
            ) VALUES (
                :id, :request_id, :nonce, :status_code, :response_json, :created_at
            )
            """
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    stmt,
                    {
                        "id": receipt_id,
                        "request_id": request_id,
                        "nonce": nonce,
                        "status_code": status_code,
                        "response_json": json.dumps(response_dict),
                        "created_at": now,
                    },
                )
        except IntegrityError:
            winner = self.get_receipt(request_id, nonce)
            if winner:
                return winner
            raise

        return AgentContinuationReceiptRecord(
            id=receipt_id,
            request_id=request_id,
            nonce=nonce,
            status_code=status_code,
            response=response_dict,
            created_at=now,
        )

    def get_receipt(self, request_id: str, nonce: str) -> AgentContinuationReceiptRecord | None:
        with self.engine.connect() as conn:
            stmt = text(
                """
                SELECT * FROM agent_continuation_receipts
                WHERE request_id = :request_id AND nonce = :nonce
                """
            )
            row = conn.execute(stmt, {"request_id": request_id, "nonce": nonce}).mappings().fetchone()
            return AgentContinuationReceiptRecord.from_row(dict(row)) if row else None
