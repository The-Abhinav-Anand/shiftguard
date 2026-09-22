# Gate 4: one bounded closure batch

Active from 21 September 2026. This replaces the repeated broad-review loop.
Gate 4 is **CORRECTIONS_REQUIRED**, not accepted. Existing historical results remain
historical; they do not certify the current working tree.

## Fixed scope and authority

Antigravity is the application writer. Astra owns the acceptance review. Terra High
is a narrow escalation after two evidenced failures on the same difficult defect;
transfer that slice rather than allowing concurrent application writers. Sol High
is optional for one named independent question, not another general review.

The acceptance specification is [gate4-acceptance.json](gate4-acceptance.json):
eight existing contracts covering data identity, API authority, continuation,
job ownership, publication/recovery, scientific verification, migration/packaging,
and candidate evidence. Its `remaining_proof` fields are **unverified obligations**,
not claims that the new tests cover the entire system.

Freeze new features and optional cleanup for this batch. Preserve the scientific
protocol, research files, original review reports and accepted historical evidence.
SCI-03 pool qualification and SCI-04 numerical policy remain explicit deferred
decisions; no silent change to their scientific definitions. API-07's checkout seed
script does not become an installed-package feature in this batch.

## Execute these four corrections together

1. **R6-01 / SCI-01 / I01:** Remove manifest-controlled synthetic opt-outs from
   production Bank loading. Synthetic data requires the explicit trusted test seam.
   Check all production callers. Prove fabricated data is rejected and both the
   frozen real dataset and explicit synthetic fixtures retain their intended paths.
2. **R6-02 / API-02 / I03:** Make resume conditional on the dependency generation
   and waiting state it inspected, or serialize binding and completion consistently.
   A successfully appended pending job must prevent completion. A serialized late
   bind may be rejected after completion. Preserve nonce/receipt retry semantics;
   test both admitted binding and lost-response replay using independent connections.
3. **R6-03 / C02 / I05:** Apply the same ownership contract to reservation, normal
   publication and recovery. Bind generation, experiment/digest/execution, job ID,
   preparing attempt and fencing token to the current owner in the transaction.
   Reject wrong or partial authority conservatively. Assert full rollback, including
   result/audit rows, job events and publication/job states. Retain a valid-owner
   control and process-level reservation tests. Consolidate duplicated ownership
   checks only when doing so removes the cause across these paths.
4. **R6-04 / SCI-02 / I06 + SCI-07 / I08:** Complete Gate 2's independent logical
   identity and projection checks. Exact key sets and byte hashes alone do not
   establish logical validity. Reconstruct the Gate 2 preimages and compare disk,
   returned output and database projections. Keep a genuinely valid fixture and
   negative fixtures with valid physical hashes but invalid logical identities.
   Finish per-attempt evidence isolation without deleting old verifier results.

The detailed counterexamples remain in
`../../docs/aegis/reviews/2026-09-20-remediation-review/REVIEW.md`.
Do not create a new numbered review or implementation plan for each correction.
Update the existing finding and its evidence in [fix-ledger.md](fix-ledger.md).

## Verification sequence and stop rules

From the application root:

```powershell
& .\.venv\Scripts\python.exe -B scripts/check_gate4_closure.py
```

This runs the permanent acceptance counterexamples. They are also collected by
the normal full suite. Failures currently represent the four existing R6 defects.
Do not delete, xfail or weaken their assertions to manufacture a pass. Test setup
may change to reflect an accepted implementation, retaining each counterexample
and its observable success/failure contract.

While fixing, use the changed contract's focused regressions. Once a focused check
passes, broaden only for an untested affected path. For each I01-I08 row, record
the exact existing/new test node IDs or reproduction artifact that proves it.
Reuse sufficient existing tests; do not add tests merely to raise the count.
For stateful boundaries, cover valid operation, invalid authority/content, retries,
and relevant concurrent/crash transitions across SQLite and PostgreSQL 16.

`SHIFTGUARD_TEST_POSTGRES_URL` must name an isolated PostgreSQL 16 **test** database.
The new continuation/publication tests create and remove only unique
`sg_closure_<uuid>` schemas; the test role needs schema creation rights. Existing
project suites may use that database's ordinary schema, so never point the full
suite at application or production data. Missing service evidence is BLOCKED, not
PASS and not a reason to start another code review. No credentials in handoffs.

When the focused guards and contract mapping are ready, submit one compact
pre-commit inspection packet. Follow the repository's existing parent verification
and commit authorization boundary. On the resulting clean candidate, run:

```powershell
& .\.venv\Scripts\python.exe -B scripts/check_gate4_closure.py --candidate
```

The candidate command runs the guards first, then **one** full suite only if the
guards pass without required skips and the tree is clean. A failed prerequisite
stops that attempt. It records source hashes, Git identity, JUnit results and logs
under a new `../verification/gate4-closure/<attempt>/` directory. It checks that
source did not change during verification. `current_attempt.json` selects the
latest attempt; earlier attempts are retained. Interrupted work stays IN_PROGRESS
and cannot inherit a previous PASS. Test success never sets `gate_accepted=true`.

Run the affected scientific reproduction on the same clean candidate, retaining
new evidence beside historical evidence. Do not rerun unrelated accepted gates.
Provide the I01-I08 coverage mapping, installed-wheel/migration evidence, required
backend results and reproduction paths in the same compact handoff. An unchanged
test result can be reused within that exact candidate; changed relevant source
invalidates it. A failure gets a targeted correction and affected checks, not an
automatic restart of every review.

**Acceptance and stop:** all eight fixed contracts have evidence, required checks
pass without unexplained skips, the four R6 blockers are closed, and Astra accepts
that exact candidate. Record acceptance once and move to the next authorized
phase. Optional cleanup, style changes and new features cannot reopen this gate.
A newly demonstrated violation of an existing blocking contract still requires a
reproducer and fix under that contract; no arbitrary review-round limit can turn
a known defect into a pass.

## Required handoff, no more than one compact packet

For each open finding, provide: root cause, affected paths, fix, exact test node IDs,
observed results and remaining limit. Include the candidate identity, I01-I08
coverage mapping, evidence directory, PostgreSQL result and explicit deferred
items. Do not substitute “all resolved” or a total passing-test count for these.

The parent-added guards and runner are verification infrastructure. They do not
fix the four production defects, complete PostgreSQL validation or accept Gate 4.
