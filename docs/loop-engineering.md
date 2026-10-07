## Current workflow — 2 October 2026

The user's 1 October override supersedes the historical assignment below: GPT-6 Luna xhigh implements disjoint, complete batches; GPT-6.1 Sol xhigh reviews the frozen backend delta; GPT-6 Astra xhigh reviews the frontend. Parent integrates evidence and handles specifically authorized difficult corrections. Reviews happen after an integrated batch, followed by correction-only re-review of material findings. Antigravity is inactive. Source commit, gate acceptance and deployment remain separate actions. Current packet: [product recovery](product-refresh-20260930/PRODUCT_RECOVERY_20261002.md); next actions: [next execution](next-execution.md). Preserve all original blocker verdicts and raw attempts.

# SHIFTGUARD implementation loop

Effective 30 September 2026 by explicit user instruction: **Antigravity codes; GPT 6.1 Sol reviews.** This supersedes the 28 September Astra review assignment (and earlier 26 September Luna/Astra assignment). Preserve prior authorship and evidence. Previous governance is archived under `../verification/gate5/antigravity-handoff-20260928/prior-governance/`.

## Roles

| Role | Owner | Responsibility |
| --- | --- | --- |
| Sole application implementer | Antigravity, using its user-configured coding model | Complete integrated batches, ordinary debugging, tests, corrections and handoff. |
| Planner and independent reviewer | GPT 6.1 Sol, in Codex | Define scope/acceptance, review frozen candidates, diagnose stalled fixes and decide review verdict. |
| Evidence/checkpoint owner | Codex parent | Validate actual evidence, preserve histories, bind accepted source and governance commits. |

No Luna/Terra coding delegation unless the user changes this assignment again. Sol is the independent planner and reviewer, not an application writer. Do not invent an Antigravity model setting or claim an external agent is running. One application writer at a time; no source edits during independent review. Existing model assignments in dated reviews describe history, not current ownership.

## Large-batch execution

1. GPT 6.1 Sol defines one usable vertical deliverable: base identity, allowed files, acceptance IDs, exclusions, dependency order and negative cases.
2. Antigravity builds all components and integration in that batch before seeking review. It fixes ordinary failures without per-file approval. A batch is a complete capability, not a target line count or an unbounded group of gates.
3. Self-verify with relevant contract checks and one final integrated run. Record actual exit codes, test counts, skipped checks, immutable evidence paths and source hashes. Real and simulated evidence remain distinct.
4. Freeze application writes. Send one compact evidence packet to GPT 6.1 Sol. Review all material findings together; optional improvements do not expand acceptance.
5. Antigravity fixes the full finding set together. GPT 6.1 Sol rechecks only changed behavior and affected dependencies. Preserve closed contracts and previous failed attempts; do not restart unrelated Gate 4/science audits.
6. Parent accepts only after required checks and independent review pass on identified source, then makes the authorized scoped source commit and separate governance checkpoint. Advance to the next gate's packet.

Two correction rounds without a newly proven requirement or closed finding trigger GPT 6.1 Sol root-cause diagnosis and a revised brief. Do not lower criteria or repeat the same broad review. Missing live access blocks only dependent live evidence; complete independent offline work first. No background scheduler or autonomous external agent is created by this workflow document.

## Current batch

**AG-G5-CLOSE completed and accepted, 29 September 2026.** See [the source-bound acceptance packet](gate5-acceptance.md); original failed review remains history.

**Current candidate: AG-G6-OFFLINE completed and verified, 30 September 2026.** Candidate attempt `offline-f72afeff-0cad-438f-bccb-157a39b08ef1` is frozen with all 6 verification suites passing (exit code 0), ready for GPT 6.1 Sol independent candidate review. See [Gate 6 batch](gate6-batch.md) and [Gate 6 implementation report](gate6-implementation.md). Live account-specific proof is a separate final evidence step requiring actual access and allowed usage; mocked success does not close Gate 6.

## 1 October correction handoff

Current Gate 6 correction review is BLOCKERS: three controls corrected, 22 findings open. Execute [AG-G6-CORRECTIONS-02](gate6-corrections-02.md); see [the current integrated review](gate6-correction-review-20261001.md). Prior current-batch paragraphs above are dated history. Gate 5 acceptance and original failure/author attempts remain intact.

## Active user override — 1 October 2026

For [LUNA6-G6-MAJOR-01](product-refresh-20260930/luna-major-batch-01.md), four GPT-6 Luna xhigh agents own exclusive file scopes. GPT-6.1 Sol xhigh reviews only after the complete major batch is integrated and self-tested. Antigravity is inactive for this batch. Earlier single-writer assignments remain historical.
