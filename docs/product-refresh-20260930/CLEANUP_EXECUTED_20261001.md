# Product cleanup execution and follow-up — 1–2 October 2026

## Final disposition

The refreshed inventory has **189 exact paths**. At final reconciliation, all 189 inventory paths are absent: **187 files were removed** and two frontend bundle paths were already absent before removal.

| Removal phase | Files removed | Bytes |
|---|---:|---:|
| Initial cleanup: source-owned bytecode, placeholders, archived wheel/sdist copies | 167 | 2,915,803 |
| Root duplicate migration files (`alembic/env.py`, revisions 0001–0008) | 9 | 16,938 |
| Orphan test bytecode archived, then removed | 8 | 60,917 |
| Remaining present inventoried frontend build/cache files | 3 | 24,271 |
| **Total** | **187** | **3,017,929** |

Only exact inventoried files were removed; no directories, application implementation source, test source, or canonical migration source was removed. The eight orphan `.pyc` files were archived byte-for-byte with SHA-256 values before deletion. The nine root migration copies were byte-identical to their packaged canonical owners before deletion. Both `alembic.ini` files and canonical revisions 0001–0010 remain. The uninventoried root revision 0009 remained absent.

The two paths already absent at initial cleanup were `frontend/dist/assets/index-Dl6Az4Ad.js` and `frontend/dist/assets/Plot-Zn5Cffy3.js`; they remained absent and were recorded separately, not counted as removals.

## Frontend cache disposition

Removed only the three currently present inventory targets: `frontend/dist/assets/index-B7552YZ9.css`, `frontend/dist/index.html`, and `frontend/tsconfig.tsbuildinfo`. Refreshed byte counts and SHA-256 values, exact path containment, reference scan, and compatibility notes are in `frontend-cache-predelete-ledger.csv`.

The scan found the same CSS basename in `shiftguard/static/index.html`, whose URL is served from the separate parent-managed `shiftguard/static/` tree; that served file was not a deletion target. No Node process named `frontend/dist`. `npm run build` regenerates TypeScript and Vite output before `copy-static`, and the Docker frontend stage runs that build before copying `dist`. Current previews use external isolated Vite output.

Two current JS files in `frontend/dist` were newer and absent from the inventory, so they were left untouched: `index-rROXHmJg.js` (296,548 bytes) and `Plot-ClZDDUfx.js` (1,218,352 bytes). Their hashes match the before-removal snapshot. No current parent-managed served asset was revalidated as part of this cleanup.

## Verification and protected state

- The corrected direct migration probe binds Python `False` for `cancel_requested`. Post-removal, fresh-to-head and 0005-to-head-with-preserved-rows passed on SQLite and PostgreSQL 16. Its uniquely named PostgreSQL schemas were dropped.
- Focused migration tests passed (**4 passed**); pytest collected **505 source-backed tests** before and after orphan bytecode removal.
- The archived wheel still contains all 10 checked canonical migration resources byte-for-byte.
- All 51 frontend source/config/package/test files in the pre-cache snapshot retained their hashes. Both uninventoried `frontend/dist` JS files also retained their hashes.
- Comparing the earlier 92-file protected-source snapshot with current files found 89 matches and three differences, all outside this cleanup’s exact removal list: `.agent/gates.json`, `.agent/ownership.json`, and `tests/agent/test_luna_g6_preflight.py`. Their current hashes are recorded; this cleanup did not write those paths. No canonical migration or frontend-source hash mismatch was found in its respective comparison.
- The initial cleanup-period static snapshot covered four served files with zero hash mismatches. That snapshot is historical to the initial cleanup period only. Parent owns current served static assets; they were outside this follow-up. The final staged-path count is **0**.

The earlier PostgreSQL probe failure was caused by the helper’s SQL integer literal `cancel_requested=0`. The corrected probe binds Python `False`; no canonical migration or backend implementation change was needed. The original failed log, initial report, and previous final ledger are preserved in the evidence directory. This cleanup issued no writes to `.agent`, test source, or historical proof; this report is the only in-checkout documentation file updated by this cleanup.

## Build-copy archive

The local wheel (643,632 bytes; SHA-256 `62412ebce9a0e8e7acbb0dd2d2252a452d8c8c79de76dee83d0fe663fcfe79d9`) and sdist (188,512 bytes; SHA-256 `b634b3bc8ca05f96efcc50e77474462061e55ffe25c4d948c464bf1fb70540c4`) were archived byte-for-byte before their local copies were removed. Accepted proof files were not moved or deleted. `dist/.gitignore` remains.

## Scope and workspace state

Frontend implementation and integrated frontend review are outside this cleanup scope; other workers own those changes and reports. No historical Markdown proof was moved or deleted. HEAD remains `83037b0f02eef62203c3f565a063d824af2722d7` on `implementation/gate-0`. No changes were staged or committed; no reset, clean, deployment, or provider call was made.

## Evidence

Evidence, refreshed ledgers, hashes, and test logs are under:

`C:\Users\Abhinav Anand\Downloads\nvidia\verification\product-execution-20261001\frontend-cleanup-major-01\luna-cleanup`

Key records: `inventory-dispositions-final.csv`, `deletion-results-complete.csv`, `final-inventory-verification.json`, `frontend-cache-predelete-ledger.csv`, `frontend-cache-deletion-results.csv`, `unlisted-frontend-build-files-after.json`, `protected-hash-deltas-since-prior-snapshot.csv`, `protected-source-hashes-current-after-cache-removal.json`, `direct-migration-matrix-postdelete.log`, `sqlite-migration-tests-postfollowup.log`, `orphan-bytecode-postdelete-proof.json`, and `postcleanup-verification.json`.
