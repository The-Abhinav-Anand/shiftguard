"""Regression tests for review findings OR-01 (stable identity) and OR-03 (terminal rejection)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from shiftguard.agent.chat import (
    ChatConversationBusy,
    ChatReceipt,
    ChatStore,
    ChatStoreError,
)
from shiftguard.agent.provider import AgentProvider, ProviderResponse
from shiftguard.api.main import create_app
from shiftguard.migrations import upgrade_database
from shiftguard.storage.db import create_engine_for_settings

from test_general_chat import FakeSDK, _session, chat_runtime  # noqa: F401  (fixture re-export)


COMPLETION_IDENTITY_FIELDS = (
    "receipt_id",
    "user_message_id",
    "assistant_message_id",
    "user_ordinal",
    "assistant_ordinal",
    "conversation_id",
)


class GatedSDK(FakeSDK):
    """FakeSDK whose dispatch parks until released, so a request stays in flight."""

    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.delay_seconds = 0.0

    async def create_completion(self, **kwargs):
        self.entered.set()
        waited = 0.0
        while not self.release.is_set() and waited < 20.0:
            await asyncio.sleep(0.01)
            waited += 0.01
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return await super().create_completion(**kwargs)


def _chat_settings(ordinary_test_settings):
    return ordinary_test_settings.model_copy(update={
        "agent_enabled": False,
        "general_chat_enabled": True,
        "nebius_api_key": "offline-test-key",
    })


@pytest.fixture
def chat_env(ordinary_test_settings, monkeypatch):
    """Settings plus a patched SDK; each test opens (and fully closes) its own app."""
    from shiftguard.agent import provider as provider_module

    sdk = FakeSDK()
    monkeypatch.setattr(provider_module, "AsyncOpenAI", lambda **_kwargs: sdk)
    return _chat_settings(ordinary_test_settings), sdk


@contextmanager
def open_client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def _post(client, headers, prompt, key, conversation_id=None):
    body = {"prompt": prompt, "idempotency_key": key}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    return client.post("/api/v1/chat/messages", json=body, headers=headers)


def _counts(client):
    with client.app.state.engine.connect() as connection:
        return {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in (
                "shiftguard_chat_conversations",
                "shiftguard_chat_messages",
                "shiftguard_chat_receipts",
            )
        }


def _receipt_row(client, key):
    with client.app.state.engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT id, status, response_json, assistant_message_id, conversation_id "
                "FROM shiftguard_chat_receipts WHERE idempotency_key = :key"
            ),
            {"key": key},
        ).mappings().first()


def _pending_claim(client, conversation_id):
    with client.app.state.engine.connect() as connection:
        return connection.execute(
            text("SELECT pending_receipt_id FROM shiftguard_chat_conversations WHERE id = :id"),
            {"id": conversation_id},
        ).scalar_one()


def _thread_post(client, headers, prompt, key, conversation_id, results, name, gate=None):
    if gate is not None:
        gate.wait(timeout=20)
    try:
        results[name] = _post(client, headers, prompt, key, conversation_id)
    except BaseException as error:  # pragma: no cover - surfaced by the assertions
        results[name] = error


# ---------------------------------------------------------------- OR-03 terminal rejection


def test_known_rejected_reply_is_terminal_and_replayable(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    sdk.answer(content="x" * 8193)
    first = _post(client, headers, "hello", "review-terminal")
    replay = _post(client, headers, "hello", "review-terminal")

    assert first.status_code == 502
    assert first.json()["error"]["code"] == "CHAT_REPLY_TOO_LONG"
    assert first.json()["status"] == "FAILED"
    assert replay.status_code == 502
    assert replay.json() == first.json()
    assert len(sdk.calls) == 1
    body = first.json()
    for name in ("receipt_id", "conversation_id", "user_message_id"):
        assert isinstance(body[name], str) and body[name]
    assert "x" * 64 not in first.text
    assert "reply" not in body

    # A different key can continue the same conversation; the rejected turn leaves no assistant row.
    follow_up = _post(client, headers, "next", "review-next", body["conversation_id"])
    assert follow_up.status_code == 200
    assert follow_up.json()["conversation_id"] == body["conversation_id"]
    assert len(sdk.calls) == 2
    assert [m["role"] for m in sdk.calls[1]["messages"][1:]] == ["user", "user"]
    history = client.get(
        f"/api/v1/chat/conversations/{body['conversation_id']}", headers=headers
    ).json()["messages"]
    assert [m["role"] for m in history] == ["user", "user", "assistant"]
    assert history[0]["id"] == body["user_message_id"]
    assert client.app.state.ordinary_budget.public_snapshot()["halted"] is False

    row = _receipt_row(client, "review-terminal")
    assert row["status"] == "FAILED" and row["assistant_message_id"] is None
    stored = json.loads(row["response_json"])
    assert stored["http_status"] == 502 and stored["body"] == body
    assert _pending_claim(client, body["conversation_id"]) is None


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ({"content": "", "tool_calls": None}, "CHAT_REPLY_INVALID"),
        ({"content": "   \n", "tool_calls": None}, "CHAT_REPLY_INVALID"),
        (
            {"content": "", "tool_calls": [{"id": "call_1", "name": "run_experiment", "arguments": "{}"}]},
            "CHAT_TOOL_CALL_REJECTED",
        ),
    ],
    ids=["empty", "blank", "tool-call"],
)
def test_every_known_rejection_after_the_provider_returned_is_terminal(chat_runtime, answer, code):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    sdk.answer(**answer)
    first = _post(client, headers, "hello", "known-rejection")
    replay = _post(client, headers, "hello", "known-rejection")
    assert first.status_code == replay.status_code == 502
    assert first.json()["error"]["code"] == code
    assert first.json()["status"] == "FAILED"
    assert replay.json() == first.json()
    assert len(sdk.calls) == 1
    assert _pending_claim(client, first.json()["conversation_id"]) is None
    assert _post(
        client, headers, "again", "known-rejection-2", first.json()["conversation_id"]
    ).status_code == 200


def test_invalid_usage_shape_reported_by_the_route_is_terminal(chat_runtime, monkeypatch):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    dispatches = []

    async def bad_usage(self, messages):
        dispatches.append(messages)
        return ProviderResponse(
            content="A usable reply.",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 5},
        )

    monkeypatch.setattr(AgentProvider, "general_chat", bad_usage)
    first = _post(client, headers, "hello", "bad-usage")
    replay = _post(client, headers, "hello", "bad-usage")
    assert first.status_code == replay.status_code == 502
    assert first.json()["error"]["code"] == "PROVIDER_USAGE_INVALID"
    assert first.json()["status"] == "FAILED"
    assert replay.json() == first.json()
    assert len(dispatches) == 1
    assert "A usable reply." not in first.text
    assert _receipt_row(client, "bad-usage")["status"] == "FAILED"


def test_ambiguous_provider_failure_stays_pending_and_never_resends(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    sdk.fail_next(RuntimeError("simulated timeout after dispatch"))
    failed = _post(client, headers, "hello", "ambiguous")
    replay = _post(client, headers, "hello", "ambiguous")
    assert failed.status_code == 502
    assert replay.status_code == 202 and replay.json()["status"] == "PENDING"
    assert _receipt_row(client, "ambiguous")["status"] == "PENDING"
    assert len(sdk.calls) == 1
    busy = _post(client, headers, "other", "ambiguous-2", replay.json()["conversation_id"])
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "CONVERSATION_BUSY"


def test_crash_between_validation_and_failed_receipt_commit_stays_unresolved(
    chat_runtime, monkeypatch,
):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    sdk.answer(content="y" * 9000)

    def crash(self, receipt, *, status_code, response):
        raise RuntimeError("simulated process death before the failed-receipt commit")

    with monkeypatch.context() as patch:
        patch.setattr(ChatStore, "fail_known", crash)
        with pytest.raises(RuntimeError, match="simulated process death"):
            _post(client, headers, "hello", "crash-key")

    row = _receipt_row(client, "crash-key")
    assert row["status"] == "PENDING" and row["response_json"] is None
    replay = _post(client, headers, "hello", "crash-key")
    assert replay.status_code == 202 and replay.json()["status"] == "PENDING"
    assert len(sdk.calls) == 1
    conversation_id = replay.json()["conversation_id"]
    assert _post(client, headers, "more", "crash-key-2", conversation_id).status_code == 409
    assert _pending_claim(client, conversation_id) == row["id"]
    assert len(sdk.calls) == 1
    assert client.app.state.ordinary_budget.public_snapshot()["halted"] is False


def test_same_key_with_different_content_conflicts_for_completed_and_failed(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    assert _post(client, headers, "completed prompt", "key-completed").status_code == 200
    sdk.answer(content="z" * 9000)
    assert _post(client, headers, "failed prompt", "key-failed").status_code == 502
    calls = len(sdk.calls)
    for key, prompt in (("key-completed", "changed"), ("key-failed", "changed")):
        conflict = _post(client, headers, prompt, key)
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    first = _receipt_row(client, "key-failed")
    conflict = _post(client, headers, "failed prompt", "key-failed", first["conversation_id"])
    assert conflict.status_code == 409  # a different conversation target is a different request
    assert len(sdk.calls) == calls


def test_other_session_cannot_read_append_or_replay_a_failed_conversation(chat_runtime):
    client, sdk = chat_runtime
    _owner, owner_headers = _session(client)
    sdk.answer(content="x" * 9000)
    failed = _post(client, owner_headers, "private", "owner-key")
    conversation_id = failed.json()["conversation_id"]
    _other, other_headers = _session(client)

    denied = client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=other_headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "CROSS_SESSION_ACCESS_DENIED"
    appended = _post(client, other_headers, "intrude", "other-1", conversation_id)
    assert appended.status_code == 404
    assert appended.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
    assert len(sdk.calls) == 1

    separate = _post(client, other_headers, "private", "owner-key")
    assert separate.status_code == 200
    assert separate.json()["conversation_id"] != conversation_id
    assert separate.json()["receipt_id"] != failed.json()["receipt_id"]
    assert len(sdk.calls) == 2


# ---------------------------------------------------------------- reopening the application


def test_completed_and_failed_replay_survive_closing_and_reopening_the_app(chat_env):
    settings, sdk = chat_env
    with open_client(settings) as first_app:
        _session_data, headers = _session(first_app)
        completed = _post(first_app, headers, "alpha", "reopen-completed")
        sdk.answer(content="q" * 9000)
        failed = _post(first_app, headers, "beta", "reopen-failed")
        assert completed.status_code == 200 and failed.status_code == 502
    assert len(sdk.calls) == 2

    with open_client(settings) as second_app:
        replay_completed = _post(second_app, headers, "alpha", "reopen-completed")
        replay_failed = _post(second_app, headers, "beta", "reopen-failed")
        assert replay_completed.status_code == 200
        assert replay_completed.json() == completed.json()
        assert replay_failed.status_code == 502
        assert replay_failed.json() == failed.json()
        assert len(sdk.calls) == 2
        history = second_app.get(
            f"/api/v1/chat/conversations/{failed.json()['conversation_id']}", headers=headers
        ).json()["messages"]
        assert [(m["id"], m["role"]) for m in history] == [
            (failed.json()["user_message_id"], "user")
        ]
        resumed = _post(
            second_app, headers, "continue", "reopen-next", failed.json()["conversation_id"]
        )
        assert resumed.status_code == 200 and len(sdk.calls) == 3


# ---------------------------------------------------------------- concurrency


def test_same_key_race_has_one_dispatch_one_receipt_and_no_stuck_loser(chat_env):
    settings, _sdk = chat_env
    from shiftguard.agent import provider as provider_module

    gated = GatedSDK()
    gated.release.set()
    gated.delay_seconds = 0.25
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(provider_module, "AsyncOpenAI", lambda **_kwargs: gated)
        with open_client(settings) as client:
            _session_data, headers = _session(client)
            barrier = threading.Barrier(2, timeout=20)
            results = {}

            def worker(name):
                barrier.wait()
                try:
                    results[name] = _post(client, headers, "race", "race-key")
                except BaseException as error:  # pragma: no cover
                    results[name] = error

            threads = [threading.Thread(target=worker, args=(name,)) for name in ("a", "b")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            assert all(not isinstance(r, BaseException) for r in results.values()), results
            statuses = sorted(r.status_code for r in results.values())
            assert set(statuses) <= {200, 202} and 200 in statuses, statuses
            assert len(gated.calls) == 1
            assert _counts(client)["shiftguard_chat_receipts"] == 1
            assert client.app.state.ordinary_budget.public_snapshot()["calls_used"] == 1
            winner = next(r for r in results.values() if r.status_code == 200)
            replay = _post(client, headers, "race", "race-key")
            assert replay.status_code == 200 and replay.json() == winner.json()
            assert len(gated.calls) == 1


def test_same_key_request_while_the_first_is_in_flight_is_pending_not_busy(chat_env):
    settings, _sdk = chat_env
    from shiftguard.agent import provider as provider_module

    gated = GatedSDK()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(provider_module, "AsyncOpenAI", lambda **_kwargs: gated)
        with open_client(settings) as client:
            _session_data, headers = _session(client)
            results = {}
            first = threading.Thread(
                target=_thread_post,
                args=(client, headers, "inflight", "inflight-key", None, results, "first"),
            )
            first.start()
            assert gated.entered.wait(timeout=20)
            second = _post(client, headers, "inflight", "inflight-key")
            assert second.status_code == 202 and second.json()["status"] == "PENDING"
            gated.release.set()
            first.join(timeout=30)
            assert results["first"].status_code == 200
            replay = _post(client, headers, "inflight", "inflight-key")
            assert replay.status_code == 200 and replay.json() == results["first"].json()
            assert len(gated.calls) == 1
            assert _counts(client)["shiftguard_chat_receipts"] == 1


def test_different_keys_cannot_hold_one_conversation_and_unrelated_receipts_cannot_unlock_it(
    chat_env,
):
    settings, _sdk = chat_env
    from shiftguard.agent import provider as provider_module

    gated = GatedSDK()
    gated.release.set()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(provider_module, "AsyncOpenAI", lambda **_kwargs: gated)
        with open_client(settings) as client:
            _session_data, headers = _session(client)
            opening = _post(client, headers, "opening", "different-0")
            conversation_id = opening.json()["conversation_id"]
            store = ChatStore(client.app.state.engine)
            unrelated = _new_receipt(
                store, "different-unrelated", session_id=_session_data["session_id"]
            )
            gated.release.clear()
            gated.entered.clear()

            results = {}
            holder = threading.Thread(
                target=_thread_post,
                args=(client, headers, "holder", "different-1", conversation_id, results, "holder"),
            )
            holder.start()
            assert gated.entered.wait(timeout=20)
            rival = _post(client, headers, "rival", "different-2", conversation_id)
            assert rival.status_code == 409
            assert rival.json()["error"]["code"] == "CONVERSATION_BUSY"
            holder_receipt = _receipt_row(client, "different-1")
            assert _pending_claim(client, conversation_id) == holder_receipt["id"]
            assert _receipt_row(client, "different-2") is None

            # An unrelated receipt, even one forged onto this conversation, cannot clear the claim.
            forged = ChatReceipt(
                id=unrelated.id,
                conversation_id=conversation_id,
                user_message_id=unrelated.user_message_id,
                status="PENDING",
                response_json=None,
                is_new=False,
            )
            with pytest.raises(ChatStoreError):
                store.fail_known(forged, status_code=502, response={"status": "FAILED"})
            assert _pending_claim(client, conversation_id) == holder_receipt["id"]
            assert _receipt_row(client, "different-unrelated")["status"] == "PENDING"
            assert _pending_claim(client, unrelated.conversation_id) == unrelated.id

            gated.release.set()
            holder.join(timeout=30)
            assert results["holder"].status_code == 200
            assert _pending_claim(client, conversation_id) is None
            assert _post(client, headers, "rival", "different-2", conversation_id).status_code == 200
            assert len(gated.calls) == 3  # opening, holder, rival


# ---------------------------------------------------------------- ChatStore.fail_known


@pytest.fixture
def store_env(ordinary_test_settings):
    settings = _chat_settings(ordinary_test_settings)
    upgrade_database(settings)
    engine = create_engine_for_settings(settings)
    try:
        yield ChatStore(engine), engine
    finally:
        engine.dispose()


def _new_receipt(store, key, *, conversation_id=None, prompt="hello", session_id="store-session"):
    return store.create_or_get(
        session_id=session_id,
        idempotency_key=key,
        request_hash=hashlib.sha256(f"{key}:{prompt}".encode()).hexdigest(),
        prompt=prompt,
        requested_conversation_id=conversation_id,
    )


def test_fail_known_is_one_transaction_and_only_releases_its_own_claim(store_env):
    store, engine = store_env
    first = _new_receipt(store, "first")
    other = _new_receipt(store, "other")
    envelope = {"status": "FAILED", "receipt_id": first.id, "error": {"code": "X", "message": "m"}}

    store.fail_known(first, status_code=502, response=envelope)
    assert store.get_conversation(first.conversation_id)["pending_receipt_id"] is None
    assert store.get_conversation(other.conversation_id)["pending_receipt_id"] == other.id
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, response_json, completed_at_utc FROM shiftguard_chat_receipts WHERE id = :id"),
            {"id": first.id},
        ).mappings().one()
    assert row["status"] == "FAILED" and row["completed_at_utc"]
    assert json.loads(row["response_json"]) == {"http_status": 502, "body": envelope}

    replayed = store.create_or_get(
        session_id="store-session",
        idempotency_key="first",
        request_hash=hashlib.sha256(b"first:hello").hexdigest(),
        prompt="hello",
        requested_conversation_id=None,
    )
    assert replayed.status == "FAILED" and not replayed.is_new
    assert store.failed_response(replayed) == (502, envelope)

    # Terminal receipts cannot be failed twice or completed afterwards.
    with pytest.raises(ChatStoreError):
        store.fail_known(first, status_code=502, response=envelope)
    with pytest.raises(ChatStoreError):
        store.complete(first, {"status": "COMPLETED"}, "late", "a" * 32)


def test_fail_known_rolls_back_when_the_conversation_claim_belongs_to_another_receipt(store_env):
    store, engine = store_env
    holder = _new_receipt(store, "holder")
    other = _new_receipt(store, "other")
    forged = ChatReceipt(
        id=other.id,
        conversation_id=holder.conversation_id,
        user_message_id=other.user_message_id,
        status="PENDING",
        response_json=None,
        is_new=False,
    )
    with pytest.raises(ChatStoreError):
        store.fail_known(forged, status_code=502, response={"status": "FAILED"})
    assert store.get_conversation(holder.conversation_id)["pending_receipt_id"] == holder.id
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, response_json, completed_at_utc FROM shiftguard_chat_receipts WHERE id = :id"),
            {"id": other.id},
        ).mappings().one()
    assert (row["status"], row["response_json"], row["completed_at_utc"]) == ("PENDING", None, None)


def test_fail_known_rejects_non_error_codes_and_unserialisable_bodies(store_env):
    store, _engine = store_env
    receipt = _new_receipt(store, "bad-input")
    with pytest.raises(ValueError):
        store.fail_known(receipt, status_code=200, response={"status": "FAILED"})
    with pytest.raises(ValueError):
        store.fail_known(receipt, status_code=502, response={"bad": float("nan")})
    assert store.get_conversation(receipt.conversation_id)["pending_receipt_id"] == receipt.id


def test_same_key_threads_through_the_store_yield_one_new_receipt(store_env):
    store, _engine = store_env
    opening = _new_receipt(store, "opening")
    store.complete(opening, {"status": "COMPLETED"}, "ok", "b" * 32)
    barrier = threading.Barrier(4, timeout=20)
    outcomes = []
    guard = threading.Lock()

    def worker():
        barrier.wait()
        try:
            receipt = store.create_or_get(
                session_id="store-session",
                idempotency_key="shared",
                request_hash="c" * 64,
                prompt="shared prompt",
                requested_conversation_id=opening.conversation_id,
            )
            result = (receipt.id, receipt.is_new)
        except ChatConversationBusy as error:  # the loser must resolve to the winner's receipt
            result = error
        with guard:
            outcomes.append(result)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(outcomes) == 4 and not any(isinstance(o, BaseException) for o in outcomes), outcomes
    assert len({receipt_id for receipt_id, _new in outcomes}) == 1
    assert sum(1 for _id, is_new in outcomes if is_new) == 1


# ---------------------------------------------------------------- OR-01 identity


def test_completion_history_and_provider_history_identities(chat_runtime):
    client, sdk = chat_runtime
    session_data, headers = _session(client)
    first = _post(client, headers, "Remember amber", "id-turn-1")
    conversation_id = first.json()["conversation_id"]
    second = _post(client, headers, "What word?", "id-turn-2", conversation_id)
    replay = _post(client, headers, "What word?", "id-turn-2", conversation_id)
    assert first.status_code == second.status_code == replay.status_code == 200
    assert replay.json() == second.json()

    for response, ordinals in ((first, (1, 2)), (second, (3, 4))):
        body = response.json()
        assert set(COMPLETION_IDENTITY_FIELDS) <= set(body)
        assert body["message_id"] == body["assistant_message_id"]
        assert (body["user_ordinal"], body["assistant_ordinal"]) == ordinals
        assert body["conversation_id"] == conversation_id
        assert body["status"] == "COMPLETED"

    history = client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=headers).json()
    assert history["conversation_id"] == conversation_id
    assert [set(m) for m in history["messages"]] == [{"id", "ordinal", "role", "content"}] * 4
    assert [m["ordinal"] for m in history["messages"]] == [1, 2, 3, 4]
    assert [m["role"] for m in history["messages"]] == ["user", "assistant", "user", "assistant"]
    assert [m["id"] for m in history["messages"]] == [
        first.json()["user_message_id"],
        first.json()["assistant_message_id"],
        second.json()["user_message_id"],
        second.json()["assistant_message_id"],
    ]
    assert len({m["id"] for m in history["messages"]}) == 4

    # Provider-bound history is role/content only and carries no identity or credential data.
    dispatched = sdk.calls[1]["messages"]
    assert all(set(message) == {"role", "content"} for message in dispatched)
    serialised = json.dumps(sdk.calls, default=str)
    forbidden = [
        session_data["session_id"], session_data["capability_token"],
        *(m["id"] for m in history["messages"]),
        first.json()["receipt_id"], second.json()["receipt_id"],
    ]
    assert not [value for value in forbidden if value in serialised]
    assert "receipt" not in serialised.lower()


def test_store_history_stays_role_and_content_only(store_env):
    store, _engine = store_env
    receipt = _new_receipt(store, "history-shape")
    assert store.history(receipt.conversation_id) == [{"role": "user", "content": "hello"}]
    [message] = store.messages(receipt.conversation_id)
    assert set(message) == {"id", "ordinal", "role", "content"}
    assert message["id"] == receipt.user_message_id and message["ordinal"] == 1


def _insert_legacy_completed_receipt(client, session_id, *, key, prompt, reply, with_assistant=True):
    ids = {name: name[:1] * 31 + str(index) for index, name in enumerate(("conv", "user", "asst", "receipt"))}
    ids["conv"] = "legacy-conversation-0001"
    response = {
        "conversation_id": ids["conv"],
        "message_id": ids["asst"],
        "status": "COMPLETED",
        "reply": reply,
        "disclaimer": "Legacy disclaimer.",
        "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
    }
    request_hash = hashlib.sha256(
        json.dumps(
            {"prompt": prompt, "conversation_id": None},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    stamp = "2026-10-01T00:00:00+00:00"
    with client.app.state.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO shiftguard_chat_conversations (id, session_id, pending_receipt_id, created_at_utc, updated_at_utc) VALUES (:id, :s, NULL, :t, :t)"),
            {"id": ids["conv"], "s": session_id, "t": stamp},
        )
        connection.execute(
            text("INSERT INTO shiftguard_chat_messages (id, conversation_id, ordinal, role, content, created_at_utc) VALUES (:id, :c, 1, 'user', :content, :t)"),
            {"id": ids["user"], "c": ids["conv"], "content": prompt, "t": stamp},
        )
        if with_assistant:
            connection.execute(
                text("INSERT INTO shiftguard_chat_messages (id, conversation_id, ordinal, role, content, created_at_utc) VALUES (:id, :c, 2, 'assistant', :content, :t)"),
                {"id": ids["asst"], "c": ids["conv"], "content": reply, "t": stamp},
            )
        connection.execute(
            text("INSERT INTO shiftguard_chat_receipts (id, session_id, idempotency_key, request_hash, conversation_id, user_message_id, assistant_message_id, status, response_json, created_at_utc, completed_at_utc) VALUES (:id, :s, :k, :h, :c, :u, :a, 'COMPLETED', :r, :t, :t)"),
            {
                "id": ids["receipt"], "s": session_id, "k": key, "h": request_hash,
                "c": ids["conv"], "u": ids["user"],
                "a": ids["asst"] if with_assistant else None,
                "r": json.dumps(response, ensure_ascii=False, separators=(",", ":")), "t": stamp,
            },
        )
    return ids, response


def test_legacy_completed_receipt_is_served_through_a_deterministic_read_adapter(chat_runtime):
    client, sdk = chat_runtime
    session_data, headers = _session(client)
    reply = "Legacy reply with unicode — café and trailing text."
    ids, legacy = _insert_legacy_completed_receipt(
        client, session_data["session_id"], key="legacy-key", prompt="Old question", reply=reply,
    )
    stored_before = _receipt_row(client, "legacy-key")["response_json"]
    messages_before = ChatStore(client.app.state.engine).messages(ids["conv"])

    first = _post(client, headers, "Old question", "legacy-key")
    second = _post(client, headers, "Old question", "legacy-key")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["reply"] == reply
    assert body["receipt_id"] == ids["receipt"]
    assert body["user_message_id"] == ids["user"]
    assert body["assistant_message_id"] == ids["asst"] == body["message_id"]
    assert (body["user_ordinal"], body["assistant_ordinal"]) == (1, 2)
    assert body["conversation_id"] == ids["conv"]
    for name, value in legacy.items():
        assert body[name] == value  # original stored fields are untouched
    assert sdk.calls == []
    assert _receipt_row(client, "legacy-key")["response_json"] == stored_before
    assert ChatStore(client.app.state.engine).messages(ids["conv"]) == messages_before
    assert _counts(client) == {
        "shiftguard_chat_conversations": 1,
        "shiftguard_chat_messages": 2,
        "shiftguard_chat_receipts": 1,
    }
    history = client.get(f"/api/v1/chat/conversations/{ids['conv']}", headers=headers).json()
    assert [m["id"] for m in history["messages"]] == [ids["user"], ids["asst"]]


def test_legacy_receipt_with_missing_message_rows_fails_closed_without_fabrication(chat_runtime):
    client, sdk = chat_runtime
    session_data, headers = _session(client)
    _insert_legacy_completed_receipt(
        client, session_data["session_id"], key="broken-legacy", prompt="Old question",
        reply="Stored reply", with_assistant=False,
    )
    before = _counts(client)
    stored_before = _receipt_row(client, "broken-legacy")["response_json"]
    response = _post(client, headers, "Old question", "broken-legacy")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "CHAT_RECEIPT_INVALID"
    assert sdk.calls == []
    assert _counts(client) == before
    assert _receipt_row(client, "broken-legacy")["response_json"] == stored_before


# ---------------------------------------------------------------- OR-09 boundary (integrator owns the handler)


@pytest.mark.parametrize(
    ("prompt", "key"),
    [("   ", "whitespace-prompt"), ("\n\t ", "whitespace-prompt-2"), ("hello", "   "), ("hello", "\t\n")],
    ids=["blank-prompt", "newline-prompt", "blank-key", "tab-key"],
)
def test_whitespace_validation_returns_422_without_dispatch(chat_runtime, prompt, key):
    client, sdk = chat_runtime
    session_data, headers = _session(client)
    before = _counts(client)
    response = client.post(
        "/api/v1/chat/messages", json={"prompt": prompt, "idempotency_key": key}, headers=headers,
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["request_id"]
    assert session_data["capability_token"] not in response.text
    assert sdk.calls == []
    assert _counts(client) == before
