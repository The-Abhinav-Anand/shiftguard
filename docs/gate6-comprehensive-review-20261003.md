# Gate 6 comprehensive review and corrections — 3 October 2026

Status: IN_PROGRESS. This is the user-authorized broader Gate 6 review following the bounded C01/C02 acceptance. Historical review verdicts and the prior 562-test source-bound run remain unchanged. No source commit, deployment, live provider call, or Gate 6 acceptance is authorized by this record.

Evidence: `../../verification/gate6-comprehensive-20261002/`. The interrupted 2 October attempt is retained; review resumed on 3 October after the shared usage window reset (2% used at resumption). Respect the user's 80% account-window ceiling; check between batches.

## Confirmed grounding findings

Read-only reproduction: `.venv/Scripts/python.exe -B ../verification/gate6-comprehensive-20261002/grounding-probes.py`. Original observations: `grounding-before.json`.

| ID | Contract | Reproduction and effect | Correction ownership |
| --- | --- | --- | --- |
| G6-C03 | A1 | `compare_calibrators` accepts false, 0.0 and 50.0 as literal integer budgets despite strict schemas; false becomes 0. Same LabelBudget alias is used by compare_outages. | Luna grounding batch |
| G6-C04 | A4 | The handler and final projector remove legitimate `mixed`/`empty` bin states; actual calibration code emits both. | Luna grounding batch |
| G6-C05 | A4 | Actual persisted 400-condition Bank masks contain eight rate groups; final inspect_missingness projection removes all eight via generic scalar-only dictionary filtering. | Luna grounding batch |
| G6-C06 | A4 | Explicit log_loss=null alongside valid Brier/ECE is removed by nested model serialization. The renderer's explicit unavailable-observation branch can no longer see it. | Luna grounding batch |
| G6-C07 | A4 | Actual saved five-point budget curve passes the registry with five available values, but the renderer emits zero claims and says no authorized published evidence exists. | Luna grounding batch |

These are scoped input/output-boundary defects. Scientific computation and accepted result bytes are protected. C06's probe is a supported adverse-value fixture, not a claim that the historical 400-condition run had a null log loss.

## Correction batch G6-GROUNDING-03

Writer: GPT-6 Luna xhigh. Exclusive source paths: `shiftguard/agent/schemas.py`, `shiftguard/agent/tools/results.py`, `shiftguard/agent/tools/projections.py`, `shiftguard/agent/rendering.py`, and, only if necessary, `shiftguard/agent/tools/metadata.py`. New regression file: `tests/agent/test_g6_comprehensive_grounding.py`. No other application or governance writes.

1. Require actual integer types before validating allowed budget literals. Reject bool, float, string, null, unsupported integers before handlers; preserve defaults and approved integer values.
2. Preserve mixed/empty only in bin_resolved_maps. Do not admit these strings as real methods or resolution-count names. Retain malformed-key/value and secret-field rejection.
3. Preserve the already-sanitized nested missingness rates for both Gate 2 and Gate 3 layouts through the final dispatch boundary. Do not bypass existing numeric, identifier, or field allowlists.
4. Preserve explicitly present null metrics through condition serialization, without inventing metrics absent from the source. Ensure the deterministic renderer retains their unavailable observations alongside healthy claims.
5. Test the complete registry/handler/projection/renderer path using an isolated published-record fixture as appropriate. Include hostile nested fields and valid controls. Keep tests focused on observable contracts.
6. Run the new regressions and affected existing grounding/registry suites, capturing exact commands/results. Parent owns final integrated verification and independent correction review.
7. C07: add deterministic budget-curve observations bound to the already validated experiment/condition/metric references. Preserve budget, requested/resolved method, labels consumed and unavailable points. Do not invent improvements, interpolate missing budgets, or lose unavailable points when a healthy explanation plan is selected. Reproduction: `budget-render-probe.py`, observations `budget-render-before.json`; the registry uses actual saved payload with an isolated repository read substitution, not a live database call.

## Parallel independent reviews

- GPT-6.1 Sol xhigh: controller/store, request fencing and side-effect admission, recovery, limits and durable continuation (A2/A3/A6).
- GPT-6 Astra xhigh: browser identity/continuation, provider adapter, API and evidence harness boundaries (A5/A6/A7/A8).
- Parent: twelve-tool schemas, projections, result binding and deterministic rendering (A1/A4); integrates findings and owns final evidence.

Each reviewer returns all reproduced material findings together. Only disjoint source owners may write concurrently. No unrelated accepted-gate audit or repeated full-suite runs during ongoing edits.

## Consolidated protocol and surface findings

Independent frozen-source packets are preserved at `protocol-review/REPORT.md` and `surface-review/review.md` under this attempt. Both contain reproducible blockers, not acceptance. Protocol probes ran on SQLite and PostgreSQL 16; surface probes used actual React/Chrome and the installed SDK with simulated/local HTTP only.

| ID | Severity | Defect | Assigned correction |
| --- | --- | --- | --- |
| PR-01 | P2 | Alternate execute recovery loses an issued continuation nonce receipt after job resolution. | Luna protocol: controller/store plus focused regressions |
| PR-02 | P1 | Reusing a provider call ID across turns can admit two jobs but retain only one tool-response message. | Luna protocol: reject cross-turn reuse before new dispatch, preserve accepted-decision recovery |
| PR-03 | P2 | Controller accepts 65–256-byte call IDs while PostgreSQL columns cap at 64 characters. | Luna protocol: additive migration 0011, no historical migration edits |
| SR-01 | P1 | Same-page Retry after lost submit selects reconciliation without a request ID and stalls; reload works. | Luna surface: useAgent retry selection and browser regression |
| SR-02 | P1 | SDK inactivity timeout permits slow trickling beyond the intended total provider/canary deadline. | Luna surface: explicit total async deadlines and timeout regression |
| SR-03 | P1 | Injected fake preflight client can emit LIVE_CANARIES_PASSED evidence. | Luna surface: injection-aware evidence classification/rejection and regression |
| INT-01 | P1 | Production workbench route only mounts BlockedAssistant; the implemented AgentPanel/useAgent workflow is unreachable. Actual browser integration tests cannot find any agent controls. | Luna frontend: mount the existing secondary panel and wire shared session/recovery/result callbacks |

Protocol owner: `shiftguard/agent/controller.py`, `shiftguard/agent/store.py`, new `0011_gate6_call_id_capacity.py`, new `tests/agent/test_g6_comprehensive_protocol.py`. Surface owner: `frontend/src/hooks/useAgent.ts`, `shiftguard/agent/provider.py`, `scripts/preflight_nebius.py`, new focused surface backend/browser tests. Parent owns generated frontend assets and governance. All three Luna batches have disjoint source scopes. No current correction is independently accepted yet.

## Acceptance boundary

Gate 6 remains pending. Offline corrections do not satisfy A7: exact-model live chat/tool/structured-output and flagship run/read/compare proof still require explicit live-call authorization and local provider access. Source and separate governance acceptance remain parent-owned.


## Stopped checkpoint — 3 October 2026

All writers stopped when shared meter reached 79% (user ceiling 80%). Review established eleven defects. C03–C07 implemented: parent original probes now pass, and parent targeted SQLite/PostgreSQL grounding suites report 30 passed (parent-grounding-junit.xml). SR01–SR03 implemented: author Python regressions 2 passed; browser test unfinished, frontend build NOT_RUN. Protocol batch interrupted for budget: inspect current controller/store/0011/test changes against protocol-review/source-binding.json; no protocol correction PASS is claimed. Exact stopped bytes are recorded in stopped-source-manifest.json. No final integrated full-suite, rebuilt wheel, generated-asset binding or independent correction re-review occurred. Original reviewer blocker verdicts remain history. Gate6 PENDING, live A7 NOT_RUN. No commit/deployment.

Next execution: complete and review protocol PR01–PR03; finish surface browser regression, rebuild frontend assets; run affected agent suites against SQLite and existing PostgreSQL16, migration/packaging checks and one integrated final suite; freeze source, have Sol/Astra review only correction deltas, then bind truthful evidence. Do not treat the prior 562-test baseline as current-delta proof. Preserve all eleven original reproductions.

## Resumed execution — 3 October 2026

The user superseded the 80% cap and authorized continuing through the remaining 5-hour window. The window had reset to 0% at resumption. Luna owns protocol completion and a separate frontend integration slice; parent owns builds and integrated evidence. Latest independent provider checks: 30 targeted tests passed; installed SDK slow-trickle probe times out at the explicit total deadline; injected-client successes now carry offline labels. The first parent replay had an incorrect expected offline status spelling; corrected replay passed, and its failed log is preserved.

The first resumed browser run was stopped after confirming INT-01: existing Gate 6 flows never reach the current page. Its failed contexts remain in browser-resume/. This is a newly affected integration defect, not a failure of the scientific engine. Rebuild and rerun browser cases after the page wiring is complete.

## Final correction review and identifier contract

The integrated browser matrix passed 17 cases, including real local worker/resume execution; Astra returned PASS for SR01–SR03 and INT01 with exact source hashes in surface-correction-review/. Backend Sol review found one remaining PR03-R1 blocker: NUL IDs pass the old byte-only check but cannot be stored in PostgreSQL text columns. Its original BLOCKERS report and eight counterexample/control results are retained under backend-correction-review/.

Parent decision for this **unaccepted operational input contract**: a provider tool-call identifier is a nonempty valid UTF-8 string of at most 256 bytes, **excluding U+0000/NUL**. Reject unsupported identifiers before accepting/checkpointing a provider decision or dispatching any handler, equally on SQLite and PostgreSQL. Do not normalize, trim, truncate or re-encode accepted identifiers. Printable and multibyte identifiers remain unchanged through storage, messages and result projections. This explicitly narrows the earlier byte-only draft rule; it does not change the frozen scientific protocol or accepted Gates 0–5.

The first full-candidate run was stopped as superseded after the review identified this residual; no full-suite PASS is claimed from it. The final corrected source will get a new manifest, wheel and full-suite attempt. Existing wheel/runtime and browser results remain labeled with the source actually tested.

## Final parent verification


Gate 6 correction source frozen at `8bb8cb4c68e813dc44781acc236b0d63de6bd3b7c2077dd58e897cda47c260af`; no active writer.
Full suite: **611 passed, 0 failed, 0 errors, 0 skipped**, including 108 PostgreSQL-labelled cases; exit code 0, two dependency warnings, 983.34 seconds.
Browser integration: **17 passed, 0 skipped**. Typecheck/build and generated asset parity passed.
Final installed wheel: **PASS**, 9 SQLite/PostgreSQL upgrade/runtime probes; all 90 module origins came from the installed wheel.
Astra surface correction review PASS. Sol original backend BLOCKERS preserved; focused PR03-R1 residual review PASS. All reproduced correction findings closed within reviewed scope.
49 protected backend/scientific files and applied migrations 0001–0010 unchanged; accepted Gates 0–5 unchanged.
No source commit, deployment or live provider calls. **Gate 6 remains PENDING**: A7 live evidence requires locally configured Nebius access and explicit call/token budget.

Authoritative evidence: `../verification/gate6-comprehensive-20261002/final-checkpoint.json` and `final-source.json`.
Review history and correction details: `docs/gate6-comprehensive-review-20261003.md`.
Do not reopen a broad audit; follow the bounded next steps in the checkpoint. Historical test counts below refer only to their original source.
