"""Durable, session-owned storage for ordinary general conversations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping, Sequence
from uuid import uuid4

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


_metadata = MetaData()
_conversations = Table(
    "shiftguard_chat_conversations",
    _metadata,
    Column("id", String(64), primary_key=True),
    Column("session_id", String(128), nullable=False),
    Column("pending_receipt_id", String(32), nullable=True),
    Column("created_at_utc", String(32), nullable=False),
    Column("updated_at_utc", String(32), nullable=False),
)
_messages = Table(
    "shiftguard_chat_messages",
    _metadata,
    Column("id", String(32), primary_key=True),
    Column("conversation_id", String(64), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("role", String(9), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at_utc", String(32), nullable=False),
)
_receipts = Table(
    "shiftguard_chat_receipts",
    _metadata,
    Column("id", String(32), primary_key=True),
    Column("session_id", String(128), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("conversation_id", String(64), nullable=False),
    Column("user_message_id", String(32), nullable=False),
    Column("assistant_message_id", String(32), nullable=True),
    Column("status", String(16), nullable=False),
    Column("response_json", Text, nullable=True),
    Column("created_at_utc", String(32), nullable=False),
    Column("completed_at_utc", String(32), nullable=True),
)


class ChatStoreError(RuntimeError):
    pass


class ChatIdempotencyConflict(ChatStoreError):
    pass


class ChatConversationNotFound(ChatStoreError):
    pass


class ChatConversationBusy(ChatStoreError):
    pass


class ChatReceiptInvalid(ChatStoreError):
    """A stored receipt cannot be served consistently; nothing is fabricated or resent."""


@dataclass(frozen=True)
class ChatReceipt:
    id: str
    conversation_id: str
    user_message_id: str
    status: str
    response_json: str | None
    is_new: bool
    assistant_message_id: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatStore:
    """Store receipts and messages before provider dispatch for at-most-once replay."""

    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def _receipt(row: Mapping[str, Any], *, is_new: bool = False) -> ChatReceipt:
        return ChatReceipt(
            id=row["id"],
            conversation_id=row["conversation_id"],
            user_message_id=row["user_message_id"],
            status=row["status"],
            response_json=row["response_json"],
            is_new=is_new,
            assistant_message_id=row["assistant_message_id"],
        )

    def _find_receipt(self, session_id: str, idempotency_key: str):
        with self.engine.connect() as connection:
            return connection.execute(
                select(_receipts).where(
                    and_(
                        _receipts.c.session_id == session_id,
                        _receipts.c.idempotency_key == idempotency_key,
                    )
                )
            ).mappings().first()

    def create_or_get(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        request_hash: str,
        prompt: str,
        requested_conversation_id: str | None,
    ) -> ChatReceipt:
        existing = self._find_receipt(session_id, idempotency_key)
        if existing is not None:
            if existing["request_hash"] != request_hash:
                raise ChatIdempotencyConflict("idempotency key was already used for a different request")
            return self._receipt(existing)

        now = _now()
        conversation_id = requested_conversation_id or uuid4().hex
        receipt_id = uuid4().hex
        user_message_id = uuid4().hex
        try:
            with self.engine.begin() as connection:
                if requested_conversation_id is None:
                    connection.execute(
                        insert(_conversations).values(
                            id=conversation_id,
                            session_id=session_id,
                            pending_receipt_id=None,
                            created_at_utc=now,
                            updated_at_utc=now,
                        )
                    )
                conversation = connection.execute(
                    select(_conversations)
                    .where(_conversations.c.id == conversation_id)
                    .with_for_update()
                ).mappings().first()
                if conversation is None or conversation["session_id"] != session_id:
                    raise ChatConversationNotFound("conversation does not belong to this session")
                claimed = connection.execute(
                    update(_conversations)
                    .where(
                        and_(
                            _conversations.c.id == conversation_id,
                            _conversations.c.pending_receipt_id.is_(None),
                        )
                    )
                    .values(pending_receipt_id=receipt_id, updated_at_utc=now)
                    .returning(_conversations.c.id)
                ).first()
                if claimed is None:
                    raise ChatConversationBusy("conversation already has a pending message")
                ordinal = connection.execute(
                    select(func.coalesce(func.max(_messages.c.ordinal), 0)).where(
                        _messages.c.conversation_id == conversation_id
                    )
                ).scalar_one() + 1
                connection.execute(
                    insert(_messages).values(
                        id=user_message_id,
                        conversation_id=conversation_id,
                        ordinal=ordinal,
                        role="user",
                        content=prompt,
                        created_at_utc=now,
                    )
                )
                connection.execute(
                    insert(_receipts).values(
                        id=receipt_id,
                        session_id=session_id,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        conversation_id=conversation_id,
                        user_message_id=user_message_id,
                        assistant_message_id=None,
                        status="PENDING",
                        response_json=None,
                        created_at_utc=now,
                        completed_at_utc=None,
                    )
                )
        except (IntegrityError, ChatConversationBusy) as error:
            # A concurrent request with the same key may have won the race (and the
            # conversation claim); resolve to its receipt instead of reporting busy.
            raced = self._find_receipt(session_id, idempotency_key)
            if raced is None:
                raise error from None
            if raced["request_hash"] != request_hash:
                raise ChatIdempotencyConflict(
                    "idempotency key was already used for a different request"
                ) from None
            return self._receipt(raced)
        return ChatReceipt(
            id=receipt_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            status="PENDING",
            response_json=None,
            is_new=True,
        )

    def history(self, conversation_id: str) -> list[dict[str, str]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(_messages.c.role, _messages.c.content)
                .where(_messages.c.conversation_id == conversation_id)
                .order_by(_messages.c.ordinal)
            ).all()
        return [{"role": row.role, "content": row.content} for row in rows]

    def complete(
        self,
        receipt: ChatReceipt,
        response: Mapping[str, Any],
        reply: str,
        assistant_message_id: str,
    ) -> dict[str, Any]:
        """Persist the assistant reply and return the identity-bearing stored response."""
        now = _now()
        with self.engine.begin() as connection:
            current = connection.execute(
                select(_receipts).where(
                    and_(_receipts.c.id == receipt.id, _receipts.c.status == "PENDING")
                )
            ).mappings().first()
            if current is None:
                raise ChatStoreError("chat receipt is no longer pending")
            user_ordinal = connection.execute(
                select(_messages.c.ordinal).where(_messages.c.id == receipt.user_message_id)
            ).scalar_one()
            ordinal = connection.execute(
                select(func.coalesce(func.max(_messages.c.ordinal), 0)).where(
                    _messages.c.conversation_id == receipt.conversation_id
                )
            ).scalar_one() + 1
            stored = {
                **dict(response),
                "message_id": assistant_message_id,
                "receipt_id": receipt.id,
                "user_message_id": receipt.user_message_id,
                "assistant_message_id": assistant_message_id,
                "user_ordinal": int(user_ordinal),
                "assistant_ordinal": int(ordinal),
                "conversation_id": receipt.conversation_id,
            }
            response_json = json.dumps(
                stored, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            )
            connection.execute(
                insert(_messages).values(
                    id=assistant_message_id,
                    conversation_id=receipt.conversation_id,
                    ordinal=ordinal,
                    role="assistant",
                    content=reply,
                    created_at_utc=now,
                )
            )
            updated = connection.execute(
                update(_receipts)
                .where(and_(_receipts.c.id == receipt.id, _receipts.c.status == "PENDING"))
                .values(
                    assistant_message_id=assistant_message_id,
                    status="COMPLETED",
                    response_json=response_json,
                    completed_at_utc=now,
                )
                .returning(_receipts.c.id)
            ).first()
            if updated is None:
                raise ChatStoreError("chat receipt is no longer pending")
            connection.execute(
                update(_conversations)
                .where(
                    and_(
                        _conversations.c.id == receipt.conversation_id,
                        _conversations.c.pending_receipt_id == receipt.id,
                    )
                )
                .values(pending_receipt_id=None, updated_at_utc=now)
            )
        return stored

    def fail_known(
        self,
        receipt: ChatReceipt,
        *,
        status_code: int,
        response: Mapping[str, Any],
    ) -> None:
        """Make a known, returned-but-rejected response a durable terminal failure.

        One transaction: the receipt moves PENDING -> FAILED (the stored body is
        replayed verbatim) and the conversation claim is released only if it still
        belongs to this receipt. Any other state rolls everything back.
        """
        if type(status_code) is not int or not 400 <= status_code <= 599:
            raise ValueError("a terminal chat failure needs an HTTP error status")
        try:
            response_json = json.dumps(
                {"http_status": status_code, "body": dict(response)},
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except TypeError as error:
            raise ValueError("terminal chat failure body is not JSON serialisable") from error
        now = _now()
        with self.engine.begin() as connection:
            failed = connection.execute(
                update(_receipts)
                .where(and_(_receipts.c.id == receipt.id, _receipts.c.status == "PENDING"))
                .values(status="FAILED", response_json=response_json, completed_at_utc=now)
            )
            if failed.rowcount != 1:
                raise ChatStoreError("chat receipt is no longer pending")
            released = connection.execute(
                update(_conversations)
                .where(
                    and_(
                        _conversations.c.id == receipt.conversation_id,
                        _conversations.c.pending_receipt_id == receipt.id,
                    )
                )
                .values(pending_receipt_id=None, updated_at_utc=now)
            )
            if released.rowcount != 1:
                raise ChatStoreError("conversation claim does not belong to this receipt")

    @staticmethod
    def failed_response(receipt: ChatReceipt) -> tuple[int, dict[str, Any]]:
        """Return the stored terminal status code and body of a FAILED receipt."""
        try:
            stored = json.loads(receipt.response_json or "")
        except ValueError:
            raise ChatReceiptInvalid("stored terminal failure is unreadable") from None
        body = stored.get("body") if isinstance(stored, dict) else None
        status_code = stored.get("http_status") if isinstance(stored, dict) else None
        if (
            type(status_code) is not int
            or not 400 <= status_code <= 599
            or not isinstance(body, dict)
            or body.get("status") != "FAILED"
            or body.get("receipt_id") != receipt.id
        ):
            raise ChatReceiptInvalid("stored terminal failure is inconsistent")
        return status_code, body

    def completed_body(self, receipt: ChatReceipt) -> dict[str, Any]:
        """Return a COMPLETED receipt's response with verified message identities.

        Receipts completed before identities were stored lack those fields; they
        are derived here from the receipt and message rows (never from content or
        position), and the stored reply text is returned untouched. Anything that
        cannot be derived or contradicts the rows fails closed.
        """
        try:
            stored = json.loads(receipt.response_json or "")
        except ValueError:
            raise ChatReceiptInvalid("stored chat reply is unreadable") from None
        if not isinstance(stored, dict) or stored.get("status") != "COMPLETED":
            raise ChatReceiptInvalid("stored chat reply is not a completed response")
        with self.engine.connect() as connection:
            row = connection.execute(
                select(_receipts).where(_receipts.c.id == receipt.id)
            ).mappings().first()
            if row is None or row["status"] != "COMPLETED" or not row["assistant_message_id"]:
                raise ChatReceiptInvalid("completed receipt has no assistant message")
            messages = {
                item["id"]: item
                for item in connection.execute(
                    select(_messages).where(
                        _messages.c.id.in_([row["user_message_id"], row["assistant_message_id"]])
                    )
                ).mappings()
            }
        user = messages.get(row["user_message_id"])
        assistant = messages.get(row["assistant_message_id"])
        if (
            user is None
            or assistant is None
            or user["role"] != "user"
            or assistant["role"] != "assistant"
            or user["conversation_id"] != row["conversation_id"]
            or assistant["conversation_id"] != row["conversation_id"]
            or not user["ordinal"] < assistant["ordinal"]
        ):
            raise ChatReceiptInvalid("completed receipt does not match its message rows")
        derived = {
            "receipt_id": row["id"],
            "user_message_id": user["id"],
            "assistant_message_id": assistant["id"],
            "user_ordinal": int(user["ordinal"]),
            "assistant_ordinal": int(assistant["ordinal"]),
            "conversation_id": row["conversation_id"],
            "message_id": assistant["id"],
        }
        body = dict(stored)
        for name, value in derived.items():
            if name in body and body[name] != value:
                raise ChatReceiptInvalid("stored reply identity contradicts its message rows")
            body[name] = value
        if isinstance(body.get("reply"), str) and body["reply"] != assistant["content"]:
            raise ChatReceiptInvalid("stored reply text does not match its assistant message")
        return body

    def discard_undispatched(self, receipt: ChatReceipt) -> None:
        """Forget a request rejected before any provider dispatch so it can be retried."""
        with self.engine.begin() as connection:
            discarded = connection.execute(
                delete(_receipts)
                .where(and_(_receipts.c.id == receipt.id, _receipts.c.status == "PENDING"))
                .returning(_receipts.c.id)
            ).first()
            if discarded is None:
                return
            connection.execute(
                delete(_messages).where(_messages.c.id == receipt.user_message_id)
            )
            connection.execute(
                update(_conversations)
                .where(
                    and_(
                        _conversations.c.id == receipt.conversation_id,
                        _conversations.c.pending_receipt_id == receipt.id,
                    )
                )
                .values(pending_receipt_id=None, updated_at_utc=_now())
            )
            remaining = connection.execute(
                select(func.count())
                .select_from(_messages)
                .where(_messages.c.conversation_id == receipt.conversation_id)
            ).scalar_one()
            if not remaining:
                connection.execute(
                    delete(_conversations).where(
                        _conversations.c.id == receipt.conversation_id
                    )
                )

    def get_conversation(self, conversation_id: str):
        with self.engine.connect() as connection:
            return connection.execute(
                select(_conversations).where(_conversations.c.id == conversation_id)
            ).mappings().first()

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """Public message records with their persisted identity; never sent to the provider."""
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    _messages.c.id, _messages.c.ordinal, _messages.c.role, _messages.c.content
                )
                .where(_messages.c.conversation_id == conversation_id)
                .order_by(_messages.c.ordinal)
            ).all()
        return [
            {"id": row.id, "ordinal": int(row.ordinal), "role": row.role, "content": row.content}
            for row in rows
        ]
