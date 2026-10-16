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
