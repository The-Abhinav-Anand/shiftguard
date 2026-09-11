# SHIFTGUARD

SHIFTGUARD is a calibration-shift research engine. Gate0 provides the local package, database bootstrap, health API, CLI, and frontend shell. Dataset ingestion, experiments, calibration analysis, jobs, and agent tools are not yet implemented.

## Local setup

Use Python 3.13 and uv. From the repository root:

```powershell
$env:UV_PYTHON_INSTALL_DIR = "..\\.tools\\python"
$env:UV_CACHE_DIR = "..\\.tools\\uv-cache"
$uv = "..\\.tools\\uv-package\\bin\\uv.exe"
& $uv lock
& $uv sync --locked --extra test
& $uv run pytest -q
& $uv run alembic upgrade head
& $uv run shiftguard status
& $uv run uvicorn shiftguard.api.main:app --reload
```

Set `SHIFTGUARD_DB_URL` in `.env` (copy `.env.example`). Local development accepts only a local SQLite file and enables WAL. A hosted deployment requires `SHIFTGUARD_ENVIRONMENT=hosted` and a PostgreSQL connection URL.

## Frontend

```powershell
cd frontend
npm ci
npm run dev
```

Run FastAPI in a second terminal with `& $uv run uvicorn shiftguard.api.main:app --reload`. Vite proxies `/api` requests to `http://127.0.0.1:8000` during development.

Production builds the frontend and serves it from the same FastAPI origin. API routes remain under `/api/v1` and are never handled by the SPA fallback.

## Container

```powershell
docker build --network host -t shiftguard:gate0 .
docker run --rm -p 8000:8000 shiftguard:gate0
```

The image compiles SQLite 3.53.1 from the verified official source archive before starting the Python application; a Docker build fails if the extracted `sqlite3.c` hash, source ID, or Python SQLite runtime is unexpected.

## Tests

`uv run pytest -q` runs local bootstrap tests. Tests needing a real PostgreSQL 16 service must be marked `postgres` and `live`; none run by default in Gate0.

## License and notices

The repository is Apache-2.0 licensed. Gate0 contains no bundled datasets or third-party source; Python and frontend dependencies are declared in their respective lockfiles and notices are described in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
