"""Backend-backed positive and negative C2 evidence-membership contracts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, event, text

from shiftguard.agent.registry import ToolRegistry
from shiftguard.agent.execution_authority import authorized_execution_presets
from shiftguard.agent.tools import ToolContext
from shiftguard.agent.schemas import RunExperimentParams
from shiftguard.agent.tools.runs import run_experiment
from shiftguard.experiments.ids import stable_hash
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.migrations import get_alembic_config, upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings
from shiftguard.storage.repositories import ExperimentRepository


@pytest.fixture(params=["sqlite", "postgres"])
def luna_agent_database(request, tmp_path):
    if request.param == "sqlite":
        settings = Settings(
            SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'luna-agent.db'}",
            SHIFTGUARD_ENVIRONMENT="local",
        )
    else:
        url = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("isolated PostgreSQL URL is unavailable")
        settings = Settings(SHIFTGUARD_DB_URL=url, SHIFTGUARD_ENVIRONMENT="hosted")
    try:
        upgrade_database(settings)
        engine = create_engine_for_settings(settings)
    except Exception as exc:
        # Preserve the concrete blocker while redacting connection credentials.
        message = str(exc)
        if request.param == "postgres":
            message = message.replace(os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL", ""), "<test-postgres-url>")
            message = re.sub(r"(?i)(password|passwd|pwd|token)(\s*[=:]\s*)[^\s,;]+", r"\1\2<redacted>", message)
            message = re.sub(r"(postgres(?:ql)?(?:\+\w+)?://)[^\s@]+@", r"\1<redacted>@", message)
        pytest.fail(f"backend setup failed ({type(exc).__name__}): {message[:300]}")
    try:
        yield engine, settings, request.param
    finally:
        engine.dispose()


def _published_fixture(engine, *, mismatch_predictor=False):
    nonce = uuid4().hex
    shared = {
        "predictor": "logistic_regression",
        "predictor_name": "logistic_regression",
        "dataset_id": "a" * 64,
        "evaluation_rows_id": "c" * 64,
        "source_map_id": "d" * 64,
        "test_mask_id": "e" * 64,
        "scenario": "mcar_0_30",
        "budget": 50,
        "status": "scored",
        "fallback_chain": [],
        "labels_consumed": 0,
        "sparse_bin_diagnostics": {
            "affected_fallback_rows": 0,
            "resolution_counts": {"raw": 0},
            "bin_eval_counts": {"0": 10},
            "bin_fallback_counts": {},
            "bin_support": {"0": 10},
            "bin_resolution_counts": {},
            "bin_resolved_maps": {},
            "sparse_prediction_failures": 0,
            "failed_attempts": [{"raw_labels": [0, 1]}],
        },
    }
    raw_condition = {
        **shared, "predictor_id": "b" * 64, "method": "raw", "requested_method": "raw",
        "resolved_method": "raw", "fit_status": "not_applicable",
        "fitted_parameters": {"fit_status": "pipeline_direct", "type": "raw_frozen_pipeline"},
        "metrics": {"brier_score": 0.2, "log_loss": 0.8, "ece": 0.1}, "acquired_record_ids": [],
    }
    raw_condition["condition_id"] = stable_hash(raw_condition)[:24]
    target_condition = {
        **shared,
        "predictor_id": "9" * 64 if mismatch_predictor else "b" * 64,
        "method": "target_temperature", "requested_method": "target_temperature",
        "resolved_method": "target_temperature", "fit_status": "fitted",
        "fitted_parameters": {"fit_status": "fitted", "temperature": 1.2},
        "metrics": {"brier_score": 0.1, "log_loss": 0.7, "ece": 0.05}, "acquired_record_ids": [],
    }
    target_condition["condition_id"] = stable_hash(target_condition)[:24]
    payload = {
        "fixture_nonce": nonce,
        "dataset": {"raw_hash": "f" * 64, "clean_hash": "1" * 64, "path": "C:\\private\\bank.csv"},
        "seeds": {"master": 31001, "private_seed": 999},
        "config": {
            "master_seed": 31001,
            "features": ["age", "job", "marital", "education", "default", "housing", "loan", "pdays", "previous", "poutcome"],
            "role_fractions": {"train": 0.55, "source_cal": 0.15, "pool": 0.1, "final": 0.2},
            "dataset_csv": "C:\\private\\bank.csv",
            "nested": {"api_key": "private-marker", "raw_labels": [0, 1]},
        },
        "protocol": {"api_key": "private-marker", "raw_labels": [0, 1]},
        "conditions": {
            "logistic_regression__mcar_0_30__b50__raw": raw_condition,
            "logistic_regression__mcar_0_30__b50__target_temperature": target_condition,
        },
    }
    logical = stable_hash(payload)
    experiment_id = logical[:24]
    generation_id = str(uuid4())
    execution_id = str(uuid4())
    manifest_hash = hashlib.sha256(nonce.encode()).hexdigest()
    manifest = {"result.json": manifest_hash}
    content_hashes = {"result": manifest_hash, "logical_content": logical}
    audit = {"execution_id": execution_id}
    repo = ExperimentRepository(engine)
    repo.reserve_publication(
        generation_id=generation_id,
        experiment_id=experiment_id,
        full_digest=logical,
        execution_id=execution_id,
        manifest=manifest,
        prepared_payload=payload,
        prepared_audit=audit,
    )
    repo.put(
        experiment_id=experiment_id,
        deterministic_payload=payload,
        content_hashes=content_hashes,
        execution_id=execution_id,
        audit_metadata=audit,
        generation_id=generation_id,
    )
    return experiment_id


def test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup(luna_agent_database):
    engine, settings, backend = luna_agent_database
    experiment_id = _published_fixture(engine)
    registry = ToolRegistry()
    context = ToolContext(
        engine=engine,
        settings=settings,
        session_id="session-no-evidence",
        authorized_experiment_ids=frozenset(),
    )
    calls = [
        ("inspect_missingness", {"experiment_id": experiment_id}),
        ("get_experiment_metadata", {"experiment_id": experiment_id}),
        ("compare_calibrators", {"experiment_id": experiment_id, "scenario": "mcar_0_30"}),
        ("compare_outages", {"experiment_id": experiment_id}),
        ("get_label_budget_curve", {"experiment_id": experiment_id, "scenario": "mcar_0_30"}),
        ("calculate_decision_loss", {"experiment_id": experiment_id, "scenario": "mcar_0_30", "fp_cost": 1.0, "fn_cost": 1.0}),
        ("read_experiment_results", {"experiment_id": experiment_id}),
        ("generate_result_summary", {"experiment_id": experiment_id}),
    ]
    statements: list[str] = []

    def observe(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        for ordinal, (name, params) in enumerate(calls):
            result = registry.dispatch(name, json.dumps(params), context, f"call-{ordinal}")
            assert result.status == "unavailable", (backend, name, result.model_dump())
            assert result.error and "UNAUTHORIZED_EXPERIMENT_REFERENCE" in result.error
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert statements == [], f"{backend} queried storage before denying all eight readers"


def test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata(luna_agent_database):
    engine, settings, _backend = luna_agent_database
    experiment_id = _published_fixture(engine)
    registry = ToolRegistry()
    context = ToolContext(
        engine=engine,
        settings=settings,
        session_id="session-with-selected-evidence",
        authorized_experiment_ids=frozenset({experiment_id}),
    )
    metadata = registry.dispatch("get_experiment_metadata", json.dumps({"experiment_id": experiment_id}), context, "call-meta")
    assert metadata.status == "success"
    metadata_json = json.dumps(metadata.model_dump(mode="json"))
    assert "private-marker" not in metadata_json
    assert "raw_labels" not in metadata_json
    assert "C:\\\\private" not in metadata_json

    result = registry.dispatch("read_experiment_results", json.dumps({"experiment_id": experiment_id}), context, "call-results")
    assert result.status == "success"
    condition = next(iter(result.data["conditions"].values()))
    assert condition["metrics"]["brier_score"] == 0.2
    assert len(condition["sparse_bin_diagnostics"]) == 8
    assert "failed_attempts" not in json.dumps(result.data)

    summary = registry.dispatch("generate_result_summary", json.dumps({"experiment_id": experiment_id}), context, "call-summary")
    assert summary.status == "success"
    assert summary.data["focus"] == "all"
    assert summary.data["total_conditions"] == 2


def test_luna_g6_comparison_requires_bound_predictor_identity(luna_agent_database):
    engine, settings, backend = luna_agent_database
    registry = ToolRegistry()
    for mismatched, expected in ((False, True), (True, False)):
        experiment_id = _published_fixture(engine, mismatch_predictor=mismatched)
        context = ToolContext(engine=engine, settings=settings, session_id="session", authorized_experiment_ids=frozenset({experiment_id}))
        result = registry.dispatch(
            "compare_calibrators",
            json.dumps({"experiment_id": experiment_id, "scenario": "mcar_0_30"}),
            context,
            "call-compare",
        )
        assert result.status == "success", (backend, result.model_dump())
        comparison = result.data["calibrator_comparisons"]["target_temperature"]
        assert comparison["comparison_qualified"] is expected, (backend, comparison)
        if not expected:
            assert comparison["qualification_reason"] == "mismatched_predictor_id"


def test_luna_g6_adhoc_enqueue_requires_current_session_authority(luna_agent_database):
    engine, settings, backend = luna_agent_database
    approved_presets = authorized_execution_presets("Run bank-baseline")
    assert approved_presets == frozenset({"bank-baseline"})

    expired = ContinuationService(engine).create_session()
    with engine.begin() as conn:
        conn.execute(text("UPDATE agent_sessions SET status = 'expired' WHERE id = :sid"), {"sid": expired.id})
    expired_ctx = ToolContext(
        engine=engine, settings=settings, session_id=expired.id,
        authorized_run_presets=approved_presets,
    )
    denied = run_experiment(RunExperimentParams(preset_name="bank-baseline"), expired_ctx, "call-expired")
    assert denied.status == "error", backend
    assert denied.job_id is None
    assert "Session is not active" in (denied.error or ""), backend

    ungranted = ContinuationService(engine).create_session()
    ungranted_ctx = ToolContext(engine=engine, settings=settings, session_id=ungranted.id)
    denied_without_grant = run_experiment(
        RunExperimentParams(preset_name="bank-baseline"), ungranted_ctx, "call-ungranted"
    )
    assert denied_without_grant.status == "error", backend
    assert "EXECUTION_NOT_AUTHORIZED" in (denied_without_grant.error or ""), backend
    assert denied_without_grant.job_id is None
    with engine.connect() as conn:
        admissions = conn.execute(
            text("SELECT COUNT(*) FROM jobs WHERE session_id = :sid"), {"sid": ungranted.id}
        ).scalar_one()
    assert admissions == 0, backend

    active = ContinuationService(engine).create_session()
    active_ctx = ToolContext(
        engine=engine, settings=settings, session_id=active.id,
        authorized_run_presets=approved_presets,
    )
    admitted = run_experiment(RunExperimentParams(preset_name="bank-baseline"), active_ctx, "call-active")
    assert admitted.status == "success", backend
    assert admitted.job_id
