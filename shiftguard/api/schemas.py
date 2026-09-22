"""Strict Pydantic schemas for Gate 4 REST API with extra='forbid'."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorDetail(StrictBaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class ErrorResponse(StrictBaseModel):
    error: ErrorDetail


class PresetOverrides(StrictBaseModel):
    seed: Literal[31001, 31002, 31003] | None = Field(default=None)


class ExperimentSubmitRequest(StrictBaseModel):
    preset_name: Literal["bank-outage-50", "bank-stress", "bank-baseline"] = "bank-outage-50"
    session_id: str | None = Field(default=None, max_length=64)
    overrides: PresetOverrides | None = None


class ExperimentSubmitResponse(StrictBaseModel):
    job_id: str
    status: str
    status_url: str
    estimated_duration_seconds: int = 60


class JobStatusResponse(StrictBaseModel):
    job_id: str
    status: str
    experiment_id: str | None = None
    session_id: str | None = None
    attempt: int
    max_attempts: int
    cancel_requested: bool
    error: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class JobCancelResponse(StrictBaseModel):
    job_id: str
    status: str
    message: str


class SessionCreateRequest(StrictBaseModel):
    initial_state: dict[str, Any] | None = None


class SessionCreateResponse(StrictBaseModel):
    session_id: str
    status: str
    nonce: str
    capability_token: str
    created_at: str


class SessionResumeRequest(StrictBaseModel):
    nonce: str = Field(min_length=16, max_length=64)


class SessionResumeResponse(StrictBaseModel):
    session_id: str
    status: str
    nonce: str
    pending_job_ids: list[str] | None = None
    result: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
    message: str | None = None
