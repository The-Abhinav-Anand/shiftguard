"""Integration tests for durable agent session continuation."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from shiftguard.api.main import create_app
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.queue import JobQueue
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def client_and_queue(tmp_path):
    db_file = tmp_path / "continuation_test.db"
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
    )
    upgrade_database(settings)
    app = create_app(settings)
    with TestClient(app) as test_client:
        queue = JobQueue(test_client.app.state.engine)
        yield test_client, queue


def test_session_lifecycle_and_continuation(client_and_queue):
    client, queue = client_and_queue

    # 1. Create session
    create_res = client.post("/api/v1/agent/sessions", json={"initial_state": {"intent": "fit_models"}})
    assert create_res.status_code == 201
    sdata = create_res.json()
    session_id = sdata["session_id"]
    nonce1 = sdata["nonce"]
    stoken = sdata["capability_token"]
    headers = {"X-Session-Token": stoken}
    assert sdata["status"] == "ACTIVE"

    # 2. Inspect session
    get_res = client.get(f"/api/v1/agent/sessions/{session_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["active_nonce"] == nonce1

    # 3. Enqueue two jobs and bind to session
    job1 = queue.enqueue({"preset_name": "bank-outage-50"}, session_id=session_id)
    job2 = queue.enqueue({"preset_name": "bank-stress"}, session_id=session_id)

    continuation = ContinuationService(client.app.state.engine)
    continuation.bind_jobs_to_session(session_id, [job1.id, job2.id])

    # 4. Resume while jobs pending -> 202 Accepted
    resume_pending = client.post(f"/api/v1/agent/sessions/{session_id}/resume", json={"nonce": nonce1}, headers=headers)
    assert resume_pending.status_code == 202
    assert resume_pending.json()["status"] == "WAITING_FOR_JOB"
    assert set(resume_pending.json()["pending_job_ids"]) == {job1.id, job2.id}

    # 5. Wrong nonce is rejected with 403
    resume_bad_nonce = client.post(f"/api/v1/agent/sessions/{session_id}/resume", json={"nonce": "invalid-nonce-123456789"}, headers=headers)
    assert resume_bad_nonce.status_code == 403

    # 6. Complete both jobs
    claimed1 = queue.claim_next_job("worker-1")
    queue.mark_completed(claimed1.id, claimed1.fencing_token, "exp-1", {"metrics": "ok"})

    claimed2 = queue.claim_next_job("worker-2")
    queue.mark_completed(claimed2.id, claimed2.fencing_token, "exp-2", {"metrics": "ok"})

    # 7. Resume after completion -> 200 OK with deterministic results and fresh nonce
    resume_done = client.post(f"/api/v1/agent/sessions/{session_id}/resume", json={"nonce": nonce1}, headers=headers)
    assert resume_done.status_code == 200
    res_data = resume_done.json()
    assert res_data["status"] == "COMPLETED"
    nonce2 = res_data["nonce"]
    assert nonce2 != nonce1
    assert "result" in res_data
    assert res_data["result"]["overall_status"] == "success"
    assert job1.id in res_data["result"]["jobs"]
    assert job2.id in res_data["result"]["jobs"]

    # 8. Idempotent replay: calling resume again with the new nonce returns the same cached result
    resume_cached = client.post(f"/api/v1/agent/sessions/{session_id}/resume", json={"nonce": nonce2}, headers=headers)
    assert resume_cached.status_code == 200
    assert resume_cached.json()["status"] == "COMPLETED"
    assert resume_cached.json()["result"] == res_data["result"]
