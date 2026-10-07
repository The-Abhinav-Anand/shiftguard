import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from scripts import preflight_nebius
from shiftguard.agent.provider import AgentProvider, ProviderError
from shiftguard.settings import Settings


def test_provider_total_deadline_is_typed_and_single_attempt():
    provider = AgentProvider(Settings(agent_enabled=True, nebius_api_key="fixture", nebius_timeout=0.03))
    calls = 0

    async def slow(**kwargs):
        nonlocal calls
        calls += 1
        while True:
            await asyncio.sleep(0.005)

    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=slow)))
    started = time.monotonic()
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.chat([{"role": "user", "content": "ping"}]))
    assert time.monotonic() - started < 0.5
    assert calls == 1
    assert caught.value.code == "PROVIDER_TIMEOUT"
    assert caught.value.status_code == 504
    assert str(caught.value) == "Provider request timed out. Please try again."


def test_injected_preflight_defaults_offline_and_rejects_live_label(monkeypatch, tmp_path):
    monkeypatch.setenv("NEBIUS_API_KEY", "fixture")
    monkeypatch.setenv("NEBIUS_MODEL", preflight_nebius.EXPECTED_MODEL)
    monkeypatch.setattr(preflight_nebius, "PREFLIGHT_TIMEOUT_SECONDS", 0.02)
    calls = []

    class Client:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        async def create(self, **kwargs):
            calls.append(kwargs)
            await asyncio.sleep(1)
        async def close(self):
            pass

    path = tmp_path / "offline.json"
    result = asyncio.run(preflight_nebius.run_preflight(True, 3, 1000, str(path), preflight_nebius.EXPECTED_MODEL, client_factory=Client))
    report = json.loads(path.read_text())
    assert result == 1 and report["mode"] == "offline_test"
    assert report["test_kind"] == preflight_nebius.OFFLINE_FAKE_TEST_KIND
    assert report["canaries"]["chat_ping"]["failure"] == "PROVIDER_TIMEOUT"
    assert report["wire_attempts"] == len(calls) == 1

    calls.clear()
    path = tmp_path / "rejected-live.json"
    result = asyncio.run(preflight_nebius.run_preflight(True, 3, 1000, str(path), preflight_nebius.EXPECTED_MODEL, client_factory=Client, test_kind="provider_live_canary"))
    report = json.loads(path.read_text())
    assert result == 1 and report["status"] == "INVALID_TEST_KIND"
    assert report["wire_attempts"] == 0 and calls == []
