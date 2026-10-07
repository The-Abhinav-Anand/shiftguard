"""Offline checks for the isolated live-acceptance harness and evidence contract."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from shiftguard.settings import Settings


ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = ROOT / "scripts" / "run_live_acceptance.py"
_spec = importlib.util.spec_from_file_location("shiftguard_live_acceptance_harness", HARNESS_PATH)
harness = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(harness)


def _trace(name, arguments, data, *, status="success", result_status="success", call_id="call-opaque-01", ordinal=1, job_id=None):
    return {
        "ordinal": ordinal,
        "tool_name": name,
        "tool_call_id": call_id,
        "arguments": arguments,
        "status": status,
        "job_id": job_id,
        "result": {"status": result_status, "data": data, "error_code": None},
    }


def _valid_evidence():
    rows = [{"path": "shiftguard/example.py", "sha256": "c" * 64}]
    source_sha = hashlib.sha256(harness._canonical_json(rows)).hexdigest()
    from shiftguard.agent.policy import APPROVED_CALIBRATORS
    from shiftguard.agent.rendering import ResultRenderer

    experiment_id = "1" * 24
    methods = sorted(APPROVED_CALIBRATORS)
    condition_ids = {method: f"{index:024x}" for index, method in enumerate(methods, 1)}
    raw_id = condition_ids["raw"]
    raw_metrics = {"brier_score": 0.19, "log_loss": 0.57}
    context = {
        "predictor_id": "p" * 64, "dataset_id": "d" * 64,
        "evaluation_rows_id": "e" * 64, "source_map_id": "s" * 64,
    }
    run_trace = _trace(
        "run_experiment", {"preset_name": "bank-stress"},
        {"experiment_id": experiment_id, "preset_name": "bank-stress", "master_seed": 31001},
        call_id="tool-run-01", job_id="job-1",
    )
    read_trace = _trace(
        "read_experiment_results",
        {"experiment_id": experiment_id, "condition_key": harness.EXPECTED_CONDITION_KEY},
        {
            "experiment_id": experiment_id,
            "condition_key": harness.EXPECTED_CONDITION_KEY,
            "condition_id": raw_id,
            "scenario": harness.EXPECTED_SCENARIO,
            "predictor": harness.EXPECTED_PREDICTOR,
            "budget": 50,
            "status": "scored",
            "metrics": raw_metrics,
        },
        call_id="tool-read-01",
    )
    compare_methods = {}
    for index, method in enumerate(methods, 1):
        brier = raw_metrics["brier_score"] if method == "raw" else 0.19 - 0.002 * index
        item = {
            **context,
            "condition_id": condition_ids[method],
            "comparison_qualified": True, "status": "scored",
            "scenario": harness.EXPECTED_SCENARIO, "budget": 50,
            "resolved_method": method,
            "brier_score": brier, "log_loss": 0.57 - 0.005 * index,
        }
        compare_methods[method] = item
    compare_trace = _trace(
        "compare_calibrators",
        {"experiment_id": experiment_id, "scenario": harness.EXPECTED_SCENARIO,
         "predictor": harness.EXPECTED_PREDICTOR, "budget": 50},
        {"experiment_id": experiment_id, "scenario": harness.EXPECTED_SCENARIO,
         "predictor": harness.EXPECTED_PREDICTOR, "budget": 50,
         "calibrator_comparisons": compare_methods},
        call_id="tool-compare-01",
    )
    read_claims = ResultRenderer.render_from_tool_results(
        harness._read_prompt(experiment_id), [read_trace], [experiment_id]
    )["claims"]
    compare_claims = ResultRenderer.render_from_tool_results(
        harness._compare_prompt(experiment_id), [compare_trace], [experiment_id]
    )["claims"]

    attempts = []
    usages = ((5, 3), (3, 2), (4, 4)) * 2
    for index, (prompt_tokens, completion_tokens) in enumerate(usages, 1):
        attempts.append({
            "attempt_no": index, "attempt_id": f"attempt-{index}",
            "status": "settled", "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "reserved_tokens": 100, "input_token_bound": 68,
            "output_token_bound": 32,
            "provider_request_id_sha256": hashlib.sha256(f"request-{index}".encode()).hexdigest(),
            "input_sha256": hashlib.sha256(f"input-{index}".encode()).hexdigest(),
        })
    snapshot = {
        "ledger_id": "live-fixture", "source_digest": source_sha,
        "max_calls": 10, "max_tokens": 50_000, "calls_used": 6,
        "tokens_committed": 42, "halted": False, "halt_reason": None,
        "attempts": attempts,
    }
    session_id = "session-fixture"
    request_ids = {"run": "req_" + "2" * 20, "read": "req_" + "3" * 20, "compare": "req_" + "4" * 20}
    stage_traces = {"run": [run_trace], "read": [read_trace], "compare": [compare_trace]}
    prompts = {
        "run": "Run bank-stress", "read": harness._read_prompt(experiment_id),
        "compare": harness._compare_prompt(experiment_id),
    }
    stages = {}
    for offset, stage in enumerate(("run", "read", "compare")):
        trace = stage_traces[stage]
        call_ids = [item["tool_call_id"] for item in trace]
        stages[stage] = {
            "status": "COMPLETED", "request_id": request_ids[stage],
            "session_id": session_id,
            "intent_key_sha256": hashlib.sha256(f"intent-{stage}".encode()).hexdigest(),
            "prompt": prompts[stage], "tool_trace": trace,
            "claims": [] if stage == "run" else (read_claims if stage == "read" else compare_claims),
            "evidence_refs": [] if stage == "run" else [experiment_id],
            "agent_call_count": 1, "agent_turn_count": 2,
            "provider_calls_before_stage": offset * 2,
            "provider_calls_after_stage": offset * 2 + 2,
            "provider_calls_before_replay": offset * 2 + 2,
            "provider_calls_after_replay": offset * 2 + 2,
            "idempotent_replay_zero_added_calls": True,
            "replay_request_id": request_ids[stage],
            "transcript_binding": {
                "request_id": request_ids[stage], "session_id": session_id,
                "database_status": "COMPLETED", "message_sha256": hashlib.sha256(stage.encode()).hexdigest(),
                "database_turn_count": 2, "database_call_count": 1,
                "provider_attempt_ids": [a["attempt_id"] for a in attempts[offset * 2:offset * 2 + 2]],
                "provider_input_sha256": [a["input_sha256"] for a in attempts[offset * 2:offset * 2 + 2]],
                "assistant_tool_call_ids": call_ids, "tool_response_call_ids": call_ids,
                "tool_call_ids": call_ids,
                "api_trace_sha256": hashlib.sha256(harness._canonical_json(trace)).hexdigest(),
                "executions": [{
                    "execution_id": f"execution-{stage}", "tool_call_id": call_ids[0],
                    "arguments_sha256": hashlib.sha256(harness._canonical_json(trace[0]["arguments"])).hexdigest(),
                    "result_sha256": hashlib.sha256(harness._canonical_json(trace[0]["result"])).hexdigest(),
                    "public_result_sha256": hashlib.sha256(harness._canonical_json(trace[0]["result"])).hexdigest(),
                    "ordinal": trace[0]["ordinal"], "tool_name": trace[0]["tool_name"],
                    "status": trace[0]["status"], "job_id": trace[0]["job_id"],
                }],
            },
        }
    run_stage = stages["run"]
    for stage in stages.values():
        stage["transcript_binding"]["renderer_name"] = "ResultRenderer.render_from_tool_results"
        stage["transcript_binding"]["renderer_claims_sha256"] = hashlib.sha256(
            harness._canonical_json(stage["claims"])
        ).hexdigest()
    run_stage.update({
        "preset": "bank-stress", "job_id": "job-1", "durable_wait_observed": True,
        "resume_events": [{
            "request_id": request_ids["run"], "job_id": "job-1",
            "job_status": "completed", "resume_status_code": 202,
            "provider_calls_before": 1, "provider_calls_after": 1,
        }],
    })
    condition_bindings = {
        "read": {
            "condition_key": harness.EXPECTED_CONDITION_KEY, "condition_id": raw_id,
            "status": "scored", "metrics": raw_metrics,
        },
        "compare": {},
    }
    for method, item in compare_methods.items():
        condition_bindings["compare"][method] = {
            "condition_key": f"{harness.EXPECTED_PREDICTOR}__{harness.EXPECTED_SCENARIO}__b50__{method}",
            "condition_id": item["condition_id"], "status": "scored",
            "metrics": {"brier_score": item["brier_score"], "log_loss": item["log_loss"]},
        }
    document = {
        "schema": harness.LIVE_EVIDENCE_SCHEMA,
        "status": "PASS",
        "source_binding": {"sha256": source_sha, "files": rows},
        "runtime": {
            "provider": "nebius", "model": harness.EXPECTED_MODEL,
            "database_major": 16, "loopback_only": True,
        },
        "ledger_id": "live-fixture",
        "budget": snapshot,
        "startup_budget": {"before": snapshot, "after": snapshot, "provider_calls_added": 0},
        "session_id": session_id,
        "durable_waits": [{"stage": "run", "request_id": request_ids["run"], "job_id": "job-1", "status": "WAITING_FOR_JOB"}],
        "requests": stages,
        "publication": {
            "experiment_id": experiment_id, "evaluation_tier": "development",
            "job_id": "job-1", "job_status": "completed",
            "master_seed": 31001, "condition_count": 400,
            "condition_bindings": condition_bindings,
        },
    }
    document["provider_accounting"] = harness._provider_accounting(document)
    return document


def test_cli_requires_explicit_live_and_enforces_ten_call_hard_ceiling():
    parser = harness._parser()
    live = parser.parse_args(["--live", "--max-calls", "10"])
    harness._validate_live_args(live)
    assert live.max_tokens == 50000
    with pytest.raises(harness.HarnessFailure, match="AT_MOST_10"):
        harness._validate_live_args(parser.parse_args(["--live", "--max-calls", "11"]))
    with pytest.raises(harness.HarnessFailure, match="50000"):
        harness._validate_live_args(parser.parse_args(["--live", "--max-calls", "10", "--max-tokens", "50001"]))


def test_acceptance_evidence_requires_actual_tools_durable_resume_and_qualified_metrics():
    evidence = _valid_evidence()
    checks = harness.validate_evidence_document(evidence)
    assert "model_bounded_published_read" in checks
    assert "model_qualified_comparison_and_claim_binding" in checks
    assert "idempotent_replay_zero_added_calls" in checks

    evidence["requests"]["compare"]["tool_trace"][0]["result"]["data"]["calibrator_comparisons"]["source_temperature"]["comparison_qualified"] = False
    evidence["requests"]["compare"]["transcript_binding"]["api_trace_sha256"] = hashlib.sha256(
        harness._canonical_json(evidence["requests"]["compare"]["tool_trace"])
    ).hexdigest()
    with pytest.raises(harness.HarnessFailure, match="MODEL_COMPARISON_NOT_QUALIFIED|PUBLIC_TRACE_EXECUTION|FINAL_CLAIMS"):
        harness.validate_evidence_document(evidence)


def test_pass_validation_checks_the_final_document_and_all_eight_rendered_methods():
    evidence = _valid_evidence()
    checks = harness.validate_evidence_document(evidence)
    assert "startup_budget_unchanged" in checks
    assert "published_condition_ids_and_metrics_bound" in checks
    assert evidence["budget"]["calls_used"] == 6  # Restarted settled ledger is valid.

    evidence["status"] = "RUNNING"
    evidence["requests"]["run"].pop("preset")
    assert harness.validate_evidence_document(evidence)
    evidence["status"] = "PASS"
    with pytest.raises(harness.HarnessFailure, match="FLAGSHIP_RUN_NOT_COMPLETED"):
        harness.validate_evidence_document(evidence)


def test_pass_requires_exact_method_grid_transcript_ids_and_unhalted_final_snapshot():
    evidence = _valid_evidence()
    evidence["requests"]["compare"]["transcript_binding"]["assistant_tool_call_ids"] = []
    with pytest.raises(harness.HarnessFailure, match="PERSISTED_TRANSCRIPT_BINDING_INVALID"):
        harness.validate_evidence_document(evidence)

    evidence = _valid_evidence()
    del evidence["requests"]["compare"]["tool_trace"][0]["tool_call_id"]
    with pytest.raises(harness.HarnessFailure, match="PERSISTED_TRANSCRIPT_BINDING_INVALID"):
        harness.validate_evidence_document(evidence)

    evidence = _valid_evidence()
    evidence["budget"]["halted"] = True
    evidence["budget"]["halt_reason"] = "timeout"
    with pytest.raises(harness.HarnessFailure, match="BUDGET_LEDGER_HALTED"):
        harness.validate_evidence_document(evidence)


def test_startup_delta_compares_existing_settled_ledger_and_rejects_unresolved_change():
    evidence = _valid_evidence()
    evidence["startup_budget"]["before"] = {**evidence["startup_budget"]["before"], "calls_used": 2}
    with pytest.raises(harness.HarnessFailure, match="STARTUP_BUDGET_DELTA_INVALID"):
        harness.validate_evidence_document(evidence)


def test_harness_source_binding_includes_locked_bank_inputs():
    files = {row["path"] for row in harness.source_manifest()["files"]}
    assert "configs/bank-stress.yaml" in files
    assert "data/manifests/bank.json" in files


def test_poll_persists_wait_resume_and_uses_lowercase_job_terminal_status(monkeypatch, tmp_path):
    statuses = iter([
        {"status": "WAITING_FOR_JOB", "active_job_id": "job-lower", "resume_nonce": "one-use"},
        {"status": "WAITING_FOR_JOB", "active_job_id": "job-lower", "resume_nonce": "one-use"},
        {"status": "COMPLETED", "request_id": "5" * 24, "session_id": "session-fixture",
         "prompt": "Run bank-stress", "tool_trace": [], "evidence_refs": [], "call_count": 1},
    ])

    class _HttpResponse:
        status_code = 202

        @staticmethod
        def json():
            return {"status": "RUNNING"}

    class _Client:
        def get(self, path, **_kwargs):
            if path.startswith("/api/v1/jobs/"):
                return SimpleNamespace(status_code=200, json=lambda: {"status": "completed"})
            return SimpleNamespace(status_code=200, json=lambda: next(statuses))

        def post(self, *_args, **_kwargs):
            return _HttpResponse()

    class _Budget:
        @staticmethod
        def snapshot():
            return {"calls_used": 1}

    monkeypatch.setattr(harness, "_persisted_stage_binding", lambda *_a, **_kw: {
        "request_id": "5" * 24, "session_id": "session-fixture", "database_status": "COMPLETED",
        "message_sha256": "a" * 64, "assistant_tool_call_ids": [],
        "tool_response_call_ids": [], "tool_call_ids": [],
        "api_trace_sha256": hashlib.sha256(harness._canonical_json([])).hexdigest(),
        "executions": [],
    })
    state = {"session_id": "session-fixture", "stage_evidence": {}, "durable_waits": []}
    evidence = {"requests": {"run": {"prompt": "Run bank-stress"}}, "durable_waits": []}
    harness._poll_request(
        _Client(), request_id="5" * 24, headers={}, timeout_seconds=60,
        evidence=evidence, stage="run", state=state, state_path=tmp_path / "state.json",
        budget=_Budget(), engine=None, prompt="Run bank-stress", session_id="session-fixture",
    )
    item = evidence["requests"]["run"]
    assert item["durable_wait_observed"] is True
    assert item["job_id"] == "job-lower"
    assert item["resume_events"][0]["job_status"] == "completed"
    assert item["resume_events"][0]["resume_status_code"] == 202
    assert state["durable_waits"][0]["request_id"] == "5" * 24


def test_evidence_rejects_capabilities_and_unredacted_provider_fields():
    evidence = _valid_evidence()
    evidence["runtime"]["capability_token"] = "must-not-be-saved"
    with pytest.raises(harness.HarnessFailure, match="SENSITIVE_FIELD"):
        harness.validate_evidence_document(evidence)


def test_evidence_sidecar_inspection_is_offline(tmp_path):
    evidence = _valid_evidence()
    path = tmp_path / "attempt.json"
    harness._write_json(path, evidence)
    inspected = harness._inspect_evidence(path, require_current_source=False)
    assert inspected["status"] == "PASS"
    assert inspected["calls_used"] == 6
    assert "aggregate_budget" in inspected["checks"]


def test_failed_attempt_without_initialized_ledger_remains_inspectable_offline(tmp_path):
    rows = [{"path": "scripts/run_live_acceptance.py", "sha256": "d" * 64}]
    evidence = {
        "schema": harness.LIVE_EVIDENCE_SCHEMA, "status": "FAIL",
        "source_binding": {"sha256": hashlib.sha256(harness._canonical_json(rows)).hexdigest(), "files": rows},
        "runtime": {}, "budget": {}, "requests": {}, "ledger_id": "live-not-started",
    }
    path = tmp_path / "failed-before-start.json"
    harness._write_json(path, evidence)
    inspected = harness._inspect_evidence(path, require_current_source=False)
    assert inspected["status"] == "FAIL"
    assert "ledger_not_initialized" in inspected["checks"]


def test_offline_cli_budget_check_never_calls_a_provider(capsys):
    assert harness.main(["--offline-check"]) == 0
    assert json.loads(capsys.readouterr().out) == {"offline_budget_guard": "PASS", "provider_calls": 0}


def test_actual_app_startup_is_invocation_scoped_and_makes_zero_provider_calls(tmp_path, monkeypatch):
    monkeypatch.delenv("SHIFTGUARD_LIVE_ACCEPTANCE_LEDGER", raising=False)
    calls = []

    async def fake_completion(**_kwargs):
        calls.append("dispatch")
        raise AssertionError("startup must not dispatch a provider request")

    class QuietClient:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=fake_completion))

        async def close(self):
            return None

    monkeypatch.setattr("shiftguard.agent.provider.AsyncOpenAI", QuietClient)
    from shiftguard.api.main import create_app

    settings = Settings(
        _env_file=None,
        db_url=f"sqlite:///{(tmp_path / 'isolated-app.sqlite').as_posix()}",
        environment="local",
        artifact_root=tmp_path / "artifacts",
        embedded_worker=False,
        nebius_api_key="offline-dummy-key-123456789",
        agent_enabled=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        status = client.get("/api/v1/agent/status").json()
        assert status["enabled"] is True and status["available"] is True
        assert app.state.agent_provider.attempt_budget is None
    assert calls == []


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_submit_then_poll_projects_actual_request_and_tool_transcript(tmp_path, monkeypatch, backend):
    monkeypatch.delenv("SHIFTGUARD_LIVE_ACCEPTANCE_LEDGER", raising=False)
    sdk_calls = []

    async def fake_completion(**kwargs):
        sdk_calls.append(kwargs)
        messages = kwargs["messages"]
        if any(item.get("role") == "tool" for item in messages):
            message = SimpleNamespace(content='{"template":"summary","condition_refs":[]}', tool_calls=None)
            finish_reason = "stop"
        else:
            message = SimpleNamespace(content=None, tool_calls=[SimpleNamespace(
                id="offline-tool-call-01", type="function",
                function=SimpleNamespace(name="list_available_scenarios", arguments='{"dataset_id":"bank"}'),
            )])
            finish_reason = "tool_calls"
        return SimpleNamespace(
            id=f"offline-provider-request-{len(sdk_calls)}",
            model=harness.EXPECTED_MODEL,
            choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=5, total_tokens=13),
        )

    class _Sdk:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=fake_completion))

        async def close(self):
            return None

    monkeypatch.setattr("shiftguard.agent.provider.AsyncOpenAI", _Sdk)
    from shiftguard.api.main import create_app

    cleanup = None
    if backend == "sqlite":
        settings = Settings(
            _env_file=None,
            db_url=f"sqlite:///{(tmp_path / 'actual-submit-poll.sqlite').as_posix()}",
            environment="local", artifact_root=tmp_path / "artifacts",
            embedded_worker=False, nebius_api_key="offline-dummy-provider-key-92751",
            nebius_max_output_tokens=32, agent_enabled=True,
        )
    else:
        raw_url = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
        if not raw_url:
            pytest.skip("SHIFTGUARD_TEST_POSTGRES_URL is not set by the existing PostgreSQL helper")
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url

        admin_url = make_url(raw_url)
        if admin_url.database != "shiftguard_gate3" or admin_url.port != 15432:
            pytest.fail("PostgreSQL helper target differs from the authorized test host/database")
        admin_url = admin_url.set(drivername="postgresql+psycopg", query={k: v for k, v in admin_url.query.items() if k != "options"})
        schema = "sg_luna_g67_app_" + uuid4().hex[:12]
        admin_engine = create_engine(admin_url, pool_pre_ping=True)
        with admin_engine.begin() as connection:
            version = int(connection.execute(text("SELECT current_setting('server_version_num')::integer")).scalar_one())
            database = connection.execute(text("SELECT current_database()")).scalar_one()
            assert version // 10000 == 16 and database == "shiftguard_gate3"
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        scoped = admin_url.set(query={**dict(admin_url.query), "options": f"-csearch_path={schema}"})
        settings = Settings(
            _env_file=None, db_url=scoped.render_as_string(hide_password=False),
            environment="hosted", artifact_root=tmp_path / "artifacts",
            embedded_worker=False, nebius_api_key="offline-dummy-provider-key-92751",
            nebius_max_output_tokens=32, agent_enabled=True,
        )
        cleanup = (admin_engine, schema)
    app = create_app(settings)

    class _Budget:
        @staticmethod
        def snapshot():
            return {"calls_used": len(sdk_calls)}

    try:
        with TestClient(app) as client:
            created = client.post("/api/v1/agent/sessions", json={}).json()
            headers = {
                "X-Session-ID": created["session_id"],
                "X-Session-Token": created["capability_token"],
            }
            state = {
                "version": 2, "schema": "sg_live_acceptance_fixture", "ledger_id": "offline",
                "source_sha256": "a" * 64, "max_calls": 2, "max_tokens": 50000,
                "session_id": created["session_id"], "requests": {}, "stage_evidence": {},
                "durable_waits": [],
            }
            evidence = {"requests": {}, "durable_waits": []}
            result = harness._submit_stage(
                client, state=state, state_path=tmp_path / "actual-state.json", evidence=evidence,
                stage="read", prompt="Show the development scenarios", headers=headers,
                budget=_Budget(), engine=app.state.engine, timeout_seconds=60,
            )
            assert result["status"] == "COMPLETED"
            assert evidence["requests"]["read"]["transcript_binding"]["database_status"] == "COMPLETED"
            assert evidence["requests"]["read"]["transcript_binding"]["tool_call_ids"] == ["offline-tool-call-01"]
            assert evidence["requests"]["read"]["tool_trace"][0]["tool_name"] == "list_available_scenarios"
            assert len(sdk_calls) == 2
    finally:
        if cleanup:
            admin_engine, schema = cleanup
            with admin_engine.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            admin_engine.dispose()


def test_explicit_run_grant_and_bounded_evidence_prompts_are_distinct():
    from shiftguard.agent.execution_authority import authorized_execution_presets

    assert authorized_execution_presets("Run bank-stress") == frozenset({"bank-stress"})
    experiment_id = "a" * 24
    read_prompt = harness._read_prompt(experiment_id)
    compare_prompt = harness._compare_prompt(experiment_id)
    assert authorized_execution_presets(read_prompt) == frozenset()
    assert authorized_execution_presets(compare_prompt) == frozenset()
    assert read_prompt.endswith(f"condition {harness.EXPECTED_CONDITION_KEY}")
    assert compare_prompt.endswith("predictor logistic_regression scenario history_block_0_50 budget 50")


def test_bank_stress_suite_tool_is_accepted_as_flagship_run():
    assert harness._is_flagship_run_tool({
        "tool_name": "run_stress_suite", "arguments": {"suite_name": "flagship-stress"},
        "status": "success", "job_id": "job-1",
    })
    assert not harness._is_flagship_run_tool({
        "tool_name": "run_stress_suite", "arguments": {"suite_name": "bank-stress-30"},
        "status": "success", "job_id": "job-1",
    })


def test_submit_stage_records_successful_idempotent_replay_without_provider(monkeypatch, tmp_path):
    class _Response:
        status_code = 202

        @staticmethod
        def json():
            return {"request_id": "request-1", "status": "RUNNING"}

    class _Client:
        def __init__(self):
            self.posts = 0
            self.evidence = None

        def post(self, *_args, **_kwargs):
            self.posts += 1
            if self.posts == 1:
                assert self.evidence["requests"].get("read") is not None
            return _Response()

    class _Budget:
        @staticmethod
        def snapshot():
            return {"calls_used": 2}

    def _complete(_client, *, evidence, stage, **_kwargs):
        evidence["requests"][stage] = {"status": "COMPLETED"}
        return {"status": "COMPLETED"}

    monkeypatch.setattr(harness, "_poll_request", _complete)
    client = _Client()
    state = {"requests": {}, "session_id": "session-fixture", "stage_evidence": {}, "durable_waits": []}
    evidence = {"requests": {}}
    client.evidence = evidence
    prompt = "Read experiment " + "a" * 24 + " condition " + harness.EXPECTED_CONDITION_KEY
    harness._submit_stage(
        client, state=state, state_path=tmp_path / "state.json", evidence=evidence,
        stage="read", prompt=prompt, headers={}, budget=_Budget(), timeout_seconds=60,
        engine=None,
    )
    assert client.posts == 2
    assert evidence["requests"]["read"]["idempotent_replay_zero_added_calls"] is True
    assert evidence["requests"]["read"]["provider_calls_before_replay"] == evidence["requests"]["read"]["provider_calls_after_replay"] == 2
    assert evidence["requests"]["read"]["prompt"] == prompt
