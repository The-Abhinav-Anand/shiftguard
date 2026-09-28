# G6-01: bounded Nemotron runtime

Prepared 28 September 2026 from blueprint v2 Sections 6–10 and the original Gate 6 execution plan. Status: PLANNED; activation requires Gate 5 acceptance. No live provider call, provider capability, current price, account credit or Gate 6 acceptance is claimed by this document.

## Ownership and scope

Antigravity implements one integrated batch and all ordinary corrections. GPT-6 Astra Extra High independently reviews the completed candidate and correction deltas under `docs/loop-engineering.md`. One application writer at a time; the 28 September workflow supersedes Luna coding ownership.

Retain the accepted scientific engine, API session capabilities, durable jobs, publication ownership and browser. Python owns numerical results. The provider proposes approved operations and evidence references. Seed 31001 only; no confirmatory unsealing, Adult replication, paid-account changes, deployment or broader cleanup.

Expected owners: `shiftguard/agent/{provider,policy,registry,schemas,controller,prompts}.py`, a bounded deterministic result renderer, `scripts/preflight_nebius.py`, focused `tests/agent/**`, and narrow additions to existing API settings/routes/schemas and browser controls. If durable provider/trace storage needs schema additions, use a forward migration; do not edit revisions 0001–0008. Reuse queue and continuation services rather than creating another worker or session system.

## Integrated implementation sequence

1. **Map existing contracts.** Bind current authenticated sessions, approved presets, persisted result readers and continuation states to the blueprint's twelve tools. Record their concrete existing owners. Any unsupported tool request returns a typed unavailable result; do not silently invent scientific behavior or configuration.
2. **Provider adapter.** Use the blueprint's async OpenAI-compatible client boundary with explicit finite timeout and retry limits. Keep credentials server-side. Verify current official provider documentation and installed SDK behavior before coding the adapter. The blueprint model `nvidia/Nemotron-3_5-Lightning` is a requested model, not proof of account availability. Do not substitute a model automatically or enable the optional Super fallback.
3. **Static registry.** Register exactly `inspect_dataset`, `list_available_scenarios`, `inspect_missingness`, `run_experiment`, `run_stress_suite`, `compare_outages`, `compare_calibrators`, `get_label_budget_curve`, `calculate_decision_loss`, `read_experiment_results`, `get_experiment_metadata`, and `generate_result_summary`. Give each a strict typed argument/result schema and explicit session policy. No general dictionary, executable code, SQL, filesystem path, raw dataset, final-test labels or user-controlled network target crosses this boundary.
4. **Bounded control loop.** Serialize tool execution, preserve original provider tool-call IDs, limit each request to six turns and eight total calls, and permit at most one correction per invalid call signature. Enforce server authorization independently of the model. Side effects reuse durable jobs, admission quotas and idempotency; a provider retry or browser reconnect must not duplicate work.
5. **Durable continuation.** Persist the request/tool/job linkage before returning a waiting response. Resume via the existing authority and nonce/receipt system after the job finishes. Keep browser disconnects, duplicate resume requests and provider timeouts distinguishable from scientific failures. Do not hold an HTTP request open for a stress suite.
6. **Grounded display.** Resolve experiment IDs and permitted metric references from persisted server records. Render only supported facts through a deterministic template; retain null, adverse, fallback and qualification information. Invalid output receives the bounded validation/fallback path, never an unchecked model answer. Display public request/tool/result facts without secrets or hidden reasoning.
7. **Browser integration.** Add the natural-language workflow beside the working preset controls. Keep all Gate 5 cached-result and job features usable when the provider is disabled or unavailable. Show whether evidence came from a cached result or a new run; show actual approved run/read/compare calls and experiment IDs.
8. **Verification and review.** Finish local deterministic contract tests and the real browser-to-job flow before the consolidated Astra review. Mock provider tests are labeled mock evidence. Once explicit account access and usage authorization exist, execute minimal exact-model chat, tool-call and structured-output canaries and one live flagship run/read/compare flow. Record sanitized usage and actual capability results. Live proof is required to accept Gate 6.

## Acceptance matrix

| ID | Required proof |
| --- | --- |
| G6-A1 | Strict twelve-tool registry; unknown tools, invalid types, unauthorized sessions and arbitrary inputs rejected before handlers execute. |
| G6-A2 | Exact call IDs, serial order, turn/call caps and one-correction policy verified with deterministic provider fixtures. |
| G6-A3 | Accepted side effects bind to one authorized durable job; retries, reconnect and duplicate continuation preserve identity. |
| G6-A4 | Persisted experiment/metric references determine every rendered analytical fact; malformed, nonexistent and unavailable evidence cannot become a successful answer. |
| G6-A5 | Provider timeout/429/5xx and unavailable credentials produce sanitized explicit states while the Gate 5 browser remains usable. |
| G6-A6 | Real local browser-to-worker continuation and public-safe tool trace pass; affected Gate 4 ownership/session invariants remain verified. |
| G6-A7 | Account-specific exact-model chat/tool canaries and a live flagship run/read/compare transcript exist; structured-output limits have a tested fallback. Mocks cannot satisfy this row. |
| G6-A8 | Independent Astra review, identified-source checks, redacted evidence and separate source/governance checkpoints complete. |

Minimum planned tests cover registry authorization, argument validation, malformed provider responses, call/turn limits, retry idempotency, cancellation/continuation races, provider failures, evidence-only rendering and label/secret exclusion. Reuse the Gate 5 browser suites and run backend suites only where the new integration affects their contracts. Store logs, source hashes and sanitized live evidence outside the application checkout under `../verification/gate6/`.

## Required from the user

Local implementation and mock verification need no paid API key. Live acceptance requires a locally stored Nebius Token Factory key, account access to the exact model, and explicit authorization for the allowed live-call budget (including use of any available credits). Do not paste the key into chat or commit it. Do not redeem credits, add payment details, contact providers or make chargeable calls on inferred authorization. Inspect only whether a local secret exists, never print its value.

Until those live prerequisites are supplied, complete independent offline work and record G6-A7 as BLOCKED_REQUIRED_LIVE_EVIDENCE. Gate 6 is not accepted merely because its mocked tests pass. The held-out agent evaluation and full adversarial Gate 7 campaign remain the following gate; the basic grounding and execution boundaries above are required immediately.
