from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

pytest_plugins = ["test_luna_g6_protocol"]

from test_luna_g6_protocol import _call, _controller, _request, _response
from shiftguard.agent.provider import ScriptedProvider
from shiftguard.agent.tools import ToolContext


def _job_count(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one()


def test_direct_registry_rejects_nul_before_handler(protocol_env):
    env = protocol_env
    request = _request(env)
    registry = env["registry"]
    calls = []
    entry = registry._tools["inspect_dataset"]
    original_handler = entry.handler
    entry.handler = lambda *args: calls.append(args)
    context = ToolContext(
        engine=env["engine"], settings=env["settings"],
        session_id=env["session"].id,
        session_token=env["session"].capability_token,
        request_id=request.id,
    )
    try:
        result = registry.dispatch(
            "inspect_dataset", {"dataset_id": "bank"}, context, "bad\x00id",
        )
    finally:
        entry.handler = original_handler

    assert result.status == "error"
    assert result.error == "INVALID_ARGUMENTS: Arguments were rejected."
    assert calls == []
    assert env["store"].get_request(request.id).accepted_decision is None
    assert env["store"].list_tool_executions(request.id) == []
    assert _job_count(env["engine"]) == 0


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("inspect_dataset", {"dataset_id": "bank"}),
        ("run_experiment", {"preset_name": "bank-baseline"}),
    ],
    ids=("synchronous", "job"),
)
def test_controller_rejects_nul_before_checkpoint_or_dispatch(
    protocol_env, tool_name, arguments,
):
    env = protocol_env
    request = _request(env)
    provider = ScriptedProvider([_response(_call(tool_name, arguments, "bad\x00id"))])

    result = asyncio.run(
        _controller(env, provider).execute_request(request.id, "nul-call-id"),
    )

    assert result.status == "FAILED"
    assert result.accepted_decision is None
    assert result.error == {
        "code": "REQUEST_FAILED",
        "message": "EXPERIMENT_UNAVAILABLE: Published evidence is unavailable.",
    }
    assert env["store"].list_tool_executions(request.id) == []
    assert _job_count(env["engine"]) == 0
