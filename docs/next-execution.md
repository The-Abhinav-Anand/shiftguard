# Current handoff: backend and candidate verification

The existing WSL PostgreSQL16 test service has been restored without installation.
All 27 acceptance guards pass with zero skips, including 10 PostgreSQL cases.
Evidence: `../verification/gate4-closure/20260921T195859Z-938cbc516d2c/summary.json` and `postgres-service.json` in that directory.
R6-01 through R6-04 remain locally verified; Gate 4 is still unaccepted.

Antigravity retains application ownership. Follow [the current handoff](gate4-closure-review.md)
for service restart and the exact next batch. Load
`../.tools/use-existing-test-postgres.ps1` into the test PowerShell process;
credentials are derived from the existing test container and never printed.

Remaining: fixed I02/I04 backend admission/worker coverage, I07 PostgreSQL legacy
upgrade/package coverage, authorized clean source commit, one candidate full
suite, affected Gate2/Gate3 reproductions, final independent acceptance.
Reuse the corrected mapping at `../verification/gate4-closure/20260921T195859Z-938cbc516d2c/contract-evidence.json`, the prior 101-pass
independent local result and current installed-wheel SQLite proof where source
hashes match. The historical 311-pass/11-skip full-suite count stays author-reported.
No code changes or commit were made during service recovery. No broad review
restart, new features, research edits or optional cleanup.

## Historical author handoff (superseded)



The following prior claims are retained for history. They do not override the
20 September FAIL review, the reopened ledger entries or the workflow above.

# Next execution: Codebase Hardening and Gate 4 Execution

Prepared 17 September 2026. This is an active execution handoff.
Baseline source commit: `c11dc059391810f347e8329c558b6b3e45cd037f`.
Active execution plan: `../docs/aegis/reviews/2026-09-17-codebase-audit/EXECUTION_PLAN.md`.
Review companion: `../docs/aegis/reviews/2026-09-17-codebase-audit/REVIEW.md`.
Fix ledger: [docs/fix-ledger.md](fix-ledger.md).

## Workflow and ownership

1. **Active Writer:** Gemini / Antigravity (`gemini_antigravity`) performs the bulk hardening and Gate 4 implementation.
2. **Escalation:** Terra High is an explicit escalation for a named difficult failure after two documented failed attempts.
3. **Reviewer:** Astra High owns planning, scientific decisions, and gate-exit review; Astra High does not write application code concurrently.
4. **Fix Ledger:** All twelve findings (A01–A12) are tracked in [docs/fix-ledger.md](fix-ledger.md).
5. **No Blind Hash Overwrites:** Scientific corrections (A06 nested uniforms, A07 unconstrained temperature fitting) will result in new experiment and condition IDs. Historical artifacts and review records are preserved.

## Hardening and Gate 4 Sequence

### Batch H0 (Completed): Truthful Checkpoint & Governance
- Reconciled `AGENTS.md`, `.agent/*`, `README.md`, `pyproject.toml`, and `docs/next-execution.md`.
- Established single fix ledger `docs/fix-ledger.md`.
- Staged skills into `.agent/skills/` (`shiftguard-candidate-evidence`, `shiftguard-review-handoff`, `shiftguard-safe-consolidation`).
- Verified discovery with dry-run test.

### Batch H1 (Completed): Scientific and Input-Contract Corrections
- **H1.1 (A01):** Enforced frozen Adult training identity before data access; rejected test/archive paths; verified bytes before writing outputs.
- **H1.2 (A05):** Made configs deeply immutable; validated unique ordered dimensions; rejected boolean budgets and invalid costs/probabilities; enforced history probability 0.50.
- **H1.3 (A06, A07):** Nested MCAR masks from single shared uniform matrix; stable unconstrained log-temperature fitting with explicit boundary/non-convergence failure handling.
- **H1.4 (A08, A12):** Centralized metric input validator (1D, equal length, binary labels, finite probabilities, positive costs); added 4 contract metric test suites and entrypoint coverage.

### Batch H2 (Completed): Integrity, Packaging, Publication, and Bounded Simplification
- **H2.1 (A02, A03):** Recoverable publication protocol (private staging -> manifest check -> PREPARED -> atomic rename -> PUBLISHED); conflict-safe repo insert on SQLite/PostgreSQL with UUID replay handling; additive migration `0004_publication_records.py`.
- **H2.2 (A04, A10):** Independent verifier closure in `verify_gate3_reproduction.py` (exact manifests, recomputed logical digest, condition ID preimages, all DB projections compared to disk, isolated attempt directories).
- **H2.3 (A09):** Packaged Alembic migrations and resource loader independent of cwd; tested wheel build and isolated distribution startup.

### Batch H3 (Completed): Hardening Candidate Verification
- Ran regression probes, full test suite, verified PostgreSQL 16 hygiene.
- Packaged comprehensive review packet in `docs/aegis/reviews/2026-09-17-codebase-audit/HARDENING_REVIEW_PACKET.md`.

### Gate 4 (Completed): Durable API and Worker
- Runtime contract (`docs/gate4-runtime-contract.md`), additive migration `0005_gate4_jobs_and_continuation.py` for `jobs`, `job_events`, `agent_sessions`, and `idempotency_records`.
- Queue claim (`BEGIN IMMEDIATE` on SQLite, `SKIP LOCKED` on PostgreSQL), worker fencing token, independent heartbeat thread on separate DB connection, bounded retries, cooperative cancellation.
- Lease recovery service (`recover_expired_leases`, `cleanup_abandoned_staging`).
- Agent continuation service with single-use nonces and atomic state transitions.
- Strict preset API (FastAPI) with `extra="forbid"`, error envelopes, request ID tracing, path traversal security, and zero dataset leakage.
- Wheel built and verified (`dist/shiftguard-0.1.0-py3-none-any.whl`).

### Complete Codebase Review Remediation (19 September 2026 - Completed)
- **Batch 1 (Concurrency & Transitions):** Initial reservation serialization (`BEGIN IMMEDIATE` / advisory lock); attempt-bound generations and recovery fencing (`0008_gate4_attempt_binding.py`); savepoint error boundaries around corrupt manifest/metadata JSON in recovery; unexpired lease guards on worker terminal mutations; atomic recheck loop in cancellation; `list_published` deduplication by `experiment_id`.
- **Batch 2 (API, Scientific, & Migrations):** Strict `PresetOverrides` schema (development seeds only, extra forbidden, explicit None check for seed 0); write-locked session rebind with dependency deduplication; PostgreSQL hosted profile auto-detection from URL and settings propagation; `SessionStatus.EXPIRED` handling with stable 401; canonical migration chain synced (`0007_gate4_r4_hardening.py` and `0008_gate4_attempt_binding.py`); polling interval float validation; Bank dataset 41,188 row count and frozen digest enforcement with explicit synthetic test seam; Gate 2/3 verifier hygiene and attempt lifecycle hardening; centralized calibration fraction validation; integer `master_seed` and `protocol_id` validation.
- **Batch 3 (Controlled Cleanup):** Removed dead bypass helpers (`finalize_publication`, `verify_capability`), redundant `enqueue_experiment` alias, obsolete runner imports, redundant root `COPY alembic/` in Dockerfile, redundant `.gitkeep`s, and `frontend/tsconfig.tsbuildinfo`.
- Full test pass: **285 passed, 1 skipped** (PostgreSQL service test).

## Next Actions
1. **Astra High Final Gate Review**: Independent review of Complete Codebase Review remediation and test verification.
2. **Clean Candidate Commit**: Author clean candidate commit upon Astra High review acceptance.
3. **Staging Verification**: Run live PostgreSQL 16 reproduction in target staging environment (`SHIFTGUARD_TEST_POSTGRES_URL`).


