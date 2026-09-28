# G5-01 consolidated independent review

**Verdict: BLOCKERS — G5-R01 and G5-R02.** Completed 28 September 2026 (Asia/Calcutta). This is the bounded application review, not source acceptance, gate closure, or authorization to commit.

## Candidate and review boundary

- Base HEAD: `475b4b7fc7a3c5fb87396aac7e75d035343628df`.
- Frozen manifest: `../verification/gate5/independent-review-20260927/source-manifest.json`; source digest `3943dc28ed294c052d35724df4369ccdea686f829f0152ea4a46e575da2599eb`.
- All 36 manifest file hashes matched during the focused probes. The subsequently inspected parent `../verification/gate5/independent-review-20260927/validation.json` independently confirms all 36 application files and all 79 protected backend files unchanged, plus matching visual static hashes. Parent owns governance and binding a later corrected candidate.
- Reviewed the scoped diff, all new frontend source and browser tests, build/test harness, generated asset references, dependency-lock changes, and the static-boundary test update. Backend reads were limited to the API/auth contracts needed to assess frontend behavior. No Gate 4/science reaudit.
- Ownership remains Luna `xhigh` for application corrections and Astra `xhigh` for independent review; no Antigravity. This review changed only this document and external `reviewer-*` evidence. No application fixes, commits, deployments, or server lifecycle changes.

## Material findings — one correction batch

### G5-R01 [P2] Preserve and expose actual per-bin fallback diagnostics

**Contract:** G5-A4 actual fallback details must be inspectable; G5-A3 displayed diagnostics must remain bound to the persisted selected record.

**Locations:** `frontend/src/api/client.ts:189-209` constructs a reduced condition without `sparse_bin_diagnostics`; `frontend/src/api/types.ts:136-154` omits that field; `frontend/src/components/ResultDetails.tsx:68-74` presents only whole-condition fallback fields.

**Concrete trigger:** Open the real published stress experiment `d8a18a371c8c88ee20ba1087`; select Logistic regression, Cellwise MCAR 30%, Source fraction binned, budget 50. The selected condition is `a15856cfceebf15e4520aa08` (`logistic_regression__mcar_0_30__b50__source_fraction_binned_temperature`). Its persisted `sparse_bin_diagnostics` records **9 affected fallback rows**, with **8,229 fitted-bin resolutions and 9 source-remasked resolutions**. The same omission also affects the corresponding random-forest record.

**Actual:** The panel labeled “Actual fit and fallback details” shows Source fraction binned → Source fraction binned, fitted/scored, “Fallback chain: None recorded”, “Fallback reason: None recorded”, and 0/0 fit/prediction failures. The aggregate fields themselves match the payload, but the recorded per-bin fallback is not inspectable anywhere in the product. `saveExperiment` sanitizes the payload before placing it in live state, so the detail is lost even before reload; it is also absent from the browser cache afterward. A successful fit and zero failures do not imply that no rows used fallback.

**Expected:** Retain the persisted aggregate/per-bin fallback diagnostics needed by this view and display their actual affected-row and resolved-map counts for the selected condition, including after cache reload. Distinguish whole-condition fallback from per-bin fallback. Display the existing Python results without deriving new scientific values or changing the backend.

**Proof:** `reviewer-probes.json`, probe `real-persisted-sparse-fallback`; `reviewer-sparse-fallback.png`. The probe uses the unmodified real published payload and asserts this condition equals the author-run `conditions.json` record. Both initial display and reload reproduce the omission; no browser exceptions occurred. The existing flagship test checks another method and does not assert this fallback behavior.

**Owner/regression:** Luna; typed payload/cache projection, selected diagnostics, and one browser regression using this persisted condition before and after reload.

### G5-R02 [P2] Offer session recovery after a submission receives an authentication rejection

**Contract:** G5-A6 requires explicit expired-session behavior and usable recovery; G5-A2 requires session-bound submission identity to remain correct through recovery.

**Locations:** `frontend/src/hooks/useWorkbench.ts:104-108` treats submission-time 401/403 as an online API error without clearing readiness or invoking session recovery. `frontend/src/App.tsx:149` only exposes Reconnect when offline or not ready; `frontend/src/App.tsx:177` disables new submission while the rejected pending submission remains stored.

**Concrete trigger:** Successfully bootstrap a session with no active jobs; let it expire or become invalid before the next Submit run. The existing backend authentication contract can return HTTP 401 `SESSION_EXPIRED` or `INVALID_SESSION_CREDENTIALS` for that POST.

**Actual:** The error is visible, but the UI still says “API connected”, has **zero Reconnect buttons**, disables Submit run, and offers only “Retry same submission”. That action resends the same invalid credentials and repeats the rejection. With no active job to trigger the separate polling authentication handler, there is no in-product path to obtain a new session. A manual browser reload happens to recover through the startup validation path; the error does not explain that workaround.

**Expected:** Route definitive submission authentication failures into the existing explicit session-replacement/reconnect flow. Preserve cached evidence, explain the disposition of old-session private jobs/pending work, and make a new authorized submission possible without an unexplained reload. Continue retaining the original session and idempotency key for genuinely ambiguous transport/response-loss retries; do not silently replay an uncertain accepted run as a new session's job.

**Proof:** `reviewer-probes.json`, probe `submit-time-session-expiry`; `reviewer-submit-expiry.png`. A focused browser probe supplied the existing API's 401 response shape after successful bootstrap and confirmed two rejected attempts, retained pending state, disabled Submit run, zero recovery buttons, and no browser exceptions. This is an explicitly simulated authentication failure, not a real session-expiry or worker-failure test. The existing expiry test intercepts session validation during reload, so it does not cover this branch.

**Owner/regression:** Luna; submission/auth recovery state and a browser regression for expiry after bootstrap with no active jobs. Keep the existing accepted-job lost-response identity test passing.

## A1–A8 assessment and proof

| Contract | Review assessment |
| --- | --- |
| A1 | Supported. Same-origin built product, typed approved-preset request body, server-issued capability session, no arbitrary dataset/path/code controls. Real stress, outage and baseline browser paths passed. |
| A2 | Supported for normal submit/poll, intentional rerun and reload, plus lost-response replay using the same accepted job/key. Credentials are header-bound; capability tokens do not enter rendered request facts or URLs. Submission-time auth recovery remains affected by G5-R02. |
| A3 | Four views select stored numeric payloads; tested predictor/scenario/method/budget/metric/cost changes bind to persisted records. Reliability/decision-loss fixed budget 50 and pattern comparison budget are disclosed. Null/failed values remain unavailable. The explicitly labeled perfect-calibration reference is not an empirical series. Actual fallback inspection is incomplete under G5-R01. |
| A4 | **Blocked by G5-R01.** Logical/condition identity, provenance hashes, single-seed illustrative labeling and matching qualification are present; per-bin fallback is discarded. Adverse stored scores are not rewritten. |
| A5 | Supported for retained cached stress during simulated new-job failure, network loss and reload; cached versus fresh sources are labeled. The review found no additional blocker in this scoped behavior. |
| A6 | **Blocked by G5-R02.** Existing tests support lost-response retry, cancellation request/terminal outcome, worker failure, startup expiry recovery and storage/network notices, with simulation limits below. |
| A7 | Supported by numeric/table equivalents, named controls, keyboard/mobile browser checks, and parent desktop/mobile observations with matching static hashes. Parent owns visual acceptance. |
| A8 | Required parent verification passed: 8 browser tests, 0 skipped/unexpected/flaky; 5 static-boundary tests; typecheck and build exit 0. Config uses `../tests/e2e`, managed same-origin FastAPI with built assets and isolated storage; external hosted mode requires explicit `SG_E2E_BASE_URL`. Passing tests do not resolve the two uncovered defects. |

Parent evidence read directly from `../verification/gate5/independent-review-20260927/parent-attempt/`: `commands.json`, `playwright-report.json`, `static-junit.xml`, `typecheck.log`, `build.log`. Browser duration was 304,935.47 ms; the static JUnit suite reports 5 tests and zero failures/errors/skips. The author report independently records 8/8 with zero skips/unexpected/flaky, but is supporting evidence rather than the acceptance decision. Parent visual evidence is `../verification/gate5/parent-visual-20260927/observations.json`.

Parent `validation.json` binds those results to the same frozen source digest and records `INDEPENDENT_CHECKS_PASSED_REVIEW_PENDING`, no source commit, and gate acceptance pending. This completed review supplies the blocker verdict; it does not alter that parent-owned record.

The stress run, identical stress rerun, outage run and baseline run use real workers and persisted results. The lost-response test forwards to the real acceptance endpoint and then simulates loss of its response. Worker-failure/cancellation outcomes, expiry/network/storage faults and unavailable-record branches are intercepted fixtures; they demonstrate client behavior, not real worker outage/cancellation fault handling. These limitations are disclosed in the implementation handoff and do not themselves create another blocker.

## Focused review evidence and limits

External directory: `../verification/gate5/independent-review-20260927/`.

- `reviewer-probes.mjs`: reproducible probes against the frozen generated assets; run from the application root with `node ../verification/gate5/independent-review-20260927/reviewer-probes.mjs`.
- `reviewer-probes.json`: exact observed outcomes, source digest and 36-file hash check. Probe command exited 0; assertions confirm the two defects, not acceptance.
- `reviewer-submit-expiry.png` and `reviewer-sparse-fallback.png`: captured rendered states.

The probes fulfill the built files directly from disk in isolated browser contexts and intercept all browser API requests. The only preview-server traffic was read-only retrieval of three already-published experiment envelopes. No worker job was submitted by the reviewer, no server was started or stopped, and no full parent suite was duplicated. Numerical computation and final labels remain in Python; no frontend scientific recomputation was introduced or requested.

The relocated historical focused attempt is not an acceptance blocker and was not moved by this reviewer. The existing Plotly chunk-size warning is non-blocking; no optional improvement is a condition of this verdict.

**Next action:** Luna fixes G5-R01 and G5-R02 together and supplies affected regressions. Astra reviews the correction delta and affected contracts; parent binds the final evidence and owns source/gate acceptance. Keep this original blocker verdict as history.
