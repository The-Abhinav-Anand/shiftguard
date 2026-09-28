# Gate 5 correction review — G5-R01 / G5-R02

**Verdict: PASS. Both original material findings are resolved on the identified candidate; no reproducible material blocker remains in the correction delta or affected invariants.** Reviewed 29 September 2026 (Asia/Calcutta). Parent source acceptance, commit and gate closure remain pending.

## Candidate and boundary

- Base HEAD: `475b4b7fc7a3c5fb87396aac7e75d035343628df`.
- Reviewed source digest: `0e961a563ca38f02074b86a95c67fac8267b26f27182a8dab9a2f1256e28f492`.
- Current manifest: `../verification/gate5/correction-review-20260929/source-manifest.json`. Parent reconstructed this current 36-file map and matched the declared digest; a separate newer author manifest was not supplied. This review uses the reconstructed manifest, not an assumed author artifact.
- Compared with `../verification/gate5/antigravity-handoff-20260928/checkpoint.json`, only `tests/e2e/test_reload.spec.ts` changed. The production corrections were already present before that handoff. Antigravity's correction changes the two cache expectations to the intended eight-field projection and explicitly excludes `failed_attempts`.
- Compared with the initial reviewed candidate, the relevant production changes are in `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/components/ResultDetails.tsx`, `frontend/src/hooks/useWorkbench.ts` and `frontend/src/App.tsx`, with regenerated assets and affected browser coverage. Review included the unchanged workspace persistence and retry dependencies needed to assess those changes.
- Current ownership is **Antigravity codes; Astra Extra High reviews**. Historical Luna authorship and the original review are preserved. This reviewer wrote only this document and external `reviewer-*` evidence.

Parent's completed `validation.json` records 36/36 application files and 79/79 protected backend files matching, the original review unchanged, and all four fresh externally built assets byte-identical with no extra static files. These are parent verification results, not a duplicate reviewer backend audit. The focused probes separately checked the 12 source/test/static files they relied on against the current manifest before and after execution.

## Finding closure

### G5-R01 — PASS: persisted per-bin fallback survives selection and cache reload

`frontend/src/api/types.ts:136` defines the eight diagnostic fields. `frontend/src/api/client.ts:205` explicitly retains their persisted values, including nested per-bin resolution counts, while omitting `failed_attempts`. `frontend/src/components/ResultDetails.tsx:41` displays the aggregate counts, sparse prediction failures and per-bin evaluation/fallback/support/resolution details. Its whole-condition fallback label at line 130 distinguishes that separate contract. Counts are selected and formatted; no scientific values are recomputed.

Independent probes used the existing author database read-only and compared the selected condition directly with its actual `conditions.json` artifact. For experiment `d8a18a371c8c88ee20ba1087`, condition `a15856cfceebf15e4520aa08`, key `logistic_regression__mcar_0_30__b50__source_fraction_binned_temperature`, the built UI and cache preserve:

- 9 affected fallback rows; 8,229 fitted-bin resolutions; 9 source-remasked resolutions; persisted zero counts remain present.
- Bin 8: evaluation 9, fallback 9, support 8, resolved map source-remasked temperature, and exact resolution counts including the recorded zeros.
- All eight allowed cache fields equal the artifact-derived projection; `failed_attempts` is absent before and after reload.
- Whole-condition fallback remains “None recorded”, separately from the visible per-bin fallback.

The same assertions passed for random-forest condition `e1194f7c2e81e5bdcd8c966e`. Switching to a method without sparse diagnostics removes the per-bin panel, so it does not retain the previous selection's values. Both predictors passed again after reload with experiment list/result retrieval blocked; only one successful result-envelope read occurred in the entire probe. This verifies browser-cache persistence rather than a hidden result refetch.

**Regression semantics:** `tests/e2e/test_reload.spec.ts:60` now builds its expected cache object from the actual server diagnostics. Both deep-equality assertions and explicit telemetry exclusions remain. The earlier raw-object expectation incorrectly included `failed_attempts`; correcting that expectation does not weaken the required scientific diagnostics. The author test's loose table-row text assertions are supplemented here by exact per-cell checks and both predictor identities. Parent independently reran this test with keyboard/mobile coverage successfully.

### G5-R02 — PASS: definitive submission-authentication rejection has explicit recovery

`frontend/src/hooks/useWorkbench.ts:113` recognizes HTTP 401 only when its code is in the four-code session-authentication allowlist. Those codes match the existing contract in `shiftguard/api/auth.py`. It clears readiness, explains the rejected pending submission and old private-job disposition, and preserves published cached results. `frontend/src/App.tsx:149` exposes Reconnect; line 191 suppresses invalid-session retry. Reconnect revalidates the old credentials, clears the rejected pending intent on definitive rejection, and obtains a replacement session before a new intentional submission.

Four separate focused probes covered `SESSION_EXPIRED`, `INVALID_SESSION_CREDENTIALS`, `INVALID_CAPABILITY_TOKEN` and `MISSING_SESSION_CREDENTIALS`, including both supported error-envelope shapes. Each started after successful bootstrap with **no active jobs**, then verified:

- A visible authentication notice and Reconnect control; Submit disabled and invalid-session retry absent.
- No automatic session rotation or resubmission before the explicit reconnect action.
- Replacement session/token, pending intent cleared, cached payload preserved, and no automatic replay during reconnect.
- A subsequent explicit Submit uses the replacement credentials and a different idempotency key.

An independent business-rule HTTP 403 probe retained the original session, credentials, complete pending object and retry key/body through a repeated rejection. It did not expose Reconnect or create a replacement session.

**Affected identity invariant — PASS:** separate HTTP 503 response-loss and transport-abort probes preserved the entire pending object, credentials, request body and idempotency key across recovery/reload. Retry restored one simulated accepted job; a later intentional submission used a new key. These two probes use a simulated acceptance registry solely to inspect frontend identity. The parent's fresh lost-response test supplies the real acceptance proof: it forwards the first submission to the actual backend, replaces that response with a 503, reloads, retries the same key, observes the same job ID and waits for real completion.

## Evidence and acceptance mapping

External correction evidence root: `../verification/gate5/correction-review-20260929/`.

| Evidence owner | Actual result | Evidence |
| --- | --- | --- |
| Independent reviewer | 8 focused probes passed; 0 failed/skipped; exit 0; no uncaught browser exceptions or unexpected requests | `reviewer-probes.mjs`, `reviewer-probes.json`, `reviewer-sparse-fallback.png`, `reviewer-submit-expiry.png` |
| Parent | Typecheck and external production build exit 0; 4/4 built files match frozen assets | `parent-attempt/commands.json`, `typecheck.log`, `build.log`, `generated-assets-comparison.json` |
| Parent | 3 affected browser cases passed; 0 unexpected/skipped/flaky; 173,158.095 ms | `parent-attempt/playwright-report.json` |
| Parent | 5 static tests passed; 0 failures/errors/skips; 5.439 s; two existing deprecation warnings | `parent-attempt/static-junit.xml`, `static.log` |
| Author, supporting evidence | 9 browser cases passed; 0 unexpected/skipped/flaky; 5 static tests passed | `../ag-g5-20260929-012222-0fb15873/playwright-report.json`, `static-junit.xml`, relative to the correction evidence root |

The parent JSON/XML reports, command outcomes, generated-assets comparison and final `validation.json` were read directly. Author results remain labeled author evidence. Parent validation binds raw report hashes and the current source digest while explicitly retaining `acceptance: PENDING`.

| Affected contract | Assessment |
| --- | --- |
| G5-A2 | Session-bound request identity is retained for ambiguous retries; explicit recovery permits a distinct authorized intent. |
| G5-A3 / G5-A4 | Actual aggregate and per-bin diagnostics remain tied to the selected persisted condition, including cached reload. |
| G5-A5 / G5-A6 | Published cache survives rejection/recovery; submission-time authentication recovery is usable without an unexplained reload. |
| G5-A7 / G5-A8, affected portion | Parent keyboard/mobile reload case, three affected browser cases, typecheck/build and static boundaries pass. |

No unaffected acceptance item, Gate 4 scientific result or backend suite was reopened.

## Reproduction and limits

From the repository root, using the existing Node/Chrome/Python installations:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
& 'C:/Program Files/nodejs/node.exe' '../verification/gate5/correction-review-20260929/reviewer-probes.mjs'
# Final run: exit 0; 8 passed, 0 failed, 0 skipped.
```

The probes fulfill the frozen built files directly from disk in isolated Chrome contexts and intercept all browser transport. Their real numerical input is the existing persisted stress record and exact artifact JSON. Authentication failures and the reviewer's acceptance registry are simulated client branches, not demonstrations of actual expiry, worker failure or backend idempotency. No server was started or contacted on 8765 or 8875; no worker run, full suite, rebuild, installation or paid API call was performed by this reviewer.

Probe-harness history is preserved in `reviewer-harness-attempt1.json`: seven cases passed; the initial exact-cell expectation omitted the persisted zero-resolution entries that the application correctly displayed. The external probe expectation was corrected to include every persisted resolution entry; the final eight-case run passed. An earlier extraction setup attempt used lowercase publication status and stopped before browser execution; the read-only query was corrected to the stored `PUBLISHED` value. Neither issue required an application change.

The original `docs/gate5-review.md` remains byte-identical before/after this review, SHA-256 `e80a4d8f56aa66d1ac5b54f51e10feb57c171575c2393e2339cf0d002fcc8f47`. No application or governance edits, commit, deployment or gate-acceptance mutation occurred.

**Next owner/action:** Parent binds this PASS and the completed independent evidence to the frozen candidate and performs its separate acceptance/checkpoint decision. No further correction is requested by this review.
