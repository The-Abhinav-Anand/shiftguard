from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json

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
    budgets = [OrdinaryBudget(ordinary_engine) for _ in range(ORDINARY_MAX_CALLS + 4)]

    def attempt(budget):
        try:
            return _reserve(budget)
        except OrdinaryBudgetLimitExceeded:
            return None

    with ThreadPoolExecutor(max_workers=ORDINARY_MAX_CALLS + 4) as pool:
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
            messages=[{"role": "user", "content": "x" * (ORDINARY_MAX_TOKENS + 1_000)}],
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


def test_owner_set_daily_allowance_is_fifty_calls_and_one_hundred_thousand_tokens(ordinary_engine):
    assert (ORDINARY_MAX_CALLS, ORDINARY_MAX_TOKENS, ORDINARY_MAX_OUTPUT_TOKENS) == (50, 100_000, 1024)
    assert ordinary_module.ORDINARY_MAX_RETRIES == 0
    snapshot = OrdinaryBudget(ordinary_engine).public_snapshot()
    assert (snapshot["calls_remaining"], snapshot["tokens_remaining"]) == (50, 100_000)


def test_a_day_opened_under_a_different_policy_halts_instead_of_resetting(ordinary_engine):
    # A ledger row written under another allowance is never re-based or reset mid-day.
    budget = OrdinaryBudget(ordinary_engine)
    _reserve(budget)
    with ordinary_engine.begin() as connection:
        connection.execute(ordinary_module._daily.update().values(max_calls=10))
    with pytest.raises(OrdinaryBudgetHalted, match="policy_binding_mismatch"):
        _reserve(budget)
    assert budget.public_snapshot()["halted"] is True
    assert budget.public_snapshot()["calls_used"] == 1


def _call_row(engine, reservation):
    with engine.connect() as connection:
        return connection.execute(
            ordinary_module._calls.select().where(
                ordinary_module._calls.c.reservation_id == reservation.reservation_id
            )
        ).mappings().one()


def _daily_row(engine):
    with engine.connect() as connection:
        return connection.execute(ordinary_module._daily.select()).mappings().one()


def test_close_timeout_charges_in_full_and_keeps_the_day_open(ordinary_engine):
    budget = OrdinaryBudget(ordinary_engine)
    reservation = _reserve(budget)
    budget.close_timeout(reservation)
    row = _call_row(ordinary_engine, reservation)
    assert (row["status"], row["failure_kind"]) == ("closed_timeout", "timeout")
    daily = _daily_row(ordinary_engine)
    assert daily["calls_used"] == 1
    assert daily["tokens_committed"] == reservation.reserved_tokens
    assert daily["halted"] == 0 and daily["halt_reason"] is None
    assert budget.public_snapshot()["halted"] is False
    again = _reserve(budget)
    assert again.reservation_id != reservation.reservation_id
    assert _daily_row(ordinary_engine)["calls_used"] == 2


def test_close_timeout_is_idempotent_and_never_changes_a_settled_row(ordinary_engine):
    budget = OrdinaryBudget(ordinary_engine)
    timed_out = _reserve(budget)
    budget.close_timeout(timed_out)
    budget.close_timeout(timed_out)
    assert _daily_row(ordinary_engine)["tokens_committed"] == timed_out.reserved_tokens
    assert _call_row(ordinary_engine, timed_out)["status"] == "closed_timeout"

    settled = _reserve(budget)
    budget.settle(settled, {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}, None)
    before = _daily_row(ordinary_engine)
    budget.close_timeout(settled)
    row = _call_row(ordinary_engine, settled)
    assert (row["status"], row["failure_kind"], row["total_tokens"]) == ("settled", None, 5)
    assert _daily_row(ordinary_engine) == before

    # A timeout never resurrects or relabels a row closed as unknown.
    unknown = _reserve(budget)
    budget.close_unknown(unknown, "provider_error")
    budget.close_timeout(unknown)
    assert _call_row(ordinary_engine, unknown)["status"] == "closed_unknown"
    assert _daily_row(ordinary_engine)["halt_reason"] == "provider_error"


def test_repeated_timeouts_exhaust_the_cap_through_normal_limit_errors(ordinary_engine):
    budget = OrdinaryBudget(ordinary_engine)
    charged = 0
    for _ in range(ORDINARY_MAX_CALLS + 5):
        try:
            reservation = _reserve(budget)
        except OrdinaryBudgetLimitExceeded as err:
            assert err.limit in {"calls", "tokens"}
            break
        budget.close_timeout(reservation)
        charged += 1
        daily = _daily_row(ordinary_engine)
        assert daily["calls_used"] == charged <= ORDINARY_MAX_CALLS
        assert daily["tokens_committed"] <= ORDINARY_MAX_TOKENS
        assert daily["halted"] == 0
    else:
        pytest.fail("repeated timeouts never reached the daily cap")
    assert charged == ORDINARY_MAX_CALLS
    assert _daily_row(ordinary_engine)["halted"] == 0


@pytest.mark.parametrize(
    "kind",
    ["timeout", "provider_error", "invalid_usage", "unknown", "usage_bound_exceeded"],
)
def test_close_unknown_still_halts_the_day_for_every_kind(ordinary_engine, kind):
    budget = OrdinaryBudget(ordinary_engine)
    reservation = _reserve(budget)
    budget.close_unknown(reservation, kind)
    daily = _daily_row(ordinary_engine)
    assert (daily["halted"], daily["halt_reason"]) == (1, kind)
    assert _call_row(ordinary_engine, reservation)["status"] == "closed_unknown"
    with pytest.raises(OrdinaryBudgetHalted, match=kind):
        _reserve(budget)


def test_policy_digest_binds_the_timeout_policy(ordinary_engine):
    old_policy = hashlib.sha256(
        json.dumps(
            {
                "namespace": ordinary_module.ORDINARY_NAMESPACE,
                "max_calls": ORDINARY_MAX_CALLS,
                "max_tokens": ORDINARY_MAX_TOKENS,
                "max_output_tokens": ORDINARY_MAX_OUTPUT_TOKENS,
                "max_retries": ordinary_module.ORDINARY_MAX_RETRIES,
                "unknown_usage": "halt-day",
                "dispatch": "reserve-before-dispatch",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert old_policy != ordinary_module._POLICY_DIGEST
    budget = OrdinaryBudget(ordinary_engine)
    _reserve(budget)
    with ordinary_engine.begin() as connection:
        connection.execute(ordinary_module._daily.update().values(policy_digest=old_policy))
    with pytest.raises(OrdinaryBudgetHalted, match="policy_binding_mismatch"):
        _reserve(budget)
    assert budget.public_snapshot()["halted"] is True
