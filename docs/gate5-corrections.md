# Gate 5 correction handoff — G5-R01 and G5-R02 closure

Application edits are frozen for independent Astra correction review. This packet records the complete resolution of blockers G5-R01 and G5-R02 in batch **AG-G5-CLOSE**, the isolated verification evidence, and the frozen candidate manifest. Gate 5 remains uncommitted and unaccepted until independent review and parent acceptance are recorded.

## Candidate identity and baseline integrity

- **Base HEAD:** `475b4b7fc7a3c5fb87396aac7e75d035343628df`
- **Accepted Gate 4 source:** `10170feab3c16c5eb61153d57d9e5879ba5a6fd6`
- **Candidate source digest:** `0e961a563ca38f02074b86a95c67fac8267b26f27182a8dab9a2f1256e28f492`
- **Tracked application files:** 36 files verified. Exactly 1 file (`tests/e2e/test_reload.spec.ts`) updated in this correction delta compared to handoff checkpoint `cd96b3b0345376ccd50bdb45132100f38407e558bccbd54318054e7630d5a59b`.
- **Protected backend files:** All 79 protected files compared against `../verification/gate5/baseline.json`; 0 mismatches, 0 additions, 0 modifications.
- **Generated static assets:** Rebuilt via Vite production build and confirmed matching `shiftguard/static/**`.

## Finding closure ledger

### G5-R01: Preserve and expose actual per-bin fallback diagnostics

- **Defect and cause:** The original candidate's client sanitization (`frontend/src/api/client.ts`) and type definitions (`frontend/src/api/types.ts`) discarded `sparse_bin_diagnostics` from persisted condition records. The UI (`frontend/src/components/ResultDetails.tsx`) only exposed whole-condition fallback fields, falsely implying "None recorded" even when rows used per-bin fallback.
- **Production resolution:**
  1. `frontend/src/api/types.ts`: added `SparseBinDiagnostics` typing the 8 aggregate and per-bin diagnostic fields (`affected_fallback_rows`, `resolution_counts`, `bin_eval_counts`, `bin_fallback_counts`, `bin_support`, `bin_resolution_counts`, `bin_resolved_maps`, `sparse_prediction_failures`).
  2. `frontend/src/api/client.ts`: in `sanitizeForBrowserCache`, projected these 8 fields into the cached condition while excluding internal raw telemetry (`failed_attempts`).
  3. `frontend/src/components/ResultDetails.tsx`: rendered `SparseBinDetails` displaying affected fallback rows, aggregate resolution counts, sparse prediction failures, and a per-bin breakdown table. Preserved clear distinction between whole-condition fallback and per-bin fallback.
- **Regression test & closure proof:**
  - `tests/e2e/test_reload.spec.ts`: selects real condition `a15856cfceebf15e4520aa08` (`logistic_regression__mcar_0_30__b50__source_fraction_binned_temperature`).
  - Verifies visible counts: **9 affected fallback rows**, **8,229 fitted-bin resolutions**, **9 source-remasked resolutions**, bin 8 evaluation 9 / fallback 9 / support 8 / source-remasked 9, and whole-condition fallback chain "None recorded".
  - Verifies cache projection before and after page reload: asserts deep equality against an independently constructed expected object with the 8 allowed diagnostic fields from the server record, and explicitly asserts `failed_attempts` is not in the cached diagnostics.

### G5-R02: Offer session recovery after a submission receives an authentication rejection

- **Defect and cause:** Submission-time HTTP 401/403 was previously treated as a general API error without clearing readiness or initiating session recovery. The product remained in "API connected" state with zero Reconnect buttons and only "Retry same submission", which endlessly repeated invalid credentials with no in-product recovery.
- **Production resolution:**
  1. `frontend/src/hooks/useWorkbench.ts`: defined `SESSION_AUTH_CODES` allowlist (`MISSING_SESSION_CREDENTIALS`, `INVALID_SESSION_CREDENTIALS`, `SESSION_EXPIRED`, `INVALID_CAPABILITY_TOKEN`). On submission HTTP 401 with these codes, sets `ready = false`, records an informative error notice explaining old jobs/pending work cannot transfer to a new session, and logs activity.
  2. `frontend/src/App.tsx`: renders `Reconnect` whenever `ready === false` and backend is not actively checking; hides "Retry same submission" when session is invalid.
  3. Reconnect flow clears the invalid pending submission, creates a new authorized session, preserves cached published results, and re-enables "Submit run" for fresh intentional submissions.
  4. Preserved existing accepted-job lost-response retry identity: transport retries reuse the original credentials and idempotency key to recover the existing job rather than duplicating submissions.
- **Regression test & closure proof:**
  - `tests/e2e/test_reload.spec.ts` (`[simulated] submission session expiry reconnects and allows a new authorized submission`):
    - Submits a run that receives simulated 401 `SESSION_EXPIRED`.
    - Confirms alert displays `SESSION_EXPIRED` and notice that pending submission will be discarded.
    - Confirms `Reconnect` button is visible, `Retry same submission` is absent, and `Submit run` is disabled.
    - Clicks `Reconnect`: verifies transition to `SESSION_REPLACED`, new session ID assigned, cached results retained, and `Submit run` enabled.
    - Submits again: confirms new job accepted with a different session ID and distinct idempotency key.
    - Follow-up check: verifies business-rule 403 error does not trigger reconnect and retains standard retry controls.

## Isolated verification evidence

Executed from clean PowerShell environment with Python thread limits set to 1 and isolated attempt directory:

- **Attempt ID:** `ag-g5-20260929-012222-0fb15873`
- **Attempt directory:** `C:\Users\Abhinav Anand\Downloads\nvidia\verification\gate5\ag-g5-20260929-012222-0fb15873`

### Exact commands and exit codes

```powershell
Set-Location -LiteralPath 'C:\Users\Abhinav Anand\Downloads\nvidia\shiftguard'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
Remove-Item Env:SG_E2E_BASE_URL -ErrorAction SilentlyContinue
$attemptId = 'ag-g5-20260929-012222-0fb15873'
$attemptDir = 'C:\Users\Abhinav Anand\Downloads\nvidia\verification\gate5\ag-g5-20260929-012222-0fb15873'
$env:SG_GATE5_ATTEMPT_DIR = $attemptDir
$npmExe = 'C:\Program Files\nodejs\npm.cmd'

& $npmExe --prefix frontend run typecheck *> (Join-Path $attemptDir 'typecheck.log')
# Exit code: 0

& $npmExe --prefix frontend run build *> (Join-Path $attemptDir 'build.log')
# Exit code: 0

& $npmExe --prefix frontend run test:e2e *> (Join-Path $attemptDir 'playwright.log')
# Exit code: 0

& .\.venv\Scripts\python.exe -B -m pytest tests/integration/test_static_boundaries.py -q -p no:cacheprovider --basetemp (Join-Path $attemptDir 'pytest-temp') --junitxml (Join-Path $attemptDir 'static-junit.xml') --tb=short *> (Join-Path $attemptDir 'static.log')
# Exit code: 0
```

### Test counts and execution summary

| Suite | Expected | Passed | Failed | Skipped | Flaky | Duration | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TypeScript check | 0 errors | Pass | 0 | 0 | 0 | ~7s | `typecheck.log` |
| Vite production build | 0 errors | Pass | 0 | 0 | 0 | ~8s | `build.log` |
| Playwright browser E2E | 9 | 9 | 0 | 0 | 0 | 414.99s (~6.9m) | `playwright-report.json`, `playwright.log` |
| Pytest static boundaries | 5 | 5 | 0 | 0 | 0 | 3.36s | `static-junit.xml`, `static.log` |

### Playwright 9-test breakdown

1. `test_flagship_preset.spec.ts`:
   - `real worker stress payload binds every chart, table and filter; identical rerun restores job identity` -> **PASSED** (real worker, seed 31001)
   - `real bank-outage-50 preset publishes a readable result` -> **PASSED** (real worker)
   - `real bank-baseline preset publishes a readable result` -> **PASSED** (real worker)
2. `test_job_errors.spec.ts`:
   - `[simulated] lost response after real acceptance retries the original job across reload` -> **PASSED**
   - `[simulated] worker failure and cancellation outcomes retain cached evidence` -> **PASSED**
   - `[simulated] expired session, network loss and storage failure recover explicitly` -> **PASSED**
3. `test_reload.spec.ts`:
   - `persisted cache survives reload with private credentials and keyboard/mobile access` -> **PASSED** (G5-R01 per-bin fallback and 8-field cache projection verified before/after reload)
   - `[simulated] submission session expiry reconnects and allows a new authorized submission` -> **PASSED** (G5-R02 submission 401 expiry, reconnect, session replacement, and business 403 verified)
   - `[simulated] unavailable records remain explicit and corrupt storage has a usable empty state` -> **PASSED**

### Static boundary 5-test breakdown

1. `test_built_entry_asset_has_javascript_mime_type_and_product_content` -> **PASSED**
2. `test_missing_static_asset_is_a_404_not_spa` -> **PASSED**
3. `test_api_prefix_never_falls_back_to_spa[/api]` -> **PASSED**
4. `test_api_prefix_never_falls_back_to_spa[/api/]` -> **PASSED**
5. `test_api_prefix_never_falls_back_to_spa[/api/unknown]` -> **PASSED**

### Captured artifacts and visual records

- Desktop render: `screenshots/gate5-flagship-desktop.png` (304,480 bytes)
- Mobile render: `screenshots/gate5-result-mobile.png` (297,242 bytes)
- Isolated SQLite database: `shiftguard.sqlite` (11,636,736 bytes)
- Seeding & server logs: `seed-cli.log`, `seed-stress.yaml`, `worker-browser-evidence.json`, `server.stop`

## Explicitly simulated branches and disclosed limits

- **Real worker executions:** Flagship stress, bank-outage-50, and bank-baseline presets execute against embedded real Python workers producing real persisted payloads.
- **Simulated client branches:**
  1. Lost-response retry: first POST is actually accepted by the backend before the response is simulated as lost; retry recovers the real accepted job.
  2. Submission session expiry: routes 401 `SESSION_EXPIRED` to test client reconnect and session replacement.
  3. Worker failure, cancellation, storage corruption, and unavailable records: mock specific client failure states to prove defensive frontend resilience.
- **Vite bundle notice:** Vite emits an advisory warning that `Plot-DUZzS8HM.js` exceeds 500 kB due to Plotly.js bundling; this was previously confirmed non-blocking.
- **Backend changes:** Zero backend Python or science modifications made. All 79 protected files remain identical to baseline.

## Review handoff status

All material findings (G5-R01 and G5-R02) are closed with green end-to-end evidence. Application source is frozen. The packet is ready for GPT-6 Astra Extra High independent correction review. Gate 5 remains uncommitted and pending acceptance.
