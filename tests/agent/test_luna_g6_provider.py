"""Permanent offline provider-adapter security and shape-bound regressions."""

from __future__ import annotations

import asyncio
import json

import httpx
import openai
import pytest

import shiftguard.agent.provider as provider_module
from shiftguard.agent.provider import AgentProvider, ProviderError
from shiftguard.settings import Settings


MODEL = "nvidia/Nemotron-3_5-Lightning"


def _provider(monkeypatch, handler, *, key="offline-known-secret-1234567890", output=37):
    actual_client = provider_module.AsyncOpenAI
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    monkeypatch.setattr(
        provider_module,
        "AsyncOpenAI",
        lambda **kwargs: actual_client(**kwargs, http_client=http_client),
    )
    settings = Settings(
        agent_enabled=True,
        nebius_api_key=key,
        nebius_base_url="https://offline.invalid/v1",
        nebius_model=MODEL,
        nebius_timeout=12.0,
        nebius_max_retries=0,
        nebius_max_output_tokens=output,
        _env_file=None,
    )
    return AgentProvider(settings), http_client


def _completion(body: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "offline-response-id",
        "object": "chat.completion",
        "created": 0,
        "model": MODEL,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", **body}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    })


def test_luna_g6_provider_p04_positive_actual_sdk_roundtrip(monkeypatch):
    requests: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return _completion({"content": "PONG"})

    provider, http_client = _provider(monkeypatch, handle)

    async def run():
        try:
            response = await provider.chat([{"role": "user", "content": "ping"}])
            assert response.content == "PONG"
            assert response.provider_request_id == "offline-response-id"
            assert response.usage == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
            assert requests[0]["model"] == MODEL
            assert requests[0]["max_tokens"] == 37
        finally:
            await provider.close()

    asyncio.run(run())
    assert http_client.is_closed


def test_luna_g6_provider_p04_configured_key_never_reaches_error_or_log(monkeypatch, caplog):
    secret = "credential embedded in ordinary upstream prose 8f12ab34"

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": secret, "type": "invalid_request_error"}})

    provider, _http_client = _provider(monkeypatch, handle, key=secret)

    async def run():
        try:
            with pytest.raises(ProviderError) as caught:
                await provider.chat([{"role": "user", "content": "ping"}])
            assert secret not in str(caught.value)
            assert secret not in caught.value.message
            assert secret not in (caught.value.raw_error or "")
            assert "PROVIDER" in caught.value.code
        finally:
            await provider.close()

    asyncio.run(run())
    assert secret not in caplog.text


def test_luna_g6_provider_p04_empty_choices_is_typed(monkeypatch):
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "offline-empty",
            "object": "chat.completion",
            "created": 0,
            "model": MODEL,
            "choices": [],
        })

    provider, _http_client = _provider(monkeypatch, handle)

    async def run():
        try:
            with pytest.raises(ProviderError) as caught:
                await provider.chat([{"role": "user", "content": "ping"}])
            assert caught.value.code == "PROVIDER_INVALID_RESPONSE"
            assert caught.value.status_code == 502
        finally:
            await provider.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("status", "error_type", "expected_code"),
    [(401, "authentication_error", "PROVIDER_AUTH_ERROR"),
     (429, "rate_limit_error", "PROVIDER_RATE_LIMIT"),
     (500, "server_error", "PROVIDER_SERVER_ERROR")],
    ids=["401", "429", "500"],
)
def test_luna_g6_provider_p04_actual_sdk_error_classification(monkeypatch, status, error_type, expected_code):
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "offline fixture error", "type": error_type}})

    provider, _http_client = _provider(monkeypatch, handle)

    async def run():
        try:
            with pytest.raises(ProviderError) as caught:
                await provider.chat([{"role": "user", "content": "ping"}])
            assert caught.value.code == expected_code
        finally:
            await provider.close()

    asyncio.run(run())


def test_luna_g6_provider_p04_output_cap_and_transcript_shape_bounds(monkeypatch):
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _completion({"content": "PONG"})

    provider, _http_client = _provider(monkeypatch, handle, output=37)

    async def run():
        try:
            await provider.chat([{"role": "user", "content": "ok"}])
            with pytest.raises(ProviderError) as caught:
                await provider.chat([{"role": "user", "content": "x" * 70000}])
            assert caught.value.code == "PROVIDER_INVALID_RESPONSE"
            assert len(requests) == 1
            assert json.loads(requests[0].content)["max_tokens"] == 37
        finally:
            await provider.close()

    asyncio.run(run())


def test_luna_g6_provider_p04_original_tool_call_id_preserved(monkeypatch):
    call_id = "call_original_19"

    def handle(_request: httpx.Request) -> httpx.Response:
        return _completion({
            "content": None,
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {"name": "inspect_dataset", "arguments": "{\"dataset_id\":\"bank\"}"},
            }],
        })

    provider, _http_client = _provider(monkeypatch, handle)

    async def run():
        try:
            response = await provider.chat([{"role": "user", "content": "inspect"}])
            assert response.tool_calls is not None
            assert response.tool_calls[0].id == call_id
            assert response.tool_calls[0].function.arguments == '{"dataset_id":"bank"}'
        finally:
            await provider.close()

    asyncio.run(run())


def test_luna_g6_provider_p04_sdk_client_closes(monkeypatch):
    provider, http_client = _provider(monkeypatch, lambda _request: _completion({"content": "PONG"}))
    asyncio.run(provider.close())
    assert http_client.is_closed


def test_luna_g6_provider_p04_settings_reject_unbounded_values():
    with pytest.raises(ValueError):
        Settings(nebius_timeout=float("inf"), _env_file=None)
    with pytest.raises(ValueError):
        Settings(nebius_max_retries=1, _env_file=None)
    with pytest.raises(ValueError):
        Settings(nebius_max_output_tokens=0, _env_file=None)
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError):
        settings.nebius_timeout = float("inf")
    with pytest.raises(ValueError):
        settings.nebius_max_retries = 1
    with pytest.raises(ValueError):
        settings.nebius_max_output_tokens = 4097
