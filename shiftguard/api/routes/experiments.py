from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from shiftguard.api.auth import verify_session_authority
from shiftguard.api.schemas import ExperimentSubmitRequest, ExperimentSubmitResponse
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.queue import IdempotencyConflictError, JobQueue, QuotaExceededError
from shiftguard.storage.repositories import ExperimentRepository

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentSubmitResponse, status_code=202)
def submit_experiment(
    req: ExperimentSubmitRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JSONResponse:
    """Submit an experiment run job.
    
    Durable enqueue is committed before returning 202 Accepted.
    Replay with same Idempotency-Key and payload returns existing job.
    Replay with same Idempotency-Key and changed payload returns 409 Conflict.
    Enforces server-issued session existence, capability authority, and active job quota limits.
    """
    engine = request.app.state.engine

    # Require authenticated session: anonymous/unscoped submissions are rejected
    effective_session_id = x_session_id or req.session_id
    if not effective_session_id and not x_session_token:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SESSION_REQUIRED",
                    "message": "Authenticated session is required to submit experiments",
                }
            },
        )

    if req.session_id and x_session_id and req.session_id != x_session_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "CROSS_SESSION_ACCESS_DENIED",
                    "message": f"Body session_id '{req.session_id}' does not match header X-Session-ID '{x_session_id}'",
                }
            },
        )

    session = verify_session_authority(engine, effective_session_id, x_session_token)

    queue = JobQueue(engine)

    try:
        job = queue.enqueue(
            request_params=req.model_dump(),
            session_id=session.id,
            idempotency_key=idempotency_key,
        )
    except IdempotencyConflictError as err:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "IDEMPOTENCY_KEY_CONFLICT",
                    "message": str(err),
                }
            },
        )
    except QuotaExceededError as err:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "SESSION_QUOTA_EXCEEDED",
                    "message": str(err),
                }
            },
        )

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job.id,
            "status": job.status.value,
            "status_url": f"/api/v1/jobs/{job.id}",
            "estimated_duration_seconds": 60,
        },
    )


@router.get("")
def list_experiments(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List verified PUBLISHED experiments with bounded pagination."""
    repo = ExperimentRepository(request.app.state.engine)
    try:
        records = repo.list_published(limit=limit, offset=offset)
        return {
            "experiments": records,
            "limit": limit,
            "offset": offset,
        }
    finally:
        repo.dispose()


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str, request: Request) -> dict[str, Any]:
    """Retrieve verified published experiment overview and deterministic payload."""
    repo = ExperimentRepository(request.app.state.engine)
    try:
        res = repo.get_published(experiment_id)
        if not res:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "EXPERIMENT_NOT_FOUND",
                        "message": f"Published experiment '{experiment_id}' not found",
                    }
                },
            )
        exp, pub = res
        return {
            "experiment_id": exp.experiment_id,
            "created_at": pub.created_at,
            "payload": exp.deterministic_payload,
            "content_hashes": exp.content_hashes,
        }
    finally:
        repo.dispose()


@router.get("/{experiment_id}/metrics")
def get_experiment_metrics(experiment_id: str, request: Request) -> dict[str, Any]:
    """Retrieve condition metrics for a verified published experiment."""
    repo = ExperimentRepository(request.app.state.engine)
    try:
        res = repo.get_published(experiment_id)
        if not res:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "EXPERIMENT_NOT_FOUND",
                        "message": f"Published experiment '{experiment_id}' not found",
                    }
                },
            )
        exp, pub = res
        conditions = exp.deterministic_payload.get("conditions", {})
        comparisons = exp.deterministic_payload.get("comparisons", {})
        return {
            "experiment_id": experiment_id,
            "conditions": conditions,
            "comparisons": comparisons,
        }
    finally:
        repo.dispose()


@router.get("/{experiment_id}/artifacts")
def list_experiment_artifacts(experiment_id: str, request: Request) -> dict[str, Any]:
    """List available verified published artifacts from publication manifest."""
    repo = ExperimentRepository(request.app.state.engine)
    try:
        res = repo.get_published(experiment_id)
        if not res:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "EXPERIMENT_NOT_FOUND",
                        "message": f"Published experiment '{experiment_id}' not found",
                    }
                },
            )
        exp, pub = res
        artifacts = []
        for rel_path, digest in pub.manifest.items():
            name = Path(rel_path).stem
            artifacts.append({
                "name": name,
                "relative_path": rel_path,
                "sha256": digest,
                "download_url": f"/api/v1/experiments/{experiment_id}/artifacts/{name}",
            })
        return {
            "experiment_id": experiment_id,
            "artifacts": artifacts,
        }
    finally:
        repo.dispose()


@router.get("/{experiment_id}/artifacts/{artifact_name}")
def download_experiment_artifact(
    experiment_id: str,
    artifact_name: str,
    request: Request,
) -> FileResponse:
    """Download a specific artifact JSON file safely backed by verified published manifest."""
    # Prevent traversal
    if ".." in artifact_name or "/" in artifact_name or "\\" in artifact_name:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_ARTIFACT_NAME",
                    "message": "Path traversal characters are strictly forbidden",
                }
            },
        )

    repo = ExperimentRepository(request.app.state.engine)
    try:
        res = repo.get_published(experiment_id)
        if not res:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "EXPERIMENT_NOT_FOUND",
                        "message": f"Published experiment '{experiment_id}' not found",
                    }
                },
            )
        exp, pub = res

        # Locate relative path in published manifest
        target_rel_path: str | None = None
        expected_hash: str | None = None
        for rel_path, digest in pub.manifest.items():
            if Path(rel_path).stem == artifact_name or rel_path == artifact_name or rel_path == f"{artifact_name}.json":
                target_rel_path = rel_path
                expected_hash = digest
                break

        if not target_rel_path or not expected_hash:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "ARTIFACT_NOT_IN_MANIFEST",
                        "message": f"Artifact '{artifact_name}' not part of verified published manifest",
                    }
                },
            )

        target_file = request.app.state.settings.artifact_root / experiment_id / target_rel_path
        if not target_file.is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "ARTIFACT_FILE_MISSING",
                        "message": f"Artifact file '{target_rel_path}' missing from disk",
                    }
                },
            )

        # Verify disk file hash against publication manifest
        actual_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "ARTIFACT_INTEGRITY_MISMATCH",
                        "message": f"Artifact file '{target_rel_path}' on disk failed manifest hash verification",
                    }
                },
            )

        return FileResponse(
            path=str(target_file),
            media_type="application/json",
            filename=f"{artifact_name}.json",
        )
    finally:
        repo.dispose()
