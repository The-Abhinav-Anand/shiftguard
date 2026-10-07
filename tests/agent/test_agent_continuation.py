"""Tests for agent durable continuation, job waiting, and nonce receipt replay."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine, text
from uuid import uuid4

from shiftguard.agent.controller import AgentController
from shiftguard.agent.provider import ProviderResponse, ScriptedProvider
from shiftguard.agent.registry import ToolRegistry
from shiftguard.agent.schemas import FunctionCall, ToolCall
from shiftguard.agent.store import AgentStore
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.models import JobStatus
from shiftguard.jobs.queue import JobQueue
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def continuation_env(tmp_path):
    db_file = tmp_path / "test_cont.db"
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
    )
    upgrade_database(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    store = AgentStore(engine)
    queue = JobQueue(engine)
    registry = ToolRegistry()
    return engine, settings, store, queue, registry


import asyncio


def test_job_waiting_and_resume_flow(continuation_env):
    engine, settings, store, queue, registry = continuation_env
    cont_service = ContinuationService(engine)
    session = cont_service.create_session()

    # 1. Turn 1 calls run_experiment (side-effect)
    tc_run = ToolCall(
        id="call_run_1",
        type="function",
        function=FunctionCall(name="run_experiment", arguments='{"preset_name": "bank-baseline"}'),
    )
    resp1 = ProviderResponse(content=None, tool_calls=[tc_run])

    # Turn 2 (resumed after job finishes) provides final answer
    resp2 = ProviderResponse(content="The experiment job finished and I evaluated the results.", tool_calls=None)

    provider = ScriptedProvider(responses=[resp1, resp2])
    controller = AgentController(engine, settings, store, registry, provider, session.capability_token)

    req, _ = store.create_or_get_request(
        session_id=session.id,
        intent_key="intent_cont_1",
        canonical_body_hash="hash_c1",
        prompt="Run bank baseline",
        authority_token_hash=store.authority_hash(session.capability_token),
    )

    async def _run():
        # First execution pauses for job
        req_step1 = await controller.execute_request(req.id, worker_id="worker_cont")
        assert req_step1.status == "WAITING_FOR_JOB"
        assert req_step1.active_job_id is not None
        job_id = req_step1.active_job_id
        nonce_1 = req_step1.active_nonce

        # 2. Try to resume while job is still queued -> 202 Accepted
        status_code, res_waiting = await controller.resume_request(req.id, nonce=nonce_1, worker_id="worker_cont")
        assert status_code == 202
        assert res_waiting["status"] == "WAITING_FOR_JOB"
        nonce_2 = res_waiting["resume_nonce"]

        # 3. Simulate job completion
        job = queue.get_job(job_id)
        assert job is not None
        claimed = queue.claim_next_job(worker_id="test_worker")
        assert claimed is not None
        queue.mark_completed(
            job_id=job.id,
            fencing_token=claimed.fencing_token,
            experiment_id="exp_synth_12345",
            result_data={"experiment_id": "exp_synth_12345"},
        )
        execution_id = str(uuid4())
        generation_id = str(uuid4())
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO experiments (id, payload_json, content_hashes_json) VALUES (:id, '{}', '{}')"),
                         {"id": "exp_synth_12345"})
            conn.execute(text("INSERT INTO experiment_executions (execution_id, experiment_id, audit_json) VALUES (:e, :id, '{}')"),
                         {"e": execution_id, "id": "exp_synth_12345"})
            conn.execute(text("""
                INSERT INTO experiment_publications (
                    generation_id, experiment_id, full_digest, execution_id, status,
                    manifest_json, created_at, updated_at, job_id
                ) VALUES (:g, :id, :digest, :e, 'PUBLISHED', '{}', :now, :now, :job)
            """), {"g": generation_id, "id": "exp_synth_12345", "digest": "a" * 64,
                  "e": execution_id, "now": "2026-10-01T00:00:00+00:00", "job": job.id})

        # 4. Resume request with job completed -> 200 OK and transitions to COMPLETED
        status_code2, res_done = await controller.resume_request(req.id, nonce=nonce_2, worker_id="worker_cont")
        assert status_code2 == 200
        assert res_done["status"] == "COMPLETED"

        # 5. Nonce receipt replay: call with nonce_2 again returns exact cached receipt without provider call
        status_code3, res_replay = await controller.resume_request(req.id, nonce=nonce_2, worker_id="worker_cont")
        assert status_code3 == 200
        assert res_replay == res_done

        # Replaying nonce_1 returns exact cached 202 receipt
        status_code_orig, res_replay_1 = await controller.resume_request(req.id, nonce=nonce_1, worker_id="worker_cont")
        assert status_code_orig == 202
        assert res_replay_1 == res_waiting

    asyncio.run(_run())


def test_sequential_requests_in_same_session(continuation_env):
    engine, settings, store, queue, registry = continuation_env
    cont_service = ContinuationService(engine)
    session = cont_service.create_session()

    # Turn 1 for request A
    r_a = ProviderResponse(content="Answer for request A", tool_calls=None)
    # Turn 1 for request B
    r_b = ProviderResponse(content="Answer for request B", tool_calls=None)

    provider = ScriptedProvider(responses=[r_a, r_b])
    session_id = session.id
    controller = AgentController(engine, settings, store, registry, provider, session.capability_token)

    async def _run():
        # Submit question 1
        req1, _ = store.create_or_get_request(
            session_id=session_id,
            intent_key="intent_q1",
            canonical_body_hash="hash_q1",
            prompt="First question",
            authority_token_hash=store.authority_hash(session.capability_token),
        )
        done1 = await controller.execute_request(req1.id, worker_id="worker_1")
        assert done1.status == "COMPLETED"
        assert done1.final_response is not None

        # Submit question 2 under same session
        req2, _ = store.create_or_get_request(
            session_id=session_id,
            intent_key="intent_q2",
            canonical_body_hash="hash_q2",
            prompt="Second question",
            authority_token_hash=store.authority_hash(session.capability_token),
        )
        done2 = await controller.execute_request(req2.id, worker_id="worker_1")
        assert done2.status == "COMPLETED"
        assert done2.id != done1.id

    asyncio.run(_run())
