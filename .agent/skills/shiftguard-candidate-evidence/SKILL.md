---
name: shiftguard-candidate-evidence
description: Verify a completed SHIFTGUARD candidate using isolated tests, exact source identity, immutable artifact evidence, and the required SQLite/PostgreSQL checks. Use before a gate review or closure, not while ordinary edits are still in progress.
---

1. Read the active gate packet, Git HEAD/status, ownership, and latest independent review. Record source SHA separately from any later documentation checkpoint SHA. Never infer acceptance from tests alone.
2. Confirm the requested gate and affected frozen invariants. Use the existing local Python and service setup. Do not install another runtime/database or change global Git configuration.
3. Run cheap negative probes and affected tests first. Use a fresh temporary directory for every pytest invocation; the historical fixed `.pytest-tmp` path can collide or retain incompatible permissions.

```powershell
$candidateTemp = Join-Path $env:TEMP ('shiftguard-check-' + [guid]::NewGuid())
& .\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --basetemp "$candidateTemp" --tb=short
```

4. Run the complete suite once on the stable candidate. Record warnings, skips, and exit code. A separately run skipped service test must be reported separately, not rewritten as a single full-suite result.
5. Check the isolated PostgreSQL service with a bounded timeout. Use only `SHIFTGUARD_TEST_POSTGRES_URL`; do not print credentials, mutate the normal application database, or silently substitute SQLite. Missing required PostgreSQL evidence is BLOCKED.
6. After the authorized source commit, require a clean checkout and the expected SHA. Execute the active tracked reproduction verifier into a fresh external candidate directory. Gate 3 requires two SQLite executions sharing one fresh database plus one PostgreSQL execution.
7. Independently validate semantic payloads, physical artifact hashes, source hashes, distinct execution UUIDs, and Git provenance (`available is True`, `dirty is False`, exact SHA). Hash agreement alone is insufficient.
8. Preserve prior artifacts and review verdicts. A failed new attempt cannot inherit an old PASS. Link candidate evidence and record PASS, FAIL, BLOCKED, or NOT_RUN explicitly.
9. Send one compact review packet. Only the independent reviewer/parent can accept the source. Close governance after acceptance; preserve both source and checkpoint identities.

Output: candidate SHA, affected invariants, exact commands/results, artifact/source checks, service evidence, review link, limitations, next action. Never claim a test or reproduction that was not run.
