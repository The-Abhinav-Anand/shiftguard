# SHIFTGUARD autopilot runbook

The owner (Abhinav) has handed delivery to Claude: review, decide, build, test, commit,
deploy and prepare submission without asking him. Each scheduled run starts fresh. Read this
file, `.agent/session-state.md`, `.agent/AUTOPILOT_LOG.md` and
`docs/superpowers/plans/2026-10-15-launch-plan.md`, then do the next unfinished items.

Hard deadline: Devpost submission by **30 Oct 2026 20:00 IST** (official 22:30 IST). The app
must stay reachable until **16 Dec 2026 01:30 IST**.

## Each run

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

## Queue (priority order; skip blocked items, come back later)

1. **Hosting scaffold:**
   - add a `caddy` HTTPS service and `deploy/Caddyfile` to `deploy/compose.judge.yaml`, using `SHIFTGUARD_DOMAIN`;
   - add `deploy/bootstrap-vm.sh`. On Ubuntu 22.04/24.04 it installs Docker Engine and the compose plugin from Docker's apt repository, clones or pulls the repo, builds the image, generates `judge.env` and `postgres.env` with random passwords if absent, copies the dataset, then runs `docker compose up -d`. It must work on ARM64.
   - Extend `tests/integration/test_hosted_release_contract.py` to cover both.
2. **Public repository face:**
   - README rewrite: who it is for (launch plan §4), what it shows, a 5-minute quickstart, the architecture, honest limits;
   - `docs/README.md` index labelling the gate and review docs as the engineering log;
   - `docs/ADAPTING.md` ("use your own tabular dataset", documentation only);
   - `CITATION.cff`, `CONTRIBUTING.md`, `.github/ISSUE_TEMPLATE/`;
   - audit `THIRD_PARTY_NOTICES.md` against shipped dependencies.
3. **Screenshots and demo video, no owner needed:**
   - Start the scripted local harness or the local server.
   - Use Playwright with `recordVideo` to capture the flow in `docs/submission/DEMO_SCRIPT.md`, with on-screen captions drawn by an injected overlay instead of a voice-over. The result is one `.webm` under 3:00, plus PNG screenshots in `docs/submission/media/`.
   - Do not install ffmpeg or other tools. If a voice track is ever wanted, that is optional and the owner records it.
   - Use only already-published records and the scripted provider for the chat panels. Label any scripted assistant content on screen as "recorded with test data". Never present scripted text as a live Nemotron reply.
4. **Submission text:**
   - finalize `docs/submission/SUBMISSION.md`, `JUDGE_GUIDE.md` (measured preset times; the 50-call cap) and `RELEASE_CHECKLIST.md`;
   - add a sponsor-feedback paragraph from real experience with Token Factory and Nemotron;
   - write `docs/submission/DEVPOST_FORM.md` with every form field ready to paste.
5. **GitHub publish (needs `gh auth status` OK):**
   - Re-run the history secret scan. It must find no Nebius key (compared in memory against `.env`), no `.env`, `*.sqlite` or `*.db` files, and no real credentials.
   - Create the public repository `shiftguard` under the authenticated account if missing (`gh repo create shiftguard --public --source . --remote origin`).
   - Push `implementation/gate-0` as `main`; set the description, topics and website.
   - Never force-push over the owner's commits.
6. **Deploy (needs a reachable VM recorded in OWNER_ACTIONS):**
   - over SSH, run `deploy/bootstrap-vm.sh`;
   - run `scripts/check_hosted_release.py` against the HTTPS URL;
   - repeat the restart and second-owner checks;
   - scan the logs and bundle for secrets;
   - record the URL in README, JUDGE_GUIDE and SUBMISSION.
   - The owner places `NEBIUS_API_KEY` in `deploy/judge.env` on the VM; never read, print or copy it. Then enable both assistants and do one live check: one general-chat message and one Results question, about 9 calls at most, within the 50 / 100,000 daily cap.
7. **Fallback if no VM by 26 Oct:** run the stack on this PC (the existing local server) behind a Cloudflare quick tunnel only if `cloudflared` already exists. Otherwise submit with the repo, quickstart and video, and say plainly in `DEVPOST_FORM.md` that the hosted demo is pending. Record this decision in the log.
8. **Freeze (27–28 Oct):**
   - full test suite once;
   - tag `hackathon-2026-submission`;
   - record the image digest;
   - back up the database and artifacts together;
   - final checklist.
9. **After 30 Oct:** weekly health check of the URL, readiness and the daily allowance. Fix outages only; no feature work on the judged build.

## Guardrails (never break these, even to save time)

- Never print, log, commit or paste `.env`, API keys, database URLs or passwords. Compare secrets only in memory and report counts.
- No paid model calls except the single live check in item 6, within the 50 calls / 100,000 tokens daily cap. Never change the cap, retries or ledger, and never reset a day.
- Never create accounts, enter passwords or card details, or log in on the owner's behalf. Those are owner actions (below). Do not upload to YouTube or press Devpost "Submit". Prepare them fully and list them as owner actions.
- Do not edit migrations 0001–0011, the numerical engine owners (`calibration/`, `experiments/`, `metrics/`, `datasets/`), or Gate 8/9 real-data access. Gates 8 and 9 stay pending; no real outcome access.
- Do not delete evidence under `../verification/` or historical docs. Do not reset or rewrite git history.
- Don't present your own checks as an independent review. Be honest in every public text: single-seed development results, Bank only, no uploads.
- If something fails twice, find the root cause before retrying. Log failures as they are.

## Owner actions (keep `.agent/OWNER_ACTIONS.md` current and short)

The only things that need Abhinav, each a few minutes. Keep them in one list with exact
click-by-click steps. Notify him once when the list changes, never repeatedly.
1. `gh auth login` on this PC (browser sign-in), so the repo can be created and pushed.
2. Hosting VM, preferably Oracle Cloud Always Free (Ampere A1, Ubuntu 24.04, ports 80/443 open). Then either add this PC's public SSH key (`~/.ssh/id_ed25519.pub`; generate it if missing) to the VM, or run the one bootstrap command himself. Also a free DuckDNS subdomain pointing at the VM IP, with the domain recorded in OWNER_ACTIONS.
3. Put `NEBIUS_API_KEY=` into `deploy/judge.env` on the VM, or approve copying it from this PC's `.env` over SSH without printing it.
4. Upload the prepared video to YouTube (Public) and paste its URL into OWNER_ACTIONS.
5. On submission day, paste `DEVPOST_FORM.md` into Devpost and press Submit.
