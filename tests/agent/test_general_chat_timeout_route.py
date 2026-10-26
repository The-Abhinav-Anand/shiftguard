"""Route contract: a general-chat provider timeout keeps the day open and the receipt pending."""

from __future__ import annotations

import httpx
import openai

from test_chat_review_regressions import _post, _receipt_row  # noqa: F401
from test_general_chat import FakeSDK, _session, chat_runtime  # noqa: F401  (fixture re-export)

TIMEOUT_MESSAGE = (
    "The model did not answer in time. This message stays unresolved and will not be sent "
    "again; start a new conversation to continue."
)


def test_general_chat_timeout_stays_pending_without_halting_the_day(chat_runtime):
    client, sdk = chat_runtime
    _session_data, headers = _session(client)
    sdk.fail_next(openai.APITimeoutError(request=httpx.Request("POST", "https://offline.invalid/v1")))

    timed_out = _post(client, headers, "hello", "timeout-key")
    assert timed_out.status_code == 504
    error = timed_out.json()["error"]
    assert error["code"] == "PROVIDER_TIMEOUT"
    assert error["message"] == TIMEOUT_MESSAGE

    snapshot = client.app.state.ordinary_budget.public_snapshot()
    assert snapshot["halted"] is False
    assert snapshot["calls_used"] == 1
    assert _receipt_row(client, "timeout-key")["status"] == "PENDING"

    replay = _post(client, headers, "hello", "timeout-key")
    assert replay.status_code == 202 and replay.json()["status"] == "PENDING"
    assert len(sdk.calls) == 1

    # A new conversation dispatches normally because the day is still open.
    fresh = _post(client, headers, "hello again", "fresh-key")
    assert fresh.status_code == 200
    assert len(sdk.calls) == 2
