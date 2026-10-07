# Gate 6 correction Sol review — AG-G6-CORRECTIONS-01

**Verdict: BLOCKERS. Three original findings are corrected; fifteen are partially corrected with reproducible material blockers remaining. Gate 6 acceptance remains parent-owned and pending.**

Reviewed 1 October 2026 by independent GPT-6.1 Sol. Scope is ONLY original G6-S01–G6-S18 and their affected application invariants. Antigravity remains the sole application writer. This sidecar wrote only this new report and bounded helpers/logs under `../verification/gate6/correction-review-20261001/sol/`; application code, tests, governance and historical evidence were preserved. No Gate 4 restart, ordinary full suite, browser, provider-adapter/preflight, package or live-provider run was performed.

| Candidate binding | Value |
| --- | --- |
| Application / outer root | `C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard` / parent directory |
| Current base HEAD | `83037b0f02eef62203c3f565a063d824af2722d7`; dirty correction working tree |
| Author correction attempt | `corrections-954b80fb-d425-48d3-b157-d93a7a91b906` |
| Declared 44-file digest | `fd84e1ff09bffc67a24d6d6f26aa6ffc8d4b4dcfca2c2ad96ab5a3a8926cbf1a`; declaration, not recomputed here |
| Parent binding update | Parent reports only `docs/gate6-implementation.md` differs; the other 43 declared entries match and 75 protected raw backend files are unchanged. This is parent-supplied evidence, not this sidecar's independent hash verification. |
| Ownership | Application changes: Antigravity. P01–P07, full-suite, browser/provider/preflight/evidence/package/source hashing: parent. |

Read app AGENTS.md, .agent/ownership.json and live state, both original Gate 6 review packets, the S correction requirements, author correction proof-map/raw agent evidence, and retained original independent probes. Existing local review-handoff skill was applied within this narrower assignment. Author RESOLVED labels and test counts supply no independent proof. Three cited proof-map nodes do not exist in current tests: `test_unauthorized_session_rejected`, `test_unauthorized_experiment_id_rejected`, `test_bank_stress_preset_dispatched`; closures below rely on actual reviewer probes.

## Independent execution and evidence

**118 expected-correctness cases: 76 failed, 42 passed, 0 errors, 0 skipped.** SQLite: 59 cases, 38 failures, 21 passes. Actual PostgreSQL16: identical counts. These are product-correctness assertions; failures reproduce defects, and passes record corrections/controls. No author-claimed test count is used.

| Invocation | Actual result | Evidence |
| --- | --- |
| Initial focused application contracts | 110 cases: 68 failed, 42 passed; exit 1; 34.24 s; two deprecation warnings | [complete log](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/pytest.log>); [JUnit](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/junit.xml>); [command](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/command.json>) |
| Focused follow-ups for observed failure/nonce/diagnostic/projection defects | 8 cases: 8 failed; exit 1; 3.64 s; two deprecation warnings | [complete log](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/pytest.log>); [JUnit](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/junit.xml>); [command](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/command.json>) |

Used only `.venv/Scripts/python.exe -B`, no cache provider, UTF-8/one-thread numeric settings, fresh temporary SQLite databases and unique `sol_g6c_<uuid>` PostgreSQL schemas. Fixture teardown drops only its own schema. Both invocations successfully verified the existing PostgreSQL16 helper through authorized `require_escalated` WSL access; **PostgreSQL runtime is AVAILABLE, not BLOCKED**. No installation or daemon/container replacement/start was performed. No credential-bearing database URL was printed; pytest engine representations mask passwords. Test payloads/IDs/errors are synthetic and demonstrate application contracts, not scientific performance or validity of historical artifacts.

Reproduce the first complete focused run from the app root (use the same narrow WSL escalation):

```powershell
& '..\verification\gate6\correction-review-20261001\sol\run_probes.ps1' -Backend all
```

To run any minimal node below after loading the existing helper, invoke the existing Python with `-B -m pytest <probe-file>::<node> -q -p no:cacheprovider --basetemp <fresh-directory-under-this-sol-root> --junitxml <new-sol-run>/junit.xml --tb=short`, and set `SOL_PROBE_RECORD_ROOT` to that new run directory. Substitute `postgres` for `sqlite` to reproduce the same backend result. Do not reuse a prior evidence directory.

Probe files: [original-contract adaptations](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/test_correction_contracts.py>), [focused follow-ups](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/test_edge_contracts.py>), [shared isolated fixtures](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/support.py>). Exact executed helper snapshots are retained beside each run's logs. [Structured packet](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/review-packet.json>) includes every collected node/result and all eighteen closures; [bounded current line excerpts](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/current-source-excerpts.txt>) records the reviewed source locations without duplicating parent hashing.

Post-probe read-only isolation verification: **0 remaining schemas with this sidecar's exact `sol_g6c_` prefix**, [record](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/postgres-isolation.json>). No unrelated schema was changed or removed.

## All eighteen original closures

| Finding | Closure | Independently corrected | Still broken / scope limit |
| --- | --- | --- | --- |
| G6-S01 | PARTIALLY_CORRECTED | Ordinary call/turn counters | Accepted decision/job crash recovery |
| G6-S02 | PARTIALLY_CORRECTED | Ledger survives resume | Repeated dispatch bypasses repair admission |
| G6-S03 | PARTIALLY_CORRECTED | Await/expired publication checks | Tool writes and queue admission remain unfenced |
| G6-S04 | CORRECTED | Waiting lease release; immediate new-worker HTTP resume | Receipt crash/nonce atomicity remains S07 |
| G6-S05 | PARTIALLY_CORRECTED | One run + following read preserves IDs | Second run orphan; wrong stress name; ten calls; missing overflow responses |
| G6-S06 | CORRECTED | Barrier-tested request/receipt insert-or-read races | Terminal continuation receipt crash remains S07 |
| G6-S07 | PARTIALLY_CORRECTED | Ordinary exact HTTP replay; wrong waiting nonce rejection | Completion/receipt crash; never-issued RUNNING nonce |
| G6-S08 | PARTIALLY_CORRECTED | Expired status checked before dispatch | Expiry between SELECT and admission still queues work |
| G6-S09 | PARTIALLY_CORRECTED | read_experiment_results rejects unauthorized references | Other seven readers and empty-set renderer bypass authority |
| G6-S10 | PARTIALLY_CORRECTED | Zero-evidence fabricated narrative dropped | Valid claim enables false numeric/qualitative narrative |
| G6-S11 | PARTIALLY_CORRECTED | Original None formatting crashes removed; condition ID kept | Typed error lost; null scientific availability omitted |
| G6-S12 | PARTIALLY_CORRECTED | Basic failed/fallback/outage qualification visible | Failed ninth condition and five sparse fields lost |
| G6-S13 | CORRECTED | Real queue routes aliases to bank-stress worker branch | Scientific stress execution NOT_RUN by sidecar; parent owns worker/browser evidence |
| G6-S14 | PARTIALLY_CORRECTED | Dataset/rows/mask mismatch, budget and curve/cost IDs | Predictor mismatch and absent identities still qualify |
| G6-S15 | PARTIALLY_CORRECTED | Temporal/MCAR-0.20, aliases, extra selectors, arbitrary method/focus | Default summary rejected; unsupported scenario/budget can match records |
| G6-S16 | PARTIALLY_CORRECTED | Top-level known path removal | Nested paths/raw labels/private fields reach provider/public trace |
| G6-S17 | PARTIALLY_CORRECTED | Large-argument rejection and public size reduction | Full rejected blob stays in transcript; small private argument echoed |
| G6-S18 | PARTIALLY_CORRECTED | Terminal trace status; attached ID fallback | Failed resume/GET 500; cancelled answer omission; unverified conflicting evidence |

All fifteen PARTIALLY_CORRECTED rows are **still material blockers**, not conditional passes. No S probe is runtime-BLOCKED. A7 remains `BLOCKED_REQUIRED_LIVE_EVIDENCE` outside this offline sidecar; parent-owned checks are NOT_RUN here, with no independent claim about their completion.

## Consolidated current blockers and corrected controls

### G6-S01 [P1] PARTIALLY_CORRECTED: Crash recovery still loses accepted decisions

**Current source:** [shiftguard/agent/controller.py:152](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:152>); [shiftguard/agent/controller.py:299](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:299>); [shiftguard/agent/controller.py:418](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:418>); [shiftguard/jobs/queue.py:185](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/jobs/queue.py:185>).

**Actual independent output:** Call/turn checkpoints between ordinary read calls now persist. Crash before enqueue or after enqueue raises `AttributeError: JobQueue has no attribute get_job_by_key`; the request remains RUNNING, call_count=0, saved proposed IDs=[], and the after-enqueue case retains one unlinked job. A crash after the tool result commits instead produces COMPLETED with one job, active_job_id=null and a second provider decision; the accepted following read disappears.

**Minimal main probe node(s):** `test_S01_crash_replays_accepted_intent[sqlite-before_enqueue]`, `test_S01_crash_replays_accepted_intent[sqlite-after_enqueue]`, `test_S01_crash_replays_accepted_intent[sqlite-after_result]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S01-crash-before_enqueue ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S01-crash-before_enqueue-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S01-crash-before_enqueue-postgres.json>)); S01-crash-after_enqueue ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S01-crash-after_enqueue-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S01-crash-after_enqueue-postgres.json>)); S01-crash-after_result ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S01-crash-after_result-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S01-crash-after_result-postgres.json>)).

**Required correction, Antigravity-owned:** Checkpoint the complete accepted response, ordered intents and counters before dispatch; recover through the existing scoped idempotency record with the saved original key. Make result/job linkage and request acknowledgment recoverable as one fenced transition.

### G6-S02 [P1] PARTIALLY_CORRECTED: Repair ledger persists but does not prevent repeated dispatch

**Current source:** [shiftguard/agent/controller.py:344](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:344>); [shiftguard/agent/controller.py:390](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:390>); [shiftguard/agent/policy.py:132](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/policy.py:132>).

**Actual independent output:** The ledger survives a job pause as inspect_dataset:INVALID_ARGUMENTS:argument=1. Nevertheless bad1, bad2, bad3 and bad4 all reach registry.dispatch. The precheck computes inspect_dataset:invalid_arguments, which cannot match the stored signature. Later calls only receive REPAIR_BUDGET_EXCEEDED after execution. Persisting the aggregate count has not enforced initial failure plus one corrective attempt.

**Minimal main probe node(s):** `test_S02_one_corrective_attempt_survives_resume[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S02-repair-budget ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S02-repair-budget-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S02-repair-budget-postgres.json>)).

**Required correction, Antigravity-owned:** Derive one structured normalized signature consistently for pre-dispatch admission and the durable ledger, including error field locations. Stop subsequent dispatches after the one correction allowance, including calls resumed from a saved turn.

### G6-S03 [P1] PARTIALLY_CORRECTED: Ownership checks remain separate from mutations and admission

**Current source:** [shiftguard/agent/controller.py:328](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:328>); [shiftguard/agent/controller.py:339](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:339>); [shiftguard/agent/controller.py:390](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:390>); [shiftguard/agent/store.py:428](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:428>); [shiftguard/agent/store.py:513](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:513>).

**Actual independent output:** Takeover during provider await and expired request publication are rejected. Moving the takeover to immediately after the last check reproduces the defect: the winning owner finishes COMPLETED, while the old owner inserts a PENDING execution; at the dispatch boundary the old owner additionally creates one job and changes its trace to success. Its final request CAS loses, leaving the job unlinked. record_tool_execution/update_tool_execution contain no owner/generation predicate and dispatch is outside the checked transaction.

**Minimal main probe node(s):** `test_S03_admission_and_tool_writes_are_atomic_with_ownership[sqlite-intent]`, `test_S03_admission_and_tool_writes_are_atomic_with_ownership[sqlite-dispatch]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S03-race-intent ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S03-race-intent-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S03-race-intent-postgres.json>)); S03-race-dispatch ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S03-race-dispatch-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S03-race-dispatch-postgres.json>)).

**Required correction, Antigravity-owned:** Fence every tool/receipt mutation and guarded queue admission in the same transaction as the current request owner, generation, unexpired lease and legal status. Check CAS outcomes and stop on ownership loss.

### G6-S04 CORRECTED: Waiting ownership is released and the next HTTP worker resumes

**Current source:** [shiftguard/agent/controller.py:446](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:446>); [shiftguard/agent/store.py:305](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:305>).

**Actual independent output:** Submit returns 202 with worker_id=null and lease_expires_at=null while waiting. After job completion a distinct HTTP invocation immediately returns 200/COMPLETED and requests the next scripted provider turn. No forced lease expiry was needed. Receipt-crash and nonce defects are retained under S07 rather than treating this passing ordinary-resume control as complete continuation acceptance.

**Minimal main probe node(s):** `test_S04_immediate_http_resume_distinct_workers[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S04-http-resume ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S04-http-resume-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S04-http-resume-postgres.json>)).

### G6-S05 [P1] PARTIALLY_CORRECTED: Resumed multi-call exchange mishandles another run and the call budget

**Current source:** [shiftguard/agent/controller.py:309](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:309>); [shiftguard/agent/controller.py:634](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:634>); [shiftguard/agent/controller.py:644](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:644>); [shiftguard/agent/controller.py:681](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:681>); [shiftguard/agent/controller.py:702](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:702>).

**Actual independent output:** run_a followed by read_b now yields one response for each original ID. A second run in the saved turn instead yields COMPLETED/200 with two queue jobs and active_job_id=null, without waiting for run_b. run_stress_suite resumes with tool message name=run_experiment. A run followed by nine reads executes all ten calls, exceeding the eight-call cap. Ten proposals without a pause yield only eight responses, dropping c8 and c9.

**Minimal main probe node(s):** `test_S05_serial_exchange_after_job_pause[sqlite-second_run]`, `test_S05_serial_exchange_after_job_pause[sqlite-over_budget]`, `test_S05_serial_exchange_after_job_pause[sqlite-stress_name]`, `test_S05_overflow_calls_receive_rejection_responses[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S05-exchange-second_run ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S05-exchange-second_run-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S05-exchange-second_run-postgres.json>)); S05-exchange-over_budget ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S05-exchange-over_budget-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S05-exchange-over_budget-postgres.json>)); S05-exchange-stress_name ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S05-exchange-stress_name-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S05-exchange-stress_name-postgres.json>)); S05-overflow-exchange ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S05-overflow-exchange-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S05-overflow-exchange-postgres.json>)).

**Required correction, Antigravity-owned:** Use the same durable serial dispatcher for initial and resumed calls; pause on every admitted run, preserve its original name/ID, and return one bounded rejection response for each overflow ID without executing it. Preserve durable repair checks on this path.

### G6-S06 CORRECTED: Concurrent request/receipt unique conflicts return their winner

**Current source:** [shiftguard/agent/store.py:214](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:214>); [shiftguard/agent/store.py:598](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:598>).

**Actual independent output:** Barrier-synchronized identical intents both return the same durable request. Changed-body competitors return one winner plus IdempotencyConflictError rather than raw IntegrityError. Concurrent same-nonce receipt inserts both return the exact winning receipt ID/body. These six backend cases and ordinary HTTP replay pass. Completion/receipt atomicity and missing terminal receipts remain S07 blockers.

**Minimal main probe node(s):** `test_S06_concurrent_intent_returns_winner_or_conflict[sqlite-False]`, `test_S06_concurrent_intent_returns_winner_or_conflict[sqlite-True]`, `test_S06_concurrent_receipt_insert_returns_exact_winner[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S06-intents-False ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S06-intents-False-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S06-intents-False-postgres.json>)); S06-intents-True ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S06-intents-True-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S06-intents-True-postgres.json>)); S06-receipts ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S06-receipts-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S06-receipts-postgres.json>)).

### G6-S07 [P1] PARTIALLY_CORRECTED: Receipt publication is not atomic with continuation completion

**Current source:** [shiftguard/agent/controller.py:525](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:525>); [shiftguard/agent/controller.py:535](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:535>); [shiftguard/agent/controller.py:553](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:553>); [shiftguard/agent/controller.py:702](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:702>); [shiftguard/agent/controller.py:722](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:722>).

**Actual independent output:** Ordinary old-nonce HTTP replay now returns the exact original 202 bytes even after completion; an incorrect waiting nonce returns 400. Crash after COMPLETED commits but before store_receipt leaves no receipt. Retrying the original nonce returns 202 with status=COMPLETED and message="Contention on request lease. Retry in progress." forever because terminal requests cannot be claimed. Separately, a fresh RUNNING request with active_nonce=null accepts nonce=unissued, returns 202, and stores its receipt.

**Minimal main probe node(s):** `test_S07_crash_after_completion_before_receipt_replays[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S07-receipt-crash ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S07-receipt-crash-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S07-receipt-crash-postgres.json>)).

**Focused follow-up:** `test_S07_never_issued_nonce_rejected_on_running_request[sqlite]` in test_edge_contracts.py; actual JSON [sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/S07-unissued-running-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/S07-unissued-running-postgres.json>).

**Required correction, Antigravity-owned:** Bind every nonce to an actual issued request/session/generation, including terminal and RUNNING states. Commit the durable continuation outcome and exact response receipt together, or retain enough accepted continuation state to reconstruct and insert the same winning envelope after a crash.

### G6-S08 [P1] PARTIALLY_CORRECTED: Session status validation is not atomic with queue admission

**Current source:** [shiftguard/agent/registry.py:282](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/registry.py:282>); [shiftguard/agent/tools/runs.py:34](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/runs.py:34>); [shiftguard/jobs/queue.py:75](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/jobs/queue.py:75>).

**Actual independent output:** Session expiry before the registry check now prevents enqueue. Expire the session after its SELECT but before the real queue enqueue: one job is admitted and the request becomes WAITING_FOR_JOB under an expired session on both backends. The registry uses an independent read connection; the queue locks/selects only session identity and never validates its status in that admission transaction.

**Minimal main probe node(s):** `test_S08_session_authority_is_atomic_with_queue_admission[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S08-admission-race ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S08-admission-race-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S08-admission-race-postgres.json>)).

**Required correction, Antigravity-owned:** Revalidate and lock current session/request authority in the same guarded queue transaction as the side effect. A caller-constructed context and an earlier SELECT cannot supply authority.

### G6-S09 [P1] PARTIALLY_CORRECTED: Seven experiment-reading tools bypass request evidence authority

**Current source:** [shiftguard/agent/tools/results.py:56](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:56>); [shiftguard/agent/tools/results.py:155](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:155>); [shiftguard/agent/tools/results.py:222](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:222>); [shiftguard/agent/tools/metadata.py:142](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/metadata.py:142>); [shiftguard/agent/rendering.py:39](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:39>).

**Actual independent output:** The original unauthorized read_experiment_results probe is corrected: zero repository reads. With the same metadata-only prompt, get_experiment_metadata, inspect_missingness, compare_calibrators, compare_outages, get_label_budget_curve, calculate_decision_loss and generate_result_summary each perform one unauthorized publication lookup. The compare and summary paths return empirical claims while evidence_refs=[]; the renderer fails open when its allowed set is empty.

**Minimal main probe node(s):** `test_S09_every_experiment_reader_checks_request_authority[sqlite-compare_calibrators]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S09-authority-compare_calibrators ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S09-authority-compare_calibrators-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S09-authority-compare_calibrators-postgres.json>)).

**Required correction, Antigravity-owned:** Apply one fail-closed request-owned evidence check before every experiment lookup and before claim resolution. Include validated user selections and verified attached-job evidence in the durable allowed set; empty membership authorizes no empirical facts.

### G6-S10 [P1] PARTIALLY_CORRECTED: Valid evidence still permits false unchecked provider prose

**Current source:** [shiftguard/agent/rendering.py:245](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:245>); [shiftguard/agent/rendering.py:260](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:260>); [shiftguard/agent/rendering.py:265](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:265>).

**Actual independent output:** The original fabrication with zero claims is removed. After a valid authorized 0.2 Brier read, all three independent false texts survive verbatim: "Brier score is 0.0000; calibration improved.", "The method recovered and is superior; statistically significant improvement.", and "All 82 rows recovered." The heuristic only drops text when both forbidden wording and its narrow number pattern match; it never validates an explanation plan.

**Minimal main probe node(s):** `test_S10_valid_evidence_never_authorizes_unchecked_prose[sqlite-Brier score is 0.0000; calibration improved.]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S10-grounding-c18adeb2 ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S10-grounding-c18adeb2-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S10-grounding-c18adeb2-postgres.json>)).

**Required correction, Antigravity-owned:** Accept only the required strict allowlisted explanation plan, resolve every fact/direction/reference in Python, and use one bounded repair followed by deterministic valid-evidence fallback or explicit unavailable output. Never return unchecked provider narrative.

### G6-S11 [P2] PARTIALLY_CORRECTED: Null/error formatting no longer crashes, but typed outcomes disappear

**Current source:** [shiftguard/agent/rendering.py:33](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:33>); [shiftguard/agent/rendering.py:175](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:175>); [shiftguard/agent/tools/results.py:542](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:542>).

**Actual independent output:** Unsupported (2.5,7.5) now finishes without the original TypeError, but its final response only says "Analysis completed across registered tools."; UNSUPPORTED_COST_PAIR disappears. A null persisted loss keeps condition_id and loss=null, but tool status remains success and the rendered claim has no unavailable status or reason. Thus exception removal has not implemented the typed error/unavailable/null contract.

**Minimal main probe node(s):** `test_S11_unsupported_cost_is_rendered_as_typed_error[sqlite]`, `test_S11_null_loss_keeps_unavailable_and_reference[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S11-error-render ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S11-error-render-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S11-error-render-postgres.json>)); S11-null-loss ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S11-null-loss-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S11-null-loss-postgres.json>)).

**Required correction, Antigravity-owned:** Render safe structured errors and explicit unavailable/null observations with their condition references and reasons. Do not silently skip errors or label unavailable scientific outcomes as successful evaluations.

### G6-S12 [P1] PARTIALLY_CORRECTED: Required failure/fallback evidence is still truncated

**Current source:** [shiftguard/agent/rendering.py:45](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:45>); [shiftguard/agent/rendering.py:69](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:69>); [shiftguard/agent/rendering.py:109](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:109>); [shiftguard/agent/rendering.py:218](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:218>).

**Actual independent output:** The basic original failed-first condition, nine fallback rows and outage qualification now appear. Place a failed condition ninth: the tool returns it but the renderer drops it entirely because it slices conditions to eight, and the summary has no prediction_failed. All eight sparse fields survive the result projection, but final fallback_analysis drops bin_eval_counts, bin_fallback_counts, bin_support, bin_resolution_counts and bin_resolved_maps, and omits condition_id.

**Minimal main probe node(s):** `test_S12_failed_condition_after_eight_results_is_preserved[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S12-failed-ninth ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S12-failed-ninth-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S12-failed-ninth-postgres.json>)).

**Focused follow-up:** `test_S12_all_sparse_diagnostics_stay_bound_to_each_condition[sqlite]` in test_edge_contracts.py; actual JSON [sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/S12-all-eight-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/S12-all-eight-postgres.json>).

**Required correction, Antigravity-owned:** Preserve required failed/adverse/null outcomes even when display summaries are bounded. Keep all eight accepted sparse diagnostics, requested/resolved method and fallback reasons bound to each exact condition, instead of overwriting one aggregate fallback dictionary.

### G6-S13 CORRECTED: Stress aliases select the actual bank-stress worker branch

**Current source:** [shiftguard/agent/tools/runs.py:89](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/runs.py:89>); [shiftguard/jobs/worker.py:136](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/jobs/worker.py:136>).

**Actual independent output:** Real registry/queue dispatch of flagship-stress returns success and queues preset_name=bank-stress; configs/bank-stress.yaml exists. The unchanged existing worker selects StressConfig for bank-stress at worker.py:136. This closes the original nonexistent bank-stress-30 routing defect. No scientific stress execution was performed by this sidecar; parent retains worker/browser evidence.

**Minimal main probe node(s):** `test_S13_stress_alias_maps_to_existing_worker_preset[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S13-stress-preset ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S13-stress-preset-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S13-stress-preset-postgres.json>)).

### G6-S14 [P1] PARTIALLY_CORRECTED: Predictor identity and absent comparison context still qualify as improvement

**Current source:** [shiftguard/agent/tools/results.py:234](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:234>); [shiftguard/agent/tools/results.py:253](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:253>); [shiftguard/agent/rendering.py:123](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:123>).

**Actual independent output:** Different dataset, evaluation-row and mask identities now return unqualified directions; requested outage budget 25 no longer receives the stored budget-50 row, and curve/cost condition IDs are preserved. A pair with different predictor_id still renders target_temperature improved with comparison_qualified=true and delta=-0.3. Removing all context IDs from both conditions produces the same qualified improvement. base_pred is assigned but never checked; absent fields skip all validation.

**Minimal main probe node(s):** `test_S14_comparison_requires_complete_compatible_context[sqlite-predictor_id]`, `test_S14_comparison_requires_complete_compatible_context[sqlite-missing_context]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S14-context-predictor_id ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S14-context-predictor_id-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S14-context-predictor_id-postgres.json>)); S14-context-missing_context ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S14-context-missing_context-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S14-context-missing_context-postgres.json>)).

**Required correction, Antigravity-owned:** Require complete compatible persisted dataset/predictor/evaluation/source-map/mask/policy context before computing or declaring a comparative direction. Missing identity evidence is unqualified/unavailable, not implicit compatibility.

### G6-S15 [P2] PARTIALLY_CORRECTED: Schema defaults and semantic allowlists disagree

**Current source:** [shiftguard/agent/schemas.py:111](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/schemas.py:111>); [shiftguard/agent/policy.py:69](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/policy.py:69>); [shiftguard/agent/registry.py:309](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/registry.py:309>); [shiftguard/agent/tools/results.py:205](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:205>).

**Actual independent output:** Temporal-lead/MCAR-0.20 advertising, ambiguous missingness selectors, substring condition aliases, arbitrary method and arbitrary focus probes are corrected. Nevertheless generate_result_summary with only experiment_id uses its advertised default focus=all and returns UNSUPPORTED_PARAMETER; its documented all/fallback/outages/calibration names disagree with overview/calibrator/outage/cost policy. A persisted invented_scenario/budget17 condition is accepted by compare_calibrators, so semantic validation still depends on matching stored names.

**Minimal main probe node(s):** `test_S15_advertised_default_summary_is_executable[sqlite]`, `test_S15_impossible_scenario_and_budget_rejected_before_matching_records[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S15-default-summary ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S15-default-summary-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S15-default-summary-postgres.json>)); S15-impossible-combination ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S15-impossible-combination-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S15-impossible-combination-postgres.json>)).

**Required correction, Antigravity-owned:** Align schema defaults/descriptions with canonical supported semantics. Validate scenario/budget/method/predictor combinations before repository selection, without adding scientific configurations.

### G6-S16 [P1] PARTIALLY_CORRECTED: Metadata filtering is shallow rather than an approved projection

**Current source:** [shiftguard/agent/tools/results.py:174](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:174>); [shiftguard/agent/tools/results.py:177](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:177>); [shiftguard/agent/tools/results.py:190](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:190>); [shiftguard/agent/schemas.py:122](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/schemas.py:122>).

**Actual independent output:** The original top-level dataset_csv path is removed. A nested config path, synthetic api_key, raw_labels and a dataset.path still reach the next scripted provider input and public trace. protocol fields are also forwarded verbatim. The handler blacklists a few top-level keys/string forms while accepting arbitrary nested values; no typed bounded output projection is enforced.

**Minimal main probe node(s):** `test_S16_nested_private_metadata_never_reaches_provider_or_public_trace[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S16-projection ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S16-projection-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S16-projection-postgres.json>)).

**Required correction, Antigravity-owned:** Define a per-tool strict public result schema and project allowlisted config/provenance IDs, hashes and aggregates. Exclude arbitrary nested config, raw labels and server paths before persistence/model transport/public trace.

### G6-S17 [P2] PARTIALLY_CORRECTED: Rejected arguments remain in the durable provider transcript

**Current source:** [shiftguard/agent/controller.py:36](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:36>); [shiftguard/agent/controller.py:299](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:299>); [shiftguard/agent/controller.py:319](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:319>); [shiftguard/agent/registry.py:229](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/registry.py:229>); [shiftguard/agent/registry.py:274](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/registry.py:274>).

**Actual independent output:** The 200000-byte argument is rejected before handler execution and the public trace is reduced to 1577 bytes. However messages_json is 202185 bytes and retains the complete rejected blob; the next provider turn receives it unchanged. A small rejected api_key=SYNTHETIC_PRIVATE_VALUE is also persisted and returned in public trace arguments plus the raw Pydantic validation error. Argument truncation alone has not bounded/sanitized the accepted transcript and rejected metadata.

**Minimal main probe node(s):** `test_S17_rejected_oversized_arguments_not_retained_in_transcript[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S17-bounded-transcript ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S17-bounded-transcript-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S17-bounded-transcript-postgres.json>)).

**Focused follow-up:** `test_S17_rejected_private_arguments_not_publicly_echoed[sqlite]` in test_edge_contracts.py; actual JSON [sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/S17-invalid-private-argument-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/S17-invalid-private-argument-postgres.json>).

**Required correction, Antigravity-owned:** Validate/bound provider decisions before storing assistant_tool_msg. Persist safe validated arguments or bounded structured rejection metadata; sanitize validation/handler errors and bound transcript, IDs, names, results and collections independently of provider-adapter limits.

### G6-S18 [P1] PARTIALLY_CORRECTED: Failed job trace becomes an unreadable HTTP 500 and evidence linkage is unchecked

**Current source:** [shiftguard/agent/controller.py:58](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:58>); [shiftguard/agent/controller.py:592](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:592>); [shiftguard/agent/controller.py:607](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:607>); [shiftguard/agent/controller.py:625](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:625>); [shiftguard/agent/controller.py:720](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:720>); [shiftguard/agent/schemas.py:135](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/schemas.py:135>); [shiftguard/jobs/worker.py:176](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/jobs/worker.py:176>).

**Actual independent output:** Terminal trace statuses and attached job.experiment_id fallback are corrected. A legitimate dictionary job error is now copied into result.error but ToolTraceEntry.error requires str: resume and subsequent GET both return HTTP 500, request status becomes FAILED, and no receipt is written. A cancelled trace records cancelled but its final answer still says only "Analysis completed across registered tools." A completed job whose result names an unpublished ID different from job.experiment_id accepts that forged ID as evidence and announces it as published without checking publication linkage.

**Minimal main probe node(s):** `test_S18_terminal_trace_and_answer_preserve_job_failure[sqlite-cancelled]`, `test_S18_unpublished_conflicting_result_id_not_accepted_as_evidence[sqlite]`. Both backend variants were executed; this is not a proposed test.

**Observed JSON:** S18-terminal-cancelled ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S18-terminal-cancelled-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S18-terminal-cancelled-postgres.json>)); S18-job-evidence-binding ([sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S18-job-evidence-binding-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/run-440ccc06b7664294bd6dc62b2fe86e95/S18-job-evidence-binding-postgres.json>)).

**Focused follow-up:** `test_S18_failed_job_resume_is_safe_http_and_replayable[sqlite]` in test_edge_contracts.py; actual JSON [sqlite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/S18-failed-http-sqlite.json>) / [postgres](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/correction-review-20261001/sol/edge-1b81e2a8282b48db9928d2a82af0a436/S18-failed-http-postgres.json>).

**Required correction, Antigravity-owned:** Finalize a typed safe terminal result/trace and exact receipt in one fenced continuation transition. Render failed/cancelled outcomes explicitly. Resolve evidence only from consistent attached-job identity and verified publication/execution linkage; reject missing or conflicting evidence instead of claiming publication.

## Affected invariant verdicts and handoff boundary

| Affected invariant | Verdict | Original findings |
| --- | --- | --- |
| Durable accepted decisions/counters/repair admission | FAIL | S01, S02 |
| Current request owner/session authority and guarded admission | FAIL | S03, S08 |
| Prompt resume, original IDs, serial work, bounded calls | FAIL overall; ordinary waiting lease corrected | S04 corrected; S05 remains |
| Concurrent durable identity/receipt insert replay | PASS for original unique-conflict reproductions | S06 corrected |
| Issued nonce and crash-safe exact response receipt | FAIL | S07 |
| Authorized grounded facts and truthful null/adverse/fallback semantics | FAIL | S09–S12, S14–S18 |
| Actual stress preset routing | PASS within dispatch/worker-resolution scope | S13 corrected |
| Parent full suite / browser / provider / package / hashes | NOT_RUN by sidecar; parent-owned | P01–P07 excluded |
| Live exact-model evidence | BLOCKED_REQUIRED_LIVE_EVIDENCE; not invoked | A7 outside this review |

**Next correction boundary:** Antigravity corrects the fifteen remaining original S findings as one integrated delta together with the parent-owned packet. Preserve all original failure records and this evidence. Sol re-review remains limited to those correction deltas and affected invariants; parent owns full-suite, source binding, integration and final acceptance. This packet does not create an application change, commit, gate acceptance or additional audit phase.
