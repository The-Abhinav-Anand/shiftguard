"""Explicit factory for isolated, deterministic scripted API/browser tests."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import threading
import time
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine

from shiftguard.agent.provider import DynamicE2EProvider, ScriptedProvider, create_e2e_scripted_provider
from shiftguard.api.main import create_app
from shiftguard.jobs.models import JobRecord, JobStatus
from shiftguard.jobs.queue import JobQueue
from shiftguard.jobs.worker import ExperimentWorker
from shiftguard.settings import Settings


@dataclass
class _WorkerScenario:
    scenario_id: str
    outcome: Literal["pause_next", "fail_next"]
    session_id: str
    state: str = "armed"
    job_id: str | None = None
    failure_raised: bool = False
    pause_started: bool = False
    release_event: threading.Event = field(default_factory=threading.Event)


class _ScenarioController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._scenarios: dict[str, _WorkerScenario] = {}
        self._pending: deque[str] = deque()

    def arm(self, outcome: Literal["pause_next", "fail_next"], session_id: str) -> _WorkerScenario:
        with self._lock:
            if any(item.state in {"armed", "claimed", "paused", "released"} for item in self._scenarios.values()):
                raise ValueError("a worker scenario is already active")
            scenario = _WorkerScenario(scenario_id=uuid4().hex, outcome=outcome, session_id=session_id)
            self._scenarios[scenario.scenario_id] = scenario
            self._pending.append(scenario.scenario_id)
            return scenario

    def get(self, scenario_id: str) -> _WorkerScenario | None:
        with self._lock:
            return self._scenarios.get(scenario_id)

    def claim(self, job: JobRecord) -> None:
        with self._lock:
            for _ in range(len(self._pending)):
                scenario_id = self._pending.popleft()
                scenario = self._scenarios.get(scenario_id)
                if scenario is None or scenario.state != "armed":
                    continue
                if scenario.session_id != job.session_id:
                    self._pending.append(scenario_id)
                    continue
                scenario.job_id = job.id
                scenario.state = "claimed"
                return

    def for_job(self, job_id: str) -> _WorkerScenario | None:
        with self._lock:
            return next((item for item in self._scenarios.values() if item.job_id == job_id), None)

    def fail_once(self, scenario: _WorkerScenario) -> bool:
        with self._lock:
            if scenario.outcome != "fail_next" or scenario.failure_raised:
                return False
            scenario.failure_raised = True
            return True

    def pause_until_released(self, scenario: _WorkerScenario, engine: Engine) -> None:
        with self._lock:
            if scenario.outcome != "pause_next" or scenario.pause_started:
                return
            scenario.pause_started = True
        deadline = time.monotonic() + 50
        while not scenario.release_event.is_set():
            with engine.connect() as connection:
                heartbeat = connection.execute(text(
                    "SELECT 1 FROM job_events WHERE job_id = :job_id AND event_type = 'HEARTBEAT' LIMIT 1"
                ), {"job_id": scenario.job_id}).first()
            if heartbeat:
                with self._lock:
                    if not scenario.release_event.is_set():
                        scenario.state = "paused"
                break
            if time.monotonic() >= deadline:
                with self._lock:
                    scenario.state = "failed"
                raise RuntimeError("managed worker heartbeat did not arrive for paused scenario")
            time.sleep(0.05)
        if not scenario.release_event.wait(timeout=120):
            with self._lock:
                scenario.state = "failed"
            raise RuntimeError("managed worker pause scenario was not released")
        with self._lock:
            scenario.state = "released"

    def release(self, scenario_id: str, queue: JobQueue) -> _WorkerScenario:
        with self._lock:
            scenario = self._scenarios.get(scenario_id)
            if scenario is None:
                raise KeyError(scenario_id)
            if scenario.outcome != "pause_next" or not scenario.job_id:
                raise ValueError("only a claimed pause scenario can be released")
        job = queue.get_job(scenario.job_id)
        cancellation_won = (
            job is not None
            and job.session_id == scenario.session_id
            and job.cancel_requested
            and job.status in {JobStatus.RUNNING, JobStatus.CANCELLED}
        )
        if not cancellation_won:
            raise ValueError("release requires a real job with cancellation requested or completed")
        scenario.release_event.set()
        return scenario

    def terminal(self, job_id: str, status: str) -> None:
        with self._lock:
            scenario = next((item for item in self._scenarios.values() if item.job_id == job_id), None)
            if scenario is not None:
                scenario.state = status

    def shutdown(self, queue: JobQueue) -> None:
        with self._lock:
            active = [item for item in self._scenarios.values() if item.job_id and item.state in {"claimed", "paused", "released"}]
        for scenario in active:
            job = queue.get_job(scenario.job_id or "")
            if job is not None and job.status == JobStatus.RUNNING and not job.cancel_requested:
                queue.request_cancellation(job.id, session_id=job.session_id)
            scenario.release_event.set()


class _ScenarioJobQueue(JobQueue):
    def __init__(self, engine: Engine, scenarios: _ScenarioController) -> None:
        super().__init__(engine)
        self._scenarios = scenarios

    def claim_next_job(self, worker_id: str, lease_seconds: int = 90) -> JobRecord | None:
        job = super().claim_next_job(worker_id=worker_id, lease_seconds=lease_seconds)
        if job is not None:
            self._scenarios.claim(job)
        return job

    def is_cancellation_requested(self, job_id: str, fencing_token: str) -> bool:
        scenario = self._scenarios.for_job(job_id)
        if scenario is not None and self._scenarios.fail_once(scenario):
            raise RuntimeError("scripted managed worker failure")
        if scenario is not None and scenario.outcome == "pause_next":
            self._scenarios.pause_until_released(scenario, self.engine)
        return super().is_cancellation_requested(job_id, fencing_token)


class _ScenarioWorker(ExperimentWorker):
    def __init__(self, settings: Settings, scenarios: _ScenarioController) -> None:
        super().__init__(settings, heartbeat_interval=10, lease_seconds=90)
        self._scenarios = scenarios

    def execute_job(self, job: JobRecord, queue: JobQueue) -> None:
        try:
            super().execute_job(job, queue)
        finally:
            current = queue.get_job(job.id)
            if current is not None and current.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
                self._scenarios.terminal(job.id, current.status.value)


class _ScenarioWorkerFactory:
    def __init__(self) -> None:
        self.scenarios = _ScenarioController()

    def create_queue(self, engine: Engine) -> _ScenarioJobQueue:
        return _ScenarioJobQueue(engine, self.scenarios)

    def create_worker(self, settings: Settings) -> _ScenarioWorker:
        return _ScenarioWorker(settings, self.scenarios)

    def shutdown(self, queue: JobQueue) -> None:
        self.scenarios.shutdown(queue)


class _ScenarioInput(BaseModel):
    outcome: Literal["pause_next", "fail_next"]
    session_id: str = Field(min_length=1, max_length=128)


def _scenario_router(scenarios: _ScenarioController) -> APIRouter:
    router = APIRouter(prefix="/__test__/worker/scenarios", tags=["scripted test worker"])

    @router.post("")
    def arm_scenario(body: _ScenarioInput) -> dict[str, str]:
        try:
            scenario = scenarios.arm(body.outcome, body.session_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"scenario_id": scenario.scenario_id}

    @router.get("/{scenario_id}")
    def scenario_state(scenario_id: str) -> dict[str, str | None]:
        scenario = scenarios.get(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="worker scenario not found")
        return {"state": scenario.state, "job_id": scenario.job_id}

    @router.post("/{scenario_id}/release")
    def release_scenario(scenario_id: str, request: Request) -> dict[str, str | None]:
        try:
            scenario = scenarios.release(scenario_id, JobQueue(request.app.state.engine))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="worker scenario not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"state": scenario.state, "job_id": scenario.job_id}

    return router


def create_scripted_test_app(
    settings: Settings,
    provider: ScriptedProvider | DynamicE2EProvider | None = None,
) -> FastAPI:
    """Build a local SQLite app with an explicitly supplied in-process script."""
    if settings.environment != "local" or settings.database_backend != "sqlite":
        raise ValueError("scripted test apps require the local SQLite profile")
    if provider is not None and type(provider) not in {ScriptedProvider, DynamicE2EProvider}:
        raise TypeError("scripted test apps accept only the built-in scripted providers")
    app = create_app(settings)
    app.state.test_harness = True
    app.state.test_harness_metadata = {
        "provider_kind": "scripted",
        "evidence_mode": "scripted",
        "live_provider_calls": False,
    }
    app.state.agent_provider = provider if provider is not None else create_e2e_scripted_provider()
    if settings.embedded_worker:
        worker_factory = _ScenarioWorkerFactory()
        app.state.test_worker_factory = worker_factory
        spa_fallback = next(
            (route for route in app.router.routes if getattr(route, "path", None) == "/{path:path}"),
            None,
        )
        if spa_fallback is not None:
            app.router.routes.remove(spa_fallback)
        app.include_router(_scenario_router(worker_factory.scenarios))
        if spa_fallback is not None:
            app.router.routes.append(spa_fallback)

    @app.middleware("http")
    async def mark_scripted_harness(request, call_next):
        response = await call_next(request)
        response.headers["X-Shiftguard-Test-Harness"] = "scripted"
        return response

    return app
