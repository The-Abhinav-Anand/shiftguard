# Antigravity execution instructions — SHIFTGUARD

Active checkpoint, 30 September 2026: **Gate 6 independent review returned BLOCKERS (25 findings).** Execute only [AG-G6-CORRECTIONS-01](gate6-corrections.md), with [the complete review](gate6-review.md), [Sol application findings](gate6-sol-review.md) and [next execution](next-execution.md). Antigravity codes; **GPT-6.1 Sol Extra High** reviews. The dated AG-G5-CLOSE instructions below, including their Astra assignment and old HEAD/status, are retained as history and are **not the current execution packet**. Gate 5 is accepted; Gate 6 is pending.

Effective 28 September 2026. Copy this entire document into Antigravity. It replaces Luna as the future coding owner, while retaining the existing implementation and evidence. This is an execution packet; it is not a claim that Antigravity has already run or that a gate has passed.

## Your role and working rules

You are the sole application implementer in Antigravity. Complete coherent batches of code, integration, tests and documentation before handing work to GPT-6 Astra Extra High (`gpt-6-astra`, `xhigh`) in Codex for independent review. Use your configured coding model; no particular Antigravity model is implied or required by this packet.

Do not stop after each file or component for approval. Finish the entire authorized batch and ordinary debugging. Do not change the product architecture, replace the project, start a parallel writer, or submit your own work as independently accepted. Astra reviews a stable candidate once and returns all material findings together. You fix the complete finding set together; the next review covers only the correction delta and affected contracts. Optional cleanup is recorded separately.

Two correction rounds without a newly proven requirement or closed finding require a concrete Astra root-cause brief before another rewrite. Test failures are investigated from their actual assertion and data. Do not weaken tests, add skips, fake evidence, or make production code expose unnecessary data merely to satisfy an incorrect expectation.

Use the retained checkout:

```text
Workspace: C:\Users\Abhinav Anand\Downloads\nvidia
Application: C:\Users\Abhinav Anand\Downloads\nvidia\shiftguard
Shell: Windows PowerShell
Branch: implementation/gate-0
Current HEAD: 475b4b7fc7a3c5fb87396aac7e75d035343628df
Accepted Gate 4 source: 10170feab3c16c5eb61153d57d9e5879ba5a6fd6
Current source snapshot: ../verification/gate5/antigravity-handoff-20260928/checkpoint.json
Snapshot digest: cd96b3b0345376ccd50bdb45132100f38407e558bccbd54318054e7630d5a59b
```

The checkout is intentionally dirty with the retained Gate 5 implementation, tests and workflow documents. Preserve every change. Do not reset, clean, switch branches, discard files or assume HEAD contains the browser implementation. Read `AGENTS.md`, `.agent/HANDOFF.md`, `.agent/ownership.json`, `docs/next-execution.md`, and the batch-specific review. Do not reload old review histories or the entire blueprint for the current correction.

## Current facts: resume here

- Gate 4 is accepted. Gates 0–2 remain frozen; Gate 3 hardened reproduction is verified. All 79 protected backend files still match the baseline.
- Gate 5 exists: typed API/session client, approved presets, durable jobs, submit/retry/cancel/reload, four persisted scientific views, provenance, cached results, responsive UI and browser tests. Do not rebuild it.
- The initial candidate passed independent typecheck/build, **8 browser tests and 5 static-serving tests**. Its independent Astra review found only **G5-R01** and **G5-R02**. That original evidence does not automatically accept the later corrections.
- Both production corrections are written. R01 preserves and renders aggregate/per-bin fallback diagnostics; R02 exposes explicit reconnect after recognized submission authentication errors. The original lost-response behavior is retained.
- Latest corrected browser run: **9 cases collected; 8 passed, 1 failed; 0 skipped, 0 flaky**, 427.169 seconds. Report: `../verification/gate5/correction-1-author-20260928/playwright-report.json`.
- The one reported failure is in `tests/e2e/test_reload.spec.ts:62`, repeated expectation at approximately line 67. The cache comparison expects the entire raw diagnostics object, including `failed_attempts: []`; the deliberate cache projection excludes `failed_attempts`.
- The new simulated submission-expiry recovery test passed, including the unrelated business-403 branch. Corrected source has **not** received Astra re-review. Gate 5 remains unaccepted and uncommitted.
- Parent independently inspected the corrected fallback panel and cache reload: 9 fallback rows; 8,229 fitted-bin and 9 source-remasked resolutions; bin 8 has evaluation 9/fallback 9/support 8. Mobile layout had no page-wide overflow. Evidence: `../verification/gate5/independent-review-20260927/correction-1-visual.json`.
- No coding agent is currently active. Prior Luna agents stopped; their code and evidence remain. Do not wait for a background completion notification that has already happened.

## Batch AG-G5-CLOSE — finish the existing browser candidate

Deliver this whole batch before asking Astra to review. It is closure of existing code, not a new frontend redesign.

### 1. Inspect only the necessary owners

Read `docs/gate5-review.md` for the exact findings and `docs/gate5-batch.md` for A1–A8. Inspect:

- `frontend/src/api/types.ts`: `SparseBinDiagnostics` and `StressCondition`.
- `frontend/src/api/client.ts`: `sanitizeForBrowserCache`.
- `frontend/src/components/ResultDetails.tsx`: `SparseBinDetails` and selected diagnostics.
- `frontend/src/hooks/useWorkbench.ts`: authentication classification, submission and reconnect flow.
- `frontend/src/App.tsx`: reconnect, readiness and pending-submit controls.
- `tests/e2e/test_reload.spec.ts`, `test_job_errors.spec.ts`, `test_flagship_preset.spec.ts` and their existing fixtures.

Use bounded reads and `rg` scoped to these files. Do not run a text search against minified `conditions.json`: a single matching line can emit the entire megabyte-sized artifact. Parse JSON and select the exact condition key instead.

### 2. Correct the cache regression expectation

Keep the cache projection limited to the intended aggregate diagnostic fields. Do not copy `failed_attempts` into the browser to make the failing equality pass.

Build an independent expected object from the real server record with exactly these fields:

```typescript
const expectedCachedDiagnostics = {
  affected_fallback_rows: diagnostics.affected_fallback_rows,
  resolution_counts: diagnostics.resolution_counts,
  bin_eval_counts: diagnostics.bin_eval_counts,
  bin_fallback_counts: diagnostics.bin_fallback_counts,
  bin_support: diagnostics.bin_support,
  bin_resolution_counts: diagnostics.bin_resolution_counts,
  bin_resolved_maps: diagnostics.bin_resolved_maps,
  sparse_prediction_failures: diagnostics.sparse_prediction_failures,
};
```

Before and after reload, assert deep equality against that expected object and separately assert the cached object does not contain `failed_attempts`. Do not call the production sanitization helper to construct the expected result, replace all checks with truthiness, delete the regression, or mask the failure with a skip.

Retain the actual-record assertions for condition `a15856cfceebf15e4520aa08`, key `logistic_regression__mcar_0_30__b50__source_fraction_binned_temperature`: 9 affected fallback rows, 8,229 fitted-bin resolutions and 9 source-remasked resolutions, including the bin-8 counts. Keep the distinction between whole-condition fallback and per-bin fallback in the UI. Missing diagnostics in an older cache must not be presented as proven zero fallback.

### 3. Finish both findings, without expanding scope

For R01, verify the selected real record, visible aggregate counts, per-bin counts, stored cache and reload. Values come from the persisted Python payload; do not derive scientific results in JavaScript.

For R02, retain the explicit authentication error-code allowlist. Current backend session errors are HTTP 401; an unrelated business 403 must not rotate the session. Verify a session rejected after successful bootstrap with no active jobs can visibly reconnect, replace invalid authority, keep cached evidence and make a new intentional submission without a manual reload. Explain that inaccessible old-session jobs/pending work cannot silently transfer to the replacement session.

Keep the accepted-job lost-response test passing: the first POST is actually accepted by the backend before its response is simulated as lost; retry must retain its original credentials/idempotency key and recover the same job. Do not equate an ambiguous transport failure with a definitive authentication rejection or replay an uncertain accepted run as a new session's job.

Allowed writes for this batch: `frontend/**`, `tests/e2e/**`, generated `shiftguard/static/**`, `docs/gate5-corrections.md`, and the already-authorized asset discovery adjustment in `tests/integration/test_static_boundaries.py` only if needed. Backend Python/science, migrations, data, accepted artifacts and original review evidence are protected. Parent owns final governance and commits.

### 4. Verify on an isolated attempt

Reuse the installed Node, Python and Chrome. Do not run dependency installation, browser installation, PostgreSQL provisioning or global Git configuration changes. The local frontend batch does not require PostgreSQL or a paid service. All evidence must be outside the application checkout.

Use these commands from the application root; capture each exit code immediately and stop to fix an actual failure before proceeding:

```powershell
Set-Location -LiteralPath 'C:\Users\Abhinav Anand\Downloads\nvidia\shiftguard'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
Remove-Item Env:SG_E2E_BASE_URL -ErrorAction SilentlyContinue
$attemptId = 'ag-g5-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$attemptDir = Join-Path 'C:\Users\Abhinav Anand\Downloads\nvidia\verification\gate5' $attemptId
New-Item -ItemType Directory -Path $attemptDir | Out-Null
$env:SG_GATE5_ATTEMPT_DIR = $attemptDir
$npmExe = 'C:\Program Files\nodejs\npm.cmd'

& $npmExe --prefix frontend run typecheck *> (Join-Path $attemptDir 'typecheck.log')
if ($LASTEXITCODE -ne 0) { throw 'Typecheck failed; inspect its log.' }
& $npmExe --prefix frontend run build *> (Join-Path $attemptDir 'build.log')
if ($LASTEXITCODE -ne 0) { throw 'Build failed; inspect its log.' }
& $npmExe --prefix frontend run test:e2e *> (Join-Path $attemptDir 'playwright.log')
if ($LASTEXITCODE -ne 0) { throw 'Browser suite failed; preserve attempt and inspect JSON report.' }
& .\.venv\Scripts\python.exe -B -m pytest tests/integration/test_static_boundaries.py -q -p no:cacheprovider --basetemp (Join-Path $attemptDir 'pytest-temp') --junitxml (Join-Path $attemptDir 'static-junit.xml') --tb=short *> (Join-Path $attemptDir 'static.log')
if ($LASTEXITCODE -ne 0) { throw 'Static boundary suite failed; inspect its log.' }
```

Expected current browser count is 9, all passing with no skips or flaky retries; explain any justified count change. Static suite expectation is 5 passing. Do not treat a launched process or an empty failure list during setup as success. Preserve JSON reports, logs, screenshots and run IDs. If a focused rerun is needed during debugging, give it a separate fresh attempt directory. After the final correction, run the integrated suite once; avoid repeating unaffected full Gate 4 tests/reproductions.

Chrome: `C:\Program Files\Google\Chrome\Application\chrome.exe`. Playwright owns port 8765. An older parent view-only preview may occupy 8875; do not terminate it or unrelated processes. If a stale test process blocks 8765, verify its exact command line, PID and attempt directory before stopping only that owned process. Do not connect tests to an arbitrary existing server. Use narrow execution permission escalation if the sandbox blocks the existing tools.

### 5. Freeze and hand off to Astra

Write `docs/gate5-corrections.md` with both finding IDs, cause, actual changed paths, regression names, exact commands/exit codes/counts, evidence directory, screenshots, and explicitly simulated branches. Mark the code ready for independent correction review; do not mark the gate accepted.

Check Git status with `git -c 'safe.directory=C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard' status --short`. Record HEAD and SHA-256 of changed source/static files. Compare the 79 protected hashes in `../verification/gate5/baseline.json`; all must match. Confirm generated assets match the source build. Preserve the original initial review, failed correction report and historical evidence. Freeze application edits before handoff.

Return one compact packet containing: candidate identity, changed files, G5-R01/R02 closure evidence, actual test results, artifact paths and any unresolved limitation. Do not claim Astra ran, copy the initial candidate's PASS into the corrected candidate, stage/commit/push, deploy or begin Gate 6 during this handoff.

## Astra correction-review request

Send this request back to Codex with Antigravity's completed handoff:

> Use GPT-6 Astra Extra High to re-review the frozen G5-R01/G5-R02 correction delta and affected invariants. Read docs/gate5-review.md, docs/gate5-corrections.md, the new source manifest and actual test reports. Independently confirm persisted per-bin fallback/cache behavior, submission-time auth recovery and preservation of accepted-job lost-response identity. Check generated assets and the protected backend hash comparison. Keep the original blocker verdict as history. Do not restart an unrelated codebase/Gate 4 audit. Return PASS or all reproducible material blockers in one packet. Parent binds the final verification to source and owns the source commit and separate governance checkpoint. Gate 5 stays pending until that acceptance is actually recorded.

An existing reviewer was `01a0e380-c345-7c92-b5b7-8cf212caafaa`; its availability must be checked, not assumed. A fresh Astra reviewer can use this compact packet if needed. Do not substitute a coding model for the independent reviewer or claim model dispatch without evidence.

## Next large batch: AG-G6-OFFLINE

Start only after the Gate 5 acceptance checkpoint is recorded. Follow `docs/gate6-batch.md`, updated to Antigravity ownership. Deliver the whole bounded agent product in one integrated coding batch:

1. Strict argument/result schemas and the exact twelve-tool registry mapped to existing scientific/API owners.
2. Async provider adapter, finite timeouts/retries, sanitized errors and disabled-without-credentials behavior.
3. Serial controller with original tool-call IDs, six-turn/eight-call caps, one invalid-call correction and server-side authorization.
4. Durable request/tool/job linkage, retry identity, session authority and existing queue/continuation integration; forward migrations only if actually necessary.
5. Persisted-evidence reference validation and deterministic rendering so unsupported model numbers, arbitrary code/paths/SQL/URLs and final labels cannot enter successful results.
6. Browser request/tool/result trace, waiting/recovery states and continued access to all Gate 5 preset/cache features during provider failure.
7. Contract, negative, continuation, grounding, failure and browser tests plus a complete batch handoff.

Do not split this into seven separate approval cycles or deliver disconnected stubs. Use a dependency order internally, integrate end to end, self-verify, then freeze for one Astra review. Keep backend computation and existing durable ownership rules authoritative. Check current official provider documentation and the installed SDK at implementation time; the old blueprint is not proof that a model or account feature is available today.

Offline mocked-provider success is **not** live Gate 6 acceptance. Implement and test all work that does not require credentials without waiting for them. The exact-model live canary and flagship run/read/compare path form the final evidence step after user access and budget authorization.

## Later phase boundaries

| Batch | Integrated deliverable | Exit requirement |
| --- | --- | --- |
| AG-G6-LIVE | Exact-model chat/tool/structured-output canaries and actual natural-language run/read/compare | Redacted real provider evidence, persisted experiment references, observed usage, tested fallback and Astra acceptance. |
| AG-G7 | Adversarial grounding, tool injection, unauthorized input, provider failures/replay/quotas and held-out agent evaluation | No unsupported rendered evidence in the required tests; measured live evaluation only with authorized usage. |
| AG-G8 | Predeclared protocol lock and Bank paired-repeat statistical suite | Lock both dataset protocols before unsealing; preserve adverse/null results and uncertainty; scientific decisions require explicit review. |
| AG-G9 | Adult replication using the same frozen engine | Official split/identity protections and accepted replication evidence; no premature access to sealed outcomes. |
| AG-G10 | Hosted judge product and restart persistence | Explicit destination/access, public browser tests, persistence proof and no exposed secrets. |
| AG-G11 | Submission freeze | Verified source tag/image identity, backups, final video/description/judge package and explicit publication authorization. |

These are sequencing boundaries, not authorization to open all gates at once. Keep each batch's source scope and acceptance criteria explicit. Do not spend paid credits, change accounts, publish or unseal research under a generic coding instruction.

## What the user must do

1. Paste this packet into Antigravity and let it complete **AG-G5-CLOSE** in the existing checkout. No installation, key, payment or scientific decision is required for that batch.
2. Return its single evidence handoff to this Codex conversation for Astra review. Do not alternate reviewers after every small edit.
3. For live Gate 6 only: provide a Nebius Token Factory key through local secret storage, access to the requested model, and an explicit allowed usage budget. Do not paste secrets into chat. Until then, complete offline work and label live evidence blocked.
4. Deployment destination, publishing actions and confirmatory choices are later explicit inputs. They do not block the current frontend closure.
