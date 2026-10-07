"""Persistent aggregate request/token budget for explicitly scoped live runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Mapping, Sequence
from uuid import uuid4

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    and_,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine, URL


HARD_MAX_CALLS = 10
HARD_MAX_TOKENS = 50_000
EXPECTED_PROVIDER_MODEL = "nvidia/Nemotron-3_5-Lightning"
EXPECTED_PROVIDER_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
LIVE_BUDGET_ENV = "SHIFTGUARD_LIVE_ACCEPTANCE_LEDGER"
_LEDGER_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SOURCE_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_FAILURE_KINDS = frozenset({"timeout", "provider_error", "invalid_usage", "unknown", "usage_bound_exceeded", "unresolved_restart"})
_metadata = MetaData()

_ledgers = Table(
    "agent_attempt_budgets",
    _metadata,
    Column("ledger_id", String(128), primary_key=True),
    Column("source_digest", String(64), nullable=False),
    Column("max_calls", Integer, nullable=False),
    Column("max_tokens", Integer, nullable=False),
    Column("calls_used", Integer, nullable=False),
    Column("tokens_committed", Integer, nullable=False),
    Column("halted", Integer, nullable=False, default=0),
    Column("halt_reason", String(32), nullable=True),
)
_attempts = Table(
    "agent_attempt_budget_calls",
    _metadata,
    Column("ledger_id", String(128), primary_key=True),
    Column("attempt_no", Integer, primary_key=True),
    Column("attempt_id", String(32), nullable=False, unique=True),
    Column("created_at_utc", String(32), nullable=False),
    Column("input_sha256", String(64), nullable=False),
    Column("input_token_bound", Integer, nullable=False),
    Column("output_token_bound", Integer, nullable=False),
    Column("reserved_tokens", Integer, nullable=False),
    Column("status", String(24), nullable=False),
    Column("failure_kind", String(24), nullable=True),
    Column("prompt_tokens", Integer, nullable=True),
    Column("completion_tokens", Integer, nullable=True),
    Column("total_tokens", Integer, nullable=True),
    Column("provider_request_id_sha256", String(64), nullable=True),
)


class BudgetError(RuntimeError):
    """Base error for an invalid or exhausted persisted attempt budget."""


class BudgetLimitExceeded(BudgetError):
    def __init__(self, limit: str):
        super().__init__(limit)
        self.limit = limit


class BudgetUsageInvalid(BudgetError):
    pass


class BudgetHalted(BudgetError):
    """The persistent ledger is closed to new reservations."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class BudgetBoundExceeded(BudgetError):
    """Valid provider usage exceeded its conservative request reservation."""


@dataclass(frozen=True)
class AttemptReservation:
    ledger_id: str
    attempt_no: int
    attempt_id: str
    reserved_tokens: int


def input_token_upper_bound(
    *,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]] | None,
    max_output_tokens: int,
) -> tuple[int, str]:
    """Return a byte-derived input token ceiling and a content-only fingerprint."""
    bounded = {
        "model": model,
        "messages": list(messages),
        "tools": list(tools or ()),
        "max_tokens": max_output_tokens,
    }
    encoded = json.dumps(
        bounded, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    # UTF-8 byte count bounds byte-level tokenizers. Framing allowance covers
    # per-message/tool separators and provider-side chat-template fields.
    framing = 256 + 256 * (len(messages) + len(tools or ()))
    return len(encoded) + framing, hashlib.sha256(encoded).hexdigest()


class AttemptBudget:
    """A restart-safe, cross-process budget bound to one source and ledger ID."""

    def __init__(
        self,
        engine: Engine,
        *,
        ledger_id: str,
        source_digest: str,
        max_calls: int,
        max_tokens: int,
        owns_engine: bool = False,
    ) -> None:
        if not _LEDGER_ID.fullmatch(ledger_id):
            raise ValueError("ledger_id must be a bounded identifier")
        if not _SOURCE_DIGEST.fullmatch(source_digest):
            raise ValueError("source_digest must be a lowercase SHA-256 digest")
        if type(max_calls) is not int or not 1 <= max_calls <= HARD_MAX_CALLS:
            raise ValueError(f"max_calls must be between 1 and {HARD_MAX_CALLS}")
        if type(max_tokens) is not int or not 1 <= max_tokens <= HARD_MAX_TOKENS:
            raise ValueError(f"max_tokens must be between 1 and {HARD_MAX_TOKENS}")
        self.engine = engine
        self.ledger_id = ledger_id
        self.source_digest = source_digest
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self._owns_engine = owns_engine
        self._local_halt_reason: str | None = None
        _metadata.create_all(engine, tables=[_ledgers, _attempts])
        with engine.begin() as connection:
            current = connection.execute(
                select(_ledgers).where(_ledgers.c.ledger_id == ledger_id)
            ).mappings().first()
            if current is None:
                try:
                    with connection.begin_nested():
                        connection.execute(
                            insert(_ledgers).values(
                                ledger_id=ledger_id,
                                source_digest=source_digest,
                                max_calls=max_calls,
                                max_tokens=max_tokens,
                                calls_used=0,
                                tokens_committed=0,
                                halted=0,
                                halt_reason=None,
                            )
                        )
                except IntegrityError:
                    # Another process initialized the same named ledger.
                    pass
                current = connection.execute(
                    select(_ledgers).where(_ledgers.c.ledger_id == ledger_id)
                ).mappings().first()
            if current is None:
                raise BudgetError("budget ledger could not be initialized")
            if (
                current["source_digest"] != source_digest
                or current["max_calls"] != max_calls
                or current["max_tokens"] != max_tokens
            ):
                raise BudgetError("ledger source binding or ceilings do not match")

    @classmethod
    def from_invocation_environment(cls, settings: Any) -> AttemptBudget | None:
        """Load a live-only budget binding; normal app settings never enable it."""
        encoded = os.environ.get(LIVE_BUDGET_ENV)
        if encoded is None:
            return None
        try:
            value = json.loads(encoded)
        except (TypeError, json.JSONDecodeError):
            raise BudgetError("live attempt budget binding is invalid") from None
        if not isinstance(value, dict) or set(value) != {
            "ledger_id", "source_digest", "max_calls", "max_tokens"
        }:
            raise BudgetError("live attempt budget binding has invalid fields")
        url: URL = settings.sqlalchemy_url
        schema_options = url.query.get("options")
        schema_match = (
            re.fullmatch(r"-csearch_path=(sg_live_acceptance_[a-z0-9_]{1,32})", schema_options)
            if isinstance(schema_options, str) else None
        )
        if (
            settings.agent_enabled is not True
            or not isinstance(settings.nebius_api_key, str)
            or not settings.nebius_api_key.strip()
            or settings.environment != "hosted"
            or settings.nebius_model != EXPECTED_PROVIDER_MODEL
            or settings.nebius_base_url != EXPECTED_PROVIDER_BASE_URL
            or settings.nebius_max_retries != 0
            or url.drivername != "postgresql+psycopg"
            or url.host not in {"127.0.0.1", "localhost", "::1"}
            or url.port != 15432
            or url.database != "shiftguard_gate3"
            or schema_match is None
        ):
            raise BudgetError("live attempt budget requires its isolated local PostgreSQL profile")
        engine = create_engine(url, pool_pre_ping=True)
        try:
            return cls(
                engine,
                ledger_id=value["ledger_id"],
                source_digest=value["source_digest"],
                max_calls=value["max_calls"],
                max_tokens=value["max_tokens"],
                owns_engine=True,
            )
        except Exception:
            engine.dispose()
            raise

    def reserve(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None,
        max_output_tokens: int,
    ) -> AttemptReservation:
        input_bound, fingerprint = input_token_upper_bound(
            model=model,
            messages=messages,
            tools=tools,
            max_output_tokens=max_output_tokens,
        )
        if type(max_output_tokens) is not int or max_output_tokens < 1:
            raise ValueError("max_output_tokens must be a positive integer")
        total_bound = input_bound + max_output_tokens
        attempt_id = uuid4().hex
        if self._local_halt_reason is not None:
            raise BudgetHalted(self._local_halt_reason)
        with self.engine.begin() as connection:
            updated = connection.execute(
                update(_ledgers)
                .where(
                    and_(
                        _ledgers.c.ledger_id == self.ledger_id,
                        _ledgers.c.halted == 0,
                        _ledgers.c.calls_used < self.max_calls,
                        _ledgers.c.tokens_committed + total_bound <= self.max_tokens,
                    )
                )
                .values(
                    calls_used=_ledgers.c.calls_used + 1,
                    tokens_committed=_ledgers.c.tokens_committed + total_bound,
                )
                .returning(_ledgers.c.calls_used)
            ).first()
            if updated is None:
                current = connection.execute(
                    select(_ledgers.c.calls_used, _ledgers.c.tokens_committed,
                           _ledgers.c.halted, _ledgers.c.halt_reason).where(
                        _ledgers.c.ledger_id == self.ledger_id
                    )
                ).first()
                if current is None:
                    raise BudgetError("budget ledger disappeared")
                if current[2]:
                    raise BudgetHalted(current[3] or "unknown")
                if current[0] >= self.max_calls:
                    raise BudgetLimitExceeded("calls")
                raise BudgetLimitExceeded("tokens")
            attempt_no = int(updated[0])
            connection.execute(
                insert(_attempts).values(
                    ledger_id=self.ledger_id,
                    attempt_no=attempt_no,
                    attempt_id=attempt_id,
                    created_at_utc=datetime.now(timezone.utc).isoformat(),
                    input_sha256=fingerprint,
                    input_token_bound=input_bound,
                    output_token_bound=max_output_tokens,
                    reserved_tokens=total_bound,
                    status="reserved",
                    failure_kind=None,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    provider_request_id_sha256=None,
                )
            )
        return AttemptReservation(self.ledger_id, attempt_no, attempt_id, total_bound)

    def settle(
        self,
        reservation: AttemptReservation,
        usage: Mapping[str, Any] | None,
        provider_request_id: str | None,
    ) -> None:
        if not isinstance(usage, Mapping):
            raise BudgetUsageInvalid("provider usage is missing")
        names = ("prompt_tokens", "completion_tokens", "total_tokens")
        values = [usage.get(name) for name in names]
        if any(type(value) is not int or value < 0 for value in values):
            raise BudgetUsageInvalid("provider usage is invalid")
        prompt_tokens, completion_tokens, total_tokens = values
        if total_tokens != prompt_tokens + completion_tokens:
            raise BudgetUsageInvalid("provider usage totals are inconsistent")
        if provider_request_id is not None and (
            not isinstance(provider_request_id, str)
            or not provider_request_id
            or len(provider_request_id.encode("utf-8")) > 256
            or any(ord(char) < 32 for char in provider_request_id)
        ):
            raise BudgetUsageInvalid("provider request identifier is invalid")

        request_fingerprint = (
            hashlib.sha256(provider_request_id.encode("utf-8")).hexdigest()
            if provider_request_id is not None else None
        )
        bound_exceeded = False

        with self.engine.begin() as connection:
            attempt = connection.execute(
                select(_attempts).where(
                    and_(
                        _attempts.c.ledger_id == reservation.ledger_id,
                        _attempts.c.attempt_no == reservation.attempt_no,
                        _attempts.c.attempt_id == reservation.attempt_id,
                        _attempts.c.status == "reserved",
                    )
                )
            ).mappings().first()
            if attempt is None:
                raise BudgetError("attempt is not open for settlement")
            bound_exceeded = (
                prompt_tokens > attempt["input_token_bound"]
                or completion_tokens > attempt["output_token_bound"]
                or total_tokens > attempt["reserved_tokens"]
            )
            settled = connection.execute(
                update(_attempts)
                .where(
                    and_(
                        _attempts.c.ledger_id == reservation.ledger_id,
                        _attempts.c.attempt_no == reservation.attempt_no,
                        _attempts.c.attempt_id == reservation.attempt_id,
                        _attempts.c.status == "reserved",
                    )
                )
                .values(
                    status="over_bound" if bound_exceeded else "settled",
                    failure_kind="usage_bound_exceeded" if bound_exceeded else None,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    provider_request_id_sha256=request_fingerprint,
                )
                .returning(_attempts.c.reserved_tokens)
            ).first()
            if settled is None:
                raise BudgetError("attempt is not open for settlement")
            values_to_set = {
                "tokens_committed": _ledgers.c.tokens_committed - settled.reserved_tokens + total_tokens,
            }
            if bound_exceeded:
                values_to_set.update(halted=1, halt_reason="usage_bound_exceeded")
            connection.execute(
                update(_ledgers)
                .where(_ledgers.c.ledger_id == reservation.ledger_id)
                .values(**values_to_set)
            )
        if bound_exceeded:
            raise BudgetBoundExceeded("provider usage exceeded its reserved component bound")

    def close_unknown(self, reservation: AttemptReservation, failure_kind: str = "unknown") -> None:
        if failure_kind not in _FAILURE_KINDS:
            failure_kind = "unknown"
        self._local_halt_reason = failure_kind
        with self.engine.begin() as connection:
            closed = connection.execute(
                update(_attempts)
                .where(
                    and_(
                        _attempts.c.ledger_id == reservation.ledger_id,
                        _attempts.c.attempt_no == reservation.attempt_no,
                        _attempts.c.attempt_id == reservation.attempt_id,
                        _attempts.c.status == "reserved",
                    )
                )
                .values(status="closed_unknown", failure_kind=failure_kind)
            ).rowcount
            if closed == 1:
                connection.execute(
                    update(_ledgers)
                    .where(_ledgers.c.ledger_id == reservation.ledger_id)
                    .values(halted=1, halt_reason=failure_kind)
                )
        # The original reservation remains committed. Failed and unknown attempts
        # therefore consume both a call and their conservative token allocation.

    def recover_unresolved(self) -> bool:
        """Halt a resumed ledger if a prior process died with a reserved call."""
        with self.engine.begin() as connection:
            unresolved = connection.execute(
                select(_attempts.c.attempt_no).where(
                    and_(_attempts.c.ledger_id == self.ledger_id,
                         _attempts.c.status == "reserved")
                ).limit(1)
            ).first()
            if unresolved is None:
                return False
            connection.execute(
                update(_ledgers)
                .where(_ledgers.c.ledger_id == self.ledger_id)
                .values(halted=1, halt_reason="unresolved_restart")
            )
            return True

    def snapshot(self) -> dict[str, Any]:
        with self.engine.connect() as connection:
            ledger = connection.execute(
                select(_ledgers).where(_ledgers.c.ledger_id == self.ledger_id)
            ).mappings().one()
            attempts = connection.execute(
                select(_attempts)
                .where(_attempts.c.ledger_id == self.ledger_id)
                .order_by(_attempts.c.attempt_no)
            ).mappings().all()
        return {
            "ledger_id": self.ledger_id,
            "source_digest": ledger["source_digest"],
            "max_calls": ledger["max_calls"],
            "max_tokens": ledger["max_tokens"],
            "calls_used": ledger["calls_used"],
            "tokens_committed": ledger["tokens_committed"],
            "halted": bool(ledger["halted"]),
            "halt_reason": ledger["halt_reason"],
            "attempts": [dict(row) for row in attempts],
        }

    def close(self) -> None:
        if self._owns_engine:
            self.engine.dispose()
