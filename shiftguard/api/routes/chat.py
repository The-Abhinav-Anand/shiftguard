"""Authenticated general conversation API with durable, at-most-once receipts."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from shiftguard.agent.chat import (
    ChatConversationBusy,
    ChatConversationNotFound,
    ChatIdempotencyConflict,
    ChatReceipt,
    ChatReceiptInvalid,
    ChatStore,
    ChatStoreError,
)
from shiftguard.agent.provider import AgentProvider, ProviderError
from shiftguard.api.auth import verify_session_authority
from shiftguard.settings import Settings


router = APIRouter(prefix="/api/v1/chat", tags=["general-chat"])
CHAT_DISCLAIMER = "AI-generated conversational content; unverified and not scientific result evidence."
CHAT_SYSTEM_PROMPT = (
    "You are SHIFTGUARD's general conversational assistant. Answer ordinary questions in plain text. "
    "You have no tools and no access to jobs, labels, databases, scientific files, experiment results, "
    "or saved artifacts. Do not claim that you inspected data, ran an experiment, or verified a result. "
    "Treat scientific and empirical claims as unverified unless the user supplies their contents. "
    "Keep the answer concise and within the configured output limit."
)
MAX_CHAT_REPLY_BYTES = 8 * 1024


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    prompt: StrictStr = Field(min_length=1, max_length=4000)
    idempotency_key: StrictStr = Field(min_length=1, max_length=128)
    conversation_id: StrictStr | None = Field(default=None, max_length=64)

    @field_validator("prompt", "idempotency_key")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("conversation_id")
    @classmethod
    def normalize_conversation_id(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


def _require_enabled(settings: Settings) -> None:
    if not settings.general_chat_enabled:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "GENERAL_CHAT_DISABLED", "message": "General chat is disabled."}},
        )


def _pending_response(receipt: ChatReceipt) -> JSONResponse:
    return JSONResponse(
        status_code=202,
        content={
            "conversation_id": receipt.conversation_id,
            "message_id": receipt.user_message_id,
            "receipt_id": receipt.id,
            "user_message_id": receipt.user_message_id,
            "status": "PENDING",
        },
    )


def _receipt_invalid() -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"error": {"code": "CHAT_RECEIPT_INVALID", "message": "Stored chat reply is unavailable."}},
    )


def _terminal_failure(
    request: Request,
    store: ChatStore,
    receipt: ChatReceipt,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Persist a known, rejected provider response as a replayable terminal failure.

    Only for a response that was returned and then refused by this route. The body
    never carries the rejected model text.
    """
    error: dict[str, str] = {"code": code, "message": message}
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        error["request_id"] = request_id
    body = {
        "status": "FAILED",
        "receipt_id": receipt.id,
        "conversation_id": receipt.conversation_id,
        "user_message_id": receipt.user_message_id,
        "error": error,
    }
    try:
        store.fail_known(receipt, status_code=status_code, response=body)
    except ChatStoreError:
        # The failed state could not be recorded; the receipt stays unresolved and is
        # never resent, exactly like any other ambiguous outcome.
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "CHAT_RECEIPT_UNRESOLVED", "message": "The reply outcome could not be recorded; it will not be sent again."}},
        ) from None
    return JSONResponse(status_code=status_code, content=body)


@router.post("/messages")
async def post_message(
    body: ChatMessageRequest,
    request: Request,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    _require_enabled(settings)
    engine = request.app.state.engine
    session = verify_session_authority(engine, x_session_id, x_session_token)
    store = ChatStore(engine)
    key = body.idempotency_key
    canonical = json.dumps(
        {"prompt": body.prompt, "conversation_id": body.conversation_id},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request_hash = hashlib.sha256(canonical).hexdigest()
    try:
        receipt = store.create_or_get(
            session_id=session.id,
            idempotency_key=key,
            request_hash=request_hash,
            prompt=body.prompt,
            requested_conversation_id=body.conversation_id,
        )
    except ChatIdempotencyConflict as err:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "IDEMPOTENCY_CONFLICT", "message": str(err)}},
        ) from None
    except ChatConversationNotFound:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."}},
        ) from None
    except ChatConversationBusy:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "CONVERSATION_BUSY", "message": "Conversation has a pending message."}},
        ) from None

    if receipt.status == "COMPLETED":
        try:
            return JSONResponse(status_code=200, content=store.completed_body(receipt))
        except ChatReceiptInvalid:
            raise _receipt_invalid() from None
    if receipt.status == "FAILED":
        try:
            failed_status, failed_body = store.failed_response(receipt)
        except ChatReceiptInvalid:
            raise _receipt_invalid() from None
        return JSONResponse(status_code=failed_status, content=failed_body)
    if receipt.status != "PENDING":
        raise _receipt_invalid()
    if not receipt.is_new:
        return _pending_response(receipt)

    ordinary_budget = getattr(request.app.state, "ordinary_budget", None)
    provider = getattr(request.app.state, "agent_provider", None)
    if ordinary_budget is None:
        store.discard_undispatched(receipt)
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "ORDINARY_BUDGET_UNAVAILABLE", "message": "Ordinary usage budget is unavailable."}},
        )
    if provider is None:
        provider = AgentProvider(settings, ordinary_budget=ordinary_budget)
    if not isinstance(provider, AgentProvider) or not provider.is_available():
        store.discard_undispatched(receipt)
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "PROVIDER_DISABLED", "message": "Nemotron is unavailable."}},
        )

    server_history = store.history(receipt.conversation_id)
    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}, *server_history]
    try:
        result = await provider.general_chat(messages)
    except ProviderError as err:
        # Only a definite non-dispatch is forgotten; an ambiguous failure keeps
        # its pending receipt so a retry can never issue a second paid request.
        if not err.dispatched:
            store.discard_undispatched(receipt)
        raise HTTPException(
            status_code=err.status_code or 502,
            detail={"error": {"code": err.code, "message": err.message}},
        ) from None
    # The provider returned. From here every rejection is a known outcome of a settled
    # request, so it becomes a durable terminal failure instead of a permanent PENDING.
    if result.tool_calls:
        return _terminal_failure(
            request, store, receipt, status_code=502, code="CHAT_TOOL_CALL_REJECTED",
            message="General chat does not accept provider tool calls.",
        )
    if not isinstance(result.content, str) or not result.content.strip():
        return _terminal_failure(
            request, store, receipt, status_code=502, code="CHAT_REPLY_INVALID",
            message="Provider returned no conversational reply.",
        )
    reply = result.content.strip()
    if len(reply.encode("utf-8")) > MAX_CHAT_REPLY_BYTES:
        return _terminal_failure(
            request, store, receipt, status_code=502, code="CHAT_REPLY_TOO_LONG",
            message="Provider reply exceeded the chat response limit.",
        )
    raw_usage = result.usage
    if not isinstance(raw_usage, dict) or any(
        type(raw_usage.get(name)) is not int or raw_usage[name] < 0
        for name in ("prompt_tokens", "completion_tokens", "total_tokens")
    ) or raw_usage["total_tokens"] != raw_usage["prompt_tokens"] + raw_usage["completion_tokens"]:
        return _terminal_failure(
            request, store, receipt, status_code=502, code="PROVIDER_USAGE_INVALID",
            message="Provider usage was missing or invalid.",
        )
    usage = {
        name: raw_usage[name]
        for name in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    assistant_message_id = uuid4().hex
    response_body = {
        "conversation_id": receipt.conversation_id,
        "message_id": assistant_message_id,
        "status": "COMPLETED",
        "reply": reply,
        "disclaimer": CHAT_DISCLAIMER,
        "usage": usage,
    }
    # complete() adds the persisted identities, so the original response and every
    # replay carry the same body.
    stored_body = store.complete(receipt, response_body, reply, assistant_message_id)
    return JSONResponse(status_code=200, content=stored_body)


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    request: Request,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    _require_enabled(settings)
    session = verify_session_authority(request.app.state.engine, x_session_id, x_session_token)
    store = ChatStore(request.app.state.engine)
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."}},
        )
    if conversation["session_id"] != session.id:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "CROSS_SESSION_ACCESS_DENIED", "message": "Conversation belongs to another session."}},
        )
    return JSONResponse(
        status_code=200,
        content={
            "conversation_id": conversation_id,
            "messages": store.messages(conversation_id),
        },
    )
