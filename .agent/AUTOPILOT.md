# SHIFTGUARD autopilot runbook

The owner (Abhinav) has handed delivery to Claude: review, decide, build, test, commit,
deploy and prepare submission without asking him. Each scheduled run starts fresh. Read this
file, `.agent/session-state.md`, `.agent/AUTOPILOT_LOG.md` and
`docs/superpowers/plans/2026-10-15-results-assistant-and-remaining-gates.md` (current plan), then do the next unfinished items.

Hard deadline: Devpost submission by **30 Oct 2026 20:00 IST** (official 22:30 IST). The app
must stay reachable until **16 Dec 2026 01:30 IST**.

## Each run

0. **Concurrency guard.** If `git status` shows uncommitted changes to tracked source, or untracked files under `shiftguard/`, `tests/`, `frontend/src/`, `deploy/` or `scripts/`, and any of those files was modified less than 3 hours ago, an interactive session is working.
   - Do only read-only checks: site health, ledger, certificate.
   - Append one log line and exit without editing or committing.
   - If the newest such change is 3 hours old or more, the interactive session is gone. Take over: read the latest log entries, review the uncommitted work as an in-progress batch (tests plus the Opus review), then continue.
1. Orient (5 minutes at most):
   - `git log --oneline -8` and `git status`;
   - the last entries of `AUTOPILOT_LOG.md`;
   - `.agent/OWNER_ACTIONS.md`.

   Check whether the owner completed anything listed there. Signs he did:
   - `gh auth status` succeeds;
   - an SSH host or key is recorded in `.agent/OWNER_ACTIONS.md`;
   - the file itself was edited.
2. Pick the highest-priority unfinished item from the queue below that is not blocked. Work until it is done and verified, then take the next one. Stop starting new items when roughly an hour of usage remains.
3. Verify every change with the focused tests for that area: both databases where relevant, browser specs for frontend changes. Do not rerun the 3-hour full suite for doc-only changes. Run it once before the release freeze.
4. Commit verified work on `implementation/gate-0`. The commit message says what changed and which checks passed, and ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Push only after the GitHub remote exists, and only after the secret scan below.
5. Append a dated entry to `.agent/AUTOPILOT_LOG.md`: done, verified (exact counts), blocked, next. Update `.agent/session-state.md` only for milestone changes.
6. Notify the owner (PushNotification) only when he must act, or when a milestone completes: live URL up, repo public, video ready, submission ready. Never for routine progress.

## Subagents (owner's rule, 15 Oct 2026)

- Writing code and running checks: use subagents on **Haiku** (small, mechanical edits and searches) or **Sonnet** (features and fixes). Give each one disjoint file ownership and a self-contained brief.
- Reviewing: one **Opus** reviewer at **xhigh** effort per batch, reviewing the finished diff and its evidence before you commit or deploy. Act on its findings; a review is never skipped to save time.
- The run itself integrates, verifies, commits and logs. Report the reviewer's verdict in `AUTOPILOT_LOG.md` as a model review, not as human acceptance.

## Queue (priority order; skip blocked items, come back later)

The authoritative plan is `docs/superpowers/plans/2026-10-15-results-assistant-and-remaining-gates.md`. This queue mirrors it; follow the plan for detail.

**Status (16 Oct 2026):** live at https://shiftguard.duckdns.org (Oracle E2.1.Micro x86_64, 1 GB + 2 GB swap; checkout `/opt/shiftguard`; image built on this PC and loaded with `SHIFTGUARD_SKIP_BUILD=1`; both assistants enabled; `NEBIUS_API_KEY` copied over SSH with the owner's approval).

Done: hosting scaffold, public README and docs, captioned demo video, submission text, public GitHub repo, deploy, and the hosted probe for all three presets. On the VM: restart and second-owner checks pass, nightly backups are installed, and hosted container logs are secret-free (the full static-bundle scan is still pending; see RELEASE_CHECKLIST row 10). Evidence: `../verification/gate10-hosted-*`. Log: `AUTOPILOT_LOG.md`.

1. **Batch R: Results assistant (in progress, top priority).**
   - Root causes:
     - (A) free-form prompts have no selection authority;
     - (B) a full 400-condition read (258 KB) exceeded the provider's 64 KB transcript bound.
   - Fixes:
     - provider-copy projection only when the provider would reject the transcript;
     - an unauthorized-read short-circuit with typed guidance (`EXPERIMENT_NOT_SELECTED` / `EXPERIMENT_NOT_PUBLISHED`), never for Run commands, never hiding a failed or cancelled outcome, and never echoing a model-chosen id;
     - insert-only "Ask about this result" buttons;
     - a guidance notice in the panel.
   - The Opus review of 16 Oct returned CORRECTIONS_REQUIRED (M1–M8); corrections are in progress.
   - Then: a delta Opus review, commit and push, rebuild the image, resumable upload, `docker load`, `docker compose up -d`.
   - Then live checks within the cap with `scripts/check_hosted_live.py`: `Summarize experiment <id>` and the compare command. A pass must have no guidance, bound evidence and non-empty claims. Record calls and tokens per question, then set the questions-per-day figure in JUDGE_GUIDE, SUBMISSION and DEVPOST_FORM from the measurement.
1b. **Judge resilience: provider timeouts (before the freeze).**
   - On 22 Oct the first live call timed out at 25 s, and the halt-on-unknown policy stopped both assistants for the rest of the UTC day.
   - Change: a TIMEOUT closes the reservation as charged in full and does NOT halt the day. The reservation is a strict upper bound (byte-bounded input plus the 1,024-token output cap), so the hard cap still holds.
   - Other unknown outcomes keep the halt.
   - Add `NEBIUS_TIMEOUT: ${NEBIUS_TIMEOUT:-55}` to the compose app environment (the VM already sets 55 in judge.env).
   - Tests on both backends, the Opus xhigh review, then the freeze image.
   - Live checks after the daily reset use `scripts/check_hosted_live.py --skip-chat` (Summarize, then Compare).
2. **Batch H: Gate 10 remainder.**
   - Keep RELEASE_CHECKLIST claims strictly evidence-backed (paths under `../verification/`).
   - Run the clean-browser hosted smoke test: Playwright with `SG_E2E_BASE_URL=https://shiftguard.duckdns.org`, product specs only, with no paid calls.
   - Weekly: certificate expiry, readiness, ledger, backup freshness.
3. **Batch F: Gate 11 freeze (27–28 Oct).**
   - full Python suite once on the final source;
   - tag `hackathon-2026-submission`;
   - record the image and VM digests;
   - backup;
   - final checklist;
   - re-record the demo video with the live Results assistant inside the cap, removing the scripted badge only for live shots.
   - Then mark OWNER_ACTIONS: video upload, Devpost submit.
4. **Batch S8: Gate 8 on Bank (development tier only).**
   - Record the owner-delegated authorization in `../research/gate8-20261009/`.
   - Resource preflight on 41,188 fabricated rows.
   - Run the full 5×10 `gate8-nested-v1` schedule on real Bank locally, restartable. Labels stay evaluator-private.
   - Aggregate the primary contrast with the declared group bootstrap, labelled `bank_overlap_diagnostic`, "development; Bank outcomes previously inspected; not confirmatory".
   - Report every coordinate, including failures.
   - In the app, label single-seed UI runs "illustrative".
5. **Batch S9: Gate 9 Adult (prospective; may continue after 30 Oct).**
   - Build the custodian manifest from the official UCI archive without test labels.
   - Write the author-locked protocol amendment, have Opus check it for consistency, then commit and push it publicly BEFORE any test outcome is read. That commit is the lock, labelled "author-locked, not externally peer-reviewed".
   - Wire the engine, with Bank Gate 2/3 byte-identical reproduction for any change to a numerical owner.
   - Development runs on the training file only.
   - Unseal the test file once and report whatever it shows.
   - Never rush this into the judged build.
6. **After 30 Oct:** weekly health check; outage fixes only on the judged build; continue S8/S9 for the paper.

## Guardrails (never break these, even to save time)

- Never print, log, commit or paste `.env`, API keys, tokens, database URLs or passwords. Compare secrets only in memory and report counts.
- Paid model calls only for the bounded live checks named in this queue, inside the 50 calls / 100,000 tokens daily cap. Never change the cap, retries or ledger, and never reset a day.
- Never create accounts, enter passwords or card details, or log in for the owner. Do not upload to YouTube or press Devpost "Submit"; prepare them and list them in OWNER_ACTIONS.
- Never edit applied migrations 0001–0011. Gate 7 security fixtures and `scripts/run_live_acceptance.py` contracts stay unchanged. If a change conflicts with them, change the design, not the test. A denied action is never retried or routed around.
- Numerical engine owners (`calibration/`, `experiments/`, `metrics/`, `datasets/`) may change only for Batch S9 wiring, and only with Bank Gate 2/3 byte-identical reproduction as evidence.
- Real outcome access only as the plan allows. Bank repeats are development tier and never called confirmatory. Adult test outcomes are read only after the public lock commit, exactly once.
- Do not delete evidence under `../verification/` or historical docs. Do not reset or rewrite git history; never force-push.
- Don't present your own checks or the Opus subagent's review as independent human review. Every public text stays honest: development evidence, Bank only, no uploads, Gate 8/9 status exactly as achieved.
- If something fails twice, find the root cause before retrying. Log failures as they are.

## Owner actions (keep `.agent/OWNER_ACTIONS.md` current and short)

The only things that need Abhinav, each a few minutes. Keep them in one list with exact
click-by-click steps. Notify him once when the list changes, never repeatedly.
1. `gh auth login` on this PC (browser sign-in), so the repo can be created and pushed.
2. Hosting VM, preferably Oracle Cloud Always Free (Ampere A1, Ubuntu 24.04, ports 80/443 open). Then either add this PC's public SSH key (`~/.ssh/id_ed25519.pub`; generate it if missing) to the VM, or run the one bootstrap command himself. Also a free DuckDNS subdomain pointing at the VM IP, with the domain recorded in OWNER_ACTIONS.
Items 1–3 (GitHub sign-in, VM and domain, key copy) are DONE.
4. Upload the final video to YouTube (Public) and paste its URL into OWNER_ACTIONS.
5. On submission day, paste `DEVPOST_FORM.md` into Devpost and press Submit.
