# SHIFTGUARD

SHIFTGUARD is a calibration-shift research engine. Gates 0–4 provide the deterministic Bank baseline, outage/recalibration slice, 400-condition development stress engine, and verified API/durable-worker backend. The Gate 5 browser candidate adds approved runs, durable job controls, four persisted scientific views, provenance and cached results; Gate 5 is accepted; see [the acceptance packet](docs/gate5-acceptance.md). Live agent integration, confirmatory research, full Adult replication, hosted deployment and submission remain unfinished. See [blueprint progress](docs/blueprint-progress.md).

Current execution follows [loop engineering](docs/loop-engineering.md): GPT-6 Luna xhigh implements bounded batches, GPT-6.1 Sol xhigh reviews the backend delta, and GPT-6 Astra xhigh reviews the frontend. The ordinary preloaded Bank engine and workbench are working; both bounded correction reviews returned PASS. Gate 6 remains pending its required evidence and acceptance. See [the current recovery checkpoint](docs/product-refresh-20260930/PRODUCT_RECOVERY_20261002.md).

The [version 0.2 working paper](../research/SHIFTGUARD_Working_Paper_v0.2.pdf) reports the actual single-seed Bank development results, including adverse outcomes. Editable DOCX, extraction CSVs and provenance are in the outer `research/` directory. It is not a confirmatory or peer-reviewed publication.

## Local setup

For this existing checkout with its preloaded Bank dataset, start the API and experiment worker together:

```powershell
.\scripts\start-local.ps1
```

Open `http://127.0.0.1:8000`. Choose an approved analysis and click **Run analysis**, or open a saved result. This uses the existing database and artifacts. Closing the launch terminal does not stop the hidden local server. Runtime ownership and logs are recorded in `var/runtime/`.

For a fresh environment, use the setup below.

Use Python 3.13 and uv. From the repository root:

```powershell
$env:UV_PYTHON_INSTALL_DIR = "..\\.tools\\python"
$env:UV_CACHE_DIR = "..\\.tools\\uv-cache"
$uv = "..\\.tools\\uv-package\\bin\\uv.exe"
& $uv sync --locked --extra test
& $uv run pytest -q
& $uv run alembic upgrade head
& $uv run shiftguard status
& $uv run python scripts/download_datasets.py --dataset bank --manifest data/manifests/bank.json
& $uv run shiftguard run --config configs/bank-baseline.yaml
.\scripts\start-local.ps1
```

## Gate2 development slice

The development-only history outage and 50-label target-temperature slice runs with:

```powershell
& $uv run shiftguard run --config configs/bank-outage-50.yaml
```

It persists no-outage raw/source, outage raw/source/target conditions and paired deltas. It is not a confirmatory result.

The history mask is fixed on the entire unlabeled target pool in canonical row order before revealing the nested 50-label prefix. Test masking uses an independent stream. Overall new missingness uses observed cells across all ten features as its denominator; history-group and acquired-subset rates are reported separately with counts. Prediction failures resolve source to raw and target to frozen source to raw before evaluator access. An exhausted chain produces a failed condition with null metrics and unavailable comparisons.

Artifact status exclusions and replacement IDs are in [the Gate2 status ledger](docs/submission-evidence/gate2-artifact-status.json). Previous artifact bytes remain intact. Counts distinguish unique calibrator fit failures from unique prediction failures per feature regime, avoiding double-counted source reuse. Final outcomes never select a fallback.

Set `SHIFTGUARD_DB_URL` in `.env` (copy `.env.example`). Local development accepts only a local SQLite file and enables WAL. A hosted deployment requires `SHIFTGUARD_ENVIRONMENT=hosted` and a PostgreSQL connection URL.

## Frontend

```powershell
cd frontend
npm ci
npm run dev
```

Run `.\scripts\start-local.ps1` from the repository root first. Vite proxies `/api` requests to `http://127.0.0.1:8000` during development. An API launched without an embedded or separate worker accepts jobs but cannot execute them.

Production builds the frontend and serves it from the same FastAPI origin. API routes remain under `/api/v1` and are never handled by the SPA fallback.

`/` opens the preloaded-data workbench; `/demo` is an alias. `/about` explains the product and its business use. Private workspace routes explicitly describe planned capabilities. The public assistant remains disabled pending Gate 6 acceptance.

## Container

```powershell
docker build --network host -t shiftguard:gate0 .
docker run --rm -p 8000:8000 shiftguard:gate0
```

The image compiles SQLite 3.53.1 from the verified official source archive before starting the Python application; a Docker build fails if the extracted `sqlite3.c` hash, source ID, or Python SQLite runtime is unexpected.

## Tests

`uv run pytest -q` runs the local suite. Tests needing a real PostgreSQL 16 service are opt-in via the `postgres` and `live` markers. The Gate2 author check is `uv run --no-sync pytest tests/unit/test_history_block.py tests/unit/test_acquisition_prefix.py tests/integration/test_outage_recovery.py -q`; parent verification precedes the consolidated gate-exit review.

## License and notices

The repository is Apache-2.0 licensed. Gate0 contains no bundled datasets or third-party source; Python and frontend dependencies are declared in their respective lockfiles and notices are described in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
