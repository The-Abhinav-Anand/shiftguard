# SHIFTGUARD Opus Corrections and Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task in the large batches below. Claude Code Opus is the receiving executor. Steps use checkbox syntax for tracking. The source owner retains commit and acceptance authority. This document does not launch additional agents or authorize deployment or paid calls.

**Goal:** Close the nine independently reproduced defects in the Opus continuation, verify one integrated source snapshot, and prepare a working hosted Bank demonstration and complete hackathon submission without overstating Gate 8/9 or paper evidence.

**Architecture:** Preserve the accepted deterministic Bank pipeline, durable jobs/publication and closed Results-assistant registry. Correct ordinary-chat receipt recovery and enforce a single ordinary-provider owner per database; strengthen the synthetic repeat/Adult contracts at their public boundaries. Deploy one API process and one separate experiment worker with PostgreSQL 16 and shared durable artifacts; keep research adapters outside public presets until separately accepted.

**Tech Stack:** Existing Python 3.13 environment, FastAPI/Pydantic, SQLAlchemy/Alembic, PostgreSQL 16, supported SQLite, NumPy/scikit-learn, React/TypeScript/Vite, Playwright, existing Dockerfile, Nebius Token Factory through the existing OpenAI-compatible client. Reuse lockfiles and retained tools.

**Spec:** [Independent Opus review](../../opus-review-20261014.md), `docs/ordinary-chat.md`, `docs/gate8-next-execution.md`, `../research/gate8-20261009/SCIENTIFIC_DECISIONS.md` and `../research/gate8-20261009/decisions.json` relative to the application root. The review's OR-01–OR-09 are the correction specification. The scientific packet remains DRAFT / NOT LOCKED.

## Global constraints

- Application root: `C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard`. Commands below run here unless another directory is stated. Outer evidence root: `C:/Users/Abhinav Anand/Downloads/nvidia/verification`.
- Historical HEAD is `f3f696579345347884d547f7ec4c75a84ce21184`, branch `implementation/gate-0`. The working tree is dirty; do not reset it, overwrite another writer, or treat HEAD as the reviewed source.
- Reviewed runtime inventory: 318 files, digest `5bfb5f5815ad49ec215d265827a07270d6536c3afd646061ef8a0013928e83fe`. Full suite: 1,102 passed, zero skipped; this is a baseline, not a required future test count.
- Preserve accepted Gates 0–7 and historical failed reviews. Gate 8/9 engineering, real execution, scientific approval and final acceptance are distinct states.
- Keep general chat tool-free and labelled unverified. Results answers remain deterministically rendered from published Bank records. No repeat/Adult read tools or upload UI in these correction batches.
- Keep server-issued session authority, immutable request identity, at-most-once dispatch, the current shared ordinary limit of 10 calls / 50,000 tokens per UTC day, and zero SDK retries. Do not reset a ledger, change a date, create a new database, or rotate sessions to regain spend.
- No automatic paid startup/health probes. Historical live allowances and sealed Gate 7 evidence do not grant a fresh budget. Live testing requires a specific unspent authorization; credentials stay local/backend-only.
- Preserve migrations 0001–0011 byte-for-byte. Inspect current forward revisions before adding any. Never rewrite an applied revision to avoid an upgrade test.
- Preserve `gate8-nested-v1`, the declared five outer and ten inner coordinates, budgets `(0, 25, 50, 100, 200)`, eight methods, two predictors and five scenarios. No dropping failed cells, picking favorable seeds or treating fifty repeats as fifty datasets.
- Primary contrast remains `target_temperature - source_fraction_binned_temperature`, budget 50, binary Brier MSE, equal weighting over eight shifted cells, then ten inner repeats, then five outer repeats.
- Keep final labels inside evaluator-owned paths; no row-level outcomes or group sufficient statistics in public API responses or logs.
- Keep fabricated-data restrictions. Real Bank repeat access requires its separate authorization; confirmatory interpretation and Adult outcome access require the scientific/custodian prerequisites. This plan does not supply them.
- Use existing Python, Node and retained PostgreSQL services. Do not install replacement runtimes, change global Git settings, delete evidence, or remove tests just because an earlier gate is accepted.
- Implement one coherent batch before its review. Focused checks run during edits; one full integrated run follows the final stable correction source. Do not repeat the two-hour suite after documentation-only changes.

## Review focus

1. A pending user message survives reload before its assistant message exists: Task A1 must recover exactly one reply without a new paid dispatch.
2. Another process starts while a provider request is in flight: Task A3 must refuse a second owner without modifying the live reservation.
3. A known provider response fails application validation after usage settled: Task A2 must produce a replayable terminal failure and unlock only its own conversation claim.
4. Plausible dimensions hide impossible sums, changing row membership or false resolution counts: Tasks B1–B2 must reject them before summaries or completion claims.
5. A healthy API container has no functioning worker, dataset or persisted artifacts: Task D2 must exercise a real manual preset, restart and browser result recovery.

## 1. Execution map and ownership

| Batch | Deliverable | Depends on | Review boundary |
|---|---|---|---|
| 0 | Freeze inputs and reproduce failures | Current checkout | Baseline evidence, no code changes |
| A | Reliable ordinary chat and exclusive provider ownership | 0 | OR-01/02/03/09 and affected Gate 7 invariants |
| B | Validated repeat/Adult engineering | 0 | OR-04/05/06/07/08; fabricated data only |
| C | Exact-source integrated correction evidence | A + B | One correction verdict; source commit and governance checkpoint remain separate |
| D | Hosted judge build | A + C for activation; configuration work may start earlier | Linux image, PostgreSQL, worker, UI, persistence and bounded live path |
| E | Submission package and rehearsal | D for final evidence; text/video drafting may start earlier | Public artifacts, sponsor usage, judge access and release identity |
| R | Later empirical research | Separate authority and scientific decisions | Does not block the Bank hackathon product |

Claude owns implementation, local test execution and correction evidence. The parent/source owner reviews the packet, creates the authorized source commit and records the separate governance checkpoint. Do not assign approval to an unavailable scientist or impersonate a custodian. If work is delegated later, give workers non-overlapping file ownership; only the integrator edits shared models, application lifespan or generated assets.

### Batch 0 — preserve and reproduce

- [ ] Read `AGENTS.md`, `CLAUDE.md`, this plan and `docs/opus-review-20261014.md`. Read `.agent/session-state.md`, `.agent/gates.json`, `.agent/handoff.json` for actual accepted state; historical prose is not a new allowance.
- [ ] Read `../verification/opus-review-20261014/{source-before.json,source-after.json,test-summary.json,probe-results.json,validation-probe.json,protected-comparison.json,asset-comparison.json}`. Read the corresponding scripts rather than relying on the review summary alone.
- [ ] Capture `git status --short`, HEAD, current changed paths and hashes into a new `../verification/opus-corrections-<UTC>-<uuid>/` attempt. Record the nine expected failing cases. If source has changed since the review, identify the delta before editing; do not silently overwrite it.
- [ ] Translate the independent probes into repository regression tests in the owning tasks. Preserve the original probe artifacts unchanged. The first browser attempt's ambiguous locator and sandbox `os.link` failures are environmental/test-harness events, not additional product findings.
- [ ] Use `.venv/Scripts/python.exe`; load the retained test database with `. ../.tools/use-existing-test-postgres.ps1` when backend tests require it. Do not echo the resulting URL. If the retained daemon is unavailable, use its existing start script, not a replacement installation.

**Exit:** Every correction has an identified failing assertion and file owner. Do not rerun the entire passing baseline merely to begin the work.

## 2. Batch A — ordinary-chat reliability

### Task A1 — identity-based reply recovery (OR-01)

**Modify:** `shiftguard/agent/chat.py`, `shiftguard/api/routes/chat.py`, `frontend/src/api/chat.ts`, `frontend/src/hooks/useChat.ts`, and `frontend/src/components/GeneralChatPanel.tsx` only where state presentation needs adjustment.

**Tests:** extend `tests/agent/test_general_chat.py`; create `tests/e2e/test_chat_receipt_recovery.spec.ts` using `../verification/opus-review-20261014/chat-reload.spec.ts` as the failing scenario.

**Interfaces to produce:**

- Keep provider `ChatStore.history(conversation_id)` as role/content-only messages; provider requests must not accidentally acquire database fields.
- Make `ChatStore.messages(conversation_id)` return public message records with `id: str`, `ordinal: int`, `role` and `content`. Query the already persisted IDs/ordinals; do not derive IDs from content or list positions.
- Completion responses keep the existing `message_id` assistant-ID alias for compatibility and add `receipt_id`, `user_message_id`, `assistant_message_id`, `user_ordinal`, `assistant_ordinal` and `conversation_id`. Both original completion and replay return the same identity-bearing body.
- Frontend `ChatMessage` carries server identity and ordinal. Optimistic entries use a distinct local key and remain associated with the original idempotency key until reconciled.
- Add a pure `mergeChatMessages(existing, incoming)` helper in `frontend/src/api/chat.ts`: deduplicate by server ID, verify matching identities have identical role/content/ordinal, order by ordinal, reject conflicting records. Do not infer completion from message count.

- [ ] Add failing browser cases: history contains only the pending user row; history already contains both rows; response is lost before conversation ID reaches the browser; same content occurs in two different messages; reload occurs twice; local storage write fails.
- [ ] Assert the original idempotency key and conversation identity survive every replay. In the independent failure case, four messages remain, the recovered reply is visible exactly once, and the pending retry UI disappears only after reconciliation.
- [ ] Return stable message identities from the backend. Verify cross-session conversation access still fails and provider history contains no IDs, tokens or internal receipt data.
- [ ] For pre-correction completed receipts without the new identity fields, derive them from the stored receipt/message rows through a deterministic read adapter. Never fabricate IDs, dispatch again, or rewrite the historical reply text. Test this upgrade path and repeat replay for a consistent response.
- [ ] Merge the two completion records with fetched history by identity. Replace the matching optimistic user entry rather than appending a second copy. Treat a conflicting server record as a visible protocol error; do not clear pending identity on that error.
- [ ] Handle old local-storage history without IDs by refetching authorized server history before merging. Preserve its pending request key; do not submit a replacement prompt automatically.
- [ ] Run the old four browser cases and the new recovery cases against a fresh build with mocked APIs. A browser mock is sufficient for the merge assertion; backend receipt tests prove the server's identities separately.

**Exit:** OR-01's exact browser reproduction passes; retries do not duplicate replies or dispatches. Do not solve it by disabling reload, clearing history or issuing a new request key.

### Task A2 — distinguish terminal response rejection from ambiguous dispatch (OR-03)

**Modify:** `shiftguard/agent/chat.py`, `shiftguard/api/routes/chat.py`, `frontend/src/api/chat.ts`, `frontend/src/hooks/useChat.ts`.

**Create:** `tests/agent/test_chat_review_regressions.py` for receipt/state cases; use the existing SQLite/PostgreSQL fixture conventions.

**Interfaces to produce:**

- Add `ChatStore.fail_known(receipt: ChatReceipt, *, status_code: int, response: Mapping[str, Any]) -> None`.
- Persist status `FAILED` with `response_json={"http_status": status_code, "body": response}` and completion time. Existing string status/JSON columns can represent this; no migration is needed solely to add this state.
- A terminal failure body includes `status="FAILED"`, `receipt_id`, `conversation_id`, `user_message_id`, and the existing safe error envelope. It never contains rejected model text.
- Add a typed frontend `ChatTerminalFailure` carrying that verified identity and HTTP error code. The current generic `ApiError` discards extra response fields; preserve terminal receipt metadata explicitly so the hook can distinguish a definite failure from an ambiguous network error.
- Keep completed legacy response JSON readable. Replay dispatch handles `COMPLETED`, `FAILED` and `PENDING` explicitly; do not reinterpret old completed bodies as failure envelopes.

- [ ] Reproduce the 8,193-byte settled reply: first response is 502, same-key replay is the identical 502 without another SDK call, and a different key can continue the same conversation.
- [ ] In one transaction, CAS the receipt from PENDING to FAILED and clear `pending_receipt_id` only if it still equals that receipt. Assert the transition affected one row; rollback all changes on an ownership/state conflict.
- [ ] Retain the submitted user message as history; no fabricated assistant message is added. Mark the failed turn in the client from its terminal receipt and keep conversation ID available for the next explicit message.
- [ ] Call `fail_known` only for a known returned response rejected after successful accounting, such as empty/oversized text. A timeout, unknown usage, interrupted settlement or unknown dispatch remains conservative and never permits automatic resend.
- [ ] Preserve definite pre-dispatch rejection handling. Budget exhaustion or invalid input before dispatch must not be converted into a successful paid receipt.
- [ ] Add concurrent same-key requests with a barrier: one reservation/dispatch, one receipt, no permanently busy loser. Add different-key concurrency: one active conversation claim; an unrelated receipt cannot unlock it.
- [ ] Test completed/failed replay after process/database reopen, cross-session denial, content mismatch under the same key, and a crash between response validation and failed-receipt commit. That crash remains unresolved rather than producing a second dispatch.

**Exit:** Known rejection reaches a durable terminal state; ambiguous usage still fails closed. No budget limits or provider retry settings change.

### Task A3 — exclusive ordinary-provider ownership (OR-02)

**Create:** `shiftguard/agent/ordinary_owner.py`, `tests/agent/test_ordinary_owner.py`.

**Modify:** `shiftguard/api/main.py`, `shiftguard/agent/provider.py`, and `shiftguard/agent/ordinary_budget.py` only where the startup-recovery contract needs an explicit owner assertion.

**Bounded deployment decision:** Support one ordinary-provider dispatching API process per database for this judge build. Do not build a second distributed job system. Experiment workers do not dispatch the ordinary provider and need no such ownership lock.

**Interfaces to produce:**

```python
class OrdinaryOwnerUnavailable(RuntimeError): ...

class OrdinaryDispatchOwner:
    def __init__(self, engine: Engine) -> None: ...
    def acquire(self) -> None: ...
    def assert_held(self) -> None: ...
    def close(self) -> None: ...
```

- [ ] Add the regression first: owner A holds a reservation; app B attempts startup; B is rejected without changing day totals, halt state or A's reservation; A settles successfully.
- [ ] For PostgreSQL, acquire a nonblocking session advisory lock on a dedicated connection held for the entire app lifespan. Derive the key with a documented SHA-256 namespace, database and effective schema; do not use randomized Python `hash()`. The connection is never returned to a pool while owned.
- [ ] For file-backed SQLite, use an OS-held nonblocking exclusive lock on a sidecar file derived from the canonical database path. Use `msvcrt.locking` on Windows and `fcntl.flock` on Linux with a retained handle. A lockfile's existence is not ownership; never unlink a held sidecar to bypass contention. Keep SQLite on the already required local filesystem.
- [ ] Explicit test-harness/in-memory cases remain test-only. Ordinary live-enabled in-memory SQLite cannot provide cross-process ownership and must fail configuration validation.
- [ ] Acquire ownership before `recover_unresolved()` and before constructing an enabled provider. Only then recover abandoned reservations. A failed owner acquisition must not create/reset a day ledger or run recovery.
- [ ] Check ownership immediately before a reserve/dispatch sequence and fail closed on loss. Serialize use of the dedicated ownership connection. Do not reacquire transparently inside an existing provider instance or replay in-flight requests after ownership loss.
- [ ] Structure lifespan with `try/finally`/an exit stack: close the provider and stop accepting new dispatches before releasing ownership; release the lock and database resources on startup errors as well as normal shutdown.
- [ ] Test second startup, graceful shutdown and takeover, abrupt owner death followed by conservative unknown-reservation recovery, startup failure after lock acquisition, independent databases, and disabled-provider apps that do not recover the ordinary ledger.
- [ ] Execute process-level lock tests on Windows SQLite and PostgreSQL now; run the Linux `fcntl` path in the release image in Batch D. Do not claim Linux proof from a Windows unit mock.

**Exit:** One live owner is enforceable. A genuinely lost owner with uncertain provider usage may still halt the budget; that remains the deliberate spend policy. No zero-downtime or arbitrary multi-worker promise is made.

### Task A4 — JSON-safe validation errors (OR-09)

**Modify:** the `RequestValidationError` handler in `shiftguard/api/main.py`.

**Tests:** `tests/agent/test_chat_review_regressions.py` plus existing API validation tests affected by its public error shape.

- [ ] Add whitespace-only `prompt` and `idempotency_key` cases expecting HTTP 422, `error.code=VALIDATION_ERROR`, a request ID, no chat receipt/message rows and zero provider calls.
- [ ] Convert each Pydantic error to JSON primitives: at most 20 entries; bounded field-location segments, type code and message. Omit raw `input`, exception-valued `ctx` and arbitrary exception stringification. Preserve the existing outer error envelope.
- [ ] Test normal field errors, extra fields, oversized input, nested validation and Unicode. Verify error output contains no submitted prompt or capability token.
- [ ] Retain the route's whitespace rejection; do not bypass the validator to avoid the serialization bug.

### Batch A verification and protected scope

Run these after completing A1–A4, using a unique evidence directory and isolated temporary root:

```powershell
. ../.tools/use-existing-test-postgres.ps1
& ./.venv/Scripts/python.exe -m pytest tests/agent/test_general_chat.py tests/agent/test_ordinary_budget.py tests/agent/test_chat_review_regressions.py tests/agent/test_ordinary_owner.py tests/agent/test_gate7_adversarial_campaign.py tests/agent/test_gate7_execution_authority.py -q -p no:cacheprovider
```

From `frontend`, run `npm run typecheck`, `npm run build`, then the old/new chat Playwright specs through the existing isolated harness. Reuse its `SG_GATE5_ATTEMPT_DIR` evidence mechanism; never point tests at the user's active conversation database.

Update `scripts/check_gate7_candidate.py` and its tests only for the exact reviewed additions that affect the protected app factory/provider comparison. Preserve reconstructed historical source checks. Negative fixtures must still reject default-on activation, auth removal, tool exposure to general chat, ownership bypass and numerical engine edits. Do not expand a blanket allowlist until every differing hunk has a reason and test.

**Batch A exit:** Four findings closed, backend tests on both supported databases, old/new browser scenarios pass, general chat remains ungrounded and tool-free, Results rendering and accepted-job identity remain protected.

## 3. Batch B — scientific engineering contracts

### Task B1 — validate aggregate values and actual membership (OR-04/05)

**Modify:** `shiftguard/repeats/aggregation.py`, `shiftguard/repeats/uncertainty.py`, their callers and `shiftguard/repeats/__init__.py` if exports change.

**Tests:** extend `tests/repeats/test_aggregation.py` and `tests/repeats/test_uncertainty.py`.

**Interfaces to produce:**

- Extend `PreparedAggregate` with `membership_by_outer: tuple[tuple[tuple[str, str], ...], ...]`, containing ordered `(row_id, group_id)` pairs derived from the bound role manifests.
- Add `validate_prepared_aggregate(prepared: PreparedAggregate, plan: RepeatPlan) -> None` in `aggregation.py`. It validates the plan with `ensure_planned`, then checks the aggregate against that plan.
- Require keyword-only `plan: RepeatPlan` on `weighted_estimate`, `draw_estimates` and `paired_group_interval`. These are unaccepted internal engineering APIs; change all callers and fixtures together rather than retaining an unvalidated compatibility path.
- Make `point_estimate` a derived read-only property using validated sums/counts, or reject any serialized supplied value that disagrees with that derivation. The returned interval uses the derived value. Do not trust `999.0` because it is stored in a frozen dataclass.

- [ ] Add OR-04's replaced-sum/point case and OR-05's changing-row-ID/equal-count case. Both must raise `RepeatContractError`, not return an interval or silently relabel its mode.
- [ ] Check exact outer/group dimensions, canonical unique group IDs, plan digest, synthetic claim scope and exact per-outer membership. Recompute counts from membership and compare to `plan.group_counts(outer)` and aggregate counts.
- [ ] Check counts are Python integers excluding booleans, nonnegative and safely representable. Reject overflow before NumPy conversion/multiplication; avoid int64 overflow in weighted denominators, including caller-supplied weights.
- [ ] Check every sum is finite and `abs(sum) <= count`; a zero count requires a zero sum. Required outer row mass must be positive. No clipping, epsilon expansion, dropped groups or renormalization.
- [ ] In `fixed_external`, require the same canonical row-to-group membership across all five outers, not merely equal group totals. In `bank_overlap_diagnostic`, preserve differing memberships and its explicit nonconfirmatory label.
- [ ] Use the same boundary validation for whole intervals, chunked draws and direct weighted estimates. Missing evidence remains typed unavailability; invalid evidence is a typed error.
- [ ] Keep the exact bootstrap: 10,000 draws, PCG64 with `SeedSequence([61001, 8, 1, draw_id])`, shared group multiplicities, linear quantiles at .025/.975, no redraw/drop of invalid draws. A smaller visible test draw count never claims the declared procedure.
- [ ] Verify valid before/after estimates and chunk equivalence, all-zero multiplicities, singleton/absent groups, large counts, NaN/Inf, negative counts, booleans, duplicate IDs, changed grouping with identical row IDs and changed row IDs with identical counts.

**Exit:** Detached or tampered aggregate objects cannot bypass the plan/membership/value contract. Golden seed identity and valid numerical results remain unchanged.

### Task B2 — terminal condition accounting and pair binding (OR-06)

**Modify:** `shiftguard/repeats/models.py`, `validation.py`, `development_adapter.py`, `aggregation.py`, and completion/store serialization only where the strengthened contract requires it.

**Tests:** `tests/repeats/test_repeat_validation.py`, `tests/repeats/test_aggregation.py`, `tests/repeats/test_restart_contract.py`, `tests/repeats_adapter/test_development_adapter.py`.

- [ ] Add OR-06's complete 20,000-slot fixture with impossible counts. Assert it cannot produce either `full_grid_complete` or `primary_ready`.
- [ ] Validate unique resolution-method entries in declared method order, with strictly positive counts for entries that exist. A completed condition's counts sum exactly to its plan-bound evaluation row count. A failed condition has `resolved_method=None`, empty counts and no scored metrics.
- [ ] Validate every positive resolution against the requested method's allowed fallback chain, including binned per-row resolutions. Preserve a declared representation of mixed resolutions rather than pretending the entire condition used one fallback.
- [ ] Add `validate_coordinate_result(plan: RepeatPlan, result: CoordinateResult) -> None` in `development_adapter.py`, where `CoordinateResult` already lives. It joins primary pairs to terminal records before returning/persisting a coordinate. Check IDs, outer/inner coordinate, predictor, scenario, budget 50, requested methods, resolved accounting, fit identity and shared evaluation/mask/acquisition context.
- [ ] Keep pure fabricated algebra fixtures usable without claiming they are completed execution inventories. Only the joined adapter/completion path can claim execution completion.
- [ ] Extend paired-cell metadata to carry target/source resolution counts. Derive `fallback_cells` from any row resolving away from the requested method; mixed-bin fallback must not be hidden by the top-level method label. Preserve this metadata through serialization and database/store reopen.
- [ ] Test duplicate entries, zero-only completed accounting, wrong total, failed-but-resolved status, forbidden fallback edge, a primary pair copied from another condition, and a mixed-bin condition with a nonidentity source map.
- [ ] If the stored synthetic record schema changes, increment its explicit version and produce new attempt artifacts. Never reinterpret historical bytes under the new schema or rewrite old completion manifests. Test supported old reads or a clear version error; no silent defaults that invent accounting.

**Exit:** Exactly 400 terminal slots per coordinate and 20,000 across the declared grid can be complete only with auditable accounting. All 400 primary comparisons across the grid bind to valid terminal evidence or remain unavailable with reasons.

### Task B3 — Adult uniforms and strict scorer bounds (OR-07/08)

**Modify:** `shiftguard/adult_adapter/missingness.py`, `shiftguard/repeats/development_adapter.py`.

**Tests:** `tests/adult_adapter/test_adult_missingness.py`, `tests/repeats_adapter/test_development_adapter.py`.

- [ ] Before comparing uniforms to a rate, require a NumPy ndarray of the declared shape, floating dtype, finite values and `0 <= u < 1`. Reject integer, boolean, object and complex arrays with `AdultAdapterError`; do not cast invalid inputs into acceptable ones.
- [ ] Test NaN, both infinities, negative values, exactly 1, wrong shape and each unsupported dtype. Test valid float32/float64 matrices, zero, the largest representable value below 1, observed-cell handling and nested masks. Existing valid mask identities remain stable.
- [ ] Remove `_ROUNDING_SLACK` and its clipping branch from the private group scorer. Validate returned group sums for finiteness and exact signed row-count bounds; raise `RepeatContractError` on invalid results.
- [ ] Keep the fault-injection case `1.0000000005` for a one-row group as an error. Valid boundary cases -1, 0 and 1 remain valid. Do not weaken the central evaluator's probability validation or move final labels outside its owner.
- [ ] Preserve exact raw-token duplicate grouping, unsupported-role reporting and the Adult 13-feature contract already specified by the decision packet. Do not change these to make the new tests easier.

### Batch B verification

```powershell
& ./.venv/Scripts/python.exe -m pytest tests/repeats tests/repeats_adapter tests/adult_adapter -q -p no:cacheprovider
```

Use a unique `--basetemp` and store JUnit XML. If Windows denies a hardlink inside the sandbox, preserve that attempt and run the same isolated command with the necessary local permission. Do not replace the immutable hardlink protocol with overwrites to manufacture a pass.

Verify the seed golden digest stays `68900ea10536435e183f1f57d47154281f7c32db34a5f837b369330693bbffee`. Re-run the fabricated 2,200-row full-coordinate proof and all-primary-cell aggregation. Keep resource timing labelled by data size and environment. Do not extrapolate it into an unmeasured real Bank runtime.

**Batch B exit:** Five findings closed using fabricated data; no real outcome access, no scientific approval claim, no new public product integration.

## 4. Batch C — one integrated correction checkpoint

**Modify:** `docs/next-execution.md`, relevant active `.agent` pointers and `docs/fix-ledger.md` after verification. Keep the initial independent review unchanged. Create a separate correction review/result.

**Evidence schema:** each attempt records UTC timestamps, parent source snapshot, HEAD/dirty state, enumerated source paths with SHA-256, command/cwd, exit code, Python/Node/database versions, test counts/skips, evidence file hashes, protected comparisons, build asset hashes and outstanding external blockers. No credentials or complete settings dumps.

- [ ] Freeze source after A/B focused suites pass. Extend the inventory for newly created runtime/tests/deploy files; distinguish source files from generated assets and documentation. Hash before and after the integrated run.
- [ ] Build frontend once and compare every generated asset to `shiftguard/static`. Missing, extra and changed files must all be accounted for; HTML must reference the new asset names. Run typechecking and old/new affected browser suites against that build.
- [ ] Run the complete Python suite once with the existing PostgreSQL 16 setup and a unique basetemp. Required PostgreSQL skips mean BLOCKED, not PASS. The baseline took 2:04:02; allow a bounded long-running session and log progress rather than repeatedly restarting it.
- [ ] Re-run the OR-01–OR-09 regression matrix. Tests must fail on the relevant old implementation or the retained independent probe must establish the old failure. Do not count test names as evidence.
- [ ] Run affected Gate 7 adversarial/authority/rendering and label-firewall checks. Compare frozen backend/migration hashes. If numerical engine files stayed unchanged, record that fact; do not restart an unrelated Gate 4 audit. If a protected numerical owner changed, the affected Gate 2/3 reproduction becomes required evidence.
- [ ] Build and install the wheel into an isolated environment outside the source checkout using retained tooling. Verify imports resolve from the installed wheel, current migrations are included, an empty database upgrades, the supported historical upgrade preserves data, CLI help/status work and API health boots. Keep build/install evidence distinct from source-mode tests.
- [ ] Produce `correction-review.json` with all nine IDs, before/after source identities, regression node IDs, verdict and limitations. Preserve `docs/opus-review-20261014.md` as the initial CORRECTIONS_REQUIRED packet.
- [ ] Return the source diff and evidence to the parent/source owner for the authorized source commit. Bind acceptance to that commit and the tested runtime-file manifest; exclude only declared nonruntime documentation from source equivalence. If runtime bytes change after freeze, rerun affected checks before accepting.
- [ ] Record the governance checkpoint separately: ordinary-chat correction acceptance, synthetic engineering status, real-data restrictions and next hosting task. Do not label all Gates 8/9 complete because their engineering tests pass.

**Stop rule:** Close this correction review when the matrix passes on unchanged source. Reopen it only for a reproducible failure, an affected protected invariant or missing required evidence. New optional features go into later scope rather than becoming another surprise gate.

## 5. Batch D — Gate 10 judge deployment

### Task D1 — complete the existing release scaffold

**Modify:** existing `Dockerfile`, `.dockerignore`, `.env.example`, deployment sections of `README.md`; `shiftguard/settings.py`/health routes only for the bounded release checks below.

**Create:** `deploy/compose.judge.yaml`, `deploy/README.md`, `scripts/check_hosted_release.py`, `tests/integration/test_hosted_release_contract.py`.

**Deployment contract:** one API process with one Uvicorn worker, one separate experiment worker, PostgreSQL 16, a migration/init step, a durable artifacts volume and verified read-only Bank dataset files. The API and worker use the same image and artifact path. Use HTTPS at the ingress; do not expose PostgreSQL publicly.

- [ ] Reuse the current image stages and SQLite source verification. Pin actual resolved base-image digests in release evidence; never invent a digest. Keep lockfile installs and supported SQLite floor. Build as a nonroot runtime user with writable mounts only where needed.
- [ ] Add a compose init service running the existing `shiftguard status` migration path; start API/worker only after it succeeds. Serialize migration startup. If repeated app migration checks remain, make them safe after the completed init rather than assuming simultaneous Alembic upgrades are harmless.
- [ ] API command: `uvicorn shiftguard.api.main:app --host 0.0.0.0 --port 8000 --workers 1`. Set `SHIFTGUARD_EMBEDDED_WORKER=false` so the separate worker is the sole deployment worker.
- [ ] Worker command: `shiftguard worker --poll-interval 0.5 --recovery-interval 5`. Keep the existing queue/fencing/recovery code; do not rewrite it for compose.
- [ ] Set `SHIFTGUARD_ENVIRONMENT=hosted`, backend database URL through an untracked secret/environment channel, and `SHIFTGUARD_ARTIFACT_ROOT=/app/var/artifacts`. Provider flags start false for offline smoke. Do not put real credentials in YAML, image layers, Git, build arguments or frontend environment variables.
- [ ] Mount verified `bank-additional-full.csv` and `bank-marketing.manifest.json` at `/app/var/datasets/` read-only. Verify their frozen hashes/contract before readiness. Dataset files are deliberately excluded from the current build context; a successful image build is not proof they are present at runtime.
- [ ] Share `/app/var/artifacts` durably between API and worker. Configure persistence/backup for PostgreSQL and artifacts together. A disposable container filesystem is not the result store.
- [ ] Keep `/health/live` cheap and free of provider calls. Add or extend readiness to check database connectivity, expected migration head and verified dataset availability. Expose worker operation through the deployment acceptance probe; do not pretend a database ping proves worker liveness.
- [ ] Configure graceful shutdown, restart policy and resource limits measured from the accepted Bank preset. Keep API requests asynchronous through durable jobs. Do not allow the proxy timeout to turn a long experiment into a duplicated synchronous run.
- [ ] Build and execute the Linux image using the retained build service. Record image digest and installed package/runtime versions. Exercise the Linux ownership-lock path; mocks of `fcntl` are insufficient.

**Exit:** Offline release starts from an empty isolated database, mounts the correct data, runs migrations and serves the exact built frontend. Prepare the concrete deployable files/image before any missing hosting-access or spend approval is requested.

### Task D2 — hosted acceptance and model activation

**Probe interface:** `scripts/check_hosted_release.py --base-url URL --output PATH` is offline with respect to model inference by default. It creates its own session, submits a declared Bank preset, polls jobs and reads published artifacts; it never silently sends chat prompts. Its report stores safe IDs/hashes and redacted errors, not capabilities.

- [ ] Test session issuance, missing/wrong capability, quota/idempotency errors and one successful manual Bank workflow through public HTTP. Confirm actual worker progress and publication, not a fixture inserted by the probe.
- [ ] In a fresh browser, verify Saved results discovery, reliability plot, budget curve, decision-loss plot, pattern-versus-rate comparison, fallback/qualification text and experiment/condition provenance. Refresh the page and reopen by saved identity.
- [ ] Restart API and worker during an isolated test job at a controlled checkpoint; verify eventual correct terminal state, no duplicate published record and retained result access. Exercise cancellation and completed-job lost-response recovery without changing accepted queue semantics.
- [ ] Restart the deployment and verify previously published artifacts still match the database manifest. Read one artifact through the public route and compare its digest with the stored manifest.
- [ ] Inspect built assets, source maps if emitted, logs, image history/configuration and repository diff for credentials. Automated checks may compare secrets in memory but must report only whether a leak was found and its location, never the secret itself.
- [ ] Test a second provider-enabled API startup against the same database: readiness/startup fails, current owner/ledger remain intact. Deployment documentation explicitly prohibits scaling API workers while this ownership profile is active.
- [ ] Record the exact unspent live-call authorization before enabling provider flags. The current review spent zero calls; it does not grant a new allowance. Read existing usage locally without exposing credentials, and use the smaller of the authorized allowance and durable remaining cap.
- [ ] A separately authorized live acceptance covers a short general-chat exchange and a Results-assistant question about a saved Bank experiment. Count underlying provider requests, not UI messages: the Results workflow may require multiple tool-planning turns. Stop on authentication failure, unknown usage, cap exhaustion or unexpected dispatch; do not loop retries.
- [ ] Capture model ID, provider, sanitized usage, request/experiment IDs, rendered response provenance and pass/fail. General chat remains labelled unverified; Results numbers must agree with stored records. No screenshot may reveal the key.
- [ ] Define and test judge access before declaring readiness. The shared 10-call/day limit remains unchanged absent explicit owner authorization; one visitor exhausting it must yield a truthful cap message, not a broken spinner or fabricated live response. Arrange protected judge capacity/access with the owner while keeping required judge access free. Any larger allowance is a separate spend decision.

**Gate 10 exit:** Exact release image is running at the accessible HTTPS URL, manual engine and graphs work, persistence/restart checks pass, authorized live NVIDIA/Token Factory path is evidenced, and judge access/capacity is documented. A local PASS or healthy landing page alone does not close hosting.

## 6. Batch E — Gate 11 submission package

**Modify:** `README.md`, existing `LICENSE` only if an actual licensing correction is required, and `THIRD_PARTY_NOTICES.md` for the distributed release.

**Create:** `docs/submission/SUBMISSION.md`, `DEMO_SCRIPT.md`, `JUDGE_GUIDE.md`, `RELEASE_CHECKLIST.md`, `CLAIMS_AND_EVIDENCE.md`.

- [ ] Keep the existing Apache-2.0 license; it already exists. Audit third-party notices against shipped Python/frontend assets and Bank data provenance. Replace obsolete “Gate 0 only” scope statements with actual distribution facts.
- [ ] Write clean setup instructions for a fresh checkout, exact supported runtimes, offline/manual mode, worker process, database migrations, dataset provisioning, backend-only credentials and the two assistant modes. Explain that business uploads and Adult replication are not available.
- [ ] Draft submission text covering the problem, business use case, missing-feature simulation, calibration comparison, deterministic provenance, sponsor runtime integration, current limitations and actual evidence. Do not describe synthetic repeat adapter tests as replicated findings.
- [ ] Produce a 2:40 video script: 0:00–0:20 problem/business example; 0:20–0:55 approved Bank run/results; 0:55–1:35 graphs and practical interpretation; 1:35–2:10 a real authorized Nemotron Results interaction with provenance; 2:10–2:30 reliability/limits; 2:30–2:40 sponsor technology and access. Record actual UI outcomes; do not stage fake model responses as live.
- [ ] Prepare a judge guide with public URL, any free access instructions, a short deterministic click path, expected model-cap behavior, repository link, and a fallback recorded demonstration clearly labelled recorded. A recording does not replace the required working build.
- [ ] Prepare the public-source release: inspect current files and relevant history for secrets, private artifacts and data licensing. Exclude local evidence databases/keys from publication; preserve them locally. Do not delete regression tests or erase historical failures as cleanup.
- [ ] After owner-authorized publication, verify repository visibility/setup from a clean session, the public YouTube video duration under three minutes, selected track, sponsor feedback and all submitted links. Attach exact release commit/tag/image/source manifest to the checklist.
- [ ] Rehearse from an empty browser profile on a separate device/network if available. Verify session creation, data/results, charts and the model path using only the explicitly remaining live allowance.
- [ ] Keep the service and free judge access available through the official judging end. Record who owns hosting/credits monitoring; do not create an unrequested recurring automation.

Official requirements checked on 14 October 2026: [rules](https://nebiusglobalaihackathon.devpost.com/rules), [schedule](https://nebiusglobalaihackathon.devpost.com/details/dates). Token Factory runtime inference satisfies the stated Nebius requirement; AI Cloud hosting is optional. Verify rule changes before final submission.

### Working calendar (IST; acceptance criteria override dates)

| Date | Target | Evidence required before advancing |
|---|---|---|
| 14 October | Freeze this review and start correction regressions | Nine mapped failures, preserved source |
| 15–17 October | Complete A/B coherent correction batches | Focused backend/browser/science checks |
| 18–20 October | C integration and D release-image checks | Stable-source full suite, installed package, Linux proof |
| 21–23 October | Hosted acceptance | Real jobs/graphs/restart, bounded authorized live model path |
| 24–26 October | Feature freeze and submission assets | README/notices, claims table, video and judge guide |
| 27–29 October | Clean judge rehearsal and link checks | Exact release identity and working access |
| 30 October, target 20:00 | Submit with buffer | Official deadline is 22:30 IST |
| Through 16 December, 01:30 | Maintain judge access | Hosting and approved provider capacity available |

If a date slips, preserve the acceptance checks and reduce optional scope. Real Bank repeats, Adult replication and uploads are not prerequisites for the accepted Bank demonstration.

## 7. Research continuation after engineering acceptance

This section is a bounded future execution specification, not permission to expose real outcomes today.

### R1 — resource and identity preflight

- [ ] Run the corrected adapter on fabricated data at Bank-like size (41,188 rows) and one declared coordinate. Record wall time, peak memory, artifact size and evaluator overhead. This measures resources without accessing real outcomes.
- [ ] Define durable per-coordinate records using the existing synthetic store/completion contract, source manifest and declared seed map. Prove interruption/restart skips only a byte-verified completed coordinate and never changes its identity.
- [ ] Keep final labels/group loss sums evaluator-private. Optimize per-group scoring only if profiling requires it and an equivalent aggregate contract is proved; do not open a label-export shortcut for speed.

### R2 — real Bank development repeats

- [ ] Obtain the separate real-data execution authorization and freeze the exact source/data/config/roles/5-by-10 schedule before any new outcome inspection. Name its development scope and the earlier Bank exposure explicitly.
- [ ] Resolve SCI-03 qualification and SCI-04 numerical policy through their actual decision process. Unresolved qualification remains unknown/unavailable; it is not automatically “qualified” because a run succeeds.
- [ ] Execute the declared schedule with restartable evidence and retain failures. Do not select a subset after seeing outcomes, tune on the final evaluation labels or relabel overlapping Bank evaluations as fixed-external.
- [ ] Report the prespecified contrast, sensitivity and permitted interval with its conditional/development limits. The current group-bootstrap implementation differs from the blueprint's outer-first procedure; a human amendment is required before claiming it is the blueprint's confirmatory procedure.

### R3 — prospective Adult replication

- [ ] Before real wiring, obtain a custodian-owned training/test source manifest, feature-only overlap/group evidence and physical source-line mapping. The adapter's synthetic tests are not evidence that the external file is uncontaminated.
- [ ] Amend the prospective data contract to distinguish physical line ID from cleaned-record ordinal, document the 13 predictors, exact-token grouping and zero-observed-cell semantics. Preserve historical parser/evidence bytes; do not rewrite old results under the new parser.
- [ ] Wire grouped quarantine and role allocation to the engine only after their protocol is approved. Under-supported roles remain unavailable; no silent row fallback or duplicate leakage across roles.

### R4 — paper evidence and claims

- [ ] Keep a claims table linking each sentence about results to experiment/condition IDs, exact source and a table/figure generator. Existing single-seed results are illustrative; the new adapter tests establish engineering behavior only.
- [ ] Draft methods, motivation, dataset/task explanation, missingness mechanisms, leakage controls, baselines, fallback graph, metrics and reproducibility from implemented contracts. Add empirical tables only after authorized runs exist.
- [ ] Include mixed/negative findings, missingness qualification and scientific limitations. Do not promise an improvement, statistical significance, general business effectiveness or publication acceptance.
- [ ] A professor can assess the method and protocol before confirmatory results exist. Technical-agent review cannot supply scientific approval or retrospectively preregister an already inspected analysis.

## 8. Exact closure matrix

These are proposed regression names for the executor to create, not claims that the tests already exist.

| Finding | Owning tests | Required observation |
|---|---|---|
| OR-01 | `test_chat_receipt_recovery.spec.ts`: pending-history reload and completed-history replay | Reply visible exactly once; original key retained; no count heuristic |
| OR-02 | `test_ordinary_owner.py::test_second_owner_does_not_recover_live_reservation` | Second startup rejected; first reservation settles; Windows/Linux/backend ownership proof |
| OR-03 | `test_chat_review_regressions.py::test_known_rejected_reply_is_terminal_and_replayable` | 502 replay with one dispatch; new key can continue |
| OR-04 | `test_uncertainty.py::test_rejects_impossible_prepared_aggregate` | No interval for out-of-bound/zero-mass/overflow/tampered values |
| OR-05 | `test_uncertainty.py::test_fixed_external_requires_identical_row_membership` | Equal counts with different IDs rejected |
| OR-06 | `test_repeat_validation.py::test_inventory_rejects_invalid_resolution_accounting` and adapter pair-binding tests | No false complete grid; mixed fallback retained |
| OR-07 | `test_adult_missingness.py::test_rejects_invalid_uniform_arrays` | NaN/Inf/out-of-range/unsupported dtype rejected before hash |
| OR-08 | `test_development_adapter.py::test_out_of_bound_group_loss_is_not_clamped` | Typed error for 1.0000000005; valid extrema unchanged |
| OR-09 | `test_chat_review_regressions.py::test_whitespace_validation_returns_422_without_dispatch` | JSON-safe 422, request ID, zero writes/dispatch |

## 9. What is required from Abhinav

No user action is needed to write the correction code, run offline tests with existing services, build the artifacts or draft the submission materials.

| Required input/action | Needed by | Exact purpose |
|---|---|---|
| Confirm hackathon registration/eligibility and submission-account access | Before final submission | Only the account holder can establish eligibility and submit if no authorized connector exists |
| Supply the chosen hosting account/project access and approve its concrete cost/resource configuration | Before D deployment | The executor must first prepare the image/configuration and estimated resource request |
| Confirm active Nebius credentials/credits locally and a bounded remaining request/token allowance | Before live acceptance | Credentials never belong in chat; existing sealed allowances cannot be reused |
| Approve any increase from the current shared daily limit and judge-access arrangement | Before opening the live demo | Prevent accidental spending while allowing actual judging |
| Authorize the source commit/public repository/release publication and supply repository access if missing | After C evidence, before E publication | Reviewable diff and secret scan must already be prepared |
| Provide/upload the final video and submit the completed forms where account access is unavailable | E | Executor supplies the script, descriptions and verified checklist first |
| Name a real scientific approver/custodian and authorize real repeat work | R only | Not required to finish the current Bank product; required for the claims/data access described in R |

## 10. Ready-to-paste instruction for Claude Code Opus

> Continue in `C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard`. Read `AGENTS.md`, `CLAUDE.md`, `docs/opus-review-20261014.md` and `docs/superpowers/plans/2026-10-14-opus-corrections-and-delivery.md`. Preserve the dirty working tree and historical acceptance/evidence. The independent baseline is 1,102 passing Python tests, 279 repeat/adapter tests and four existing chat browser cases, but OR-01 through OR-09 remain reproducible defects. Implement Batch A and Batch B as coherent changes using the specified failure cases and interfaces. Use existing runtimes/PostgreSQL; no paid calls, real repeat outcome access, deletion, deployment or budget increase in these correction batches. Keep general chat tool-free, Results rendering grounded, session authority intact and numerical owners frozen. After focused tests pass, freeze source and perform Batch C once. Return one correction packet with every finding, exact evidence paths, source hashes, actual test counts/skips and unresolved external requirements. Do not rewrite the initial CORRECTIONS_REQUIRED verdict into PASS. The parent owns the authorized source commit and separate governance checkpoint. Prepare Batch D deployment and Batch E submission files next, completing concrete artifacts before requesting any genuinely missing account/spend authority. Gates 8 and 9 stay pending until their distinct acceptance requirements are actually met. Do not restart an unrelated Gate 4 audit or implement business uploads as part of this plan.

## 11. Plan self-check

- All nine review findings map to an implementation task and an observable regression.
- Source/API contracts, frontend reconciliation, backend ownership and scientific identity changes have explicit file ownership.
- Windows tests, PostgreSQL tests, Linux release checks, mocked browser proof and paid live proof are separate evidence classes.
- Existing Docker/license scaffolding is reused; deployment dependencies include data, worker and durable artifacts.
- Gates 0–7 history, frozen scientific decisions, cost constraints and publication authority remain intact.
- The final source integration run happens once after coherent corrections; further runs require a material change or failure.
