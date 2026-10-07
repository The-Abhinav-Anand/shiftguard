"""R09 preflight contract probes; every provider response is an offline fake."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from scripts import preflight_nebius
from shiftguard.agent.rendering import parse_explanation_plan


MODEL = preflight_nebius.EXPECTED_MODEL


def _choice(*, content=None, tool_calls=None):
    return SimpleNamespace(
        id="offline-response-id",
        model=MODEL,
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, tool_calls=tool_calls),
            finish_reason="tool_calls" if tool_calls else "stop",
        )],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4, total_tokens=16),
    )


def _inspect_call():
    arguments = '{"dataset_id":"bank"}'
    return SimpleNamespace(
        id="offline-inspect-call",
        type="function",
        function=SimpleNamespace(name="inspect_dataset", arguments=arguments),
        model_dump=lambda: {
            "id": "offline-inspect-call",
            "type": "function",
            "function": {"name": "inspect_dataset", "arguments": arguments},
        },
    )


def _fake_client_factory(plan_content: str, captured: dict):
    responses = [
        _choice(content="PONG"),
        _choice(tool_calls=[_inspect_call()]),
        _choice(content=plan_content),
    ]

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            captured["calls"] = []
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        async def create(self, **kwargs):
            captured["calls"].append(kwargs)
            return responses.pop(0)

        async def close(self):
            captured["closed"] = True

    return FakeClient


def _configure_fake_endpoint(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "offline-test-key-only")
    monkeypatch.setenv("NEBIUS_MODEL", MODEL)
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://offline.invalid/v1")


def _run_offline_fake(monkeypatch, tmp_path, plan_content: str):
    _configure_fake_endpoint(monkeypatch)
    captured: dict = {}
    evidence_path = tmp_path / "offline-preflight.json"
    code = asyncio.run(preflight_nebius.run_preflight(
        live=True,
        max_calls=3,
        max_tokens=10_000,
        evidence_path=str(evidence_path),
        requested_model=MODEL,
        client_factory=_fake_client_factory(plan_content, captured),
        test_kind=preflight_nebius.OFFLINE_FAKE_TEST_KIND,
    ))
    return code, json.loads(evidence_path.read_text(encoding="utf-8")), captured


def test_g6_r09_offline_fake_accepts_runtime_strict_plan_and_python_facts(monkeypatch, tmp_path):
    strict_plan = '{"template":"summary","condition_refs":[]}'
    parsed = parse_explanation_plan(strict_plan, set())
    assert parsed is not None
    assert parsed.model_dump() == {"template": "summary", "condition_refs": []}
    referenced = parse_explanation_plan(
        '{"template":"comparisons","condition_refs":["condition-demo"]}',
        {"condition-demo"},
    )
    assert referenced is not None and referenced.template == "comparisons"
    assert parse_explanation_plan(
        '{"template":"summary","condition_refs":["condition-demo"]}', set(),
    ) is None

    code, evidence, captured = _run_offline_fake(monkeypatch, tmp_path, strict_plan)

    assert code == 0
    assert evidence["status"] == "OFFLINE_TEST_CANARIES_PASSED"
    assert evidence["mode"] == "offline_test"
    assert evidence["provider"] == "nebius"
    assert evidence["model_expected"] == evidence["model_configured"] == evidence["model_requested"] == MODEL
    assert evidence["test_kind"] == "offline_injected_fake"
    assert evidence["canaries"]["tool_exchange_and_explanation"]["explanation_mode"] == "strict_explanation_plan"
    assert evidence["canaries"]["tool_exchange_and_explanation"]["fact_source"] == "python_owned_metadata_only"
    assert evidence["canaries"]["tool_exchange_and_explanation"]["authorized_condition_refs"] == []
    assert all(canary["model_returned"] == MODEL for canary in evidence["canaries"].values())
    assert len(captured["calls"]) == 3
    assert captured["client_kwargs"]["max_retries"] == 0
    assert json.loads(captured["calls"][2]["messages"][2]["content"]) == {
        "dataset_id": "bank",
        "canary": "metadata-only",
    }
    assert "Do not include prose, numbers, claims" in captured["calls"][2]["messages"][3]["content"]
    assert captured["closed"] is True


def test_g6_r09_offline_fake_rejects_independent_unchecked_narrative_probe(monkeypatch, tmp_path):
    unchecked = json.dumps({
        "kind": "explanation_plan",
        "summary": "Brier score is 0.0000; statistically significant improvement.",
        "claims": [{"text": "All 82 rows recovered.", "evidence": ["inspect_dataset"]}],
    })
    assert parse_explanation_plan(unchecked, set()) is None

    code, evidence, captured = _run_offline_fake(monkeypatch, tmp_path, unchecked)

    canary = evidence["canaries"]["tool_exchange_and_explanation"]
    assert code != 0
    assert evidence["status"] == "OFFLINE_TEST_CANARY_FAILED"
    assert evidence["status"] != "LIVE_CANARIES_PASSED"
    assert evidence["failure"] == "STRICT_EXPLANATION_PLAN_INVALID"
    assert canary["status"] == "FAIL"
    assert canary["explanation_mode"] is None
    assert canary["fact_source"] == "python_owned_metadata_only"
    assert evidence["mode"] == "offline_test"
    assert evidence["test_kind"] == "offline_injected_fake"
    assert len(captured["calls"]) == evidence["wire_attempts"] == 3
