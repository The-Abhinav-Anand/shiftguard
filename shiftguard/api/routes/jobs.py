from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from shiftguard.api.auth import verify_session_authority
from shiftguard.api.schemas import JobCancelResponse, JobStatusResponse
from shiftguard.jobs.queue import JobQueue

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    request: Request,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JobStatusResponse:
    """Retrieve current status of an enqueued or completed job with session capability verification."""
    queue = JobQueue(request.app.state.engine)
    job = queue.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": f"Job '{job_id}' not found",
                }
            },
        )

    if job.session_id:
        if not x_session_id or not x_session_token:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "MISSING_SESSION_CREDENTIALS",
                        "message": "Session credentials required to access this job",
                    }
                },
            )
        if job.session_id != x_session_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "CROSS_SESSION_ACCESS_DENIED",
                        "message": f"Access denied: Job '{job_id}' belongs to another session",
                    }
                },
            )
        verify_session_authority(request.app.state.engine, x_session_id, x_session_token)

    return JobStatusResponse(
        job_id=job.id,
        status=job.status.value,
        experiment_id=job.experiment_id,
        session_id=job.session_id,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        cancel_requested=job.cancel_requested,
        error=job.error,
        result=job.result,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    request: Request,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JSONResponse:
    """Request cooperative or immediate cancellation of a job with session capability check."""
    queue = JobQueue(request.app.state.engine)
    job = queue.get_job(job_id)
    if not job:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": f"Job '{job_id}' not found",
                }
            },
        )

    if job.session_id:
        if not x_session_id or not x_session_token:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "MISSING_SESSION_CREDENTIALS",
                        "message": "Session credentials required to cancel this job",
                    }
                },
            )
        if job.session_id != x_session_id:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CROSS_SESSION_ACCESS_DENIED",
                        "message": f"Cancellation denied: Job '{job_id}' belongs to another session",
                    }
                },
            )
        try:
            verify_session_authority(request.app.state.engine, x_session_id, x_session_token)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)

    success, resolution = queue.request_cancellation(job_id, session_id=x_session_id)

    if resolution == "forbidden":
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "CROSS_SESSION_ACCESS_DENIED",
                    "message": f"Cancellation denied: Job '{job_id}' belongs to another session",
                }
            },
        )
    elif resolution == "not_found":
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": f"Job '{job_id}' not found",
                }
            },
        )
    elif resolution == "terminal":
        current_status = job.status.value if job else "terminal"
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "JOB_ALREADY_TERMINAL",
                    "message": f"Cannot cancel job '{job_id}' in terminal state '{current_status}'",
                }
            },
        )
    else:
        message = "Job cancelled immediately" if resolution == "cancelled" else "Cancellation requested for running job"
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": resolution,
                "message": message,
            },
        )
