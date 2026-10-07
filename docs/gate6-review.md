# Gate 6 consolidated independent review — BLOCKERS

Reviewed 30 September 2026. **25 material blockers: 18 application findings (G6-S01–S18) and seven parent findings (G6-P01–P07). Gate 6 remains pending. Do not proceed to live acceptance or Gate 7.**

Owner: GPT-6.1 Sol Extra High independent application review, with parent evidence/integration checks. Antigravity remains the sole application writer. The complete packet consists of this parent integration report and [Sol's application findings](gate6-sol-review.md); [the correction batch](gate6-corrections.md) is the execution instruction.

## Frozen source and evidence

- Working HEAD: `83037b0f02eef62203c3f565a063d824af2722d7`; accepted Gate 5 source: `f63116fedc2751493d79d44897ba913b6d28b0b5`.
- Reviewed offline attempt: `../verification/gate6/offline-f72afeff-0cad-438f-bccb-157a39b08ef1/`.
- Its 40-file digest independently recomputes to `4d392741d38da64eb480f5f04bc97a3221649ee9a7ef7b4e8ec13be4fcc9e1d8`. All 40 raw hashes still match after the parent build.
- Protected comparison covers 75 baseline tracked backend/config/migration files: zero changes. `shiftguard/api/main.py` and `shiftguard/settings.py` are expected modifications and are separately recorded. This is this review's explicit scope, not a claim to have regenerated the previous Gate 5 79-file packet.
- `scripts/execute_gate6_offline_suite.py` is omitted from the author's manifest. The manifest also lacks the promised protected comparison; the parent supplied it independently.
- Parent evidence: `../verification/gate6/independent-review-20260930/parent/`; application reviewer evidence: its sibling `sol/`.

The author's actual reports contain **34 agent tests, 12 browser tests and 5 static tests passing**, with no failures/skips in those reports. These counts are real. They do not prove the missing crash, ownership, grounding and browser recovery contracts. Author evidence and independent evidence retain separate labels.

## Parent findings

### G6-P01 — P1: lost-response retry creates a second job; reload loses waiting work

Owners: `frontend/src/hooks/useAgent.ts:16`, `:59`, `:113`; agent browser API and workspace persistence.

`submitQuery` creates a fresh key for every button press. Agent state exists only in React state; no pending intent, accepted request ID, job link or continuation nonce is saved. A real HTTP probe accepted a request/job, then dropped its response. Clicking Submit again produced two different keys, request IDs and queued jobs. Reloading a WAITING_FOR_JOB request produced zero active cards and no persisted request identity. Poll/resume transport errors also stop the timer without a bounded recovery path.

Evidence: parent `browser-probes-revised.json`, sections `lost_submit_response` and `waiting_reload`. The API, authentication, SQLite and queue were real; the provider was explicitly scripted and the worker was disabled because these probes concern admission and identity.

Fix: persist a bounded session-bound intent before sending; retain key/body/request/job/nonce across response loss, reconnect and reload; provide Retry for ambiguous acceptance. New deliberate intent receives a new UUID. Rehydrate and GET the existing request under its original valid session, then continue polling/resume. Preserve Gate 5 caches and never transfer private work to a replacement session.

### G6-P02 — P1: agent auth recovery automatically replaces a rejected session

Owners: `frontend/src/App.tsx:61`, `frontend/src/hooks/useAgent.ts:88`, `:124`.

The callback invokes `workbench.reconnect()` immediately on any agent 401. With a genuinely expired session in the isolated database, submitting a query caused session creation count to rise from one to two without a user action; the Reconnect button was absent. An upstream provider-auth 401 must also remain distinct from browser capability rejection.

Evidence: parent `browser-probes-revised.json`, `auth_rejection`. The first simulated auth probe did not expire backend authority and is retained separately; the revised probe did.

Fix: classify the recognized capability rejection codes, mark agent submission unavailable and expose explicit Reconnect. Retain ambiguous accepted intent and old session association until the user chooses recovery. Business 403, provider failures and transport failures do not rotate credentials. Reconnect must invalidate old private request resumability while preserving published cache.

### G6-P03 — P1: preflight limits and overall canary verdict are unenforced

Owner: `scripts/preflight_nebius.py:21`, `:70`, `:111`, `:146`.

`max_tokens` is never consulted. The second request has no output cap. A fake transport supplied 10,000 total tokens under an allowance of one and the script returned success. A failed tool canary still yields `LIVE_CANARIES_PASSED` and exit zero. A single logical call with the SDK's configured retry sent two wire requests under a one-call allowance. Chat content, exact returned model, arguments/call ID and structured explanation capability are not completely validated.

Evidence: parent `provider-expanded-probes-junit.xml`, the three preflight probes. All requests used in-process fakes/MockTransport; **no external inference occurred**.

Fix: validate explicit positive allowances and requested exact model before client creation; define and enforce logical/wire/output/total-token accounting with finite input bounds, no hidden SDK retries, and unknown usage treated as unknown. Conservatively budget input plus maximum output before each wire attempt and stop when remaining allowance cannot cover it. Require each canary to pass, fail closed on malformed/mismatched output and incomplete coverage, verify original call IDs and typed arguments, add the structured-plan/fallback canary, record actual accounting and sanitized evidence. No live run is authorized by this review.

### G6-P04 — P1: provider error handling leaks credentials and misses malformed responses

Owner: `shiftguard/agent/provider.py:20`, `:165`, `:173`.

The regex redactor misses a configured key embedded after an arbitrary word; the unexpected-error branch copies that string into public `ProviderError.message` and logs it. The independent test used a dummy key, which remained visible. Empty `choices` raises an uncaught `IndexError` after the exception handler. Provider outputs have no explicit size/output-token limit and settings do not validate the newly introduced retry/timeout bounds.

Evidence: parent `provider-expanded-probes-junit.xml`, `test_unexpected_provider_error_can_expose_configured_key` and `test_provider_empty_choices_escapes_typed_failure`.

Fix: use fixed public error messages, explicitly remove known configured secrets from diagnostic strings, and avoid echoing arbitrary upstream bodies. Wrap response parsing and shape/size validation in the typed failure boundary. Test actual adapter exceptions with MockTransport for timeout/429/auth/model/5xx/invalid shapes, async close and output bounds. Failures must preserve manual controls and previously cached results.

### G6-P05 — P1: the required full-suite command cannot collect the new tests

Owners: new `tests/agent/test_api.py`, `test_continuation.py`, `test_migrations.py`; `pyproject.toml` and migration assertions as appropriate.

The required full suite stops with three import-file-mismatch errors because these basenames already exist under integration tests. Parent preserved the normal command's exit **2**, three collection errors and one deselected test. This is not a stale-cache diagnosis: both sets of source files are present and the default import mode collides. A separate diagnostic importlib run is recorded below; it does not make the normal command pass.

Evidence: parent `full.log` and `full-junit.xml`. Old migration tests must be reconciled to the new current head without dropping historical upgrade/data-preservation checks.

Fix: use unique module basenames or an intentionally configured/import-tested package collection mode; run the ordinary documented command again. The separate diagnostic suite completed with **372 passed, one failed, zero skipped and two warnings** in 572.42 s. Its failure is `tests/unit/test_migrations_isolation.py::test_upgrade_database_from_isolated_working_directory`: the test expects 0008 while the candidate correctly upgrades to 0009. Update current-head assertions without weakening historical upgrade/data-preservation checks, add upgrade-from-0008 coverage, and verify installed-wheel resources outside checkout. Never skip required cases to obtain a green report.

### G6-P06 — P1: the evidence generator writes PASS independently of test outcomes

Owner: `scripts/execute_gate6_offline_suite.py:18`, `:81`, `:172`, `:298` onward.

Contract statuses A1–A6 are hardcoded PASS. A controlled probe forced every one of the six commands to fail: `main()` returned 6, while its contract file still marked every offline row PASS. The script hardcodes base provenance, omits itself from the source map, lacks the protected comparison and prints a credential-bearing PostgreSQL URL prefix. Its A8 text still assigns Astra despite the current GPT-6.1 Sol workflow.

Evidence: parent `provider-expanded-probes-junit.xml`, `test_offline_evidence_marks_contracts_pass_when_every_command_fails`; `source-and-report-audit.json`.

Fix: derive verdicts from complete collected reports and actual required node results, require both backend cases, preserve FAIL/BLOCKED/NOT_RUN distinctions, detect missing/stale artifacts, bind command inputs to the actual before/after source inventory and HEAD, include scripts/generated/deleted/protected paths, and sanitize credentials completely. Point A8 to GPT-6.1 Sol, retaining previous packets as historical evidence. Add negative evidence-generator tests.

### G6-P07 — P2: scripted provider bypasses the disabled runtime and is labeled live

Owners: `shiftguard/api/main.py:36`, `shiftguard/api/routes/agent_requests.py:75`, `frontend/src/components/AgentPanel.tsx:39`, `frontend/playwright.config.ts:66`.

Setting the unguarded `SHIFTGUARD_AGENT_PROVIDER_MODE=scripted` replaces the lifespan provider even with `agent_enabled=False`. The real status endpoint reports enabled/available and the UI says Nemotron is active. This construction is not restricted to a test app or forbidden in hosted mode. It cannot serve as live-provider evidence.

Evidence: parent `browser-probes-revised.json`, `scripted_startup`; the independent browser was deliberately started in this mode.

Fix: inject scripted providers through a clearly isolated test construction/harness, reject them in ordinary hosted startup, expose explicit provider kind and label scripted evidence accurately. The production enable/disable switch remains authoritative. Ensure ordinary disabled startup makes no provider calls and leaves manual controls intact.

## Verification ledger

| Evidence | Result and limit |
| --- | --- |
| Author reports | 34 agent / 12 browser / 5 static passed, source-bound author evidence |
| Parent typecheck/build | Exit 0 / 0; four regenerated static hashes still match |
| Parent provider/preflight/evidence probes | 6 passed assertions reproducing the defects above; no inference |
| Parent browser/HTTP probes | Three material failures reproduced: duplicate accepted jobs, lost reload identity, implicit session replacement |
| Normal parent full suite | Exit 2; three collection errors; no full regression PASS |
| Diagnostic importlib full suite | Exit 1; 372 passed, one failed, zero skipped, two warnings; separate command, not a substitute for fixing normal collection |
| Sol application probes | 58 passed assertions: 52 defect reproductions and six controls on SQLite/PostgreSQL; 27 existing targeted tests passed, two PostgreSQL nodes deselected in that targeted command |
| Source/protection | 40/40 manifest hashes match; 75 protected tracked files unchanged; expected main/settings modifications identified |
| Live provider evidence | NOT_RUN; A7 remains BLOCKED_REQUIRED_LIVE_EVIDENCE |
| Gate 6 acceptance | PENDING; independent verdict BLOCKERS; no source/governance commit created |

## Next action

Antigravity executes [AG-G6-CORRECTIONS-01](gate6-corrections.md) as one integrated correction batch, resolving this complete parent list and the complete Sol application list. No further phase is opened. Freeze one corrected source map and evidence packet; GPT-6.1 Sol re-reviews only the delta and affected invariants. Parent retains source-commit/checkpoint ownership. Preserve accepted Gate 5 and every original failed report.
