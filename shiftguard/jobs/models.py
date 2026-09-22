"""Data models and enums for Gate 4 durable queue and continuation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobEventType(str, Enum):
    ENQUEUED = "ENQUEUED"
    CLAIMED = "CLAIMED"
    HEARTBEAT = "HEARTBEAT"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REQUEUED = "REQUEUED"


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    WAITING_FOR_JOB = "WAITING_FOR_JOB"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "expired"


def utc_now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class JobRecord:
    id: str
    payload_hash: str
    status: JobStatus
    request_params: dict[str, Any]
    experiment_id: str | None = None
    session_id: str | None = None
    idempotency_key: str | None = None
    worker_id: str | None = None
    fencing_token: str | None = None
    attempt: int = 0
    max_attempts: int = 3
    lease_expires_at: str | None = None
    heartbeat_at: str | None = None
    cancel_requested: bool = False
    error: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> JobRecord:
        params_raw = row.get("request_params_json")
        params = json.loads(params_raw) if isinstance(params_raw, str) else (params_raw or {})
        err_raw = row.get("error_json")
        err = json.loads(err_raw) if isinstance(err_raw, str) and err_raw else None
        res_raw = row.get("result_json")
        res = json.loads(res_raw) if isinstance(res_raw, str) and res_raw else None

        return cls(
            id=row["id"],
            experiment_id=row.get("experiment_id"),
            session_id=row.get("session_id"),
            idempotency_key=row.get("idempotency_key"),
            payload_hash=row["payload_hash"],
            status=JobStatus(row["status"]),
            request_params=params,
            worker_id=row.get("worker_id"),
            fencing_token=row.get("fencing_token"),
            attempt=int(row.get("attempt") or 0),
            max_attempts=int(row.get("max_attempts") or 3),
            lease_expires_at=row.get("lease_expires_at"),
            heartbeat_at=row.get("heartbeat_at"),
            cancel_requested=bool(row.get("cancel_requested")),
            error=err,
            result=res,
            created_at=row.get("created_at") or "",
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "experiment_id": self.experiment_id,
            "session_id": self.session_id,
            "idempotency_key": self.idempotency_key,
            "status": self.status.value,
            "request_params": self.request_params,
            "worker_id": self.worker_id,
            "fencing_token": self.fencing_token,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "lease_expires_at": self.lease_expires_at,
            "heartbeat_at": self.heartbeat_at,
            "cancel_requested": self.cancel_requested,
            "error": self.error,
            "result": self.result,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class WorkerFencedOutException(Exception):
    """Raised when a worker has lost its lease or has been superseded by another claim."""
    pass


class WorkerCancelledException(Exception):
    """Raised when a worker detects that its job has been cancelled."""
    pass


class PublicationContentionError(Exception):
    """Raised when publication reservation conflicts with an active owner."""
    pass


class PublicationLostOwnershipError(Exception):
    """Raised when publication cannot be finalized due to lost or superseded PREPARED state."""
    pass

