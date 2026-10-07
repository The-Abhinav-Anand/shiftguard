"""Tests for AgentProvider adapter, error classification, secret redaction, and ScriptedProvider."""

from __future__ import annotations

import pytest

from shiftguard.agent.policy import AgentErrorCode
from shiftguard.agent.provider import (
    AgentProvider,
    ProviderDisabledError,
    ProviderError,
    ProviderResponse,
    ScriptedProvider,
    redact_secrets,
)
from shiftguard.agent.schemas import FunctionCall, ToolCall
from shiftguard.settings import Settings


def test_provider_disabled_by_default():
    settings = Settings(agent_enabled=False, nebius_api_key=None)
    provider = AgentProvider(settings)
    assert not provider.is_available()


import asyncio

def test_provider_disabled_raises_on_chat():
    settings = Settings(agent_enabled=False, nebius_api_key=None)
    provider = AgentProvider(settings)

    async def _run():
        with pytest.raises(ProviderDisabledError) as exc_info:
            await provider.chat([{"role": "user", "content": "hello"}])
        assert exc_info.value.code == AgentErrorCode.PROVIDER_DISABLED

    asyncio.run(_run())


def test_secret_redaction():
    text_with_bearer = "Authorization failed: Bearer secret_nebius_key_1234567890abcdef in request"
    redacted = redact_secrets(text_with_bearer)
    assert "secret_nebius_key_1234567890abcdef" not in redacted
    assert "[REDACTED]" in redacted

    text_with_key = "Connection failed for key=nb_live_9876543210fedcba9876"
    redacted_key = redact_secrets(text_with_key)
    assert "nb_live_9876543210fedcba9876" not in redacted_key
    assert "[REDACTED]" in redacted_key


def test_scripted_provider_replays_responses_in_order():
    r1 = ProviderResponse(
        content=None,
        tool_calls=[
            ToolCall(
                id="call_001",
                type="function",
                function=FunctionCall(name="inspect_dataset", arguments='{"dataset_id": "bank"}'),
            )
        ],
    )
    r2 = ProviderResponse(content="Bank dataset inspected.", tool_calls=None)

    scripted = ScriptedProvider(responses=[r1, r2])

    async def _run():
        resp1 = await scripted.chat([{"role": "user", "content": "step 1"}])
        assert resp1.tool_calls is not None
        assert resp1.tool_calls[0].id == "call_001"
        assert resp1.is_mock is True

        resp2 = await scripted.chat([{"role": "user", "content": "step 2"}])
        assert resp2.content == "Bank dataset inspected."
        assert resp2.is_mock is True

        # Fallback response after script exhausted
        resp3 = await scripted.chat([{"role": "user", "content": "step 3"}])
        assert "Scripted default" in (resp3.content or "")
        assert resp3.is_mock is True

    asyncio.run(_run())


def test_scripted_provider_simulates_provider_error():
    err = ProviderError(
        code="PROVIDER_TIMEOUT",
        message="Simulated timeout",
        status_code=504,
    )
    scripted = ScriptedProvider(responses=[err])

    async def _run():
        with pytest.raises(ProviderError) as exc_info:
            await scripted.chat([{"role": "user", "content": "test"}])
        assert exc_info.value.code == "PROVIDER_TIMEOUT"
        assert exc_info.value.status_code == 504

    asyncio.run(_run())
