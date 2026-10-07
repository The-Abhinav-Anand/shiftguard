# Gate 7 public-regression candidate contract

The versioned matrix at `tests/agent/fixtures/gate7_adversarial_matrix.json` is classified `PUBLIC_REGRESSION`. It is a permanent offline containment suite, not a held-out model-quality benchmark. Its scripted provider responses do not estimate live-model accuracy, completion quality, routing quality, or scientific performance.

Each matrix execution uses the retained `AgentController`, `ToolRegistry`, registered handlers, Python-owned renderer, and durable request records. SQLite cases use a newly created migrated database and published synthetic reports. Five authority cases also target the existing `SHIFTGUARD_TEST_POSTGRES_URL` fixture. The campaign reads no `.env`, accesses no final labels, performs no experiment scoring, and makes no paid or live provider request.

Execution authority comes from the entire immutable human command, using a closed command grammar. Examples are `Run bank-baseline`, `Run bank-stress`, `Run bank-outage-50`, or `Run bank-baseline and bank-outage-50 then compare the results`. Existing `Run the baseline`, `Run bank baseline`, and `Run the flagship stress suite` aliases are supported. Unsupported, quoted, hypothetical, negated or appended commands grant no execution permission. Each grant names its queue preset; a model cannot substitute another resource. The registry rejects missing grants before handler dispatch, handlers reject ungranted direct calls, and the fenced admission transaction independently derives permission from the persisted human prompt. Read/compare requests grant no execution permission. The original quoted-run row now injects a real run decision on both SQLite and PostgreSQL.

Separate execution-authority tests prove accepted-job lost-response replay keeps one request, job and nonce, with no repeated provider call or admission. This is distinct from the matrix's read-only response replay. The summary oracle checks the exact persisted claim set; negative renderer mutations must fail the actual campaign assertion.

Rejected tool names and invalid schemas must not reach handlers. Evidence authorization is checked inside the registered read handler, so unauthorized evidence cases assert the expected single guard-handler entry and prove that no publication or experiment row was queried. Every rejected or read-only case also compares the session's job count and artifact tree before and after. Expiry cases require no job admission, no handler dispatch, no artifact change, and no completed response. Positive controls require exact persisted claim values, identifiers, method/budget binding, and the renderer's single-seed disclaimer.

Run one attempt with:

```powershell
& .\.venv\Scripts\python.exe -B scripts/check_gate7_candidate.py
```

The checker creates a unique directory under `../verification/gate7-candidate-campaign/` and writes `junit.xml`, `pytest.log`, exact case-ID accounting in `report.json` and `report.md`, `source-binding.json`, and `protected-files.json`. It uses a new pytest `--basetemp` for that attempt, preserves earlier attempts, and redacts database URLs and secret-shaped error text. A second invocation is a second evidence attempt; reports never inherit a prior result.

`OFFLINE_REGRESSION_PASS` means only that the scripted regression run and required source comparisons completed. Missing PostgreSQL proof, skipped cases, incomplete ID accounting, source drift, or a protected-file mismatch yields `BLOCKED`; test failures yield `FAIL`. This checker cannot set a live-provider PASS, accept Gate 6, accept Gate 7, or create a source commit. Gate 6 and Gate 7 remain pending until the parent records exact-source evidence and the appropriate acceptance checkpoint.
