# Contributing

Thanks for looking. SHIFTGUARD is a research workbench, so the bar for a change is that its
results stay reproducible and honest.

## Before you start

- Open an issue first for anything larger than a small fix, so we can agree on scope.
- Read the [README](README.md) limits and [docs/submission/CLAIMS_AND_EVIDENCE.md](docs/submission/CLAIMS_AND_EVIDENCE.md).
  A change that alters a shown result must update the claim it supports.

## Development setup

```bash
uv sync --locked --extra test
uv run pytest -q
```

Frontend (`frontend/`): `npm ci`, `npm run typecheck`, `npm run build`. The production build
is written to `shiftguard/static/` and committed, so the app runs without Node.js.
Browser specs: `npx playwright test --config playwright.config.ts` from `frontend/`.

PostgreSQL cases run when `SHIFTGUARD_TEST_POSTGRES_URL` points at a disposable PostgreSQL 16
database. Never point it at a database you care about.

## Rules that protect the results

- **Do not edit applied Alembic migrations.** Add a new revision instead.
- **Keep the label firewall.** Final-test outcomes are read only inside the evaluator. Do not
  select methods, budgets or thresholds by looking at final-test results.
- **Count every condition.** Failures and fallbacks are reported, never dropped.
- **No numbers from the model.** The Results assistant may call approved tools; Python renders
  every figure from stored records.
- **No new paid model calls in tests.** Tests use the scripted provider. Never weaken the daily
  allowance, the zero-retry rule or the single-owner lock.
- **No secrets in the repository.** `.env`, `deploy/judge.env` and `deploy/postgres.env` stay
  local. Never commit API keys, database URLs or data files.

## Pull requests

- One coherent change per pull request, with tests for new behaviour.
- Say which checks you ran and their results.
- By contributing you agree that your contribution is licensed under Apache-2.0.
