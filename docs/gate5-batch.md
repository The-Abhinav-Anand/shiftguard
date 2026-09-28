# G5-01 implementation contract

Current ownership override, 28 September 2026: Antigravity completes code/corrections; GPT-6 Astra Extra High reviews. The dated authorization below remains historical; A1–A8 and scientific boundaries are unchanged. Execute docs/antigravity-execution-prompt.md.

Authorized 26 September 2026: implement `docs/next-execution.md` using GPT-6 Luna Extra High for the entire coding batch and GPT-6 Astra Extra High for independent review. Base HEAD: `475b4b7fc7a3c5fb87396aac7e75d035343628df`; existing uncommitted workflow updates are retained.

## Change boundary

User-visible need: an actual browser product for the already verified experiment engine. The existing health-link placeholder cannot run or inspect experiments; code changes are required. Initial scope: `frontend/**`, `tests/e2e/**`, `docs/gate5-*.md`, plus `shiftguard/static/**` solely for generated frontend build assets replacing the tracked Gate 0 shell. Parent owns `.agent/**` and external verification. Backend API gaps must be demonstrated before parent expands the scope. No scientific logic, accepted artifacts, migration history or confirmatory data changes.

Use a small set of typed owners for API/session state, experiment/job orchestration, scientific display and UI styling. Avoid a single oversized App file, duplicated fetch/error logic, a general chart framework or a new state-management dependency unless needed. Match blueprint section 18.1: React/TypeScript/Vite and Plotly via react-plotly.js for the scientific views. A coherent usable vertical slice, rather than a line-count target, defines the large batch.

## Acceptance IDs

| ID | Required behavior and proof |
| --- | --- |
| G5-A1 | Same-origin built React product starts through FastAPI. Approved preset controls use typed schemas and server-issued session credentials. No arbitrary dataset/path/code fields. |
| G5-A2 | Submit, poll, cancel, rerun and reload retain correct job identity and credentials. Lost-response retry reuses an idempotency key; a new intentional run gets a new key. Credentials never enter URLs or displayed traces. |
| G5-A3 | Budget curve, pattern-versus-rate, reliability and decision-loss views render real persisted payloads. Predictor/scenario/method/budget/cost labels bind to the selected records. Show unavailable/failed values honestly; no invented numeric series or scientific recomputation in JavaScript. |
| G5-A4 | Experiment identity, provenance, actual fallback and qualification details are inspectable. Single-seed results are labeled illustrative; adverse results remain adverse. |
| G5-A5 | A persisted cached stress run stays usable when a new job fails or the worker is unavailable. Clearly distinguish cached results from fresh computation. Empty first-use state is usable. |
| G5-A6 | Errors, cancellation requests, terminal outcomes and recovery are visible. Reload restores work; retry does not duplicate submission. Expired session/network/storage failure behavior is explicit. |
| G5-A7 | Keyboard and narrow-screen use remain practical, labels are accessible, and charts have readable numeric/table equivalents. Parent visually inspects actual desktop and mobile renders. No fake live-agent interface; traces contain request/result facts only. |
| G5-A8 | Build/type checks and the three planned Playwright suites pass. `frontend/playwright.config.ts` uses `testDir: '../tests/e2e'` and a managed same-origin FastAPI server with built assets. At least one real browser-to-worker-to-persisted-result path is exercised; mocked error branches are identified as such. Hosted mode requires explicit SG_E2E_BASE_URL. |

## Evidence and loop

Antigravity delivers the integrated batch and a compact `docs/gate5-implementation.md` mapping these IDs to exact tests and actual results. Preserve commands, counts, limitations and any new dependency. Parent independently runs the needed acceptance checks and requests one Astra Extra High review of the stable candidate. Antigravity then fixes all blocking findings in one correction batch; Astra rechecks only affected behavior. Two correction cycles without verified progress trigger root-cause diagnosis. Do not reopen unaffected Gate 4 science or rerun its full suite for frontend-only changes.

Verification output belongs outside the tracked app under `../verification/gate5/`. Reuse existing Node/Python/browser runtimes. Use isolated test databases/artifact directories; do not modify the normal application database or historical artifacts. Do not commit, publish, deploy or contact anyone from the implementation agent. Parent handles reviewed candidate/checkpoint commits.

## Narrow integration boundary expansion

Parent inspection found `tests/integration/test_static_boundaries.py` hard-codes `/assets/gate0.js`. The assigned implementer may update that test to discover the real entry script from the built index and preserve the JavaScript MIME, missing asset 404 and API/SPA boundary assertions. This is a frontend asset contract update; no backend Python implementation changes are authorized. Run this affected suite with an isolated pytest temporary directory.
