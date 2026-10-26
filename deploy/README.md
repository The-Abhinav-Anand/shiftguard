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
| `caddy` | `caddy:2` with `deploy/Caddyfile` | The only public service (80/443). Gets a Let's Encrypt certificate for `SHIFTGUARD_DOMAIN` and proxies to `api:8000`. Certificates persist in `caddy_data` |

## One-command VM setup

On a fresh Ubuntu 22.04 or 24.04 VM (amd64 or arm64, 2 GB RAM or more) with TCP 80 and 443
open in the cloud firewall, and a DNS name pointing at the VM:

```bash
curl -fsSL https://raw.githubusercontent.com/The-Abhinav-Anand/shiftguard/main/deploy/bootstrap-vm.sh -o bootstrap-vm.sh
sudo SHIFTGUARD_DOMAIN=shiftguard.duckdns.org bash bootstrap-vm.sh
```

`deploy/bootstrap-vm.sh` is safe to rerun. It:

1. installs Docker Engine and the compose plugin from Docker's apt repository;
2. clones the repository into `/opt/shiftguard`, or fast-forwards it (never resets);
3. builds the image on the VM, so it matches the CPU architecture;
4. creates `deploy/judge.env` and `deploy/postgres.env` with a random password, mode 600, only if
   they are missing (it never overwrites an existing `NEBIUS_API_KEY`);
5. writes `deploy/.env` with `SHIFTGUARD_DOMAIN` and both assistant flags set to `false`;
6. copies the Bank dataset from `--dataset-from DIR`, or downloads it from UCI and checks it
   against `data/manifests/bank.json` (the clean CSV must hash to the frozen digest);
7. runs `docker compose up -d` and waits for `/health/ready`.

It opens 80/443 in the host's iptables `INPUT` chain only when that chain has a reject rule
(Oracle's Ubuntu images ship one). It never prints the password, database URL or API key.

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

The API listens on `127.0.0.1:8000` only; the `caddy` service is the HTTPS front. On a
platform with its own HTTPS ingress, drop `caddy` and point the ingress at the API instead. Experiments run as durable jobs, so no
request waits for one to finish, but a model call may take up to `NEBIUS_TIMEOUT` (55 s): set the
ingress timeout to at least 60 s for chat and longer for Results-assistant requests (up to 8 calls).

## Enabling the model

Only after a specific live allowance has been authorized:

1. Set `NEBIUS_API_KEY` in `judge.env`.
2. Start with `SHIFTGUARD_GENERAL_CHAT_ENABLED=true` and/or `SHIFTGUARD_AGENT_ENABLED=true`
   in the shell environment of `docker compose up`.
   `compose.judge.yaml` sets `NEBIUS_TIMEOUT` to 55 seconds (the settings maximum) unless
   `NEBIUS_TIMEOUT` is set in the shell or `deploy/.env`; a value in `judge.env` is overridden.
   A restart while a model call is in flight can still halt that UTC day (startup recovery
   treats the open reservation as unknown). A release that changes the ledger policy halts a
   UTC day already opened under the old policy (`policy_binding_mismatch`), so deploy such a
   release before the first model call of the UTC day (00:00 UTC, 05:30 IST).
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
