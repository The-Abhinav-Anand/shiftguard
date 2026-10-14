from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from shiftguard.agent import ordinary_budget as ordinary_module
from shiftguard.agent.ordinary_budget import (
    ORDINARY_MAX_CALLS,
    ORDINARY_MAX_OUTPUT_TOKENS,
    ORDINARY_MAX_TOKENS,
    OrdinaryBudget,
    OrdinaryBudgetHalted,
    OrdinaryBudgetLimitExceeded,
    OrdinaryBudgetUsageInvalid,
)
from shiftguard.agent.ordinary_owner import OrdinaryDispatchOwner
from shiftguard.migrations import upgrade_database
from shiftguard.storage.db import create_engine_for_settings


@pytest.fixture
def ordinary_engine(ordinary_test_settings):
    settings = ordinary_test_settings
    upgrade_database(settings)
    engine = create_engine_for_settings(settings)
    try:
        yield engine
    finally:
        engine.dispose()


def _reserve(budget: OrdinaryBudget, prompt="hello"):
    return budget.reserve(
        model="nvidia/Nemotron-3_5-Lightning",
        messages=[{"role": "user", "content": prompt}],
        tools=None,
        max_output_tokens=ORDINARY_MAX_OUTPUT_TOKENS,
    )


def test_ordinary_ledger_is_durable_and_uses_conservative_defaults(ordinary_engine):
    budget = OrdinaryBudget(ordinary_engine)
    reservation = _reserve(budget)
    budget.settle(
        reservation,
        {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "offline-request-1",
    )
    restarted = OrdinaryBudget(ordinary_engine)
    snapshot = restarted.public_snapshot()
    assert snapshot["calls_used"] == 1
    assert snapshot["calls_remaining"] == ORDINARY_MAX_CALLS - 1
    assert snapshot["tokens_committed"] == 5
    assert snapshot["tokens_remaining"] == ORDINARY_MAX_TOKENS - 5


def test_unknown_usage_halts_daily_budget_and_keeps_reservation_charged(ordinary_engine):
    budget = OrdinaryBudget(ordinary_engine)
    reservation = _reserve(budget)
    with pytest.raises(OrdinaryBudgetUsageInvalid):
        budget.settle(reservation, None, None)
    budget.close_unknown(reservation, "invalid_usage")
    snapshot = budget.public_snapshot()
    assert snapshot["halted"] is True
    assert snapshot["calls_used"] == 1
    assert snapshot["tokens_committed"] == reservation.reserved_tokens
    with pytest.raises(OrdinaryBudgetHalted):
        _reserve(budget)


def test_call_limit_is_atomic_under_concurrent_reservations(ordinary_engine):
    budgets = [OrdinaryBudget(ordinary_engine) for _ in range(14)]

    def attempt(budget):
        try:
            return _reserve(budget)
        except OrdinaryBudgetLimitExceeded:
            return None

    with ThreadPoolExecutor(max_workers=14) as pool:
        results = list(pool.map(attempt, budgets))
    accepted = [result for result in results if result is not None]
    assert len(accepted) == ORDINARY_MAX_CALLS
    snapshot = OrdinaryBudget(ordinary_engine).public_snapshot()
    assert snapshot["calls_used"] == ORDINARY_MAX_CALLS
    assert snapshot["calls_remaining"] == 0


def test_token_bound_and_unknown_restart_fail_closed(ordinary_engine, monkeypatch):
    budget = OrdinaryBudget(ordinary_engine)
    with pytest.raises(OrdinaryBudgetLimitExceeded, match="tokens"):
        budget.reserve(
            model="nvidia/Nemotron-3_5-Lightning",
            messages=[{"role": "user", "content": "x" * 51_000}],
            tools=None,
            max_output_tokens=ORDINARY_MAX_OUTPUT_TOKENS,
        )
    assert budget.public_snapshot()["calls_used"] == 0

    reservation = _reserve(budget)
    # Recovery treats open reservations as abandoned, so it needs exclusive ownership.
    owner = OrdinaryDispatchOwner(ordinary_engine)
    owner.acquire()
    try:
        assert OrdinaryBudget(ordinary_engine, owner=owner).recover_unresolved() is True
    finally:
        owner.close()
    assert budget.public_snapshot()["halted"] is True
    assert budget.public_snapshot()["calls_used"] == 1


def test_new_utc_day_gets_a_separate_daily_aggregate(ordinary_engine, monkeypatch):
    clock = {"now": datetime(2026, 10, 9, 23, 59, tzinfo=timezone.utc)}
    monkeypatch.setattr(ordinary_module, "_utc_now", lambda: clock["now"])
    budget = OrdinaryBudget(ordinary_engine)
    first = _reserve(budget)
    budget.settle(first, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, None)
    clock["now"] = datetime(2026, 10, 10, 0, 1, tzinfo=timezone.utc)
    assert budget.public_snapshot()["calls_used"] == 0
    second = _reserve(budget)
    assert second.utc_day == "2026-10-10"
