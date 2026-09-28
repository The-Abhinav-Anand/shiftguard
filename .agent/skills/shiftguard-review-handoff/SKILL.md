---
name: shiftguard-review-handoff
description: Prepare or resume a compact SHIFTGUARD loop handoff between Antigravity and GPT-6 Astra Extra High. Use when transferring a completed batch, resolving stale checkpoints, or preparing one independent gate review.
---

1. Inspect HEAD/status, ownership, gate ledger, active packet, and latest candidate review. Treat stale summaries as historical; reconcile using exact commits and evidence, not timestamps alone.
2. Follow `docs/loop-engineering.md`. Record one active application writer: Antigravity using the user-configured coding model implements the complete authorized batch and corrections. GPT-6 Astra with `reasoning_effort=xhigh` plans/reviews independently and never writes concurrently. Do not delegate coding to Luna/Terra/Sol under the current assignment.
3. Maintain one fix ledger: ID, reproducible defect, affected invariant, owner/file, regression test, actual result, remaining action. Do not reopen closed issues without affected behavior or new evidence.
4. Complete a coherent batch before review. Keep ordinary failures with the writer. Escalate unresolved scientific/protocol contradictions immediately rather than inventing a new scientific choice.
5. Prepare a packet containing exact base/head, narrow diff/function excerpts, fix ledger, negative-probe results, full-suite/service results when required, immutable evidence links, and explicit limitations. Aim for about 3,000 input tokens; include necessary dependency context even when it exceeds that target.
6. Use one consolidated Astra Extra High review after the whole batch is integrated and self-tested. Return all material findings together to Antigravity. A correction review covers changed behavior and affected invariants, not an automatic repeat of all historical gates. After two correction cycles with no verified acceptance progress, have Astra diagnose the root cause and revise the Antigravity brief; do not lower acceptance criteria or manufacture a PASS.
7. Preserve initial FAIL records and corrected candidate history. Source acceptance and documentation closure are separate. Do not copy an old PASS into a new source candidate.
8. Check account usage before delegation and at milestones. It is shared and delayed. Reserve capacity for final evidence and reporting, stop below the user ceiling, and never redeem a reset without a direct user request.

Output only the compact packet and the next executable action. A handoff contains no fabricated model availability, installations, tests, commits, or acceptance.
