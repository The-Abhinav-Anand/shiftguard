# SHIFTGUARD Claude Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for sequential execution. Use superpowers:subagent-driven-development only if the receiving user's model/tool permissions support it. Steps use checkbox syntax. The requested executor is Claude Code Opus 5.5; historical model assignments are superseded.

**Goal:** Finish the retained ordinary-chat candidate, then implement the technically approved synthetic Gate 8 repeat slice and leave external scientific/deployment dependencies explicit.

**Architecture:** Extend existing chat/provider/worker ownership without replacing accepted experiment runners. Add pure prospective repeat contracts in a separate package and synthetic-only persistence; connect real evaluators only after a separately approved protocol lock. Parent acceptance remains distinct from author verification.

**Tech Stack:** Existing Python 3.13/scikit-learn 1.9.0, SQLAlchemy/Alembic, SQLite/PostgreSQL 16, FastAPI, React/TypeScript/Vite/Playwright and the retained lockfiles.

**Spec:** `docs/ordinary-chat.md`; outer `research/gate8-20261009/decisions.json` and `SCIENTIFIC_DECISIONS.md`; complete context in outer `deliverables/claude-handoff-20261012/PROJECT_HANDOFF.md`.

Source: retained HEAD f3f696579345347884d547f7ec4c75a84ce21184 plus source-manifest.json dirty snapshot. Created: 12 October 2026. Status: handoff plan, not executed. Commands below have expected acceptance results; they are not observed new passes.

## Global constraints

- Preserve dirty/untracked source, frozen Gates 0–7, applied migrations 0001–0011, original failures and sealed paid ledgers.
- Default seed 31001, existing Bank grid and result bytes stay reproducible. No real dataset/evaluator/provider invocation in P2 tests.
- Protocol remains DRAFT_NOT_LOCKED and confirmatory_dispatch_permitted=false until real authority/exposure/approval and a prospective lock exist.
- Source commits require completed parent verification and existing authorization. Never stage all changes indiscriminately.
- No new live API allowance, runtime/dependency installation, public deployment or submission is granted by this plan.
- Independent review means actual separately performed review. Executor self-review is verification, not independent acceptance.

## Review focus

1. Failed transactional downgrade preserves the actual dialect-specific revision and data; a new migration head does not justify weakening old row/width protections. Task 1 owns this.
2. Lost/ambiguous replies and concurrent chat retries cannot spend twice or transfer another session's history; Task 2 owns this.
3. A new served build must preserve preloaded analysis, completed-job reload identity, saved-result discovery and graphs; Task 3 owns this.
4. Missing primary cells, adverse effects and shared groups cannot disappear through renormalization, duplicate means or invalid-draw replacement; Tasks 4–6 own this.
5. Restart, incomplete writes and digest conflicts cannot be counted as completed scientific repeats; Task 7 owns this.

## Files and ownership

All paths below are relative to the application root unless explicitly called outer. Claude executes sequentially; the sets below are editing scopes, not permissions for parallel overlapping writers.

| Task | Owned create/modify paths | Existing/proposed test scope |
|---|---|---|
| 1 | `tests/agent/test_g6_comprehensive_protocol.py` | Its call-ID migration test; migration-isolation and historical-upgrade tests are read/run only |
| 2 | Retained `agent/chat.py`, `ordinary_budget.py`, `provider.py`, API chat/main/status/settings, revision 0012; ordinary tests | `tests/agent/test_general_chat.py`, `test_ordinary_budget.py`, `test_provider.py` |
| 3 | Retained frontend chat files, `api/agent.ts`, workbench, launcher; generated `shiftguard/static/` | Existing general-chat/result/preset/reload browser suites and static-boundary tests |
| 4 | Create `shiftguard/repeats/__init__.py`, `models.py`, `seeds.py`, `planning.py`, `validation.py` | Create `tests/repeats/test_seed_plan.py`, `test_validation.py` |
| 5 | Create `shiftguard/repeats/aggregation.py` | Create `tests/repeats/test_aggregation.py` |
| 6 | Create `shiftguard/repeats/uncertainty.py` | Create `tests/repeats/test_uncertainty.py` |
| 7 | Create `shiftguard/repeats/completion.py`, `synthetic_store.py` | Create `tests/repeats/test_restart_contract.py` |
| Acceptance checkpoint | Fresh outer verification folder; later source/governance checkpoints | Read/run affected tests; do not change source during the frozen run |

`shiftguard/agent/...` and `shiftguard/api/...` are the full package prefixes for the abbreviated Task 2 paths. New repeat paths are proposed future files, not present implementation. Avoid shared editing by keeping model/type changes in Task 4 and consuming them later.

## Common verification harness

Run from the application root. Create a distinct attempt once per major batch:

```powershell
$attempt = Join-Path (Resolve-Path ..).Path ('verification/claude-continuation-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $attempt | Out-Null
$testTemp = Join-Path $env:TEMP ('sg-claude-' + [guid]::NewGuid().ToString('N'))
$env:PYTHONDONTWRITEBYTECODE = '1'
```

Use a fresh testTemp for each additional pytest invocation. Preserve reports in attempt. Inspect/dot-source `../.tools/use-existing-test-postgres.ps1` only for the retained local service. Never print the URL. If unavailable, retain SQLite progress and record PostgreSQL NOT_RUN/BLOCKED. A SQLite pass is not two-backend closure.

## Task 1 — Close migration-fixture verification

Owner: Claude migration-fixture editor. Deliverable: row/width-preserving upgrade and rejected-downgrade proof on both backends.

- [ ] **Step 1 — Use the retained failing regression.** Read `test_call_id_migration_widens_preserves_and_downgrades_without_loss`, focused-02 source/log and current diff. The current initial upgrade assertion already expects 0012. Do not edit that again from the historical first-failure message.
- [ ] **Step 2 — Run to reproduce the current assertion.**

```powershell
& .\.venv\Scripts\python.exe -B -m pytest tests/agent/test_g6_comprehensive_protocol.py -k test_call_id_migration_widens_preserves_and_downgrades_without_loss -v -p no:cacheprovider --basetemp $testTemp --tb=short --junitxml "$attempt/migration.xml"
```

Expected investigation target: after rejected downgrade to 0010, PostgreSQL transactional rollback can keep 0012 while SQLite nontransactional DDL leaves 0011. Do not describe that predicted failure as a newly observed result.

- [ ] **Step 3 — Make the minimal confirmed fixture correction.** If the run confirms the two states, replace only the post-rejected-downgrade revision assertion with:

```python
expected_revision = (
    "0012_ordinary_chat_and_budget"
    if env["engine"].dialect.name == "postgresql"
    else "0011_gate6_call_id_capacity"
)
assert _revision(env["engine"]) == expected_revision
```

Keep the original oversized 65-character ID, explicit rejection, 256-byte columns, exact stored values, later successful downgrade and historical data-preservation assertions. Add table-presence assertions matching the confirmed transaction state if needed. If the actual transition differs, diagnose that transition before editing the test; never hardcode a false expected state.

- [ ] **Step 4 — Rerun the identical command and migration siblings.** The two parametrized dialect cases must pass with preserved rows/widths; `tests/unit/test_migrations_isolation.py` and `tests/agent/test_luna_g6_protocol_migration.py` must pass. Record actual collected node IDs and service/skip reasons.
- [ ] **Step 5 — Prepare a reviewable delta.** Proposed message after authorized source acceptance: `test(migrations): preserve dialect-specific downgrade expectations`. Stage only this test when authorization exists; no commit during handoff preparation or before integration review.

## Task 2 — Close ordinary backend and budget contracts

Owner: Claude backend executor. Interfaces consumed: existing session authority, ChatStore receipts/history, AgentProvider.chat and OrdinaryBudget reservation/settlement/recovery. Produce the same authenticated API contract from ordinary-chat.md; do not add a second chat or budget framework.

- [ ] **Step 1 — Pin any uncovered failure with a test.** Reuse existing auth/ownership, altered-key-body conflict, pending replay, server-only history, tool rejection, reply/usage bounds, concurrent reservation and UTC rollover tests. Add a case only for a demonstrated gap. In particular, trace definitely undispatched provider-disabled/budget-unavailable rejection versus ambiguous already-dispatched failure; only the latter may remain indefinitely pending to avoid duplicate spending.
- [ ] **Step 2 — Run focused cases before editing.**

```powershell
& .\.venv\Scripts\python.exe -B -m pytest tests/agent/test_general_chat.py tests/agent/test_ordinary_budget.py tests/agent/test_provider.py tests/agent/test_g6_comprehensive_protocol.py tests/agent/test_luna_g6_protocol_migration.py tests/unit/test_migrations_isolation.py -q -p no:cacheprovider --basetemp $testTemp --tb=short --junitxml "$attempt/ordinary-backend.xml"
```

- [ ] **Step 3 — Correct only reproduced contract defects.** Preserve 10 calls/50,000 tokens shared per UTC day, output 1,024/retries zero, reserve-before-dispatch, conservative uncertain-usage accounting, server-owned history, session-scoped immutable receipts and no general-chat tools. Confirm recovery reaches the durable ledger at startup. Revise pending 0012 only before any accepted deployment; never alter applied 0001–0011.
- [ ] **Step 4 — Rerun the identical focused command.** Both configured backends must pass. Reconcile the current test inventory against retained failed reports without changing old reports. Freeze backend files for independent review.
- [ ] **Step 5 — Prepare source acceptance.** Proposed later source message: `feat(agent): finish authenticated ordinary chat and shared budgeting`. Combine the coherent chat/backend changes after parent acceptance; do not claim the interrupted earlier reviewer returned PASS.

## Task 3 — Verify the production frontend and product journey

Owner: Claude frontend/integration executor. Consume the exact accepted backend response shapes. General chat renders unverified text; verified result panels consume experiment artifacts only.

- [ ] **Step 1 — Pin any reproduced UI defect.** Existing browser tests cover disabled status, server history, panel switching, lost-response identity and HTML-shaped literal content. Use the saved-result/preset/reload suites to catch a real integration failure. Preserve accepted submission-time auth recovery and an accepted job's identity after a lost response.
- [ ] **Step 2 — Run typecheck and production build.**

```powershell
Push-Location frontend
npm run typecheck
if ($LASTEXITCODE -ne 0) { throw 'Frontend typecheck failed' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
Pop-Location
```

The build copies dist into `shiftguard/static/`; verify those copied byte hashes. Before changing assets retain a compact old asset manifest, not another full dependency tree.

- [ ] **Step 3 — Repair only the concrete frontend/integration failure.** Keep manual presets, visible job status, discovery of existing saved Bank results, graph loading/error paths, accessible text/tables and route errors. Use real readiness/job/artifact state, never time-based fake progress. The launcher must retain worker-enabled process ownership and flags.
- [ ] **Step 4 — Run the affected browser suites and static boundary checks.**

```powershell
$env:SG_GATE5_ATTEMPT_DIR = Join-Path $attempt 'browser'
Remove-Item Env:SG_E2E_BASE_URL -ErrorAction SilentlyContinue
Push-Location frontend
npm run test:e2e -- test_general_chat.spec.ts test_result_discovery.spec.ts test_preset_graphs.spec.ts test_reload.spec.ts test_chart_chunk_failure.spec.ts
if ($LASTEXITCODE -ne 0) { throw 'Affected browser checks failed' }
Pop-Location
& .\.venv\Scripts\python.exe -B -m pytest tests/integration/test_static_boundaries.py tests/integration/test_worker_lifecycle.py tests/leakage/test_label_firewall.py -q -p no:cacheprovider --basetemp $testTemp --tb=short --junitxml "$attempt/product-boundaries.xml"
```

The default browser harness is isolated/scripted, not live model evidence. Inspect its fixtures and ensure local paid credentials are absent before running it. For real local product verification after candidate checks, use `scripts/start-local.ps1`; inspect readiness, complete a declared preloaded development job, reopen its published result and confirm actual graphs. Log exact job/experiment IDs and evidence; this development replay is not an independent research replication.

- [ ] **Step 5 — Freeze assets with their source and prepare acceptance.** Proposed later message: `feat(frontend): integrate ordinary chat without losing benchmark results`. Independent review covers affected frontend/content; parent verifies generated assets and source before a separate governance checkpoint.

## Ordinary-chat acceptance and activation boundary

Obtain one consolidated backend/science review and one affected frontend review, preserving all blockers. Run one full suite on stable source with real PostgreSQL cases and exact collection/skip reasons. Capture before/after source and asset digests; no source edits during that evidence run.

```powershell
& .\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp $testTemp --tb=short --junitxml "$attempt/full-suite.xml"
```

Only after this acceptance boundary, complete the already requested local activation by editing server-side `.env` flags to true and restarting only the owned local server. `/api/v1/agent/status` requires no inference. Authentication proof needs a real paid reply, which requires a distinct current user-approved live ceiling; do not run a canary automatically or borrow a sealed gate allowance. If live authorization is absent, record LOCAL_ENABLED_LIVE_NOT_RUN without asserting provider success. Defaults in source remain disabled.

## Task 4 — Pure repeat schema, planning and validation

Owner: Claude repeat-contract executor. Create only the listed new repeat package/test files. Dependencies: the technically approved P1 schema/reference; ordinary chat closure prevents simultaneous mixed acceptance.

Interfaces to define exactly: `derive_repeat_seed_map(key: RepeatKey, spec: RepeatSpec) -> SeedMap`; `plan_repeats(spec: RepeatSpec, binding: SourceBinding, roles: tuple[OuterRoleManifest,...]) -> RepeatPlan`; `validate_probability_pair(left: ProbabilityArray, right: ProbabilityArray, pair: PairContext) -> ValidatedPair`; `validate_condition_inventory(plan: RepeatPlan, conditions: tuple[TerminalCondition,...]) -> InventoryResult`. Expand the complete field/validation definitions from `decisions.json` p2 and the P1 packet before coding; use frozen dataclasses/immutable tuples with strict integers. The ellipsis in tuple type notation denotes a variable-length tuple, not omitted implementation.

- [ ] **Step 1 — Write `test_seed_plan.py` and `test_validation.py`.** Assert the 50-map golden digest `68900ea10536435e183f1f57d47154281f7c32db34a5f837b369330693bbffee`, exact (41001,51001) vector in the packet, shared outer split/model streams and distinct inner mask/acquisition/remask streams. Reject boolean/float/undeclared seeds, missing/extra/duplicate slots and mismatched paired row order/context. Validate finite two-column probabilities in [0,1] with row sum tolerance 1e-4 before clipping. Monkeypatch application loaders/evaluators/providers to raise if invoked.
- [ ] **Step 2 — Run the new tests and retain the actual missing-module/assertion failures.** `& .\.venv\Scripts\python.exe -B -m pytest tests/repeats/test_seed_plan.py tests/repeats/test_validation.py -q -p no:cacheprovider --basetemp $testTemp --tb=short`.
- [ ] **Step 3 — Implement the exact reviewed contracts.** Outer seeds 41001–41005, inner 51001–51010, fixed spawn indices and PCG64 remask children as defined in P1. Bind complete immutable source/role/group/seed contexts. Exact 400 slots/repeat and 20,000/full design; 400 primary pairs. Do not loosen BaselineConfig or route through the legacy runner. Return typed missing evidence for absent cells; reject extra/duplicate identities. The complete runnable numerical reference is embedded in SCIENTIFIC_DECISIONS.md section 8; port its declared algorithm, not a newly invented seed derivation.
- [ ] **Step 4 — Rerun the identical command.** Golden vectors and all negative cases pass; no real data/provider/evaluator invocation and legacy source bytes unchanged.
- [ ] **Step 5 — Prepare later message `feat(repeats): add immutable synthetic repeat planning`.** Stage only this task's new files after review/authorization, not the unrelated chat delta.

## Task 5 — Pure primary aggregation

Owner: Claude aggregation executor. Create aggregation.py and test_aggregation.py; consume Task 4 immutable contexts. Define `aggregate_primary(plan: RepeatPlan, pairs: tuple[PairedGroupLossCell,...]) -> PrimarySummary | MissingEvidence` and the prepared group-sum representation needed by Task 6.

- [ ] **Step 1 — Write synthetic arithmetic tests.** Contrast is target_temperature minus source_fraction_binned_temperature at budget 50. Eight shifted cells receive 1/8, ten inners 1/10 and five outers 1/5. Fixture counts [1,3] and paired sums [.2,-.6] must give -.1, not equal-group mean -.2. One .8 effect in exactly one of 400 primary cells gives .002. A missing/failed/unqualified/unknown-authority required pair makes estimate and interval null with all reasons. Valid fallbacks remain requested strategies.
- [ ] **Step 2 — Run `& .\.venv\Scripts\python.exe -B -m pytest tests/repeats/test_aggregation.py -q -p no:cacheprovider --basetemp $testTemp --tb=short` and retain the actual failure.**
- [ ] **Step 3 — Implement the reducer from P1.** Preserve original row mass within each cell and equal declared weights across cells/repeats. Validate strict nonnegative counts, bounded finite paired sums, zero membership/zero sums and exact contexts. Retain outer/inner summaries and ddof=1 sensitivity SDs. Never divide variability by sqrt(50) or infer independent datasets. No real labels/loader/evaluator inputs.
- [ ] **Step 4 — Rerun the identical command.** Include order/chunk invariance, nonfinite and missing-secondary/full-grid distinction. Mark synthetic outputs as synthetic.
- [ ] **Step 5 — Prepare later message `feat(repeats): aggregate qualified paired synthetic cells`.** Commit only after source acceptance and authorization.

## Task 6 — Conditional group uncertainty

Owner: Claude uncertainty executor. Create uncertainty.py and test_uncertainty.py. Define `group_multiplicities(group_ids: tuple[str,...], draw_id: int, spec: UncertaintySpec) -> tuple[int,...]` and `paired_group_interval(prepared: PreparedAggregate, spec: UncertaintySpec) -> IntervalResult | MissingEvidence`.

- [ ] **Step 1 — Write synthetic cluster tests.** One multiplicity per globally sorted group is reused across all its occurrences. Enumerated two-group draws (2,0),(1,1),(0,2) give [.2,-.1,-.2] for the Task 5 fixture. Changing evaluation membership is rejected in fixed_external. An invalid zero-mass draw in bank_overlap_diagnostic makes the interval unavailable with draw IDs retained. Constant .125 effects yield [.125,.125].
- [ ] **Step 2 — Run `& .\.venv\Scripts\python.exe -B -m pytest tests/repeats/test_uncertainty.py -q -p no:cacheprovider --basetemp $testTemp --tb=short` and retain the actual failure.**
- [ ] **Step 3 — Implement the exact P1 algorithm.** For b=0..9999 use SeedSequence([61001,8,1,b]), PCG64, G draws and bincount. Quantiles [.025,.975], method linear. Collapse inner/cell group sums once as specified, prove equality to full arithmetic, stream weights within the measured memory envelope. Never discard/redraw failed draws. Modes are fixed_external and bank_overlap_diagnostic; the latter has no confirmatory coverage/hypothesis claim.
- [ ] **Step 4 — Rerun the identical command.** Test deterministic resume, chunking, fewer than two groups, unavailable mass, degenerate intervals and retained negative/adverse evidence.
- [ ] **Step 5 — Prepare later message `feat(repeats): add deterministic conditional group intervals`.** The blueprint's outer-first procedure differs; technical implementation does not resolve the required human amendment.

## Task 7 — Synthetic restart-safe completion

Owner: Claude persistence executor. Create completion.py, synthetic_store.py and test_restart_contract.py. Define `completion_action(existing: CompletionRecord | None, incoming: CompletionRecord) -> INSERT | IDEMPOTENT_REUSE | Conflict` using typed actions and a small isolated synthetic store. No migration or public API for real repeats belongs in this slice.

- [ ] **Step 1 — Write isolated crash/retry tests.** Crash before atomic commit counts no completion; crash after commit returns immutable identical content on retry; different digest under the same repeat ID conflicts; truncated-ID collision cannot overwrite; failure attempts remain; scheduling/UUID/time does not alter scientific identity. Inject faults at actual persistence seams.
- [ ] **Step 2 — Run `& .\.venv\Scripts\python.exe -B -m pytest tests/repeats/test_restart_contract.py -q -p no:cacheprovider --basetemp $testTemp --tb=short` and retain the actual failure.**
- [ ] **Step 3 — Implement the existing P1 logical contract plus real synthetic-store atomic writes.** Bind plan/context/content with canonical SHA-256 JSON, ensure_ascii true and allow_nan false; separate UTF-8 LF byte hashes. Reuse reviewed immutable/conflict-safe storage patterns without adding a general workflow engine. Keep data strictly fabricated and evaluator-private by interface; no real scoring adapter or public artifact endpoint.
- [ ] **Step 4 — Rerun the identical command.** Demonstrate actual isolated process/store restart, not only a mocked logical callback. Verify old seed/default runner/scientific/migration hashes unchanged and collect meaningful tests from Tasks 4–7.
- [ ] **Step 5 — Prepare later message `feat(repeats): persist synthetic repeat completions atomically`.** Parent accepts the complete P2 batch only after an independent science/backend review and source-bound focused/full evidence. Pure reference's existing 47 passes are not production implementation passes.

## External closure and paper progression

P2 acceptance is not full Gate 8 acceptance. The user supplies the actual independent human approver and custodian; SCI-03 pool qualification and SCI-04 numerical authority; exposure/seal history; fixed external row/group bindings and feature-only group audit; approval of the changed uncertainty estimand/group allocation. Bind code, lockfiles, exact bytes/roles/groups/grid/seeds/metrics/contrast/allowed claims before unsealing.

After a real prospective lock and authorization, implement/review the evaluator-private adapter and execute the approved design. Preserve every failed/adverse cell and compute the declared interval. Bank repeats remain development robustness. Adult adapter/replication is Gate 9; hosting Gate 10; submission Gate 11. Do not add those implementations to P2.

Update the working paper from independently recomputed actual results using RESEARCH_HANDOFF.md. Reconcile the faculty DOCX in a separate current verification record; never overwrite its historical checksum. Reconcile stale Gate 7 ledger pointers as governance-only work after confirming the final accepted live record. Keep source acceptance distinct from governance.

## Completion packet

One final major-batch packet contains source and dependency/asset hashes, exact test nodes and command reports, actual counts/skip reasons, consolidated independent review/blockers, fixed-source proof and preserved baseline checks. Freeze first, verify next, authorize source commit, then record a separate governance checkpoint. No fixed wall-clock estimate is asserted for service recovery, review or full-suite execution.
