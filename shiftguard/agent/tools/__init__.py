"""Tool context and shared exports for Gate 6 tool handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from sqlalchemy.engine import Engine
from shiftguard.settings import Settings
from shiftguard.jobs.models import JobRecord


@dataclass(frozen=True)
class ToolContext:
    engine: Engine
    settings: Settings
    session_id: str
    session_token: str | None = None
    request_id: str | None = None
    ordinal: int = 1
    authorized_experiment_ids: frozenset[str] | None = None
    admit_job: Callable[[dict[str, Any]], JobRecord] | None = None
    authorized_run_presets: frozenset[str] = frozenset()


def experiment_evidence_allowed(ctx: ToolContext, experiment_id: str) -> bool:
    """Fail closed unless the durable request context explicitly authorizes this ID."""
    allowed = ctx.authorized_experiment_ids
    return allowed is not None and experiment_id in allowed
