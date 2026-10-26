"""Provider-level contract: a timeout is charged in full and does not halt the ordinary day."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest
from sqlalchemy import create_engine, text

from shiftguard.agent.budget import AttemptBudget
from shiftguard.agent.ordinary_budget import OrdinaryBudget
from shiftguard.agent.provider import AgentProvider, ProviderError
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings

MODEL = "nvidia/Nemotron-3_5-Lightning"


@pytest.fixture
def ordinary_engine(ordinary_test_settings):
    upgrade_database(ordinary_test_settings)
    engine = create_engine_for_settings(ordinary_test_settings)
    try:
        yield engine
    finally:
        engine.dispose()


def _settings(timeout: float = 5.0) -> Settings:
    return Settings(
        _env_file=None,
        db_url="sqlite:///./offline-provider-isolation.db",
        environment="local",
        nebius_api_key="dummy-provider-secret-123456789",
        nebius_max_output_tokens=32,
        nebius_timeout=timeout,
        agent_enabled=True,
    )


def _ok_response():
    return SimpleNamespace(
        id="provider-request-offline-1",
        model=MODEL,
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="ok", tool_calls=None), finish_reason="stop"
        )],
        usage=SimpleNamespace(prompt_tokens=8, completion_tokens=5, total_tokens=13),
    )


def _provider(monkeypatch, create, *, ordinary=None, attempt=None, timeout: float = 5.0):
    provider = AgentProvider(_settings(timeout), ordinary_budget=ordinary, attempt_budget=attempt)
    monkeypatch.setattr(provider._client.chat.completions, "create", create)
    return provider


def _call_rows(engine):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT status, failure_kind, reserved_tokens, input_token_bound, "
                "output_token_bound FROM ordinary_budget_calls ORDER BY created_at_utc"
            )
        ).mappings().all()


def _chat(provider):
    return asyncio.run(provider.chat([{"role": "user", "content": "ping"}]))


async def _sdk_timeout(**_kwargs):
    raise openai.APITimeoutError(request=httpx.Request("POST", "https://offline.invalid/v1"))


async def _deadline_timeout(**_kwargs):
    await asyncio.sleep(10)


async def _success(**_kwargs):
    return _ok_response()


@pytest.mark.parametrize(
    "create, timeout",
    [(_sdk_timeout, 5.0), (_deadline_timeout, 0.03)],
    ids=["sdk-timeout", "asyncio-deadline"],
)
def test_timeout_charges_reservation_and_keeps_ordinary_day_open(
    ordinary_engine, monkeypatch, create, timeout
):
    ordinary = OrdinaryBudget(ordinary_engine)
    provider = _provider(monkeypatch, create, ordinary=ordinary, timeout=timeout)
    with pytest.raises(ProviderError) as caught:
        _chat(provider)
    assert caught.value.code == "PROVIDER_TIMEOUT"
    assert caught.value.status_code == 504
    snapshot = ordinary.public_snapshot()
    assert snapshot["halted"] is False
    assert snapshot["calls_used"] == 1
    rows = _call_rows(ordinary_engine)
    assert len(rows) == 1
    assert rows[0]["status"] == "closed_timeout"
    assert rows[0]["failure_kind"] == "timeout"
    # The charge is exactly the reservation: byte-bounded input plus the output cap.
    assert rows[0]["reserved_tokens"] == rows[0]["input_token_bound"] + 32
    assert rows[0]["output_token_bound"] == 32
    assert snapshot["tokens_committed"] == rows[0]["reserved_tokens"]
    charged = snapshot["tokens_committed"]

    # The day continues: a following call reserves and settles normally.
    monkeypatch.setattr(provider._client.chat.completions, "create", _success)
    assert _chat(provider).content == "ok"
    after = ordinary.public_snapshot()
    assert after["halted"] is False
    assert after["calls_used"] == 2
    assert after["tokens_committed"] == charged + 13


def test_non_timeout_provider_error_still_halts_the_ordinary_day(ordinary_engine, monkeypatch):
    async def broken(**_kwargs):
        raise RuntimeError("boom")

    ordinary = OrdinaryBudget(ordinary_engine)
    provider = _provider(monkeypatch, broken, ordinary=ordinary)
    with pytest.raises(ProviderError):
        _chat(provider)
    assert ordinary.public_snapshot()["halted"] is True


def test_close_timeout_failure_falls_back_to_halting_the_day(ordinary_engine, monkeypatch):
    ordinary = OrdinaryBudget(ordinary_engine)

    def failing(_reservation):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(ordinary, "close_timeout", failing)
    provider = _provider(monkeypatch, _sdk_timeout, ordinary=ordinary)
    with pytest.raises(ProviderError) as caught:
        _chat(provider)
    assert caught.value.code == "PROVIDER_TIMEOUT"
    snapshot = ordinary.public_snapshot()
    assert snapshot["halted"] is True
    assert snapshot["calls_used"] == 1


@pytest.mark.parametrize(
    "create, timeout",
    [(_sdk_timeout, 5.0), (_deadline_timeout, 0.03)],
    ids=["sdk-timeout", "asyncio-deadline"],
)
def test_sealed_attempt_ledger_still_halts_on_timeout(
    ordinary_engine, monkeypatch, tmp_path, create, timeout
):
    attempt = AttemptBudget(
        create_engine(
            f"sqlite:///{(tmp_path / 'attempt.sqlite').as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 15},
        ),
        ledger_id="offline-timeout-test",
        source_digest="a" * 64,
        max_calls=3,
        max_tokens=40_000,
    )
    ordinary = OrdinaryBudget(ordinary_engine)
    provider = _provider(monkeypatch, create, ordinary=ordinary, attempt=attempt, timeout=timeout)
    with pytest.raises(ProviderError) as caught:
        _chat(provider)
    assert caught.value.code == "PROVIDER_TIMEOUT"
    assert attempt.snapshot()["halted"] is True
    assert attempt.snapshot()["halt_reason"] == "timeout"
    assert ordinary.public_snapshot()["halted"] is False
    assert ordinary.public_snapshot()["calls_used"] == 1


def test_timeout_after_the_provider_responded_still_halts_the_day(ordinary_engine, monkeypatch):
    """A TimeoutError outside the provider await (here: settle) is not the exempt case."""
    ordinary = OrdinaryBudget(ordinary_engine)

    def settle_times_out(*_args, **_kwargs):
        raise TimeoutError("ledger socket timeout")

    monkeypatch.setattr(ordinary, "settle", settle_times_out)
    provider = _provider(monkeypatch, _success, ordinary=ordinary)
    with pytest.raises(ProviderError) as caught:
        _chat(provider)
    assert caught.value.code == "PROVIDER_TIMEOUT"
    assert ordinary.public_snapshot()["halted"] is True
    assert _call_rows(ordinary_engine)[0]["status"] == "closed_unknown"


def test_dispatch_timeout_error_is_not_closed_twice(ordinary_engine, monkeypatch):
    ordinary = OrdinaryBudget(ordinary_engine)
    closed = []
    original_unknown = ordinary.close_unknown
    monkeypatch.setattr(
        ordinary, "close_unknown", lambda *args: (closed.append(args), original_unknown(*args))
    )
    provider = _provider(monkeypatch, _sdk_timeout, ordinary=ordinary)
    with pytest.raises(ProviderError) as caught:
        _chat(provider)
    assert caught.value.code == "PROVIDER_TIMEOUT"
    assert caught.value.dispatched is True
    assert closed == []
    assert ordinary.public_snapshot()["halted"] is False
    assert _call_rows(ordinary_engine)[0]["status"] == "closed_timeout"


def test_close_timeout_returns_zero_when_nothing_is_open(ordinary_engine):
    ordinary = OrdinaryBudget(ordinary_engine)
    reservation = ordinary.reserve(
        model=MODEL, messages=[{"role": "user", "content": "ping"}], tools=None,
        max_output_tokens=32,
    )
    assert ordinary.close_timeout(reservation) == 1
    assert ordinary.close_timeout(reservation) == 0


def test_connection_error_still_halts_the_ordinary_day(ordinary_engine, monkeypatch):
    async def refused(**_kwargs):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://offline.invalid/v1"))

    ordinary = OrdinaryBudget(ordinary_engine)
    provider = _provider(monkeypatch, refused, ordinary=ordinary)
    with pytest.raises(ProviderError) as caught:
        _chat(provider)
    assert caught.value.code == "PROVIDER_CONNECTION_ERROR"
    assert ordinary.public_snapshot()["halted"] is True
    assert _call_rows(ordinary_engine)[0]["status"] == "closed_unknown"


def test_cancellation_still_halts_the_ordinary_day(ordinary_engine, monkeypatch):
    async def cancelled(**_kwargs):
        raise asyncio.CancelledError

    ordinary = OrdinaryBudget(ordinary_engine)
    provider = _provider(monkeypatch, cancelled, ordinary=ordinary)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(provider.chat([{"role": "user", "content": "ping"}]))
    assert ordinary.public_snapshot()["halted"] is True
    assert _call_rows(ordinary_engine)[0]["status"] == "closed_unknown"
