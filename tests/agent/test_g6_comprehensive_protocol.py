import asyncio
import json

import pytest
from alembic import command
from sqlalchemy import inspect, text

from test_luna_g6_protocol import (
    SimulatedCrash, _call, _complete_published, _controller, _expire,
    _request, _response, protocol_env,
)
from shiftguard.agent.provider import ScriptedProvider
from shiftguard.migrations import get_alembic_config


def _revision(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _column_length(engine, table, column):
    return next(c["type"].length for c in inspect(engine).get_columns(table) if c["name"] == column)


def _job_count(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one()


def test_execute_recovery_replays_original_nonce_receipt(protocol_env, monkeypatch):
    env = protocol_env
    request = _request(env)
    provider = ScriptedProvider([
        _response(_call("run_experiment", {"preset_name": "bank-baseline"}, "first")),
        _response(content=json.dumps({"template": "summary", "condition_refs": []})),
    ])
    controller = _controller(env, provider)
    waiting = asyncio.run(controller.execute_request(request.id, "initial"))
    nonce = waiting.active_nonce
    _complete_published(env, waiting.active_job_id)
    original = controller._run_owned_request

    async def crash(*args):
        raise SimulatedCrash()

    monkeypatch.setattr(controller, "_run_owned_request", crash)
    with pytest.raises(SimulatedCrash):
        asyncio.run(controller.resume_request(request.id, nonce, "resume"))
    resolved = env["store"].get_request(request.id)
    assert resolved.status == "RUNNING" and resolved.active_job_id is None
    assert resolved.active_nonce == nonce and env["store"].get_receipt(request.id, nonce) is None

    _expire(env, request.id)
    monkeypatch.setattr(controller, "_run_owned_request", original)
    recovered = asyncio.run(controller.execute_request(request.id, "recovery"))
    receipt = env["store"].get_receipt(request.id, nonce)
    replay = asyncio.run(controller.resume_request(request.id, nonce, "duplicate-resume"))
    assert recovered.status == "COMPLETED"
    assert receipt and receipt.status_code == 200 and replay == (200, receipt.response)
    assert len(provider.history) == 2 and _job_count(env["engine"]) == 1


def test_execute_recovery_settles_nonce_with_terminal_job_error(protocol_env, monkeypatch):
    env = protocol_env
    request = _request(env)
    provider = ScriptedProvider([
        _response(_call("run_experiment", {"preset_name": "bank-baseline"}, "failed-job")),
        _response(content="The queued operation failed."),
    ])
    controller = _controller(env, provider)
    waiting = asyncio.run(controller.execute_request(request.id, "initial"))
    nonce = waiting.active_nonce
    with env["engine"].begin() as conn:
        conn.execute(text("UPDATE jobs SET status='failed', error_json=:error WHERE id=:id"), {
            "error": json.dumps({"code": "SYNTHETIC_FAILURE", "message": "safe test failure"}),
            "id": waiting.active_job_id,
        })
    original = controller._run_owned_request

    async def crash(*args):
        raise SimulatedCrash()

    monkeypatch.setattr(controller, "_run_owned_request", crash)
    with pytest.raises(SimulatedCrash):
        asyncio.run(controller.resume_request(request.id, nonce, "resume"))
    resolved = env["store"].get_request(request.id)
    assert resolved.status == "RUNNING" and resolved.active_nonce == nonce
    assert env["store"].get_receipt(request.id, nonce) is None

    _expire(env, request.id)
    monkeypatch.setattr(controller, "_run_owned_request", original)
    recovered = asyncio.run(controller.execute_request(request.id, "recovery"))
    receipt = env["store"].get_receipt(request.id, nonce)
    replay = asyncio.run(controller.resume_request(request.id, nonce, "duplicate-resume"))
    assert recovered.status == "FAILED"
    assert receipt and receipt.status_code == 500 and replay == (500, receipt.response)
    assert receipt.response["final_response"]["outcomes"][0]["error"]["code"] == "SYNTHETIC_FAILURE"
    assert len(env["store"].list_tool_executions(request.id)) == 1
    assert _job_count(env["engine"]) == 1 and len(provider.history) == 2


def test_execute_recovery_carries_nonce_through_next_job_admission(protocol_env, monkeypatch):
    env = protocol_env
    request = _request(env, prompt="Run bank-baseline and bank-outage-50")
    provider = ScriptedProvider([
        _response(_call("run_experiment", {"preset_name": "bank-baseline"}, "first-job")),
        _response(_call("run_experiment", {"preset_name": "bank-outage-50"}, "second-job")),
        _response(content=json.dumps({"template": "summary", "condition_refs": []})),
    ])
    controller = _controller(env, provider)
    first = asyncio.run(controller.execute_request(request.id, "initial"))
    first_nonce = first.active_nonce
    _complete_published(env, first.active_job_id)
    original = controller._run_owned_request

    async def crash(*args):
        raise SimulatedCrash()

    monkeypatch.setattr(controller, "_run_owned_request", crash)
    with pytest.raises(SimulatedCrash):
        asyncio.run(controller.resume_request(request.id, first_nonce, "resume"))
    assert env["store"].get_receipt(request.id, first_nonce) is None

    _expire(env, request.id)
    monkeypatch.setattr(controller, "_run_owned_request", original)
    second = asyncio.run(controller.execute_request(request.id, "recovery"))
    first_receipt = env["store"].get_receipt(request.id, first_nonce)
    assert second.status == "WAITING_FOR_JOB" and second.active_job_id != first.active_job_id
    assert second.active_nonce and second.active_nonce != first_nonce
    assert first_receipt and first_receipt.status_code == 202
    assert first_receipt.response["active_job_id"] == second.active_job_id
    assert asyncio.run(controller.resume_request(request.id, first_nonce, "old-nonce")) == (
        202, first_receipt.response,
    )
    assert len(env["store"].list_tool_executions(request.id)) == 2
    assert _job_count(env["engine"]) == 2 and len(provider.history) == 2

    _complete_published(env, second.active_job_id)
    status, response = asyncio.run(
        controller.resume_request(request.id, second.active_nonce, "second-resume")
    )
    assert status == 200 and env["store"].get_request(request.id).status == "COMPLETED"
    assert env["store"].get_receipt(request.id, second.active_nonce).response == response
    assert env["store"].get_receipt(request.id, first_nonce).response == first_receipt.response


def test_call_id_migration_widens_preserves_and_downgrades_without_loss(protocol_env):
    env = protocol_env
    settings = env["settings"]
    config = get_alembic_config(settings)
    command.downgrade(config, "0010_gate6_protocol_hardening")
    assert _revision(env["engine"]) == "0010_gate6_protocol_hardening"
    assert _column_length(env["engine"], "agent_requests", "active_tool_call_id") == 64
    assert _column_length(env["engine"], "agent_tool_executions", "tool_call_id") == 64

    call_id = "legacy_" + "x" * 57
    request = _request(env)
    controller = _controller(env, ScriptedProvider([
        _response(_call("inspect_dataset", {"dataset_id": "bank"}, call_id)),
        _response(content="The dataset is available."),
    ]))
    completed = asyncio.run(controller.execute_request(request.id, "legacy-width"))
    assert completed.status == "COMPLETED"
    with env["engine"].begin() as conn:
        conn.execute(text("UPDATE agent_requests SET active_tool_call_id=:call_id WHERE id=:id"), {
            "call_id": call_id, "id": request.id,
        })

    command.upgrade(config, "head")
    assert _revision(env["engine"]) == "0011_gate6_call_id_capacity"
    assert _column_length(env["engine"], "agent_requests", "active_tool_call_id") == 256
    assert _column_length(env["engine"], "agent_tool_executions", "tool_call_id") == 256
    with env["engine"].connect() as conn:
        assert conn.execute(text(
            "SELECT active_tool_call_id FROM agent_requests WHERE id=:id"
        ), {"id": request.id}).scalar_one() == call_id
        assert conn.execute(text(
            "SELECT tool_call_id FROM agent_tool_executions WHERE request_id=:id"
        ), {"id": request.id}).scalar_one() == call_id

    oversized = "z" * 65
    with env["engine"].begin() as conn:
        conn.execute(text("UPDATE agent_requests SET active_tool_call_id=:value WHERE id=:id"), {
            "value": oversized, "id": request.id,
        })
        conn.execute(text("UPDATE agent_tool_executions SET tool_call_id=:value WHERE request_id=:id"), {
            "value": oversized, "id": request.id,
        })
    with pytest.raises(RuntimeError, match="Cannot downgrade call-ID capacity"):
        command.downgrade(config, "0010_gate6_protocol_hardening")
    assert _revision(env["engine"]) == "0011_gate6_call_id_capacity"
    assert _column_length(env["engine"], "agent_requests", "active_tool_call_id") == 256
    assert _column_length(env["engine"], "agent_tool_executions", "tool_call_id") == 256
    with env["engine"].connect() as conn:
        assert conn.execute(text(
            "SELECT active_tool_call_id FROM agent_requests WHERE id=:id"
        ), {"id": request.id}).scalar_one() == oversized
        assert conn.execute(text(
            "SELECT tool_call_id FROM agent_tool_executions WHERE request_id=:id"
        ), {"id": request.id}).scalar_one() == oversized

    with env["engine"].begin() as conn:
        conn.execute(text("UPDATE agent_requests SET active_tool_call_id=:value WHERE id=:id"), {
            "value": call_id, "id": request.id,
        })
        conn.execute(text("UPDATE agent_tool_executions SET tool_call_id=:value WHERE request_id=:id"), {
            "value": call_id, "id": request.id,
        })
    command.downgrade(config, "0010_gate6_protocol_hardening")
    assert _revision(env["engine"]) == "0010_gate6_protocol_hardening"
    assert _column_length(env["engine"], "agent_requests", "active_tool_call_id") == 64
    assert _column_length(env["engine"], "agent_tool_executions", "tool_call_id") == 64
    with env["engine"].connect() as conn:
        assert conn.execute(text(
            "SELECT active_tool_call_id FROM agent_requests WHERE id=:id"
        ), {"id": request.id}).scalar_one() == call_id
        assert conn.execute(text(
            "SELECT tool_call_id FROM agent_tool_executions WHERE request_id=:id"
        ), {"id": request.id}).scalar_one() == call_id
    command.upgrade(config, "head")
    assert _revision(env["engine"]) == "0011_gate6_call_id_capacity"


def test_call_ids_at_utf8_byte_boundaries_round_trip_storage(protocol_env):
    env = protocol_env
    call_ids = ("a" * 65, "é" * 64, "é" * 128)
    assert [len(value.encode("utf-8")) for value in call_ids] == [65, 128, 256]
    controller = _controller(env, ScriptedProvider([]))
    normalized, _ = controller._normalize_decision(_response(*[
        _call("inspect_dataset", {"dataset_id": "bank"}, call_id)
        for call_id in call_ids
    ]))
    assert [call["id"] for call in normalized["tool_calls"]] == list(call_ids)

    request = _request(env)
    with env["engine"].begin() as conn:
        for ordinal, call_id in enumerate(call_ids, start=1):
            conn.execute(text("""
                INSERT INTO agent_tool_executions (
                    id, request_id, ordinal, tool_name, tool_call_id, arguments_json,
                    status, idempotency_key, job_id, result_json, created_at, completed_at
                ) VALUES (
                    :id, :request_id, :ordinal, 'inspect_dataset', :call_id, '{}',
                    'success', :key, NULL, NULL, '2026-10-03T00:00:00+00:00', NULL
                )
            """), {
                "id": f"boundary-{ordinal}", "request_id": request.id, "ordinal": ordinal,
                "call_id": call_id, "key": f"agent:{request.id}:{ordinal}",
            })
        conn.execute(text(
            "UPDATE agent_requests SET active_tool_call_id=:call_id WHERE id=:id"
        ), {"call_id": call_ids[0], "id": request.id})

    records = env["store"].list_tool_executions(request.id)
    assert [record.tool_call_id for record in records] == list(call_ids)
    assert [len(record.tool_call_id.encode("utf-8")) for record in records] == [65, 128, 256]
    assert env["store"].get_request(request.id).active_tool_call_id == call_ids[0]


def test_call_id_over_256_utf8_bytes_is_rejected_before_storage(protocol_env):
    env = protocol_env
    request = _request(env)
    call_id = "x" * 255 + "é"
    assert len(call_id.encode("utf-8")) == 257
    result = asyncio.run(_controller(env, ScriptedProvider([
        _response(_call("inspect_dataset", {"dataset_id": "bank"}, call_id)),
    ])).execute_request(request.id, "oversized"))
    assert result.status == "FAILED"
    assert env["store"].list_tool_executions(request.id) == []
    assert env["store"].get_request(request.id).accepted_decision is None


def test_long_call_id_is_preserved_in_waiting_job_link(protocol_env):
    env = protocol_env
    request = _request(env)
    call_id = "w" * 65
    waiting = asyncio.run(_controller(env, ScriptedProvider([
        _response(_call("run_experiment", {"preset_name": "bank-baseline"}, call_id)),
    ])).execute_request(request.id, "waiting-link"))
    traces = env["store"].list_tool_executions(request.id)
    assert waiting.status == "WAITING_FOR_JOB" and waiting.active_job_id
    assert waiting.active_tool_call_id == call_id
    assert len(traces) == 1 and traces[0].tool_call_id == call_id
    assert traces[0].job_id == waiting.active_job_id
    assert env["queue"].get_job(waiting.active_job_id).id == waiting.active_job_id


@pytest.mark.parametrize("tool_kind", ["sync", "async"])
@pytest.mark.parametrize("arguments_differ", [False, True], ids=["same-args", "changed-args"])
def test_reused_call_id_is_rejected_before_second_dispatch(protocol_env, tool_kind, arguments_differ):
    env = protocol_env
    request = _request(env)
    call_id = "reused-across-turns"
    if tool_kind == "sync":
        first_args = {"dataset_id": "bank"}
        second_args = {"dataset_id": "adult" if arguments_differ else "bank"}
        first_call = _call("inspect_dataset", first_args, call_id)
        second_call = _call("inspect_dataset", second_args, call_id)
    else:
        first_args = {"preset_name": "bank-baseline"}
        second_args = {
            "preset_name": "bank-outage-50" if arguments_differ else "bank-baseline"
        }
        first_call = _call("run_experiment", first_args, call_id)
        second_call = _call("run_experiment", second_args, call_id)
    provider = ScriptedProvider([
        _response(first_call), _response(second_call),
    ])
    controller = _controller(env, provider)

    if tool_kind == "sync":
        terminal = asyncio.run(controller.execute_request(request.id, "sync-reuse"))
        status_code = None
    else:
        first = asyncio.run(controller.execute_request(request.id, "async-first"))
        assert first.status == "WAITING_FOR_JOB"
        _complete_published(env, first.active_job_id)
        status_code, _ = asyncio.run(
            controller.resume_request(request.id, first.active_nonce, "async-reuse")
        )
        terminal = env["store"].get_request(request.id)

    traces = env["store"].list_tool_executions(request.id)
    messages = [
        message for message in terminal.messages
        if message.get("role") == "tool" and message.get("tool_call_id") == call_id
    ]
    assistant_calls = [
        call for message in terminal.messages if message.get("role") == "assistant"
        for call in message.get("tool_calls", []) if call.get("id") == call_id
    ]
    assert terminal.status == "FAILED"
    assert len(traces) == 1 and traces[0].tool_call_id == call_id
    assert len(messages) == 1 and len(assistant_calls) == 1
    assert len(provider.history) == 2
    assert _job_count(env["engine"]) == (1 if tool_kind == "async" else 0)
    if tool_kind == "async":
        receipt = env["store"].get_receipt(request.id, first.active_nonce)
        assert status_code == 500 and receipt and receipt.status_code == 500
        assert asyncio.run(controller.resume_request(request.id, first.active_nonce, "replay")) == (
            500, receipt.response,
        )
