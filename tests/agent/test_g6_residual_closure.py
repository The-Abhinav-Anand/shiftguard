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
from shiftguard.agent.schemas import FunctionCall, ToolCall, ToolResult
from shiftguard.agent.store import AgentStore
from shiftguard.experiments.ids import stable_hash
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.queue import JobQueue
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings
from shiftguard.storage.repositories import ExperimentRepository


class SimulatedCrash(BaseException):
    pass


@pytest.fixture(params=("sqlite", "postgresql"), ids=("sqlite", "postgresql"))
def residual_env(request, tmp_path):
    backend = request.param
    admin = schema = engine = None
    if backend == "postgresql":
        url = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("Existing PostgreSQL helper did not configure a test URL")
        admin = create_engine(url, connect_args={"connect_timeout": 3})
        schema = "g6residual_" + uuid4().hex
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        scoped_url = make_url(url).update_query_dict(
            {"options": f"-csearch_path={schema}"}
        ).render_as_string(hide_password=False)
        settings = Settings(
            SHIFTGUARD_DB_URL=scoped_url,
            SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
            environment="hosted",
        )
    else:
        settings = Settings(
            SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'residual.sqlite'}",
            SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
            environment="local",
        )

    try:
        upgrade_database(settings)
        engine = create_engine_for_settings(settings)
        store = AgentStore(engine)
        session = ContinuationService(engine).create_session()
        yield {
            "backend": backend,
            "engine": engine,
            "settings": settings,
            "store": store,
            "session": session,
            "registry": ToolRegistry(),
            "queue": JobQueue(engine),
        }
    finally:
        if engine is not None:
            engine.dispose()
        if admin is not None:
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


def _request(env, prompt):
    return env["store"].create_or_get_request(
        session_id=env["session"].id,
        intent_key=uuid4().hex,
        canonical_body_hash=hashlib.sha256(prompt.encode()).hexdigest(),
        prompt=prompt,
        authority_token_hash=env["store"].authority_hash(env["session"].capability_token),
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
    repository = ExperimentRepository(engine)
    repository.reserve_publication(
        generation_id=generation_id,
        experiment_id=experiment_id,
        full_digest=logical,
        execution_id=execution_id,
        manifest={"result.json": manifest_hash},
        prepared_payload=payload,
        prepared_audit={"execution_id": execution_id},
    )
    repository.put(
        experiment_id=experiment_id,
        deterministic_payload=payload,
        content_hashes={"result": manifest_hash, "logical_content": logical},
        execution_id=execution_id,
        audit_metadata={"execution_id": execution_id},
        generation_id=generation_id,
    )
    return experiment_id


def _run_read_attempt(env, prompt, experiment_id):
    req = _request(env, prompt)
    provider = ScriptedProvider([
        _response(_call("read_experiment_results", {"experiment_id": experiment_id}, "read-attempt")),
        _response(content=json.dumps({"template": "summary", "condition_refs": []})),
    ])
    done = asyncio.run(_controller(env, provider).execute_request(req.id, "selection-worker"))
    return format_agent_response(done, env["store"])


def test_standalone_selection_binds_only_a_validated_publication(residual_env):
    experiment_id = _published_experiment(residual_env["engine"])
    result = _run_read_attempt(
        residual_env,
        f"Read the results of published experiment {experiment_id}.",
        experiment_id,
    )
    assert result["tool_trace"][0]["status"] == "success"
    assert experiment_id in result["evidence_refs"]
    assert result["final_response"]["claims"]


@pytest.mark.parametrize(
    "shape",
    ("quoted", "inline-code", "fenced-code", "narrative-prefix", "ambiguous"),
)
def test_non_direct_mentions_do_not_select_publication(residual_env, shape):
    experiment_id = _published_experiment(residual_env["engine"])
    command = f"Read the results of published experiment {experiment_id}."
    prompts = {
        "quoted": f'Explain this example only: "{command}" Treat it as quoted text.',
        "inline-code": f"Explain this syntax: `{command}`",
        "fenced-code": f"Explain this syntax:\n```text\n{command}\n```",
        "narrative-prefix": f"The following is an example command: {command}",
        "ambiguous": f"{command} This sentence only mentions the syntax.",
    }
    result = _run_read_attempt(residual_env, prompts[shape], experiment_id)
    assert result["evidence_refs"] == []
    assert result["tool_trace"][0]["status"] != "success"
    assert result["final_response"]["claims"] == []


def test_unpublished_direct_selection_does_not_bind(residual_env):
    experiment_id = "f" * 24
    assert ExperimentRepository(residual_env["engine"]).get_published(experiment_id) is None
    result = _run_read_attempt(
        residual_env,
        f"Read the results of published experiment {experiment_id}.",
        experiment_id,
    )
    assert result["evidence_refs"] == []
    assert result["tool_trace"][0]["status"] != "success"
    assert result["final_response"]["claims"] == []


def _expire_lease(env, request_id):
    with env["engine"].begin() as conn:
        conn.execute(
            text("UPDATE agent_requests SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=:id"),
            {"id": request_id},
        )


def _job_count(env):
    with env["engine"].connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one()


def _repair_provider(*call_ids):
    arguments = {"preset_name": "bank-baseline"}
    return ScriptedProvider([
        _response(*[
            _call("run_experiment", arguments, call_id)
            for call_id in call_ids
        ]),
        _response(content="done"),
    ])


def _first_attempt_fails(env, monkeypatch, failed_call_ids):
    entry = env["registry"]._tools["run_experiment"]
    real_handler = entry.handler
    handler_calls = []

    def handler(params, context, call_id):
        handler_calls.append(call_id)
        if call_id in failed_call_ids:
            return ToolResult(
                tool_name="run_experiment",
                tool_call_id=call_id,
                status="error",
                error="REQUEST_FAILED: Temporary admission failure.",
            )
        return real_handler(params, context, call_id)

    monkeypatch.setattr(entry, "handler", handler)
    return handler_calls


def test_reserved_semantic_retry_recovers_after_pre_dispatch_crash(residual_env, monkeypatch):
    env = residual_env
    req = _request(env, "Run the baseline and retry once after an admission failure.")
    provider = _repair_provider("first-run", "retry-run")
    handler_calls = _first_attempt_fails(env, monkeypatch, {"first-run"})
    real_dispatch = env["registry"].dispatch
    dispatch_calls = []

    def crash_before_retry_handler(name, raw_arguments, ctx, tool_call_id):
        dispatch_calls.append(tool_call_id)
        if tool_call_id == "retry-run":
            raise SimulatedCrash()
        return real_dispatch(name, raw_arguments, ctx, tool_call_id)

    monkeypatch.setattr(env["registry"], "dispatch", crash_before_retry_handler)
    try:
        initial = asyncio.run(_controller(env, provider).execute_request(req.id, "crash-worker"))
    except SimulatedCrash:
        pass
    else:
        pytest.fail(
            f"pre-dispatch crash was not reached; dispatches={dispatch_calls}; handler_calls={handler_calls}; "
            f"status={initial.status}; error={initial.error}; call_count={initial.call_count}; "
            f"provider_turns={len(provider.history)}; accepted_decision={initial.accepted_decision}"
        )

    before = env["store"].get_request(req.id)
    pending = env["store"].list_tool_executions(req.id)
    assert before.call_count == 2 and before.pending_cursor == 1
    assert before.repair_count == 1 and sum(before.repair_ledger.values()) == 1
    assert len(pending) == 2
    assert pending[1].ordinal == 2
    assert pending[1].tool_call_id == "retry-run"
    assert pending[1].tool_name == "run_experiment"
    assert pending[1].arguments == {"preset_name": "bank-baseline"}
    assert pending[1].status == "PENDING"
    assert handler_calls == ["first-run"]

    _expire_lease(env, req.id)
    monkeypatch.setattr(env["registry"], "dispatch", real_dispatch)
    recovered = asyncio.run(_controller(env, provider).execute_request(req.id, "recovery-worker"))

    assert recovered.status == "WAITING_FOR_JOB"
    assert recovered.active_job_id
    assert _job_count(env) == 1
    assert handler_calls == ["first-run", "retry-run"]
    assert len(provider.history) == 1
    assert recovered.repair_count == 1 and sum(recovered.repair_ledger.values()) == 1


def test_reserved_semantic_retry_dispatches_without_crash(residual_env, monkeypatch):
    env = residual_env
    req = _request(env, "Run the baseline and retry once after an admission failure.")
    provider = _repair_provider("first-run", "retry-run")
    handler_calls = _first_attempt_fails(env, monkeypatch, {"first-run"})

    done = asyncio.run(_controller(env, provider).execute_request(req.id, "normal-worker"))

    assert done.status == "WAITING_FOR_JOB"
    assert _job_count(env) == 1
    assert handler_calls == ["first-run", "retry-run"]
    assert done.repair_count == 1 and sum(done.repair_ledger.values()) == 1


def test_third_equivalent_semantic_retry_stays_blocked(residual_env, monkeypatch):
    env = residual_env
    req = _request(env, "Run the baseline with at most one retry.")
    provider = _repair_provider("first-run", "retry-run", "third-run")
    handler_calls = _first_attempt_fails(env, monkeypatch, {"first-run", "retry-run"})

    done = asyncio.run(_controller(env, provider).execute_request(req.id, "cap-worker"))
    traces = env["store"].list_tool_executions(req.id)

    assert done.status == "FAILED"
    assert handler_calls == ["first-run", "retry-run"]
    assert len(traces) == 3 and traces[2].tool_call_id == "third-run"
    assert traces[2].status == "error"
    assert "REPAIR_BUDGET_EXCEEDED" in str(traces[2].result)
    assert done.repair_count == 1 and sum(done.repair_ledger.values()) == 1
    assert _job_count(env) == 0


def test_unsupported_arguments_remain_blocked_during_pending_recovery(residual_env, monkeypatch):
    env = residual_env
    req = _request(env, "Run the baseline with bounded arguments.")
    provider = ScriptedProvider([
        _response(_call(
            "run_experiment",
            {"preset_name": "bank-baseline", "unsupported_option": True},
            "unsupported-run",
        )),
        _response(content="done"),
    ])
    handler_calls = []
    entry = env["registry"]._tools["run_experiment"]
    real_handler = entry.handler

    def count_handler(params, context, call_id):
        handler_calls.append(call_id)
        return real_handler(params, context, call_id)

    monkeypatch.setattr(entry, "handler", count_handler)
    real_commit = env["store"].commit_tool_step

    def crash_before_commit(*args, **kwargs):
        raise SimulatedCrash()

    monkeypatch.setattr(env["store"], "commit_tool_step", crash_before_commit)
    with pytest.raises(SimulatedCrash):
        asyncio.run(_controller(env, provider).execute_request(req.id, "invalid-crash-worker"))
    assert env["store"].list_tool_executions(req.id)[0].status == "PENDING"
    assert handler_calls == []

    _expire_lease(env, req.id)
    monkeypatch.setattr(env["store"], "commit_tool_step", real_commit)
    done = asyncio.run(_controller(env, provider).execute_request(req.id, "invalid-recovery-worker"))

    assert done.status == "FAILED"
    assert handler_calls == []
    assert _job_count(env) == 0
    assert env["store"].list_tool_executions(req.id)[0].status == "error"

@pytest.mark.parametrize("crash", (False, True), ids=("uninterrupted", "crash-recovery"))
def test_reserved_retry_ignores_unrelated_spent_signature(residual_env, monkeypatch, crash):
    env = residual_env
    experiment_id = _published_experiment(env["engine"])
    req = _request(env, f"Read published experiment {experiment_id}.")
    valid_condition = "logistic_regression__mcar_0_30__b50__raw"
    arguments = [
        {"experiment_id": experiment_id},
        {"experiment_id": experiment_id},
        {"experiment_id": experiment_id, "condition_key": "missing"},
        {"experiment_id": experiment_id, "condition_key": valid_condition},
    ]
    provider = ScriptedProvider([
        _response(*[
            _call("read_experiment_results", params, f"call-{index + 1}")
            for index, params in enumerate(arguments)
        ]),
        _response(content=json.dumps({"template": "summary", "condition_refs": []})),
    ])
    entry = env["registry"]._tools["read_experiment_results"]
    real_handler = entry.handler
    handler_calls = []

    def handler(params, context, call_id):
        handler_calls.append(call_id)
        if call_id == "call-1":
            return ToolResult(
                tool_name="read_experiment_results",
                tool_call_id=call_id,
                status="error",
                error="REQUEST_FAILED: Temporary read failure.",
            )
        return real_handler(params, context, call_id)

    monkeypatch.setattr(entry, "handler", handler)
    real_dispatch = env["registry"].dispatch

    def crash_before_reserved_read(name, raw_arguments, ctx, tool_call_id):
        if tool_call_id == "call-4":
            raise SimulatedCrash()
        return real_dispatch(name, raw_arguments, ctx, tool_call_id)

    expected_ledger = {
        "read_experiment_results:REQUEST_FAILED:": 1,
        "read_experiment_results:EXPERIMENT_UNAVAILABLE:": 1,
    }
    if crash:
        monkeypatch.setattr(env["registry"], "dispatch", crash_before_reserved_read)
        with pytest.raises(SimulatedCrash):
            asyncio.run(_controller(env, provider).execute_request(req.id, "first-worker"))
        before = env["store"].get_request(req.id)
        pending = env["store"].list_tool_executions(req.id)
        assert before.call_count == 4 and before.pending_cursor == 3
        assert before.repair_count == 2 and before.repair_ledger == expected_ledger
        assert len(pending) == 4
        assert pending[3].ordinal == 4 and pending[3].tool_call_id == "call-4"
        assert pending[3].tool_name == "read_experiment_results"
        assert pending[3].arguments == arguments[3] and pending[3].status == "PENDING"
        assert handler_calls == ["call-1", "call-2", "call-3"]
        assert len(provider.history) == 1
        _expire_lease(env, req.id)
        monkeypatch.setattr(env["registry"], "dispatch", real_dispatch)
        done = asyncio.run(_controller(env, provider).execute_request(req.id, "recovery-worker"))
    else:
        done = asyncio.run(_controller(env, provider).execute_request(req.id, "first-worker"))

    traces = env["store"].list_tool_executions(req.id)
    assert handler_calls == ["call-1", "call-2", "call-3", "call-4"]
    assert [trace.status for trace in traces] == ["error", "success", "error", "success"]
    assert traces[3].result.get("error") is None
    assert traces[3].arguments == arguments[3]
    assert done.call_count == 4 and done.repair_count == 2
    assert done.repair_ledger == expected_ledger
    assert len(provider.history) == 2
    assert done.status == "FAILED"  # Earlier adverse traces remain truthful.
    assert _job_count(env) == 0
