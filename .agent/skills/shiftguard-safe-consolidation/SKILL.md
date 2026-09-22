---
name: shiftguard-safe-consolidation
description: Remove proven duplicate or unused SHIFTGUARD code while preserving frozen scientific behavior, artifact compatibility, applied migrations, and audit history. Use for an explicitly authorized cleanup batch.
---

1. Classify each candidate as internal code, contract-carrying code, generated output, persistent data, or historical evidence. Search imports, CLI/config references, tests, packaging, and documentation before calling anything dead.
2. Write the deletion/consolidation entry first: current owners, selected canonical owner, callers to migrate, behavior to preserve, negative check, compatibility requirement, and affected frozen gates.
3. Keep Gate 1/2/3 entrypoints when they reproduce accepted results. Similar runner code is not proof that an entire runner is disposable. Extract only identical mechanics; keep scientifically distinct orchestration explicit.
4. Preserve JSON serialization bytes and identity rules for existing artifacts. Test both semantic equivalence and saved-byte hashes where the old contract requires them. Never rewrite historical artifacts to make a refactor appear compatible.
5. Delete a duplicate implementation after moving every active caller and checking external contracts. Avoid aliases or fallback ladders without a demonstrated compatibility consumer.
6. Do not delete applied Alembic revisions, datasets/manifests, execution audits, failed-candidate evidence, the frozen verification checkout, research outputs, or protected originals. Use forward migrations for schema evolution.
7. Remove scratch/generated output only under an explicitly verified workspace path and the declared cleanup scope. Do not use broad recursive cleanup or reset a dirty checkout.
8. Run focused behavior tests and reference searches. Run affected frozen-gate checks only when the consolidation touches their invariants. Keep cleanup separate from new scientific behavior and durable-worker changes.

Output: removed/replaced symbols, migrated callers, retained compatibility, exact verification, net maintenance effect, and deferred items with reasons. Fewer lines alone is not acceptance.
