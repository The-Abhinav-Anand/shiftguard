"""Integration tests for agent REST API endpoints, auth verification, and cross-session isolation."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from starlette.testclient import TestClient

from shiftguard.agent.provider import ProviderResponse, ScriptedProvider
from shiftguard.agent.schemas import FunctionCall, ToolCall
from shiftguard.api.test_harness import create_scripted_test_app
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


HISTORICAL_0009_DB = (
    Path(__file__).resolve().parents[2].parent / "verification" / "gate6"
    / "offline-f72afeff-0cad-438f-bccb-157a39b08ef1" / "shiftguard.sqlite"
)


@pytest.fixture
def agent_api_client(tmp_path):
    db_file = tmp_path / "test_api.db"
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
        environment="local",
        embedded_worker=False,
        agent_enabled=True,
    )
    upgrade_database(settings)
    r1 = ProviderResponse(content="Hello from test provider!", tool_calls=None)
    scripted = ScriptedProvider(responses=[r1])
    app = create_scripted_test_app(settings, provider=scripted)

    with TestClient(app) as client:
        yield client


def test_agent_status_endpoint(agent_api_client: TestClient):
    resp = agent_api_client.get("/api/v1/agent/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "available" in data
    assert data["max_turns"] == 6
    assert data["max_calls"] == 8


def test_unauthenticated_request_rejected_401(agent_api_client: TestClient):
    # Missing session headers
    resp = agent_api_client.post(
        "/api/v1/agent/requests",
        json={"prompt": "test prompt", "idempotency_key": "key_1"},
    )
    assert resp.status_code == 401
    err = resp.json().get("error", {})
    assert err.get("code") == "MISSING_SESSION_CREDENTIALS"


def test_authenticated_request_submit_and_retrieve(agent_api_client: TestClient):
    # 1. Create session
    s_resp = agent_api_client.post("/api/v1/agent/sessions", json={})
    assert s_resp.status_code == 201
    s_data = s_resp.json()
    session_id = s_data["session_id"]
    token = s_data["capability_token"]
    headers = {"X-Session-ID": session_id, "X-Session-Token": token}

    # 2. Submit agent request
    submit_resp = agent_api_client.post(
        "/api/v1/agent/requests",
        json={"prompt": "Inspect bank dataset", "idempotency_key": "req_key_001"},
        headers=headers,
    )
    assert submit_resp.status_code == 200
    r_data = submit_resp.json()
    assert r_data["status"] == "COMPLETED"
    req_id = r_data["request_id"]

    # 3. Retrieve agent request
    get_resp = agent_api_client.get(f"/api/v1/agent/requests/{req_id}", headers=headers)
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["request_id"] == req_id
    assert get_data["session_id"] == session_id


def test_cross_session_access_denied_403(agent_api_client: TestClient):
    # Session 1 creates request
    s1 = agent_api_client.post("/api/v1/agent/sessions", json={}).json()
    h1 = {"X-Session-ID": s1["session_id"], "X-Session-Token": s1["capability_token"]}

    submit_resp = agent_api_client.post(
        "/api/v1/agent/requests",
        json={"prompt": "Private inquiry", "idempotency_key": "priv_key"},
        headers=h1,
    )
    req_id = submit_resp.json()["request_id"]

    # Session 2 attempts to read Session 1's request
    s2 = agent_api_client.post("/api/v1/agent/sessions", json={}).json()
    h2 = {"X-Session-ID": s2["session_id"], "X-Session-Token": s2["capability_token"]}

    cross_resp = agent_api_client.get(f"/api/v1/agent/requests/{req_id}", headers=h2)
    assert cross_resp.status_code == 403
    err = cross_resp.json().get("error", {})
    assert err.get("code") == "CROSS_SESSION_ACCESS_DENIED"


def test_resume_nonce_is_server_issued_and_replays_exact_http_receipt(agent_api_client: TestClient):
    provider = agent_api_client.app.state.agent_provider
    provider.responses = [ProviderResponse(tool_calls=[ToolCall(
        id="api_run_original",
        function=FunctionCall(name="run_experiment", arguments='{"preset_name":"bank-baseline"}'),
    )])]
    session = agent_api_client.post("/api/v1/agent/sessions", json={}).json()
    headers = {
        "X-Session-ID": session["session_id"],
        "X-Session-Token": session["capability_token"],
    }
    submitted = agent_api_client.post(
        "/api/v1/agent/requests",
        json={"prompt": "Run the baseline", "idempotency_key": "resume_receipt"},
        headers=headers,
    )
    assert submitted.status_code == 202
    request_id = submitted.json()["request_id"]
    original_nonce = submitted.json()["resume_nonce"]
    endpoint = f"/api/v1/agent/requests/{request_id}/resume"

    first = agent_api_client.post(endpoint, json={"nonce": original_nonce}, headers=headers)
    invalid = agent_api_client.post(endpoint, json={"nonce": "not-server-issued"}, headers=headers)
    replay = agent_api_client.post(endpoint, json={"nonce": original_nonce}, headers=headers)

    assert first.status_code == replay.status_code == 202
    assert first.json() == replay.json()
    assert first.json()["resume_nonce"] != original_nonce
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_RESUME_NONCE"
    assert len(provider.history) == 1


@pytest.mark.parametrize("replay_kind", ["intent_retry", "receipt_resume"])
def test_luna_g6_protocol_historical_0009_same_session_retry_or_resume_binds_without_reexecution(
    tmp_path, replay_kind,
):
    assert HISTORICAL_0009_DB.is_file()
    db_file = tmp_path / "historical-0009-copy.sqlite"
    shutil.copyfile(HISTORICAL_0009_DB, db_file)
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
        environment="local",
        embedded_worker=False,
        agent_enabled=True,
    )
    upgrade_database(settings)
    engine = create_engine(settings.db_url)
    with engine.connect() as conn:
        before_request = conn.execute(text("""
            SELECT id, session_id, intent_key, canonical_body_hash, prompt, status,
                   generation, lease_expires_at, active_job_id, updated_at,
                   final_response_json, authority_token_hash
            FROM agent_requests ORDER BY created_at LIMIT 1
        """)).mappings().one()
        session = conn.execute(text("""
            SELECT status, capability_token FROM agent_sessions WHERE id=:id
        """), {"id": before_request["session_id"]}).mappings().one()
        assert before_request["status"] == "COMPLETED"
        assert session["status"].upper() == "ACTIVE"
        assert hashlib.sha256(before_request["prompt"].strip().encode()).hexdigest() == before_request["canonical_body_hash"]
        assert before_request["authority_token_hash"] is None
        before_trace = conn.execute(text("""
            SELECT id, job_id, status, result_json FROM agent_tool_executions
            WHERE request_id=:id ORDER BY ordinal
        """), {"id": before_request["id"]}).all()
        before_receipts = conn.execute(text("""
            SELECT id, nonce, status_code, response_json FROM agent_continuation_receipts
            WHERE request_id=:id ORDER BY created_at, id
        """), {"id": before_request["id"]}).all()
        assert before_trace and before_receipts
    engine.dispose()

    provider = ScriptedProvider(responses=[])
    app = create_scripted_test_app(settings, provider=provider)
    headers = {
        "X-Session-ID": before_request["session_id"],
        "X-Session-Token": session["capability_token"],
    }
    with TestClient(app) as client:
        if replay_kind == "intent_retry":
            replay = client.post("/api/v1/agent/requests", json={
                "prompt": before_request["prompt"],
                "idempotency_key": before_request["intent_key"],
            }, headers=headers)
            assert replay.status_code == 200
            assert replay.json()["request_id"] == before_request["id"]
            assert replay.json()["status"] == "COMPLETED"
        else:
            receipt = before_receipts[-1]
            replay = client.post(
                f"/api/v1/agent/requests/{before_request['id']}/resume",
                json={"nonce": receipt.nonce}, headers=headers,
            )
            assert replay.status_code == receipt.status_code
            assert replay.json() == json.loads(receipt.response_json)
        assert provider.history == []
        with app.state.engine.connect() as conn:
            after_request = conn.execute(text("""
                SELECT id, session_id, intent_key, canonical_body_hash, status,
                       generation, lease_expires_at, active_job_id, updated_at,
                       final_response_json, authority_token_hash
                FROM agent_requests WHERE id=:id
            """), {"id": before_request["id"]}).mappings().one()
            after_trace = conn.execute(text("""
                SELECT id, job_id, status, result_json FROM agent_tool_executions
                WHERE request_id=:id ORDER BY ordinal
            """), {"id": before_request["id"]}).all()
            after_receipts = conn.execute(text("""
                SELECT id, nonce, status_code, response_json FROM agent_continuation_receipts
                WHERE request_id=:id ORDER BY created_at, id
            """), {"id": before_request["id"]}).all()

    assert after_request["authority_token_hash"] == hashlib.sha256(
        session["capability_token"].strip().encode()
    ).hexdigest()
    assert {
        key: after_request[key] for key in (
            "id", "session_id", "intent_key", "canonical_body_hash", "status", "generation",
            "lease_expires_at", "active_job_id", "updated_at", "final_response_json",
        )
    } == {
        key: before_request[key] for key in (
            "id", "session_id", "intent_key", "canonical_body_hash", "status", "generation",
            "lease_expires_at", "active_job_id", "updated_at", "final_response_json",
        )
    }
    assert after_trace == before_trace
    assert after_receipts == before_receipts
