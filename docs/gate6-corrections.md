# AG-G6-CORRECTIONS-01 — complete Antigravity execution packet

30 September 2026. **Authorized next scope: correct the frozen Gate 6 offline candidate.** Antigravity is the sole application writer; GPT-6.1 Sol Extra High (`gpt-6.1-sol`, `xhigh`) independently reviews the stable result. Do not implement Gate 7 or execute paid/live inference.

Read [the consolidated review](gate6-review.md), [all Sol application findings](gate6-sol-review.md), [Gate 6 contracts](gate6-execution-plan.md) and current `AGENTS.md`. The reviewed source is digest `4d392741d38da64eb480f5f04bc97a3221649ee9a7ef7b4e8ec13be4fcc9e1d8`, dirty on HEAD `83037b0f02eef62203c3f565a063d824af2722d7`. Preserve it, every original report and the accepted Gate 5 source `f63116fedc2751493d79d44897ba913b6d28b0b5`.

Finish the whole batch and ordinary debugging before one review handoff. These internal phases are ordered implementation dependencies, not separate permission or review gates. Resolve every S/application and P/parent finding in the two reports; do not narrow the batch to the seven parent entries.

## 1. Repair the durable state protocol first

Owners: `agent/store.py`, `controller.py`, `schemas.py`, `policy.py`, the agent request routes and a forward migration if required.

1. Define and enforce legal request/tool states and recovery transitions. Separate a durable provider-turn ledger, proposed tool ordinal, validated intent, enqueue outcome and completed tool response. Restore exact stored provider response/intents rather than calling the provider again after a crash.
2. Count every proposed call, including rejected calls, before executing it. Persist counters and repair signatures transactionally; six turns/eight calls apply across waiting, restarts and retries. Permit one correction per normalized invalid-call signature despite changed IDs; a repeated invalid signature cannot continue a dispatch/repair loop. A final-answer repair uses the same turn budget.
3. Fence every state write, trace write and side-effect admission with current request owner/generation and a non-expired lease. Never ignore a failed CAS. Use a finite, validated lease policy compatible with provider timeout/retry duration; renew or stop before expiration. Protect dispatch itself, not only the last request-status update. If existing queue admission lacks a transaction-aware primitive, add a minimal connection-aware guarded enqueue path in the queue owner, reusing current idempotency/quota/admission logic. Check and lock request generation/lease and current session status in the same database transaction that admits its queue job. SQLite uses the existing immediate write-transaction discipline; PostgreSQL locks the relevant rows. Do not hold a write transaction across a provider await or try to open a second SQLite writer while holding the first.
4. Persist the complete accepted provider response and ordered tool intents before enqueue. Recover PENDING intents in ordinal order. Existing queue idempotency must use the same session/request/ordinal-derived key at every retry. Crash before enqueue, after enqueue before job-link persistence, and after result before acknowledgment must recover one request and one job with the original intent.
5. Serialize multiple calls, including those after a waiting side effect. Persist their unfinished positions. Append exactly one matching response per original `tool_call_id`; never duplicate the run call's tool response or omit a following call. Do not regenerate accepted decisions after resume.
6. Use request-scoped, server-issued durable continuation identity and replay receipts. Bind nonce to request, session and waiting generation; reject arbitrary/foreign values. Concurrent/resubmitted same-nonce operations have one continuation winner and return the same documented envelope. Store the actual HTTP response shape, not an internal partial result. Release waiting ownership promptly so completed jobs can resume without a full lease wait. Use conflict-safe insert-or-read for same-intent requests and receipts, verifying the winning body hash; duplicate operations must not raise raw IntegrityError. Lease contention returns 202/in-progress and cannot consume a final receipt for continuation that did not occur.
7. Check dispatch-time authority for the current request/session and permitted evidence. Model-created IDs and a caller-created ToolContext are not authority. Keep browser capability lifetime separate from one completed agent request; two questions work in one valid session. Preserve legacy session continuation behavior.
8. Reject or handle cancellation and failed jobs explicitly; do not present their results as successful or cancel other jobs in the session. Finalize the original tool execution/trace with completed/failed/cancelled outcome in the same fenced state transition. Resolve evidence only through the attached job's result/experiment_id and verified publication linkage; remove the unrelated global latest-publication fallback. Keep failed/cancelled outcomes in the deterministic answer and replay receipt.

Write independent barrier/fault-injection regressions for each persistence boundary on both SQLite and PostgreSQL, using unique files/schemas. Use the existing queue/publication owners. Any missing primitive needs a narrow demonstrated reason, an affected invariant test and a reviewed ownership change; this packet does not authorize a broad Gate 4 rewrite.

## 2. Repair tool semantics and deterministic grounding

Owners: registry/schemas, grouped metadata/run/result handlers and rendering/prompts.

1. Keep exactly twelve registered names. Validate strict JSON and semantic combinations before dispatch, including seed, dataset, predictor, scenario, budget, method and cost. Unsupported combinations return typed unavailable/error results. Never coerce a requested run into a different preset.
2. Map `run_stress_suite` to an actual existing executable preset (`bank-stress` where applicable), not a fabricated config name. Disclose the preset's actual multi-condition scope. Verify a real queue worker can resolve and complete the preset.
3. Read Bank metadata and scenario IDs/parameters from authoritative existing config/manifests/persisted evidence. Do not hardcode erroneous feature-role counts or report requested rates as realized missingness. Return unavailable where evidence is absent, with denominator meanings.
4. Restrict all experiment reads/comparisons/summaries to authorized visible evidence membership. Validate compatible dataset/predictor/evaluation/source-map/mask/scientific-policy identities. Preserve comparison qualification and unqualified reasons; never compare unrelated rows merely by method/metric name.
5. Return typed bounded public projections. Preserve failed/null conditions, adverse values, all eight accepted sparse-bin diagnostics and supported persisted cost-grid rows. Unsupported decision costs yield `UNSUPPORTED_COST_PAIR`; missing/failed persisted metrics yield typed unavailable results without throwing an untyped exception.
6. Replace unchecked provider narrative with an allowlisted explanation-plan schema. The plan can select templates and authorized persisted references; Python resolves every numeric value and empirical direction. Reject invented IDs, paths, numbers, superiority/significance/recovery claims, raw HTML and unsupported prose. One bounded repair is allowed; thereafter return an accurate deterministic fallback/unavailable answer.
7. Expose fallbacks, failed conditions, null metrics and unqualified comparisons in final output and the reused scientific views. Do not silently omit inconvenient evidence. Preserve the single-seed 31001 limitation and avoid claims of significance.
8. Bound provider arguments/transcript/messages/results/trace/evidence collections by count and bytes before persistence and acknowledgment. Invalid arbitrarily large arguments must not become stored/public trace. Reject raw rows, labels, predictions, paths, credentials and private internals.

Add negative fixtures independent of the handler's current output: invented evidence, mismatched contexts, false qualitative/numeric claims, adverse/null/unqualified results, unsupported preset/costs and oversized payloads. Tests must verify the actual renderer/public response, not just a successful status flag.

## 3. Restore browser recovery and provider boundaries

Owners: `frontend/src/hooks/useAgent.ts`, `api/agent.ts`, bounded workspace state, AgentPanel/App and provider/settings/preflight.

1. Persist a session-bound pending agent intent before submit, with UUID/key/canonical body, then accepted request/job/nonce and safe result references. Retain identity during network failure, accepted-response loss, reload and resume-response loss. A Retry action reuses the same key/body; an explicit new inquiry creates another key. Clear is a UI action, not silent cancellation or credential transfer.
2. Rehydrate saved requests only under their original valid credentials and refresh with GET. Poll actual jobs and resume with the stable issued nonce. Add bounded recovery for transient poll/resume failures and in-flight guards. Avoid stale callbacks/responses reviving cleared or replaced-session work.
3. Replace automatic `workbench.reconnect()` on agent rejection with the accepted explicit Reconnect pattern. Recognized session-auth errors disable submission and explain recovery; provider 401, business 403 and transport errors do not rotate session. Reconnect preserves published cache and does not replay private old work under new authority.
4. Keep ResultDetails/cache and all nine accepted Gate 5 browser tests intact. Two sequential questions, provider failure, failed/cancelled jobs, manual presets and cached numeric views must remain usable. Add keyboard/mobile/error-announcement coverage where new controls change behavior.
5. Put the entire provider request/response parsing inside sanitized typed failure handling. Use fixed public errors, redact configured key values explicitly and never copy arbitrary upstream exceptions into public output/logs. Validate response shapes, names/call IDs, sizes and settings timeout/retry/output bounds. Exercise the actual OpenAI adapter with offline MockTransport, including async shutdown.
6. Isolate scripted providers in test application construction or a guarded test harness; disallow fake provider activation in ordinary hosted startup. Return provider kind and label scripted UI/evidence accordingly. `agent_enabled=False` stays authoritative for ordinary startup. Do not mistake a scripted response for live Nemotron.
7. Make preflight offline by default. Validate explicit exact-model and positive call/token allowances before any network operation; disable hidden retries or account for every attempt. Enforce conservative total token and output limits before each call, stop on insufficient/unknown budget, verify all chat/tool/structured-plan/fallback canaries, require matching exact model and original call IDs, and fail on any failed/missing canary. The script must not write overall PASS when one canary failed. No real invocation of `--live` is authorized in this batch.

Browser regressions must include real API/queue accepted-then-lost submit response, WAITING reload, completed resume response loss/replay, actual expired-session recovery, unrelated business failure, cancellation/provider failure, and real worker run/read/compare. Provider injection may be scripted; the queue/worker/persistence must stay real. Preserve the parent probe artifacts as original failures.

## 4. Integrate the tests, migrations and trustworthy evidence

1. Fix the three new test module-name collisions so the documented normal full-suite command collects. Update current-head assertions for forward migration 0009 while retaining upgrade-from-0005/0008 state-preservation checks. Do not remove old regressions or use a diagnostic override as acceptance.
2. Verify fresh/upgrade paths on SQLite and PostgreSQL. If the unaccepted 0009 candidate shape must change, document it and test upgrading existing 0009 databases through a forward repair revision when persistence compatibility requires one; never rewrite frozen revisions 0001–0008.
3. Build and inspect a candidate wheel and run migration/CLI/API/agent import smoke outside the source checkout. A source checkout import is not installed-wheel proof. Keep exact package resource evidence.
4. Rewrite the offline evidence generator to derive PASS/FAIL/BLOCKED/NOT_RUN from actual collected test reports/commands/required backend coverage. Preserve all command errors and logs. Missing reports, required skips, failed canaries, inconsistent counts and stale source must prevent PASS. Test these negative cases with offline injection.
5. Capture actual HEAD/dirty status and all relevant source hashes before/after commands, include verification scripts and generated/deleted assets, and explicitly compare protected backend/config/migration files. Omit no executable helper. Do not print PostgreSQL URL prefixes or credentials. Use current reviewer GPT-6.1 Sol; preserve historical Astra reports unchanged.
6. Create a fresh immutable `../verification/gate6/corrections-<uuid>/` attempt with source manifest, command exit codes, complete logs/JUnit/collected node IDs, Playwright JSON/screenshots, contract evidence, package smoke and exact parent/application finding-to-proof map. Correct the implementation report by adding a dated correction record; do not overwrite the original external author attempt.

## Verification and handoff

Use this complete closure map; implementation details and independent reproductions remain in the two original reports.

| Findings | Required correction owner/step |
| --- | --- |
| S01 | Phase 1: persisted response/intents/counters and crash replay with one queue key |
| S02 | Phase 1: durable normalized repair ledger and pre-dispatch stop |
| S03 | Phase 1: lease/generation/authority-fenced writes and atomic guarded admission |
| S04 | Phase 1: release waiting lease and correct in-progress receipt semantics |
| S05 | Phase 1: persist remaining calls and one original-ID tool response |
| S06 | Phase 1: concurrent insert-or-read intent and receipt replay |
| S07 | Phase 1: issued nonce and exact recorded HTTP envelope replay |
| S08 | Phase 1: current session authority checked atomically at admission |
| S09 | Phase 2: request-owned evidence membership before reads/rendering |
| S10 | Phase 2: validated explanation plans; no unchecked narrative |
| S11 | Phase 2: typed error/unavailable/null decision loss rendering |
| S12 | Phase 2: failed/adverse/fallback/qualification preservation |
| S13 | Phase 2: actual bank-stress preset/worker binding |
| S14 | Phase 2: comparison context/budget and curve/cost condition references |
| S15 | Phase 2: semantic allowlists and exact condition selectors |
| S16 | Phase 2: safe metadata/config/provenance projection |
| S17 | Phases 2–3: bounded sanitized arguments/results/transcript/public trace |
| S18 | Phase 1: job-bound evidence and authoritative terminal tool trace |
| P01 | Phase 3: durable browser intent, retry, reload and resume recovery |
| P02 | Phase 3: explicit capability reconnect and provider-error distinction |
| P03 | Phase 3: enforceable preflight budgets and strict complete canaries |
| P04 | Phase 3: sanitized typed provider errors/response validation |
| P05 | Phase 4: normal full collection, current head and installed package |
| P06 | Phase 4: report-derived source-bound evidence, no credentials printed |
| P07 | Phase 3: isolated scripted injection and truthful provider label |

Use the existing Python/Node/service setup. Do not install another database/runtime or change global Git settings. Process-only UTF-8 and one-thread numeric library settings remain required. Reuse the existing PostgreSQL 16 service through `../.tools/use-existing-test-postgres.ps1`; do not print its URL. Use isolated SQLite files, unique PostgreSQL schemas and fresh browser attempts.

Run in dependency order: focused negative regressions → complete agent tests on both backends → affected legacy API/continuation/queue/migration tests → typecheck/build → all Gate 5 and new real agent browser cases → static boundaries → one normal complete backend suite → installed-wheel smoke → source/contract evidence validation. Collect actual tests before quoting counts. The only current `live` marker is the existing PostgreSQL service check; run required database cases explicitly when excluding live-provider tests.

Do not repeat stable passing tests without a change/failure reason. If a focused regression fails, fix the shared cause and rerun its affected set before broad verification. Scientific code/configs are protected; no automatic Gate 2/Gate 3 reproduction is required for untouched agent/UI source. A demonstrated change to scientific identity/persistence/publication requires its affected reproduction and parent review.

Freeze the final candidate. Return one handoff containing every finding ID with exact test nodes, actual counts/skips/warnings, source digest and all remaining prerequisites. GPT-6.1 Sol returns PASS or every remaining material blocker together, scoped to this correction delta and affected contracts. Antigravity does not commit, push, deploy or mark acceptance. Parent owns final binding/source commit/separate governance checkpoint.

**Gate 6 stays pending:** offline corrections first; A7 remains BLOCKED_REQUIRED_LIVE_EVIDENCE until the user supplies exact-model access and an explicit allowed live usage ceiling. No additional user information is required to implement this correction batch.
