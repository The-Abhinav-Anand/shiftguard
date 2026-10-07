# LUNA6-G6-MAJOR-01 â€” four scoped writers, one major-batch review

Authorized 1 October 2026 by the user's instruction to launch four GPT-6 Luna subagents for MASTER_PLAN.md. This supersedes the Antigravity writer assignment for this execution. GPT-6.1 Sol xhigh is dispatched only after the major batch is integrated, self-tested and frozen; no per-file Sol review.

## First deliverable and dependency

Complete the offline Gate 6 correction batch from [the master plan](MASTER_PLAN.md), [the 22-finding packet](../gate6-corrections-02.md) and [the independent review](../gate6-correction-review-20261001.md). Preserve corrected S04/S06/S13 and accepted Gate 5 behavior. The public visual refresh and private BYO batches follow this dependency; do not mix them into these fixes.

## Exclusive ownership

| Luna | Production write set | Test write set |
| --- | --- | --- |
| 1: durable protocol | agent/controller.py, agent/store.py, jobs/queue.py narrowly, api/routes/agent_requests.py, forward revision 0010; restore only 0009's historically applied shape | Existing request/loop/continuation/API/migration agent tests; new uniquely named protocol tests |
| 2: safe tools and grounding | agent/registry.py, schemas.py, policy.py, rendering.py, prompts.py, tools/* | Existing grounding/registry tests; new uniquely named grounding/semantic tests |
| 3: browser identity | frontend/src/hooks/useAgent.ts, api/agent.ts, components/AgentPanel.tsx; App.tsx only required auth composition; no redesign | tests/e2e/test_agent_flow.spec.ts and new uniquely named browser cases |
| 4: provider and proof | agent/provider.py, settings.py, api/main.py, explicit api/test_harness.py, preflight and offline evidence scripts; frontend/scripts/e2e-server.py and test launcher/config only as needed | Existing provider tests; new uniquely named preflight/evidence/startup tests; migration isolation only head expectation |

All application paths above are relative to `shiftguard/` package under the application repository except frontend/scripts/tests. Each file has exactly one writer. Parent owns governance, integration report, generated assets and final package/evidence execution. Shared-file changes require a request to parent, not an unassigned edit. No additional subagents.

## Integration interfaces

- Preserve public API response/error envelopes, original request/job/intent/call IDs and issued continuation nonce. Frontend consumes those identities; it never invents a continuation.
- Preserve ProviderClient.chat(messages, tools=None), ProviderResponse, typed ProviderError and close lifecycle. Owner 4 supplies bounded sanitized response/error handling; owner 1 checkpoints only sanitized accepted decisions.
- Owner 2 retains ToolResult and ToolTraceEntry compatibility, adds strict explanation-plan/projection schemas and exposes reusable safe argument/error helpers; owner 1 imports them rather than duplicating a permissive projection.
- Owner 2 adds an optional `ToolContext.admit_job` callback accepting `request_params: dict` and returning the canonical JobRecord. Run handlers use it when provided. Owner 1 supplies a callback that validates request/session/generation/lease and performs canonical queue admission and owned trace/link/pause in one transaction. Ad-hoc handler tests remain subject to actual session authority; absence of callback must not bypass request fencing for a request-bound context.
- Owner 1 extends the existing queue with a caller-connection admission primitive reusing idempotency/quota logic. No nested SQLite writer, provider await inside transaction, second scheduler or second queue implementation.
- Owner 4 provides an explicit isolated scripted test app/launcher. Ordinary hosted startup cannot enable scripted inference through environment flags or override agent_enabled=False. Coordinate the launcher with owner 3 through parent.
- Existing supported tools, six turns/eight executable calls, single corrective attempt per normalized signature, seed 31001 and numerical/scientific policies remain fixed.

## Batch completion and review

Each Luna implements its whole slice and focused positive/negative cases, records actual results and a changed-file list, and reports cross-owner requests to parent. It does not edit historical evidence, current governance, generated assets, dependency locks, accepted scientific owners or another writer's files.

Parent integrates interfaces, fixes ordinary cross-slice failures through the assigned Luna, runs focused contracts on SQLite/actual isolated PostgreSQL, browser/build/package checks and one full ordinary suite on stable source. Record one new immutable evidence attempt and before/after source/protected/history hashes. Missing required evidence remains BLOCKED. Only then launch **one GPT-6.1 Sol xhigh** correction-delta review of the complete major batch. Parent retains acceptance, source commit and separate checkpoint ownership; no self-acceptance.

No live inference, installation, deletion, commit, push or deployment is authorized here. Offline execution needs no new user input. Live A7 remains a separate prerequisite.
