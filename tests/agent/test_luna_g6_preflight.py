"""Fake-transport preflight cases; these never connect to a provider endpoint."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
import httpx
import openai

from scripts import preflight_nebius


MODEL = preflight_nebius.EXPECTED_MODEL


def _choice(content=None, tool_calls=None):
    return SimpleNamespace(
        id="offline-request-id",
        model=MODEL,
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, tool_calls=tool_calls),
            finish_reason="tool_calls" if tool_calls else "stop",
        )],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4, total_tokens=16),
    )


def _call(arguments='{"dataset_id":"bank"}', call_id="original-call-7", name="inspect_dataset"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
        model_dump=lambda: {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        },
    )


def _client_factory(responses, captured: dict):
    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            captured["calls"] = []
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
            self.responses = list(responses)
            captured["client"] = self

        async def create(self, **kwargs):
            captured["calls"].append(kwargs)
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        async def close(self):
            captured["closed"] = True

    return FakeClient


def _responses(*, ping="PONG", tool_arguments='{"dataset_id":"bank"}', model=MODEL, plan=None, usage=True):
    first = _choice(content=ping)
    second = _choice(tool_calls=[_call(arguments=tool_arguments)])
    if plan is None:
        plan = json.dumps({"template": "summary", "condition_refs": []})
    third = _choice(content=plan)
    first.model = model
    if not usage:
        first.usage = None
    return [first, second, third]


def _configure(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "offline-dummy-key-only")
    monkeypatch.setenv("NEBIUS_MODEL", MODEL)
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://offline.invalid/v1")


def _run(monkeypatch, tmp_path, responses, *, calls=3, tokens=10000, model=MODEL):
    _configure(monkeypatch)
    captured: dict = {}
    path = tmp_path / "preflight.json"
    result = asyncio.run(preflight_nebius.run_preflight(
        live=True,
        max_calls=calls,
        max_tokens=tokens,
        evidence_path=str(path),
        requested_model=model,
        client_factory=_client_factory(responses, captured),
        test_kind=preflight_nebius.OFFLINE_FAKE_TEST_KIND,
    ))
    report = json.loads(path.read_text(encoding="utf-8"))
    return result, report, captured


def test_luna_g6_preflight_p03_positive(monkeypatch, tmp_path):
    result, report, captured = _run(monkeypatch, tmp_path, _responses())
    assert result == 0
    assert report["status"] == "OFFLINE_TEST_CANARIES_PASSED"
    assert report["mode"] == "offline_test"
    assert report["provider"] == "nebius"
    assert report["model_expected"] == report["model_requested"] == report["model_configured"] == MODEL
    assert report["test_kind"] == "offline_injected_fake"
    assert report["wire_attempts"] == report["total_calls_made"] == 3
    assert report["sdk_retries"] == 0
    assert report["canaries"]["chat_ping"]["exact_pong"] is True
    assert report["canaries"]["tool_calling"]["exact_arguments"] is True
    assert report["canaries"]["tool_exchange_and_explanation"]["explanation_mode"] == "strict_explanation_plan"
    assert report["canaries"]["tool_exchange_and_explanation"]["fact_source"] == "python_owned_metadata_only"
    assert captured["client_kwargs"]["max_retries"] == 0
    exchange = captured["calls"][2]["messages"]
    assert exchange[1]["tool_calls"][0]["id"] == exchange[2]["tool_call_id"] == "original-call-7"
    assert all("max_tokens" in call and call["max_tokens"] > 0 for call in captured["calls"])
    assert captured["closed"] is True


def test_luna_g6_preflight_p03_one_token_no_wire(monkeypatch, tmp_path):
    result, report, captured = _run(monkeypatch, tmp_path, _responses(), tokens=1)
    assert result != 0
    assert report["status"] == "OFFLINE_TEST_CANARY_FAILED"
    assert report["wire_attempts"] == 0
    assert captured["calls"] == []


def test_luna_g6_preflight_p03_unknown_usage_stops(monkeypatch, tmp_path):
    responses = _responses()
    responses[0].usage = None
    result, report, captured = _run(monkeypatch, tmp_path, responses)
    assert result != 0
    assert report["failure"] == "USAGE_MISSING"
    assert report["wire_attempts"] == 1
    assert len(captured["calls"]) == 1


def test_luna_g6_preflight_p03_exact_ping_required(monkeypatch, tmp_path):
    result, report, captured = _run(monkeypatch, tmp_path, _responses(ping="PONG, done"))
    assert result != 0
    assert report["failure"] == "PING_CONTENT_INVALID"
    assert len(captured["calls"]) == 1


def test_luna_g6_preflight_p03_exact_model_required(monkeypatch, tmp_path):
    result, report, captured = _run(monkeypatch, tmp_path, _responses(model="nvidia/Nemotron"))
    assert result != 0
    assert report["status"] == "OFFLINE_TEST_CANARY_FAILED"
    assert report["wire_attempts"] == 1
    assert "model_returned" not in report["canaries"]["chat_ping"]

    _configure(monkeypatch)
    untouched: dict = {}
    path = tmp_path / "missing-model.json"
    refused = asyncio.run(preflight_nebius.run_preflight(
        True, 3, 10000, str(path), None,
        client_factory=_client_factory(_responses(), untouched),
        test_kind=preflight_nebius.OFFLINE_FAKE_TEST_KIND,
    ))
    assert refused != 0
    assert json.loads(path.read_text())["failure"] == "EXACT_MODEL_CONFIRMATION_REQUIRED"
    assert "client" not in untouched


def test_luna_g6_preflight_p03_tool_arguments_required(monkeypatch, tmp_path):
    result, report, captured = _run(monkeypatch, tmp_path, _responses(tool_arguments='{"dataset_id":"invented"}'))
    assert result != 0
    assert report["failure"] == "TOOL_CALL_INVALID"
    assert len(captured["calls"]) == 2


def test_luna_g6_preflight_p03_original_id_exchange_required():
    mismatched = SimpleNamespace(
        id="expected-id",
        function=SimpleNamespace(name="inspect_dataset", arguments='{"dataset_id":"bank"}'),
        model_dump=lambda: {
            "id": "different-id",
            "type": "function",
            "function": {"name": "inspect_dataset", "arguments": '{"dataset_id":"bank"}'},
        },
    )
    with pytest.raises(ValueError, match="original call id"):
        preflight_nebius.build_tool_exchange_messages(mismatched)


def test_luna_g6_preflight_p03_plan_or_fallback_required(monkeypatch, tmp_path):
    result, report, _captured = _run(monkeypatch, tmp_path, _responses(plan="not json"))
    assert result != 0
    assert report["status"] == "OFFLINE_TEST_CANARY_FAILED"
    assert report["failure"] == "STRICT_EXPLANATION_PLAN_INVALID"


def test_luna_g6_preflight_p03_provider_supplied_fallback_fails_required_plan(monkeypatch, tmp_path):
    provider_supplied_fallback = json.dumps({
        "kind": "validated_fallback",
        "summary": "Use the deterministic metadata result.",
        "source": "inspect_dataset",
    })
    result, report, _captured = _run(monkeypatch, tmp_path, _responses(plan=provider_supplied_fallback))
    assert result != 0
    assert report["status"] == "OFFLINE_TEST_CANARY_FAILED"
    assert report["failure"] == "STRICT_EXPLANATION_PLAN_INVALID"
    assert report["canaries"]["tool_exchange_and_explanation"]["explanation_mode"] is None


def test_luna_g6_preflight_p03_call_allowance_stops(monkeypatch, tmp_path):
    result, report, captured = _run(monkeypatch, tmp_path, _responses(), calls=1)
    assert result != 0
    assert report["canaries"]["tool_calling"]["status"] == "NOT_RUN"
    assert report["wire_attempts"] == 1
    assert len(captured["calls"]) == 1


def test_luna_g6_preflight_p03_sdk_429_is_single_wire_attempt(monkeypatch, tmp_path):
    _configure(monkeypatch)
    actual_client = openai.AsyncOpenAI
    wire_requests = []

    def transport(request):
        wire_requests.append(request)
        return httpx.Response(429, headers={"retry-after": "0"}, json={
            "error": {"message": "offline rate limit", "type": "rate_limit_error"},
        })

    def factory(**kwargs):
        assert kwargs["max_retries"] == 0
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        return actual_client(**kwargs, http_client=http_client)

    path = tmp_path / "429.json"
    result = asyncio.run(preflight_nebius.run_preflight(
        True, 1, 10000, str(path), MODEL, client_factory=factory,
        test_kind=preflight_nebius.OFFLINE_FAKE_TEST_KIND,
    ))
    report = json.loads(path.read_text(encoding="utf-8"))
    assert result != 0
    assert len(wire_requests) == report["wire_attempts"] == 1
    assert report["sdk_retries"] == 0
