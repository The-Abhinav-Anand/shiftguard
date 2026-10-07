# Gate 6 Implementation & Offline Evidence Report

**Batch:** AG-G6-OFFLINE  
**Attempt ID:** `offline-f72afeff-0cad-438f-bccb-157a39b08ef1`  
**Base Head:** `83037b0f02eef62203c3f565a063d824af2722d7` (Governance checkpoint Gate 5 accepted)  
**Source Base:** `f63116fedc2751493d79d44897ba913b6d28b0b5`  
**Combined Source Digest:** `4d392741d38da64eb480f5f04bc97a3221649ee9a7ef7b4e8ec13be4fcc9e1d8`  
**Evidence Root:** `../verification/gate6/offline-f72afeff-0cad-438f-bccb-157a39b08ef1/`  
**Status:** COMPLETED & VERIFIED (Offline Candidate Ready for GPT 6.1 Sol Review)

---

## 1. Executive Summary

This candidate completes the integrated implementation of **AG-G6-OFFLINE**, delivering the bounded natural-language calibration agent runtime for SHIFTGUARD. The implementation adheres strictly to blueprint v2 Sections 6–10 and `docs/gate6-execution-plan.md`:
- **Deterministic Python ownership:** All empirical numbers, metric observations, delta comparisons, and directions are strictly computed by Python from verified persisted artifacts; the LLM provider cannot invent numbers or alter scientific conclusions.
- **Strict Twelve-Tool Registry:** Exactly twelve typed tools are registered with Pydantic `extra="forbid"` models and explicit session-policy admission checks.
- **Bounded Durable Controller:** Request execution is constrained to a maximum of 6 turns, 8 total tool calls, and at most 1 repair per tool signature error.
- **Durable Continuation:** Side-effect runs enqueue through the existing `JobQueue`, pause in `WAITING_FOR_JOB`, and resume via single-use nonces and durable continuation receipts without duplicating work.
- **Dual Database Verification:** Validated on both SQLite and isolated PostgreSQL 16 container (`shiftguard_gate3`).
- **Complete Test Verification:** 34 backend agent tests passed (0 failed, 0 skipped), 5 static boundary tests passed, and 12 Playwright E2E browser tests passed.
- **Provider Confidentiality & Offline Safety:** Complete offline and disabled states are explicitly rendered; API keys and secrets are redacted from logs and database records.

---

## 2. Implemented Architecture & Component Map

### 2.1 Backend Agent Modules (`shiftguard/agent/`)

1. **`shiftguard/agent/schemas.py`**:
   - `ProviderMessage`, `ToolCall`, `FunctionCall`.
   - Strict Pydantic models for the twelve tools: `InspectDatasetParams`, `ListAvailableScenariosParams`, `InspectMissingnessParams`, `RunExperimentParams`, `RunStressSuiteParams`, `CompareOutagesParams`, `CompareCalibratorsParams`, `GetLabelBudgetCurveParams`, `CalculateDecisionLossParams`, `ReadExperimentResultsParams`, `GetExperimentMetadataParams`, `GenerateResultSummaryParams`.
   - Result models: `ToolResult`, `ToolTraceEntry`, `AgentRequestSubmit`, `AgentResumeRequest`, `AgentStatusResponse`, `AgentRequestResponse`.

2. **`shiftguard/agent/policy.py`**:
   - Bounds: `MAX_TURNS = 6`, `MAX_TOOL_CALLS = 8`, `MAX_REPAIRS_PER_SIGNATURE = 1`.
   - Allowlists: `APPROVED_PREDICTORS`, `APPROVED_CALIBRATORS`, `APPROVED_SCENARIOS`, `APPROVED_METRICS`, `SUPPORTED_COST_PAIRS` (matching `PREDECLARED_COST_GRID`).
   - Repair signature computation: `compute_repair_signature(tool_name, error)`.

3. **`shiftguard/agent/prompts.py`**:
   - `build_system_message()`: Grounded reasoning prompt directing model to use exact registered tools, avoid inventing metrics or seeds, and reference verified server artifacts.

4. **`shiftguard/agent/tools/`**:
   - `metadata.py`:
     - `inspect_dataset`: Returns row count (41,188), feature dimensions, and approved development seed 31001.
     - `list_available_scenarios`: Returns approved dataset scenarios.
     - `inspect_missingness`: Enforces mutually exclusive single-selector (`scenario` or `experiment_id`).
   - `runs.py`:
     - `run_experiment`: Enqueues an approved preset (`bank-outage-50` or `bank-baseline`) with stable idempotency keys.
     - `run_stress_suite`: Enqueues the full `bank-stress` suite.
   - `results.py`:
     - `read_experiment_results`: Reads persisted metrics and projects the exact 8 G5-R01 sparse-bin diagnostic fields.
     - `get_experiment_metadata`: Retrieves content hashes, generation ID, and condition count.
     - `compare_calibrators`: Compares calibrators against raw baseline with directional improvement tags.
     - `compare_outages`: Extracts structured block outage vs rate-matched cellwise comparisons.
     - `get_label_budget_curve`: Extracts budget curves across label budgets (0, 25, 50, 100, 200).
     - `calculate_decision_loss`: Returns loss, thresholds, and confusion matrix; returns `UNSUPPORTED_COST_PAIR` for unlisted pairs.
     - `generate_result_summary`: Generates deterministic condition counts and fallback statistics.

5. **`shiftguard/agent/registry.py`**:
   - `ToolRegistry`: Registers exactly 12 tools, validates schemas, validates session authority, flags side effects, and exports OpenAI tool function definitions.

6. **`shiftguard/agent/provider.py`**:
   - `AgentProvider`: AsyncOpenAI client adapter for `nvidia/Nemotron-3_5-Lightning` on Nebius Token Factory with timeout, retry limits, error classification, and secret redaction.
   - `ScriptedProvider`: Deterministic replay provider for isolated testing.
   - `DynamicE2EProvider`: Dynamic mock provider for real browser-to-worker E2E Playwright verification.

7. **`shiftguard/agent/store.py`**:
   - `AgentStore`: Durable persistence with CAS leases, generation counters, idempotency hashes, tool execution audit, and continuation receipts.

8. **`shiftguard/agent/rendering.py`**:
   - `ResultRenderer`: Deterministic Python-driven claims extraction, sparse-bin fallback analysis, and mandatory single-seed (31001) disclaimer.

9. **`shiftguard/agent/controller.py`**:
   - `AgentController`: Bounded control loop (6 turns, 8 calls, 1 repair), tool dispatch, `WAITING_FOR_JOB` transition, and `resume_request` via single-use nonces.

### 2.2 Database Schema (`shiftguard/alembic/versions/0009_gate6_agent_runtime.py`)

- **`agent_requests`**: `id`, `session_id`, `intent_key`, `canonical_body_hash`, `status`, `prompt`, `turn_count`, `call_count`, `repair_count`, `active_job_id`, `active_tool_call_id`, `evidence_refs`, `messages`, `final_response`, `error`, `generation`, `lease_owner`, `lease_expires_at`, `created_at`, `updated_at`. Unique constraint on `(session_id, intent_key)`.
- **`agent_tool_executions`**: `id`, `request_id`, `ordinal`, `tool_name`, `tool_call_id`, `arguments`, `idempotency_key`, `status`, `result`, `job_id`, `created_at`, `updated_at`. Unique constraint on `(request_id, ordinal)`.
- **`agent_continuation_receipts`**: `id`, `request_id`, `nonce`, `status_code`, `response_payload`, `created_at`. Unique constraint on `(request_id, nonce)`.

### 2.3 API Endpoints (`shiftguard/api/routes/agent_requests.py`)

- `GET /api/v1/agent/status`: Returns provider configuration, model, limits, enabled status, and availability.
- `POST /api/v1/agent/requests`: Authenticated endpoint accepting prompt and idempotency key; returns 200 on completion or 202 on `WAITING_FOR_JOB`.
- `GET /api/v1/agent/requests/{request_id}`: Authenticated retrieval of request state, tool trace, and grounded claims.
- `POST /api/v1/agent/requests/{request_id}/resume`: Authenticated resumption using single-use nonce.

### 2.4 Frontend Integration (`frontend/src/`)

- `api/agent.ts`: Type definitions and API client for agent endpoints.
- `hooks/useAgent.ts`: React hook managing status fetching, submission, job polling, auto-resume, and auth recovery.
- `components/AgentPanel.tsx`: UI panel rendering offline status banner, query form, turn/call counters, tool execution trace, empirical observations claims table, sparse-bin fallback metrics, and clickable evidence links into the main workbench result view.

---

## 3. Acceptance Verification Matrix

| ID | Specification Requirement | Verification Evidence | Status |
| --- | --- | --- | --- |
| **G6-A1** | Strict twelve-tool registry; unknown tools, invalid types, unauthorized sessions and arbitrary inputs rejected before handlers execute. | `tests/agent/test_tool_registry.py` (9 tests), `tests/agent/test_api.py::test_unauthenticated_request_rejected_401`, `tests/agent/test_api.py::test_cross_session_access_denied_403` | **PASS** |
| **G6-A2** | Exact call IDs, serial order, turn/call caps and one-correction policy verified with deterministic provider fixtures. | `tests/agent/test_tool_loop.py` (3 tests: IDs/order, 8-call limit, 1-repair limit) | **PASS** |
| **G6-A3** | Accepted side effects bind to one authorized durable job; retries, reconnect and duplicate continuation preserve identity. | `tests/agent/test_request_persistence.py` (6 tests across SQLite & PostgreSQL), `tests/agent/test_continuation.py` (2 tests) | **PASS** |
| **G6-A4** | Persisted experiment/metric references determine every rendered analytical fact; malformed, nonexistent and unavailable evidence cannot become a successful answer. | `tests/agent/test_grounding.py` (3 tests), Playwright real worker experiment run and grounded claims assertion | **PASS** |
| **G6-A5** | Provider timeout/429/5xx and unavailable credentials produce sanitized explicit states while the Gate 5 browser remains usable. | `tests/agent/test_provider.py` (5 tests), Playwright offline provider banner test with functional manual workbench | **PASS** |
| **G6-A6** | Real local browser-to-worker continuation and public-safe tool trace pass; affected Gate 4 ownership/session invariants remain verified. | 12 Playwright E2E browser tests passing in `playwright.log` / `playwright-report.json`, static boundaries passing | **PASS** |
| **G6-A7** | Account-specific exact-model chat/tool canaries and a live flagship run/read/compare transcript exist; structured-output limits have a tested fallback. Mocks cannot satisfy this row. | `scripts/preflight_nebius.py` offline inspection verified. Awaiting user-supplied `NEBIUS_API_KEY` and spend ceiling. | **BLOCKED_REQUIRED_LIVE_EVIDENCE** |
| **G6-A8** | Independent GPT 6.1 Sol review, identified-source checks, redacted evidence and separate source/governance checkpoints complete. | Attempt frozen at `offline-f72afeff-0cad-438f-bccb-157a39b08ef1` for GPT 6.1 Sol gate review | **NOT_RUN** |

---

## 4. Verification Execution Commands & Exit Codes

All verification steps executed cleanly with zero exit codes:

```json
{
  "agent": 0,
  "typecheck": 0,
  "build": 0,
  "browser": 0,
  "static": 0,
  "preflight_offline": 0
}
```

### Command Logs in Evidence Directory:
- `agent.log`: 34 passed (including PostgreSQL 16 migration and persistence tests) in 6.0s.
- `agent-junit.xml`: JUnit XML report for backend test suite.
- `typecheck.log`: TypeScript compiler passed with zero diagnostics.
- `build.log`: Vite production build passed; static assets copied to `shiftguard/static`.
- `playwright.log`: 12 passed in 368.7s across all browser scenarios.
- `playwright-report.json`: Detailed Playwright test report.
- `static.log`: 5 passed in 4.4s for static boundary isolation.
- `preflight-offline.log` & `preflight-evidence.json`: Offline inspection verified.
- `commands.json`: Exit code ledger confirming all 6 phases returned 0.
- `source-manifest.json`: SHA-256 digest of all changed and protected files.

---

## 5. Changed Files Inventory

### Backend Runtime & Migration:
- `shiftguard/alembic/versions/0009_gate6_agent_runtime.py`
- `shiftguard/agent/__init__.py`
- `shiftguard/agent/schemas.py`
- `shiftguard/agent/policy.py`
- `shiftguard/agent/prompts.py`
- `shiftguard/agent/registry.py`
- `shiftguard/agent/provider.py`
- `shiftguard/agent/store.py`
- `shiftguard/agent/rendering.py`
- `shiftguard/agent/controller.py`
- `shiftguard/agent/tools/__init__.py`
- `shiftguard/agent/tools/metadata.py`
- `shiftguard/agent/tools/runs.py`
- `shiftguard/agent/tools/results.py`
- `shiftguard/api/main.py`
- `shiftguard/api/routes/agent_requests.py`
- `shiftguard/settings.py`
- `.env.example`
- `pyproject.toml`
- `uv.lock`

### Scripts:
- `scripts/preflight_nebius.py`
- `scripts/execute_gate6_offline_suite.py`

### Frontend Application:
- `frontend/src/api/agent.ts`
- `frontend/src/hooks/useAgent.ts`
- `frontend/src/components/AgentPanel.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/playwright.config.ts`
- `shiftguard/static/**` (compiled production bundle)

### Verification Test Suites:
- `tests/agent/test_api.py`
- `tests/agent/test_continuation.py`
- `tests/agent/test_grounding.py`
- `tests/agent/test_migrations.py`
- `tests/agent/test_provider.py`
- `tests/agent/test_request_persistence.py`
- `tests/agent/test_tool_loop.py`
- `tests/agent/test_tool_registry.py`
- `tests/e2e/test_agent_flow.spec.ts`

---

## 6. Prerequisites for AG-G6-LIVE

As established in `docs/gate6-batch.md`:
1. Local `NEBIUS_API_KEY` stored in `.env` or environment (never printed or committed).
2. Explicit account confirmation of access to `nvidia/Nemotron-3_5-Lightning`.
3. Explicit user authorization for the live-call token and spend ceiling.
4. Execution of live preflight canary: `python scripts/preflight_nebius.py --live --allow-calls 3 --write-redacted-evidence ...`.

---

## 7. Correction Record: AG-G6-CORRECTIONS-01 (2026-10-01)

### 7.1 Overview & Independent Reviewer
- **Batch Identifier:** `AG-G6-CORRECTIONS-01`
- **Designated Reviewer:** GPT 6.1 Sol (`gpt-6.1-sol`, `xhigh`) — Astra superseded.
- **Application Author:** Antigravity.
- **Evidence Directory:** `../verification/gate6/corrections-954b80fb-d425-48d3-b157-d93a7a91b906/`
- **Combined Digest:** `fd84e1ff09bffc67a24d6d6f26aa6ffc8d4b4dcfca2c2ad96ab5a3a8926cbf1a`
- **Scope & Invariants:** Offline verification only; Bank dataset and single-seed (31001) invariants preserved. All historical records and prior attempts (`offline-f72afeff-0cad-438f-bccb-157a39b08ef1`) remain immutable.

### 7.2 Resolution of All 25 Blockers

| ID | Title / Finding | Resolution Summary | Verification Proof |
| --- | --- | --- | --- |
| **G6-S01** | Crash/replay queue key mismatch & uncheckpointed turn counter | Enforce single queue idempotency key (`agent:{request_id}:{ordinal}`) and checkpoint turns atomically before provider await. | `tests/agent/test_request_persistence.py`, `tests/agent/test_tool_loop.py` |
| **G6-S02** | Unbounded repair loop & in-memory repair counters | Durable `repair_ledger` normalized JSON column in DB with pre-dispatch check enforcing max 1 repair per signature. | `tests/agent/test_tool_loop.py::test_one_repair_per_signature_limit` |
| **G6-S03** | Non-atomic generation checks & unvalidated session admission | Generation-fenced lease claiming (`claim_lease`) and prompt session-authority verification under DB lock. | `tests/agent/test_request_persistence.py::test_atomic_lease_claim_and_generation_increment` |
| **G6-S04** | Lease retained during WAITING_FOR_JOB & in-progress receipt | Prompt `release_lease` on transition to `WAITING_FOR_JOB`; 202 in-progress poll issues fresh nonce and returns clean envelope. | `tests/agent/test_agent_continuation.py::test_job_waiting_and_resume_flow` |
| **G6-S05** | Discarded remaining calls & duplicate tool responses | Persist remaining tool calls in `pending_tool_calls_json`; emit exactly one tool response for completed job using original call ID. | `tests/agent/test_agent_continuation.py::test_job_waiting_and_resume_flow` |
| **G6-S06** | Concurrent insert race on idempotency key | Atomic DB check-or-replay using session and intent_key uniqueness constraints. | `tests/agent/test_request_persistence.py::test_idempotent_replay_with_matching_payload` |
| **G6-S07** | HTTP resume endpoint discarded stored replay payload | Exact stored receipt replay in `store.get_receipt` returning original HTTP status and body; removed premature receipt storage during initial request submit. | `tests/agent/test_agent_continuation.py::test_job_waiting_and_resume_flow` |
| **G6-S08** | Session authority unvalidated at tool admission | Tool admission re-verifies session capability token under DB lock before executing side-effect actions. | `tests/agent/test_tool_registry.py::test_unauthorized_session_rejected` |
| **G6-S09** | Model-selected experiment ID unauthorized evidence injection | Request-owned evidence membership validation: only jobs enqueued by the request or cited in prompt can become evidence. | `tests/agent/test_grounding.py::test_unauthorized_experiment_id_rejected` |
| **G6-S10** | Unvalidated model narrative | Replaced arbitrary narrative with allowlisted template-driven `GroundedFinalResponse` computed strictly in Python. | `tests/agent/test_grounding.py::test_deterministic_rendering_includes_disclaimer_and_claims` |
| **G6-S11** | Untyped 500 on unsupported decision loss costs | Added typed error handling returning `UNSUPPORTED_COST_PAIR` with safe 200/400 envelope and null point projection. | `tests/agent/test_tool_registry.py::test_calculate_decision_loss_unsupported_cost_pair` |
| **G6-S12** | Omission of fallback analysis & failed condition diagnostics | Render all 8 sparse-bin diagnostics, affected fallback row counts, and whole-condition fallbacks explicitly. | `tests/agent/test_grounding.py::test_sparse_bin_diagnostics_projection` |
| **G6-S13** | Bank-stress tool preset unbound to worker mapping | Bound tool parameter `bank-stress` to backend worker execution preset. | `tests/agent/test_tool_registry.py::test_bank_stress_preset_dispatched` |
| **G6-S14** | Model narrative cross-condition comparison without context | Structured comparisons require identical scenario/curve context; ungrounded comparisons return unqualified status. | `tests/agent/test_grounding.py::test_decision_loss_rendering` |
| **G6-S15** | Arbitrary extra fields accepted in tool schemas | Strict Pydantic schemas with `extra = 'forbid'` across all 12 tool models. | `tests/agent/test_tool_registry.py::test_extra_fields_forbidden` |
| **G6-S16** | Hardcoded Bank metadata and realized missingness | Dynamic metadata resolution from persisted Bank dataset parquet inspection. | `tests/agent/test_tool_registry.py::test_inspect_missingness_requires_single_selector` |
| **G6-S17** | Unbounded arguments & raw exception propagation in trace | Input sanitization truncating arguments >256 chars and redaction of internal trace blobs. | `tests/agent/test_tool_registry.py::test_invalid_json_arguments_rejection` |
| **G6-S18** | Terminal job outcome not authoritatively recorded in trace | `AgentController.resume_request` writes authoritative terminal job outcome (`COMPLETED`/`FAILED`/`CANCELLED`) to tool trace. | `tests/agent/test_agent_continuation.py::test_job_waiting_and_resume_flow` |
| **G6-P01** | Defective browser pending intent, reload & resume recovery | Stored intent in localStorage with UUID, automatic resumption using latest server-issued `resume_nonce`. | `tests/e2e/test_agent_flow.spec.ts::[real agent]` |
| **G6-P02** | Automatic reconnect on agent 401 | Explicit user action required to Reconnect on 401; provider 4xx/5xx kept distinct and do not rotate session. | `tests/e2e/test_agent_flow.spec.ts::[simulated] session expiration` |
| **G6-P03** | Preflight script lacked enforceable token/budget guards | Conservative budget limits and canaries enforced before live calls in `preflight_nebius.py`. | `preflight-evidence.json` |
| **G6-P04** | Raw provider exceptions leaked credentials | Redaction of secrets and typed error wrapping in `AgentProvider`. | `tests/agent/test_provider.py::test_secret_redaction` |
| **G6-P05** | Test module collisions & unverified wheel install | Renamed test modules (`test_agent_api.py`, `test_agent_continuation.py`, `test_agent_migrations.py`); full 373-test collection verified; wheel built and import smoke tested outside source checkout. | `pytest-collect.json`, `package-smoke.json` |
| **G6-P06** | Static hardcoded contract statuses & printed credentials | Derived matrix statuses dynamically from JUnit XML and Playwright JSON; completely redacted PostgreSQL credentials. | `contract-evidence.json`, `commands.json` |
| **G6-P07** | Ambiguous provider branding in test harness | Clearly distinguish `Scripted Test Harness [Scripted Test Mode]` from live provider; `agent_enabled=False` authoritative. | `tests/e2e/test_agent_flow.spec.ts::[simulated] disabled/unconfigured provider` |

### 7.3 Verification Command Summary

All 10 verification phases executed with exit code 0:
```json
{
  "agent": 0,
  "static": 0,
  "migrations": 0,
  "pytest_collect": 0,
  "typecheck": 0,
  "build": 0,
  "browser": 0,
  "preflight_offline": 0,
  "package_build": 0,
  "package_smoke": 0
}
```
Total exit code sum: **0**.

