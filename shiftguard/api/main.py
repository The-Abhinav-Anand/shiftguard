from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import check_database_connection, create_engine_for_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    upgrade_database(settings)
    engine = create_engine_for_settings(settings)
    check_database_connection(engine)
    app.state.engine = engine
    yield
    engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="SHIFTGUARD", lifespan=lifespan)
    app.state.settings = settings or Settings()
    static_dir = Path(__file__).parent.parent / "static"
    index_file = static_dir / "index.html"
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/api/v1/health")
    def health(request: Request) -> dict[str, str]:
        check_database_connection(request.app.state.engine)
        return {"status": "ok", "database": "ready"}

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/") or path == "assets" or path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(index_file)

    return app


app = create_app()
