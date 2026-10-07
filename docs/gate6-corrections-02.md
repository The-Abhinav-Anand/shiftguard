# AG-G6-CORRECTIONS-02 — Antigravity execution packet

1 October 2026. **Implement the 22 remaining findings from [the independent correction review](gate6-correction-review-20261001.md), together with [all current S reproductions](gate6-correction-sol-review-20261001.md).** Antigravity is the sole application writer; GPT-6.1 Sol Extra High independently reviews the integrated correction delta. Internal batches below are implementation dependencies, not repeated approval/review gates.

## Scope, input and completion authority

- Working HEAD `83037b0f02eef62203c3f565a063d824af2722d7`, dirty; accepted Gate 5 source `f63116fedc2751493d79d44897ba913b6d28b0b5`.
- Preserve author attempt `corrections-954b80fb-d425-48d3-b157-d93a7a91b906` and original attempt `offline-f72afeff-0cad-438f-bccb-157a39b08ef1` byte-for-byte. Do not edit their reports, fixtures or SQLite files.
- Author-declared 44-file digest `fd84e1ff09bffc67a24d6d6f26aa6ffc8d4b4dcfca2c2ad96ab5a3a8926cbf1a`; current same-path digest `28731222f12c4237e8e55d7a986a50868c82d6ae153b48a1394ca4d109409ffa`. Difference is the implementation Markdown, not the other 43 entries. Start from actual working bytes, not a claimed old checksum.
- Closed controls: S04 waiting lease release, S06 conflict-safe request/receipt insertion, S13 actual stress preset routing. Preserve their positive and negative behavior; their passing controls do not waive adjacent open contracts.
- Open S IDs: **S01/S02/S03/S05/S07/S08/S09/S10/S11/S12/S14/S15/S16/S17/S18**. Open P IDs: **P01–P07**.
- Current regression baseline: 373 ordinary cases pass with live isolated PostgreSQL16; independent Sol 118 correctness cases have 76 failures; parent provider/evidence/startup/migration/browser defects are reproducible. The complete raw evidence is `../verification/gate6/correction-review-20261001/`.
- No paid/live calls, install/global configuration, confirmatory seeds/protocol change, broader Gate 4 rewrite, BYO/upload work, frontend redesign, deletion, source commit, push or deployment. Parent owns source commit and separate governance checkpoint after actual acceptance.

## C0 — Freeze one executable contract and permanent failure corpus

**Files:** existing agent schemas/policy/store/controller, API route, queue admission, migration owner, frontend agent hook/API/panel, provider/preflight, evidence script; their focused tests only. Update exact allowlist before source edits. Existing metadata/run/result handlers and renderer stay their canonical owners; no general agent framework or second scheduler.

1. Inspect current owner/HEAD and source; maintain one active writer. Create a new immutable `corrections-<uuid>` attempt. Preserve current governance as historical author/independent records.
2. Read and run cheap minimal examples from each open S/P row. Import reviewer helpers by copying their exact reviewed versions into the new attempt or transfer equivalent permanent tests; never edit original reproductions into weaker expectations. Use actual SQLite and unique PostgreSQL schemas with separate-connection barriers.
3. Write one compact transition table: request phase, provider-turn acceptance, proposed call/ordinal, validated durable intent, guarded queue admission, waiting job, terminal tool response, next intent, final answer, continuation response receipt. For every write, state authority predicate, transaction boundary, replay identity and legal terminal outcome. Map each open finding to that owner/test.
4. Keep six provider turns/eight executable calls and one corrective attempt per normalized invalid signature across waiting/restart/retry. Bound the maximum accepted provider response and return one safe rejection for every overflow call ID without executing it. Track proposals/rejections explicitly without hiding a cap violation in reset counters.
5. Freeze typed safe tool/error/final-plan schemas and approved semantics from existing Bank/config/policy owners. Choose finite validated provider bounds compatible with lease policy. Existing seed 31001 and scientific/numerical choices do not change.

**Exit:** exact contracts and reproduced failures, not a fresh claim that all items are resolved. Do not spend this phase rerunning unchanged scientific gates.

## C1 — One durable, fenced execution/continuation protocol

**Findings:** S01/S02/S03/S05/S07/S08/S18 protocol parts; P05. **Owners:** `shiftguard/agent/{store,controller,schemas,policy}.py`, `shiftguard/jobs/queue.py` narrowly, `shiftguard/api/routes/agent_requests.py`, forward Alembic repair revision and permanent protocol tests.

### Migration continuity first

Restore/document the already-applied 0009 baseline shape and add a new forward repair revision, allocating from actual current head. It must handle both original persisted 0009 and the expanded author-correction shape; add missing fields conditionally and backfill deterministic safe values. Existing requests without a legitimate nonce get a newly issued persisted nonce in a legal waiting transition, not acceptance of arbitrary supplied nonce. Do not change frozen revisions 0001–0008. Preserve all existing rows/constraints and nonempty session/request/job/receipt/result/execution data. Test the exact copied historical author SQLite plus PostgreSQL fixtures; fresh and 0008 upgrades alone are insufficient.

### Guarded transaction contract

Add the minimum connection-aware queue primitive in the existing queue owner. Reuse ordinary quota/idempotency/admission behavior; do not implement a parallel enqueue path in the controller. A caller already holding the SQLite write transaction must not open a second writer. PostgreSQL uses the established locks in consistent order.

For a side-effect transaction, atomically:

1. Lock/read the durable request and session. Require matching request/session, worker owner/generation, legal phase, unexpired request lease and current ACTIVE authority. Revalidate token/authority version bound to the originally verified request if it can rotate; an earlier API/registry SELECT is not sufficient.
2. Read the saved normalized tool intent/ordinal and budget/repair ledger; validate immutable key/body hash and that it is eligible. Use exactly `agent:{request_id}:{ordinal}` through normal admission, retry and recovery.
3. Insert-or-read the authorized queue job through the same DB connection. Existing matching intent replays its exact job; changed content conflicts; quota remains serialized.
4. Persist the owned job link/tool state and request pause together, checking every conditional rowcount. If any predicate loses, roll back all trace/job/event/request changes. Release WAITING ownership promptly while preserving the durable generation/continuation identity.

Do not hold any DB transaction across provider awaits, worker completion waits or network operations. Renew bounded leases outside those transactions or ensure a whole provider attempt/parsing interval fits the lease; stop if authority is lost. Fencing applies to tool trace and receipts as well as the request's last status update.

### Durable provider turn and one serial dispatcher

- Persist the complete **validated/sanitized accepted** provider decision, original IDs/names/order, turn/call budget and pending cursor before any handler side effect. Invalid/oversized raw decisions are bounded rejections, not accepted transcript blobs.
- Unify initial execution and resume through one serial intent dispatcher. Recover saved accepted work without asking the provider for a new decision. Replace the missing `get_job_by_key` call with the existing canonical scoped idempotency lookup/guarded primitive.
- Enqueue crash points before/after admission/link/result/acknowledgment must recover one request and one job. After every run intent, pause again; a second run must not become an orphan while request reports COMPLETED.
- Emit exactly one response for each original call ID, with the actual original name. Preserve remaining reads/runs and safe overflow responses; never reset caps or skip repair admission on resume.
- Use the same structured normalized repair signature before admission and when recording failure. Initial failure plus one corrective attempt is allowed; later same-signature calls never reach handler/queue, including across restarts and changed call IDs.

### Exact continuation result and receipt

- Nonce must have been issued for this request, session and waiting generation; reject arbitrary values in RUNNING/terminal states too. Distinguish non-consuming in-progress polling from a completed continuation receipt.
- Commit terminal/pause outcome and exact documented HTTP receipt atomically, or preserve enough accepted continuation state to reconstruct the **same** winning status/body after interruption. A terminal request without receipt must not remain forever at 202/COMPLETED lease contention.
- Keep existing conflict-safe receipt insertion. Retry returns its exact winning response, including after later request progress.
- Typed failed/cancelled job errors must fit public trace schema. Dict-valued worker errors cannot create resume/GET 500. Final answer retains terminal failure/cancellation; verify consistent attached job experiment identity and PUBLISHED/execution linkage before accepting evidence.

**Exit proof:** all original durability/authority barriers, second-run/overflow cases, receipt-crash/unissued-nonce cases and failed/cancelled HTTP cases pass on both backends, alongside S04/S06/S13 controls. No phantom queue job, missing response, duplicate acknowledgement or partial publication/trace survives a losing transaction.

## C2 — One authorized, typed grounding/projection pipeline

**Findings:** S09/S10/S11/S12/S14/S15/S16/S17 and S18 evidence parts. **Owners:** registry/schema/policy, existing metadata/result handlers, rendering/prompts/controller; permanent semantic/grounding tests.

1. Require one durable evidence-membership check before **all eight experiment readers**, comparisons and final fact resolution. Populate membership only from validated user-selected evidence or verified attached-job publication. Model-created IDs, prompt substrings or empty allowed sets do not grant authority. An empty allowed set authorizes no empirical facts.
2. Replace arbitrary result/config forwarding with strict per-tool safe projection models. Allow known IDs/hashes/aggregates; exclude raw labels, arbitrary nested config, storage paths, credentials and runtime data before transcript persistence or model/public transport. Do not add another blacklist around a dictionary.
3. Bound/sanitize the complete provider transcript before storage: argument bytes, names/IDs, collection lengths, result sizes and validation errors. Preserve only validated arguments or safe rejection codes/field locations. Never keep a rejected 200 KB value in `messages_json` or echo private values through Pydantic error input.
4. Actually implement the required allowlisted explanation-plan schema. Provider may choose allowed templates and authorized condition references; Python supplies every number, empirical direction, qualification and text. Reject raw empirical narrative. Use one bounded repair under the same turn policy, then deterministic valid-evidence fallback or explicit unavailable outcome.
5. Keep typed UNSUPPORTED_COST_PAIR and null/unavailable reason/condition IDs visible in final output. Preserve failed/adverse/cancelled conditions beyond a display limit through deterministic selected summaries or pagination; do not slice away the failed ninth condition.
6. Keep all eight accepted sparse diagnostics bound per condition, including `bin_eval_counts`, `bin_fallback_counts`, `bin_support`, `bin_resolution_counts`, `bin_resolved_maps`, and the existing aggregate fields. A single overwritten fallback dictionary is not preservation of multiple conditions. Reuse the accepted Gate 5 projection contract.
7. Require complete compatible comparison context; predictor equality is mandatory, and missing identity fields are unavailable/unqualified. Bind each curve/cost/budget row to its actual condition. Different calibration maps are allowed when that is the comparison, but each map's fitted context/parameters must be verified. Use existing scientific policies; no new matching tolerance or method choice.
8. Align all twelve tools' strict defaults, advertised metadata, semantic allowlists and actual handler behavior. The advertised `generate_result_summary` default must execute. Unsupported scenario/budget/method/seed/predictor combinations fail before lookup even if matching fabricated records exist.

**Exit proof:** unauthorized-reader, false-prose, null/error, sparse/failure ordering, mismatched/missing context, nested-private metadata and rejected-transcript cases pass on both backends. New tests use complete typed valid fixtures plus explicit negative mutations; do not test only absence of prose when there are no valid claims.

## C3 — Browser-owned intent and explicit authority recovery

**Findings:** P01/P02 and browser effect of S07/S18. **Owners:** `frontend/src/hooks/useAgent.ts`, agent API client/panel and App composition; preserve accepted Gate 5 hooks/cache/results.

- Define bounded principal-bound phases for unsent/pending acceptance, RUNNING, WAITING, resuming, terminal and recoverable transport failure. Save canonical prompt/key before POST, then actual request/job/issued nonce before further requests.
- On reload, expose unresolved stored intent even without a request ID/error. Retry/reconcile uses the exact original key/body under its original valid authority. Rehydrate every supported nonterminal phase, not only known-ID WAITING. Keep displayed key and accepted response-loss identity stable.
- Recognize capability error codes separately from provider/business/transport errors. Explicit Reconnect establishes/verifies new credentials and resets obsolete auth UI; it does not silently migrate old accepted work or overwrite preserved public results.
- Use epoch/AbortController/in-flight guards for query, poll, GET and resume. Clear/new inquiry/reconnect/unmount invalidate earlier callbacks/timers. Do not generate continuation nonces or allow delayed responses to recreate cleared cards.
- On transient poll/resume/accepted-response loss, retain a bounded recovery action and latest issued nonce. Retry a pending continuation by its exact issued identity/receipt rather than inventing another run. Storage errors are visible, not silently treated as durable persistence.
- Transfer the parent actual HTTP/browser failures into permanent tests. Test accepted POST response loss before reload, WAITING reload, lost resume response, delayed callback after Clear, actual session expiry followed by explicit reconnect, provider 401/business 403, cancellation/failure and two sequential questions. Keep all nine accepted Gate 5 cases.

**Exit proof:** real API/queue/worker browser cases, with scripted provider explicitly labeled; no fake queue/job/receipt as success proof. Parent admission-only probes deliberately disable workers; final continuation proof must run the real worker too.

## C4 — Bounded provider, preflight and isolated harness

**Findings:** P03/P04/P07. **Owners:** existing provider/settings/prompts, preflight script, app composition and explicit test factory; no inference allowed.

1. Put the complete actual SDK call and response parsing in typed sanitized handling. Fixed public errors; known configured secret replacement in all retained/logged errors; no raw arbitrary upstream text. Validate choice/tool/content/usage/model shapes and byte limits. Invalid empty choices are a typed failure.
2. Add finite positive timeout/output limits and bounded retry settings. Each request contains an explicit output limit. Use timeout/retry duration compatible with request leases. Actual adapter MockTransport tests verify classification, known secret removal, parsing, bounds, client shutdown and retry count.
3. Preflight remains offline by default. Live mode requires explicit exact model and positive allowances; disable hidden SDK retries or count every wire attempt. Reserve conservative input+output before each call; missing usage cannot release budget or authorize another call. Stop before insufficient allowance, always writing a truthful final evidence status.
4. Validate PONG, exact model, strict tool parameters, original call-ID tool-response exchange and structured explanation-plan/fallback. Every required canary is PASS or overall result is not PASS. One-call/one-token, wrong prefix model/content/arguments, unknown usage, 429 and missing plan are negative cases using fake transport only.
5. Ordinary hosted app cannot activate a scripted provider through environment flags or injected test dependencies. Disabled setting remains authoritative. Use a dedicated isolated test application/harness with explicit mode, and label API/UI/results/evidence scripted. Verify ordinary local and hosted disabled paths and invalid hosted test activation.

**Exit proof:** all parent provider/preflight/startup assertions pass, including actual SDK MockTransport. A7 remains BLOCKED until a separate explicitly authorized live attempt; never claim its canaries from these offline tests.

## C5 — Evidence derives from execution, then one final review

**Findings:** P05 proof remainder/P06 and truthful overall handoff. **Owners:** existing `scripts/execute_gate6_offline_suite.py`, focused verifier-hygiene tests, package tests and current governance.

1. Generate one per-obligation proof map from real collected node IDs and actual test outcomes/backend coverage. Delete no regression to make collection pass. No literal RESOLVED or aggregate agent success satisfies a finding without its executed negative proof. Required skip/missing case/report/wrong count/failed canary → BLOCKED/FAIL/NOT_RUN as applicable.
2. Validate complete JUnit testcase trees and recursive Playwright outcomes. Check report counts against actual cases; reject all-skipped or empty/fabricated-positive reports. Missing browser report cannot give A4 PASS. Preserve nonzero command exits and fail safely if package or Git operations fail.
3. Snapshot source/helper/generated/protected hashes **before** tests and compare after. Capture real Git availability, HEAD/dirty and failed-command state. Include every executable helper and generated/deleted asset. Final implementation/governance Markdown must either be finalized before packet binding or have an explicitly separate checkpoint hash; do not calculate a digest then mutate a member.
4. Build exact wheel; compare contents/source, validate import origins and run fresh/supported upgrades, CLI/API/agent outside checkout on SQLite and required PostgreSQL. Dependency/runtime installation remains outside this scope; use existing tools.
5. Self-test the evidence builder with missing reports, all required skips, fake counters, nonexistent proof node, wrong backend, failed commands/canary, changed source and wrong package origin. Each prevents PASS. Preserve the failed injected attempts as evidence.
6. Run tests in this order: cheap focused negatives → permanent agent/protocol/API/queue/migration cases on both backends → typecheck/isolated build → all Gate 5 plus new real browser recovery cases → static/package/upgrade → **one** full ordinary suite on stable source → final source/report binding. Use fresh temporary directory per pytest and immutable attempt per evidence build.
7. Shared queue admission modifications require the affected accepted ownership/quota/cancel/publication regression cases, not another broad historical audit. Scientific Gate 2/3 reproduction is required only if numerical/publication identity or their owned execution changes. No confirmatory inference or scientific choices are authorized.

Use the existing `.tools/use-existing-test-postgres.ps1` with narrowly authorized WSL access; never print its derived URL. Current verified service is PostgreSQL16.15, but recheck the exact service before a new batch rather than inheriting availability. Do not install a substitute.

### Final handoff checklist

- All 22 open original IDs independently demonstrated corrected; S04/S06/S13 controls preserved.
- Current ordinary collection/full suite, actual required PostgreSQL cases, browser and exact installed/extracted package obligations have actual counts/commands/reports with no required skips.
- One unchanged candidate manifest, protected comparison, full generated/served parity, package origins, complete source/history/exit binding; initial reviews and author attempts untouched.
- Typed null/error/fallback/unqualified/adverse results and public-safe transcripts verified end-to-end.
- One compact Antigravity correction packet submitted; one consolidated GPT-6.1 Sol xhigh review of changed behavior/affected invariants, all material findings returned together. Parent owns final acceptance/source commit/checkpoint. No self-acceptance by the producer.
- Gate 6 remains pending while any offline contract or A7 live proof is missing. Do not open Gate 7 or claim perfect/all-resolved from passing happy-path tests.

No new user input is needed for C0–C5 offline execution. Exact-model account access and an explicit live call/token allowance are required only for A7 after offline correctness passes.
