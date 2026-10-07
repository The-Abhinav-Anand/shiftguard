"""Offline contracts for persisted live-provider attempt accounting."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from shiftguard.agent.budget import (
    AttemptBudget,
    BudgetError,
    BudgetHalted,
    BudgetLimitExceeded,
)
from shiftguard.agent.provider import AgentProvider, ProviderError
from shiftguard.settings import Settings


SOURCE = "a" * 64
SECRET = "dummy-provider-secret-123456789"
BODY_MARKER = "private-provider-body-marker-7d91"


def _engine(path: Path):
    return create_engine(
        f"sqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )


def _budget(path: Path, *, calls: int = 3, tokens: int = 40_000, ledger: str = "offline-test"):
    return AttemptBudget(
        _engine(path), ledger_id=ledger, source_digest=SOURCE,
        max_calls=calls, max_tokens=tokens,
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        db_url="sqlite:///./offline-provider-isolation.db",
        environment="local",
        nebius_api_key=SECRET,
        nebius_max_output_tokens=32,
        agent_enabled=True,
    )


def _response(*, usage=True, request_id="provider-request-offline-1", prompt_tokens=8, completion_tokens=5):
    return SimpleNamespace(
        id=request_id,
        model="nvidia/Nemotron-3_5-Lightning",
        choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"template":"summary","condition_refs":[]}', tool_calls=None),
            finish_reason="stop",
        )],
        usage=(SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                               total_tokens=prompt_tokens + completion_tokens) if usage else None),
    )


def _provider(budget: AttemptBudget, monkeypatch, create):
    provider = AgentProvider(_settings(), attempt_budget=budget)
    calls = []

    async def dispatch(**kwargs):
        calls.append(kwargs)
        return await create(**kwargs)

    monkeypatch.setattr(provider._client.chat.completions, "create", dispatch)
    return provider, calls


def _run(provider: AgentProvider, content: str = BODY_MARKER):
    return asyncio.run(provider.chat(
        messages=[{"role": "user", "content": content}], tools=[]
    ))


def test_provider_does_not_dispatch_fourth_request_when_call_ceiling_is_three(tmp_path, monkeypatch):
    budget = _budget(tmp_path / "cap.sqlite", calls=3)

    async def dispatch(**_kwargs):
        return _response()

    provider, calls = _provider(budget, monkeypatch, dispatch)
    for _ in range(3):
        assert _run(provider).usage["total_tokens"] == 13
    with pytest.raises(ProviderError, match="allowance is exhausted"):
        _run(provider)

    assert len(calls) == 3
    snapshot = budget.snapshot()
    assert snapshot["calls_used"] == 3
    assert snapshot["tokens_committed"] == 39
    assert [row["status"] for row in snapshot["attempts"]] == ["settled"] * 3
    assert provider.max_retries == 0


def test_concurrent_last_slot_has_one_winner(tmp_path):
    budget = _budget(tmp_path / "concurrent.sqlite", calls=1)

    def reserve():
        try:
            return budget.reserve(
                model="nvidia/Nemotron-3_5-Lightning",
                messages=[{"role": "user", "content": BODY_MARKER}],
                tools=[], max_output_tokens=32,
            )
        except BudgetLimitExceeded:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: reserve(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert budget.snapshot()["calls_used"] == 1


def test_missing_usage_closes_and_consumes_the_attempt(tmp_path, monkeypatch):
    budget = _budget(tmp_path / "missing-usage.sqlite", calls=1)

    async def dispatch(**_kwargs):
        return _response(usage=False)

    provider, calls = _provider(budget, monkeypatch, dispatch)
    with pytest.raises(ProviderError, match="usage was missing or invalid"):
        _run(provider)
    with pytest.raises(ProviderError, match="ledger is halted"):
        _run(provider)

    assert len(calls) == 1
    snapshot = budget.snapshot()
    assert snapshot["calls_used"] == 1
    assert snapshot["attempts"][0]["status"] == "closed_unknown"
    assert snapshot["attempts"][0]["failure_kind"] == "invalid_usage"
    assert snapshot["tokens_committed"] == snapshot["attempts"][0]["reserved_tokens"]


def test_timeout_keeps_call_and_token_reservation_and_halts_after_restart(tmp_path, monkeypatch):
    path = tmp_path / "restart.sqlite"
    first = _budget(path, calls=2, tokens=40_000, ledger="restart-test")

    async def timeout(**_kwargs):
        raise asyncio.TimeoutError()

    provider, calls = _provider(first, monkeypatch, timeout)
    with pytest.raises(ProviderError, match="timed out"):
        _run(provider)
    assert len(calls) == 1
    assert first.snapshot()["attempts"][0]["failure_kind"] == "timeout"
    first.engine.dispose()

    reopened = _budget(path, calls=2, tokens=40_000, ledger="restart-test")
    assert reopened.snapshot()["calls_used"] == 1
    assert reopened.snapshot()["halted"] is True
    assert reopened.snapshot()["halt_reason"] == "timeout"

    async def successful(**_kwargs):
        return _response()

    resumed_provider, resumed_calls = _provider(reopened, monkeypatch, successful)
    with pytest.raises(ProviderError, match="ledger is halted"):
        _run(resumed_provider)
    assert resumed_calls == []
    assert [row["status"] for row in reopened.snapshot()["attempts"]] == ["closed_unknown"]
    with pytest.raises(BudgetError, match="source binding or ceilings"):
        _budget(path, calls=3, tokens=40_000, ledger="restart-test")


def test_budget_ledger_persists_only_hashes_usage_and_redacted_identifiers(tmp_path, monkeypatch):
    path = tmp_path / "redacted.sqlite"
    budget = _budget(path, calls=1)

    async def successful(**_kwargs):
        return _response(request_id=SECRET)

    provider, _calls = _provider(budget, monkeypatch, successful)
    _run(provider, f"{BODY_MARKER}; Authorization: Bearer {SECRET}")
    snapshot = budget.snapshot()
    serialized = repr(snapshot)
    assert SECRET not in serialized
    assert BODY_MARKER not in serialized
    assert "messages" not in snapshot["attempts"][0]
    assert "response" not in snapshot["attempts"][0]
    assert snapshot["attempts"][0]["provider_request_id_sha256"] == hashlib.sha256(SECRET.encode()).hexdigest()
    assert "provider_request_id" not in snapshot["attempts"][0]


def test_unresolved_reservation_only_halts_on_explicit_recovery(tmp_path):
    path = tmp_path / "unresolved.sqlite"
    first = _budget(path, calls=2, ledger="unresolved-test")
    reservation = first.reserve(
        model="nvidia/Nemotron-3_5-Lightning",
        messages=[{"role": "user", "content": BODY_MARKER}], tools=[], max_output_tokens=32,
    )
    concurrent_open = _budget(path, calls=2, ledger="unresolved-test")
    assert concurrent_open.snapshot()["halted"] is False
    first.settle(reservation, {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13}, "in-flight-id")
    assert concurrent_open.snapshot()["attempts"][0]["status"] == "settled"

    crash_path = tmp_path / "crash.sqlite"
    crashed = _budget(crash_path, calls=2, ledger="crash-test")
    crashed.reserve(
        model="nvidia/Nemotron-3_5-Lightning",
        messages=[{"role": "user", "content": BODY_MARKER}], tools=[], max_output_tokens=32,
    )
    crashed.engine.dispose()
    reopened = _budget(crash_path, calls=2, ledger="crash-test")
    assert reopened.recover_unresolved() is True
    assert reopened.snapshot()["attempts"][0]["status"] == "reserved"
    assert reopened.snapshot()["halt_reason"] == "unresolved_restart"
    with pytest.raises(BudgetHalted, match="unresolved_restart"):
        reopened.reserve(
            model="nvidia/Nemotron-3_5-Lightning",
            messages=[{"role": "user", "content": "blocked"}], tools=[], max_output_tokens=32,
        )


def test_settled_ledger_reopens_and_continues_with_same_identity(tmp_path):
    path = tmp_path / "settled-restart.sqlite"
    first = _budget(path, calls=3, tokens=50_000, ledger="settled-restart-test")
    first_attempt = first.reserve(
        model="nvidia/Nemotron-3_5-Lightning",
        messages=[{"role": "user", "content": BODY_MARKER}], tools=[], max_output_tokens=32,
    )
    first.settle(first_attempt, {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13}, "first-id")
    first.engine.dispose()

    resumed = _budget(path, calls=3, tokens=50_000, ledger="settled-restart-test")
    assert resumed.snapshot()["ledger_id"] == "settled-restart-test"
    assert resumed.snapshot()["halted"] is False
    assert resumed.snapshot()["calls_used"] == 1
    second = resumed.reserve(
        model="nvidia/Nemotron-3_5-Lightning",
        messages=[{"role": "user", "content": "resumed"}], tools=[], max_output_tokens=32,
    )
    resumed.settle(second, {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}, "second-id")
    assert resumed.snapshot()["calls_used"] == 2
    assert resumed.snapshot()["tokens_committed"] == 24


@pytest.mark.parametrize("prompt_tokens,completion_tokens", [(8, 33), (10_000, 1)])
def test_provider_overbound_component_is_truthfully_charged_and_permanently_halted(
    tmp_path, monkeypatch, prompt_tokens, completion_tokens,
):
    path = tmp_path / "overbound.sqlite"
    budget = _budget(path, calls=2, tokens=40_000, ledger="overbound-test")
    provider, dispatched = _provider(budget, monkeypatch, lambda **_kwargs: asyncio.sleep(0))

    async def excessive(**_kwargs):
        return _response(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    provider._client.chat.completions.create = excessive
    with pytest.raises(ProviderError, match="component bound"):
        _run(provider)
    snapshot = budget.snapshot()
    assert len(dispatched) == 0
    assert snapshot["halted"] is True
    assert snapshot["halt_reason"] == "usage_bound_exceeded"
    attempt = snapshot["attempts"][0]
    assert attempt["status"] == "over_bound"
    assert attempt["prompt_tokens"] == prompt_tokens
    assert attempt["completion_tokens"] == completion_tokens
    assert snapshot["tokens_committed"] == prompt_tokens + completion_tokens
    reopened = _budget(path, calls=2, tokens=40_000, ledger="overbound-test")
    with pytest.raises(BudgetHalted):
        reopened.reserve(
            model="nvidia/Nemotron-3_5-Lightning",
            messages=[{"role": "user", "content": "blocked"}], tools=[], max_output_tokens=32,
        )


def test_settlement_charges_actual_usage_and_fingerprints_provider_identifier(tmp_path):
    budget = _budget(tmp_path / "settle-fingerprint.sqlite", calls=1)
    reservation = budget.reserve(
        model="nvidia/Nemotron-3_5-Lightning",
        messages=[{"role": "user", "content": BODY_MARKER}], tools=[], max_output_tokens=32,
    )
    budget.settle(
        reservation,
        {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
        SECRET,
    )
    payload = json.dumps(budget.snapshot(), sort_keys=True)
    assert SECRET not in payload
    assert hashlib.sha256(SECRET.encode()).hexdigest() in payload


def test_maximum_call_ceiling_cannot_exceed_hard_limit(tmp_path):
    with pytest.raises(ValueError, match="between 1 and 10"):
        _budget(tmp_path / "hard-limit.sqlite", calls=11)


def test_token_ceiling_allows_parent_limit_but_rejects_higher_value(tmp_path):
    accepted = _budget(tmp_path / "accepted-token-limit.sqlite", tokens=50_000)
    assert accepted.max_tokens == 50_000
    with pytest.raises(ValueError, match="between 1 and 50000"):
        _budget(tmp_path / "hard-token-limit.sqlite", tokens=50_001)


@pytest.fixture
def isolated_postgres_budget():
    raw_url = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("SHIFTGUARD_TEST_POSTGRES_URL is not set by the existing PostgreSQL helper")
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    admin_url = make_url(raw_url)
    if admin_url.database != "shiftguard_gate3" or admin_url.port != 15432:
        pytest.fail("PostgreSQL test helper did not target the authorized host and database")
    admin_url = admin_url.set(drivername="postgresql+psycopg", query={k: v for k, v in admin_url.query.items() if k != "options"})
    schema = "sg_luna_g67_" + uuid4().hex[:12]
    admin = create_engine(admin_url, pool_pre_ping=True)
    with admin.begin() as connection:
        version = int(connection.execute(text("SELECT current_setting('server_version_num')::integer")).scalar_one())
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        assert version // 10000 == 16 and database == "shiftguard_gate3"
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped_url = admin_url.set(query={**dict(admin_url.query), "options": f"-csearch_path={schema}"})
    engine = create_engine(scoped_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.dispose()


def test_postgres16_ledger_restart_halt_and_redaction(isolated_postgres_budget):
    engine = isolated_postgres_budget
    budget = AttemptBudget(
        engine, ledger_id="pg16-" + uuid4().hex,
        source_digest=SOURCE, max_calls=3, max_tokens=50_000,
    )
    attempt = budget.reserve(
        model="nvidia/Nemotron-3_5-Lightning",
        messages=[{"role": "user", "content": BODY_MARKER}], tools=[], max_output_tokens=32,
    )
    other_instance = AttemptBudget(
        engine, ledger_id=budget.ledger_id, source_digest=SOURCE,
        max_calls=3, max_tokens=50_000,
    )
    assert other_instance.snapshot()["halted"] is False
    budget.settle(attempt, {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13}, SECRET)
    attempt = other_instance.reserve(
        model="nvidia/Nemotron-3_5-Lightning",
        messages=[{"role": "user", "content": BODY_MARKER}], tools=[], max_output_tokens=32,
    )
    other_instance.close_unknown(attempt, "timeout")
    snapshot = budget.snapshot()
    assert snapshot["halted"] is True and snapshot["halt_reason"] == "timeout"
    assert SECRET not in json.dumps(snapshot)
    assert snapshot["attempts"][0]["provider_request_id_sha256"] == hashlib.sha256(SECRET.encode()).hexdigest()
    reopened = AttemptBudget(
        engine, ledger_id=budget.ledger_id, source_digest=SOURCE,
        max_calls=3, max_tokens=50_000,
    )
    with pytest.raises(BudgetHalted):
        reopened.reserve(
            model="nvidia/Nemotron-3_5-Lightning",
            messages=[{"role": "user", "content": "no more"}], tools=[], max_output_tokens=32,
        )

    concurrent = AttemptBudget(
        engine, ledger_id="pg16-race-" + uuid4().hex,
        source_digest=SOURCE, max_calls=1, max_tokens=50_000,
    )
    second_instance = AttemptBudget(
        engine, ledger_id=concurrent.ledger_id, source_digest=SOURCE,
        max_calls=1, max_tokens=50_000,
    )

    def reserve_once(target):
        try:
            return target.reserve(
                model="nvidia/Nemotron-3_5-Lightning",
                messages=[{"role": "user", "content": "last slot"}],
                tools=[], max_output_tokens=32,
            )
        except BudgetLimitExceeded:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        reservations = list(pool.map(reserve_once, (concurrent, second_instance)))
    assert sum(item is not None for item in reservations) == 1
    assert concurrent.snapshot()["calls_used"] == 1
