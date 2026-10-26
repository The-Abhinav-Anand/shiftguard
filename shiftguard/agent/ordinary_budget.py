"""Durable UTC-day usage budget shared by ordinary model requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence
from uuid import uuid4

from sqlalchemy import (
    Column,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    and_,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from shiftguard.agent.budget import input_token_upper_bound
from shiftguard.agent.ordinary_owner import OrdinaryDispatchOwner, OrdinaryOwnerUnavailable


ORDINARY_NAMESPACE = "ordinary-v1"
# Owner-set daily allowance (15 October 2026): 50 calls and 100,000 tokens per UTC day.
ORDINARY_MAX_CALLS = 50
ORDINARY_MAX_TOKENS = 100_000
ORDINARY_MAX_OUTPUT_TOKENS = 1024
ORDINARY_MAX_RETRIES = 0
_SOURCE_DIGEST = hashlib.sha256(b"shiftguard.ordinary_budget.v1").hexdigest()
_POLICY_DIGEST = hashlib.sha256(
    json.dumps(
        {
            "namespace": ORDINARY_NAMESPACE,
            "max_calls": ORDINARY_MAX_CALLS,
            "max_tokens": ORDINARY_MAX_TOKENS,
            "max_output_tokens": ORDINARY_MAX_OUTPUT_TOKENS,
            "max_retries": ORDINARY_MAX_RETRIES,
            "unknown_usage": "halt-day",
            "timeout": "charge-reservation-no-halt",
            "dispatch": "reserve-before-dispatch",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

_metadata = MetaData()
_daily = Table(
    "ordinary_budget_daily",
    _metadata,
    Column("namespace", String(32), nullable=False),
    Column("utc_day", String(10), nullable=False),
    Column("source_digest", String(64), nullable=False),
    Column("policy_digest", String(64), nullable=False),
    Column("max_calls", Integer, nullable=False),
    Column("max_tokens", Integer, nullable=False),
    Column("calls_used", Integer, nullable=False),
    Column("tokens_committed", Integer, nullable=False),
    Column("halted", Integer, nullable=False),
    Column("halt_reason", String(32), nullable=True),
    PrimaryKeyConstraint("namespace", "utc_day"),
)
_calls = Table(
    "ordinary_budget_calls",
    _metadata,
    Column("reservation_id", String(32), primary_key=True),
    Column("namespace", String(32), nullable=False),
    Column("utc_day", String(10), nullable=False),
    Column("created_at_utc", String(32), nullable=False),
    Column("input_sha256", String(64), nullable=False),
    Column("input_token_bound", Integer, nullable=False),
    Column("output_token_bound", Integer, nullable=False),
    Column("reserved_tokens", Integer, nullable=False),
    Column("status", String(24), nullable=False),
    Column("failure_kind", String(32), nullable=True),
    Column("prompt_tokens", Integer, nullable=True),
    Column("completion_tokens", Integer, nullable=True),
    Column("total_tokens", Integer, nullable=True),
    Column("provider_request_id_sha256", String(64), nullable=True),
    ForeignKeyConstraint(
        ["namespace", "utc_day"],
        ["ordinary_budget_daily.namespace", "ordinary_budget_daily.utc_day"],
        ondelete="CASCADE",
    ),
)


class OrdinaryBudgetError(RuntimeError):
    """Base class for ordinary usage ledger errors."""


class OrdinaryBudgetLimitExceeded(OrdinaryBudgetError):
    def __init__(self, limit: str):
        super().__init__(limit)
        self.limit = limit


class OrdinaryBudgetHalted(OrdinaryBudgetError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class OrdinaryBudgetUsageInvalid(OrdinaryBudgetError):
    pass


class OrdinaryBudgetBoundExceeded(OrdinaryBudgetError):
    pass


@dataclass(frozen=True)
class OrdinaryReservation:
    utc_day: str
    reservation_id: str
    reserved_tokens: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrdinaryBudget:
    """A separate, durable daily ledger for all ordinary provider dispatches."""

    def __init__(self, engine: Engine, *, owner: OrdinaryDispatchOwner | None = None):
        self.engine = engine
        self.owner = owner

    @staticmethod
    def _day(now: datetime | None = None) -> str:
        return (now or _utc_now()).astimezone(timezone.utc).date().isoformat()

    @staticmethod
    def _validate_policy(row: Mapping[str, Any]) -> None:
        if (
            row["source_digest"] != _SOURCE_DIGEST
            or row["policy_digest"] != _POLICY_DIGEST
            or row["max_calls"] != ORDINARY_MAX_CALLS
            or row["max_tokens"] != ORDINARY_MAX_TOKENS
        ):
            raise OrdinaryBudgetHalted("policy_binding_mismatch")

    def _ensure_daily(self, connection, day: str):
        values = {
            "namespace": ORDINARY_NAMESPACE,
            "utc_day": day,
            "source_digest": _SOURCE_DIGEST,
            "policy_digest": _POLICY_DIGEST,
            "max_calls": ORDINARY_MAX_CALLS,
            "max_tokens": ORDINARY_MAX_TOKENS,
            "calls_used": 0,
            "tokens_committed": 0,
            "halted": 0,
            "halt_reason": None,
        }
        if connection.dialect.name == "sqlite":
            statement = sqlite_insert(_daily).values(**values).on_conflict_do_nothing(
                index_elements=["namespace", "utc_day"]
            )
            connection.execute(statement)
        elif connection.dialect.name == "postgresql":
            statement = pg_insert(_daily).values(**values).on_conflict_do_nothing(
                index_elements=["namespace", "utc_day"]
            )
            connection.execute(statement)
        else:
            current = connection.execute(
                select(_daily).where(
                    and_(_daily.c.namespace == ORDINARY_NAMESPACE, _daily.c.utc_day == day)
                )
            ).mappings().first()
            if current is None:
                connection.execute(insert(_daily).values(**values))
        current = connection.execute(
            select(_daily).where(
                and_(_daily.c.namespace == ORDINARY_NAMESPACE, _daily.c.utc_day == day)
            )
        ).mappings().first()
        if current is None:
            raise OrdinaryBudgetError("ordinary daily budget could not be initialized")
        self._validate_policy(current)
        return current

    def reserve(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None,
        max_output_tokens: int,
    ) -> OrdinaryReservation:
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= ORDINARY_MAX_OUTPUT_TOKENS:
            raise ValueError("ordinary max_output_tokens is outside its policy bound")
        input_bound, fingerprint = input_token_upper_bound(
            model=model,
            messages=messages,
            tools=tools,
            max_output_tokens=max_output_tokens,
        )
        reserved_tokens = input_bound + max_output_tokens
        if self.owner is not None:
            # Fail closed before writing anything if this process no longer owns dispatch.
            self.owner.assert_held()
        day = self._day()
        reservation_id = uuid4().hex
        now = _utc_now().isoformat()
        with self.engine.begin() as connection:
            self._ensure_daily(connection, day)
            updated = connection.execute(
                update(_daily)
                .where(
                    and_(
                        _daily.c.namespace == ORDINARY_NAMESPACE,
                        _daily.c.utc_day == day,
                        _daily.c.halted == 0,
                        _daily.c.calls_used < ORDINARY_MAX_CALLS,
                        _daily.c.tokens_committed + reserved_tokens <= ORDINARY_MAX_TOKENS,
                    )
                )
                .values(
                    calls_used=_daily.c.calls_used + 1,
                    tokens_committed=_daily.c.tokens_committed + reserved_tokens,
                )
                .returning(_daily.c.calls_used)
            ).first()
            if updated is None:
                current = connection.execute(
                    select(_daily).where(
                        and_(_daily.c.namespace == ORDINARY_NAMESPACE, _daily.c.utc_day == day)
                    )
                ).mappings().one()
                self._validate_policy(current)
                if current["halted"]:
                    raise OrdinaryBudgetHalted(current["halt_reason"] or "unknown")
                if current["calls_used"] >= ORDINARY_MAX_CALLS:
                    raise OrdinaryBudgetLimitExceeded("calls")
                raise OrdinaryBudgetLimitExceeded("tokens")
            connection.execute(
                insert(_calls).values(
                    reservation_id=reservation_id,
                    namespace=ORDINARY_NAMESPACE,
                    utc_day=day,
                    created_at_utc=now,
                    input_sha256=fingerprint,
                    input_token_bound=input_bound,
                    output_token_bound=max_output_tokens,
                    reserved_tokens=reserved_tokens,
                    status="reserved",
                    failure_kind=None,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    provider_request_id_sha256=None,
                )
            )
        return OrdinaryReservation(day, reservation_id, reserved_tokens)

    def settle(
        self,
        reservation: OrdinaryReservation,
        usage: Mapping[str, Any] | None,
        provider_request_id: str | None,
    ) -> None:
        if not isinstance(usage, Mapping):
            raise OrdinaryBudgetUsageInvalid("provider usage is missing")
        names = ("prompt_tokens", "completion_tokens", "total_tokens")
        values = [usage.get(name) for name in names]
        if any(type(value) is not int or value < 0 for value in values):
            raise OrdinaryBudgetUsageInvalid("provider usage is invalid")
        prompt_tokens, completion_tokens, total_tokens = values
        if total_tokens != prompt_tokens + completion_tokens:
            raise OrdinaryBudgetUsageInvalid("provider usage is inconsistent")
        if provider_request_id is not None and (
            not isinstance(provider_request_id, str)
            or not provider_request_id
            or len(provider_request_id.encode("utf-8")) > 256
            or any(ord(char) < 32 for char in provider_request_id)
        ):
            raise OrdinaryBudgetUsageInvalid("provider request identifier is invalid")
        request_digest = (
            hashlib.sha256(provider_request_id.encode("utf-8")).hexdigest()
            if provider_request_id is not None
            else None
        )
        with self.engine.begin() as connection:
            attempt = connection.execute(
                select(_calls).where(
                    and_(
                        _calls.c.namespace == ORDINARY_NAMESPACE,
                        _calls.c.utc_day == reservation.utc_day,
                        _calls.c.reservation_id == reservation.reservation_id,
                        _calls.c.status == "reserved",
                    )
                )
            ).mappings().first()
            if attempt is None:
                raise OrdinaryBudgetError("ordinary reservation is not open for settlement")
            exceeded = (
                prompt_tokens > attempt["input_token_bound"]
                or completion_tokens > attempt["output_token_bound"]
                or total_tokens > attempt["reserved_tokens"]
            )
            settled = connection.execute(
                update(_calls)
                .where(
                    and_(
                        _calls.c.reservation_id == reservation.reservation_id,
                        _calls.c.status == "reserved",
                    )
                )
                .values(
                    status="over_bound" if exceeded else "settled",
                    failure_kind="usage_bound_exceeded" if exceeded else None,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    provider_request_id_sha256=request_digest,
                )
                .returning(_calls.c.reserved_tokens)
            ).first()
            if settled is None:
                raise OrdinaryBudgetError("ordinary reservation is not open for settlement")
            values_to_set = {
                "tokens_committed": _daily.c.tokens_committed - settled[0] + total_tokens,
            }
            if exceeded:
                values_to_set.update(halted=1, halt_reason="usage_bound_exceeded")
            connection.execute(
                update(_daily)
                .where(
                    and_(
                        _daily.c.namespace == ORDINARY_NAMESPACE,
                        _daily.c.utc_day == reservation.utc_day,
                    )
                )
                .values(**values_to_set)
            )
        if exceeded:
            raise OrdinaryBudgetBoundExceeded("provider usage exceeded its reserved bounds")

    def close_unknown(
        self, reservation: OrdinaryReservation, failure_kind: str = "unknown"
    ) -> None:
        if failure_kind not in {
            "timeout",
            "provider_error",
            "invalid_usage",
            "unknown",
            "usage_bound_exceeded",
            "unresolved_restart",
        }:
            failure_kind = "unknown"
        with self.engine.begin() as connection:
            closed = connection.execute(
                update(_calls)
                .where(
                    and_(
                        _calls.c.namespace == ORDINARY_NAMESPACE,
                        _calls.c.utc_day == reservation.utc_day,
                        _calls.c.reservation_id == reservation.reservation_id,
                        _calls.c.status == "reserved",
                    )
                )
                .values(status="closed_unknown", failure_kind=failure_kind)
            ).rowcount
            if closed:
                connection.execute(
                    update(_daily)
                    .where(
                        and_(
                            _daily.c.namespace == ORDINARY_NAMESPACE,
                            _daily.c.utc_day == reservation.utc_day,
                        )
                    )
                    .values(halted=1, halt_reason=failure_kind)
                )

    def close_timeout(self, reservation: OrdinaryReservation) -> int:
        """Close an open reservation after a provider timeout without halting the day.

        The reservation (byte-bounded input plus the output cap) stays fully charged
        in calls_used and tokens_committed, so the daily hard cap still holds. Only a
        row that is still "reserved" changes; a second call or a settled row is a no-op.
        Returns the number of rows changed (0 when nothing was open).
        """
        with self.engine.begin() as connection:
            result = connection.execute(
                update(_calls)
                .where(
                    and_(
                        _calls.c.namespace == ORDINARY_NAMESPACE,
                        _calls.c.utc_day == reservation.utc_day,
                        _calls.c.reservation_id == reservation.reservation_id,
                        _calls.c.status == "reserved",
                    )
                )
                .values(status="closed_timeout", failure_kind="timeout")
            )
            return int(result.rowcount)

    def release_unstarted(self, reservation: OrdinaryReservation) -> None:
        """Release a reservation only when a second local ledger blocks dispatch."""
        with self.engine.begin() as connection:
            released = connection.execute(
                update(_calls)
                .where(
                    and_(
                        _calls.c.namespace == ORDINARY_NAMESPACE,
                        _calls.c.utc_day == reservation.utc_day,
                        _calls.c.reservation_id == reservation.reservation_id,
                        _calls.c.status == "reserved",
                    )
                )
                .values(status="released", failure_kind="dispatch_not_started")
                .returning(_calls.c.reserved_tokens)
            ).first()
            if released is not None:
                connection.execute(
                    update(_daily)
                    .where(
                        and_(
                            _daily.c.namespace == ORDINARY_NAMESPACE,
                            _daily.c.utc_day == reservation.utc_day,
                            _daily.c.calls_used > 0,
                        )
                    )
                    .values(
                        calls_used=_daily.c.calls_used - 1,
                        tokens_committed=_daily.c.tokens_committed - released[0],
                    )
                )

    def recover_unresolved(self) -> bool:
        """Fail closed for this UTC day after a process died with an open call.

        An open reservation is only abandoned if no other process can still be
        dispatching it, so recovery requires held exclusive ownership.
        """
        if self.owner is None:
            raise OrdinaryOwnerUnavailable("recovery requires exclusive ordinary dispatch ownership")
        self.owner.assert_held()
        day = self._day()
        with self.engine.begin() as connection:
            unresolved = connection.execute(
                select(_calls.c.reservation_id).where(
                    and_(
                        _calls.c.namespace == ORDINARY_NAMESPACE,
                        _calls.c.utc_day == day,
                        _calls.c.status == "reserved",
                    )
                )
            ).all()
            if not unresolved:
                return False
            connection.execute(
                update(_calls)
                .where(
                    and_(
                        _calls.c.namespace == ORDINARY_NAMESPACE,
                        _calls.c.utc_day == day,
                        _calls.c.status == "reserved",
                    )
                )
                .values(status="closed_unknown", failure_kind="unresolved_restart")
            )
            connection.execute(
                update(_daily)
                .where(
                    and_(_daily.c.namespace == ORDINARY_NAMESPACE, _daily.c.utc_day == day)
                )
                .values(halted=1, halt_reason="unresolved_restart")
            )
            return True

    def public_snapshot(self) -> dict[str, Any]:
        day = self._day()
        with self.engine.connect() as connection:
            row = connection.execute(
                select(_daily).where(
                    and_(_daily.c.namespace == ORDINARY_NAMESPACE, _daily.c.utc_day == day)
                )
            ).mappings().first()
        if row is None:
            return {
                "utc_day": day,
                "calls_used": 0,
                "calls_remaining": ORDINARY_MAX_CALLS,
                "tokens_committed": 0,
                "tokens_remaining": ORDINARY_MAX_TOKENS,
                "halted": False,
            }
        try:
            self._validate_policy(row)
            halted = bool(row["halted"])
        except OrdinaryBudgetHalted:
            halted = True
        calls = int(row["calls_used"])
        tokens = int(row["tokens_committed"])
        return {
            "utc_day": day,
            "calls_used": calls,
            "calls_remaining": max(0, ORDINARY_MAX_CALLS - calls),
            "tokens_committed": tokens,
            "tokens_remaining": max(0, ORDINARY_MAX_TOKENS - tokens),
            "halted": halted,
        }
