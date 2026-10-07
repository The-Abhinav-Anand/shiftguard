# Gate 6 correction review — BLOCKERS

1 October 2026. Candidate **AG-G6-CORRECTIONS-01**. Independent GPT-6.1 Sol Extra High application review plus parent integration/source/evidence verification.

**Result: 3 of the original 25 findings are corrected; 22 remain material blockers. Gate 5 remains accepted. Gate 6 remains pending and unaccepted.** The author's claim that all 25 are resolved is contradicted by current executable negative tests. The normal suite genuinely passes; its current coverage does not establish the missing contracts.

This is a correction-delta review of G6-S01–S18 and G6-P01–P07, not another codebase or Gate 4 audit. Antigravity remains the sole application writer. Parent and reviewer changed only independent probe/report artifacts and current governance/handoff documentation. No application implementation, source commit, deployment, live inference or frozen scientific reproduction occurred.

## Source and preserved history

| Binding | Independently observed |
| --- | --- |
| Working HEAD | `83037b0f02eef62203c3f565a063d824af2722d7`, dirty |
| Last accepted Gate 5 source | `f63116fedc2751493d79d44897ba913b6d28b0b5` |
| Author attempt | `../verification/gate6/corrections-954b80fb-d425-48d3-b157-d93a7a91b906/` |
| Author declared 44-file digest | `fd84e1ff09bffc67a24d6d6f26aa6ffc8d4b4dcfca2c2ad96ab5a3a8926cbf1a` |
| Recomputed current digest over the same 44 paths | `28731222f12c4237e8e55d7a986a50868c82d6ae153b48a1394ca4d109409ffa` |
| Difference | Only `docs/gate6-implementation.md`; the remaining 43 entries match the submitted manifest |
| Protected backend/config/migrations | 75 raw file hashes unchanged against the retained independent baseline; expected existing main/settings changes remain separately manifested |
| Generated/served assets | Independent isolated Vite build: all four files byte/hash identical to current served static files |
| Independent evidence | `../verification/gate6/correction-review-20261001/parent/` and `sol/` |

The documentation mismatch does not mean the submitted executable files drifted during this review; it means the packet's declared combined digest cannot truthfully bind the current complete 44-file packet. The producer records only an end-of-run manifest, no before/after manifest or protected comparison. Three claimed correction-proof nodes are absent from the actual agent JUnit report and current tests: S08 `test_unauthorized_session_rejected`, S09 `test_unauthorized_experiment_id_rejected`, and S13 `test_bank_stress_preset_dispatched`.

Initial [parent review](gate6-review.md), [Sol review](gate6-sol-review.md), original [correction instructions](gate6-corrections.md), original author attempt and corrected author attempt remain history. New acceptance is not copied from those artifacts. See [source/report audit](../../verification/gate6/correction-review-20261001/parent/source-and-report-audit.json), [protected comparison](../../verification/gate6/correction-review-20261001/parent/protected-backend-comparison.json) and the final [review record](../../verification/gate6/correction-review-20261001/review-record.json).

## Actual verification results

| Check | Result and scope |
| --- | --- |
| Independent ordinary full suite | **373 passed, 0 failed/errors/skips, 2 warnings, 569.47 seconds**, exit 0. Existing PostgreSQL **16.15** verified; tests used their isolated files/schemas. [JUnit](../../verification/gate6/correction-review-20261001/parent/full-junit.xml), [log](../../verification/gate6/correction-review-20261001/parent/full.log). |
| Sol application contracts | **118 cases: 76 failed, 42 passed, 0 errors/skips**. SQLite and actual PostgreSQL each: 38 failures, 21 passes. Failures are expected-correctness assertions reproducing defects, not 76 unrelated issues. [Complete S review](gate6-correction-sol-review-20261001.md), [structured packet](../../verification/gate6/correction-review-20261001/sol/review-packet.json). |
| Parent provider/preflight/evidence probes | First invocation **11 failed, 2 passed**; actual OpenAI adapter MockTransport follow-up **2 failed, 13 deselected**. No network inference. [First JUnit](../../verification/gate6/correction-review-20261001/parent/provider-evidence-probes-junit.xml), [actual adapter JUnit](../../verification/gate6/correction-review-20261001/parent/actual-adapter-junit.xml). |
| Parent startup/migration probes | **2 failed, 1 passed**, including real hosted PostgreSQL startup; exact historical SQLite upgrade follow-up **1 failed, 3 deselected**. [Startup JUnit](../../verification/gate6/correction-review-20261001/parent/startup-migration-junit.xml), [historical upgrade JUnit](../../verification/gate6/correction-review-20261001/parent/historical-upgrade-junit.xml). |
| Parent browser/HTTP contracts | **2 passed, 3 failed**, real isolated API/SQLite/durable queue; explicitly scripted provider; worker deliberately disabled for admission/recovery identity cases. [Observed cases](../../verification/gate6/correction-review-20261001/parent/browser-contract-probes.json). Initial harness timeout records are retained; corrected final harness has no probe errors. |
| TypeScript / isolated production build | Both exit 0. All four built/served hashes match. Existing large Plotly chunk warning and outside-root output notice are not Gate 6 blockers. [Comparison](../../verification/gate6/correction-review-20261001/parent/generated-served-comparison.json). |
| Exact existing wheel | SHA-256 `62412ebce9a0e8e7acbb0dd2d2252a452d8c8c79de76dee83d0fe663fcfe79d9`; package entries match current source bytes. Extracted-wheel isolated CLI help, API health, SQLite fresh 0009 and 0008→0009 upgrade with full session-row preservation pass. All imported SHIFTGUARD modules resolve outside checkout. This is extracted-wheel runtime proof, not a newly installed runtime or PostgreSQL wheel proof. [Report](../../verification/gate6/correction-review-20261001/parent/wheel-runtime-smoke.json). |
| Author supplied success reports | Independently parsed: 34 agent, 5 static, 2 migration cases; 12 browser cases; zero reported failures/skips. Those counts are genuine. Author performed full collection, not full-suite execution. |
| Live model / clean committed candidate | **NOT_RUN / NOT_ACCEPTED**. A7 remains `BLOCKED_REQUIRED_LIVE_EVIDENCE`; no key or usage permission was requested for this offline review. |

The two full-suite warnings concern deprecated Starlette/httpx and AnyIO APIs. No dependency installation or speculative dependency upgrade was performed. Initial WSL access failed because the sandbox denied access; narrowly authorized access to the existing service succeeded. No replacement daemon/database was installed or started.

## Every original finding

| ID | Independent closure | Current result |
| --- | --- | --- |
| S01 | PARTIAL — OPEN | Accepted response/intents are not crash-replayed; recovery calls missing `JobQueue.get_job_by_key`; accepted following calls disappear. |
| S02 | PARTIAL — OPEN | Durable repair ledger exists, but admission and stored signatures disagree; repeated invalid calls still dispatch. |
| S03 | PARTIAL — OPEN | Ownership checks precede separate unguarded trace mutations and queue admission; stale owner creates an unlinked job after winner completes. |
| S04 | **CORRECTED** | WAITING lease released; distinct HTTP worker resumes immediately. |
| S05 | PARTIAL — OPEN | Resumed second run is not awaited; wrong tool name; resumed batch executes ten calls; overflow IDs lack matching responses. |
| S06 | **CORRECTED** | Barrier-tested concurrent request and receipt insertion returns exact winner or typed conflict. |
| S07 | PARTIAL — OPEN | Crash between completion and receipt causes endless 202/COMPLETED contention; unissued nonce accepted for RUNNING request. |
| S08 | PARTIAL — OPEN | Session expiry between SELECT and real enqueue still admits a job. |
| S09 | PARTIAL — OPEN | Only one reader enforces membership; seven others and the empty-set renderer allow unauthorized empirical evidence. |
| S10 | PARTIAL — OPEN | Valid evidence enables false raw provider prose despite numeric/qualitative contradictions. |
| S11 | PARTIAL — OPEN | Original formatting crashes fixed; typed cost error and null/unavailable reasons disappear from final result. |
| S12 | PARTIAL — OPEN | Failed ninth condition and five required sparse diagnostics omitted from final output. |
| S13 | **CORRECTED** | Stress alias enters actual `bank-stress` queue/worker branch; closure is routing, not a new scientific result. |
| S14 | PARTIAL — OPEN | Different predictors and absent identity context still qualify as improvement. |
| S15 | PARTIAL — OPEN | Advertised default summary is rejected; invented scenario/budget can match stored records. |
| S16 | PARTIAL — OPEN | Shallow metadata filtering exposes nested paths, private fields and labels to provider/trace. |
| S17 | PARTIAL — OPEN | Rejected 200 KB arguments remain in transcript; smaller private values appear in validation/trace output. |
| S18 | PARTIAL — OPEN | Dict-valued failed-job error produces resume/GET 500; cancellation omitted; inconsistent unpublished job result accepted as evidence. |
| P01 | PARTIAL — OPEN | Explicit lost-submit Retry and WAITING reload now pass; accepted-response loss followed by reload has no recovery card/control. |
| P02 | PARTIAL — OPEN | Automatic reconnect removed; explicit reconnect leaves inquiry disabled; provider 401 classified as session expiry. |
| P03 | PARTIAL — OPEN | Positive allowances checked, but no pre-call total reservation, hidden retries, unknown usage accepted and incomplete/incorrect canaries pass. |
| P04 | PARTIAL — OPEN | Regex redaction misses actual configured key; malformed responses escape typed boundary; ordinary output unbounded. |
| P05 | PARTIAL — OPEN | Collection collisions/current head fixed and wheel now independently runs; already-applied original 0009 cannot acquire newly added columns. |
| P06 | PARTIAL — OPEN | Some report counts dynamic; required skips/fabricated counts still PASS, proof map unconditionally RESOLVED, source/proof binding incomplete. |
| P07 | PARTIAL — OPEN | Scripted branding accurate and ordinary local disabled startup works; hosted flag still overrides disabled setting. |

The [Sol packet](gate6-correction-sol-review-20261001.md) contains current line links, minimal executed nodes and observed JSON for every S finding. The following parent findings complete that packet; there is no additional hidden review queue.

## Remaining parent blockers

### P01 — P1: ambiguous accepted intent is inaccessible after reload

`frontend/src/hooks/useAgent.ts:74`, `:173`, `:240`; AgentPanel recovery controls. Drop an actual accepted POST response, then reload: the queue retains request `req_6e05b04d4a2948fb8aef` and job `ffa3c3b1-073d-46dd-ad68-35847a84b6c8`. The browser retains prompt/key but displays **zero active cards and zero Retry controls**. Rehydration only GETs saved WAITING records with a known request ID, and `canRetry` requires a current error that reload erased. The successful explicit Retry control is separately retained as progress.

Fix: make unresolved persisted intent a first-class recoverable phase even without a returned request ID. Reconcile under the original session and original key/body; expose Retry/Resume immediately after reload. Persist the current issued nonce/job/phase before later calls. Add epoch/abort/in-flight guards so Clear, reconnect, new inquiry and unmount suppress old callbacks; transient poll/resume failures retain a recoverable phase. Never synthesize `nonce_${Date.now()}` or rebind old work to another session.

### P02 — P1: explicit reconnect creates credentials but does not restore submission

`frontend/src/hooks/useAgent.ts:36`, `:138`, `:218`; `frontend/src/App.tsx:202`. Expire the actual server session and submit. Automatic replacement correctly does not occur. Click explicit Reconnect: session count rises from one to two, but the inquiry remains disabled with the same expiry notice because `sessionExpired` is not reset after new verified credentials. A separate HTTP 401 `PROVIDER_AUTH_ERROR` envelope is also rewritten as SESSION_EXPIRED and disables the inquiry.

Fix: classify documented capability error codes, not every HTTP 401. Clear obsolete auth UI only after successful explicit reauthentication; bind active/pending state to its owning session and keep old work separate. Provider/business/transport failures do not request capability replacement. Preserve accepted Gate 5 published caches.

### P03 — P1: preflight budget and required canaries remain unenforceable

`scripts/preflight_nebius.py:72`, `:81`, `:91`, `:100`, `:111`, `:127`, `:153`. Offline probes demonstrate:

- Total allowance of one token still sends a request with `max_tokens=10` plus input.
- `--allow-calls 1` causes two wire requests after an SDK-handled 429 because `max_retries=1`.
- Missing usage is treated as zero and a second request executes.
- Wrong PONG content plus `dataset_id="invented"` tool arguments reports LIVE_CANARIES_PASSED.
- Prefix model `nvidia/Nemotron` satisfies the supposed exact-model check.
- Only chat/tool generation canaries run: no structured explanation-plan or validated fallback, and no tool-response exchange proving original call-ID matching. Second request has no output cap.

Fix: explicit positive allowance and exact model before construction; disable hidden retries or account for every wire attempt; reserve conservative input+output for every request; finite positive output limit on each; fail closed on unknown usage. Validate required chat content, exact model, strict tool argument/name/ID exchange and structured-plan/fallback. Missing/failed required canary cannot produce PASS. No real `--live` run is authorized by this correction packet.

### P04 — P1: real adapter can leak configured credentials and throw untyped parsing errors

`shiftguard/agent/provider.py:17`, `:165`, `:168`, `:173`; settings bounds. Actual OpenAI SDK with `httpx.MockTransport` produces a 400 body containing a synthetic configured key in ordinary prose. That key remains in `ProviderError.message`, raw error and logger output; regexes cover only selected textual key/Bearer patterns. A conforming response envelope with empty choices raises untyped IndexError outside the try block. Ordinary chat requests also omit an output token limit.

Fix: fixed bounded public errors, exact known-secret replacement, sanitized structured logs; whole request/response/model/tool/usage parsing inside typed error handling. Bound settings, timeouts, retries, output, IDs, arguments and collections; close actual async clients on every lifecycle. Add actual-adapter 400/401/429/500/malformed/oversized MockTransport cases, not only regex and ScriptedProvider tests.

### P05 — P1: persisted original 0009 databases never receive the correction schema

`shiftguard/alembic/versions/0009_gate6_agent_runtime.py:36`, `:37`, `:38`; `shiftguard/migrations.py:26`. Original immutable author SQLite is already stamped `0009_gate6_agent_runtime` and lacks **active_nonce, repair_ledger_json, pending_tool_calls_json**. Current correction adds them by rewriting the same revision. Copy that exact historical DB, run current `upgrade_database`: Alembic performs no upgrade and all three columns remain absent. This is a real historical-DB reproduction, not just a simulated schema; original bytes were never modified. [Original columns](../../verification/gate6/correction-review-20261001/parent/historical-0009-schema.json).

Fix: preserve applied revision shape and add a forward repair migration that safely creates/backfills correction fields on both the original and expanded 0009 shapes. Verify fresh/0008/original-0009/correction-0009 databases with nonempty sessions, requests, jobs, receipts and immutable result/audit data. Collection and isolated SQLite wheel runtime are already proven progress; preserve those tests. Run the accepted package through real supported upgrades, not just import statements.

### P06 — P1: evidence generator still manufactures closure without proof

`scripts/execute_gate6_offline_suite.py:65`, `:481`, `:596`; source/contract/proof outputs. Two concrete injected JUnit fixtures are incorrectly PASS: all required tests skipped, and declared tests=34 with no testcase nodes. A1/A2/A3 share one aggregate agent status; A4 can pass without a browser report if command exits are zero. All 25 proof entries still hardcode RESOLVED; three cited tests do not exist. Failed Git commands are not checked; the manifest appears only after tests; protected comparison and full-suite execution are missing from the author packet. The current doc hash mismatch demonstrates failed exact packet binding.

Fix: per-obligation actual collected/testcase IDs, recursive complete report results and required backend matrix; required skips/missing reports/wrong counts/failed commands/stale source → FAIL/BLOCKED/NOT_RUN. Proof-map verdicts come from verified node coverage and independent review, not literal strings. Capture real Git availability/HEAD/dirty errors, before/after application/generated hashes, final document/checkpoint separately, protected comparison, complete raw commands/results and installed-package origins. Negative-test the evidence builder itself.

### P07 — P1: hosted test flag overrides authoritative disabled state

`shiftguard/api/main.py:36`, `:37`; `shiftguard/api/routes/agent_requests.py:34`. Actual hosted PostgreSQL app with `agent_enabled=False` and `SHIFTGUARD_ALLOW_TEST_SCRIPTED_PROVIDER=true`/scripted mode starts a DynamicE2EProvider and reports enabled/available=true. A normal local disabled startup without that flag correctly stays disabled; visible scripted labels are also improved. The hosted path is still not isolated test construction and the disabled setting remains overridable.

Fix: ordinary hosted startup rejects test-only injection/flags and always obeys disabled settings. Inject scripted providers only in a dedicated isolated test-app factory with explicit test metadata. Keep provider kind honest throughout API/browser/evidence; do not treat availability in a scripted harness as Nemotron live evidence.

## Root cause and next execution

This candidate fixes many individual happy paths but leaves shared contracts split across entry points: initial versus resumed dispatcher, check versus mutation/admission transactions, tool results versus final rendering, raw transcript versus public projection, and advertised schema versus actual policy. Adding separate local checks has not made these paths one enforceable protocol. The correction must unify those owners and transfer the executed negative cases into permanent coverage.

Execute [AG-G6-CORRECTIONS-02](gate6-corrections-02.md) as one integrated Antigravity batch. Preserve S04/S06/S13 corrected controls and all 22 negative reproductions. No extra user input is required for offline correction; live A7 is separate. Parent owns one correction-only independent re-review, exact final source binding, source commit and separate governance checkpoint. Do not proceed to Gate 7 or business-upload/frontend implementation while this shared Gate 6 delta is being corrected.
