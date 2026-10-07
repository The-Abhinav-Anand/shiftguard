"""Targeted regressions for the final bounded Gate 6 controller corrections."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from shiftguard.agent.controller import AgentController, format_agent_response
from shiftguard.agent.provider import ProviderResponse, ScriptedProvider
from shiftguard.agent.registry import ToolRegistry
from shiftguard.agent.schemas import FunctionCall, ToolCall
from shiftguard.agent.store import AgentStore
from shiftguard.experiments.ids import stable_hash
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.queue import JobQueue
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.repositories import ExperimentRepository


class SimulatedCrash(BaseException):
    pass


@pytest.fixture(params=("sqlite", "postgresql"), ids=("sqlite", "postgresql"))
def review_env(request, tmp_path):
    backend = request.param
    admin = schema = engine = None
    if backend == "postgresql":
        url = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("SHIFTGUARD_TEST_POSTGRES_URL is absent")
        admin = create_engine(url, connect_args={"connect_timeout": 3})
        schema = "g6review_" + uuid4().hex
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        db_url = make_url(url).update_query_dict(
            {"options": f"-csearch_path={schema}"}
        ).render_as_string(hide_password=False)
        settings = Settings(
            SHIFTGUARD_DB_URL=db_url,
            SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
            environment="hosted",
        )
    else:
        settings = Settings(
            SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'review.sqlite'}",
            SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
            environment="local",
        )
    try:
        upgrade_database(settings)
        engine = create_engine(settings.db_url)
        store = AgentStore(engine)
        session = ContinuationService(engine).create_session()
        yield {
            "backend": backend,
            "engine": engine,
            "settings": settings,
            "store": store,
            "queue": JobQueue(engine),
            "registry": ToolRegistry(),
            "session": session,
        }
    finally:
        if engine is not None:
            engine.dispose()
        if admin is not None and schema is not None:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def _call(name, arguments, call_id):
    return ToolCall(
        id=call_id,
        type="function",
        function=FunctionCall(name=name, arguments=json.dumps(arguments)),
    )


def _response(*calls, content=None):
    return ProviderResponse(content=content, tool_calls=list(calls) or None)


def _request(env, prompt="Run the baseline"):
    session = env["session"]
    return env["store"].create_or_get_request(
        session_id=session.id,
        intent_key=uuid4().hex,
        canonical_body_hash=uuid4().hex,
        prompt=prompt,
        authority_token_hash=env["store"].authority_hash(session.capability_token),
    )[0]


def _controller(env, provider):
    return AgentController(
        env["engine"], env["settings"], env["store"], env["registry"],
        provider, env["session"].capability_token,
    )


def _published_experiment(engine):
    nonce = uuid4().hex
    shared = {
        "predictor": "logistic_regression",
        "predictor_name": "logistic_regression",
        "dataset_id": "a" * 64,
        "evaluation_rows_id": "c" * 64,
        "source_map_id": "d" * 64,
        "test_mask_id": "e" * 64,
        "scenario": "mcar_0_30",
        "budget": 50,
        "status": "scored",
        "fallback_chain": [],
        "labels_consumed": 0,
        "sparse_bin_diagnostics": {
            "affected_fallback_rows": 0,
            "resolution_counts": {"raw": 0},
            "bin_eval_counts": {"0": 10},
            "bin_fallback_counts": {},
            "bin_support": {"0": 10},
            "bin_resolution_counts": {},
            "bin_resolved_maps": {},
            "sparse_prediction_failures": 0,
            "failed_attempts": [],
        },
    }
    raw = {
        **shared,
        "predictor_id": "b" * 64,
        "method": "raw",
        "requested_method": "raw",
        "resolved_method": "raw",
        "fit_status": "not_applicable",
        "fitted_parameters": {"fit_status": "pipeline_direct", "type": "raw_frozen_pipeline"},
        "metrics": {"brier_score": 0.2, "log_loss": 0.8, "ece": 0.1},
        "acquired_record_ids": [],
    }
    raw["condition_id"] = stable_hash(raw)[:24]
    target = {
        **shared,
        "predictor_id": "b" * 64,
        "method": "target_temperature",
        "requested_method": "target_temperature",
        "resolved_method": "target_temperature",
        "fit_status": "fitted",
        "fitted_parameters": {"fit_status": "fitted", "temperature": 1.2},
        "metrics": {"brier_score": 0.1, "log_loss": 0.7, "ece": 0.05},
        "acquired_record_ids": [],
    }
    target["condition_id"] = stable_hash(target)[:24]
    payload = {
        "fixture_nonce": nonce,
        "dataset": {"raw_hash": "f" * 64, "clean_hash": "1" * 64},
        "seeds": {"master": 31001},
        "config": {"master_seed": 31001},
        "protocol": {},
        "conditions": {
            "logistic_regression__mcar_0_30__b50__raw": raw,
            "logistic_regression__mcar_0_30__b50__target_temperature": target,
        },
    }
    logical = stable_hash(payload)
    experiment_id = logical[:24]
    generation_id, execution_id = str(uuid4()), str(uuid4())
    manifest_hash = hashlib.sha256(nonce.encode()).hexdigest()
    repo = ExperimentRepository(engine)
    repo.reserve_publication(
        generation_id=generation_id,
        experiment_id=experiment_id,
        full_digest=logical,
        execution_id=execution_id,
        manifest={"result.json": manifest_hash},
        prepared_payload=payload,
        prepared_audit={"execution_id": execution_id},
    )
    repo.put(
        experiment_id=experiment_id,
        deterministic_payload=payload,
        content_hashes={"result": manifest_hash, "logical_content": logical},
        execution_id=execution_id,
        audit_metadata={"execution_id": execution_id},
        generation_id=generation_id,
    )
    return experiment_id


def _expire_lease(env, request_id):
    with env["engine"].begin() as conn:
        conn.execute(text("""
            UPDATE agent_requests SET lease_expires_at='2000-01-01T00:00:00+00:00'
            WHERE id=:id
        """), {"id": request_id})


def _complete_published_job(env, job_id):
    claimed = env["queue"].claim_next_job(worker_id="review-protocol-worker")
    assert claimed and claimed.id == job_id
    experiment_id = uuid4().hex[:24]
    execution_id, generation_id = str(uuid4()), str(uuid4())
    env["queue"].mark_completed(
        job_id=job_id,
        fencing_token=claimed.fencing_token,
        experiment_id=experiment_id,
        result_data={"experiment_id": experiment_id},
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
            "generation": generation_id,
            "id": experiment_id,
            "digest": "a" * 64,
            "execution": execution_id,
            "now": now,
            "job": job_id,
        })
    return experiment_id


def test_selected_published_experiment_is_bound_and_grounded(review_env):
    env = review_env
    experiment_id = _published_experiment(env["engine"])
    req = _request(env, f"Read the results of published experiment {experiment_id}.")
    provider = ScriptedProvider([
        _response(_call("read_experiment_results", {"experiment_id": experiment_id}, "read-selected")),
        _response(content=json.dumps({"template": "summary", "condition_refs": []})),
    ])

    done = asyncio.run(_controller(env, provider).execute_request(req.id, "selected-worker"))
    formatted = format_agent_response(done, env["store"])

    assert formatted["tool_trace"][0]["status"] == "success"
    assert formatted["tool_trace"][0]["result"]["data"]["total_conditions"] == 2
    assert experiment_id in formatted["evidence_refs"]
    assert len(formatted["final_response"]["claims"]) >= 2


def test_unselected_prompt_substring_does_not_authorize_published_facts(review_env):
    env = review_env
    experiment_id = _published_experiment(env["engine"])
    req = _request(env, f"This note contains token {experiment_id}, with no request to read it.")
    provider = ScriptedProvider([
        _response(_call("read_experiment_results", {"experiment_id": experiment_id}, "read-unselected")),
    ])

    done = asyncio.run(_controller(env, provider).execute_request(req.id, "unselected-worker"))
    formatted = format_agent_response(done, env["store"])

    assert formatted["evidence_refs"] == []
    assert formatted["tool_trace"][0]["status"] in {"error", "unavailable"}
    assert formatted["final_response"]["claims"] == []


def test_reserved_eighth_run_recovers_once_and_new_ninth_call_stays_capped(review_env, monkeypatch):
    env = review_env
    req = _request(env, "Inspect Bank and run the baseline.")
    calls = [_call("inspect_dataset", {"dataset_id": "bank"}, f"read-{i}") for i in range(7)]
    calls.append(_call("run_experiment", {"preset_name": "bank-baseline"}, "eighth-run"))
    provider = ScriptedProvider([
        _response(*calls),
        _response(content="The published run is ready."),
    ])
    original = env["registry"].dispatch
    attempts = []

    def crash_before_eighth_dispatch(name, raw_arguments, ctx, tool_call_id):
        if tool_call_id == "eighth-run":
            attempts.append("reserved")
            if len(attempts) == 1:
                raise SimulatedCrash()
        return original(name, raw_arguments, ctx, tool_call_id)

    monkeypatch.setattr(env["registry"], "dispatch", crash_before_eighth_dispatch)
    with pytest.raises(SimulatedCrash):
        asyncio.run(_controller(env, provider).execute_request(req.id, "crash-worker"))
    before = env["store"].get_request(req.id)
    assert before.call_count == 8 and before.pending_cursor == 7

    _expire_lease(env, req.id)
    waiting = asyncio.run(_controller(env, provider).execute_request(req.id, "recovery-worker"))
    assert waiting.status == "WAITING_FOR_JOB"
    assert len(attempts) == 2 and len(provider.history) == 1
    with env["engine"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one() == 1

    _complete_published_job(env, waiting.active_job_id)
    status, body = asyncio.run(_controller(env, provider).resume_request(
        req.id, waiting.active_nonce, "recovery-resume",
    ))
    assert status == 200 and body["status"] == "COMPLETED"
    assert [row["tool_call_id"] for row in body["tool_trace"]].count("eighth-run") == 1
    assert len(provider.history) == 1


def test_new_calls_after_eighth_reservation_are_overflowed(review_env):
    env = review_env
    req = _request(env)
    calls = [_call("inspect_dataset", {"dataset_id": "bank"}, f"call-{i}") for i in range(9)]
    done = asyncio.run(_controller(env, ScriptedProvider([_response(*calls)])).execute_request(
        req.id, "cap-worker",
    ))
    overflow = [
        json.loads(message["content"])
        for message in done.messages
        if message.get("role") == "tool" and message.get("tool_call_id") == "call-8"
    ]
    assert done.call_count == 8
    assert len(env["store"].list_tool_executions(req.id)) == 8
    assert len(overflow) == 1 and overflow[0]["status"] == "error"
    assert "BUDGET_EXCEEDED" in str(overflow[0]["error"])


def test_semantic_handler_error_gets_one_repair_then_refuses_before_dispatch(review_env, monkeypatch):
    env = review_env
    req = _request(env)
    arguments = {
        "experiment_id": "a" * 24,
        "scenario": "mcar_0_30",
        "fp_cost": 2.5,
        "fn_cost": 7.5,
    }
    entry = env["registry"]._tools["calculate_decision_loss"]
    original = entry.handler
    invocations = []

    def count_handler(params, context, call_id):
        invocations.append(call_id)
        return original(params, context, call_id)

    monkeypatch.setattr(entry, "handler", count_handler)
    provider = ScriptedProvider([
        _response(*[
            _call("calculate_decision_loss", arguments, f"invalid-cost-{i}")
            for i in range(4)
        ]),
        _response(content="The invalid requests were bounded."),
    ])

    done = asyncio.run(_controller(env, provider).execute_request(req.id, "repair-worker"))
    traces = env["store"].list_tool_executions(req.id)

    assert invocations == ["invalid-cost-0", "invalid-cost-1"]
    assert done.repair_count == 1
    assert len(done.repair_ledger) == 1 and next(iter(done.repair_ledger.values())) == 1
    assert all(
        (trace.arguments["fp_cost"], trace.arguments["fn_cost"]) == (2.5, 7.5)
        for trace in traces
    )
    assert all(trace.status == "error" for trace in traces)
    assert all("REPAIR_BUDGET_EXCEEDED" in str(trace.result) for trace in traces[1:])


@pytest.mark.parametrize("first_invalid", [False, True], ids=("successful-final", "failed-final"))
def test_budget_final_request_status_matches_the_final_answer(review_env, first_invalid):
    env = review_env
    req = _request(env)
    calls = []
    if first_invalid:
        calls.append(_call("inspect_dataset", {"dataset_id": False}, "invalid-first"))
    calls.extend(
        _call("inspect_dataset", {"dataset_id": "bank"}, f"valid-{i}")
        for i in range(8 - len(calls))
    )

    done = asyncio.run(_controller(env, ScriptedProvider([_response(*calls)])).execute_request(
        req.id, "budget-worker",
    ))
    formatted = format_agent_response(done, env["store"])
    expected = "FAILED" if first_invalid else "COMPLETED"

    assert formatted["final_response"]["status"] == expected
    assert done.status == expected
    assert (formatted["error"]["code"] == "FAILED") if first_invalid else formatted["error"] is None


def test_legacy_pending_json_arguments_are_normalized_once(review_env, monkeypatch):
    env = review_env
    req = _request(env, "Run the baseline, then inspect Bank.")
    provider = ScriptedProvider([
        _response(_call("run_experiment", {"preset_name": "bank-baseline"}, "legacy-run")),
        _response(content="The saved read was processed."),
    ])
    control = _controller(env, provider)
    waiting = asyncio.run(control.execute_request(req.id, "legacy-first"))
    following = {
        "id": "legacy-following",
        "type": "function",
        "function": {"name": "inspect_dataset", "arguments": json.dumps({"dataset_id": "bank"})},
    }
    with env["engine"].begin() as conn:
        conn.execute(text("""
            UPDATE agent_requests
            SET accepted_decision_json=NULL, pending_cursor=0,
                pending_tool_calls_json=:calls, authority_token_hash=NULL
            WHERE id=:id
        """), {"id": req.id, "calls": json.dumps([following])})
    _complete_published_job(env, waiting.active_job_id)
    observed = {}
    original_dispatch = env["registry"].dispatch

    def inspect_normalized(name, raw_arguments, ctx, tool_call_id):
        if tool_call_id == "legacy-following":
            saved = env["store"].get_request(req.id)
            observed["cursor"] = saved.pending_cursor
            observed["call"] = saved.accepted_decision["tool_calls"][saved.pending_cursor]
        return original_dispatch(name, raw_arguments, ctx, tool_call_id)

    monkeypatch.setattr(env["registry"], "dispatch", inspect_normalized)
    status, body = asyncio.run(control.resume_request(
        req.id, waiting.active_nonce, "legacy-resume",
    ))

    assert status == 200 and body["status"] == "COMPLETED"
    assert observed["cursor"] == 0
    assert observed["call"] == {
        "id": "legacy-following",
        "name": "inspect_dataset",
        "arguments": {"dataset_id": "bank"},
    }
    trace = next(entry for entry in body["tool_trace"] if entry["tool_call_id"] == "legacy-following")
    assert trace["status"] == "success"
    assert trace["arguments"] == {"dataset_id": "bank"}


@pytest.mark.parametrize("malformed", [False, True], ids=("valid-legacy-json", "malformed-legacy-json"))
def test_controller_normalizes_legacy_accepted_decision_once(review_env, monkeypatch, malformed):
    env = review_env
    req = _request(env, "Run the baseline, then inspect Bank.")
    provider = ScriptedProvider([
        _response(_call("run_experiment", {"preset_name": "bank-baseline"}, "direct-legacy-run")),
        _response(content="The saved read was processed."),
    ])
    control = _controller(env, provider)
    waiting = asyncio.run(control.execute_request(req.id, "direct-legacy-first"))
    legacy_decision = {
        "content": None,
        "tool_calls": [{
            "id": "direct-legacy-following",
            "name": "inspect_dataset",
            "arguments": "{broken-json" if malformed else json.dumps({"dataset_id": "bank"}),
        }],
        "first_ordinal": 2,
    }
    with env["engine"].begin() as conn:
        conn.execute(text("""
            UPDATE agent_requests
            SET accepted_decision_json=:decision, pending_cursor=0,
                pending_tool_calls_json='[]'
            WHERE id=:id
        """), {"id": req.id, "decision": json.dumps(legacy_decision)})
    _complete_published_job(env, waiting.active_job_id)
    observed = {}
    original_dispatch = env["registry"].dispatch

    def inspect_normalized(name, raw_arguments, ctx, tool_call_id):
        if tool_call_id == "direct-legacy-following":
            saved = env["store"].get_request(req.id)
            observed["cursor"] = saved.pending_cursor
            observed["first_ordinal"] = saved.accepted_decision["first_ordinal"]
            observed["call"] = saved.accepted_decision["tool_calls"][saved.pending_cursor]
        return original_dispatch(name, raw_arguments, ctx, tool_call_id)

    monkeypatch.setattr(env["registry"], "dispatch", inspect_normalized)
    status, body = asyncio.run(control.resume_request(
        req.id, waiting.active_nonce, "direct-legacy-resume",
    ))

    if malformed:
        assert status == 500 and body["status"] == "FAILED"
        assert observed == {}
        assert "direct-legacy-following" not in [entry["tool_call_id"] for entry in body["tool_trace"]]
    else:
        assert status == 200 and body["status"] == "COMPLETED"
        assert observed["cursor"] == 0 and observed["first_ordinal"] == 2
        assert observed["call"] == {
            "id": "direct-legacy-following",
            "name": "inspect_dataset",
            "arguments": {"dataset_id": "bank"},
        }
        trace = next(entry for entry in body["tool_trace"] if entry["tool_call_id"] == "direct-legacy-following")
        assert trace["status"] == "success"
