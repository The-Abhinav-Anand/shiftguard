"""Offline SDK-wire contracts for the bounded Nemotron provider controls."""

from __future__ import annotations

import asyncio
import json

import httpx
import openai
import pytest

import shiftguard.agent.provider as provider_module
from scripts import preflight_nebius
from shiftguard.agent.provider import AgentProvider
from shiftguard.settings import Settings


MODEL = "nvidia/Nemotron-3_5-Lightning"
OFFLINE_KEY = "offline-dummy-key-only"


def _completion(*, content=None, tool_calls=None, model=MODEL, finish_reason=None):
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "id": "offline-g7-response",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{
            "index": 0,
            "finish_reason": finish_reason or ("tool_calls" if tool_calls else "stop"),
            "message": message,
        }],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 4,
            "total_tokens": 16,
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
    }


def _inspect_tool_call():
    return {
        "id": "offline-inspect-7",
        "type": "function",
        "function": {
            "name": "inspect_dataset",
            "arguments": '{"dataset_id":"bank"}',
        },
    }


def _configure_preflight(monkeypatch, thinking: bool | None):
    monkeypatch.setenv("NEBIUS_API_KEY", OFFLINE_KEY)
    monkeypatch.setenv("NEBIUS_MODEL", MODEL)
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://offline.invalid/v1")
    if thinking is None:
        monkeypatch.delenv("NEBIUS_ENABLE_THINKING", raising=False)
        monkeypatch.delenv("nebius_enable_thinking", raising=False)
    else:
        monkeypatch.setenv("NEBIUS_ENABLE_THINKING", str(thinking).lower())


@pytest.mark.parametrize(
    ("configured_thinking", "thinking"),
    [(None, False), (True, True)],
    ids=["bounded-default", "explicit-opt-in"],
)
def test_runtime_sends_template_control_and_preserves_output_cap(monkeypatch, configured_thinking, thinking):
    if configured_thinking is None:
        monkeypatch.delenv("NEBIUS_ENABLE_THINKING", raising=False)
        monkeypatch.delenv("nebius_enable_thinking", raising=False)
    else:
        monkeypatch.setenv("NEBIUS_ENABLE_THINKING", str(configured_thinking).lower())
    captured: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=_completion(content="PONG"))

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    actual_client = provider_module.AsyncOpenAI
    monkeypatch.setattr(
        provider_module,
        "AsyncOpenAI",
        lambda **kwargs: actual_client(**kwargs, http_client=http_client),
    )
    settings = Settings(
        agent_enabled=True,
        nebius_api_key=OFFLINE_KEY,
        nebius_base_url="https://offline.invalid/v1",
        nebius_model=MODEL,
        nebius_timeout=12.0,
        nebius_max_retries=0,
        nebius_max_output_tokens=37,
        _env_file=None,
    )
    provider = AgentProvider(settings)

    async def run():
        try:
            response = await provider.chat([{"role": "user", "content": "ping"}])
            assert response.content == "PONG"
            assert response.usage == {
                "prompt_tokens": 12,
                "completion_tokens": 4,
                "total_tokens": 16,
                "reasoning_tokens": 2,
            }
        finally:
            await provider.close()

    asyncio.run(run())
    assert captured[0]["chat_template_kwargs"] == {"enable_thinking": thinking}
    assert captured[0]["max_tokens"] == 37
    assert http_client.is_closed


@pytest.mark.parametrize(
    ("configured_thinking", "thinking"),
    [(None, False), (True, True)],
    ids=["bounded-default", "explicit-opt-in"],
)
def test_preflight_transmits_same_control_caps_and_redacted_diagnostics(
    monkeypatch, tmp_path, configured_thinking, thinking,
):
    _configure_preflight(monkeypatch, configured_thinking)
    bodies: list[dict] = []
    plans = [
        _completion(content="PONG"),
        _completion(tool_calls=[_inspect_tool_call()]),
        _completion(content='{"template":"summary","condition_refs":[]}'),
    ]

    def handle(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=plans[len(bodies) - 1])

    clients: list[openai.AsyncOpenAI] = []

    def client_factory(**kwargs):
        assert kwargs["max_retries"] == 0
        client = openai.AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
        )
        clients.append(client)
        return client

    evidence_path = tmp_path / "preflight.json"
    result = asyncio.run(preflight_nebius.run_preflight(
        live=True,
        max_calls=3,
        max_tokens=10_000,
        evidence_path=str(evidence_path),
        requested_model=MODEL,
        client_factory=client_factory,
        test_kind=preflight_nebius.OFFLINE_FAKE_TEST_KIND,
    ))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert result == 0
    assert evidence["status"] == "OFFLINE_TEST_CANARIES_PASSED"
    assert evidence["thinking_setting_enabled"] is thinking
    assert evidence["wire_attempts"] == evidence["total_calls_made"] == 3
    assert evidence["sdk_retries"] == 0
    assert evidence["reported_tokens"] == 48
    assert evidence["reserved_tokens"] <= 10_000
    assert [body["max_tokens"] for body in bodies] == [16, 128, 256]
    assert all(body["model"] == MODEL for body in bodies)
    assert all(body["chat_template_kwargs"] == {"enable_thinking": thinking} for body in bodies)
    assert all("extra_body" not in body for body in bodies)
    assert evidence["canaries"]["chat_ping"]["exact_pong"] is True
    ping_diagnostics = evidence["canaries"]["chat_ping"]["diagnostics"]
    assert ping_diagnostics == {
        "finish_reason": "stop",
        "content_present": True,
        "content_length": 4,
        "usage": {"prompt_tokens": 12, "completion_tokens": 4, "reasoning_tokens": 2},
    }
    tool_diagnostics = evidence["canaries"]["tool_calling"]["diagnostics"]
    assert tool_diagnostics["content_present"] is False
    assert tool_diagnostics["content_length"] == 0
    assert tool_diagnostics["finish_reason"] == "tool_calls"
    evidence_text = json.dumps(evidence)
    assert "PONG" not in evidence_text
    assert '{"template":"summary"' not in evidence_text
    assert OFFLINE_KEY not in evidence_text
    assert "Authorization" not in evidence_text
    assert clients and clients[0]._client.is_closed


def test_preflight_does_not_persist_credential_in_unrecognized_finish_reason(monkeypatch, tmp_path):
    _configure_preflight(monkeypatch, False)
    credential = "Bearer sol-g7-dummy-key-123456789"
    responses = [
        _completion(content="PONG", finish_reason=credential),
        _completion(tool_calls=[_inspect_tool_call()]),
        _completion(content='{"template":"summary","condition_refs":[]}'),
    ]
    request_urls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        request_urls.append(str(request.url))
        return httpx.Response(200, json=responses[len(request_urls) - 1])

    clients: list[openai.AsyncOpenAI] = []

    def client_factory(**kwargs):
        assert kwargs["max_retries"] == 0
        client = openai.AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
        )
        clients.append(client)
        return client

    evidence_path = tmp_path / "credential-finish-reason.json"
    result = asyncio.run(preflight_nebius.run_preflight(
        live=True,
        max_calls=3,
        max_tokens=10_000,
        evidence_path=str(evidence_path),
        requested_model=MODEL,
        client_factory=client_factory,
        test_kind=preflight_nebius.OFFLINE_FAKE_TEST_KIND,
    ))
    serialized_evidence = evidence_path.read_text(encoding="utf-8")
    evidence = json.loads(serialized_evidence)

    assert result == 0
    assert evidence["status"] == "OFFLINE_TEST_CANARIES_PASSED"
    assert evidence["wire_attempts"] == evidence["total_calls_made"] == 3
    assert [httpx.URL(url).host for url in request_urls] == ["offline.invalid"] * 3
    assert evidence["canaries"]["chat_ping"]["exact_pong"] is True
    assert evidence["canaries"]["tool_calling"]["exact_tool_name"] is True
    assert evidence["canaries"]["tool_calling"]["exact_arguments"] is True
    assert evidence["canaries"]["tool_exchange_and_explanation"]["status"] == "PASS"
    assert evidence["canaries"]["chat_ping"]["diagnostics"]["finish_reason"] is None
    assert credential not in serialized_evidence
    assert credential not in json.dumps(evidence)
    assert OFFLINE_KEY not in serialized_evidence
    assert len(clients) == 1 and clients[0]._client.is_closed


def test_preflight_reports_nonexact_ping_without_relaxing_check(monkeypatch, tmp_path):
    _configure_preflight(monkeypatch, False)
    bodies: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_completion(content="PONG, extra"))

    def client_factory(**kwargs):
        return openai.AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
        )

    evidence_path = tmp_path / "invalid-ping.json"
    result = asyncio.run(preflight_nebius.run_preflight(
        True, 3, 10_000, str(evidence_path), MODEL,
        client_factory=client_factory,
        test_kind=preflight_nebius.OFFLINE_FAKE_TEST_KIND,
    ))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert result != 0
    assert evidence["failure"] == "PING_CONTENT_INVALID"
    assert len(bodies) == evidence["wire_attempts"] == 1
    canary = evidence["canaries"]["chat_ping"]
    assert canary["status"] == "FAIL"
    assert canary["exact_pong"] is False
    assert canary["diagnostics"]["content_length"] == len("PONG, extra")
    assert "PONG, extra" not in json.dumps(evidence)


def test_preflight_rejects_live_client_injection_before_factory_call(monkeypatch, tmp_path):
    _configure_preflight(monkeypatch, False)
    factory_calls: list[dict] = []
    evidence_path = tmp_path / "injected-live-client.json"

    def forbidden_factory(**kwargs):
        factory_calls.append(kwargs)
        raise AssertionError("live test must not receive an injected client")

    result = asyncio.run(preflight_nebius.run_preflight(
        live=True,
        max_calls=3,
        max_tokens=10_000,
        evidence_path=str(evidence_path),
        requested_model=MODEL,
        client_factory=forbidden_factory,
        test_kind="provider_live_canary",
    ))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert result != 0
    assert evidence["failure"] == "INJECTED_CLIENT_REQUIRES_OFFLINE_TEST_KIND"
    assert evidence["wire_attempts"] == 0
    assert factory_calls == []
