from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.models import JobEventType, JobRecord, JobStatus, SessionStatus
from shiftguard.jobs.queue import IdempotencyConflictError, JobQueue
from shiftguard.jobs.recovery import cleanup_abandoned_staging, recover_expired_leases


def __getattr__(name: str):
    if name == "ExperimentWorker":
        from shiftguard.jobs.worker import ExperimentWorker
        return ExperimentWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ContinuationService",
    "ExperimentWorker",
    "IdempotencyConflictError",
    "JobEventType",
    "JobQueue",
    "JobRecord",
    "JobStatus",
    "SessionStatus",
    "cleanup_abandoned_staging",
    "recover_expired_leases",
]
