"""Integration tests for Gate 4 API boundary hardening and session security."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from shiftguard.api.main import create_app
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def api_client(tmp_path):
    db_file = tmp_path / "api_security.db"
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
    )
    upgrade_database(settings)
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def test_arbitrary_config_paths_strictly_rejected(api_client):
    """G4-04: API rejects arbitrary config or dataset paths with 422 error envelope."""
    # Attempting to supply outside dataset paths
    payload = {
        "preset_name": "bank-outage-50",
        "config": {"dataset_csv": "C:/outside.csv"},
    }
    res = api_client.post("/api/v1/experiments", json=payload)
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "request_id" in err


def test_server_issued_session_authority_required(api_client):
    """G4-04 / R2-01: Anonymous submission and forged session credentials are strictly rejected."""
    # 1. Anonymous submission without any session headers -> 401 SESSION_REQUIRED
    res_anon = api_client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"})
    assert res_anon.status_code == 401
    assert res_anon.json()["error"]["code"] == "SESSION_REQUIRED"

    # 2. Forged non-existent session ID -> 401 INVALID_SESSION_CREDENTIALS
    res_forged = api_client.post(
        "/api/v1/experiments",
        json={"preset_name": "bank-outage-50"},
        headers={"X-Session-ID": "forged-session-id-12345", "X-Session-Token": "bogus-token"},
    )
    assert res_forged.status_code == 401
    assert res_forged.json()["error"]["code"] == "INVALID_SESSION_CREDENTIALS"

    # 3. Valid session ID but forged capability token -> 401 INVALID_CAPABILITY_TOKEN
    s_res = api_client.post("/api/v1/agent/sessions", json={})
    assert s_res.status_code == 201
    real_sid = s_res.json()["session_id"]
    res_bad_tok = api_client.post(
        "/api/v1/experiments",
        json={"preset_name": "bank-outage-50"},
        headers={"X-Session-ID": real_sid, "X-Session-Token": "wrong-token"},
    )
    assert res_bad_tok.status_code == 401
    assert res_bad_tok.json()["error"]["code"] == "INVALID_CAPABILITY_TOKEN"


def test_cross_session_job_access_denied(api_client):
    """G4-04 / R2-01: Missing session credentials return 401, cross-session read and cancel return 403."""
    # 1. Create two separate agent sessions
    s1_res = api_client.post("/api/v1/agent/sessions", json={})
    assert s1_res.status_code == 201
    s1_id = s1_res.json()["session_id"]
    s1_token = s1_res.json()["capability_token"]

    s2_res = api_client.post("/api/v1/agent/sessions", json={})
    assert s2_res.status_code == 201
    s2_id = s2_res.json()["session_id"]
    s2_token = s2_res.json()["capability_token"]

    # 2. Session 1 submits an experiment job
    sub_res = api_client.post(
        "/api/v1/experiments",
        json={"preset_name": "bank-outage-50", "session_id": s1_id},
        headers={"X-Session-ID": s1_id, "X-Session-Token": s1_token},
    )
    assert sub_res.status_code == 202
    job_id = sub_res.json()["job_id"]

    # 3. Missing credentials -> 401 MISSING_SESSION_CREDENTIALS
    read_no_auth = api_client.get(f"/api/v1/jobs/{job_id}")
    assert read_no_auth.status_code == 401
    assert read_no_auth.json()["error"]["code"] == "MISSING_SESSION_CREDENTIALS"

    cancel_no_auth = api_client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancel_no_auth.status_code == 401
    assert cancel_no_auth.json()["error"]["code"] == "MISSING_SESSION_CREDENTIALS"

    # 4. Session 1 reads its own job with valid credentials -> 200 OK
    read_s1 = api_client.get(f"/api/v1/jobs/{job_id}", headers={"X-Session-ID": s1_id, "X-Session-Token": s1_token})
    assert read_s1.status_code == 200
    assert read_s1.json()["session_id"] == s1_id

    # 5. Session 2 attempts to read Session 1's job -> 403 Forbidden
    read_s2 = api_client.get(f"/api/v1/jobs/{job_id}", headers={"X-Session-ID": s2_id, "X-Session-Token": s2_token})
    assert read_s2.status_code == 403
    assert read_s2.json()["error"]["code"] == "CROSS_SESSION_ACCESS_DENIED"

    # 6. Session 2 attempts to cancel Session 1's job -> 403 Forbidden
    cancel_s2 = api_client.post(f"/api/v1/jobs/{job_id}/cancel", headers={"X-Session-ID": s2_id, "X-Session-Token": s2_token})
    assert cancel_s2.status_code == 403
    assert cancel_s2.json()["error"]["code"] == "CROSS_SESSION_ACCESS_DENIED"


def test_session_active_job_quota_enforced(api_client):
    """G4-04 / R2-05: Active job quota per session (restored max 2) returns 429 when exceeded."""
    # Create valid session
    s_res = api_client.post("/api/v1/agent/sessions", json={})
    assert s_res.status_code == 201
    s_id = s_res.json()["session_id"]
    s_token = s_res.json()["capability_token"]
    headers = {"X-Session-ID": s_id, "X-Session-Token": s_token}

    # Enqueue 2 active jobs (the approved quota limit)
    for i in range(2):
        res = api_client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=headers)
        assert res.status_code == 202

    # 3rd submission must trigger 429 quota exceeded
    res3 = api_client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=headers)
    assert res3.status_code == 429
    err = res3.json()["error"]
    assert err["code"] == "SESSION_QUOTA_EXCEEDED"
