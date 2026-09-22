"""Integration tests for Gate 4 typed REST API and jobs lifecycle."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from shiftguard.api.main import create_app
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "api_test.db"
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
    )
    upgrade_database(settings)
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client):
    s_res = client.post("/api/v1/agent/sessions", json={})
    assert s_res.status_code == 201
    sid = s_res.json()["session_id"]
    stoken = s_res.json()["capability_token"]
    return {"X-Session-ID": sid, "X-Session-Token": stoken}


def test_health_live_and_ready(client):
    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json() == {"status": "ok"}

    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200
    data = res_ready.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"


def test_approved_metadata_presets_only(client):
    res_ds = client.get("/api/v1/datasets")
    assert res_ds.status_code == 200
    datasets = res_ds.json()["datasets"]
    assert any(d["id"] == "bank" for d in datasets)
    assert any(d["id"] == "adult_train" for d in datasets)

    # Check individual dataset metadata
    res_bank = client.get("/api/v1/datasets/bank")
    assert res_bank.status_code == 200
    assert res_bank.json()["features_count"] == 16
    assert "y" not in res_bank.json()  # No raw labels leaked

    res_models = client.get("/api/v1/models")
    assert res_models.status_code == 200
    models = res_models.json()["models"]
    assert len(models) == 2
    assert {m["id"] for m in models} == {"logistic_regression", "random_forest"}

    res_scenarios = client.get("/api/v1/scenarios")
    assert res_scenarios.status_code == 200
    scenarios = res_scenarios.json()["scenarios"]
    assert any(s["id"] == "history_block_0_50" for s in scenarios)


def test_submit_experiment_returns_202_and_status_url(client, auth_headers):
    payload = {"preset_name": "bank-outage-50"}
    res = client.post("/api/v1/experiments", json=payload, headers=auth_headers)
    assert res.status_code == 202
    data = res.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["status_url"] == f"/api/v1/jobs/{data['job_id']}"
    assert data["estimated_duration_seconds"] == 60

    # Inspect status
    job_res = client.get(data["status_url"], headers=auth_headers)
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["job_id"] == data["job_id"]
    assert job_data["status"] == "queued"
    assert job_data["attempt"] == 0
    assert job_data["cancel_requested"] is False


def test_idempotent_submit_replay_and_conflict(client, auth_headers):
    key = "user-idempotency-key-001"
    payload1 = {"preset_name": "bank-outage-50"}
    payload2 = {"preset_name": "bank-stress"}

    h1 = {**auth_headers, "Idempotency-Key": key}

    # First submit
    res1 = client.post("/api/v1/experiments", json=payload1, headers=h1)
    assert res1.status_code == 202
    job_id1 = res1.json()["job_id"]

    # Replay with same key and payload -> returns same job_id
    res2 = client.post("/api/v1/experiments", json=payload1, headers=h1)
    assert res2.status_code == 202
    assert res2.json()["job_id"] == job_id1

    # Conflict with same key but different payload -> returns 409
    res3 = client.post("/api/v1/experiments", json=payload2, headers=h1)
    assert res3.status_code == 409
    err = res3.json()["error"]
    assert err["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_extra_fields_forbidden_returns_422_error_envelope(client, auth_headers):
    # extra field 'unsupported_field'
    payload = {"preset_name": "bank-outage-50", "unsupported_field": "exploit"}
    res = client.post("/api/v1/experiments", json=payload, headers=auth_headers)
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "request_id" in err


def test_cancel_queued_job(client, auth_headers):
    res_submit = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=auth_headers)
    assert res_submit.status_code == 202
    job_id = res_submit.json()["job_id"]

    # Cancel queued job
    res_cancel = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_headers)
    assert res_cancel.status_code == 202
    data = res_cancel.json()
    assert data["job_id"] == job_id
    assert data["status"] == "cancelled"

    # Verify status is cancelled
    res_status = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert res_status.json()["status"] == "cancelled"

    # Cancelling again returns 409 Conflict (terminal)
    res_cancel_again = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_headers)
    assert res_cancel_again.status_code == 409
    assert res_cancel_again.json()["error"]["code"] == "JOB_ALREADY_TERMINAL"


def test_end_to_end_worker_execution_and_results_retrieval(client, auth_headers):
    from shiftguard.jobs.queue import JobQueue
    from shiftguard.jobs.worker import ExperimentWorker

    # 1. Enqueue job
    res_submit = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=auth_headers)
    assert res_submit.status_code == 202
    job_id = res_submit.json()["job_id"]

    # 2. Worker executes job
    queue = JobQueue(client.app.state.engine)
    worker = ExperimentWorker(settings=client.app.state.settings, heartbeat_interval=1, lease_seconds=10)
    executed = worker.run_once(queue)

    assert executed is not None
    assert executed.status.value == "completed"
    assert executed.experiment_id is not None
    exp_id = executed.experiment_id

    # 3. Check job endpoint
    job_res = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert job_res.status_code == 200
    assert job_res.json()["status"] == "completed"
    assert job_res.json()["experiment_id"] == exp_id

    # 4. Check experiments endpoint
    exp_res = client.get(f"/api/v1/experiments/{exp_id}")
    assert exp_res.status_code == 200
    assert exp_res.json()["experiment_id"] == exp_id

    # 5. Check metrics endpoint
    metrics_res = client.get(f"/api/v1/experiments/{exp_id}/metrics")
    assert metrics_res.status_code == 200
    assert "conditions" in metrics_res.json()
    assert "no_outage_raw" in metrics_res.json()["conditions"]

    # 6. Check artifacts endpoint
    art_res = client.get(f"/api/v1/experiments/{exp_id}/artifacts")
    assert art_res.status_code == 200
    artifacts = art_res.json()["artifacts"]
    assert any(a["name"] == "config" for a in artifacts)
    assert any(a["name"] == "masks" for a in artifacts)

    # 7. Download artifact file safely
    dl_res = client.get(f"/api/v1/experiments/{exp_id}/artifacts/config")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/json"
    assert "features" in dl_res.json()


def test_artifact_path_traversal_rejection(client):
    # Traversal in artifact name is rejected
    res = client.get("/api/v1/experiments/exp-123/artifacts/..%2F..%2Fetc")
    assert res.status_code in (400, 404)

