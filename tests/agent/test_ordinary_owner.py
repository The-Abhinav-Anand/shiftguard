"""OR-02: exactly one live process owns ordinary provider dispatch per database."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from starlette.testclient import TestClient

from shiftguard.agent.ordinary_budget import OrdinaryBudget
from shiftguard.agent.ordinary_owner import (
    OrdinaryDispatchOwner,
    OrdinaryOwnerUnavailable,
    postgres_owner_key,
    sqlite_owner_path,
)
from shiftguard.api.main import create_app
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings


APP_ROOT = Path(__file__).resolve().parents[2]
USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}


class _RecordingSDK:
    def __init__(self):
        self.calls = []
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("ownership tests never dispatch")

    async def close(self):
        return None


@pytest.fixture
def owner_settings(ordinary_test_settings, monkeypatch):
    from shiftguard.agent import provider as provider_module

    sdk = _RecordingSDK()
    monkeypatch.setattr(provider_module, "AsyncOpenAI", lambda **_kwargs: sdk)
    settings = ordinary_test_settings.model_copy(update={
        "agent_enabled": False,
        "general_chat_enabled": True,
        "nebius_api_key": "offline-test-key",
    })
    upgrade_database(settings)
    return settings, sdk


def _ledger(engine) -> tuple[dict, list[tuple[str, str | None]]]:
    with engine.connect() as connection:
        daily = connection.execute(
            text("SELECT calls_used, tokens_committed, halted, halt_reason FROM ordinary_budget_daily")
        ).mappings().all()
        calls = connection.execute(
            text("SELECT status, failure_kind FROM ordinary_budget_calls ORDER BY created_at_utc")
        ).all()
    return [dict(row) for row in daily], [tuple(row) for row in calls]


def _reserve(budget: OrdinaryBudget):
    return budget.reserve(
        model="offline-model",
        messages=[{"role": "user", "content": "in flight"}],
        tools=None,
        max_output_tokens=16,
    )


def test_second_owner_does_not_recover_live_reservation(owner_settings):
    settings, sdk = owner_settings
    with TestClient(create_app(settings)) as owner_a:
        budget = owner_a.app.state.ordinary_budget
        reservation = _reserve(budget)
        before = _ledger(budget.engine)
        assert before[1] == [("reserved", None)]

        with pytest.raises(OrdinaryOwnerUnavailable):
            with TestClient(create_app(settings)):
                pass

        assert _ledger(budget.engine) == before
        budget.settle(reservation, USAGE, "offline-request")
        daily, calls = _ledger(budget.engine)
        assert calls == [("settled", None)]
        assert daily[0]["halted"] == 0 and daily[0]["calls_used"] == 1
    assert sdk.calls == []


def test_graceful_shutdown_releases_ownership_for_the_next_process(owner_settings):
    settings, _sdk = owner_settings
    with TestClient(create_app(settings)) as first:
        assert first.app.state.ordinary_budget.owner is not None
    with TestClient(create_app(settings)) as second:
        second.app.state.ordinary_budget.owner.assert_held()


def test_startup_failure_after_acquisition_releases_ownership(owner_settings, monkeypatch):
    settings, _sdk = owner_settings
    from shiftguard.api import main as main_module

    def broken_provider(*_args, **_kwargs):
        raise RuntimeError("provider construction failed")

    monkeypatch.setattr(main_module, "AgentProvider", broken_provider)
    with pytest.raises(RuntimeError, match="provider construction failed"):
        with TestClient(create_app(settings)):
            pass
    monkeypatch.undo()

    engine = create_engine_for_settings(settings)
    owner = OrdinaryDispatchOwner(engine)
    try:
        owner.acquire()
        owner.assert_held()
    finally:
        owner.close()
        engine.dispose()


def test_disabled_provider_app_neither_owns_nor_recovers_the_ledger(owner_settings):
    settings, _sdk = owner_settings
    engine = create_engine_for_settings(settings)
    try:
        _reserve(OrdinaryBudget(engine))
        before = _ledger(engine)
        disabled = settings.model_copy(update={"general_chat_enabled": False, "agent_enabled": False})
        with TestClient(create_app(disabled)) as client:
            assert client.app.state.ordinary_budget is None
            owner = OrdinaryDispatchOwner(engine)
            owner.acquire()
            owner.close()
        assert _ledger(engine) == before
    finally:
        engine.dispose()


def test_recovery_requires_held_ownership(owner_settings):
    settings, _sdk = owner_settings
    engine = create_engine_for_settings(settings)
    try:
        _reserve(OrdinaryBudget(engine))
        before = _ledger(engine)
        with pytest.raises(OrdinaryOwnerUnavailable):
            OrdinaryBudget(engine).recover_unresolved()
        closed = OrdinaryDispatchOwner(engine)
        closed.acquire()
        closed.close()
        with pytest.raises(OrdinaryOwnerUnavailable):
            OrdinaryBudget(engine, owner=closed).recover_unresolved()
        assert _ledger(engine) == before

        owner = OrdinaryDispatchOwner(engine)
        owner.acquire()
        try:
            assert OrdinaryBudget(engine, owner=owner).recover_unresolved() is True
        finally:
            owner.close()
        daily, calls = _ledger(engine)
        assert calls == [("closed_unknown", "unresolved_restart")]
        assert daily[0]["halted"] == 1
    finally:
        engine.dispose()


def test_lost_ownership_fails_closed_before_reserve_and_never_reacquires(owner_settings):
    settings, sdk = owner_settings
    with TestClient(create_app(settings)) as client:
        budget = client.app.state.ordinary_budget
        budget.owner.close()
        with pytest.raises(OrdinaryOwnerUnavailable):
            _reserve(budget)
        with pytest.raises(OrdinaryOwnerUnavailable):
            budget.owner.acquire()
        assert _ledger(budget.engine) == ([], [])

        session = client.post("/api/v1/agent/sessions", json={}).json()
        headers = {"X-Session-ID": session["session_id"], "X-Session-Token": session["capability_token"]}
        refused = client.post(
            "/api/v1/chat/messages",
            json={"prompt": "hello", "idempotency_key": "after-loss"},
            headers=headers,
        )
        assert refused.status_code == 503
        assert refused.json()["error"]["code"] == "ORDINARY_OWNER_UNAVAILABLE"
        with budget.engine.connect() as connection:
            receipts = connection.execute(text("SELECT count(*) FROM shiftguard_chat_receipts")).scalar_one()
        assert receipts == 0
        assert _ledger(budget.engine) == ([], [])
    assert sdk.calls == []


def test_external_loss_of_the_lock_is_detected_and_fails_closed(owner_settings, tmp_path):
    settings, _sdk = owner_settings
    engine = create_engine_for_settings(settings)
    owner = OrdinaryDispatchOwner(engine)
    try:
        owner.acquire()
        if settings.database_backend == "postgresql":
            # The server ends the owning session, which releases its advisory lock.
            pid = owner._connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
            admin = create_engine(os.environ["SHIFTGUARD_TEST_POSTGRES_URL"])
            try:
                with admin.connect() as connection:
                    assert connection.execute(
                        text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
                    ).scalar_one()
            finally:
                admin.dispose()
        else:
            # Stand-in for a sidecar unlinked and recreated by someone else: the
            # path no longer names the file this process locked.
            decoy = tmp_path / "replaced-sidecar.lock"
            decoy.write_bytes(b"")
            owner._path = decoy
        with pytest.raises(OrdinaryOwnerUnavailable):
            owner.assert_held()
        with pytest.raises(OrdinaryOwnerUnavailable):
            _reserve(OrdinaryBudget(engine, owner=owner))
        with pytest.raises(OrdinaryOwnerUnavailable):
            owner.acquire()
        assert _ledger(engine) == ([], [])
        owner.close()
        successor = OrdinaryDispatchOwner(engine)
        _acquire_eventually(successor)
        successor.close()
    finally:
        owner.close()
        engine.dispose()


def test_independent_databases_have_independent_owners(owner_settings, tmp_path):
    settings, _sdk = owner_settings
    other = _independent_settings(settings, tmp_path)
    try:
        upgrade_database(other)
        with TestClient(create_app(settings)), TestClient(create_app(other)) as second:
            second.app.state.ordinary_budget.owner.assert_held()
    finally:
        _drop_independent(other)


def test_in_memory_sqlite_cannot_own_ordinary_dispatch():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, db_url="sqlite:///:memory:", general_chat_enabled=True)
    engine = create_engine("sqlite://")
    try:
        with pytest.raises(OrdinaryOwnerUnavailable):
            OrdinaryDispatchOwner(engine).acquire()
    finally:
        engine.dispose()


def test_owner_identity_is_stable_and_scoped():
    key = postgres_owner_key("shiftguard", "public")
    assert key == postgres_owner_key("shiftguard", "public")
    assert key != postgres_owner_key("shiftguard", "other")
    assert key != postgres_owner_key("other", "public")
    assert -(2**63) <= key < 2**63
    assert sqlite_owner_path("var/x.db").name == "x.db.ordinary-owner.lock"


# --- process-level ownership -------------------------------------------------

_CHILD = r"""
import os, sys
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings
from shiftguard.agent.ordinary_owner import OrdinaryDispatchOwner
from shiftguard.agent.ordinary_budget import OrdinaryBudget
settings = Settings(_env_file=None, db_url=os.environ["SG_OWNER_DB_URL"], environment=os.environ["SG_OWNER_ENV"])
engine = create_engine_for_settings(settings)
owner = OrdinaryDispatchOwner(engine)
owner.acquire()
if os.environ.get("SG_OWNER_RESERVE") == "1":
    OrdinaryBudget(engine, owner=owner).reserve(
        model="offline-model", messages=[{"role": "user", "content": "child"}], tools=None, max_output_tokens=16)
print("held", flush=True)
sys.stdin.readline()
owner.close()
engine.dispose()
print("released", flush=True)
"""


def _spawn_owner(settings: Settings, *, reserve: bool) -> subprocess.Popen:
    env = {
        **os.environ,
        "SG_OWNER_DB_URL": settings.db_url,
        "SG_OWNER_ENV": settings.environment,
        "SG_OWNER_RESERVE": "1" if reserve else "0",
    }
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", _CHILD],
        cwd=APP_ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = child.stdout.readline().strip()
    if line != "held":
        child.kill()
        _out, err = child.communicate(timeout=30)
        raise AssertionError(
            "owner child did not acquire: " + err[-2000:].replace(settings.db_url, "<db-url>")
        )
    return child


def _acquire_eventually(owner: OrdinaryDispatchOwner, seconds: float = 15.0) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            owner.acquire()
            return
        except OrdinaryOwnerUnavailable:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def test_another_process_cannot_acquire_until_the_owner_releases(owner_settings):
    settings, _sdk = owner_settings
    child = _spawn_owner(settings, reserve=False)
    engine = create_engine_for_settings(settings)
    try:
        with pytest.raises(OrdinaryOwnerUnavailable):
            OrdinaryDispatchOwner(engine).acquire()
        with pytest.raises(OrdinaryOwnerUnavailable):
            with TestClient(create_app(settings)):
                pass
        child.stdin.write("release\n")
        child.stdin.flush()
        assert child.stdout.readline().strip() == "released"
        assert child.wait(timeout=30) == 0
        owner = OrdinaryDispatchOwner(engine)
        owner.acquire()
        owner.close()
    finally:
        if child.poll() is None:
            child.kill()
        engine.dispose()


def test_abrupt_owner_death_allows_conservative_takeover(owner_settings):
    settings, _sdk = owner_settings
    child = _spawn_owner(settings, reserve=True)
    engine = create_engine_for_settings(settings)
    try:
        assert _ledger(engine)[1] == [("reserved", None)]
        with pytest.raises(OrdinaryOwnerUnavailable):
            OrdinaryDispatchOwner(engine).acquire()
        child.kill()
        child.wait(timeout=30)
        owner = OrdinaryDispatchOwner(engine)
        _acquire_eventually(owner)
        owner.close()
        with TestClient(create_app(settings)) as client:
            snapshot = client.get("/api/v1/agent/status").json()["ordinary_budget"]
            assert snapshot["halted"] is True and snapshot["calls_used"] == 1
        assert _ledger(engine)[1] == [("closed_unknown", "unresolved_restart")]
    finally:
        if child.poll() is None:
            child.kill()
        engine.dispose()


# --- independent database helpers --------------------------------------------

def _independent_settings(settings: Settings, tmp_path) -> Settings:
    if settings.database_backend == "sqlite":
        return settings.model_copy(
            update={"db_url": f"sqlite:///{(tmp_path / ('independent-' + uuid4().hex + '.sqlite')).as_posix()}"}
        )
    process_url = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]
    schema = "sg_owner_" + uuid4().hex
    admin = create_engine(process_url)
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    finally:
        admin.dispose()
    url = make_url(process_url).update_query_dict({"options": f"-csearch_path={schema}"})
    return settings.model_copy(update={"db_url": url.render_as_string(hide_password=False)})


def _drop_independent(settings: Settings) -> None:
    if settings.database_backend != "postgresql":
        return
    schema = make_url(settings.db_url).query["options"].split("=", 1)[1]
    admin = create_engine(os.environ["SHIFTGUARD_TEST_POSTGRES_URL"])
    try:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    finally:
        admin.dispose()
