"""Integration tests for G4-01 managed worker lifespan and autonomous execution."""

from __future__ import annotations

import time
import pytest
from starlette.testclient import TestClient

from shiftguard.api.main import create_app
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


def test_managed_worker_lifespan_executes_http_submitted_job(tmp_path):
    """G4-01: Prove an HTTP-submitted job completes autonomously via FastAPI lifespan worker.
    
    The test NEVER calls worker.run_once or touches worker internals.
    The background worker thread managed by the application lifespan claims,
    executes, and marks the job completed.
    """
    db_file = tmp_path / "lifecycle.db"
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
        SHIFTGUARD_EMBEDDED_WORKER=True,
        SHIFTGUARD_WORKER_POLL_INTERVAL=0.1,
        SHIFTGUARD_RECOVERY_INTERVAL=1.0,
    )
    upgrade_database(settings)
    app = create_app(settings)

    with TestClient(app) as client:
        # 0. Create agent session
        s_res = client.post("/api/v1/agent/sessions", json={})
        assert s_res.status_code == 201
        sid = s_res.json()["session_id"]
        stoken = s_res.json()["capability_token"]
        headers = {"X-Session-ID": sid, "X-Session-Token": stoken}

        # 1. Submit experiment job via public REST API with session authority
        sub_res = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=headers)
        assert sub_res.status_code == 202
        job_id = sub_res.json()["job_id"]
        status_url = sub_res.json()["status_url"]

        # 2. Poll status URL until job reaches terminal completed state
        # The background worker thread in lifespan is doing the work!
        max_wait = 30.0
        start = time.time()
        final_data = None
        while time.time() - start < max_wait:
            res = client.get(status_url, headers=headers)
            assert res.status_code == 200
            data = res.json()
            if data["status"] in ("completed", "failed"):
                final_data = data
                break
            time.sleep(0.2)

        assert final_data is not None, f"Job {job_id} did not complete within {max_wait}s"
        assert final_data["status"] == "completed", f"Job failed: {final_data.get('error')}"
        assert final_data["experiment_id"] is not None
        assert final_data["completed_at"] is not None

        # 3. Verify published experiment is retrievable via public API
        exp_id = final_data["experiment_id"]
        exp_res = client.get(f"/api/v1/experiments/{exp_id}")
        assert exp_res.status_code == 200
        assert exp_res.json()["experiment_id"] == exp_id
