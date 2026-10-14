"""Health, liveness, and readiness endpoints."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import threading

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from shiftguard.datasets.bank import FROZEN_BANK_SOURCE, FROZEN_CLEAN_DIGEST, FROZEN_ROW_COUNT
from shiftguard.experiments.config import OutageConfig
from shiftguard.migrations import get_alembic_config
from shiftguard.storage.db import check_database_connection

router = APIRouter(tags=["health"])

# The accepted Bank presets read these paths relative to the working directory.
DATASET_CSV: Path = OutageConfig.dataset_csv
DATASET_MANIFEST: Path = OutageConfig.dataset_manifest

_dataset_lock = threading.Lock()
_dataset_cache: dict[tuple, bool] = {}


def reset_dataset_cache() -> None:
    with _dataset_lock:
        _dataset_cache.clear()


@lru_cache(maxsize=1)
def _expected_head() -> str | None:
    return ScriptDirectory.from_config(get_alembic_config()).get_current_head()


def _current_revision(engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _dataset_verified(csv_path: Path, manifest_path: Path) -> bool:
    """Frozen Bank identity, re-hashed only when either file's size or mtime changes."""
    try:
        csv_stat, manifest_stat = csv_path.stat(), manifest_path.stat()
    except OSError:
        return False
    key = (str(csv_path), csv_stat.st_size, csv_stat.st_mtime_ns,
           str(manifest_path), manifest_stat.st_size, manifest_stat.st_mtime_ns)
    with _dataset_lock:
        cached = _dataset_cache.get(key)
        if cached is not None:
            return cached
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            verified = (
                isinstance(manifest, dict)
                and all(manifest.get(name) == value for name, value in FROZEN_BANK_SOURCE.items())
                and manifest.get("clean_sha256") == FROZEN_CLEAN_DIGEST
                and manifest.get("rows") == FROZEN_ROW_COUNT
                and hashlib.sha256(csv_path.read_bytes()).hexdigest() == FROZEN_CLEAN_DIGEST
            )
        except (OSError, ValueError):
            verified = False
        _dataset_cache.clear()
        _dataset_cache[key] = verified
        return verified


def _not_ready(reason: str) -> JSONResponse:
    # Fixed reason codes only: exception text can carry paths or connection details.
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "SERVICE_UNAVAILABLE",
                "message": "Readiness check failed",
                "details": {"reason": reason},
            }
        },
    )


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Process liveness probe; does not depend on external services."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(request: Request) -> JSONResponse:
    """Database, schema head, artifact storage and the frozen Bank dataset.

    Worker liveness is not inferred here; the hosted acceptance probe proves it
    by completing a real job.
    """
    engine = request.app.state.engine
    try:
        check_database_connection(engine)
    except Exception:
        return _not_ready("database_unavailable")
    try:
        if _current_revision(engine) != _expected_head():
            return _not_ready("migration_not_at_head")
    except Exception:
        return _not_ready("migration_not_at_head")
    try:
        artifact_root = request.app.state.settings.artifact_root
        artifact_root.mkdir(parents=True, exist_ok=True)
        if not artifact_root.is_dir():
            return _not_ready("storage_unwritable")
    except OSError:
        return _not_ready("storage_unwritable")
    if not _dataset_verified(DATASET_CSV, DATASET_MANIFEST):
        return _not_ready("dataset_unverified")
    return JSONResponse(
        status_code=200,
        content={
            "status": "ready",
            "database": "connected",
            "migration": "head",
            "storage": "writable",
            "dataset": "verified",
        },
    )
