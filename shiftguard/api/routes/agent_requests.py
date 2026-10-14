"""FastAPI routes for Gate 6 natural-language agent requests, execution, and resumption."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from shiftguard.agent.controller import AgentController, format_agent_response
from shiftguard.agent.provider import AgentProvider
from shiftguard.agent.registry import ToolRegistry
from shiftguard.agent.schemas import (
    AgentRequestResponse,
    AgentRequestSubmit,
    AgentResumeRequest,
    AgentStatusResponse,
)
from shiftguard.agent.store import AgentRequestRecord, AgentStore, IdempotencyConflictError
from shiftguard.api.auth import verify_session_authority
from shiftguard.settings import Settings

router = APIRouter(prefix="/api/v1/agent", tags=["agent-requests"])


@router.get("/status", response_model=AgentStatusResponse)
def get_agent_status(request: Request) -> JSONResponse:
    """Return status of agent runtime, Nebius configuration, and execution boundaries."""
    settings: Settings = request.app.state.settings
    provider = getattr(request.app.state, "agent_provider", None) or AgentProvider(settings)
    is_scripted = provider.__class__.__name__ in ("ScriptedProvider", "DynamicE2EProvider")
    agent_enabled = bool(getattr(settings, "agent_enabled", False)) or is_scripted
    general_chat_enabled = bool(getattr(settings, "general_chat_enabled", False))
    provider_kind = "scripted" if is_scripted else ("nebius" if agent_enabled or general_chat_enabled else "disabled")
    ordinary_budget = getattr(request.app.state, "ordinary_budget", None)

    return JSONResponse(
        status_code=200,
        content={
            "enabled": agent_enabled,
            "available": bool(provider and provider.is_available()),
            "provider_kind": provider_kind,
            "model": "scripted-test-harness" if is_scripted else getattr(settings, "nebius_model", "nvidia/Nemotron-3_5-Lightning"),
            "max_turns": 6,
            "max_calls": 8,
            "active_requests_count": 0,
            "general_chat_enabled": general_chat_enabled,
            "ordinary_budget": ordinary_budget.public_snapshot() if ordinary_budget is not None else None,
        },
    )


@router.post("/requests", response_model=AgentRequestResponse, status_code=200)
async def submit_agent_request(
    body: AgentRequestSubmit,
    request: Request,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JSONResponse:
    """Submit a natural language inquiry or workflow command.

    Requires authenticated session credentials (X-Session-ID and X-Session-Token).
    Durable request record is created before execution starts.
    Returns 200 on completion or 202 if paused waiting for a background experiment job.
    """
    engine = request.app.state.engine
    settings: Settings = request.app.state.settings

    # Authenticate session
    session = verify_session_authority(engine, x_session_id, x_session_token)
    session_id = x_session_id.strip()

    # Compute canonical body hash
    canonical_body_hash = hashlib.sha256(body.prompt.strip().encode("utf-8")).hexdigest()

    store = AgentStore(engine)
    try:
        req_record, is_new = store.create_or_get_request(
            session_id=session_id,
            intent_key=body.idempotency_key.strip(),
            canonical_body_hash=canonical_body_hash,
            prompt=body.prompt.strip(),
            authority_token_hash=store.authority_hash(session.capability_token),
        )
    except IdempotencyConflictError as err:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": str(err),
                }
            },
        )

    req_record = store.bind_legacy_request_authority(
        req_record.id, session_id, session.capability_token,
    )
    if not req_record:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "SESSION_AUTHORITY_CHANGED", "message": "Request authority is not valid for this session capability."}},
        )

    # Provider and registry
    provider = getattr(request.app.state, "agent_provider", None)
    if provider is None:
        provider = AgentProvider(settings)
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:
        registry = ToolRegistry()

    controller = AgentController(
        engine=engine,
        settings=settings,
        store=store,
        registry=registry,
        provider=provider,
        session_token=session.capability_token,
    )

    worker_id = f"worker_{uuid4().hex[:12]}"
    updated_req = await controller.execute_request(req_record.id, worker_id)

    resp_content = format_agent_response(updated_req, store)
    status_code = 202 if updated_req.status == "WAITING_FOR_JOB" else 200

    return JSONResponse(status_code=status_code, content=resp_content)


@router.get("/requests/{request_id}", response_model=AgentRequestResponse)
def get_agent_request(
    request_id: str,
    request: Request,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JSONResponse:
    """Retrieve current status, tool trace, and grounded results for an agent request."""
    engine = request.app.state.engine
    verify_session_authority(engine, x_session_id, x_session_token)

    store = AgentStore(engine)
    req = store.get_request(request_id)
    if not req:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "REQUEST_NOT_FOUND",
                    "message": f"Agent request '{request_id}' not found",
                }
            },
        )

    if req.session_id != x_session_id.strip():
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "CROSS_SESSION_ACCESS_DENIED",
                    "message": f"Request '{request_id}' does not belong to session '{x_session_id}'",
                }
            },
        )

    resp_content = format_agent_response(req, store)
    return JSONResponse(status_code=200, content=resp_content)


@router.post("/requests/{request_id}/resume")
async def resume_agent_request(
    request_id: str,
    body: AgentResumeRequest,
    request: Request,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JSONResponse:
    """Resume an agent request waiting for a background job using a single-use nonce."""
    engine = request.app.state.engine
    settings: Settings = request.app.state.settings
    verify_session_authority(engine, x_session_id, x_session_token)

    store = AgentStore(engine)
    req = store.get_request(request_id)
    if not req:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "REQUEST_NOT_FOUND",
                    "message": f"Agent request '{request_id}' not found",
                }
            },
        )

    if req.session_id != x_session_id.strip():
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "CROSS_SESSION_ACCESS_DENIED",
                    "message": f"Request '{request_id}' does not belong to session '{x_session_id}'",
                }
            },
        )

    nonce = body.nonce.strip()

    provider = getattr(request.app.state, "agent_provider", None) or AgentProvider(settings)
    registry = getattr(request.app.state, "tool_registry", None) or ToolRegistry()
    controller = AgentController(
        engine=engine,
        settings=settings,
        store=store,
        registry=registry,
        provider=provider,
        session_token=x_session_token.strip(),
    )

    worker_id = f"worker_{uuid4().hex[:12]}"
    status_code, result = await controller.resume_request(request_id, nonce, worker_id)

    # Return the exact result envelope returned by controller/stored in receipt (G6-S07)
    return JSONResponse(status_code=status_code, content=result)
