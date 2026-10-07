"""Permanent C2 regressions for safe tool arguments, projections, and execution authority."""

from __future__ import annotations

import json

from sqlalchemy import create_engine

from shiftguard.agent.policy import APPROVED_FOCUSES, APPROVED_METHODS, compute_repair_signature
from shiftguard.agent.registry import (
    ToolRegistry,
    prepare_tool_call_arguments,
    safe_arguments_for_storage,
    safe_tool_error,
)
from shiftguard.agent.schemas import GenerateResultSummaryParams, RunExperimentParams, ToolResult
from shiftguard.agent.tools import ToolContext
from shiftguard.agent.tools.projections import project_tool_result
from shiftguard.agent.tools.runs import run_experiment
from shiftguard.jobs.models import JobRecord, JobStatus
from shiftguard.settings import Settings


def test_luna_g6_safe_argument_preparation_drops_rejected_values():
    registry = ToolRegistry()
    invalid = prepare_tool_call_arguments("inspect_dataset", '{"dataset_id":"bank","api_key":"private-marker"}', registry)
    assert not invalid.ok
    assert safe_arguments_for_storage(invalid) == {"rejected": "INVALID_ARGUMENTS"}
    assert "private-marker" not in (invalid.safe_error or "")
    assert "api_key" not in (invalid.safe_error or "")

    oversized = prepare_tool_call_arguments("inspect_dataset", '{"dataset_id":"bank","blob":"' + "X" * 200_000 + '"}', registry)
    assert not oversized.ok
    assert safe_arguments_for_storage(oversized) == {"rejected": "INVALID_ARGUMENTS"}

    accepted = prepare_tool_call_arguments("inspect_dataset", '{"dataset_id":"bank"}', registry)
    assert accepted.ok
    assert accepted.accepted_arguments == {"dataset_id": "bank"}

    invalid_dataset = prepare_tool_call_arguments("inspect_dataset", '{"dataset_id":"C:\\\\private\\\\bank.csv"}', registry)
    assert not invalid_dataset.ok
    assert safe_arguments_for_storage(invalid_dataset) == {"rejected": "INVALID_ARGUMENTS"}


def test_luna_g6_error_projection_never_echoes_private_input_or_nested_config():
    result = ToolResult(
        tool_name="get_experiment_metadata",
        tool_call_id="call_1",
        status="success",
        data={
            "experiment_id": "exp_abc123",
            "generation_id": "gen-1",
            "execution_id": "exec-1",
            "published_at": "2026-10-01T00:00:00Z",
            "condition_count": 1,
            "config": {
                "master_seed": 31001,
                "dataset_csv": "C:\\private\\bank.csv",
                "nested": {"api_key": "private-marker", "raw_labels": [0, 1]},
                "role_fractions": {"train": 0.55, "source_cal": 0.15, "pool": 0.1, "final": 0.2},
            },
            "dataset": {"clean_hash": "a" * 64, "path": "C:\\private\\bank.csv"},
            "protocol": {"raw_labels": [0, 1], "api_key": "private-marker"},
            "content_hashes": {"logical_content": "b" * 64, "private_path": "C:\\private\\bank.csv"},
        },
    )
    projected = project_tool_result(result).model_dump(mode="json")
    encoded = json.dumps(projected)
    assert "private-marker" not in encoded
    assert "raw_labels" not in encoded
    assert "C:\\\\private" not in encoded
    assert projected["data"]["config"] == {"master_seed": 31001, "role_fractions": {"train": 0.55, "source_cal": 0.15, "pool": 0.1, "final": 0.2}}
    assert projected["data"]["protocol"] == {}

    safe_error = safe_tool_error("INVALID_ARGUMENTS: api_key=private-marker")
    assert safe_error == "INVALID_ARGUMENTS: Arguments were rejected."
    assert safe_tool_error("   ") is None


def test_luna_g6_run_projection_rebuilds_notes_from_safe_job_fields():
    result = ToolResult(
        tool_name="run_experiment", tool_call_id="call_run", status="success", is_side_effect=True,
        job_id="job-123",
        data={"job_id": "job-123", "status": "queued", "preset_name": "bank-baseline",
              "master_seed": 31001, "created_at": "C:\\private\\bank.csv", "notes": "private-marker"},
    )
    projected = project_tool_result(result).model_dump(mode="json")
    encoded = json.dumps(projected)
    assert "private-marker" not in encoded
    assert "C:\\\\private" not in encoded
    assert projected["job_id"] == "job-123"
    assert projected["data"]["notes"].startswith("Job ")
    assert projected["data"]["created_at"] is None


def test_luna_g6_summary_default_and_semantic_allowlists_match():
    parsed = GenerateResultSummaryParams.model_validate({"experiment_id": "exp_abc123"})
    assert parsed.focus == "all"
    assert APPROVED_FOCUSES == frozenset({"all", "fallback", "outages", "calibration"})
    assert "all" not in APPROVED_METHODS
    assert GenerateResultSummaryParams.model_fields["focus"].default == "all"


def test_luna_g6_repair_signature_is_normalized_and_value_free():
    first = compute_repair_signature("compare_calibrators", "INVALID_ARGUMENTS: scenario rejected private-marker")
    second = compute_repair_signature("COMPARE_CALIBRATORS", "invalid_arguments: scenario rejected other-value")
    assert first == second
    assert "private-marker" not in first


def test_luna_g6_request_bound_run_requires_fenced_admission_callback(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'request-bound.db'}"
    engine = create_engine(db_url)
    ctx = ToolContext(
        engine=engine,
        settings=Settings(SHIFTGUARD_DB_URL=db_url),
        session_id="session-authorized",
        request_id="request-bound",
        authorized_run_presets=frozenset({"bank-baseline"}),
    )
    result = run_experiment(RunExperimentParams(preset_name="bank-baseline"), ctx, "call_1")
    assert result.status == "error"
    assert "fenced admission" in (result.error or "").lower()
    assert result.job_id is None


def test_luna_g6_request_bound_run_uses_canonical_admission_result(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'canonical-admission.db'}"
    engine = create_engine(db_url)
    seen: list[dict[str, str]] = []

    def admit(params: dict[str, str]) -> JobRecord:
        seen.append(params)
        return JobRecord(
            id="job-1", payload_hash="a" * 64, status=JobStatus.QUEUED,
            request_params=params, session_id="session-1",
        )

    ctx = ToolContext(
        engine=engine,
        settings=Settings(SHIFTGUARD_DB_URL=db_url),
        session_id="session-1",
        request_id="request-1",
        ordinal=2,
        admit_job=admit,
        authorized_run_presets=frozenset({"bank-baseline"}),
    )
    result = run_experiment(RunExperimentParams(preset_name="bank-baseline"), ctx, "call_2")
    assert result.status == "success"
    assert result.job_id == "job-1"
    assert seen == [{"preset_name": "bank-baseline"}]
