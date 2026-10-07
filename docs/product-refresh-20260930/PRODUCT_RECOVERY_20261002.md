# Product recovery and paper checkpoint — 2 October 2026

This packet records the recovered ordinary product and the new empirical working paper. Gate 6 remains pending. Earlier blocker packets and failed attempts are preserved; no source commit, deployment or live provider call was made.

## Ordinary engine

The preloaded Bank dataset is intact: 41,188 records, with the frozen SHA-256 checked before use. The ordinary local database had remained at migration 0003 and the ordinary API did not own an experiment worker. The recovery uses the existing environment, upgrades the database through 0010, and retains its six legacy experiment rows. It does not fabricate publication records for old results.

Start from the application directory:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1
~~~

The launcher starts a hidden API with its managed worker/recovery loop, bounded numerical-library threads, and the optional agent disabled. It records process identity after launch, verifies readiness, and safely reuses the owned server. Fresh launch and reuse both passed. The ordinary product is at http://127.0.0.1:8000/.

An authenticated HTTP submission of the real Bank stress preset completed in 112.833 seconds: job `3f2ec249-50c7-4dcc-8b6d-9cfd93d66326`, experiment `d8a18a371c8c88ee20ba1087`, 400 conditions. It used the ordinary API/queue/worker, not the test harness or a provider. Its scientific payload hashes match the accepted development artifact. Replaying that artifact is runtime evidence, not an independent scientific replication.

The final post-restart default-preset check also passed: Bank outage / 50 labels, five scored conditions, 2.154 seconds, job `34a02f95-5668-4c97-971c-45b1766eafd4`. No credentials were retained.

## Frontend

- `/` is the Bank workbench; `/demo` remains an alias; `/about` contains the product explanation.
- The visible flow is preloaded data → choose an approved analysis → run it or reopen a saved record. The default remains Bank outage / 50 labels.
- Charts have readable titles, axes and method legends. All numerical values and condition identities come from persisted results.
- An optional Three.js budget view renders actual values as bars and a line. The 2D chart and exact table remain available. Reduced motion, data saving, unsupported WebGL, hidden/offscreen state and cleanup are handled.
- Advanced filters, provenance, history and activity use disclosures. Errors, cancellations and sparse fallback warnings remain visible. “All methods” aggregates warnings across the displayed methods.
- The two supplied CodePen references informed presentation; their demo data was not copied into results.

Protected client API/auth/cache/identity files: 7 of 7 unchanged against the latest prior frontend manifest. Protected backend/config/scientific files: 50 of 50 unchanged. Accepted Gate 0–5 objects remain unchanged.

## Narrow correction and review

Astra's original frontend packet found AFR-01 (startup identity recorded before launch) and AFR-02 (“All methods” hid fallback diagnostics). Both were fixed and the correction review returned PASS, tied to frontend freeze `7c1266133755ca384840260e155716d0450f14ba521bc93ad826b81921916947`.

Sol's initial backend packet accepted C01 direct-selection authority, but found a C02 recovery edge: an unrelated spent error signature rejected another exact PENDING intent's own reserved retry. Parent reproduced it on SQLite and PostgreSQL: two uninterrupted controls passed and both recovery cases failed. The correction selects the sole owning reservation before historical non-owning matches; ambiguous ownership, immutable-intent checks, authority/fencing and third-retry caps remain enforced. The permanent regression includes both controls and both crash cases.

Current backend freeze: `0a9c0637629a4a9512800b9e1f33da33e8286de9dcd43d207f9f266957e09e28`. Only the controller and its regression file changed from the first reviewed backend freeze.

SOL_FINAL_REVIEW=PASS (bounded correction; original blocker packet retained)

## Verification ledger

| Evidence | Result and scope |
|---|---|
| Ordinary Bank stress run | PASS, 400 conditions, normal API8000 |
| Fresh startup and reuse | PASS; exact owned process identity and zero active jobs before restart |
| Final normal-origin browser corrections | 3 passed, 0 skipped; persisted values, true 3D, fallback warnings, reduced-motion/mobile behavior |
| Existing workbench closure | 10 passed; actual worker runs, saved values, cancellation, lost-response identity and auth/storage recovery |
| Refresh browser checks | 17 passed; responsive/accessibility/loading/WebGL/404 behavior |
| Typecheck and production build | PASS; generated assets installed in the ordinary server |
| Narrow backend correction matrix | 52 passed, 0 skipped, SQLite + PostgreSQL16 |
| First full suite before final C02 edge correction | 558 passed, 0 skipped, 2 dependency deprecation warnings |
| Final full suite on corrected source | 562 passed, 0 failed/errors/skips, 2 dependency warnings |
| Final installed wheel | PASS; exact packaged source; fresh/0008/0009 SQLite and PostgreSQL16 upgrades; copied nonempty historical SQLite; real API/CLI and import origins |

The 10/17 browser reports precede the final two frontend corrections; the final 3 cases exercise the changed paths. They are retained supporting reports, not mislabeled final-delta reruns. Original failed reports and the first wheel remain immutable. Final source/asset/wheel binding is recorded separately.

All current evidence is under `../../verification/product-recovery-20261002/`. The original full-suite and review verdicts remain historical.

## Research paper delivered

The new `../../research/SHIFTGUARD_Working_Paper_v0.2.md`, editable DOCX and seven-page PDF report actual Bank development results. All seven exported pages were rendered and visually checked. The original v0.1 files are retained.

The extractor verifies accepted artifact hashes and all 400 cells, produces condition-level CSVs, paired budget-50 comparisons, a figure and an evidence manifest. Parent independently reproduced the CSV/SVG extraction byte-for-byte.

The manuscript reports the mixed/adverse evidence: across eight fixed shifted predictor/scenario cells, target temperature, Platt and Beta reduce mean Brier score in four cells each while increasing log loss in all eight. Isotonic worsens Brier in five cells and log loss in all eight. It does not claim general benefit, independent replications, confirmatory significance, Adult results, financial savings or publication.

Sharing text is in `../../research/SHARING_BRIEF_v0.2.md`; nothing has been posted or sent.

## Next bounded execution

1. Bind the final full-suite, reviewer, package and source records. Keep Gate 6 PENDING until its full acceptance requirements are recorded; passing this correction packet alone does not accept the gate.
2. Preserve current source and the six accepted gate objects. The parent owns any later authorized source commit and separate governance checkpoint. No unrelated Gate 4 audit is needed.
3. Finish the required A7 provider proof only with an explicitly authorized model/account and call/token allowance. The public assistant stays disabled meanwhile. Existing offline preflight evidence is not a live proof.
4. For the paper, freeze the declared experimental protocol before confirmatory scoring: untouched evaluation policy, primary method/comparator and budgets, seed plan, aggregation/uncertainty, duplicate/missingness and numerical choices. Then run the declared multi-seed Bank evaluation; Adult follows only after its contract is frozen. See manuscript Section 6.
5. Business dataset/model ingestion is a subsequent product slice governed by `MASTER_PLAN.md` and the existing business-ingestion plan. Current successful runs use approved preloaded presets; planned upload pages do not constitute implemented BYO support.

No action is required from the user to run the restored preloaded workbench or read the paper. Live provider access/allowance and a confirmatory protocol remain separate prerequisites for those later stages.
