"""Ordinary startup authority and explicitly scripted harness regressions."""

from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from shiftguard.agent.provider import ScriptedProvider
from shiftguard.api.main import create_app
from shiftguard.api.test_harness import create_scripted_test_app
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.recovery import recover_expired_leases
from shiftguard.jobs.queue import JobQueue
from shiftguard.settings import Settings


def _clear_test_flags(monkeypatch):
    monkeypatch.delenv("SHIFTGUARD_AGENT_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("SHIFTGUARD_ALLOW_TEST_SCRIPTED_PROVIDER", raising=False)


def test_luna_g6_startup_p07_positive_explicit_harness_labeled(monkeypatch, tmp_path):
    _clear_test_flags(monkeypatch)
    settings = Settings(
        db_url=f"sqlite:///{tmp_path / 'harness.sqlite'}",
        artifact_root=tmp_path / "artifacts",
        agent_enabled=False,
        embedded_worker=False,
        _env_file=None,
    )
    app = create_scripted_test_app(settings)
    assert app.state.test_harness_metadata == {
        "provider_kind": "scripted",
        "evidence_mode": "scripted",
        "live_provider_calls": False,
    }
    with TestClient(app) as client:
        response = client.get("/api/v1/agent/status")
        assert response.status_code == 200
        assert response.headers["X-Shiftguard-Test-Harness"] == "scripted"
        body = response.json()
        assert body["enabled"] is True
        assert body["available"] is True
        assert body["provider_kind"] == "scripted"
        assert body["model"] == "scripted-test-harness"


def test_luna_g6_startup_p07_positive_harness_accepts_explicit_script(monkeypatch, tmp_path):
    _clear_test_flags(monkeypatch)
    settings = Settings(
        db_url=f"sqlite:///{tmp_path / 'provided-script.sqlite'}",
        artifact_root=tmp_path / "artifacts",
        agent_enabled=False,
        embedded_worker=False,
        _env_file=None,
    )
    scripted = ScriptedProvider()
    app = create_scripted_test_app(settings, provider=scripted)
    assert app.state.agent_provider is scripted
    assert app.state.test_harness_metadata["provider_kind"] == "scripted"


def test_luna_g6_startup_p07_negative_harness_rejects_unapproved_provider(monkeypatch, tmp_path):
    _clear_test_flags(monkeypatch)
    settings = Settings(
        db_url=f"sqlite:///{tmp_path / 'unapproved-provider.sqlite'}",
        environment="local",
        artifact_root=tmp_path / "artifacts",
        _env_file=None,
    )
    with pytest.raises(TypeError, match="built-in scripted providers"):
        create_scripted_test_app(settings, provider=object())


def test_luna_g6_startup_p07_negative_local_disabled(monkeypatch, tmp_path):
    _clear_test_flags(monkeypatch)
    settings = Settings(
        db_url=f"sqlite:///{tmp_path / 'ordinary.sqlite'}",
        artifact_root=tmp_path / "artifacts",
        agent_enabled=False,
        embedded_worker=False,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/v1/agent/status").json()
        assert body["enabled"] is False
        assert body["available"] is False
        assert body["provider_kind"] == "disabled"


@pytest.mark.skipif(not os.getenv("SHIFTGUARD_TEST_POSTGRES_URL"), reason="isolated PostgreSQL16 service unavailable")
def test_luna_g6_startup_p07_negative_hosted_disabled(monkeypatch, tmp_path):
    url = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]
    admin = create_engine(url, connect_args={"connect_timeout": 3})
    schema = "luna4_hosted_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    monkeypatch.setenv("SHIFTGUARD_AGENT_PROVIDER_MODE", "scripted")
    monkeypatch.setenv("SHIFTGUARD_ALLOW_TEST_SCRIPTED_PROVIDER", "true")
    settings = Settings(
        db_url=scoped_url,
        environment="hosted",
        artifact_root=tmp_path / "hosted-artifacts",
        agent_enabled=False,
        embedded_worker=False,
        _env_file=None,
    )
    try:
        with pytest.raises(RuntimeError, match="test-only provider flags"):
            with TestClient(create_app(settings)):
                pytest.fail("hosted application accepted scripted-provider flags")
        _clear_test_flags(monkeypatch)
        with TestClient(create_app(settings)) as client:
            body = client.get("/api/v1/agent/status").json()
            assert body["enabled"] is False
            assert body["available"] is False
            assert body["provider_kind"] == "disabled"
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize("flag,value", [
    ("SHIFTGUARD_AGENT_PROVIDER_MODE", "scripted"),
    ("SHIFTGUARD_ALLOW_TEST_SCRIPTED_PROVIDER", "true"),
])
def test_luna_g6_startup_p07_test_flags_rejected(monkeypatch, tmp_path, flag, value):
    _clear_test_flags(monkeypatch)
    monkeypatch.setenv(flag, value)
    settings = Settings(
        db_url=f"sqlite:///{tmp_path / 'flag.sqlite'}",
        artifact_root=tmp_path / "artifacts",
        agent_enabled=False,
        embedded_worker=False,
        _env_file=None,
    )
    with pytest.raises(RuntimeError, match="test-only provider flags"):
        with TestClient(create_app(settings)):
            pass


def test_luna_g6_startup_p07_injected_provider_rejected(monkeypatch, tmp_path):
    _clear_test_flags(monkeypatch)
    settings = Settings(
        db_url=f"sqlite:///{tmp_path / 'injected.sqlite'}",
        artifact_root=tmp_path / "artifacts",
        agent_enabled=False,
        embedded_worker=False,
        _env_file=None,
    )
    app = create_app(settings)
    app.state.agent_provider = ScriptedProvider()
    with pytest.raises(RuntimeError, match="provider injection"):
        with TestClient(app):
            pass


def test_luna_g6_startup_scripted_factory_refuses_hosted_profile(tmp_path):
    settings = Settings(
        db_url="postgresql+psycopg://user:password@localhost/db",
        environment="hosted",
        _env_file=None,
    )
    with pytest.raises(ValueError, match="local SQLite"):
        create_scripted_test_app(settings)


def _scenario_app_settings(tmp_path):
    return Settings(
        db_url=f"sqlite:///{tmp_path / 'worker-scenarios.sqlite'}",
        environment="local",
        artifact_root=tmp_path / "artifacts",
        agent_enabled=False,
        embedded_worker=True,
        worker_poll_interval=0.02,
        recovery_interval=3600,
        _env_file=None,
    )


def _wait_for_scenario(client, scenario_id, expected_state, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/__test__/worker/scenarios/{scenario_id}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json"), response.text[:160]
        state = response.json()
        if state["state"] == expected_state:
            return state
        time.sleep(0.05)
    pytest.fail(f"worker scenario did not reach {expected_state!r}; last state: {state!r}")


def _wait_for_claim(engine, job_id, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            claimed = connection.execute(
                text("SELECT 1 FROM job_events WHERE job_id = :job_id AND event_type = 'CLAIMED' LIMIT 1"),
                {"job_id": job_id},
            ).first()
        if claimed:
            return
        time.sleep(0.02)
    pytest.fail("managed worker did not claim the queued backlog job")


def _wait_for_completed_job(queue, job_id, timeout=120):
    """Give real backlog computation its own budget, separate from the next heartbeat."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = queue.get_job(job_id)
        assert job is not None
        if job.status.value == "completed":
            return job
        assert job.status.value not in {"failed", "cancelled"}, (job.status.value, job.error)
        time.sleep(0.05)
    pytest.fail(f"backlog job did not complete; last status: {job.status.value!r}")


def test_luna_g6_startup_scenarios_pause_a_real_claim_and_cancel_through_queue(tmp_path, monkeypatch):
    _clear_test_flags(monkeypatch)
    app = create_scripted_test_app(_scenario_app_settings(tmp_path))
    with TestClient(app) as client:
        session = ContinuationService(app.state.engine).create_session()
        armed = client.post("/__test__/worker/scenarios", json={"outcome": "pause_next", "session_id": session.id})
        assert armed.status_code == 200
        scenario_id = armed.json()["scenario_id"]
        job = JobQueue(app.state.engine).enqueue(
            {"preset_name": "bank-outage-50"}, session_id=session.id, max_attempts=1,
        )

        paused = _wait_for_scenario(client, scenario_id, "paused")
        assert paused["job_id"] == job.id
        claimed = JobQueue(app.state.engine).get_job(job.id)
        assert claimed is not None
        assert claimed.status.value == "running"
        assert claimed.worker_id
        assert claimed.fencing_token
        with app.state.engine.connect() as connection:
            event_types = {
                row[0] for row in connection.execute(
                    text("SELECT event_type FROM job_events WHERE job_id = :job_id"), {"job_id": job.id}
                ).fetchall()
            }
        assert {"ENQUEUED", "CLAIMED", "HEARTBEAT"}.issubset(event_types)

        early_release = client.post(f"/__test__/worker/scenarios/{scenario_id}/release")
        assert early_release.status_code == 409
        cancelled = client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"X-Session-ID": session.id, "X-Session-Token": session.capability_token},
        )
        assert cancelled.status_code == 202
        assert cancelled.json()["status"] == "cancel_requested"
        released = client.post(f"/__test__/worker/scenarios/{scenario_id}/release")
        assert released.status_code == 200

        deadline = time.monotonic() + 10
        terminal = None
        while time.monotonic() < deadline:
            terminal = JobQueue(app.state.engine).get_job(job.id)
            if terminal and terminal.status.value == "cancelled":
                break
            time.sleep(0.05)
        assert terminal is not None and terminal.status.value == "cancelled"
        state = _wait_for_scenario(client, scenario_id, "cancelled")
        assert state == {"state": "cancelled", "job_id": job.id}


def test_luna_g6_startup_scenarios_release_after_real_queue_recovery_terminalizes_cancel(tmp_path, monkeypatch):
    _clear_test_flags(monkeypatch)
    app = create_scripted_test_app(_scenario_app_settings(tmp_path))
    with TestClient(app) as client:
        session = ContinuationService(app.state.engine).create_session()
        armed = client.post("/__test__/worker/scenarios", json={"outcome": "pause_next", "session_id": session.id})
        assert armed.status_code == 200
        scenario_id = armed.json()["scenario_id"]
        queue = JobQueue(app.state.engine)
        job = queue.enqueue({"preset_name": "bank-outage-50"}, session_id=session.id, max_attempts=1)
        paused = _wait_for_scenario(client, scenario_id, "paused")
        assert paused["job_id"] == job.id

        cancellation = client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"X-Session-ID": session.id, "X-Session-Token": session.capability_token},
        )
        assert cancellation.status_code == 202
        assert cancellation.json()["status"] == "cancel_requested"
        with app.state.engine.begin() as connection:
            connection.execute(
                text("UPDATE jobs SET lease_expires_at = :expired WHERE id = :job_id AND status = 'running'"),
                {"expired": "2000-01-01T00:00:00+00:00", "job_id": job.id},
            )
        assert recover_expired_leases(queue) == 1
        recovered = queue.get_job(job.id)
        assert recovered is not None
        assert recovered.status.value == "cancelled"
        assert recovered.cancel_requested

        released = client.post(f"/__test__/worker/scenarios/{scenario_id}/release")
        assert released.status_code == 200
        assert released.json() == {"state": "paused", "job_id": job.id}
        terminal_state = _wait_for_scenario(client, scenario_id, "cancelled")
        assert terminal_state == {"state": "cancelled", "job_id": job.id}
        repeated_release = client.post(f"/__test__/worker/scenarios/{scenario_id}/release")
        assert repeated_release.status_code == 200
        assert repeated_release.json() == {"state": "cancelled", "job_id": job.id}
        still_cancelled = queue.get_job(job.id)
        assert still_cancelled is not None and still_cancelled.status.value == "cancelled"
        with app.state.engine.connect() as connection:
            terminal_events = connection.execute(
                text("SELECT event_type, details_json FROM job_events WHERE job_id = :job_id ORDER BY created_at"),
                {"job_id": job.id},
            ).fetchall()
        assert sum(event[0] == "CANCELLED" for event in terminal_events) == 1
        assert any(
            event[0] == "CANCELLED" and "lease_expired_while_cancellation_requested" in (event[1] or "")
            for event in terminal_events
        )


def test_luna_g6_startup_scenarios_fail_a_real_claim_and_record_real_terminal_event(tmp_path, monkeypatch):
    _clear_test_flags(monkeypatch)
    app = create_scripted_test_app(_scenario_app_settings(tmp_path))
    with TestClient(app) as client:
        session = ContinuationService(app.state.engine).create_session()
        armed = client.post("/__test__/worker/scenarios", json={"outcome": "fail_next", "session_id": session.id})
        assert armed.status_code == 200
        scenario_id = armed.json()["scenario_id"]
        job = JobQueue(app.state.engine).enqueue(
            {"preset_name": "bank-outage-50"}, session_id=session.id, max_attempts=1,
        )

        state = _wait_for_scenario(client, scenario_id, "failed")
        assert state["job_id"] == job.id
        failed = JobQueue(app.state.engine).get_job(job.id)
        assert failed is not None and failed.status.value == "failed"
        assert failed.error and failed.error["code"] == "EXECUTION_ERROR"
        with app.state.engine.connect() as connection:
            events = connection.execute(
                text("SELECT event_type FROM job_events WHERE job_id = :job_id"), {"job_id": job.id}
            ).fetchall()
        assert any(row[0] == "CLAIMED" for row in events)
        assert any(row[0] == "FAILED" for row in events)


def test_luna_g6_startup_scenario_skips_cross_session_backlog_until_bound_job_claim(tmp_path, monkeypatch):
    _clear_test_flags(monkeypatch)
    app = create_scripted_test_app(_scenario_app_settings(tmp_path))
    with TestClient(app) as client:
        sessions = ContinuationService(app.state.engine)
        backlog_session = sessions.create_session()
        intended_session = sessions.create_session()
        queue = JobQueue(app.state.engine)

        armed = client.post(
            "/__test__/worker/scenarios",
            json={"outcome": "pause_next", "session_id": intended_session.id},
        )
        assert armed.status_code == 200
        scenario_id = armed.json()["scenario_id"]

        backlog_job = queue.enqueue(
            {"preset_name": "bank-outage-50"}, session_id=backlog_session.id, max_attempts=1,
        )
        _wait_for_claim(app.state.engine, backlog_job.id)
        still_armed = client.get(f"/__test__/worker/scenarios/{scenario_id}").json()
        assert still_armed == {"state": "armed", "job_id": None}

        intended_job = queue.enqueue(
            {"preset_name": "bank-outage-50"}, session_id=intended_session.id, max_attempts=1,
        )
        # The managed worker is serial: backlog fitting/publication precedes the
        # intended job's ten-second heartbeat. Do not charge both to one wait.
        _wait_for_completed_job(queue, backlog_job.id)
        paused = _wait_for_scenario(client, scenario_id, "paused")
        assert paused["job_id"] == intended_job.id
        assert paused["job_id"] != backlog_job.id
        completed_backlog = queue.get_job(backlog_job.id)
        assert completed_backlog is not None and completed_backlog.status.value == "completed"

        cancelled = client.post(
            f"/api/v1/jobs/{intended_job.id}/cancel",
            headers={
                "X-Session-ID": intended_session.id,
                "X-Session-Token": intended_session.capability_token,
            },
        )
        assert cancelled.status_code == 202
        assert cancelled.json()["status"] == "cancel_requested"
        released = client.post(f"/__test__/worker/scenarios/{scenario_id}/release")
        assert released.status_code == 200

        deadline = time.monotonic() + 10
        terminal = None
        while time.monotonic() < deadline:
            terminal = queue.get_job(intended_job.id)
            if terminal is not None and terminal.status.value == "cancelled":
                break
            time.sleep(0.05)
        assert terminal is not None and terminal.status.value == "cancelled"
        assert queue.get_job(backlog_job.id).status.value == "completed"


def test_luna_g6_startup_worker_scenario_routes_exist_only_in_enabled_scripted_factory(tmp_path):
    settings = _scenario_app_settings(tmp_path)
    with TestClient(create_scripted_test_app(settings)) as client:
        response = client.post("/__test__/worker/scenarios", json={"outcome": "invalid"})
        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/json")
        missing_session = client.post("/__test__/worker/scenarios", json={"outcome": "pause_next"})
        assert missing_session.status_code == 422

    no_worker = Settings(
        db_url=f"sqlite:///{tmp_path / 'no-worker.sqlite'}",
        environment="local",
        embedded_worker=False,
        _env_file=None,
    )
    with TestClient(create_app(no_worker)) as client:
        ordinary_response = client.post("/__test__/worker/scenarios", json={"outcome": "pause_next"})
        assert ordinary_response.status_code == 405
    with TestClient(create_scripted_test_app(no_worker)) as client:
        scripted_response = client.post("/__test__/worker/scenarios", json={"outcome": "pause_next"})
        assert scripted_response.status_code == 405
