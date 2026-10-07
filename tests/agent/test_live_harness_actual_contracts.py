"""Offline R01–R05 integration using the normal API and immutable historical results.

Only SDK completion is stubbed. The controller, registry, result tools, store,
renderer and job completion/cancellation contracts are the actual application.
No scientific scoring or remote provider request is performed.
"""

import copy
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from shiftguard.agent.budget import AttemptBudget, LIVE_BUDGET_ENV
from shiftguard.agent.provider import AgentProvider
from shiftguard.agent.store import AgentStore
from shiftguard.api.main import create_app
from shiftguard.jobs.queue import JobQueue
from shiftguard.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("live_harness_actual_contracts", ROOT / "scripts" / "run_live_acceptance.py")
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)


DUMMY_KEY = "luna-r02-offline-dummy-key-783962"
EXPERIMENT_ID = "d8a18a371c8c88ee20ba1087"
ARTIFACT_HASHES = {
    "config.json": "44e05eb19e809234dfd4f82551c2e096a3175108effcf63560c5ef34014d01f1",
    "conditions.json": "5a9cb7ecc6f3fa00093dbb30963dc70051bf1fc157d8b74347ffbc402bf9a82f",
}


@pytest.fixture(params=["sqlite", "postgresql"])
def actual_api(request, tmp_path, monkeypatch):
    monkeypatch.delenv(LIVE_BUDGET_ENV, raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", DUMMY_KEY)
    backend = request.param
    schema = "sg_live_acceptance_lunar02_" + uuid4().hex[:12]
    admin = None
    if backend == "sqlite":
        url = make_url("sqlite:///" + (tmp_path / "actual.sqlite").as_posix())
    else:
        raw = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
        if not raw:
            pytest.skip("Existing PostgreSQL16 helper URL is not set")
        admin_url = h._test_database_url(raw)
        h._prepare_schema(admin_url, schema, create=True)
        admin = create_engine(admin_url)
        url = h._scoped_url(admin_url, schema)
    engine = create_engine(url)
    source = h.source_manifest()
    budget = AttemptBudget(engine, ledger_id="luna-r02", source_digest=source["sha256"], max_calls=10, max_tokens=50000)
    if backend == "postgresql":
        monkeypatch.setenv(LIVE_BUDGET_ENV, json.dumps({
            "ledger_id": budget.ledger_id, "source_digest": source["sha256"],
            "max_calls": 10, "max_tokens": 50000,
        }))
    artifact = ROOT / "var" / "artifacts" / EXPERIMENT_ID
    payload = {}
    for filename, expected in ARTIFACT_HASHES.items():
        raw_bytes = (artifact / filename).read_bytes()
        assert hashlib.sha256(raw_bytes).hexdigest() == expected
        payload[filename.removesuffix(".json")] = json.loads(raw_bytes)
    assert len(payload["conditions"]) == 400
    assert payload["config"]["master_seed"] == 31001
    assert payload["config"]["evaluation_tier"] == "development"
    calls = []

    async def completion(_sdk, **kwargs):
        # This patch is confined to this offline test fixture. No scripted
        # provider object replaces the normal AgentProvider in the application.
        calls.append(kwargs["messages"][-1]["role"])
        prompt = next(m["content"] for m in kwargs["messages"] if m["role"] == "user")
        if any(m["role"] == "tool" for m in kwargs["messages"]):
            message = SimpleNamespace(content='{"template":"summary","condition_refs":[]}', tool_calls=None)
            finish = "stop"
        else:
            if prompt == "Run bank-stress":
                name, args = "run_experiment", {"preset_name": "bank-stress"}
            elif prompt.startswith("Read experiment "):
                name, args = "read_experiment_results", {
                    "experiment_id": prompt.split()[2], "condition_key": h.EXPECTED_CONDITION_KEY,
                }
            elif prompt.startswith("Compare experiment "):
                name, args = "compare_calibrators", {
                    "experiment_id": prompt.split()[2], "predictor": h.EXPECTED_PREDICTOR,
                    "scenario": h.EXPECTED_SCENARIO, "budget": 50,
                }
            else:
                name, args = "execute_python", {"code": "print(1)"}
            message = SimpleNamespace(content=None, tool_calls=[SimpleNamespace(
                id="luna-original-" + name, type="function",
                function=SimpleNamespace(name=name, arguments=json.dumps(args)),
            )])
            finish = "tool_calls"
        return SimpleNamespace(
            id=DUMMY_KEY, model=h.EXPECTED_MODEL,
            choices=[SimpleNamespace(message=message, finish_reason=finish)],
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=5, total_tokens=13),
        )

    monkeypatch.setattr("openai.resources.chat.completions.AsyncCompletions.create", completion)
    settings = Settings(
        _env_file=None, db_url=url.render_as_string(hide_password=False),
        environment="hosted" if backend == "postgresql" else "local",
        artifact_root=tmp_path / "artifacts", embedded_worker=False,
        agent_enabled=True, nebius_api_key=DUMMY_KEY, nebius_max_output_tokens=1024,
    )
    app = create_app(settings)
    boundary = {"submit_http_status": None, "generic_500": False}

    @app.middleware("http")
    async def terminal_http_boundary(request, call_next):
        submitting = request.method == "POST" and request.url.path == "/api/v1/agent/requests"
        if submitting and boundary["generic_500"]:
            return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_FAILURE"}})
        response = await call_next(request)
        if submitting and boundary["submit_http_status"] is not None:
            # Test only the transport status variant; the entire terminal body
            # is produced by the actual POST route/controller/store.
            response.status_code = boundary["submit_http_status"]
        return response
    try:
        with TestClient(app) as real:
            assert type(app.state.agent_provider) is AgentProvider and not app.state.test_harness
            if backend == "sqlite":
                app.state.agent_provider.attempt_budget = budget  # Offline SQLite test only.
            assert budget.snapshot()["calls_used"] == 0
            created = real.post("/api/v1/agent/sessions", json={}).json()
            headers = {"X-Session-ID": created["session_id"], "X-Session-Token": created["capability_token"]}
            env = SimpleNamespace(
                real=real, app=app, budget=budget, payload=payload, headers=headers, calls=calls,
                tmp=tmp_path, backend=backend, job_outcome="completed",
                boundary=boundary,
                state={"version": 2, "schema": schema, "ledger_id": budget.ledger_id,
                       "source_sha256": source["sha256"], "max_calls": 10, "max_tokens": 50000,
                       "session_id": created["session_id"], "requests": {}, "stage_evidence": {}, "durable_waits": []},
            )

            class Client:
                def post(self, *args, **kwargs):
                    return real.post(*args, **kwargs)

                def get(self, path, **kwargs):
                    if "/jobs/" in path:
                        queue = JobQueue(app.state.engine)
                        job = queue.get_job(path.rsplit("/", 1)[1])
                        if job.status.value == "queued":
                            if env.job_outcome == "cancelled":
                                assert queue.request_cancellation(job.id, created["session_id"]) == (True, "cancelled")
                            else:
                                claimed = queue.claim_next_job(worker_id="offline-historical-fixture")
                                if env.job_outcome == "failed":
                                    assert queue.mark_failed(job.id, claimed.fencing_token,
                                        {"code": "OFFLINE_JOB_FAILURE", "message": "Offline failure fixture."}, retryable=False)
                                else:
                                    publish_historical(env, job.id)
                                    assert queue.mark_completed(job.id, claimed.fencing_token, EXPERIMENT_ID,
                                                                {"experiment_id": EXPERIMENT_ID})
                    return real.get(path, **kwargs)

            env.client = Client()
            yield env
    finally:
        engine.dispose()
        if admin is not None:
            with admin.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            admin.dispose()
        for filename, expected in ARTIFACT_HASHES.items():
            assert hashlib.sha256((artifact / filename).read_bytes()).hexdigest() == expected


def publish_historical(env, job_id):
    """Copy immutable development evidence into the isolated test schema only."""
    execution, generation = str(uuid4()), str(uuid4())
    now = "2026-10-07T00:00:00+00:00"
    with env.app.state.engine.begin() as connection:
        connection.execute(text("INSERT INTO experiments (id,payload_json,content_hashes_json) VALUES (:id,:payload,'{}')"),
                           {"id": EXPERIMENT_ID, "payload": json.dumps(env.payload)})
        connection.execute(text("INSERT INTO experiment_executions (execution_id,experiment_id,audit_json) VALUES (:execution,:id,'{}')"),
                           {"execution": execution, "id": EXPERIMENT_ID})
        connection.execute(text("""INSERT INTO experiment_publications
            (generation_id,experiment_id,full_digest,execution_id,status,manifest_json,created_at,updated_at,job_id)
            VALUES (:generation,:id,:digest,:execution,'PUBLISHED','{}',:now,:now,:job)"""),
                           {"generation": generation, "id": EXPERIMENT_ID, "digest": "a" * 64,
                            "execution": execution, "now": now, "job": job_id})


def submit(env, stage, prompt, *, state=None, evidence=None, client=None, path=None):
    state = env.state if state is None else state
    if evidence is None:
        evidence = {"requests": copy.deepcopy(state["stage_evidence"]),
                    "durable_waits": copy.deepcopy(state["durable_waits"])}
    result = h._submit_stage(
        client or env.client, state=state, state_path=path or env.tmp / "state.json", evidence=evidence,
        stage=stage, prompt=prompt, headers=env.headers, budget=env.budget,
        engine=env.app.state.engine, timeout_seconds=30,
    )
    return result, evidence


def generated_document(env):
    initial = env.budget.snapshot()
    doc = {
        "classification": "OFFLINE_API_CONTRACT_FIXTURE", "schema": h.LIVE_EVIDENCE_SCHEMA,
        "status": "RUNNING", "source_binding": h.source_manifest(),
        "runtime": {"provider": "nebius", "model": h.EXPECTED_MODEL, "database_major": 16,
                    "actual_test_backend": env.backend, "loopback_only": True},
        "ledger_id": env.budget.ledger_id, "session_id": env.state["session_id"],
        "requests": {}, "durable_waits": [],
        "startup_budget": {"before": initial, "after": copy.deepcopy(initial), "provider_calls_added": 0},
    }
    for stage, prompt in (("run", "Run bank-stress"), ("read", h._read_prompt(EXPERIMENT_ID)),
                          ("compare", h._compare_prompt(EXPERIMENT_ID))):
        response, doc = submit(env, stage, prompt, evidence=doc)
        assert response["status"] == "COMPLETED"
        assert re.fullmatch(r"req_[a-f0-9]{20}", response["request_id"])
    run = doc["requests"]["run"]
    run["preset"] = h.EXPECTED_PRESET
    env.state["stage_evidence"]["run"] = copy.deepcopy(run)
    h._save_state(env.tmp / "state.json", env.state)
    job = env.real.get("/api/v1/jobs/" + run["job_id"], headers=env.headers).json()
    payload, publication = h._published_experiment(env.app.state.engine, job["experiment_id"])
    doc["publication"] = {
        "experiment_id": job["experiment_id"], "job_id": job["job_id"], "job_status": job["status"],
        "status": publication["status"], "master_seed": payload["config"]["master_seed"],
        "evaluation_tier": payload["config"]["evaluation_tier"], "condition_count": len(payload["conditions"]),
    }
    h._bind_results_to_publication(doc, payload["conditions"], EXPERIMENT_ID)
    doc["budget"] = env.budget.snapshot()
    return h._pass_candidate(doc)


def test_actual_six_dispatch_workflow_saved_pass_and_independent_inspection(actual_api):
    env = actual_api
    doc = generated_document(env)
    assert doc["budget"]["calls_used"] == len(env.calls) == 6
    assert len(doc["requests"]["compare"]["claims"]) == 8
    assert all(claim["comparison_qualified"] for claim in doc["requests"]["compare"]["claims"])
    assert [(s["provider_calls_before_stage"], s["provider_calls_after_stage"])
            for s in doc["requests"].values()] == [(0, 2), (2, 4), (4, 6)]
    run = doc["requests"]["run"]
    assert run["durable_wait_observed"] and run["resume_events"][0]["job_status"] == "completed"
    result = run["tool_trace"][0]["result"]
    assert set(result) == {"status", "job_id", "experiment_id", "message"}
    assert result["experiment_id"] == EXPERIMENT_ID and result["job_id"] == run["job_id"]
    path = env.tmp / "generated-offline-pass.json"
    h._write_json(path, doc)
    assert h._inspect_evidence(path, require_current_source=True)["status"] == "PASS"
    assert DUMMY_KEY not in path.read_text()
    assert h.main(["--validate-evidence", str(path)]) == 0


def test_actual_projection_preserves_absent_null_empty_and_rejects_result_tampering(actual_api):
    env = actual_api
    response, evidence = submit(env, "run", "Run bank-stress")
    projected = h._public_tool_trace(response)
    assert "data" not in projected[0]["result"]
    for value in (None, {}):
        changed = copy.deepcopy(response)
        changed["tool_trace"][0]["result"]["data"] = value
        public_trace = h._public_tool_trace(changed)
        assert "data" in public_trace[0]["result"] and public_trace[0]["result"]["data"] == value
        with pytest.raises(h.HarnessFailure, match="API_TRACE_DIFFERS"):
            h._persisted_stage_binding(env.app.state.engine, changed, request_id=response["request_id"],
                prompt="Run bank-stress", session_id=env.state["session_id"], public_trace=public_trace)
    changed = copy.deepcopy(response)
    changed["tool_trace"][0]["result"]["experiment_id"] = "f" * 24
    with pytest.raises(h.HarnessFailure, match="API_TRACE_DIFFERS"):
        h._persisted_stage_binding(env.app.state.engine, changed, request_id=response["request_id"],
            prompt="Run bank-stress", session_id=env.state["session_id"], public_trace=h._public_tool_trace(changed))


@pytest.mark.parametrize("job_outcome,terminal", [("failed", "FAILED"), ("cancelled", "CANCELLED")])
def test_actual_adverse_terminal_is_bound_and_saved_before_failure(actual_api, job_outcome, terminal):
    env = actual_api
    env.job_outcome = job_outcome
    evidence = {"requests": {}, "durable_waits": []}
    with pytest.raises(h.HarnessFailure, match="AGENT_RESUME_FAILED|AGENT_REQUEST_DID_NOT_COMPLETE"):
        submit(env, "run", "Run bank-stress", evidence=evidence)
    saved = h._load_state(env.tmp / "state.json")
    stage = saved["stage_evidence"]["run"]
    actual = AgentStore(env.app.state.engine).get_request(stage["request_id"])
    assert actual.status == stage["status"] == stage["transcript_binding"]["database_status"] == terminal
    assert saved["requests"]["run"]["status"] == terminal
    executions = AgentStore(env.app.state.engine).list_tool_executions(actual.id)
    assert actual.active_job_id is None  # Normal terminal finalization clears it.
    assert stage["job_id"] == executions[0].job_id
    assert stage["tool_trace"][0]["job_id"] == stage["job_id"]
    assert stage["resume_events"][0]["job_status"] == job_outcome
    assert stage["provider_calls_after_stage"] == len(env.calls)


@pytest.mark.parametrize("http_status", [200, 500])
def test_actual_immediate_failed_submit_binds_and_saves_valid_terminal_envelope(actual_api, http_status):
    env = actual_api
    env.boundary["submit_http_status"] = http_status
    evidence = {"requests": {}, "durable_waits": []}
    with pytest.raises(h.HarnessFailure, match="AGENT_REQUEST_DID_NOT_COMPLETE"):
        submit(env, "read", "Unsupported operation", evidence=evidence)
    saved = h._load_state(env.tmp / "state.json")
    stage = saved["stage_evidence"]["read"]
    actual = AgentStore(env.app.state.engine).get_request(stage["request_id"])
    assert re.fullmatch(r"req_[a-f0-9]{20}", actual.id)
    assert actual.status == stage["status"] == stage["transcript_binding"]["database_status"] == "FAILED"
    assert stage["submit_http_status"] == saved["requests"]["read"]["submit_http_status"] == http_status
    assert stage["provider_calls_after_stage"] == env.budget.snapshot()["calls_used"] == len(env.calls)
    assert stage["provider_calls_after_stage"] > 0


def test_generic_500_without_identity_is_sanitized_and_creates_no_harness_request(actual_api):
    env = actual_api
    env.boundary["generic_500"] = True
    with pytest.raises(h.HarnessFailure, match="HTTP_STATUS_500"):
        submit(env, "read", "Unsupported operation")
    saved = h._load_state(env.tmp / "state.json")
    assert saved["requests"]["read"]["request_id"] is None
    assert "read" not in saved["stage_evidence"]
    assert len(env.calls) == env.budget.snapshot()["calls_used"] == 0


def test_actual_accepted_post_loss_and_later_calls_keep_original_interval(actual_api):
    env = actual_api
    _, evidence = submit(env, "run", "Run bank-stress")
    before = env.budget.snapshot()["calls_used"]
    accepted_ids = []

    class LostResponse:
        def post(self, *args, **kwargs):
            response = env.real.post(*args, **kwargs)
            assert response.json()["status"] == "COMPLETED"
            accepted_ids.append(response.json()["request_id"])
            raise httpx.ReadTimeout("Offline accepted POST response loss")

        def get(self, *args, **kwargs):
            return env.real.get(*args, **kwargs)

    with pytest.raises(httpx.ReadTimeout):
        submit(env, "read", h._read_prompt(EXPERIMENT_ID), client=LostResponse())
    saved = h._load_state(env.tmp / "state.json")
    original = saved["requests"]["read"]
    assert original["request_id"] is None and original["calls_before_submit"] == before
    assert original["provider_calls_before_stage"] == before
    # A later genuine API comparison increases the lifetime ledger to six.
    _, evidence = submit(env, "compare", h._compare_prompt(EXPERIMENT_ID), state=saved)
    response, recovered = submit(env, "read", h._read_prompt(EXPERIMENT_ID), state=saved)
    stage = recovered["requests"]["read"]
    assert response["status"] == "COMPLETED" and len(env.calls) == 6
    assert response["request_id"] == accepted_ids[0]
    assert (stage["provider_calls_before_stage"], stage["provider_calls_after_stage"]) == (2, 4)
    assert stage["provider_calls_before_replay"] == stage["provider_calls_after_replay"] == 6
    assert saved["requests"]["read"]["calls_before_submit"] == before


def test_completed_reopen_preserves_original_interval_and_observes_replay_separately(actual_api):
    env = actual_api
    doc = generated_document(env)
    state = h._load_state(env.tmp / "state.json")
    for stage, prompt in (("run", "Run bank-stress"), ("read", h._read_prompt(EXPERIMENT_ID))):
        original = copy.deepcopy(doc["requests"][stage])
        response, reopened = submit(env, stage, prompt, state=state)
        item = reopened["requests"][stage]
        assert response["status"] == "COMPLETED" and len(env.calls) == 6
        for field in ("provider_calls_before_stage", "provider_calls_after_stage", "request_id", "session_id",
                      "job_id", "durable_wait_observed", "resume_events", "tool_trace", "transcript_binding", "claims"):
            assert item[field] == original[field]
        assert item["provider_calls_before_replay"] == item["provider_calls_after_replay"] == 6
        doc["requests"][stage] = item
    assert h.validate_evidence_document(doc)


def test_five_semantic_counterexamples_reject_with_refreshed_checksums(actual_api):
    doc = generated_document(actual_api)
    for mutation in ("zero_calls", "wrong_replay", "wrong_execution_hash", "wrong_session", "extra_claim"):
        changed = copy.deepcopy(doc)
        stage = changed["requests"]["read"]
        if mutation == "zero_calls":
            changed["budget"].update(calls_used=0, tokens_committed=0, attempts=[])
        elif mutation == "wrong_replay":
            stage.update(provider_calls_before_replay=99, provider_calls_after_replay=99)
        elif mutation == "wrong_execution_hash":
            stage["transcript_binding"]["executions"][0]["arguments_sha256"] = "f" * 64
        elif mutation == "wrong_session":
            stage["session_id"] = stage["transcript_binding"]["session_id"] = "unrelated-session"
        else:
            stage = changed["requests"]["compare"]
            stage["claims"].append({"claim_type": "metric_observation", "experiment_id": "f" * 24, "value": 0.0123456789})
        stage["transcript_binding"]["renderer_claims_sha256"] = hashlib.sha256(h._canonical_json(stage["claims"])).hexdigest()
        with pytest.raises(h.HarnessFailure):
            h.validate_evidence_document(changed)


def test_interval_coherence_and_scientific_id_grammar_remain_strict(actual_api):
    doc = generated_document(actual_api)
    for mutation in ("overlap", "negative", "turns", "unprefixed_request", "prefixed_experiment"):
        changed = copy.deepcopy(doc)
        if mutation == "prefixed_experiment":
            changed["publication"]["experiment_id"] = "req_" + "a" * 20
        elif mutation == "unprefixed_request":
            changed["requests"]["read"]["request_id"] = "a" * 24
        elif mutation == "turns":
            changed["requests"]["read"]["agent_turn_count"] = 3
        else:
            changed["requests"]["read"]["provider_calls_before_stage"] = 1 if mutation == "overlap" else -1
        with pytest.raises(h.HarnessFailure):
            h.validate_evidence_document(changed)


def test_unassigned_historical_charges_are_explicit_and_not_erased(actual_api):
    env = actual_api
    reservation = env.budget.reserve(model=h.EXPECTED_MODEL, messages=[{"role": "user", "content": "prior offline charge"}],
                                     tools=[], max_output_tokens=32)
    env.budget.settle(reservation, {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13}, DUMMY_KEY)
    doc = generated_document(env)
    assert doc["budget"]["calls_used"] == 7
    assert doc["provider_accounting"]["historical_attempt_nos"] == [1]
    assert doc["provider_accounting"]["historical_calls"] == 1
    assert doc["provider_accounting"]["historical_tokens"] == 13
    doc["provider_accounting"]["historical_calls"] = 0
    with pytest.raises(h.HarnessFailure, match="PROVIDER_STAGE_LEDGER_ACCOUNTING"):
        h.validate_evidence_document(doc)
