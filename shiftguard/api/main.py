from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import threading
import os

from shiftguard.agent.provider import AgentProvider
from shiftguard.api.routes import agent, agent_requests, experiments, health, jobs, metadata
from shiftguard.jobs.queue import JobQueue
from shiftguard.jobs.recovery import run_recovery_loop
from shiftguard.jobs.worker import ExperimentWorker
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import check_database_connection, create_engine_for_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    test_flags = ("SHIFTGUARD_AGENT_PROVIDER_MODE", "SHIFTGUARD_ALLOW_TEST_SCRIPTED_PROVIDER")
    if any(name in os.environ for name in test_flags):
        raise RuntimeError("test-only provider flags are not accepted by the ordinary app; use shiftguard.api.test_harness")
    test_harness = bool(getattr(app.state, "test_harness", False))
    injected_provider = getattr(app.state, "agent_provider", None)
    test_worker_factory = getattr(app.state, "test_worker_factory", None)
    if injected_provider is not None and not test_harness:
        raise RuntimeError("provider injection is restricted to the explicit test harness")
    if test_worker_factory is not None and not test_harness:
        raise RuntimeError("test worker injection is restricted to the explicit test harness")
    if test_harness and injected_provider is None:
        raise RuntimeError("the explicit test harness requires its scripted provider")
    if test_worker_factory is not None and (settings.environment != "local" or settings.database_backend != "sqlite"):
        raise RuntimeError("test worker injection requires the local SQLite profile")

    upgrade_database(settings)
    engine = create_engine_for_settings(settings)
    check_database_connection(engine)
    app.state.engine = engine

    agent_provider = getattr(app.state, "agent_provider", None)
    if agent_provider is None:
        agent_provider = AgentProvider(settings)
        app.state.agent_provider = agent_provider

    stop_event = threading.Event()
    worker_threads: list[threading.Thread] = []
    queue = None

    enable_worker = getattr(app.state, "enable_worker", None)
    if enable_worker is None:
        enable_worker = settings.embedded_worker

    if enable_worker:
        if test_worker_factory is not None:
            queue = test_worker_factory.create_queue(engine)
            worker = test_worker_factory.create_worker(settings)
        else:
            queue = JobQueue(engine)
            worker = ExperimentWorker(settings, heartbeat_interval=5, lease_seconds=30)

        def _worker_runner():
            worker.run_loop(queue, stop_event, poll_interval=settings.worker_poll_interval)

        def _recovery_runner():
            run_recovery_loop(engine, settings.artifact_root, stop_event, interval=settings.recovery_interval)

        t_worker = threading.Thread(target=_worker_runner, daemon=True, name="shiftguard-embedded-worker")
        t_recovery = threading.Thread(target=_recovery_runner, daemon=True, name="shiftguard-embedded-recovery")
        t_worker.start()
        t_recovery.start()
        worker_threads.extend([t_worker, t_recovery])

    yield

    stop_event.set()
    if test_worker_factory is not None and queue is not None:
        test_worker_factory.shutdown(queue)
    for t in worker_threads:
        t.join(timeout=3.0)
    if hasattr(app.state, "agent_provider") and app.state.agent_provider is not None:
        await app.state.agent_provider.close()
    engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="SHIFTGUARD", lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.state.test_harness = False

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = req_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    # Standardized validation error handler
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request parameters",
                    "request_id": req_id,
                    "details": {"errors": exc.errors()},
                }
            },
        )

    # Standardized HTTP exception handler
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        req_id = getattr(request.state, "request_id", None)
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            content = exc.detail
            if req_id and not content["error"].get("request_id"):
                content["error"]["request_id"] = req_id
        elif isinstance(exc.detail, dict):
            content = exc.detail
        else:
            content = {"detail": exc.detail}
        return JSONResponse(status_code=exc.status_code, content=content)

    # Register Gate 4 routers
    app.include_router(health.router)
    app.include_router(metadata.router)
    app.include_router(jobs.router)
    app.include_router(experiments.router)
    app.include_router(agent.router)
    app.include_router(agent_requests.router)

    static_dir = Path(__file__).parent.parent / "static"
    index_file = static_dir / "index.html"
    if (static_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    # Legacy health compatibility
    @app.get("/api/v1/health")
    def health_compat(request: Request) -> dict[str, str]:
        check_database_connection(request.app.state.engine)
        return {"status": "ok", "database": "ready"}

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/") or path == "assets" or path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if index_file.is_file():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend index.html not found")

    return app


app = create_app()
