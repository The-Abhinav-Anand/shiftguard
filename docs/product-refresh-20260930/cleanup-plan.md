# Exact removal, archival and consolidation plan

30 September 2026. **No files deleted or moved.** This is the requested reviewable list.

## Exact inventories

| Inventory | Contents | Disposition |
| --- | --- | --- |
| [cleanup-inventory.csv](cleanup-inventory.csv) | Every measured cache/build/placeholder/duplicate-migration candidate, absolute path, byte count, reason and replacement | 189 listed files: 178 directly regenerable/redundant; nine migration copies conditional; two historical build copies archival-first. |
| [archive-inventory.csv](archive-inventory.csv) | 51 historical audit, proof and superseded execution-report files | Archive outside the active product working set with hashes/index and rewritten references; preserve history. |
| [test-retention-inventory.csv](test-retention-inventory.csv) | 64 current Python/TypeScript test source files | Retain contract assertions. Exclude from product runtime delivery. No test deletion justified by gate number. |
| [complete accessible file inventory](../../../verification/product-planning-20260930/file-inventory.json) | Accessible paths/sizes plus explicit runtime exclusions and permission errors | Enables narrower future cleanup; inaccessible paths have no verified removable contents. |

Counts are an inspection snapshot. Rerun the read-only inventory before any later removal because build/test operations regenerate caches.

## Remove regenerable clutter: 178 files, 3,477,242 measured bytes

The CSV's `REMOVE_REGENERABLE` rows enumerate 176 individual Python bytecode/frontend intermediate build or TypeScript cache files, totaling 3,477,240 bytes. The two `REMOVE_REDUNDANT_PLACEHOLDER` rows are:

- `C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/tests/agent/.gitkeep`
- `C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard/tests/e2e/.gitkeep`

Both directories now contain real tests. Bytecode removal is restricted to application source/test/script/verifier/root-migration caches. The inventory excludes `.venv`, `node_modules`, outer frozen verification checkouts and installed evidence packages from this removal class.

`frontend/dist/` is an intermediate Vite output. `frontend/scripts/copy-static.mjs` copies it into the served `shiftguard/static/`; Docker also consumes it during its build stage. Remove only while builds are idle and after confirming the served bundle remains complete. Keep source, `package-lock.json`, build/copy scripts and current served assets. Future builds recreate `dist`; deletion does not simplify application logic.

## Consolidate nine exact duplicate migration source files: 16,938 bytes

These root files are currently byte-identical to their corresponding canonical packaged files:

```text
alembic/env.py
alembic/versions/0001_gate0.py
alembic/versions/0002_gate1_experiments.py
alembic/versions/0003_gate1_execution_audit.py
alembic/versions/0004_publication_records.py
alembic/versions/0005_gate4_jobs_and_continuation.py
alembic/versions/0006_gate4_hardening.py
alembic/versions/0007_gate4_r4_hardening.py
alembic/versions/0008_gate4_attempt_binding.py
```

Paths above are relative to the application root. Exact absolute targets are in the CSV. Canonical owner: `shiftguard/alembic/` inside that root. `shiftguard/migrations.py` constructs the packaged script directory; root `alembic.ini` points to `%(here)s/shiftguard/alembic`; Docker no longer copies the redundant root tree. Tests use the packaged resource owner. Root-only historical 0007 is now present canonically; older audit text describing it as missing is superseded.

Before removing copies: collect incoming current source/config/test/CLI references; confirm no supported external invocation uses `alembic/env.py` or explicitly overrides script location; preserve all canonical raw revision bytes; verify direct CLI fresh/head and supported upgrades on both backends plus installed-wheel resources. Keep **both ini files**, since root CLI and installed package have different locations. Keep canonical applied revisions 0001–0008 and the unaccepted Gate 6 forward candidate 0009. Resolve Gate 6 current-head regression in its existing correction batch, not by deleting a migration or its test.

This is a separate source-cleanup batch after the candidate correction freeze, with a source diff and affected migration evidence. It must not silently alter accepted historical checkouts or a running migration directory.

## Archive before removing two old local distribution copies: 278,915 bytes

- `shiftguard/dist/shiftguard-0.1.0-py3-none-any.whl`
- `shiftguard/dist/shiftguard-0.1.0.tar.gz`

Paths are relative to the outer workspace; CSV contains exact sizes. These local copies are historical builds, not proof of the current dirty Gate 6 candidate. First preserve the originals with hashes and any incoming package-evidence references in an immutable archive. Candidate wheel proof remains required outside checkout. Retain `dist/.gitignore` if present. Do not delete an accepted wheel inside a verification packet.

## Markdown and historical proof: move out of the active reading set

The archive CSV enumerates original audit/checkpoint files under outer `docs/aegis/` and these six superseded application packets:

```text
docs/gate5-batch.md
docs/gate5-corrections.md
docs/gate5-implementation.md
docs/gate6-batch.md
docs/gate6-execution-plan.md
docs/gate6-implementation.md
```

These files are **not eligible for immediate deletion**: reviews and current corrections still reference them. Archive procedure: copy exact bytes to a dated external history archive, verify hashes, write path/claim/source index, rewrite current incoming links, verify link targets, then remove redundant active copies only when the archive is retained. Original BLOCKERS, accepted-source records and failed attempt evidence remain immutable.

Retain near the product: README, AGENTS, current next-execution, loop policy, settings/run/deployment guides, original scientific contracts, current acceptance and review pointers, fix ledger, API schemas/contracts, dataset manifests, package/legal/notices and security policy. Historical content may be linked from these; do not merge stale author claims into a new current PASS.

Current pointer refresh to perform with the next authorized documentation checkpoint: README and AGENTS still contain superseded phase/reviewer wording; `docs/loop-engineering.md` includes an old ready-for-review candidate claim. The authority is current Gate 6 review/corrections plus `.agent/gates.json`. Rewrite active introductions with dated state and preserve historical sections, not delete the corrective history.

Research manuscript, bibliography, exports/builders, evidence snapshot and original blueprint/research documents are separate requested deliverables. Keep or archive them as a unit; do not classify them as product garbage.

## Tests and source: retain or explicitly consolidate

| Path / symbol | Current dependency evidence | Action |
| --- | --- | --- |
| `tests/integration/test_gate4_review{2,3,4,5}_regressions.py` | Tests real capability/admission, terminal-state, ownership/recovery/content/migration failures repaired in active owners | Keep. Later rename/group by invariant if useful, with an assertion/node mapping and unchanged negative guarantees. |
| `tests/acceptance/test_gate4_closure.py` | I01–I08 guards, production identity, attempt/fence and evidence laws | Keep the bounded acceptance authority. |
| `tests/unit/test_verifier{,_gate3}_hygiene.py`, `test_verifier_postgres_url.py` | Import live gate-specific verifier modules | Keep tests and `verification/verify_gate{2,3}_reproduction.py`. No script retirement merely because its gate passed. |
| Leakage, acquisition, history-block, calibration, metrics, reproducibility tests | Scientific core still serves current benchmark product and will constrain BYO adapters | Keep. |
| `shiftguard/datasets/registry.py::select_nested_prefix` | Referenced only by `tests/leakage/test_label_firewall.py`; real acquisition has another owner | Conditional entire-file removal: first move those nested/label-blind assertions onto real production acquisition, prove they fail on a violating implementation and keep their behavior. Then remove helper only after reference scan. |
| `shiftguard/datasets/adult.py::ADULT_CATEGORICAL_FEATURES` | Definition only in current source/test/script search | Optional symbol removal after verifying no documented/exported consumer. This does not authorize deleting Adult ownership or its future replication path. |
| `JobQueue.record_stage` | Definition only; current runtime stage behavior is not established by a caller | Resolve whether stage events remain required; wire and verify or explicitly retire the unused method in a behavior-reviewed batch. Not a whole-file deletion. |
| `finalize_publication`, `verify_capability`, `enqueue_experiment` alias | Historical cleanup candidates already absent from current source search | No new deletion to perform. Do not repeat old cleanup instructions. |
| `runner.py`, `outage_runner.py`, `stress_runner.py` | CLI/API supported run types and distinct frozen analytical contracts | Keep; extract only proven shared mechanics under replay/reproduction checks. |
| `frontend/src/hooks/useWorkbench.ts` and Gate 5 tests | Accepted auth/cache/retry semantics; visual refresh must preserve them | Keep. Agent identity repairs belong to the current Gate 6 batch. |

## What can be excluded from deployed product without deleting engineering assets

Runtime delivery should use an explicit allowlist: installed `shiftguard` package including static and canonical migrations, locked runtime dependencies, authorized config/secrets at deployment, and runtime storage. Source tests, review/history docs, paper/resume exports, development scripts, caches, duplicate migration source and local evidence stay outside the runtime image/wheel unless an explicit packaged entrypoint needs them. Inspect built wheel/image contents to prove that boundary; don't infer it merely from a directory name.

Do not remove `.venv`, `frontend/node_modules`, required `.tools` runtimes/caches, application `var/` DBs/results, dataset bytes/manifests, source/lockfiles, live staging, accepted/failed evidence, package evidence, frozen Gate 1 clone or applied canonical migrations. A stored result can be unrelated to runtime source yet still be required audit data.

## Execution and acceptance for a later cleanup batch

1. Regenerate inventories; resolve absolute paths and verify each is under the intended root. Record source/status and active build/test/worker ownership. Do not recurse through a computed unverified target.
2. Remove only the listed idle regenerable files/placeholders with literal-path filesystem operations. No blanket `git clean`, reset or workspace recursive delete. Preserve all uncommitted Gate 6 source.
3. Perform conditional source consolidations separately, with reference searches and a focused contract map. Do not combine migration retirement with new business behavior.
4. Archive historical copies only with byte hashes, archive manifest, incoming-link rewrites and retained storage. Never delete the sole existing failed/accepted proof.
5. Verify absence of exact deleted files, unchanged protected/raw hashes, expected source diff, current link/import/CLI resolution, and only tests/builds affected by the source changes. No repeat of unrelated scientific or Gate 4 audits for cache deletion.

Sixteen directories denied read access, including pytest scratch and installed tooling areas; their paths are recorded in [inventory summary](../../../verification/product-planning-20260930/inventory-summary.json). Their size, emptiness and removable status are **not established**. No ACL change, escalation or deletion was attempted.
