# Autopilot log

## 2026-10-15 (setup)
- Autopilot configured: runs every 5 hours via the desktop scheduled task `shiftguard-autopilot`. Runbook: `.agent/AUTOPILOT.md`. Owner actions: `.agent/OWNER_ACTIONS.md`.
- State: commits 9e39afd..82e2812 on implementation/gate-0. Linux image built; local stack restart, second-owner and secret checks pass. Nothing pushed.
- Next: queue item 1 (Caddy HTTPS service and bootstrap-vm.sh).

## 2026-10-15 (run 1, scheduled)
Done (all on implementation/gate-0, not pushed):
- `7d84ae9` Queue 1, hosting scaffold: `caddy:2` HTTPS service + `deploy/Caddyfile`, `deploy/bootstrap-vm.sh` (Ubuntu 22.04/24.04, amd64/arm64), `.gitattributes` keeps `*.sh` LF, `deploy/.env` in `.dockerignore`. Verified: `test_hosted_release_contract.py` 16 passed (3 new); `caddy validate` with and without a domain (caddy@sha256:685ae3d7…); bootstrap `bash -n` + stubbed two-run test in WSL (env files mode 600, password absent from output, second run keeps env files); in-image UCI download produced the frozen clean digest 0e685060… and a manifest that passes readiness. Not verified: Caddy proxying and certificate issuance on a real VM.
- `4f3f2cc` Queue 2, public face: README rewrite, `docs/README.md` (engineering-log index), `docs/ADAPTING.md`, `CITATION.cff`, `CONTRIBUTING.md`, issue templates, `THIRD_PARTY_NOTICES.md` audit. Verified: quickstart from a fresh clone (`verification/quickstart-20261015T073708Z/`): setup exit 0 (777 s, mostly a slow package download), readiness ready, UI served, probe PASS.
- `8d94d07` Queue 3, video and screenshots: `docs/submission/media/shiftguard-demo.webm` (126.88 s, 1280x800, 8.75 MB, sha256 4f05fcf7…12ca, captions, scripted assistant badged "Recorded with test data"), 8 PNGs. Recording spec passed; typecheck clean; no paid calls. Evidence attempts: `verification/demo-record-*`.
- `71b8827` Queue 4, submission text: sponsor feedback, judge guide with measured times (local probe: baseline 2 s, outage-50 4 s, stress 89 s, all PASS), release checklist statuses, `DEVPOST_FORM.md`.
- Queue 5: history secret scan PASS (37 commits, 765 blobs; 0 forbidden files; 0 hits for the Nebius key or DuckDNS token; DB-URL pattern hits are test fixtures; the local test container's password is the default `postgres`, not a secret).

Blocked:
- GitHub publish: `gh repo create … --public` + push was denied by Claude Code's auto-mode classifier ("Create Public Surface"). Not retried or worked around. Added OWNER_ACTIONS item 7 (run 4 commands, or allow it). No repository or remote was created.
- Deploy (queue 6): no VM IP yet (OWNER_ACTIONS item 2). Live check waits for the VM.
- Video upload: ready for the owner (item 5).

Paid model calls this run: 0. Retained WSL dockerd was started for the Caddy/download checks and stopped afterwards.

Next: once published, set repo topics/homepage; once a VM IP is recorded, repoint DuckDNS, run bootstrap over SSH, hosted probe, restart/second-owner checks, secret scan, live check (≤9 calls). Fallback decision for no VM is due 26 Oct (queue 7).

## 2026-10-15 16:45 IST (interactive session, deploy)
- Repo published: https://github.com/The-Abhinav-Anand/shiftguard (main = implementation/gate-0). History scan before the push: 38 commits, 0 hits for the Nebius key or DuckDNS token, no .env/db files.
- VM: Oracle E2.1.Micro (Ampere out of capacity in Mumbai), 130.210.3.156, Ubuntu 24.04 x86_64. Docker, swap and firewall via `deploy/oracle-cloud-init.sh` over SSH. DuckDNS repointed.
- Image built locally from e249b72 and uploaded resumably (two resets; 3 corrupted 8 MB chunks re-sent; SHA-256 match). Bootstrap run with SHIFTGUARD_SKIP_BUILD=1 and --dataset-from (dataset hash 0e685060… verified).
- Live: https://shiftguard.duckdns.org, Let's Encrypt certificate valid to 2027-01-13. Hosted probe PASS for baseline (12 s), outage-50 (15 s) and stress (325 s); experiment IDs identical to the local runs.
- NEBIUS_API_KEY copied over SSH stdin (judge.env mode 600, never displayed); both assistants enabled.
- Live check: general chat PASS (1 call, 199 tokens). Results assistant FAILED (6 turns, 6 calls, hit the turn limit after a wrong-argument tool call; no fabricated numbers). Ledger after: 7/50 calls, 28,657/100,000 tokens, not halted.
- Hosted secret scan: 0 key, password or DB-URL hits in the api, worker, postgres and caddy logs; 0 in served assets.
- Evidence: verification/gate10-hosted-20261015T100844Z
- Next: runbook queue item 0 (Results assistant reliability), then 0b.

## 2026-10-16 (interactive session, Batch R and H in progress)
- Plan: `docs/superpowers/plans/2026-10-15-results-assistant-and-remaining-gates.md`.
- Results-assistant root causes found from the live DB:
  - (A) free-form prompts have no selection authority, so the model wandered;
  - (B) a full 400-condition read of 258 KB exceeded the provider's 64 KB transcript bound (corrected per review: the 16 KB limit applies only to responses).
- Batch R (uncommitted, under Opus xhigh review):
  - Backend: provider-copy projection only for provider-rejectable tool messages; not-selected short-circuit (COMPLETED with guidance.code EXPERIMENT_NOT_SELECTED, one provider turn); prompt procedure. Full tests/agent 587 passed, 0 failed, 0 skipped (SQLite + PostgreSQL). Gate 7 matrix and scripts/run_live_acceptance.py untouched (scripts/check_hosted_live.py was changed); a Sonnet worker's attempt to edit the Gate 7 fixture was blocked and the design changed instead.
  - Frontend: "Ask about this result" insert-only buttons. Full e2e 72 passed, 3 skipped.
- Batch H:
  - VM restart check PASS, correcting the per-job publication rule (`verification/gate10-hosted-restart/vm-restart-check.corrected.json`).
  - VM second-owner refusal PASS.
  - Nightly backups installed (03:15 UTC, keep 7; first set verified, dump restorable).
  - Docs updated with the live URL and hosted timings (uncommitted).
- Next: act on the review, commit, push, rebuild and redeploy the image, live-check both question types within the cap, then the Results docs (questions per day).

## 2026-10-16 (corrections to earlier entries, per Opus delta review R4)
- "first set verified, dump restorable" (entry above) referred to a set made by the pre-review backup script. Evidence was not saved under `../verification/`, so treat it as unverified. Checklist row 6 is PARTIAL until the reviewed script runs on the VM and its evidence is saved.
- "Hosted logs and bundle: secret-free": container logs yes, but the bundle scan covered only the entry chunk. Row 10 is PARTIAL.
- The short-circuit described above has since changed:
  - never for Run commands;
  - FAILED or CANCELLED outcomes keep their status, with guidance attached;
  - the id comes only from the user's prompt;
  - EXPERIMENT_NOT_PUBLISHED for an exact command naming an unpublished id;
  - a 16 KB per-message trigger restored for the model copy (R1 cost).

## 2026-10-16 18:18–19:30 IST (autopilot run 2, scheduled)
- Concurrency guard: the newest uncommitted change was 7 h old, so I took over the interactive Batch R work as an in-progress batch.
- Opus xhigh review of the whole uncommitted batch: CORRECTIONS_REQUIRED (1 major, 5 minor).
  - Major: the new token-bound test asserted `< 20,000`, but the fixed overhead alone is 18,136. It had failed on both backends (SQLite 1 failed / 427 passed; PG 1 failed / 606 passed). So the earlier "587 passed" no longer held for the current tree.
  - Minor: the panel hid the failure summary for FAILED/CANCELLED responses with guidance; the projection audit note; a condition id could be named in guidance; checklist row 6 had a cert date without evidence; backup.sh lacked chmod and a dump check.
- Fixes (Sonnet workers on disjoint files, then integrated):
  - The test asserts relative to the base bound.
  - The id after "experiment" wins; ambiguous prompts give no id.
  - The panel keeps the failure summary, with the notice labelled "How to ask:".
  - backup.sh gains `chmod 0700` and `pg_restore --list` before the set is kept. The worker left a literal `\n` that would have failed every backup; I caught and fixed it.
  - Cert evidence: `verification/gate10-hosted-cert-20261016/certificate.txt`.
- Opus xhigh delta review: ACCEPT. Nits not done yet:
  - (a) the regex does not accept "experiment id X";
  - (b) FAILED/CANCELLED final answers have no title, so the panel shows an empty h3;
  - (c) the test margin comment is loose.
- Verified on the final tree (evidence in `verification/autopilot-20261016-run2/`):
  - tests/agent SQLite: 431 passed, 0 failed (124 PG-only skips).
  - tests/agent PostgreSQL: 610 passed, 0 failed, 0 skipped.
  - typecheck clean; the frontend rebuild reproduced the committed bundle byte-for-byte before the panel fix.
  - Full Playwright: 76 passed, 1 failed, 3 skipped. The failure was F08 (`/about` scene chunk under reduced motion), which the panel change does not touch; a rerun of the spec ×3 gave 27/27, so it is flaky. Not fixed.
- Pre-push secret scan of the diff and new files: 0 hits for the API key, base URL or DuckDNS token; no DB URLs with passwords; no forbidden files. The only match was the public model name.
- Paid calls so far this run: 0.
- Commit and push: `55e75c4` pushed to main (`b37b019..55e75c4`).
- Image: built from `git archive 55e75c4` on the WSL daemon (legacy builder, `--network host` because this daemon has no container networking; the first attempt failed at `npm ci` without it). Result `shiftguard:judge` `sha256:e10541032e38…`, amd64. The bundle in the image has the same content-hashed asset names as the commit; `index.html` differs only in trailing whitespace on one line.
- Upload: `shiftguard-judge-55e75c4.tar.gz` (180,482,975 bytes, sha256 `69999977…e4c4`) sent to the VM as `/tmp/sg-55e75c4.tar.gz` in 8 MB chunks, each hash-checked. Final SHA-256 match, 0 corrupted chunks.
- BLOCKED: the production deploy step (pull, backup, `docker load`, `up -d`) was denied by Claude Code's auto-mode classifier ("Production Deploy"). Per the runbook it was not retried or routed around, and later reads of the VM state were blocked too. OWNER_ACTIONS item 8 now lists the exact commands, or the alternative of allowing autopilot deploys. The live site is still the 15 Oct image (e249b72) and healthy; ledger 0/50 calls today.
- Not done because of the block: live checks (Summarize and Compare), the questions-per-day figure, the reviewed backup on the VM (row 6), and the full static scan in the image (row 10).
- Paid calls this run: 0.
- Next: once item 8 is done, verify readiness and the image ID on the VM, then run the live checks (≤17 calls), the hosted Playwright smoke and the docs figures. Code follow-ups from the delta review: accept "experiment id X"; give FAILED/CANCELLED final answers a title; tighten the test margin comment.

## 2026-10-16 20:10–21:15 IST (autopilot run 3, scheduled)
- Orientation: the tree was clean, so the concurrency guard did not apply. Live readiness is `ready` on the 15 Oct image (e249b72). OWNER_ACTIONS item 8 (redeploy) has no status yet, so the deploy and its live checks stay blocked. They were not retried, per the runbook. The keep-awake tool is not available in this session; noted, and the run went ahead.
- Done: the three delta-review follow-ups from run 2 (Sonnet worker; Opus xhigh review).
  - "experiment id X", "experiment_id=X", "experiment-id: X" and the glued "id<hex>" now name the experiment id in typed guidance. "identifier", "idle" and "ids" are not treated as "id".
  - The panel renders the final-answer title (and the disclaimer) only when present. FAILED/CANCELLED answers have neither. `agent.ts` types are now optional for these fields. The e2e FAILED/CANCELLED payloads match the backend (no title) and assert that there is no `.final-title`.
  - The token-bound test pins the exact growth (2909 bytes) and adds an independent ceiling (14,336).
  - The frontend was rebuilt into `shiftguard/static`, and all 8 hashed chunks were renamed. 7 are byte-identical apart from hash names; the BenchmarkWorkbench chunk differs only by the two guards (checked by the reviewer).
- Opus xhigh review: CORRECTIONS_REQUIRED (1 medium: the margin assert was tautological; 2 low: glued "id<hex>" and an untested untitled path). All three were acted on. Delta review: ACCEPT. This is a model review, not human acceptance.
- Verified (evidence in `verification/autopilot-20261016-run3/`):
  - tests/agent SQLite: 431 passed, 124 skipped (PG-only).
  - Regression file: PostgreSQL 50 passed; SQLite 37 passed, 13 skipped.
  - `npm run typecheck` clean; `npm run build` OK.
  - Playwright agent specs (agent_flow, agent_surface_corrections, results_assistant_suggestions, job_errors, general_chat): 21 passed.
  - The full PostgreSQL tests/agent run and the full Playwright suite were not rerun for this small batch.
- Secret scan of the diff and the bundle: 0 hits.
- Paid calls: 0.
- Note: the image already uploaded to the VM (`/tmp/sg-55e75c4.tar.gz`) does not contain these follow-ups. OWNER_ACTIONS item 8 is still valid as written. The next image rebuild (at the latest for the Gate 11 freeze) carries them.
- Deferred: the hosted Playwright smoke test. It waits for the redeploy so that it tests the judged build. It also needs a spec list that can make no paid calls against the live, provider-enabled server.
- Blocked: OWNER_ACTIONS item 8 (redeploy), and with it the live checks, the questions-per-day figure, checklist rows 6 and 10.
- Next: verify the redeploy once item 8 is done. Then the live checks (≤17 calls), the hosted smoke test, and the docs figures. The F08 flake is still open.

## 2026-10-17 (autopilot run 4, scheduled)
- Orientation: the tree was clean, so the concurrency guard did not apply. Live readiness is `ready`, but the site still serves the 15 Oct bundle (`index-oNasIWcL.js`), not 55e75c4 or f98c1ce. OWNER_ACTIONS item 8 (redeploy) has no status yet, so the deploy and its live checks stay blocked; not retried. The keep-awake tool is not available in this session.
- Done: the F08 flake is fixed (commit `53020b0`).
  - Root cause: `scriptAssets()` is cumulative per page. The reduced-motion toggle inside a live desktop /about document (real fine pointer) legitimately starts the scene import (`SceneFrame.tsx`), and the later coarse-pointer assertion saw it. This is a test race, not an app bug; the failure snapshot confirms the final document did not request the scene.
  - Fix: the coarse-pointer visit starts from `about:blank` and checks only its own scripts. It now also waits for "View 3D illustration" and requires a non-empty script slice. After the toggle, the test asserts no canvas and the reduced-motion caption.
- Done: Batch H prep, a hosted smoke config with no paid calls (`frontend/playwright.hosted.config.ts`, same commit).
  - It selects 64 exact titles in 15 files. Excluded: "[real agent]", 9 luna3 tests that use real POSTs, bank-stress, normal_product and 2 suggestion tests. The run creates 3 live Bank jobs.
  - The URL guard accepts only a bare https origin and rejects loopback and credentials.
  - Hosted-only backstops: `fixtures.ts` aborts and fails on any non-GET to `agent/requests*` or `chat/messages`. A globalSetup tripwire (`scripts/hosted-budget-tripwire.ts`) fails the run if the live ordinary budget (calls or tokens) changes. It refuses `verification/gate5` and a reused folder.
  - Rules: no `--retries` or `--repeat-each`; exactly 64 tests.
- Review: Opus xhigh returned ACCEPT with 2 medium findings (no backstop; whole-file allowlists) and minor ones. All were acted on. Delta review: ACCEPT, with 1 minor and 3 nits. I applied the control character in the header, the trailing-slash regex, and enforcing the gate5 folder rule; the trailing-dot `localhost.` and file/title-anchored grep nits were left. These are model reviews, not human acceptance.
- Verified (evidence in `verification/autopilot-20261017-run4/`):
  - `npm run typecheck` clean.
  - F08 with `--repeat-each 10`: 10/10, on both the first and the strengthened version.
  - test_product_refresh: 9/9 (twice).
  - test_job_errors (local, fixtures.ts consumer): 3/3 (twice).
  - Hosted `--list`: 64 tests in 15 files.
  - The reviewer notes the pre-fix spec also passed 3/3 when rerun alone, so the fix rests on the code reading and the snapshot, not on the 10/10.
  - The hosted guard's page-mock precedence was checked from the Playwright source, not by a run.
- Secret scan of the batch: 0 hits. Paid calls: 0.
- Not run: the hosted smoke itself. It waits for the redeploy (item 8) so that it tests the judged build. The command for that run:
  `SG_E2E_BASE_URL=https://shiftguard.duckdns.org SG_GATE5_ATTEMPT_DIR=../verification/gate10-hosted-smoke-<date> npx playwright test -c playwright.hosted.config.ts`
- Blocked: OWNER_ACTIONS item 8 (redeploy), and with it the live checks, the questions-per-day figure, the hosted smoke, and checklist rows 6 and 10.
- Next: after item 8, verify the image on the VM, then the live checks (≤17 calls) and the hosted smoke. Otherwise start Batch S8 preparation: record the authorization and run the resource preflight on fabricated rows.

## 2026-10-17 (autopilot run 5, scheduled)
- Orientation: tree clean; concurrency guard not applied. Live readiness `ready`, still on the 15 Oct bundle (`index-oNasIWcL.js`). Certificate valid to 2027-01-13. OWNER_ACTIONS item 8 (redeploy) has no status, so the deploy, live checks, hosted smoke and checklist rows 6/10 stay blocked; not retried. The keep-awake tool is not available in this session.
- Done: Batch S8 prep.
  - Authorization record (new file, outside git): `../research/gate8-20261009/AUTHORIZATION-20261017-bank-development-repeats.md`.
    - It says plainly that this is the agent's decision under the owner's general delegation, not an owner sign-off and not scientific approval.
    - While SCI-03 is unresolved, the primary estimate is expected to be MissingEvidence by construction. Relabelling qualification to obtain a number is forbidden.
    - The per-coordinate store is evaluator-private and label-equivalent: local `var/` only, never git, verification, the VM or backups.
    - Five preconditions, including an owner veto (OWNER_ACTIONS item 9; no real coordinate before 20 Oct).
  - R1 resource preflight: `scripts/gate8_resource_preflight.py` (sha256 `3d2d1155…7e35`). It uses fabricated rows only (binding `synthetic_fabricated`) and writes no label-derived value.
    - Evidence: `../verification/gate8-preflight-20261017b/` (the first-pass folder `gate8-preflight-20261017` is kept as history).
    - 41,188 rows, one full-grid coordinate (400 conditions):
      | Fixture | Evaluation groups | Execute | Peak working set (execute / with serialization) | Artifact | Estimate, 5×10 sequential |
      |---|---|---|---|---|---|
      | default 500-profile | 444 | 64.1 s | 255.5 / 377.8 MiB | 74.6 MB | 0.90 h |
      | high-cardinality `row` | 8,005 | 117.8 s | 379.3 / 534.5 MiB | 90.4 MB | 1.64 h |
    - Per-group scoring takes 2.6% and 22.1% (26 s) of execute time. The 8,005-group case is near the ceiling for an 8,238-row evaluation set. R1's optimisation rule is not triggered, so scoring is not optimised.
    - Artifact: 58 copies of a 1.275 MB plan-owned context per coordinate. The store must reference plan-owned data by digest; the floor is about 0.35 / 2.2 MB per coordinate (precondition 4).
- Review: Opus xhigh returned CORRECTIONS_REQUIRED (2 major: the MissingEvidence expectation and fixture representativeness; 5 medium; minor ones and nits). All were acted on, by a script rewrite, a rerun and a record rewrite. The delta review returned CORRECTIONS_REQUIRED with text-only items (D1 store-digest scope, D2 veto as a checklist precondition, D3 the optimisation decision); all were applied. These are model reviews, not human acceptance.
  - Deferred to the next script edit, because the change would alter the evidence hash: D4 (reword the pandas-import environment note; that cost is real wall time in both passes) and D5 nits (`--profiles 0`/`0500` validation, use BANK_FEATURES, a single `git status` call).
- Verified: `tests/repeats_adapter` 49 passed, 0 failed (first pass; the rewrite changed nothing it imports). The script hash matches all four evidence files. The default fixture reproduces the artifact byte-for-byte across both passes.
- Secret scan of the batch (3 secret values plus DB-URL pattern, compared in memory): 0 hits. Paid calls: 0.
- Blocked: OWNER_ACTIONS item 8 (redeploy). New owner item 9 (Gate 8 veto, no action needed unless he objects); notified once.
- Next: S8 precondition 2 (adapter accepts the verified Bank binding, with a typed SCI-03 reason code and the validator reconciled), then precondition 4 (digest-referencing restartable store), then the frozen run manifest. Real coordinates no earlier than 20 Oct. After item 8: verify the image on the VM, the live checks (≤17 calls) and the hosted smoke.

## 2026-10-17 10:10–~12:30 IST (autopilot run 6, scheduled)
- Orientation: the tree was clean, so the concurrency guard did not apply. Live readiness was `ready`, still on the 15 Oct bundle (`index-oNasIWcL.js`). OWNER_ACTIONS items 8 (redeploy) and 9 (Gate 8 veto) had no status, so item 8 stays blocked and was not retried. The keep-awake tool is not available in this session.
- Done (verified, NOT committed): **Gate 8 precondition 2**, the adapter accepts the verified Bank development binding. Sonnet worker; Opus xhigh reviewer.
  - Gate: `planning.require_authorized_source` admits synthetic fixtures, or `development_exposed` with the verified Bank dataset, release, raw and clean digests (from `datasets/bank.py`). The clean rows are re-hashed.
  - Refusals: everything else is `SYNTHETIC_ONLY`. A synthetic binding carrying any verified Bank identity, or rows that hash to the verified clean digest, is `SYNTHETIC_MISLABEL`.
  - Qualification: Bank stays `unknown_authority`, with the typed reason `sci03_authority_unresolved` on every completed condition and scored cell. The validator enforces placement and exact cell reasons (failed-side codes on unscored cells). Any qualified record on a Bank plan raises `QUALIFICATION_UPGRADE`, in both `_collect` and the inventory.
  - Identity: Bank uses `execution_mode="bank_development"` and its own claim scope. Synthetic plan digests and repeat IDs are unchanged (pinned; the reviewer cross-checked them against a HEAD export). The Bank seed map equals the golden digest.
  - Downstream: store, completion, aggregation and uncertainty stay synthetic-only. `aggregate_primary` on a Bank plan returns MissingEvidence or raises.
  - Inventory: fallback slots are now counted regardless of qualification.
  - No real Bank data was loaded; fabricated rows only. Engine owners are unchanged.
- Review: Opus xhigh returned CORRECTIONS_REQUIRED (2 major, 4 medium, 2 minor, plus nits).
  - Major: the downstream synthetic gate had leaked through `plan_repeats`; a synthetic label could carry the verified Bank identity (pre-existing hole).
  - Medium: module-scoped monkeypatch leak (order-dependent failure reproduced); vacuous aggregate assertion; fallback slots dropped for `unknown_authority`; spec `execution_mode` and docstrings said synthetic.
  - All were acted on. Delta review: ACCEPT, with 2 minor and 6 nits, all applied. Delta-3: ACCEPT; I applied the docstring nit and left one test nit (a synthetic-path case for the exact-field check). These are model reviews, not human acceptance.
- Verified: `tests/repeats` + `tests/repeats_adapter`: 365 passed, 0 failed, 0 skipped (my run; log in `verification/autopilot-20261017-run6/pytest-repeats.txt`). The reviewer's reverse-order and isolation runs all passed.
- Secret scan of the diff and the new file (4 secret values plus DB-URL pattern, in memory): 0 hits. Paid calls: 0.
- BLOCKED: `git commit` was denied by Claude Code's auto-mode classifier ("Modify Shared Resources"). Not retried. New OWNER_ACTIONS item 10 has the exact commands; the message is in `verification/autopilot-20261017-run6/COMMIT_MESSAGE.txt`. The 10 uncommitted files are this run's reviewed batch, not an abandoned interactive session. Later runs should not re-review them or retry the commit until item 10 has a status. They may work on disjoint files.
- Still blocked: item 8 (redeploy), and with it the live checks, the hosted smoke test, and checklist rows 6 and 10.
- Next: precondition 4, the restartable digest-referencing store. It needs files in `shiftguard/repeats/` (a new store module), so it waits for item 10 to avoid mixing batches. Precondition 3 (frozen run manifest) comes after that. Real coordinates no earlier than 20 Oct.

## 2026-10-17 15:10–15:25 IST (autopilot run 7, scheduled)
- Orientation: the only uncommitted files are run 6's reviewed Gate 8 adapter batch (newest change 11:52 IST, 3.3 h old), which run 6 asked later runs not to re-review or re-commit until OWNER_ACTIONS item 10 has a status. It has none, so the commit was not retried. Item 8 (redeploy) also has no status; not retried. Item 9 (Gate 8 veto) has no status. The keep-awake tool is not available in this session.
- Read-only checks: readiness `ready` (database connected, migration head, storage writable, dataset verified); live bundle still the 15 Oct one (`index-oNasIWcL.js`); certificate valid to 2027-01-13 09:07 GMT; ledger 2026-10-17: 0/50 calls, 0/100,000 tokens, not halted.
- Done: the Gate 8 authorization record (outside git) now says precondition 2 is implemented, tested and reviewed but uncommitted, and stays unchecked until item 10 lands.
- Not started: precondition 4 (the store) shares `shiftguard/repeats/` with the uncommitted batch, so it waits for item 10. Everything on the deploy path (live checks, questions-per-day figure, hosted smoke, checklist rows 6/10, the video re-record) waits for item 8. No other queue item was unblocked and worth starting.
- Tests: none run (no code changed). Review: none (no commit or deploy). Paid calls: 0.
- Tried to notify the owner once about items 8 and 10 (item 10 had not been notified in run 6); the push was not delivered (Remote Control inactive). Not retried.
- Next: when item 10 says committed (or "commit: allowed"), start precondition 4; when item 8 says redeployed (or "deploy: allowed"), verify the image on the VM, then the live checks (≤17 calls) and the hosted smoke. Gate 11 freeze is 27–28 Oct, so item 8 is now on the critical path for the video.

## 2026-10-17 (interactive session with the owner present)
- OWNER_ACTIONS item 10 DONE: Gate 8 precondition 2 committed as `f71c42d` and pushed. It used run 6's message and evidence (365 passed; Opus ACCEPT after corrections).
- Item 8 (redeploy) attempted interactively and BLOCKED BY NETWORK. This PC's current connection (public IP 117.240.x) blocks outgoing TCP 22 (github.com:22 also times out; 443 works). The VM is healthy: readiness `ready`, ports 80/443 open. It still runs the 15 Oct image.
- The deploy runs as soon as the PC is on a network that allows port 22, in an interactive session (the owner authorized deploys in chat). Unattended runs must not deploy until the owner adds a permission rule; never route around the classifier.
- Next for unattended runs: Gate 8 precondition 4 (digest-referencing restartable store), now unblocked because item 10 landed. Then precondition 3 (the frozen run manifest).

## 2026-10-17 20:10–21:40 IST (autopilot run 8, scheduled)
- Orientation: the tree was clean, so the concurrency guard did not apply. Live readiness `ready`, still on the 15 Oct bundle (`index-oNasIWcL.js`). Certificate valid to 2027-01-13. The keep-awake tool is not available in this session.
  - Port 22 to the VM is reachable again from this PC. A read-only SSH check found `/tmp/sg-55e75c4.tar.gz` intact (SHA-256 matches) and the VM still on `e249b72`.
  - Unattended runs still must not deploy, so OWNER_ACTIONS item 8 now asks the owner to open an interactive session and say "deploy now". Note that the uploaded image lacks `f98c1ce`.
- Done: **Gate 8 precondition 4**, the restartable digest-referencing development store. Sonnet worker; Opus xhigh reviewer.
  - New files:
    - `shiftguard/repeats/development_store.py`
    - `tests/repeats_adapter/test_development_store.py` (52 tests)
    - `scripts/gate8_store_preflight.py`
    - No existing file changed; `models.py`, the synthetic store and the engine owners are untouched.
  - Plan-owned data is rebuilt from the plan on reopen and bound by `plan_owned_digest` in the envelope. It covers each context's `evaluation_ids`/`group_map`/dataset fields, the cell `group_ids`/`n_by_group`, the repeat id and the seed map.
  - Stored per coordinate:
    - the acquisition order, as pool positions;
    - per-context masks and predictor id;
    - conditions;
    - compact cells with sparse sums (sign of zero preserved);
    - validated-pair digests.
  - Encode checks plan-owned equality, then validates and self-decodes with a bit-exact comparison. `load` and `inventory()` deep-verify every coordinate; any failure is `CORRUPT_COMPLETION` and is never counted as completed. A light-read conflict is deep-checked before it is reported.
  - Atomic publication, as in the synthetic store; the marker is published by an exclusive link too.
  - Evaluator-private guard:
    - development stores must sit strictly inside `var/gate8-private/`;
    - no `verification` path component is allowed;
    - junctions and symlinks in the root or its subdirectories are refused;
    - the repr hides the sums.
  - Record versions: `gate8-dev-repeat-store-v1` and `gate8-dev-coordinate-v1` (compact cell/context/pair v1).
- Measurement (fabricated rows, 41,188, synthetic binding; `../verification/gate8-store-preflight-20261017b/`, script sha256 `b5a24fa6…7330`):

  | Fixture | Compact artifact | Full layout | Restart verify | tracemalloc peak | Child peak working set |
  |---|---|---|---|---|---|
  | 500-profile | 371,519 B | 74.6 MB | 3.85 s | 4.6 MiB | 177.8 MiB |
  | high-cardinality `row` | 1,999,222 B | 90.4 MB | 5.03 s | 11.7 MiB | 199.1 MiB |

  The earlier folder `gate8-store-preflight-20261017/` (script `9fb00beb…`) is the superseded pre-digest shape, kept as history.
- Review (Opus xhigh, model reviews, not human acceptance):
  - First review: CORRECTIONS_REQUIRED (2 medium: commit misclassified a deep-corrupt record; rebuilt values not digest-bound; plus minor items and nits). All applied.
  - Delta: CORRECTIONS_REQUIRED (1 minor: a junctioned subdirectory was adopted; 4 nits). All applied.
  - Delta-3: ACCEPT. Two optional nits were deferred: a per-commit layout re-check (TOCTOU window), and allowing only `*.marker` files in staging on adoption. An info item became a precondition note: confirm that no host-level backup covers `var/gate8-private/`.
- Verified: `tests/repeats` + `tests/repeats_adapter` 417 passed, 0 failed (my run; log `../verification/autopilot-20261017-run8/pytest-repeats-final.txt`). The reviewer ran the new file alone and reversed: 52/52 each.
- Secret scan of the batch (4 secret values plus DB-URL and key patterns, in memory): 0 hits. Paid calls: 0.
- Authorization record (outside git): precondition 2 ticked (`f71c42d`), precondition 4 status and the backup check added.
- Next: precondition 3, the frozen run manifest (source commit, dataset hashes, configuration, roles, schedule), committed before any real coordinate. Then a restartable driver that uses `inventory()`. No real coordinate before 20 Oct (precondition 5 veto check). The deploy waits for an interactive session.

## 2026-10-18 00:10–02:00 IST (autopilot run 9, scheduled)
- Orientation: the tree was clean, so the concurrency guard did not apply. Live readiness `ready`, still on the 15 Oct bundle (`index-oNasIWcL.js`). Certificate valid to 2027-01-13 09:07 GMT. No owner-action status changed: item 8 (redeploy) still needs an interactive session; item 9 has no veto. The keep-awake tool is not available.
- Done: **Gate 8 precondition 3 tooling**, the frozen run manifest plus the restartable driver. Sonnet worker; Opus xhigh reviewer.
  - New files:
    - `shiftguard/repeats/run_manifest.py`: schema `gate8-run-manifest-v1`, the development `SourceBinding` builder, git-blob source tree, and verification.
    - `scripts/gate8_freeze_run_manifest.py`
    - `scripts/gate8_run_development.py`: the driver.
    - Tests: `tests/repeats_adapter/test_run_manifest.py` and `test_run_driver.py`.
    - `.gitattributes` gains `docs/research/*.json text eol=lf`.
    - No existing module or engine owner changed.
  - The manifest binds:
    - the source commit and the git blob ids of the run's import closure (`shiftguard/__init__.py`, calibration, datasets, experiments, metrics, missingness, predictors, preprocessing, protocol, repeats, the two gate8 scripts, `pyproject.toml`, `uv.lock`), with an ast closure test;
    - the dataset and lock hashes, spec, seed-plan digest;
    - role digests and counts (no row ids);
    - the ordered 50-coordinate schedule, the plan digest and the store record versions;
    - the declared primary contrast and analysis, and the environment (Python, platform, numpy/scipy/scikit-learn).
  - `protocol_review_sha256` pins `SCIENTIFIC_DECISIONS.md` only. The authorization record's hash is captured as `authorization_sha256_at_freeze` and is digest-bound but not re-verified, because its checkboxes change.
  - Driver safeguards:
    - It requires a clean source scope and a manifest that is tracked and unmodified at HEAD.
    - It runs only on or after 20 Oct (IST). It re-checks the date gate and the owner veto before every coordinate. Item 9 is parsed by its heading; a missing item or Status line, or any non-affirmative Status, means no run.
    - The store root comes only from the manifest. It refuses if any other store exists under `var/gate8-private`, and holds an O_EXCL run lock.
    - It skips byte-verified completions and recorded failures; a failure is never re-run. A prepare failure fails all remaining coordinates of that outer seed. A corrupt completion stops the run. A partial grid is a typed failure.
    - The run log holds no numeric outcome.
  - Refusals: both scripts refuse today with `DATE_GATE`. Neither was run on real data, and no real Bank row was loaded.
- Review (Opus xhigh, model reviews, not human acceptance):
  - First: CORRECTIONS_REQUIRED, 1 high and 4 medium. The high: a `--store-root` override let a recorded failure be re-run. The mediums: the manifest's committed state was not checked; `source_commit` was not tied to the tree and CRLF bytes were hashed; the veto parsing was narrow; the binding pinned volatile inputs. There were also 5 minor items and nits. All applied.
  - Delta: ACCEPT. Five optional nits were deferred:
    - print the fixed reason text with `OWNER_VETO`;
    - refuse the test seams when the real loader is injected;
    - isolate the veto-regex spelling test;
    - guard the real-loader test;
    - operator note: a Windows build change re-freezes, and a preflight store under `var/gate8-private` blocks the run.
- Verified: `tests/repeats` + `tests/repeats_adapter` **580 passed**, 0 failed, 0 skipped. This is my run, 830 s; log `../verification/autopilot-20261018-run9/pytest-repeats-final.txt`. The reviewer ran the two new files: 163 passed.
- Secret scan of the batch (4 secret values plus DB-URL and key patterns, in memory): 0 hits. Paid calls: 0.
- BLOCKED: updating the authorization record outside git was denied by Claude Code's auto-mode classifier ("Instruction Poisoning"). The intended change: tick precondition 4 (`3986fcf`) and add the precondition 3 status. It was not retried. A later wait-loop command was denied the same way. The record still shows precondition 4 unticked; this log is the current status.
- Next:
  - On or after 20 Oct: confirm that no host-level backup covers `var/gate8-private/`, then run the freeze script (it loads real Bank rows for roles only, executes no coordinate), and commit and push the manifest.
  - Only after that commit: run the driver in `--limit` chunks.
  - The deploy (item 8) still waits for an interactive session.

## 2026-10-18 13:38–20:30 IST (autopilot run 10, scheduled)
- Orientation: tree clean; concurrency guard not applied. Live readiness `ready`. No owner-action status changed (item 8 redeploy still needs an interactive session; item 9 no veto). Keep-awake tool not available.
- Gate 8 precondition note checked (read-only): no host-level backup covers `var/gate8-private/`. Downloads is not redirected into OneDrive, there is no File History configuration (fhsvc stopped), and no other backup agent is running. `var/gate8-private` does not exist yet.
- Done: **Gate 9 prerequisite 1 tooling**, a label-blind Adult source manifest builder. Sonnet worker; Opus xhigh reviewer.
  - New files only, no existing file changed:
    - `shiftguard/adult_adapter/source_manifest.py`
    - `scripts/adult_build_source_manifest.py`
    - `tests/adult_adapter/test_source_manifest.py`
  - Schema `adult-source-manifest-v1`. It records:
    - per-file byte size, sha256, physical and record line counts, line endings, and skipped lines (by line number and reason);
    - per-record row id and exact-feature `group_key`;
    - feature-only duplicate groups, train/test overlap groups and test-connected keys.
  - The label field is never decoded, compared or counted. Label bytes enter only the whole-file byte_size/sha256, the field-count check and line-terminator detection. The byte_size label-prevalence side channel is documented, and no feature-region length is computed.
  - `custodian_status: author-built, not custodian-attested`. A `--test` run is an exposure event to record, not custodian evidence.
  - `verify_source_manifest` checks a closed schema with strict types. `verify_against_bytes` requires an exact rebuild and pins `uci-adult-2` to `FROZEN_ADULT_SOURCE` (sha256 and 32,561 records). `connected_group_key_set` requires the rebuild.
- Real run, train only (`data/raw/adult.data`):
  - 32,562 physical lines, 32,561 records, 24 duplicate groups (49 rows).
  - sha256 equals the frozen value.
  - `manifest_sha256=6336aa16…7317`, at `../verification/autopilot-20261018-run10/adult-source-manifest-trainonly-r2.json` (r1 `bf27b82c…` superseded, kept).
- Review (Opus xhigh, model reviews, not human acceptance):
  - First: CORRECTIONS_REQUIRED, 2 medium (verify was not a closed schema; self-digest only, with no byte re-derivation), 6 minor, 3 nits. All applied.
  - Delta: ACCEPT. Deferred to the Gate 9 wiring:
    - 1 minor: enforce an `expected_release` in `connected_group_key_set`, so a non-frozen release name cannot bypass the pin;
    - 4 nits: a typed error for a missing path; `splitlines()` in the cross-check test; a test for a trailing CR on an unterminated last line; restoring `sys.path` in the script-loading test.
- Verified: `tests/adult_adapter` + `tests/unit/test_adult_development_owner.py`: **150 passed**, 0 failed. This is my run; log `../verification/autopilot-20261018-run10/pytest-adult-final.txt`. The reviewer's run of `tests/adult_adapter`: 140 passed.
- Secret scan of the batch (7 secret values plus DB-URL and key patterns, in memory): 0 hits. Paid calls: 0.
- New owner action: item 11, permission to download the official `adult.test`. Downloading a file needs explicit approval, so it was not downloaded. It is optional before 30 Oct.
- Blocked: item 8 (redeploy), and with it the live checks, the hosted smoke test, checklist rows 6/10 and the video re-record. Gate 8 real runs wait for 20 Oct.
- Next:
  - On or after 20 Oct: the Gate 8 freeze script, then commit the manifest, then the driver in `--limit` chunks.
  - Once item 11 is done: a real train+test manifest, then the Gate 9 protocol amendment and its public lock commit.

## 2026-10-19 03:27– IST (autopilot run 11, scheduled)
- Orientation: uncommitted changes to `shiftguard/adult_adapter/source_manifest.py`, its test, and an untracked `docs/research/gate9-adult-protocol-amendment.md` (DRAFT), last modified 18 Oct 20:15–20:18 IST, about 7 hours old. Under the concurrency guard the interactive session was gone, so this run took the work over as an in-progress batch (left by run 10, not logged). Live readiness `ready`, still on the 15 Oct bundle (`index-oNasIWcL.js`). Certificate valid to 2027-01-13 09:07 GMT. No owner-action status changed (item 8 redeploy, item 9 no veto, item 11 no answer). Keep-awake tool not available.
- Done: **Gate 9 deferred items from the 7e878e9 review**, commit `645aace`.
  - `connected_group_key_set` requires the keyword `expected_release`. It accepts only the frozen release (now derived from `FROZEN_ADULT_SOURCE["dataset_id"]`) and requires the manifest release to match, so the frozen pin always runs.
  - Typed `SOURCE_MISSING` and `SOURCE_UNREADABLE`.
  - Docstring and tests for a CR ending an unterminated last line; `splitlines()`; `sys.path` restored; explicit record counts in the fabricated pin.
- Review (Opus xhigh, model reviews, not human acceptance): first CORRECTIONS_REQUIRED (1 minor: the docstring overclaimed for a lone CR after a final LF; 4 nits). All applied. Delta: ACCEPT (1 nit, applied). The reviewer noted that `FROZEN_ADULT_SOURCE` is a mutable module-level dict (owned by `datasets/`, so it was recorded, not changed).
- Verified: `tests/adult_adapter` + `tests/unit/test_adult_development_owner.py` **154 passed**, 0 failed (my run; log `../verification/autopilot-20261019-run11/pytest-adult-final.txt`); after the final nit, `test_source_manifest.py` 79 passed. The reviewer's reruns: 152, then 154.
- Secret scan of the batch (8 values from `.env` and the DuckDNS file, plus DB-URL and key patterns, in memory): 0 secret hits. The only value match was the public subdomain name "shiftguard". Paid calls: 0.
- In progress: an Opus xhigh consistency check of the Gate 9 amendment draft (stays untracked until it is reviewed).
- 2026-10-19 03:45 IST (concurrent earlier scheduled run, started 18 Oct 20:12; it launched the manifest-fix and draft workers, then stalled ~7 h): yielded to run 11 under the concurrency guard. It committed and pushed nothing. Its Opus xhigh review of the draft (model review): CORRECTIONS_REQUIRED, 1 high (all grouping.py citations off by 193 lines), 6 medium, 13 minor, 4 nits; Part A ACCEPT as in 645aace (154 passed). Findings: `../verification/autopilot-20261018-run11/review-gate9-draft-r1.md`. Weekly checks 18 Oct 20:20: 4 containers up, backups nightly (latest 20261018T031501Z, 1.8M), certificate valid to 2027-01-13. Paid calls: 0.
- Done (run 11, continued): **Gate 9 protocol amendment, committed as DRAFT r3.1** (`docs/research/gate9-adult-protocol-amendment.md`, not the lock). Sonnet worker; Opus xhigh checker.
  - r1 check (`../verification/autopilot-20261019-run11/gate9-draft-check-r1.md`): NOT_LOCKABLE. 5 high: grouping.py citations 193 lines off; a firewall self-contradiction; the primary result is MissingEvidence by construction while SCI-03 is open; the source commit is frozen yet changed after the lock; a lock could cover nothing. Also 7 medium, 7 minor, nits. All applied as r2, with no scientific open decision settled by the model.
  - r2 delta: ACCEPT_AS_DRAFT, 2 medium (disposition of the parallel r1 review; the pre-label fix contradicted the freeze) and 7 minor/nits. Applied as r3. Section 11.4 dispositions all 24 Part B findings of the parallel review.
  - r3 delta: ACCEPT_AS_DRAFT, 3 minor and 2 nits, plus two dispositions relabelled. Applied as r3.1 by this run.
  - The draft now has section 9A "Lock preconditions". The lock is forbidden while any blocking open decision is open: OD-01, 02, 04 (SCI-03/04), 08, 09, 10, 11/12, 15, 16, 19 (incl. an aligned test-label parser). There is no unseal while SCI-03 is open. Binding is two-stage: the lock binds the text, manifest digest, allocation digests and non-public source hashes; a public execution-binding commit before the unseal binds the source, dependencies, guard lift and seed map.
  - These are model checks, not human review. adult.test was not downloaded or read. Paid calls: 0.
- Blocked: the Gate 9 lock needs owner item 11 (adult.test download permission) and author dispositions of the blocking open decisions. Item 8 (redeploy) still needs an interactive session.
- Next: from 20 Oct, the Gate 8 freeze script, then commit the manifest, then the driver in `--limit` chunks. Then the Gate 9 open-decision dispositions (OD-08/09/10/11/12/16 can be drafted from the Gate 8 bindings) for a later model check.

## 2026-10-19 13:46–14:40 IST (autopilot run 12, scheduled)
- Orientation: tree clean, so the concurrency guard did not apply. HEAD `5ca598e` equals `origin/main`. Live readiness `ready`, still the 15 Oct bundle. No owner-action status changed (item 8 redeploy, item 9 no veto, item 11 no answer). Keep-awake tool not available.
- Done: **release secret scan (RELEASE_CHECKLIST row 10, partial → still PARTIAL, narrower remainder).** Executor scan scripts and evidence are in `../verification/autopilot-20261019-run12/` (`TRIAGE.md`, `SHA256SUMS.txt`).
  - v2 covers the whole local object store:
    - the contents of 870 blobs (5 unreferenced) and 56 commit messages (2 commits reflog-only), plus 5 zip members; 30,080,184 bytes;
    - file names from all trees.
  - It also covers the live bundle: 14 files, lazy chunks included, byte-identical to the build committed at `44210bb`.
  - Result: 0 exact-byte hits for `NEBIUS_API_KEY` or the DuckDNS token. All 53 pattern hits (40 DB-URL, 1 key-like, 12 credential-name assignments) are fixtures, placeholders or non-credential constants. `NEBIUS_MODEL` and `NEBIUS_BASE_URL` hits are public values.
  - Not covered: the VM and local test-database passwords (the WSL Docker daemon was down), encoded forms, and the image's history, configuration and in-image files (they are scanned at the redeploy).
- Review (Opus xhigh, model reviews, not human acceptance):
  - v1: CORRECTIONS_REQUIRED, 1 high (the crawl missed 6 lazy chunks), 3 medium (incomplete remainder list, a DB-URL count of 41 instead of 40, zip members not scanned), 4 minor and 3 nits. All addressed by scanner v2 and a rewritten TRIAGE; v1 is kept and marked superseded.
  - Delta: CORRECTIONS_REQUIRED, text only, no rescan. 2 minor and 3 nits. The wording fixes are applied. Two scanner hardening items are deferred to the redeploy scan: identifier-only skipped-key output, and quoted-value parsing with length controls.
- Verified: counts above from `release-secret-scan-v2.json` (sha256 `83c76a74…40bc`); the reviewer independently re-derived the counts and confirmed the bundle's byte identity. No product code changed, so no test suite was run. Paid calls: 0.
- Blocked: item 8 (redeploy), and with it the live Results checks, the hosted smoke test, the in-image scan and the video re-record. Gate 8 real runs wait for 20 Oct. The Gate 9 lock waits for item 11 and the author's open decisions.
- Next: from 20 Oct, the Gate 8 freeze script, then commit the manifest, then the driver in `--limit` chunks.

## 2026-10-19 15:03–16:45 IST (autopilot run 13, scheduled)
- Orientation: tree clean, so the concurrency guard did not apply. HEAD `3421378` equals `origin/main`. Live readiness `ready`, still the 15 Oct bundle (`index-oNasIWcL.js`, image e249b72). No owner-action status changed (item 8 redeploy, item 9 no veto, item 11 no answer). Keep-awake tool not available.
- Done: **release-candidate image from HEAD, prepared for a one-command deploy** (evidence `../verification/autopilot-20261019-run13/`, `TRIAGE.md`, `SHA256SUMS.txt`). Sonnet workers wrote the scanners; Opus xhigh reviewed.
  - Image `shiftguard:judge-3421378` built from `git archive 3421378`: config `sha256:0c666412…`, which shows as manifest `sha256:c5cd193c…` on the VM's containerd store. It carries the whole `55e75c4` Results assistant plus the `f98c1ce` follow-ups. Served bundle `index-Bk6b9ZMP.js`.
  - Local stack on PostgreSQL 16 (migrations to head): offline release probe **PASS 11/11**, 0 model requests. API 151 MiB, worker 136 MiB.
  - Uploaded to the VM as `/tmp/sg-3421378.tar.gz` in 20 resumable chunks: 0 mismatches, final SHA-256 MATCH (`938f8ad2…4712`). Nothing was loaded or restarted on the VM.
  - `sg-redeploy-3421378.sh` (revision 3, sha256 `f595e424…2731`) copied to the VM `/tmp` and not run. OWNER_ACTIONS item 8 now runs it: `sudo bash /tmp/sg-redeploy-3421378.sh`.
    - It loads and checks the image, keeps a checked rollback tag, fast-forwards to exactly `3421378` and takes a verified pre-deploy backup.
    - It then restarts and prints `REDEPLOY OK` only when api and worker run the new image, readiness is `ready` and the new bundle is served.
  - Read-only VM checks: `deploy/.env` names `shiftguard:judge` and both assistant flags are true; the only untracked file is `deploy/backup.sh`; Docker 29.9.1 with the containerd store.
- Secret scans (RELEASE_CHECKLIST row 10 rewritten, still PARTIAL):
  - **Image**, whole archive: config, 25 history entries and 15 layers (11,788 files, link names and targets, 997 zip members). 0 hits for the API key or the DuckDNS token in raw, case, percent, JSON, UTF-16LE or base64 forms.
  - **Repository and live bundle (v3)**, exact bytes: 0 hits for either.
  - The review found that run 12's v2, and r1 here, compared the DuckDNS token as the whole token file, not the bare token. v3 and r2 extract the single UUID and fail closed otherwise. Run 12's token result is superseded.
  - r1's JSON also held the throwaway local test-DB password in third-party file paths. It is renamed SUPERSEDED and stays outside the repo. Every path in r2 is now redacted.
  - The local test-DB comparison is not informative (8-character common word). Rotation is pending.
- Review (Opus xhigh, model reviews, not human acceptance): five rounds, all CORRECTIONS_REQUIRED, all applied.
  1. 2 high (the token form; the secret in paths), 4 medium (wrong baseline e249b72; compose/flags pre-checks; unsafe `mv`; test-DB wording), and minors.
  2. 2 medium (v3 coverage overstated; item 8 checks were comments, not gates).
  3. 1 high: in a heredoc paste, `backup.sh`'s `docker compose exec` swallowed the rest of the script, which exited 0 without deploying. Replaced by a script file.
  4. 1 high (containerd image ID), 2 medium (re-run blocked after a failed `up -d`; readiness did not prove the new image), lows.
  5. 1 low required (`set -E`), plus nits.
  - Deferred, recorded in TRIAGE: two image-scanner nits (summary `image:` line not redacted; a failed start-up self-test does not stop the scan; it passed). The script's last revision (`set -E` and two nits, exactly as proposed) was not re-reviewed.
- Verified: scanner self-tests pass. All 22 current SHA256SUMS entries verify. Boolean check: the r2 outputs and TRIAGE do not contain the test-DB password. No product code changed, so no pytest run. Paid calls: 0.
- Blocked: item 8 still needs the owner or an interactive session ("deploy now"), and with it the live Results checks, the hosted smoke test, the new containers' log scan and the video re-record. Gate 8 real runs wait for 20 Oct. The Gate 9 lock waits for item 11 and the author's open decisions.
- Next: from 20 Oct, the Gate 8 freeze script, then commit the manifest, then the driver in `--limit` chunks. After "redeployed": verify the image, bundle, flags and logs, then the live checks (≤17 calls). Rotate the local test-DB password before the next scan.
