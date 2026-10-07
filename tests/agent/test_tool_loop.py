"""Tests for AgentController bounded loop, exact tool IDs, turn/call limits, and repair policy."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine

from shiftguard.agent.controller import AgentController
from shiftguard.agent.policy import MAX_REPAIRS_PER_SIGNATURE, MAX_TOOL_CALLS, MAX_TURNS, AgentErrorCode
from shiftguard.agent.provider import ProviderResponse, ScriptedProvider
from shiftguard.agent.registry import ToolRegistry
from shiftguard.agent.schemas import FunctionCall, ToolCall
from shiftguard.agent.store import AgentStore
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def agent_environment(tmp_path):
    db_file = tmp_path / "test_loop.db"
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
    )
    upgrade_database(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    store = AgentStore(engine)
    registry = ToolRegistry()
    session = ContinuationService(engine).create_session()
    return engine, settings, store, registry, session


import asyncio


def test_exact_tool_call_id_and_serial_order(agent_environment):
    engine, settings, store, registry, session = agent_environment

    # Script provider with two tool calls in turn 1, then final answer in turn 2
    tc1 = ToolCall(
        id="call_alpha_123",
        type="function",
        function=FunctionCall(name="inspect_dataset", arguments='{"dataset_id": "bank"}'),
    )
    tc2 = ToolCall(
        id="call_beta_456",
        type="function",
        function=FunctionCall(name="list_available_scenarios", arguments='{"dataset_id": "bank"}'),
    )

    resp1 = ProviderResponse(content=None, tool_calls=[tc1, tc2])
    resp2 = ProviderResponse(content="I have inspected the dataset and scenarios.", tool_calls=None)

    provider = ScriptedProvider(responses=[resp1, resp2])
    controller = AgentController(engine, settings, store, registry, provider, session.capability_token)

    req, _ = store.create_or_get_request(
        session_id=session.id,
        intent_key="intent_1",
        canonical_body_hash="hash_1",
        prompt="Inspect dataset and list scenarios",
        authority_token_hash=store.authority_hash(session.capability_token),
    )

    async def _run():
        final_req = await controller.execute_request(req.id, worker_id="test_worker")
        assert final_req.status == "COMPLETED"
        assert final_req.call_count == 2
        assert final_req.turn_count == 2

        # Verify tool execution records
        tool_execs = store.list_tool_executions(req.id)
        assert len(tool_execs) == 2
        assert tool_execs[0].tool_call_id == "call_alpha_123"
        assert tool_execs[0].ordinal == 1
        assert tool_execs[0].tool_name == "inspect_dataset"

        assert tool_execs[1].tool_call_id == "call_beta_456"
        assert tool_execs[1].ordinal == 2
        assert tool_execs[1].tool_name == "list_available_scenarios"

        # Verify tool result messages in messages_json have exact tool_call_id
        tool_msgs = [m for m in final_req.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 2
        assert tool_msgs[0]["tool_call_id"] == "call_alpha_123"
        assert tool_msgs[1]["tool_call_id"] == "call_beta_456"

    asyncio.run(_run())


def test_bounded_max_calls_limit(agent_environment):
    engine, settings, store, registry, session = agent_environment

    # Script provider that requests 10 tool calls across turns
    responses = []
    for i in range(10):
        tc = ToolCall(
            id=f"call_{i}",
            type="function",
            function=FunctionCall(name="inspect_dataset", arguments='{"dataset_id": "bank"}'),
        )
        responses.append(ProviderResponse(content=None, tool_calls=[tc]))

    provider = ScriptedProvider(responses=responses)
    controller = AgentController(engine, settings, store, registry, provider, session.capability_token)

    req, _ = store.create_or_get_request(
        session_id=session.id,
        intent_key="intent_max_calls",
        canonical_body_hash="hash_max_calls",
        prompt="Loop calls indefinitely",
        authority_token_hash=store.authority_hash(session.capability_token),
    )

    async def _run():
        final_req = await controller.execute_request(req.id, worker_id="test_worker")
        assert final_req.status == "COMPLETED"
        assert final_req.call_count <= MAX_TOOL_CALLS
        assert "budget_limit_reached" in (final_req.final_response or {})

    asyncio.run(_run())


def test_one_repair_per_signature_limit(agent_environment):
    engine, settings, store, registry, session = agent_environment

    tc_bad_1 = ToolCall(
        id="call_bad_1",
        type="function",
        function=FunctionCall(name="inspect_dataset", arguments='{"invalid_param": 123}'),
    )
    tc_bad_2 = ToolCall(
        id="call_bad_2",
        type="function",
        function=FunctionCall(name="inspect_dataset", arguments='{"invalid_param": 123}'),
    )
    resp1 = ProviderResponse(content=None, tool_calls=[tc_bad_1])
    resp2 = ProviderResponse(content=None, tool_calls=[tc_bad_2])
    resp3 = ProviderResponse(content="Terminating after failure.", tool_calls=None)

    provider = ScriptedProvider(responses=[resp1, resp2, resp3])
    controller = AgentController(engine, settings, store, registry, provider, session.capability_token)

    req, _ = store.create_or_get_request(
        session_id=session.id,
        intent_key="intent_repair_sig",
        canonical_body_hash="hash_repair_sig",
        prompt="Test repair signature",
        authority_token_hash=store.authority_hash(session.capability_token),
    )

    async def _run():
        final_req = await controller.execute_request(req.id, worker_id="test_worker")
        tool_execs = store.list_tool_executions(req.id)
        assert len(tool_execs) == 2
        res2 = tool_execs[1].result or {}
        assert AgentErrorCode.REPAIR_BUDGET_EXCEEDED in (res2.get("error") or "")

    asyncio.run(_run())
