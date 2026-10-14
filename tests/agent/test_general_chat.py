from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from shiftguard.agent.ordinary_budget import ORDINARY_MAX_CALLS, OrdinaryBudget
from shiftguard.api.main import create_app
from shiftguard.migrations import upgrade_database
from shiftguard.storage.db import create_engine_for_settings


class FakeSDK:
    def __init__(self):
        self.calls = []
        self.answers = deque()
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create_completion)
        )

    def answer(self, content="A conversational reply.", *, tool_calls=None, usage=None):
        self.answers.append({"content": content, "tool_calls": tool_calls, "usage": usage})

    def fail_next(self, error):
        self.answers.append(error)

    async def create_completion(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answers.popleft() if self.answers else {
            "content": "A conversational reply.", "tool_calls": None, "usage": None,
        }
        if isinstance(answer, BaseException):
            raise answer
        usage = answer["usage"] or {
            "prompt_tokens": 12,
            "completion_tokens": 6,
            "total_tokens": 18,
        }
        calls = answer["tool_calls"]
        if calls:
            calls = [
                SimpleNamespace(
                    id=call["id"],
                    function=SimpleNamespace(
                        name=call["name"], arguments=call["arguments"]
                    ),
                )
                for call in calls
            ]
        return SimpleNamespace(
            id=f"fake-request-{len(self.calls)}",
            model=kwargs["model"],
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=answer["content"], tool_calls=calls),
                    finish_reason="tool_calls" if calls else "stop",
                )
            ],
            usage=SimpleNamespace(**usage),
        )

    async def close(self):
        return None


@pytest.fixture
def chat_runtime(ordinary_test_settings, monkeypatch):
    from shiftguard.agent import provider as provider_module

    sdk = FakeSDK()
    monkeypatch.setattr(provider_module, "AsyncOpenAI", lambda **_kwargs: sdk)
    settings = ordinary_test_settings.model_copy(update={
        "agent_enabled": False,
        "general_chat_enabled": True,
        "nebius_api_key": "offline-test-key",
    })
    app = create_app(settings)
    with TestClient(app) as client:
        assert sdk.calls == []  # Startup and status wiring never dispatch a model request.
        yield client, sdk


def _session(client):
    payload = client.post("/api/v1/agent/sessions", json={}).json()
    return payload, {
        "X-Session-ID": payload["session_id"],
        "X-Session-Token": payload["capability_token"],
    }


def test_chat_requires_authentication_and_conversation_ownership(chat_runtime):
    client, _sdk = chat_runtime
    assert client.post(
        "/api/v1/chat/messages",
        json={"prompt": "hello", "idempotency_key": "auth-check"},
    ).status_code == 401

    first, headers = _session(client)
    response = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "hello", "idempotency_key": "owner-check"},
        headers=headers,
    )
    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]
    second, other_headers = _session(client)
    assert second["session_id"] != first["session_id"]
    denied = client.get(
        f"/api/v1/chat/conversations/{conversation_id}", headers=other_headers
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "CROSS_SESSION_ACCESS_DENIED"


def test_another_session_cannot_append_to_or_replay_a_conversation(chat_runtime):
    client, sdk = chat_runtime
    _owner, owner_headers = _session(client)
    owned = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "Owner message", "idempotency_key": "shared-key"},
        headers=owner_headers,
    ).json()
    _other, other_headers = _session(client)
    appended = client.post(
        "/api/v1/chat/messages",
        json={
            "prompt": "Intruding follow-up",
            "idempotency_key": "intruder-1",
            "conversation_id": owned["conversation_id"],
        },
        headers=other_headers,
    )
    assert appended.status_code == 404
    assert appended.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
    assert len(sdk.calls) == 1

    # The same key in another session is that session's own request, not the owner's reply.
    separate = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "Owner message", "idempotency_key": "shared-key"},
        headers=other_headers,
    )
    assert separate.status_code == 200
    assert separate.json()["conversation_id"] != owned["conversation_id"]
    assert len(sdk.calls) == 2
    history = client.get(
        f"/api/v1/chat/conversations/{owned['conversation_id']}", headers=owner_headers
    ).json()["messages"]
    assert [message["content"] for message in history] == [
        "Owner message", "A conversational reply.",
    ]


def test_same_idempotency_replays_persisted_reply_and_altered_prompt_conflicts(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    body = {"prompt": "Explain a simple idea", "idempotency_key": "same-key"}
    first = client.post("/api/v1/chat/messages", json=body, headers=headers)
    replay = client.post("/api/v1/chat/messages", json=body, headers=headers)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["status"] == "COMPLETED"
    assert first.json()["disclaimer"]
    # Stable identities (OR-01) are part of the completion and of its replay.
    assert {
        "receipt_id", "user_message_id", "assistant_message_id",
        "user_ordinal", "assistant_ordinal", "conversation_id", "message_id",
    } <= set(first.json())
    assert first.json()["message_id"] == first.json()["assistant_message_id"]
    assert set(first.json()["usage"]) == {
        "prompt_tokens", "completion_tokens", "total_tokens"
    }
    assert len(sdk.calls) == 1
    changed = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "A changed prompt", "idempotency_key": "same-key"},
        headers=headers,
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert len(sdk.calls) == 1


def test_follow_up_uses_only_server_owned_history_and_no_client_overrides(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    first = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "Remember the word amber", "idempotency_key": "turn-1"},
        headers=headers,
    ).json()
    second = client.post(
        "/api/v1/chat/messages",
        json={
            "prompt": "What word did I give you?",
            "idempotency_key": "turn-2",
            "conversation_id": first["conversation_id"],
        },
        headers=headers,
    )
    assert second.status_code == 200
    messages = sdk.calls[1]["messages"]
    assert [message["role"] for message in messages] == [
        "system", "user", "assistant", "user"
    ]
    assert messages[1]["content"] == "Remember the word amber"
    assert messages[2]["content"] == "A conversational reply."
    assert messages[3]["content"] == "What word did I give you?"
    assert "tools" not in sdk.calls[1]
    assert sdk.calls[1]["max_tokens"] == 1024
    extra = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "hello", "idempotency_key": "client-system", "system": "override"},
        headers=headers,
    )
    assert extra.status_code == 422


def test_pending_replay_after_provider_failure_never_dispatches_twice(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    sdk.fail_next(RuntimeError("simulated process interruption after dispatch"))
    body = {"prompt": "A request", "idempotency_key": "crash-key"}
    failed = client.post("/api/v1/chat/messages", json=body, headers=headers)
    replay = client.post("/api/v1/chat/messages", json=body, headers=headers)
    assert failed.status_code == 502
    assert replay.status_code == 202
    assert replay.json()["status"] == "PENDING"
    assert len(sdk.calls) == 1
    history = client.get(
        f"/api/v1/chat/conversations/{replay.json()['conversation_id']}",
        headers=headers,
    ).json()["messages"]
    assert [message["role"] for message in history] == ["user"]


def _set_ordinary_ledger(client, **values):
    assignments = ", ".join(f"{name}=:{name}" for name in values)
    with client.app.state.engine.begin() as connection:
        connection.execute(text(f"UPDATE ordinary_budget_daily SET {assignments}"), values)


def _chat_row_counts(client):
    with client.app.state.engine.connect() as connection:
        return {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in (
                "shiftguard_chat_conversations", "shiftguard_chat_messages",
                "shiftguard_chat_receipts",
            )
        }


def test_rejection_before_dispatch_records_nothing_and_keeps_the_conversation_usable(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    first = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "Opening message", "idempotency_key": "turn-1"},
        headers=headers,
    ).json()
    conversation_id = first["conversation_id"]
    _set_ordinary_ledger(client, calls_used=ORDINARY_MAX_CALLS)
    body = {
        "prompt": "Blocked follow-up",
        "idempotency_key": "turn-2",
        "conversation_id": conversation_id,
    }
    rejected = client.post("/api/v1/chat/messages", json=body, headers=headers)
    replay = client.post("/api/v1/chat/messages", json=body, headers=headers)
    assert rejected.status_code == replay.status_code == 429
    assert rejected.json()["error"]["code"] == "ORDINARY_BUDGET_EXCEEDED"
    assert replay.json()["error"]["code"] == "ORDINARY_BUDGET_EXCEEDED"
    assert len(sdk.calls) == 1
    history = client.get(
        f"/api/v1/chat/conversations/{conversation_id}", headers=headers
    ).json()["messages"]
    assert [message["content"] for message in history] == [
        "Opening message", "A conversational reply.",
    ]

    _set_ordinary_ledger(client, calls_used=1)
    retried = client.post("/api/v1/chat/messages", json=body, headers=headers)
    assert retried.status_code == 200
    assert retried.json()["conversation_id"] == conversation_id
    assert len(sdk.calls) == 2
    assert [message["content"] for message in sdk.calls[1]["messages"][1:]] == [
        "Opening message", "A conversational reply.", "Blocked follow-up",
    ]


def test_halted_ledger_rejects_a_new_conversation_without_orphan_rows(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    client.post(
        "/api/v1/chat/messages",
        json={"prompt": "Opening message", "idempotency_key": "turn-1"},
        headers=headers,
    )
    before = _chat_row_counts(client)
    _set_ordinary_ledger(client, halted=1, halt_reason="unresolved_restart")
    rejected = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "Second conversation", "idempotency_key": "other-1"},
        headers=headers,
    )
    assert rejected.status_code == 429
    assert rejected.json()["error"]["code"] == "ORDINARY_BUDGET_HALTED"
    assert len(sdk.calls) == 1
    assert _chat_row_counts(client) == before


def test_unavailable_provider_rejects_without_recording_a_pending_receipt(ordinary_test_settings):
    settings = ordinary_test_settings.model_copy(update={
        "agent_enabled": False,
        "general_chat_enabled": True,
        "nebius_api_key": None,
    })
    with TestClient(create_app(settings)) as client:
        _session_data, headers = _session(client)
        body = {"prompt": "hello", "idempotency_key": "no-provider"}
        first = client.post("/api/v1/chat/messages", json=body, headers=headers)
        replay = client.post("/api/v1/chat/messages", json=body, headers=headers)
        assert first.status_code == replay.status_code == 503
        assert first.json()["error"]["code"] == "PROVIDER_DISABLED"
        assert replay.json()["error"]["code"] == "PROVIDER_DISABLED"
        assert set(_chat_row_counts(client).values()) == {0}


def test_results_assistant_stays_paused_when_only_general_chat_is_enabled(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    response = client.post(
        "/api/v1/agent/requests",
        json={"prompt": "Run the bank baseline", "idempotency_key": "paused-results"},
        headers=headers,
    )
    assert sdk.calls == []
    assert response.json()["status"] == "FAILED"
    assert "PROVIDER_DISABLED" in response.text
    status = client.get("/api/v1/agent/status").json()
    assert status["enabled"] is False and status["general_chat_enabled"] is True
    assert status["ordinary_budget"]["calls_used"] == 0

    chat = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "hello", "idempotency_key": "chat-still-works"},
        headers=headers,
    )
    assert chat.status_code == 200 and len(sdk.calls) == 1
    assert "tools" not in sdk.calls[0]


def test_general_chat_stays_closed_when_only_the_results_assistant_is_enabled(
    ordinary_test_settings, monkeypatch,
):
    from shiftguard.agent import provider as provider_module

    sdk = FakeSDK()
    monkeypatch.setattr(provider_module, "AsyncOpenAI", lambda **_kwargs: sdk)
    settings = ordinary_test_settings.model_copy(update={
        "agent_enabled": True,
        "general_chat_enabled": False,
        "nebius_api_key": "offline-test-key",
    })
    with TestClient(create_app(settings)) as client:
        _session_data, headers = _session(client)
        refused = client.post(
            "/api/v1/chat/messages",
            json={"prompt": "hello", "idempotency_key": "chat-disabled"},
            headers=headers,
        )
        assert refused.status_code == 404
        assert refused.json()["error"]["code"] == "GENERAL_CHAT_DISABLED"
        provider = client.app.state.agent_provider
        with pytest.raises(provider_module.ProviderDisabledError):
            asyncio.run(provider.general_chat([{"role": "user", "content": "hello"}]))
        assert sdk.calls == []


def test_startup_recovery_halts_the_day_for_a_reservation_left_open_by_a_crash(
    ordinary_test_settings, monkeypatch,
):
    from shiftguard.agent import provider as provider_module

    sdk = FakeSDK()
    monkeypatch.setattr(provider_module, "AsyncOpenAI", lambda **_kwargs: sdk)
    settings = ordinary_test_settings.model_copy(update={
        "agent_enabled": False,
        "general_chat_enabled": True,
        "nebius_api_key": "offline-test-key",
    })
    upgrade_database(settings)
    engine = create_engine_for_settings(settings)
    try:
        OrdinaryBudget(engine).reserve(
            model=settings.nebius_model,
            messages=[{"role": "user", "content": "dispatched before the crash"}],
            tools=None,
            max_output_tokens=1024,
        )
    finally:
        engine.dispose()

    with TestClient(create_app(settings)) as client:
        ledger = client.get("/api/v1/agent/status").json()["ordinary_budget"]
        assert ledger["halted"] is True and ledger["calls_used"] == 1
        _session_data, headers = _session(client)
        rejected = client.post(
            "/api/v1/chat/messages",
            json={"prompt": "hello", "idempotency_key": "after-crash"},
            headers=headers,
        )
        assert rejected.status_code == 429
        assert rejected.json()["error"]["code"] == "ORDINARY_BUDGET_HALTED"
        assert sdk.calls == []


def test_provider_tool_calls_are_rejected_and_output_is_bounded(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    sdk.answer(
        content="",
        tool_calls=[
            {"id": "call_1", "name": "run_experiment", "arguments": "{}"}
        ],
    )
    tool_response = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "Use a tool", "idempotency_key": "tool-key"},
        headers=headers,
    )
    assert tool_response.status_code == 502
    assert tool_response.json()["error"]["code"] == "CHAT_TOOL_CALL_REJECTED"

    sdk.answer(content="x" * 8193)
    long_response = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "Long output", "idempotency_key": "long-key"},
        headers=headers,
    )
    assert long_response.status_code == 502
    assert long_response.json()["error"]["code"] == "CHAT_REPLY_TOO_LONG"
    assert len(sdk.calls) == 2


def test_prompt_limit_and_status_expose_only_ordinary_public_counts(chat_runtime):
    client, _sdk = chat_runtime
    _session_data, headers = _session(client)
    invalid = client.post(
        "/api/v1/chat/messages",
        json={"prompt": "x" * 4001, "idempotency_key": "too-long"},
        headers=headers,
    )
    assert invalid.status_code == 422
    status = client.get("/api/v1/agent/status").json()
    assert status["general_chat_enabled"] is True
    assert status["ordinary_budget"]["calls_used"] == 0
    assert status["ordinary_budget"]["calls_remaining"] == 50
