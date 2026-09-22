"""Health, liveness, and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from shiftguard.storage.db import check_database_connection

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Process liveness probe; does not depend on external services."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(request: Request) -> JSONResponse:
    """Readiness probe checking database connectivity and storage readiness."""
    try:
        check_database_connection(request.app.state.engine)
        artifact_root = request.app.state.settings.artifact_root
        artifact_root.mkdir(parents=True, exist_ok=True)
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "database": "connected", "storage": "writable"},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Readiness check failed",
                    "details": {"reason": str(exc)},
                }
            },
        )
