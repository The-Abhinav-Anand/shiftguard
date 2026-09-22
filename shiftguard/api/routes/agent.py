"""Agent session continuation and checkpointing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from shiftguard.api.auth import verify_session_authority
from shiftguard.api.schemas import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionResumeRequest,
    SessionResumeResponse,
)
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.queue import JobQueue

router = APIRouter(prefix="/api/v1/agent/sessions", tags=["agent"])


@router.post("", response_model=SessionCreateResponse, status_code=201)
def create_session(
    req: SessionCreateRequest,
    request: Request,
) -> JSONResponse:
    """Create a new agent session with an active continuation nonce and capability token."""
    continuation = ContinuationService(request.app.state.engine)
    session = continuation.create_session(initial_state=req.initial_state)

    return JSONResponse(
        status_code=201,
        content={
            "session_id": session.id,
            "status": session.status.value,
            "nonce": session.active_nonce,
            "capability_token": session.capability_token,
            "created_at": session.created_at,
        },
    )


@router.get("/{session_id}")
def get_session(
    session_id: str,
    request: Request,
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> dict:
    """Retrieve current state and dependency history of an agent session."""
    session = verify_session_authority(request.app.state.engine, session_id, x_session_token)
    return session.to_dict()


@router.post("/{session_id}/resume")
def resume_session(
    session_id: str,
    req: SessionResumeRequest,
    request: Request,
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JSONResponse:
    """Resume an agent session using a single-use nonce with capability verification.
    
    If blocking jobs are still executing, returns 202 Accepted.
    If all blocking jobs have completed, returns 200 OK with deterministic transition result.
    """
    verify_session_authority(request.app.state.engine, session_id, x_session_token)
    continuation = ContinuationService(request.app.state.engine)
    queue = JobQueue(request.app.state.engine)

    status_code, payload = continuation.resume(
        session_id=session_id,
        nonce=req.nonce,
        queue=queue,
    )
    return JSONResponse(status_code=status_code, content=payload)

