# Next execution: Gate 5 browser product

Gate 4 is accepted on source `10170feab3c16c5eb61153d57d9e5879ba5a6fd6`. Gate 5 implementation has NOT_STARTED. This is the existing blueprint's next phase, not a new scientific scope.

## Ownership and limits

Parent plans and accepts. Antigravity may execute an assigned frontend batch; GPT-6 Luna High handles named coding corrections, GPT-6 Sol High performs one bounded review. Assign one writer before edits; never use concurrent writers on the same files. Keep Python responsible for all numerical results. Browser and future Nemotron layers only request approved operations and display persisted results.

## Execution sequence

1. Inspect existing `frontend/src` and the Gate 4 API/OpenAPI contract. Reuse present components and types. Record the exact frontend-only allowlist and remove duplicate stubs only when callers are verified. Preserve backend scientific behavior.
2. Wire typed API calls and server-issued session credentials. Build approved preset controls, submission with idempotency keys, polling and terminal job states. Do not accept arbitrary paths, code, SQL, data uploads or hidden experiment configuration.
3. Render all four stored payloads: budget curve, pattern versus rate, reliability and decision loss. Show units, costs/thresholds, qualification status, missing/failed conditions and single-seed illustrative status. Do not recompute numerical results in JavaScript.
4. Add provenance, fallback diagnostics, cached-versus-fresh state, cancellation, rerun and clear errors. Keep cached demonstrations usable during fresh-job failure. Trace summaries contain tool/result facts, never hidden reasoning. Do not claim live Nemotron integration before Gate 6.
5. Complete local browser acceptance: first-time preset run; all four plots; job progress and cancellation; lost-response retry; reload with credential continuity; errors and rerun; cached-view availability. Keep credentials out of URLs/logs. Verify practical narrow-screen and keyboard use as part of the same browser pass.
6. Configure Playwright at `frontend/playwright.config.ts` with `testDir: '../tests/e2e'` and a same-origin FastAPI `webServer` serving built assets. Run type/build checks and the planned flagship/reload/job-error suites. Inspect actual rendered browser output before review. Hosted tests require an explicitly supplied `SG_E2E_BASE_URL`; never invent a public deployment.
7. Deliver one coherent diff, test commands/results and screenshots to parent. Re-run affected backend tests only if backend source changes. Close Gate 5 with one source-bound review; do not restart the entire Gate 4 audit for frontend-only edits.

## Planned verification (not run for Gate 5)

From the application root, after the scripts exist and existing Node dependencies are checked:

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend run install:e2e-browser
npm --prefix frontend run test:e2e -- test_flagship_preset.spec.ts test_reload.spec.ts test_job_errors.spec.ts
```

Reuse an existing browser/runtime where available. Missing downloads/network access should be reported precisely; no paid service is required for this local phase. These commands are planned, not completion evidence.

## User requirements

No API key, paid cloud account or PostgreSQL installation is needed for local Gate 5. Deployment destination and live model credentials belong to later phases and are not authorized or configured here. For the internship pack, the user supplies actual availability/start date, weekly hours and on-site consent before applying; those personal facts must not be invented.

Authoritative original scope: [Gate 5 execution plan](../../docs/aegis/plans/2026-09-10-shiftguard-hackathon-execution-plan.md). Historical next-execution text is preserved in the independent review's `prior-governance/docs/next-execution.md`.
