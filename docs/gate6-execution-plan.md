# Gate 6 execution plan — Antigravity implementation / GPT 6.1 Sol review

**Goal:** Add a natural-language run/read/compare workflow to the accepted browser product, using Nemotron for approved tool selection and Python for persisted results and grounded explanations.

**Architecture:** Same-origin React → authenticated FastAPI → bounded async controller → static typed tools → existing durable queue and published-result repository. Persist request/tool/continuation state before acknowledging side effects.

**Tech stack:** Existing Python 3.13, FastAPI, Pydantic, SQLAlchemy/Alembic, SQLite/PostgreSQL 16, React/TypeScript/Vite/Playwright; add a locked OpenAI Python SDK dependency for `AsyncOpenAI` against Nebius Token Factory.

**Baseline/authority:** [Gate 6 contract](gate6-batch.md), [blueprint v2](../../SHIFTGUARD_Implementation_Blueprint_v2_2026-09-09.md) sections 6–10 and overriding section 28A, [original execution plan](../../docs/aegis/plans/2026-09-10-shiftguard-hackathon-execution-plan.md) Gate 6, [loop engineering](loop-engineering.md), and [Gate 5 acceptance](gate5-acceptance.md). Current user assignment: Antigravity codes; GPT 6.1 Sol reviews.

**Compatibility:** Preserve Gate 5 presets/cache/auth/retry behavior, session capabilities, job quota/idempotency/fencing, publication visibility and scientific identities. No historical migration rewrites, confirmatory unsealing, deployment or unrelated cleanup.

**Verification:** One integrated offline candidate, deterministic provider tests, real local browser/worker continuation, actual SQLite/PostgreSQL persistence checks, all Gate 5 regressions and one GPT 6.1 Sol review. Full Gate 6 acceptance additionally requires account-authorized exact-model live evidence and parent source/checkpoint binding.

Prepared **29 September 2026**. **READY_NOT_STARTED.** Give Antigravity this entire file. Implementation phases below are internal steps in one large coding batch, not separate review gates.

## 1. Gate 5 is accepted; no repair batch is required

Gate 5 has no open material blockers within its acceptance contract. G5-R01 and G5-R02 are resolved. This does not assert that every conceivable behavior is defect-free.

| Baseline | Verified state |
| --- | --- |
| Application source | `f63116fedc2751493d79d44897ba913b6d28b0b5` |
| Separate governance checkpoint / starting HEAD | `83037b0f02eef62203c3f565a063d824af2722d7` |
| Reviewed source digest | `0e961a563ca38f02074b86a95c67fac8267b26f27182a8dab9a2f1256e28f492` |
| Parent checks | Typecheck/build PASS; 3 affected browser and 5 static cases passed |
| Astra checks | 8 independent probes passed |
| Author full browser suite | 9 passed, distinctly labeled author evidence |
| Planning-time integrity check | 36 application hashes, 79 protected backend hashes and recorded evidence hashes still match |

Required final checks had no failures/skips. Two existing static-test deprecation warnings were non-blocking. The planning turn inspected evidence and source integrity; it did not rerun these tests.

Repository: `C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard`; branch: `implementation/gate-0`. Retain the planning edits to this file, `gate6-batch.md` and `next-execution.md`. Inventory any other changes rather than resetting the checkout. Keep original Gate 5 BLOCKERS/PASS reports and external acceptance files as immutable history.

## 2. Owners, batches and completion rules

| Owner | Responsibility |
| --- | --- |
| Antigravity, user-configured model | Sole application writer; integrated implementation, ordinary debugging, all corrections and evidence handoff. No model setting is invented by this plan. |
| GPT 6.1 Sol | Independent consolidated review; return every reproducible material blocker in one packet. Re-review correction deltas and affected invariants. |
| Codex parent | Independently verify reports, bind reviewed bytes to source, own source commit and separate governance checkpoint, record acceptance. |
| User | Supply this packet to Antigravity; later provide local provider access and an explicit live usage allowance. |

**AG-G6-OFFLINE:** Complete phases A–D below as one integrated batch. Do not seek review after each file or delegate coding to Luna or Terra. Sol is the independent reviewer. No paid key is needed for this batch.

**AG-G6-LIVE:** Following bounded validation step using actual authorized provider access. Offline PASS is not Gate 6 acceptance. If live behavior requires fixes, implement one correction batch and reverify affected behavior.

Missing live access blocks only live evidence. Missing required database proof is recorded separately. Two correction rounds without verified progress trigger a GPT 6.1 Sol root-cause brief, not another broad audit or lowered criteria. Do not commit, push, deploy or mark acceptance from Antigravity.

## 3. File owners and architecture boundaries

Read existing owners before adding adapters:

| Owner | Reuse and boundary |
| --- | --- |
| `shiftguard/api/auth.py` | `verify_session_authority`; authority comes from authenticated context, never model arguments. |
| `shiftguard/api/routes/experiments.py` / `jobs/queue.py` | Current preset submission, session-scoped idempotency and two-active-job quota. Use `JobQueue.enqueue`; do not create another experiment queue. |
| `shiftguard/jobs/continuation.py` | Existing nonce/receipt and CAS behavior. Its current `resume()` completes a job-dependency session; it is not an LLM loop. Add request-scoped continuation without changing legacy session-resume semantics. |
| `shiftguard/storage/repositories.py` | `get_published` / `list_published`; PREPARED and quarantined records remain invisible. |
| `shiftguard/api/routes/metadata.py`, configs, manifests | Reuse approved IDs. Ground scientific facts in config/manifests/persisted evidence, not duplicated descriptive literals. Distinguish original dataset columns from the ten modeled features. |
| `frontend/src/api/client.ts`, `state/workspace.ts`, `hooks/useWorkbench.ts` | Existing headers, pending-intent identity, cache, reconnect and response-loss handling. Preserve these paths. |

Existence check: `shiftguard/agent/` and `scripts/preflight_nebius.py` are absent; `tests/agent/` contains no existing agent implementation tests. OpenAI SDK is not declared. Runtime code is necessary; existing session endpoints do not provide inference.

Create these cohesive owners:

- `shiftguard/agent/{__init__,schemas,policy,registry,provider,controller,prompts,store,rendering}.py`.
- `shiftguard/agent/tools/` grouped into metadata, run and result handlers; avoid twelve boilerplate wrapper files.
- `shiftguard/api/routes/agent_requests.py` and typed agent request/response schemas.
- Forward migration `shiftguard/alembic/versions/0009_gate6_agent_runtime.py`, after confirming current head remains 0008.
- `scripts/preflight_nebius.py`; focused `tests/agent/**`; `tests/e2e/test_agent_flow.spec.ts`.
- `frontend/src/api/agent.ts`, `hooks/useAgent.ts`, `components/AgentPanel.tsx`; narrow App/style/cache integration.

Modify only as required: settings, `.env.example`, `pyproject.toml`/`uv.lock`, API router/lifespan registration, continuation, test harness and migration packaging tests. Queue changes need a demonstrated missing primitive; prefer existing idempotent enqueue. Generate `shiftguard/static/**` from the final build.

Protected: scientific runners/evaluator/calibrators, frozen configs/manifests, feature selection, migrations 0001–0008, accepted artifacts, research and confirmatory data. Unsupported tool operations return a typed unavailable result; they do not authorize changes to scientific policy.

Complexity check: queue 727 lines, repository 627, continuation 362 and workbench hook 292 at planning time. Put new orchestration/storage in agent owners, keep routes thin, and extract continuation internals only if both existing and new paths actually share them. No duplicated transaction algorithm, generic framework or unrelated rewrite. Retain the accepted browser/worker; this is not a deletion batch.

## 4. Phase A — pin contracts, provider and tool registry

Record concrete interfaces, bounds and transitions in one `docs/gate6-implementation.md` handoff as implemented. Do not create a second parallel plan.

### A1. Request and policy contracts

1. Require existing server-issued session credentials for every agent submit/read/resume. Reject foreign request/job IDs. Never treat arbitrary client `initial_state` as trusted controller state.
2. Assign each user intent a client idempotency key, canonical body hash, server request ID and session binding. Same key/body returns the same request; changed body returns 409. New intentional message gets a new key.
3. Keep provider tool-call IDs separate from durable execution IDs. Bound user text, transcript size, output size and evidence-ID collections; choose concrete maximums in the schemas before implementing handlers.
4. Enforce **six provider turns**, **eight proposed tool calls**, and at most **one repair per invalid-call signature**, independent of changing call IDs. Rejected calls consume the tool budget. Final explanation repair consumes the same turn budget. Persist all counters through restart/resume.
5. Separate browser capability-session lifetime from one agent request. Completion of one question must not invalidate the browser session or prevent the next question.
6. Model-visible data is approved aggregates/references only: no raw rows, final labels, full predictions, secrets, session tokens or local filesystem paths. Public trace excludes raw provider internals and hidden reasoning.

### A2. Provider adapter

- Add the SDK through existing project-local uv; update the lockfile without upgrading scientific pins or installing global runtimes.
- Configure server-side enabled/disabled mode, secret API key, allowlisted base URL, exact model, timeout, retries and finite overall controller deadline. Application startup/manual presets must work with provider disabled.
- Blueprint model remains `nvidia/Nemotron-3_5-Lightning`; account availability is unverified. No automatic model substitution or optional Super fallback.
- Use lifespan-owned `AsyncOpenAI`, explicit close, initial blueprint settings `timeout=45` seconds and `max_retries=2`. Await network calls and never hold a DB transaction across them. Use one retry layer; no multiplier around SDK retries.
- Classify timeout, connection loss, 429, 5xx, provider auth, missing model and malformed output separately. Redact errors. Persist sanitized attempts/usage, never the API key.
- Inject a scripted provider for tests. Test mode must be isolated and explicitly labeled; no simulated success in the ordinary product when credentials are absent.

### A3. Twelve functional tools

Use strict Pydantic models (`strict=True`, `extra='forbid'`), generated schemas, explicit side-effect declarations, semantic policy and typed results. Registry set must exactly equal the following list.

| Tool | Concrete implementation / constraint |
| --- | --- |
| `inspect_dataset` | Read Bank feature/role/hash metadata from authoritative config, manifests or persisted evidence. Distinguish natural/injected missingness; unavailable facts stay unavailable. |
| `list_available_scenarios` | Return executable development scenarios/permitted parameters from existing approved config. No model-defined grids. |
| `inspect_missingness` | Exactly one scenario or experiment selector. Return persisted pool/acquired/test counts, rates and denominator meanings. An unexecuted scenario has requested parameters, not realized rates. |
| `run_experiment` | Compile a supported intent into an existing approved Bank preset, seed 31001. Reject unsupported combinations instead of coercing them. Disclose when the preset computes multiple conditions. Enqueue through current queue. |
| `run_stress_suite` | Map a declared Bank stress suite to the existing bounded preset. Distinguish job ID, experiment ID and suite reference; no arbitrary grids. |
| `compare_outages` | Read persisted paired comparisons and qualification. Require compatible dataset/predictor/evaluation context and the declared mask-comparison policy; no hidden enqueue. |
| `compare_calibrators` | Read matching condition metrics/comparison references; preserve failed/null/fallback and qualification. Never compare unrelated cases just because metric names match. |
| `get_label_budget_curve` | Read the saved curve and bound condition references; no hidden runs or scientific calculation in JS/model. |
| `calculate_decision_loss` | Return the exact persisted cost-grid row bound to the requested condition. Arbitrary costs require private predictions outside the accepted public contract: return `UNSUPPORTED_COST_PAIR`, not a derived estimate from aggregate metrics. Disclose this supported subset. |
| `read_experiment_results` | Typed projection of published metrics/diagnostics/artifact refs, including the eight sparse-bin fields accepted in G5-R01. |
| `get_experiment_metadata` | Persisted config/provenance; logical identity remains distinct from execution/audit UUIDs. |
| `generate_result_summary` | Deterministic Python summary over validated references, never authoritative free-form model prose. |

Use actual repository identifiers, e.g. `logistic_regression` and stored 24-character experiment IDs; blueprint example spellings do not replace them. Bank seed 31001 is executable; Adult/confirmatory/MAR extensions remain unavailable. Twelve registered placeholders do not satisfy this phase.

Validate JSON/name/schema/semantic authority before dispatch. Reject boolean/string numeric coercions, unknown keys, arbitrary URLs/paths/code/SQL and unsupported scientific parameters. Build tool context server-side. Read through storage/services, not loopback HTTP or direct calls to HTTP route functions. Serially execute multiple tool calls and preserve each original `tool_call_id` in tool-result messages.

## 5. Phase B — durable controller, continuation and grounded API

### B1. Durable ownership and recovery

- Add request/tool records and request-scoped replay receipts using a forward migration. Existing `agent_sessions` remains authority; do not create another token/account system.
- Persist request status/generation, counters, bounded accepted provider messages, tool intents/results, job links, evidence refs and final answer. Enforce uniqueness for `(session, intent)` and `(request, durable tool ordinal)`. Native Boolean values and SQLite/PostgreSQL compatibility are required.
- Add request-scoped operations to the existing continuation owner. Preserve legacy session-resume behavior and receipt replay; new request receipts cannot collide with old session receipts. Share CAS helpers where appropriate instead of cloning race-prone transaction code.
- Specify legal request transitions such as RUNNING → WAITING_FOR_JOB → READY_TO_RESUME → RUNNING/COMPLETED, plus explicit FAILED/CANCELLED outcomes. Browser session status is separate.
- Claim a request generation atomically so two HTTP requests cannot drive the same controller concurrently. Use finite ownership leases/generation checks; expired owners can recover, stale owners cannot publish results or advance counters.
- Persist the provider response and validated tool intent **before enqueue**. Derive a stable queue idempotency key from session/request/tool ordinal; never generate a fresh key during recovery.
- Call existing `JobQueue.enqueue`, then persist the winning job link before acknowledging waiting. This is a recoverable multi-transaction protocol: crash after enqueue/before link replays the stored intent with the same key and recovers the same job. Never regenerate a provider decision for an already accepted intent.
- Return waiting promptly. Ordinary application polling observes job status; the model does not spend tool calls polling. Once complete, read the published result, append the exact tool response and resume with remaining counters.
- Nonce/receipt replay after duplicate or lost resume response returns the recorded result without another provider continuation/job. Failed/cancelled jobs produce typed failures, preserving old published cache.
- Do not claim exactly-once provider billing across a transport/process crash. Guarantee local side-effect identity, distinguish provider attempts and avoid duplicate local jobs.

### B2. Grounding and HTTP integration

- Add authenticated `POST /api/v1/agent/requests`, `GET /api/v1/agent/requests/{request_id}` and `POST /api/v1/agent/requests/{request_id}/resume`. Require session headers, submit idempotency and typed resume nonce; keep all existing `/agent/sessions` routes compatible.
- Persist state before acknowledging it. Return 202 for waiting/in-progress and explicit terminal outcomes. Agent cancellation must use current job authority and must not cancel unrelated jobs from the same session.
- Build visible evidence from authorized request state and validated user-selected published IDs. A model-produced valid-looking ID is not authorization.
- Validate final plans against allowlisted metric/reference paths and template IDs. Python resolves every number and empirical direction. No arbitrary template code, attribute traversal, raw HTML or unchecked provider narrative.
- Invented metrics/IDs, unavailable values or unsupported empirical prose receive one bounded repair; then deterministic summary of valid evidence or explicit unavailable output.
- Preserve adverse/null results, fallback counts, cost pairs, comparison qualification and illustrative single-seed labeling. Observed deltas are not statistical significance or robust recovery without accepted repeated-run uncertainty evidence.
- Keep schemas, persistence, rendering and provider behavior in their designated owners. Routes should compose those owners, not contain another controller implementation.

## 6. Phase C — browser integration and regression preservation

1. Add AgentPanel beside manual presets: prompt, submit, running/waiting/terminal state, safe trace and actual result links. Clearly display provider disabled/unavailable; no fake live interface.
2. Reuse session headers and cache. Persist bounded request ID, intent/key, nonce, status and safe result references; never the provider key or raw transcript.
3. Lost-response retry/reload retains the original request identity. Explicit new message gets a new key. Never silently replay ambiguous accepted work under a replacement session.
4. Apply G5-R02-style explicit auth recovery to agent routes. Definitive session rejection offers Reconnect; old private work does not transfer. Business 403/transient transport failure does not rotate credentials.
5. Two sequential agent requests must work in one valid browser session. Provider failure/cancellation must leave manual presets, numeric filters and old cached results usable.
6. Reuse ResultDetails and all eight sparse-bin fields. Link to actual selected experiment/condition records instead of building a second scientific display.
7. Verify keyboard focus, error announcements, mobile layout and readable table equivalents. Trace exposes approved actions/results only.
8. Extend the existing Playwright harness with an injected scripted provider, while keeping FastAPI, queue, worker, SQLite and published results real. Mocking the entire run/read/compare chain is not end-to-end proof.
9. Use `SG_GATE5_ATTEMPT_DIR` with a fresh `../verification/gate6/...` path for the existing harness. Rebuild static assets after source is stable. Do not terminate unrelated previews or reuse another attempt's database.

## 7. Phase D — verification and one frozen review packet

| Planned suite | Required proof / failure cases |
| --- | --- |
| `tests/agent/test_tool_registry.py` | Exact twelve names, functional supported handlers, strict inputs, unsupported seed/preset/cost combinations, correct condition binding. |
| `tests/agent/test_provider.py` | Disabled startup, async lifecycle, timeout/429/5xx/auth/model errors, finite retries, malformed/multiple calls and secret/label exclusion. No external inference. |
| `tests/agent/test_tool_loop.py` | Exact call IDs/order, durable six-turn/eight-call limits, repair counts despite changing IDs, no hidden enqueue from read/compare. |
| `tests/agent/test_request_persistence.py` | Same-intent replay, changed-body conflict, concurrent submit/resume, crash before enqueue/after enqueue-before-link/after result-before-response, restart and stale ownership. Actual SQLite and PostgreSQL sessions. |
| `tests/agent/test_continuation.py` | Waiting/failed/cancelled/completed jobs, receipt replay, no double continuation, sequential questions in one browser session, legacy session-resume compatibility. |
| `tests/agent/test_grounding.py` | Invented paths/IDs/numbers/directions, incompatible comparisons, adverse/null/unqualified values, exact sparse diagnostics and bounded deterministic fallback. |
| `tests/agent/test_api.py` | Missing/expired/wrong credentials, cross-session access, strict envelopes, request tracing, bounded inputs and sanitized errors. |
| `tests/agent/test_migrations.py` | Fresh schema and upgrade from 0008 preserve existing state; package includes new migration; both backends. |
| `tests/e2e/test_agent_flow.spec.ts` | Scripted provider plus real browser/API/worker run/read/compare, waiting reload, accepted response loss/retry, auth recovery, provider failure with functioning presets/cache, result links and accessibility. |
| Existing nine Gate 5 browser cases | All continue passing, especially per-bin/cache and accepted-job identity. Do not weaken/delete accepted regressions. |

Inject failures at actual persistence/transport boundaries. Tests that repeat implementation output are insufficient. No xfail/skip to hide known defects. Use isolated SQLite files and unique PostgreSQL schemas. Reuse the existing service through `../.tools/use-existing-test-postgres.ps1`; do not print credentials or install a replacement. Missing required database checks are BLOCKED.

### Planned verification commands

Run after implementing the listed tests. They have not been executed as Gate 6 evidence during planning.

```powershell
Set-Location -LiteralPath 'C:\Users\Abhinav Anand\Downloads\nvidia\shiftguard'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$sgAttempt = Join-Path (Resolve-Path '..\verification').Path ('gate6\offline-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $sgAttempt -Force | Out-Null
$env:SG_GATE5_ATTEMPT_DIR = $sgAttempt
Remove-Item Env:SG_E2E_BASE_URL -ErrorAction SilentlyContinue
$sgPython = '.\.venv\Scripts\python.exe'
$sgNpm = 'C:\Program Files\nodejs\npm.cmd'

& $sgPython -B -m pytest tests/agent -m 'not live' -q -p no:cacheprovider --basetemp "$sgAttempt\agent-temp" --junitxml "$sgAttempt\agent-junit.xml" --tb=short *> "$sgAttempt\agent.log"
$sgAgentExit = $LASTEXITCODE
& $sgNpm --prefix frontend run typecheck *> "$sgAttempt\typecheck.log"
$sgTypeExit = $LASTEXITCODE
& $sgNpm --prefix frontend run build *> "$sgAttempt\build.log"
$sgBuildExit = $LASTEXITCODE
& $sgNpm --prefix frontend run test:e2e *> "$sgAttempt\playwright.log"
$sgBrowserExit = $LASTEXITCODE
& $sgPython -B -m pytest tests/integration/test_static_boundaries.py -q -p no:cacheprovider --basetemp "$sgAttempt\static-temp" --junitxml "$sgAttempt\static-junit.xml" --tb=short *> "$sgAttempt\static.log"
$sgStaticExit = $LASTEXITCODE
@{agent=$sgAgentExit; typecheck=$sgTypeExit; build=$sgBuildExit; browser=$sgBrowserExit; static=$sgStaticExit} | ConvertTo-Json | Set-Content "$sgAttempt\commands.json" -Encoding UTF8
```

Run affected existing continuation/API/queue/migration tests when those owners change: `tests/unit/test_continuation_replay.py`, `tests/unit/test_queue_races.py`, `tests/integration/test_continuation.py`, `tests/integration/test_api_security.py`, `tests/integration/test_gate4_review2_regressions.py`, `tests/integration/test_worker_lifecycle.py`, migration isolation/upgrade suites. Record actual node IDs. Reuse Gate 4 acceptance invariants for touched transactions; do not restart a general Gate 4 audit.

Parent performs one final non-live backend suite on frozen source using `python -B -m pytest tests -m 'not live'` with isolated basetemp/JUnit and the existing PostgreSQL URL. Collect selected nodes first. Run required local PostgreSQL cases explicitly even if existing cases also carry a `live` marker; that marker must not silently exclude required database proof. Provider canaries require a separate opt-in and never run merely because an API key exists.

No automatic Gate 2/Gate 3 reproduction for an agent/UI-only change. A demonstrated change to numerical persistence/publication/identity requires the parent to add the affected reproduction once. The default scope avoids those changes.

### Handoff contents

One immutable attempt under `../verification/gate6/<attempt-id>/`:

- `source-manifest.json`: base HEAD, sorted relevant path/hash map, digest and changed-file inventory; include generated assets and changed/protected backend comparison. Expected API/continuation changes cannot be reported as “all backend unchanged.”
- `commands.json`, complete logs, JUnit, Playwright report, collected test IDs and screenshots; label scripted-provider, real worker and live-provider evidence separately.
- `contract-evidence.json`: G6-A1–A8 → exact node/artifact → PASS/FAIL/BLOCKED/NOT_RUN. Do not invent expected test counts before collection.
- `docs/gate6-implementation.md`: implemented interfaces/state transitions, source identity, changed files, actual counts, unsupported tool combinations and remaining prerequisites.

Freeze source. GPT 6.1 Sol gives one consolidated verdict; fixes are one correction batch. Preserve failed attempts and original reviews. A PASS from an earlier digest does not accept changed code.

## 8. AG-G6-LIVE — account-specific verification

Missing live access does not block offline implementation. This plan itself authorizes no paid inference, account/billing change, credit redemption or model substitution.

1. User supplies a locally stored `NEBIUS_API_KEY`, exact-model access and explicit allowed request/token/spend ceiling. Check presence only; never print the key.
2. Implement `scripts/preflight_nebius.py` with offline/config inspection by default. Network calls require `--live`, explicit exact model and bounded call/token limits; support `--write-redacted-evidence <path>`. Validate limits before making any call.
3. Confirm account-visible model availability and actual endpoint/model. Missing model/access → `BLOCKED_REQUIRED_LIVE_EVIDENCE`; never silently substitute.
4. Within the allowance, run minimal chat, typed function-call with original call ID, and structured explanation-plan canaries. Public schema documentation is not proof of exact-model adherence.
5. If strict output is unreliable, verify bounded repair/deterministic fallback with the actual provider. Tool-call/auth/model failure remains a blocker; unchecked prose is not acceptable output.
6. Execute one actual natural-language flagship run/read/compare flow through durable waiting/resume, keeping UI trace and request/job/experiment links. Scripted-provider tests cannot satisfy it.
7. Record sanitized provider request IDs, latency, token usage, observed model/capability outcomes and actual cost if available. Unknown cost is not zero. Stop at the authorized limit.
8. Bind live evidence to source. Any resulting correction needs affected re-verification and review before parent acceptance.

## 9. Acceptance, rollback and parent checkpoint

| ID | Required proof |
| --- | --- |
| G6-A1 | Exactly twelve strict tools with functional supported handlers and independent policy checks. |
| G6-A2 | Exact IDs/serial execution and durable six-turn/eight-call/repair limits. |
| G6-A3 | Same authorized request/job through response loss, duplicate operations and crash recovery. |
| G6-A4 | Python-resolved evidence and deterministic claims preserve null/adverse/fallback/qualification data. |
| G6-A5 | Explicit provider failures with working Gate 5 manual controls and cache. |
| G6-A6 | Real local browser/worker continuation, both database backends, safe trace and all Gate 5 regressions. Dialect compilation is not runtime proof. |
| G6-A7 | Exact-model account canaries and actual live run/read/compare evidence. |
| G6-A8 | GPT 6.1 Sol PASS, parent source/evidence binding, source commit and separate governance checkpoint. |

Offline completion is `OFFLINE_CHECKS_PASSED`, or `BLOCKED_REQUIRED_BACKEND_EVIDENCE` if required database proof is missing. Gate 6 remains pending until every required row, including live evidence, passes on identified source. Preserve Gate 5 acceptance.

Parent records actual commit hashes after creation; no self-referential placeholders. Reuse exact-byte evidence where valid and state pre/post-commit test provenance. Antigravity must not mark itself independently accepted.

Rollback: provider disabled preserves the accepted manual workflow. Keep additive migrations and previous source/checkpoint recoverable; do not destructively downgrade job/evidence tables. No optional cleanup or framework replacement is bundled into closure.

## 10. What is required from the user

| When | Action |
| --- | --- |
| Now | Give this entire plan to Antigravity. No paid key or extra architecture answer is needed for offline coding/tests. |
| Review | Return the frozen implementation handoff and evidence/source-manifest paths to GPT 6.1 Sol. |
| Live verification | Supply provider key locally, exact-model account access and explicit allowed live usage. Key presence alone is not permission. |
| Required service unavailable | Make the existing isolated PostgreSQL 16 service accessible; keep missing checks blocked until then. |

## 11. Current implementation references

Checked 29 September 2026; verify SDK behavior against the actual locked version during implementation. No account capability or current price is inferred.

- Nebius's application-executed tool exchange and original call IDs: [Function calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling).
- Provider JSON/schema modes, still requiring local validation: [Structured output](https://docs.tokenfactory.nebius.com/ai-models-inference/json).
- Endpoint/key configuration: [Nebius quickstart](https://docs.tokenfactory.nebius.com/quickstart).
- Async client, explicit timeouts/retries and lifecycle: [official OpenAI Python SDK](https://github.com/openai/openai-python/blob/main/README.md).

Begin with the baseline inventory, then complete phases A–D as one integrated offline batch. No Gate 6 code or provider request was executed by creating this plan.
