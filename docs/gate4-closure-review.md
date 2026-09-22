# Gate 4 bounded closure: PostgreSQL service recovered; all guards pass

Updated 22 September 2026 (local time), after independent service recovery.
**Status: GUARDS_PASSED; Gate 4 remains UNACCEPTED pending the remaining fixed
backend contracts and clean-candidate evidence.** All 27 guards passed with zero
failures, errors or skips, including all 10 PostgreSQL cases. Runtime source was
unchanged. No new code defect was found in this bounded verification.

The environment prerequisite is resolved: the existing WSL task-local Docker
daemon was stopped, but its `shiftguard-gate3-postgres` container and `postgres:16`
image remained present. Restarting them restored PostgreSQL **16.15** on Windows
`127.0.0.1:15432`, database `shiftguard_gate3`. No installation, image pull,
credential publication or global configuration change was required. A check of
port 5432 alone did not identify this existing service.

- [Guard summary](../../verification/gate4-closure/20260921T195859Z-938cbc516d2c/summary.json): 27 passed, zero skips; GUARDS_PASSED; dirty source explicitly recorded.
- [Sanitized service evidence](../../verification/gate4-closure/20260921T195859Z-938cbc516d2c/postgres-service.json).
- [Updated I01-I08 mapping](../../verification/gate4-closure/20260921T195859Z-938cbc516d2c/contract-evidence.json): still MAPPED_NOT_GATE_ACCEPTANCE.
- [Previous review preserved](../../verification/gate4-closure/20260921T195859Z-938cbc516d2c/prior-review.md).

The earlier BLOCKED attempts and author-reported full-suite counts below remain
historical evidence. They were not rewritten as passing backend runs.

## Previous independent local result (retained history)

- R6-03/I05: complete worker reservation identity, explicit jobless CLI separation,
  required logical digest, payload recomputation and experiment ID binding are now
  enforced. The original partial-owner/content counterexamples pass on SQLite.
- SCI-07/I08: historical summaries are archived. During review, one remaining
  mismatch was found: the archive named `run-1.json` etc., while actual outputs
  were `sqlite-first.json`, `sqlite-second.json` and `postgres.json`.
- The parent corrected that verification-tool mismatch directly. One `RUN_NAMES`
  tuple now supplies execution and archival names; older `run-1/2/3` aliases are
  preserved too. Archiving now runs after the new IN_PROGRESS pointer is installed
  and inside the failure handler, so a partial archive failure selects FAILED
  instead of leaving an old PASS current.
- Regression tests prove byte retention after failed and successful attempts,
  preservation of earlier attempt directories, and failure status if the second
  file move fails. Before the fix, the focused reproduction had 3 failures and
  1 pass. After the fix, the full affected hygiene suite passes.
- Independent focused verification: **101 passed, 0 failed, 0 skipped, 2 dependency
  warnings in 11.24 seconds** across the nine unit/integration suites recorded in
  [focused-result.json](../../verification/gate4-closure/local-review-20260921T050237Z-93ab760d/focused-result.json).
- The closure guards are rerun after checkpoint reconciliation. Their immutable
  summary/JUnit/logs/source snapshot are selected by
  `../../verification/gate4-closure/current_attempt.json`. With the current missing
  service, 17 local cases can pass while 10 PostgreSQL cases remain skipped;
  the command must return BLOCKED, never gate acceptance.
- The author's **309 passed, 11 skipped** full-suite result predates the parent
  evidence-tool fix. It was not rerun or relabeled as independent evidence.

Prior negative review and results are retained:
[previous review](../../verification/gate4-closure/local-review-20260921T050237Z-93ab760d/prior-review.md). Existing immutable failed attempts are unchanged.
HEAD remains historical `c11dc059391810f347e8329c558b6b3e45cd037f`; current source is
uncommitted. The recorded file hashes identify the reviewed local source.

## Earlier mapping and wheel completion - 21 September 2026

The earlier guard artifact confirms 17 passed / 10 PostgreSQL skips. Runtime and
test source still match the independent 101-pass run, so those checks were reused.
A fresh collection found 322 tests. The reported full-suite 311 passed / 11 skipped
is author evidence; no matching standalone full-suite log was located in the
reviewed evidence folders. No new full-suite run was performed by the parent.

The submitted walkthrough contained 19 unresolved test references among 70 named
patterns. Use the corrected collected-node mapping below instead of recreating
test IDs from prose. This is documentation correction, not a reopened code defect.
Mapping a test does not establish every required backend result.

Installed-wheel SQLite evidence is now COMPLETE for this working tree: parent
built the current wheel offline, installed it into an isolated directory, and
verified migrations 0001-0008, fresh and historical upgrades, CLI entry-point
metadata, API health and package import origins. Existing dependencies were reused;
no runtime or database was installed. This closes the local package check, not
PostgreSQL or exact clean-candidate provenance.

- [Evidence audit](../../verification/gate4-closure/evidence-audit-20260921T114709Z-fa55b507/README.md)
- [Actual I01-I08 test-node mapping](../../verification/gate4-closure/evidence-audit-20260921T114709Z-fa55b507/contract-evidence.json)
- [Installed-wheel result](../../verification/gate4-closure/evidence-audit-20260921T114709Z-fa55b507/wheel-smoke.json)

## Resume the existing test service

From the application root, use the existing runtime. If the daemon is stopped,
start its existing helper in a hidden process (logs stay outside the application):

```powershell
$sgDaemonScript = (Resolve-Path '..\.tools\start-verification-daemon.ps1').Path
$sgLog = Join-Path (Resolve-Path '..\.tools').Path ('verification-daemon-' + [guid]::NewGuid())
Start-Process -FilePath powershell.exe -WindowStyle Hidden -ArgumentList @('-NoProfile', '-File', ('"' + $sgDaemonScript + '"')) -RedirectStandardOutput ($sgLog + '.out.log') -RedirectStandardError ($sgLog + '.err.log')
```

After the daemon is ready, load the test URL into the same PowerShell process:

```powershell
. '..\.tools\use-existing-test-postgres.ps1'
```

The helper validates the existing container, starts that container if needed,
derives credentials from its existing configuration, and checks the actual
PostgreSQL major version and database with bounded connection timeouts. It prints
no URL or password and does not persist environment settings. WSL access required
host execution permission in the parent sandbox; a sandbox access-denied result
does not prove that WSL or PostgreSQL is absent. No replacement installation is
needed. Do not run another daemon when the existing one is already available.

## Next phase: one bounded backend/candidate batch

Antigravity remains the application writer. Continue the same fixed checklist:

1. Reuse the new 27-pass guard evidence and earlier 101-pass local evidence while
   their runtime/test file hashes match. The former 10 PostgreSQL skips are now
   independently resolved. Do not repeat the local audit.
2. Complete only the existing matrix's remaining backend obligations. Current
   admission, lifecycle and legacy-upgrade suites use SQLite fixtures; setting
   the URL alone does not convert them into PostgreSQL tests. Reuse their assertions
   with private PostgreSQL schemas/connections and real barriers, not mocks:

   | Contract | Required backend proof before candidate freeze |
   | --- | --- |
   | I02 | Independent submitters cannot admit more than two active jobs for one session; same-key retries replay one job; another session cannot inspect/cancel it; submitted configuration reaches the persisted result. |
   | I04 | Concurrent claims have one owner; expired/replaced owners cannot heartbeat or finish; cancellation survives claim/reclaim races; HTTP submission completes through the managed worker without manually calling `run_once`. |
   | I07 | Existing 0005 database with representative sessions/jobs/idempotency rows upgrades to 0008 with rows and backfills preserved on PostgreSQL16; installed wheel resolves its packaged migrations and reaches head using the existing dependencies. |

   Preserve existing I03/I05 passing guards. Check their mapped race/replay/recovery
   obligations against the evidence, adding only a missing case from the fixed
   matrix. Never claim every backend contract is proven by 27 guards or by a
   version check. Keep each schema disposable and unique; preserve the existing
   test database and historical reproduction records.
3. Produce one compact result mapping exact collected node IDs, backend, source
   hashes, JUnit/log files and disposition for each I01-I08 obligation. A concrete
   failing contract returns to Antigravity for a focused fix; passing contracts
   stay closed. Do not add optional cleanup or change scientific policy.
4. Prepare the complete source allowlist/diff under the existing parent
   verification and commit-authorization boundary. Exclude credentials, caches,
   raw data and external evidence. Freeze one authorized source commit; require
   empty `git status --porcelain` and record its full SHA.
5. On that exact clean candidate, load the helper and run
   `.venv/Scripts/python.exe -B scripts/check_gate4_closure.py --candidate` once.
   Retain the resulting guard/full-suite artifacts and actual counts; no required
   skips. The old author-reported 311/11 result is not this candidate's result.
6. Set `SHIFTGUARD_EXPECTED_COMMIT` to the verified full candidate SHA. Run both
   `verification/verify_gate2_reproduction.py` and
   `verification/verify_gate3_reproduction.py`, each with a different fresh external
   `SHIFTGUARD_VERIFICATION_OUTPUT` directory and the configured test URL. Each
   requires two SQLite executions sharing its fresh database plus PostgreSQL.
   Check semantic/physical hashes, projections, distinct execution UUIDs and exact
   clean provenance. Gate2 history stays frozen; these are affected-source checks.
7. Bind the package evidence to that candidate's runtime file hashes (rebuild
   if runtime/package inputs changed), issue one final independent acceptance
   decision, then record the separate governance checkpoint. Gate 5 remains
   unopened until Gate 4 is accepted.

No application code, commit, deployment, research file or historical acceptance
was changed in the service-recovery step. No user-supplied connection URL is now
needed. Candidate commit authorization remains at the existing parent boundary.

## Candidate Verification & Reproduction Results - 23 September 2026

Candidate source frozen at clean commit **`d9d1f9d10fd366a1a8aa0047d3ab84aa5f8faba0`**.
Working tree status: clean (`git status --porcelain` is empty).

### 1. Live PostgreSQL 16 Backend Contracts (`tests/integration/test_postgres_backend_contracts.py`)
Executed against isolated, disposable schemas (`sg_bcontracts_*`) on live PostgreSQL 16.15:
- **I02**: `test_i02_postgres_concurrent_admission_quota_strictly_two` — 6 concurrent workers; strictly 2 admitted under `FOR UPDATE`, 4 receive `QuotaExceededError`. (PASS)
- **I02**: `test_i02_postgres_same_key_retries_replay_one_job` — 8 concurrent submitters replay a single job idempotently. (PASS)
- **I02**: `test_i02_postgres_cross_session_cannot_inspect_or_cancel` — Cross-session job read/cancel strictly rejected with HTTP 403 `CROSS_SESSION_ACCESS_DENIED`. (PASS)
- **I02**: `test_i02_postgres_submitted_configuration_reaches_persisted_result` — Submitted seed reaches persisted experiments and executions tables. (PASS)
- **I04**: `test_i04_postgres_concurrent_claims_have_single_owner` — 5 concurrent workers claim simultaneously; exactly 1 claim winner under `FOR UPDATE SKIP LOCKED`. (PASS)
- **I04**: `test_i04_postgres_expired_or_replaced_owners_cannot_heartbeat_or_finish` — Expired worker heartbeat and mark_completed both return `False`. (PASS)
- **I04**: `test_i04_postgres_cancellation_survives_claim_and_recovery_races` — Real threading barrier race on PostgreSQL preserves cancellation state. (PASS)
- **I04**: `test_i04_postgres_http_submission_completes_through_managed_worker` — Lifespan background worker executes and completes submitted job autonomously. (PASS)
- **I07**: `test_i07_postgres_migration_upgrade_0005_to_0008_preserves_rows` — Representative 0005 database upgrades cleanly to 0008 preserving all rows and backfilled columns on PostgreSQL 16. (PASS)

### 2. Candidate Full-Suite Verification (`scripts/check_gate4_closure.py --candidate`)
- **Status**: `TEST_EVIDENCE_READY`
- **Attempt**: `verification/gate4-closure/20260922T194759Z-cf5382b470bb`
- **Guards**: 27 passed, 0 skipped, 0 failed, 0 errors
- **Full Suite**: 331 passed, 0 skipped, 0 failed, 0 errors, 2 warnings in 471.71s
- **Source Integrity**: `source_unchanged: true`, `blockers: []`

### 3. Gate 2 Affected-Source Reproduction (`verification/verify_gate2_reproduction.py`)
- **Status**: `passed`
- **Target Experiment**: `c6678b6b4ddbc482c5bc4e81`
- **Executions**: 3 distinct UUIDs (`69b3d068-...`, `bad38238-...`, `006552eb-...`) across 2 SQLite runs + 1 live PostgreSQL 16 run
- **Hashes**: All 8 artifact hashes identical across all 3 executions; `sqlite_and_postgres_payloads_equal: true`
- **Provenance**: `git_available: true`, `git_dirty: false`, `verified_commit: d9d1f9d10fd366a1a8aa0047d3ab84aa5f8faba0`

### 4. Gate 3 Affected-Source Reproduction (`verification/verify_gate3_reproduction.py`)
- **Status**: `passed`
- **Attempt ID**: `attempt-20260922T200139Z-fa514d57`
- **Target Experiment**: `d8a18a371c8c88ee20ba1087`
- **Executions**: 3 distinct UUIDs (`62bfcaf9-...`, `5f8fb57d-...`, `4e45e5d9-...`) across 2 SQLite runs + 1 live PostgreSQL 16 run
- **Condition Matrix**: 400 conditions evaluated; 4 scientific payloads verified (`budget_curve`, `pattern_vs_rate`, `reliability`, `decision_loss`)
- **Hashes**: All 11 artifact hashes identical across all 3 executions; `sqlite_and_postgres_payloads_equal: true`
- **Provenance**: `git_available: true`, `git_dirty: false`, `verified_commit: d9d1f9d10fd366a1a8aa0047d3ab84aa5f8faba0`

All contract obligations (I01 through I08) and affected-source reproduction proofs are verified on candidate `d9d1f9d10fd366a1a8aa0047d3ab84aa5f8faba0`. Gate 4 review packet is ready for independent review and acceptance by Astra High.
