# Gate 6 independent Sol review — frozen offline candidate

**Verdict: BLOCKERS — 18 material findings. Gate 6 is not accepted; G6-A7 remains BLOCKED_REQUIRED_LIVE_EVIDENCE.**

Reviewed 30 September 2026. Antigravity owns application implementation/corrections; GPT-6.1 Sol owns this independent review. Read AGENTS.md, docs/gate6-execution-plan.md, docs/gate6-batch.md and docs/gate6-implementation.md. Used the existing local SHIFTGUARD candidate-evidence and review-handoff skills within the narrower user-authorized scope; parent retains full-suite/source acceptance duties.

| Binding | Observed value |
| --- | --- |
| Base HEAD | `83037b0f02eef62203c3f565a063d824af2722d7` |
| Accepted Gate 5 source | `f63116fedc2751493d79d44897ba913b6d28b0b5` |
| Candidate | Dirty frozen working tree, author attempt `offline-f72afeff-0cad-438f-bccb-157a39b08ef1` |
| Independent assigned-scope digest | `a478ab07c6b09aaa59b464663be24192df3b6feb6cc4e6cad755760b5bcde093` |
| Frozen assigned files | 21 source/test files; before/after SHA-256 maps identical |
| Author full source-manifest/raw evidence audit | Parent-owned; no acceptance inferred from author report |

Scope: controller/store/registry/schemas/policy/tools/rendering, authenticated agent_requests handlers, migration 0009, and their assigned agent tests. Provider interface was followed solely to construct scripted responses. Existing queue/repository/worker/config interfaces were read only as dependencies required to test the agent contract. No unrelated Gate 4/science audit or scientific execution was performed.

Wrote only this new report and external evidence under `../verification/gate6/independent-review-20260930/sol/`. No application/governance edits, historical-review changes, commits, browser, builds, full suite, installations or live/provider network requests. Parent-owned UI/provider/preflight/harness/collection/source-evidence findings are deliberately not duplicated here.

## Executed verification

- Existing assigned tests: **27 passed, 2 PostgreSQL tests deselected, 2 deprecation warnings**, exit 0, 3.90 s. Included test_api/test_continuation/test_grounding/test_migrations/test_request_persistence/test_tool_loop/test_tool_registry; excluded test_provider and shared-public-schema PostgreSQL nodes.
- Initial independent probe run: **44 passed**, exit 0, 11.45 s, retained as preliminary evidence.
- Expanded independent probe run: **58 passed, 0 failed, 0 skipped, 2 deprecation warnings**, exit 0, 18.23 s. This is **52 passing assertions that reproduce defects plus 6 passing safety controls**, not a product PASS. Every case ran on both SQLite and actual PostgreSQL 16.
- Controls independently verify authenticated 401/foreign-session 403, same-intent identity/changed-body 409, strict Boolean and extra-key rejection, twelve names, six provider turns/eight rejected calls charged, fresh 0009 schema and isolated 0008→0009 session preservation.
- PostgreSQL used the existing helper/service and unique per-case `sol_g6_<uuid>` schemas, removed only those schemas on teardown. SQLite files and isolated pytest basetemps are beneath this evidence directory. Thread limits and UTF-8 were set. The initial sandbox helper could not access the service; authorized escalation verified it and ran the probes without exposing credentials.

Reproduce from the application root using the same local Python and existing database helper:

```powershell
& '..\verification\gate6\independent-review-20260930\sol\run_probes.ps1' -EvidenceTag ('rerun-' + [guid]::NewGuid().ToString('N'))
```

The script executes `python -B -m pytest <external test_sol_probes.py> -q -p no:cacheprovider --basetemp <unique external directory> --junitxml <external report> --tb=short`. It creates only external files and isolated test database fixtures. Avoid reusing an evidence tag to preserve prior runs.

[Probe code](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/test_sol_probes.py>), [expanded log](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes.log>), [JUnit](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes-junit.xml>), [structured packet](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/review-summary.json>), [before source map](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/scope-before.json>), [after source map](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/scope-after.json>).

## Consolidated blockers

### G6-S01 [P1] Accepted tool intents cannot recover across the enqueue boundary

**Source:** [shiftguard/agent/controller.py:163-202](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:163>); [shiftguard/agent/controller.py:240-270](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:240>); [shiftguard/agent/store.py:350-390](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:350>).

**Impact:** An acknowledged durable job can become an orphan; restarting does not replay the accepted operation with its original provider ID, ordinal and queue key. A crash before enqueue also loses the accepted decision.

**Independent repro:** Inject BaseException immediately before dispatch, and separately after the real JobQueue.enqueue commits but before the tool result/link commits. Both backends retain ordinal 1 PENDING, call_count=0, no active job, and only system/user messages. After lease expiry, a fresh controller requests another model decision and fails on the existing ordinal uniqueness constraint. After-enqueue retains one unlinked job; before-enqueue retains zero jobs. A separate crash at the next provider turn leaves two executed records but durable call_count=0.

**Evidence:** [crash-before_enqueue: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/crash-before_enqueue-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/crash-before_enqueue-postgres.json>); [crash-after_enqueue: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/crash-after_enqueue-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/crash-after_enqueue-postgres.json>); [durable-calls: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/durable-calls-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/durable-calls-postgres.json>).

**Concrete fix:** Atomically reserve/checkpoint proposed calls, provider response, remaining serial work, counters and normalized repair state under the request generation before dispatch. Recovery must process the persisted PENDING intent using its saved key, retrieve the winning queue job and commit the link/result. Use insert-or-read replay for the same ordinal; never regenerate an accepted provider decision. Add all three crash-boundary regressions.

### G6-S02 [P1] Repair limits reset at continuation and never stop repeated invalid dispatch

**Source:** [shiftguard/agent/controller.py:100-101](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:100>); [shiftguard/agent/controller.py:212-232](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:212>); [shiftguard/agent/policy.py:106-109](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/policy.py:106>).

**Impact:** One invalid signature receives fresh repair permission after each job pause/restart, and exceeding a signature budget merely changes the error text after the handler has already been dispatched.

**Independent repro:** Issue one invalid inspect_dataset signature, enqueue a baseline, complete it, then repeat the identical invalid arguments with changed provider IDs. Both backends finish with repair_count=2 for one signature. Four invalid dispatches execute; dispatch continues after REPAIR_BUDGET_EXCEEDED. Existing tests only assert that one returned string contains that code.

**Evidence:** [repair-resume: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/repair-resume-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/repair-resume-postgres.json>).

**Concrete fix:** Persist a per-signature ledger rather than an aggregate-only repair_count. Normalize structured validation/error codes and field locations, independent of changing call IDs or input text. Permit the initial failure and exactly one corrective attempt; gate subsequent proposals before handler execution, charge the durable call budget, and terminate or use deterministic unavailable/fallback behavior.

### G6-S03 [P1] Expired/stale request owners can enqueue and mutate the audit

**Source:** [shiftguard/agent/controller.py:108-118](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:108>); [shiftguard/agent/controller.py:193-218](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:193>); [shiftguard/agent/store.py:337-348](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:337>); [shiftguard/agent/store.py:407-439](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:407>).

**Impact:** A losing controller can create scientific work after another generation has completed the request. Its tool writes are not fenced; failed request CAS operations are ignored.

**Independent repro:** During the scripted provider await, expire the old lease, claim a new generation, and complete the request as new_owner. Returning a run_experiment call to the old owner still inserts one tool execution and one durable job, while the request remains COMPLETED with no active job link. Separately an expired lease with no takeover can successfully publish COMPLETED using the old generation. Both SQLite and PostgreSQL reproduce this.

**Evidence:** [stale-owner: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/stale-owner-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/stale-owner-postgres.json>); [expired-publish: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/expired-publish-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/expired-publish-postgres.json>).

**Concrete fix:** Require matching generation, lease owner, unexpired lease and legal status for every request/tool/receipt mutation and admission. Check each CAS return and stop immediately on ownership loss. Renew finite leases during legitimate long operations. Couple durable intent admission to the current generation so takeover cannot race an unfenced enqueue.

### G6-S04 [P1] WAITING_FOR_JOB retains an execution lease that blocks the next HTTP resume

**Source:** [shiftguard/agent/controller.py:258-275](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:258>); [shiftguard/agent/controller.py:323-330](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:323>); [shiftguard/api/routes/agent_requests.py:144-148](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/api/routes/agent_requests.py:144>); [shiftguard/api/routes/agent_requests.py:238-239](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/api/routes/agent_requests.py:238>).

**Impact:** Normal independent HTTP workers cannot promptly continue a completed background job. A no-progress reply is also saved as the nonce receipt.

**Independent repro:** Submit through the real authenticated handlers, mark its durable job completed, and immediately resume with the returned nonce. Submit returns 202; resume returns HTTP 200 but still WAITING_FOR_JOB, with only one scripted provider turn. This happens on both backends because every route invocation generates a new worker ID while the old 60-second lease remains held.

**Evidence:** [waiting-lease: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/waiting-lease-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/waiting-lease-postgres.json>).

**Concrete fix:** Release ownership atomically when pausing or finishing, retaining generation fencing; atomically reclaim when the job is ready. Ownership contention should return explicit in-progress/202 semantics and must not consume/store a final replay receipt for an operation it did not perform. Test route-to-route resume using distinct workers.

### G6-S05 [P1] A side-effect pause corrupts a multi-call provider exchange

**Source:** [shiftguard/agent/controller.py:163-176](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:163>); [shiftguard/agent/controller.py:249-272](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:249>); [shiftguard/agent/controller.py:377-389](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:377>).

**Impact:** Remaining approved calls are silently dropped and a completed job adds a second result for the same provider tool-call ID. The next provider input has unanswered calls and duplicate replies.

**Independent repro:** One response proposes run_a followed by read_b. After completing the job and resuming, the next scripted provider receives result IDs [run_a, run_a]; read_b has no result and only one tool execution exists. Both backends reproduce. Actual provider rejection is not claimed or tested.

**Evidence:** [transcript: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/transcript-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/transcript-postgres.json>).

**Concrete fix:** Persist the remaining ordered calls before the pause; resume that list before requesting another provider turn. Defer the single tool response for a run until its outcome is ready, or implement a protocol-valid interim/completion exchange. Preserve the original name/ID, including run_stress_suite; resolve every proposed ID, including budget rejection, exactly once.

### G6-S06 [P1] Concurrent request intents and continuation receipts do not replay atomically

**Source:** [shiftguard/agent/store.py:162-202](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:162>); [shiftguard/agent/store.py:453-482](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/store.py:453>); [shiftguard/agent/controller.py:318-335](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:318>).

**Impact:** Response-loss retries or concurrent tabs can raise an unhandled database IntegrityError instead of returning the winning durable identity/receipt.

**Independent repro:** Synchronize two identical intent submissions after their SELECTs: one creates the request, one raises IntegrityError on the session/intent constraint. Synchronize two identical nonce resumes after both receipt reads: outcomes are HTTP-equivalent 200 and IntegrityError. Each race reproduces on SQLite and PostgreSQL.

**Evidence:** [concurrent-intent: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/concurrent-intent-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/concurrent-intent-postgres.json>); [concurrent-receipt: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/concurrent-receipt-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/concurrent-receipt-postgres.json>).

**Concrete fix:** Use atomic insert-or-read under the existing unique constraints. On a conflicting intent, re-read and verify the canonical body hash before returning the winner or 409. Serialize continuation ownership and insert-or-replay receipts in the same fenced state transaction. Never allow a duplicate nonce to become a raw exception.

### G6-S07 [P1] The HTTP resume endpoint discards the stored replay payload

**Source:** [shiftguard/api/routes/agent_requests.py:57](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/api/routes/agent_requests.py:57>); [shiftguard/api/routes/agent_requests.py:239-248](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/api/routes/agent_requests.py:239>); [shiftguard/agent/controller.py:347-356](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:347>).

**Impact:** A lost-response replay is not the original response: the old status code is paired with fresh state and fresh nonce. The advertised single-use nonce is not validated against issued request state.

**Independent repro:** Save a 202 WAITING receipt, finish the request using another nonce, then replay the old nonce through the authenticated API. Both backends return 202 with body status COMPLETED rather than the recorded WAITING body. An arbitrary not_server_issued nonce is also accepted. Lease expiry is controlled in the fixture to isolate this from G6-S04.

**Evidence:** [http-receipts: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/http-receipts-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/http-receipts-postgres.json>).

**Concrete fix:** Persist a request/generation-bound nonce and the complete public response envelope once. Replay the recorded status and exact payload, including nonce and trace, without rebuilding _format_request_response. Validate nonce ownership/consumption; define whether an active-job poll consumes it, and keep that policy replay-safe.

### G6-S08 [P1] Session authority is not checked at tool admission after the provider await

**Source:** [shiftguard/api/routes/agent_requests.py:102-104](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/api/routes/agent_requests.py:102>); [shiftguard/agent/controller.py:204-218](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:204>); [shiftguard/agent/registry.py:264-272](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/registry.py:264>); [shiftguard/agent/tools/runs.py:30-38](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/runs.py:30>).

**Impact:** A request authenticated before waiting can enqueue work after its capability session has become expired. Registry dispatch has no independent session/request admission policy.

**Independent repro:** Authenticate a real session through the agent submit route; during the scripted provider call, change that session to expired; then return run_experiment. Both backends return 202 and create one durable job for the expired session.

**Evidence:** [dispatch-authority: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/dispatch-authority-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/dispatch-authority-postgres.json>).

**Concrete fix:** Build an authenticated server-owned tool context and revalidate current session/request authority at dispatch and side-effect admission, independently of model arguments. Couple side-effect admission to the authority check under a transaction/lock so expiry cannot race it. Keep metadata/results admission rules explicit.

### G6-S09 [P1] A model-selected experiment ID becomes request evidence without authorization

**Source:** [shiftguard/agent/controller.py:234-238](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:234>); [shiftguard/agent/tools/results.py:60-73](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:60>); [shiftguard/agent/rendering.py:35-36](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:35>); [shiftguard/agent/rendering.py:148-169](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:148>).

**Impact:** Publication existence is treated as user/request evidence authority. The model can choose a valid-looking unrelated ID and cause it to be rendered as an authorized analytical fact.

**Independent repro:** Start with empty evidence and prompt Inspect dataset metadata only. A scripted response chooses a different published synthetic experiment and reads its condition. Both backends complete, append that ID to evidence_refs, and render its 0.2 Brier value. The user never selected the ID and this request did not produce it. This is an evidence-authority defect, not a claim that published public results are private.

**Evidence:** [model-reference: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/model-reference-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/model-reference-postgres.json>).

**Concrete fix:** Maintain a bounded server-owned allowed-reference set from validated user selections and jobs attached to this request. Reject or return typed unavailable for model-supplied IDs outside that set before repository/claim resolution. Derive allowed evidence from durable job/request links, not from arbitrary successful tool data.

### G6-S10 [P1] Unchecked empirical prose and nonexistent evidence return successful answers

**Source:** [shiftguard/agent/controller.py:136-160](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:136>); [shiftguard/agent/rendering.py:156-157](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:156>); [shiftguard/agent/rendering.py:174-184](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:174>).

**Impact:** The API returns fabricated empirical numbers, recovery and significance assertions as provider_narrative, even with no valid evidence; no explanation validation or bounded repair occurs.

**Independent repro:** Read a nonexistent experiment, then return Brier score is 0.0000, all 8238 rows recovered; statistically significant improvement. Both backends report COMPLETED with zero claims/references and preserve that exact provider_narrative. The disclaimer does not validate or remove the contradictory prose.

**Evidence:** [unchecked-grounding: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/unchecked-grounding-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/unchecked-grounding-postgres.json>).

**Concrete fix:** Accept only a strict explanation plan using allowlisted template and metric/reference paths; resolve all numbers and directions in Python against authorized persisted records. Never return unchecked provider prose. Perform one bounded explanation repair within the durable turn budget, then deterministic valid-evidence fallback or explicit unavailable output.

### G6-S11 [P1] Typed errors and null decision loss crash deterministic rendering

**Source:** [shiftguard/agent/rendering.py:30-38](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:30>); [shiftguard/agent/rendering.py:112-127](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:112>); [shiftguard/agent/tools/results.py:473-492](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:473>).

**Impact:** A valid unsupported-cost response or null persisted loss becomes a controller failure, losing the required unavailable/null distinction and bypassing the deterministic fallback path.

**Independent repro:** Unsupported (2.5,7.5) returns a typed tool error; the next final response makes rendering format None as a float and sets request FAILED with TypeError. Separately a persisted (1,4) row with loss=null returns tool success, omits condition_id, and raises TypeError in the renderer. Both backends reproduce.

**Evidence:** [decision-loss-error: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/decision-loss-error-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/decision-loss-error-postgres.json>); [null-cost-loss: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/null-cost-loss-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/null-cost-loss-postgres.json>).

**Concrete fix:** Branch on typed tool status before reading its data. Validate a typed result projection, preserve unavailable/null loss and condition binding, and format numeric facts only when finite values are present. Error/unavailable outcomes must render a safe explicit result rather than a fabricated claim or exception.

### G6-S12 [P1] Grounded summaries drop failed, fallback and comparison qualifications

**Source:** [shiftguard/agent/rendering.py:38-71](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:38>); [shiftguard/agent/rendering.py:96-110](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:96>); [shiftguard/agent/rendering.py:150-170](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/rendering.py:150>).

**Impact:** Rendered analysis hides adverse/null conditions and sparse fallback in multi-condition reads. The analytical summary states outage deltas without the stored qualification reason or matching limits.

**Independent repro:** Give the renderer a published-shape failed raw condition, a single-class target fallback affecting nine rows, and an unqualified outage comparison with outside_tolerance/residual_mismatch. On both test backends the failed condition has no visible claim, fallback_analysis is null, and the summary loses single_class, outside_tolerance and residual mismatch. A Boolean remains in the structured outage claim, but its reason and summary qualification are dropped.

**Evidence:** [lost-qualifications: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/lost-qualifications-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/lost-qualifications-postgres.json>).

**Concrete fix:** Use typed deterministic observations for null/failed/adverse outcomes. Preserve requested/resolved method, fallback reasons/chains and all eight sparse diagnostics for aggregate and selected-condition reads. Carry matching status, qualification reason/tolerance/residual mismatch and bound condition IDs into claims and their displayed narrative; do not truncate away required failures.

### G6-S13 [P1] The stress handler maps to a name that the existing worker treats as baseline

**Source:** [shiftguard/agent/tools/runs.py:89-98](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/runs.py:89>); [shiftguard/agent/policy.py:24-33](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/policy.py:24>); [shiftguard/agent/schemas.py:62-67](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/schemas.py:62>).

**Impact:** An approved natural-language stress request queues a different scientific run type. It cannot supply the promised stress comparisons and budget curves.

**Independent repro:** Dispatch flagship-stress through the real registry and queue: success enqueues preset_name=bank-stress-30 on both backends. That preset/config does not exist. Following the existing worker interface establishes that only bank-stress selects StressConfig (worker.py:136); bank-stress-30 falls through to BaselineConfig (worker.py:148-153). No worker/scientific run was executed in this review.

**Evidence:** [stress-preset: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/stress-preset-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/stress-preset-postgres.json>).

**Concrete fix:** Map declared stress aliases to the existing bank-stress preset and import/reuse the canonical preset allowlist. Reject unsupported names before enqueue. Keep the result/tool definition accurate about the selected run type and multiple conditions. Add a dispatch-to-worker-contract regression without altering scientific owners.

### G6-S14 [P1] Comparison handlers disregard evidence compatibility and requested budget

**Source:** [shiftguard/agent/tools/results.py:213-237](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:213>); [shiftguard/agent/tools/results.py:268-315](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:268>); [shiftguard/agent/tools/results.py:370-393](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:370>); [shiftguard/agent/tools/results.py:473-491](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:473>).

**Impact:** Different datasets, evaluation rows and masks can become an improved calibrator claim. A budget-25 outage request can receive a budget-50 comparison. Curve/cost projections drop condition references required to ground each observation.

**Independent repro:** Publish synthetic same-name raw/target conditions with different dataset/evaluation-row/mask identities and scores 0.4/0.1. Both backends return success and the renderer labels target improved. Request outage budget 25 with a stored budget-50 row: success returns 50. The cost projection also omits a stored condition_id; code inspection confirms the curve projection omits each point condition_id.

**Evidence:** [comparison-context: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/comparison-context-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/comparison-context-postgres.json>); [null-cost-loss: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/null-cost-loss-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/null-cost-loss-postgres.json>).

**Concrete fix:** Bind each returned fact to exact condition IDs and validate matching dataset/predictor/evaluation context plus the declared mask-comparison policy. Honor requested budgets or return typed unavailable. Retain availability/fallback/qualification and curve/cost condition refs; derive comparative directions only from compatible persisted pairs.

### G6-S15 [P2] Strict tool names/types do not provide strict semantic handlers

**Source:** [shiftguard/agent/tools/metadata.py:77-88](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/metadata.py:77>); [shiftguard/agent/tools/metadata.py:102-109](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/metadata.py:102>); [shiftguard/agent/tools/results.py:75-88](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:75>); [shiftguard/agent/tools/results.py:325-342](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:325>); [shiftguard/agent/tools/results.py:500-569](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:500>); [shiftguard/agent/schemas.py:70-111](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/schemas.py:70>).

**Impact:** Unsupported scenario/method/focus selectors can be represented as valid operations; a nonexistent condition alias silently resolves to a different persisted condition.

**Independent repro:** Both backends report temporal_lead_0_50 as a successful approved scenario affecting duration/campaign, although those features/scenario are outside the accepted modeled/executable contract. An arbitrary_method curve and arbitrary_focus summary succeed when corresponding synthetic data exists. condition_key=raw succeeds by selecting the first longer condition containing raw. The real preset supports MCAR 0/0.10/0.30; the metadata advertises MCAR 0.20 as executable.

**Evidence:** [semantic-metadata: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/semantic-metadata-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/semantic-metadata-postgres.json>); [semantic-policy: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/semantic-policy-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/semantic-policy-postgres.json>).

**Concrete fix:** Derive executable scenarios, predictors, methods, budgets and presets from existing approved configuration. Validate method/focus/scenario/budget semantics before handlers. Require an exact condition key or a documented unambiguous typed selector; never first-match substring coercion. Return typed unavailable for unsupported operations without expanding scientific policy.

### G6-S16 [P1] Unprojected persisted configuration sends server paths to the model

**Source:** [shiftguard/agent/tools/results.py:167-178](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/tools/results.py:167>); [shiftguard/agent/controller.py:249-255](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:249>); [shiftguard/agent/schemas.py:118-125](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/schemas.py:118>).

**Impact:** Model-visible/public tool data is not restricted to approved aggregate metadata. Actual persisted config includes filesystem locations, which the handler forwards verbatim.

**Independent repro:** Publish a synthetic config containing C:/private/server/bank.csv. get_experiment_metadata returns that path, and the next scripted provider history contains it in the tool result on both backends. No real secret/path was read or printed; the fixture proves the projection behavior.

**Evidence:** [provider-path-projection: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/provider-path-projection-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/provider-path-projection-postgres.json>); [semantic-metadata: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/semantic-metadata-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/semantic-metadata-postgres.json>).

**Concrete fix:** Define per-tool strict result schemas and explicitly project approved config/provenance fields, public IDs, hashes and aggregate diagnostics. Exclude dataset/artifact paths, private audit internals and arbitrary nested config. Validate the model-visible result before persistence/transport and public trace rendering.

### G6-S17 [P2] Rejected provider arguments are unbounded, persisted and echoed publicly

**Source:** [shiftguard/agent/schemas.py:18-34](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/schemas.py:18>); [shiftguard/agent/schemas.py:118-135](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/schemas.py:118>); [shiftguard/agent/controller.py:183-202](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:183>); [shiftguard/api/routes/agent_requests.py:33-46](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/api/routes/agent_requests.py:33>).

**Impact:** A malformed/unapproved proposed argument can consume unbounded transcript/database/response space and be returned in the supposedly safe trace. Provider IDs also have no schema bounds corresponding to migration column limits.

**Independent repro:** Propose inspect_dataset with an extra 200,000-character payload. Strict input validation rejects execution, but both backends retain the entire field in arguments_json and GET returns it in tool_trace; responses exceed 200 KB. The request still reports COMPLETED. No live malformed-provider probe was run.

**Evidence:** [unbounded-trace: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/unbounded-trace-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/unbounded-trace-postgres.json>).

**Concrete fix:** Enforce concrete limits on response text, call IDs/names, argument bytes, call-list size, transcript bytes and evidence collections before storing accepted state. Persist/project only safe validated arguments; rejected inputs should yield bounded sanitized error metadata. Align validated lengths with migration columns and bound typed outputs.

### G6-S18 [P1] Job completion does not update the authoritative trace or resolve job-bound evidence safely

**Source:** [shiftguard/agent/controller.py:362-389](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:362>); [shiftguard/agent/controller.py:414-445](<C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/shiftguard/agent/controller.py:414>).

**Impact:** A failed/cancelled job remains publicly recorded as successful queued work and can end with a successful narrative. A completed job lacking result_json uses an unrelated global publication lookup that currently crashes, instead of its durable experiment linkage.

**Independent repro:** After a real enqueue, mark the isolated job failed or cancelled and resume. Both backends return request COMPLETED/200; stored tool trace remains status=success and data.status=queued, while provider_narrative says All successful. Separately complete a job with an empty result and its experiment_id field set: if another publication exists, resume raises KeyError(0) because list_published returns dictionaries, not tuples; no receipt is written. Reading job.experiment_id is skipped.

**Evidence:** [job-failed: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/job-failed-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/job-failed-postgres.json>); [job-cancelled: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/job-cancelled-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/job-cancelled-postgres.json>); [completion-fallback: SQLite](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/completion-fallback-sqlite.json>), [PostgreSQL](<C:/Users/Abhinav Anand/Downloads/nvidia/verification/gate6/independent-review-20260930/sol/expanded-probes/completion-fallback-postgres.json>).

**Concrete fix:** Atomically finalize the original tool execution with typed completed/failed/cancelled outcome and replace its pending response in the ordered transcript. Resolve only the attached job.experiment_id and verified publication owned by that job; remove the global latest-publication fallback. Preserve failure/unavailability in deterministic output and receipt, even when a conversational controller reaches a terminal state.

## Contract status and next correction boundary

| Invariant | Independent result |
| --- | --- |
| G6-A1 strict twelve semantic handlers/admission | FAIL: S08, S13, S15–S17; name/type controls pass |
| G6-A2 durable bounds, repair, original IDs/serial exchange | FAIL: S01–S05; in-process six/eight controls pass |
| G6-A3 job identity, crash/replay, fencing, receipts | FAIL: S01, S03–S07, S18; sequential identity controls pass |
| G6-A4 authorized evidence, null/adverse/qualified grounded answers | FAIL: S09–S12, S14, S16, S18 |
| G6-A5 provider/preflight | Parent-owned; not independently audited here |
| G6-A6 browser/full regression/full source evidence | Parent-owned; local targeted SQLite/PostgreSQL probes above only |
| G6-A7 live exact-model proof | BLOCKED_REQUIRED_LIVE_EVIDENCE; no live call made |
| G6-A8 independent review/source acceptance | BLOCKERS; source/governance checkpoints and final parent packet pending |

Antigravity should correct this complete set together with the parent-owned findings in one application batch, then supply the correction diff and fresh evidence. Sol re-review should cover changed behavior and these affected invariants. This report does not authorize commits, live calls, deployment or Gate 6 acceptance.
