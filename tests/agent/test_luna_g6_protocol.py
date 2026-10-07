from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from shiftguard.agent.controller import AgentController
from shiftguard.agent.provider import ProviderResponse, ScriptedProvider
from shiftguard.agent.registry import ToolRegistry
from shiftguard.agent.schemas import FunctionCall, ToolCall
from shiftguard.agent.store import AgentStore
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.queue import JobQueue
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


class SimulatedCrash(BaseException):
    pass


@pytest.fixture(params=("sqlite", "postgresql"), ids=("sqlite", "postgresql"))
def protocol_env(request, tmp_path):
    admin = None
    schema = None
    engine = None
    # The PostgreSQL URL is provisioned by the existing isolated test backend helper.
    backend = request.param
    if backend == "postgresql":
        pg = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
        if not pg:
            pytest.skip("SHIFTGUARD_TEST_POSTGRES_URL is absent")
        admin = create_engine(pg, connect_args={"connect_timeout": 3})
        schema = "luna1_proto_" + uuid4().hex
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        db_url = make_url(pg).update_query_dict(
            {"options": f"-csearch_path={schema}"}
        ).render_as_string(hide_password=False)
        settings = Settings(
            SHIFTGUARD_DB_URL=db_url,
            SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
            environment="hosted",
        )
    else:
        settings = Settings(
            SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'protocol.sqlite'}",
            SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
            environment="local",
        )
    try:
        upgrade_database(settings)
        engine = create_engine(settings.db_url)
        store = AgentStore(engine)
        session = ContinuationService(engine).create_session()
        env = {
            "engine": engine, "settings": settings, "store": store,
            "queue": JobQueue(engine), "registry": ToolRegistry(), "session": session,
        }
        yield env
    finally:
        if engine is not None:
            engine.dispose()
        if admin is not None and schema is not None:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def _call(name, args, call_id):
    return ToolCall(
        id=call_id, type="function",
        function=FunctionCall(name=name, arguments=json.dumps(args)),
    )


def _response(*calls, content=None):
    return ProviderResponse(content=content, tool_calls=list(calls) or None)


def _request(env, prompt="Run the baseline", intent=None):
    session = env["session"]
    return env["store"].create_or_get_request(
        session_id=session.id, intent_key=intent or uuid4().hex,
        canonical_body_hash=uuid4().hex, prompt=prompt,
        authority_token_hash=env["store"].authority_hash(session.capability_token),
    )[0]


def _controller(env, provider):
    return AgentController(
        env["engine"], env["settings"], env["store"], env["registry"],
        provider, env["session"].capability_token,
    )


def _expire(env, request_id):
    with env["engine"].begin() as conn:
        conn.execute(text("""
            UPDATE agent_requests SET lease_expires_at = '2000-01-01T00:00:00+00:00'
            WHERE id = :id
        """), {"id": request_id})


def _complete_published(env, job_id, result_id=None):
    queue = env["queue"]
    claimed = queue.claim_next_job(worker_id="protocol-worker")
    assert claimed and claimed.id == job_id
    experiment_id = result_id or uuid4().hex[:24]
    execution_id, generation_id = str(uuid4()), str(uuid4())
    queue.mark_completed(
        job_id=job_id, fencing_token=claimed.fencing_token,
        experiment_id=experiment_id, result_data={"experiment_id": experiment_id},
    )
    now = "2026-10-01T00:00:00+00:00"
    with env["engine"].begin() as conn:
        conn.execute(text("""
            INSERT INTO experiments (id, payload_json, content_hashes_json)
            VALUES (:id, '{}', '{}')
        """), {"id": experiment_id})
        conn.execute(text("""
            INSERT INTO experiment_executions (execution_id, experiment_id, audit_json)
            VALUES (:execution, :id, '{}')
        """), {"execution": execution_id, "id": experiment_id})
        conn.execute(text("""
            INSERT INTO experiment_publications (
                generation_id, experiment_id, full_digest, execution_id, status,
                manifest_json, created_at, updated_at, job_id
            ) VALUES (:generation, :id, :digest, :execution, 'PUBLISHED', '{}', :now, :now, :job)
        """), {
            "generation": generation_id, "id": experiment_id, "digest": "a" * 64,
            "execution": execution_id, "now": now, "job": job_id,
        })
    return experiment_id


@pytest.mark.parametrize("boundary", ["before_dispatch", "after_admission"])
def test_luna_g6_protocol_recovers_the_saved_decision(protocol_env, monkeypatch, boundary):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "original_run"),
        _call("inspect_dataset", {}, "original_read"),
    )])
    original = env["registry"].dispatch

    def crash_dispatch(*args, **kwargs):
        if boundary == "after_admission":
            original(*args, **kwargs)
        raise SimulatedCrash()

    monkeypatch.setattr(env["registry"], "dispatch", crash_dispatch)
    with pytest.raises(SimulatedCrash):
        asyncio.run(_controller(env, provider).execute_request(req.id, "first"))
    saved = env["store"].get_request(req.id)
    assert saved.accepted_decision is not None
    assert saved.turn_count == 1
    monkeypatch.setattr(env["registry"], "dispatch", original)

    if boundary == "after_admission":
        assert saved.status == "WAITING_FOR_JOB"
        assert env["queue"].get_job(saved.active_job_id) is not None
    else:
        assert saved.status == "RUNNING"
        assert saved.pending_cursor == 0
        assert env["store"].list_tool_executions(req.id)[0].status == "PENDING"
        _expire(env, req.id)
        saved = asyncio.run(_controller(env, provider).execute_request(req.id, "recovery"))
        assert saved.status == "WAITING_FOR_JOB"
    assert provider.history and len(provider.history) == 1
    assert env["queue"].get_job(saved.active_job_id) is not None
    assert env["store"].list_tool_executions(req.id)[0].job_id == saved.active_job_id
    assert env["store"].get_request(req.id).pending_cursor == 1


def test_luna_g6_protocol_lost_lease_creates_no_trace_or_job(protocol_env, monkeypatch):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "stale_call")
    )])
    original = env["store"].record_tool_execution

    def takeover(*args, **kwargs):
        with env["engine"].begin() as conn:
            conn.execute(text("""
                UPDATE agent_requests SET generation = generation + 1, worker_id = 'winner',
                    lease_expires_at = '2099-01-01T00:00:00+00:00' WHERE id = :id
            """), {"id": req.id})
        return original(*args, **kwargs)

    monkeypatch.setattr(env["store"], "record_tool_execution", takeover)
    current = asyncio.run(_controller(env, provider).execute_request(req.id, "loser"))
    assert current.worker_id == "winner"
    assert env["store"].list_tool_executions(req.id) == []
    with env["engine"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one() == 0




def test_luna_g6_protocol_takeover_after_intent_leaves_no_phantom_job(protocol_env, monkeypatch):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "post_intent_stale")
    )])
    original = env["registry"].dispatch

    def take_over_then_dispatch(*args, **kwargs):
        with env["engine"].begin() as conn:
            conn.execute(text("""
                UPDATE agent_requests SET generation=generation+1, worker_id='winner',
                    lease_expires_at='2099-01-01T00:00:00+00:00' WHERE id=:id
            """), {"id": req.id})
        return original(*args, **kwargs)

    monkeypatch.setattr(env["registry"], "dispatch", take_over_then_dispatch)
    current = asyncio.run(_controller(env, provider).execute_request(req.id, "stale-owner"))

    executions = env["store"].list_tool_executions(req.id)
    assert current.worker_id == "winner"
    assert len(executions) == 1 and executions[0].status == "PENDING" and executions[0].job_id is None
    with env["engine"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM idempotency_records")).scalar_one() == 0


def test_luna_g6_protocol_provider_turn_counter_is_reserved_before_await(protocol_env):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("inspect_dataset", {"dataset_id": "bank"}, "counter_one"),
        _call("list_available_scenarios", {"dataset_id": "bank"}, "counter_two"),
    )])
    original = provider.chat

    async def crash_on_second_turn(**kwargs):
        if len(provider.history) == 1:
            raise SimulatedCrash()
        return await original(**kwargs)

    provider.chat = crash_on_second_turn
    with pytest.raises(SimulatedCrash):
        asyncio.run(_controller(env, provider).execute_request(req.id, "counter-worker"))

    saved = env["store"].get_request(req.id)
    assert saved.turn_count == 2 and saved.call_count == 2
    assert saved.accepted_decision is None and len(env["store"].list_tool_executions(req.id)) == 2


def test_luna_g6_protocol_committed_tool_result_is_not_replayed_after_crash(protocol_env, monkeypatch):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([
        _response(_call("inspect_dataset", {"dataset_id": "bank"}, "committed_read")),
        _response(content="Read-only tool result was saved."),
    ])
    dispatch = env["registry"].dispatch
    calls = []

    def count_dispatch(*args, **kwargs):
        calls.append(kwargs.get("tool_call_id"))
        return dispatch(*args, **kwargs)

    monkeypatch.setattr(env["registry"], "dispatch", count_dispatch)
    commit = env["store"].commit_tool_step

    def commit_then_crash(*args, **kwargs):
        commit(*args, **kwargs)
        raise SimulatedCrash()

    monkeypatch.setattr(env["store"], "commit_tool_step", commit_then_crash)
    with pytest.raises(SimulatedCrash):
        asyncio.run(_controller(env, provider).execute_request(req.id, "commit-first"))
    saved = env["store"].get_request(req.id)
    assert saved.call_count == 1 and saved.accepted_decision is None
    assert env["store"].list_tool_executions(req.id)[0].status == "success"

    monkeypatch.setattr(env["store"], "commit_tool_step", commit)
    _expire(env, req.id)
    done = asyncio.run(_controller(env, provider).execute_request(req.id, "commit-recovery"))
    assert done.status == "COMPLETED" and calls == ["committed_read"]
    assert len(provider.history) == 2 and len(env["store"].list_tool_executions(req.id)) == 1


def test_luna_g6_protocol_queue_and_request_fence_rollback_together(protocol_env, monkeypatch):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "rollback_call")
    )])
    original = JobQueue.enqueue_in_transaction

    def lose_request_after_enqueue(queue, conn, *args, **kwargs):
        job = original(queue, conn, *args, **kwargs)
        conn.execute(text("UPDATE agent_requests SET generation=generation+1 WHERE id=:id"), {"id": req.id})
        return job

    controller = _controller(env, provider)
    monkeypatch.setattr(JobQueue, "enqueue_in_transaction", lose_request_after_enqueue)
    current = asyncio.run(controller.execute_request(req.id, "rollback-worker"))

    trace = env["store"].list_tool_executions(req.id)
    with env["engine"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM idempotency_records")).scalar_one() == 0
    assert current.generation == req.generation + 1
    assert len(trace) == 1 and trace[0].status == "error" and trace[0].job_id is None


def test_luna_g6_protocol_queue_payload_must_match_saved_intent(protocol_env, monkeypatch):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "altered_params")
    )])
    controller = _controller(env, provider)
    original = controller._admit_job

    def alter_job_parameters(params, *args, **kwargs):
        return original({"preset_name": "bank-outage-50"}, *args, **kwargs)

    monkeypatch.setattr(controller, "_admit_job", alter_job_parameters)
    done = asyncio.run(controller.execute_request(req.id, "intent-worker"))

    trace = env["store"].list_tool_executions(req.id)
    assert done.status == "FAILED"
    assert len(trace) == 1 and trace[0].status == "error" and trace[0].job_id is None
    with env["engine"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM idempotency_records")).scalar_one() == 0


def test_luna_g6_protocol_unissued_nonce_cannot_claim_or_replay(protocol_env):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(content="unused")])
    controller = _controller(env, provider)

    status, response = asyncio.run(controller.resume_request(req.id, "attacker-chosen", "resume-worker"))

    assert status == 400
    assert response["error"]["code"] == "INVALID_RESUME_NONCE"
    assert env["store"].get_request(req.id).generation == req.generation
    assert env["store"].get_receipt(req.id, "attacker-chosen") is None
    assert provider.history == []


def test_luna_g6_protocol_nonce_from_future_generation_is_rejected(protocol_env):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "future_generation")
    )])
    waiting = asyncio.run(_controller(env, provider).execute_request(req.id, "nonce-first"))
    with env["engine"].begin() as conn:
        conn.execute(text("UPDATE agent_requests SET active_nonce_generation=generation+5 WHERE id=:id"), {
            "id": req.id,
        })

    status, response = asyncio.run(_controller(env, provider).resume_request(
        req.id, waiting.active_nonce, "nonce-future",
    ))

    assert status == 400 and response["error"]["code"] == "INVALID_RESUME_NONCE"
    saved = env["store"].get_request(req.id)
    assert saved.status == "WAITING_FOR_JOB" and saved.generation == waiting.generation
    assert env["store"].get_receipt(req.id, waiting.active_nonce) is None


@pytest.mark.parametrize("oversized", ["arguments", "content"])
def test_luna_g6_protocol_provider_output_bounds_fail_closed(protocol_env, oversized):
    env = protocol_env
    req = _request(env)
    if oversized == "arguments":
        response = _response(_call("inspect_dataset", {"dataset_id": "a" * (8 * 1024)}, "too_large"))
    else:
        response = _response(content="x" * (16 * 1024 + 1))
    provider = ScriptedProvider([response])

    done = asyncio.run(_controller(env, provider).execute_request(req.id, "bounded-worker"))

    assert done.status == "FAILED" and done.turn_count == 1
    assert done.accepted_decision is None and done.call_count == 0
    assert env["store"].list_tool_executions(req.id) == []


def test_luna_g6_protocol_duplicate_provider_call_ids_fail_before_dispatch(protocol_env):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "duplicate_id"),
        _call("inspect_dataset", {"dataset_id": "bank"}, "duplicate_id"),
    )])

    done = asyncio.run(_controller(env, provider).execute_request(req.id, "duplicate-worker"))

    assert done.status == "FAILED" and done.call_count == 0
    assert env["store"].list_tool_executions(req.id) == []
    with env["engine"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one() == 0


def test_luna_g6_protocol_one_repair_reservation_survives_job_resume(protocol_env):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([
        _response(
            _call("inspect_dataset", {"dataset_id": False}, "bad_initial"),
            _call("run_experiment", {"preset_name": "bank-baseline"}, "pause_run"),
        ),
        _response(
            _call("inspect_dataset", {"dataset_id": "bank"}, "one_correction"),
            _call("inspect_dataset", {"dataset_id": False}, "bad_again"),
            _call("inspect_dataset", {"dataset_id": False}, "bad_third"),
        ),
        _response(content="The run ended with bounded tool failures."),
    ])
    controller = _controller(env, provider)
    waiting = asyncio.run(controller.execute_request(req.id, "repair-first"))
    assert waiting.status == "WAITING_FOR_JOB"
    assert waiting.repair_count == 0 and any(value == 0 for value in waiting.repair_ledger.values())
    _complete_published(env, waiting.active_job_id)

    status, _ = asyncio.run(controller.resume_request(req.id, waiting.active_nonce, "repair-resume"))
    done = env["store"].get_request(req.id)
    executions = env["store"].list_tool_executions(req.id)

    assert status == 500 and done.status == "FAILED"
    assert done.repair_count == 1
    assert sum(value == 1 for value in done.repair_ledger.values()) == 1
    assert [entry.tool_call_id for entry in executions] == [
        "bad_initial", "pause_run", "one_correction", "bad_again", "bad_third",
    ]
    assert executions[2].status == "success"
    assert all("REPAIR_BUDGET_EXCEEDED" in str(entry.result) for entry in executions[3:])
    assert len(provider.history) == 3


def test_luna_g6_protocol_terminal_commit_and_receipt_are_one_transaction(protocol_env, monkeypatch):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "run_once")
    ), _response(content="Published result is ready.")])
    controller = _controller(env, provider)
    waiting = asyncio.run(controller.execute_request(req.id, "first"))
    nonce = waiting.active_nonce
    assert waiting.status == "WAITING_FOR_JOB" and nonce
    _complete_published(env, waiting.active_job_id)

    original = env["store"]._insert_receipt
    crashed = False

    def crash_before_terminal_receipt(conn, request_id, used_nonce, status_code, response):
        nonlocal crashed
        if status_code == 200 and not crashed:
            crashed = True
            raise SimulatedCrash()
        return original(conn, request_id, used_nonce, status_code, response)

    monkeypatch.setattr(env["store"], "_insert_receipt", crash_before_terminal_receipt)
    with pytest.raises(SimulatedCrash):
        asyncio.run(controller.resume_request(req.id, nonce, "resume-crash"))
    after_crash = env["store"].get_request(req.id)
    assert after_crash.status == "RUNNING"
    assert env["store"].get_receipt(req.id, nonce) is None
    assert after_crash.accepted_decision is not None

    _expire(env, req.id)
    status, response = asyncio.run(controller.resume_request(req.id, nonce, "resume-retry"))
    assert status == 200
    assert env["store"].get_request(req.id).status == "COMPLETED"
    assert len(provider.history) == 2
    saved = env["store"].get_receipt(req.id, nonce)
    assert saved and saved.status_code == status and saved.response == response
    assert asyncio.run(controller.resume_request(req.id, nonce, "replay")) == (status, response)


@pytest.mark.parametrize("job_state", ["failed", "cancelled"])
def test_luna_g6_protocol_terminal_job_error_survives_resume(protocol_env, job_state):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([
        _response(_call("run_experiment", {"preset_name": "bank-baseline"}, "terminal_call")),
        _response(content="A tool job ended unsuccessfully."),
    ])
    controller = _controller(env, provider)
    waiting = asyncio.run(controller.execute_request(req.id, "terminal-first"))
    with env["engine"].begin() as conn:
        conn.execute(text("UPDATE jobs SET status=:status, error_json=:error WHERE id=:id"), {
            "status": job_state,
            "error": json.dumps({"code": "SYNTHETIC_FAILURE", "message": "safe test failure"}),
            "id": waiting.active_job_id,
        })

    status, response = asyncio.run(controller.resume_request(req.id, waiting.active_nonce, "terminal-resume"))
    trace = env["store"].list_tool_executions(req.id)[0]
    terminal = env["store"].get_request(req.id)

    assert trace.status == ("error" if job_state == "failed" else "cancelled")
    expected_code = "SYNTHETIC_FAILURE" if job_state == "failed" else "JOB_CANCELLED"
    assert trace.result["error"]["code"] == expected_code
    assert terminal.status == ("FAILED" if job_state == "failed" else "CANCELLED")
    assert status == (500 if job_state == "failed" else 200)
    assert response["final_response"]["outcomes"][0]["status"] == trace.status
    assert env["store"].get_receipt(req.id, waiting.active_nonce).response == response


def test_luna_g6_protocol_completed_job_without_publication_is_not_evidence(protocol_env):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([
        _response(_call("run_experiment", {"preset_name": "bank-baseline"}, "unpublished_call")),
        _response(content="No result can be grounded."),
    ])
    controller = _controller(env, provider)
    waiting = asyncio.run(controller.execute_request(req.id, "publication-first"))
    claimed = env["queue"].claim_next_job(worker_id="unpublished-worker")
    assert claimed and claimed.id == waiting.active_job_id
    experiment_id = uuid4().hex[:24]
    env["queue"].mark_completed(
        job_id=claimed.id, fencing_token=claimed.fencing_token,
        experiment_id=experiment_id, result_data={"experiment_id": experiment_id},
    )

    status, response = asyncio.run(controller.resume_request(req.id, waiting.active_nonce, "publication-resume"))

    assert status == 500
    assert response["evidence_refs"] == []
    assert env["store"].list_tool_executions(req.id)[0].result["error"]["code"] == "PUBLISHED_RESULT_UNVERIFIED"


def test_luna_g6_protocol_two_provider_turns_enforce_eight_call_cap(protocol_env):
    env = protocol_env
    first = _response(*[
        _call("inspect_dataset", {"dataset_id": "bank"}, f"first_{index}")
        for index in range(7)
    ])
    second = _response(
        _call("inspect_dataset", {"dataset_id": "bank"}, "eighth"),
        _call("inspect_dataset", {"dataset_id": "bank"}, "overflow_ninth"),
    )
    provider = ScriptedProvider([first, second])
    req = _request(env)

    done = asyncio.run(_controller(env, provider).execute_request(req.id, "budget-worker"))

    assert done.status == "COMPLETED", repr((done.error, done.call_count, done.turn_count, done.accepted_decision, done.pending_cursor, done.worker_id, done.lease_expires_at))
    assert done.turn_count == 2 and done.call_count == 8
    assert len(env["store"].list_tool_executions(req.id)) == 8
    overflow_messages = [
        json.loads(message["content"])
        for message in done.messages
        if message.get("role") == "tool" and message.get("tool_call_id") == "overflow_ninth"
    ]
    assert len(overflow_messages) == 1
    assert overflow_messages[0]["status"] == "error"
    assert "BUDGET_EXCEEDED" in overflow_messages[0]["error"]
    assert len(provider.history) == 2


def test_luna_g6_protocol_session_revoked_during_provider_wait_blocks_dispatch(protocol_env):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "revoked_call")
    )])

    async def revoke_then_return(**kwargs):
        with env["engine"].begin() as conn:
            conn.execute(text("UPDATE agent_sessions SET status='expired' WHERE id=:id"), {
                "id": env["session"].id,
            })
        return provider.responses[0]

    provider.chat = revoke_then_return
    current = asyncio.run(_controller(env, provider).execute_request(req.id, "revocation-worker"))

    assert current.status == "FAILED"
    assert env["store"].list_tool_executions(req.id) == []
    with env["engine"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one() == 0


def test_luna_g6_protocol_capability_rotation_invalidates_saved_request(protocol_env):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(content="must not execute")])
    with env["engine"].begin() as conn:
        conn.execute(text("UPDATE agent_sessions SET capability_token='rotated-capability' WHERE id=:id"), {
            "id": env["session"].id,
        })

    old_token_result = asyncio.run(_controller(env, provider).execute_request(req.id, "old-token"))
    new_token_controller = AgentController(
        env["engine"], env["settings"], env["store"], env["registry"],
        provider, "rotated-capability",
    )
    new_token_result = asyncio.run(new_token_controller.execute_request(req.id, "new-token"))

    assert old_token_result.turn_count == new_token_result.turn_count == 0
    assert old_token_result.accepted_decision is None and provider.history == []


@pytest.mark.parametrize("authority_state", ["expired", "revoked", "rotated", "unknown_session"])
def test_luna_g6_protocol_legacy_binding_rejects_inactive_rotated_and_unknown_authority(
    protocol_env, authority_state,
):
    env = protocol_env
    req = _request(env)
    with env["engine"].begin() as conn:
        conn.execute(text("UPDATE agent_requests SET authority_token_hash=NULL WHERE id=:id"), {"id": req.id})
        if authority_state in {"expired", "revoked"}:
            conn.execute(text("UPDATE agent_sessions SET status=:status WHERE id=:id"), {
                "status": "expired" if authority_state == "expired" else "revoked",
                "id": env["session"].id,
            })
        elif authority_state == "rotated":
            conn.execute(text("UPDATE agent_sessions SET capability_token='rotated-after-0009' WHERE id=:id"), {
                "id": env["session"].id,
            })

    candidate_session_id = "missing-legacy-session" if authority_state == "unknown_session" else env["session"].id
    bound = env["store"].bind_legacy_request_authority(
        req.id, candidate_session_id, env["session"].capability_token,
    )

    assert bound is None
    assert env["store"].get_request(req.id).authority_token_hash is None


def test_luna_g6_protocol_revoked_session_at_queue_boundary_admits_nothing(protocol_env, monkeypatch):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([_response(
        _call("run_experiment", {"preset_name": "bank-baseline"}, "revoked_admission")
    )])
    original = env["registry"].dispatch

    def revoke_before_tool(name, raw_arguments, ctx, tool_call_id):
        with env["engine"].begin() as conn:
            conn.execute(text("UPDATE agent_sessions SET status='expired' WHERE id=:id"), {
                "id": env["session"].id,
            })
        return original(name, raw_arguments, ctx, tool_call_id)

    monkeypatch.setattr(env["registry"], "dispatch", revoke_before_tool)
    current = asyncio.run(_controller(env, provider).execute_request(req.id, "revocation-worker"))

    assert current.status == "FAILED"
    assert len(env["store"].list_tool_executions(req.id)) == 1
    assert env["store"].list_tool_executions(req.id)[0].status == "PENDING"
    with env["engine"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM idempotency_records")).scalar_one() == 0
