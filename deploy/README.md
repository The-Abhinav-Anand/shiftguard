# Judge deployment

One API process, one experiment worker, PostgreSQL 16, a durable artifact volume and the
verified Bank dataset mounted read-only. Everything runs from one image built from the
repository `Dockerfile`.

| Service | Command | Notes |
|---|---|---|
| `postgres` | `postgres:16` | Not published outside the compose network; `pgdata` volume |
| `migrate` | `shiftguard status` | Runs Alembic to head once, then exits |
| `api` | `uvicorn … --workers 1` | Starts after `migrate` succeeds; embedded worker off |
| `worker` | `shiftguard worker --poll-interval 0.5 --recovery-interval 5` | Starts after `api` is healthy, so schema checks never run concurrently |

## Do not scale

Run exactly one `api` and one `worker` replica. The ordinary model budget (50 calls and
100,000 tokens per UTC day, shared by general chat and the Results assistant) has one owner
per database. A second provider-enabled API process refuses to start instead of taking
over the first one's open reservation.

## Prepare

1. Build the image from the repository root:
   `docker build -t shiftguard:judge .`
   Record the resolved base-image digests and the image ID with the release evidence.
2. Copy `judge.env.example` to `judge.env` and `postgres.env.example` to `postgres.env`,
   then set the same new database password in both. These two files are ignored by Git
   and by the Docker build context. Never put credentials in the compose file, the image,
   build arguments or the frontend.
3. Put the verified `bank-additional-full.csv` and `bank-marketing.manifest.json` in
   `deploy/datasets/` (or point `SHIFTGUARD_DATASET_DIR` elsewhere). `/health/ready`
   returns 503 `dataset_unverified` unless both match the frozen Bank identity
   (41,188 rows, clean SHA-256 `0e685060…c329`).
4. Back up the `pgdata` and `artifacts` volumes together. The database records each
   published artifact's digest, so restoring one without the other breaks verification.

## Start (offline first)

```bash
docker compose -f deploy/compose.judge.yaml up -d
```

Both assistant flags default to `false`. Run the offline acceptance probe against the
HTTPS URL. It creates its own session and runs one approved Bank preset through the
separate worker. It never sends a model request.

```bash
python scripts/check_hosted_release.py --base-url https://<host> --output <evidence>/probe.json
```

The API listens on `127.0.0.1:8000` only. Put a TLS-terminating proxy or the hosting
platform's HTTPS ingress in front of it. Keep proxy timeouts short: experiments run as
durable jobs, so no request needs to wait for one to finish.

## Enabling the model

Only after a specific live allowance has been authorized:

1. Set `NEBIUS_API_KEY` in `judge.env`.
2. Start with `SHIFTGUARD_GENERAL_CHAT_ENABLED=true` and/or `SHIFTGUARD_AGENT_ENABLED=true`
   in the shell environment of `docker compose up`.
3. Check `/api/v1/agent/status` for the remaining shared daily allowance before and after
   each live check.

Once the day's allowance is used, both assistants answer with a cap message until the next
UTC day. The manual workbench, saved results and charts keep working without the model.

## Measured on the local Linux stack (15 October 2026)

- One bank-stress job (400 conditions) on the release image: worker peaked at 315 MiB,
  API at 161 MiB and PostgreSQL at 37 MiB. The compose limits (2 GB worker, 1 GB API)
  leave ample headroom, so any VM with 2 GB or more fits.
- The job survived an abrupt worker kill and an API restart, and was published once.
- A second provider-enabled API on the same database refused to start
  (`OrdinaryOwnerUnavailable`) and left the first one serving.
- No database password or URL appeared in any container log.

Evidence: `verification/gate10-image-20261014T184638Z-e606f2d016c8/` in the outer workspace.

## What `/health/ready` checks

- Database connectivity.
- Schema at the expected Alembic head.
- Writable artifact root.
- Verified Bank dataset.

It does not show that the worker is alive. The acceptance probe shows that by completing a
real job. `/health/live` checks no dependencies.
