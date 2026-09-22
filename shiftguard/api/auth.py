"""Centralized session capability authentication and authority verification for Gate 4."""

from __future__ import annotations

import hmac
from fastapi import Header, HTTPException
from sqlalchemy.engine import Engine

from shiftguard.jobs.continuation import AgentSessionRecord, ContinuationService
from shiftguard.jobs.models import SessionStatus


def verify_session_authority(
    engine: Engine,
    x_session_id: str | None,
    x_session_token: str | None,
) -> AgentSessionRecord:
    """Verify session ID and capability token, returning authenticated AgentSessionRecord.
    
    Raises 401 MISSING_SESSION_CREDENTIALS if headers are missing or empty.
    Raises 401 INVALID_SESSION_CREDENTIALS if session does not exist.
    Raises 401 INVALID_CAPABILITY_TOKEN if token does not match.
    """
    if not x_session_id or not x_session_id.strip() or not x_session_token or not x_session_token.strip():
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "MISSING_SESSION_CREDENTIALS",
                    "message": "Both X-Session-ID and X-Session-Token headers are required",
                }
            },
        )

    continuation = ContinuationService(engine)
    session = continuation.get_session(x_session_id.strip())
    if not session:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "INVALID_SESSION_CREDENTIALS",
                    "message": f"Session '{x_session_id}' not found",
                }
            },
        )

    if session.status == SessionStatus.EXPIRED:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SESSION_EXPIRED",
                    "message": f"Session '{x_session_id}' has expired",
                }
            },
        )

    if not session.capability_token or not hmac.compare_digest(session.capability_token, x_session_token.strip()):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "INVALID_CAPABILITY_TOKEN",
                    "message": "Supplied capability token does not match session authority",
                }
            },
        )

    return session
