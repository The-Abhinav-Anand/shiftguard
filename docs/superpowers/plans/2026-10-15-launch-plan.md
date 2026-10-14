# SHIFTGUARD launch plan: hosting, GitHub, video, Devpost (15 October 2026)

Deadline: **30 October 2026, 22:30 IST** (submit by 20:00). The app must stay reachable for
judging until **16 December 2026, 01:30 IST**. Owner decisions recorded today:

- Source commits are authorized.
- Daily model allowance: 50 calls and 100,000 tokens.
- Devpost registration is done.
- No video yet.

## 1. Where things stand

| Item | State |
|---|---|
| Gates 0–7 | Done |
| Correction batch OR-01–OR-09 | Closed by executor verification; committed `9e39afd` |
| Daily allowance 50 calls / 100,000 tokens | Committed `44210bb`; live on the local server |
| Linux image | Built; single-owner lock (`fcntl`) PASS; local judge stack + offline probe PASS |
| Restart / persistence test on the Linux stack | Written, not yet run |
| Hosting | Not chosen |
| Public GitHub repo | Not created. History scan clean: no API key, `.env` or data files in 26 commits |
| Video, Devpost form | Not started; script and text drafts in `docs/submission/` |
| Gates 8 and 9 | Fabricated-data engineering only; not needed for the hackathon |

## 2. Hosting: free options checked on 15 October 2026

The app needs one always-on Linux machine for at least 62 days:
- about 2 GB RAM for PostgreSQL, the API and the worker;
- a persistent disk for the database and saved artifacts;
- HTTPS.

Free tiers that sleep or wipe their disks break saved results, and judges arrive in December.

| Option | Cost | Fit | Main risks |
|---|---|---|---|
| **Oracle Cloud Always Free, Ampere A1 VM** (recommended) | $0 | Always on; Always Free block storage; plenty of RAM even after the reported mid-2026 cut to 2 OCPU / 12 GB | Card needed for sign-up checks. ARM CPU, so the image is built on the VM. Popular regions sometimes run out of capacity. Check the live limits in the console. |
| Nebius AI Cloud CPU VM, using the Builder Program credit | $50 AI Cloud credit | Sponsor-aligned. Smallest CPU VMs are listed from about $0.05/hour | About 62 days × 24 h × $0.05 ≈ $75 before disk, so the $50 credit would likely run out in early December, mid-judging, unless topped up |
| Google Cloud e2-micro, Always Free | $0 | Always on, 30 GB disk, US regions only | 1 GB RAM is tight for PostgreSQL + API + worker; needs swap; risky |
| Render free | $0 | Poor | Web service sleeps after idle; free Postgres expires after 30 days and is then deleted |
| Koyeb free | $0 | Poor | 512 MB, no persistent volumes, scales to zero |
| Hugging Face Spaces | $0–paid | Poor | Docker Spaces may need a paid plan; no free persistent disk; sleeps after 48 h idle |
| DigitalOcean via the GitHub Student Pack | — | — | Reported to have ended on 31 July 2026 |
| Your own PC + Cloudflare Tunnel | $0 | Last resort | The PC must stay on and online until 16 December |

**Recommendation:** Oracle Always Free for hosting, with Nebius Token Factory for the model. That meets the sponsor rule: runtime inference on Token Factory with an NVIDIA open model. HTTPS: a free DuckDNS subdomain with Caddy, which gets a Let's Encrypt certificate automatically.

Model cost ceiling: 100,000 tokens/day × 62 days ≈ 6.2M tokens at most. Check the Nemotron price in the Token Factory console against your $50 Token Factory credit.

## 3. Work plan

Owner: **you** = needs your account, decision or recording; **Claude** = I do it.

### Phase A — finish local proof (15–16 Oct) — Claude
1. Run the restart test on the local Linux stack:
   - kill the worker and restart the API mid-job;
   - check that the job finishes once with one publication;
   - replay the original request;
   - recreate the API container and check that the artifact digests still match;
   - test cancellation.
2. Second-owner refusal with chat enabled; record worker peak memory to set the compose limits.
3. Add a `caddy` HTTPS service and `deploy/Caddyfile` to the compose stack.
4. Write `deploy/bootstrap-vm.sh`. It installs Docker and the compose plugin, builds the image on the VM (works on ARM), creates the env files with generated passwords, and starts the stack.

### Phase B — hosting (16–19 Oct)
1. **You:**
   - create the Oracle Cloud account and one Ampere A1 VM (Ubuntu 24.04, 2 OCPU / 12 GB);
   - open ports 80 and 443;
   - create a DuckDNS subdomain pointing at the VM;
   - choose how I get access: SSH access for me, or you run one script I give you.
2. **Claude:**
   - deploy;
   - upload the verified Bank dataset files;
   - run `scripts/check_hosted_release.py` against the HTTPS URL;
   - run the restart and persistence checks and the second-API refusal;
   - scan the live bundle and logs for the key.
3. **You:** put `NEBIUS_API_KEY` in `deploy/judge.env` on the VM yourself, so the key never passes through chat.
4. **Claude:** live acceptance within the 50/100,000 daily cap: one general-chat message and one Results-assistant question about a saved Bank result. At most about 9 provider calls. Record the model, sanitized usage and provenance.

### Phase C — GitHub (19–22 Oct)
1. **You:** create an empty public repository, for example `github.com/<you>/shiftguard`. Then either sign in the GitHub CLI (`gh auth login`) on this machine so I can push, or push yourself.
2. **Claude:** prepare the public face. Section 4 says why it matters:
   - rewrite the README as "who it's for, what it shows, 5-minute quickstart, architecture, honest limits";
   - screenshots;
   - `CITATION.cff`, `CONTRIBUTING.md`, issue templates;
   - a docs index that labels the gate and review documents as the engineering log;
   - an "Adapting SHIFTGUARD to your data" guide.
3. Push the reviewed history with `main` as the default branch. Before pushing I re-run the secret scan on everything being published.

### Phase D — video (22–25 Oct) — you record, Claude prepares
1. Script: `docs/submission/DEMO_SCRIPT.md` (2:40). I'll refresh it against the live URL and write a shot list with exact clicks.
2. Record with OBS Studio (free) or Windows' built-in recorder (Win+Alt+R records one app window) at 1080p, then add a voice-over.
3. Upload to YouTube as **Public**, under 3:00. Never show the API key, `.env` or a terminal with secrets.

### Phase E — Devpost and freeze (25–30 Oct)
1. **Claude:**
   - fill `docs/submission/SUBMISSION.md` with the real links;
   - finish `JUDGE_GUIDE.md`, with measured preset times and the 50-call cap behaviour;
   - write a sponsor-feedback paragraph from what we actually used.
2. **You:** paste the text into the Devpost form, choose the "Best Apps and Agents" track, add the links (live app, GitHub, YouTube), and confirm eligibility.
3. **Freeze (28 Oct):**
   - tag `hackathon-2026-submission`;
   - record the image digest;
   - back up PostgreSQL and the artifacts together;
   - rehearse from a phone on mobile data.
4. **Submit by 30 Oct, 20:00 IST.**

### Phase F — keep it alive (31 Oct–16 Dec)
- Weekly health check of the URL, the readiness endpoint and the daily allowance (you, or a scheduled check if you want one).
- No changes to the deployed build after the freeze except fixes for outages.

## 4. How SHIFTGUARD is useful to others (README message)

**The problem it addresses.** Models in production lose input fields: a data feed breaks, a schema changes, a customer withdraws consent. The model keeps returning probabilities, but nobody checks whether they still match real outcome rates. Teams that act on thresholds (credit, fraud, marketing, triage) make worse decisions without noticing.

**Who can use it today, and how:**

1. **ML engineers and data scientists running tabular models.**
   - Rehearse a field outage before it happens: random cell loss, losing a whole block of history fields, or random loss matched to the same rate.
   - See how calibration and decision loss move.
   - See how many fresh labelled outcomes recalibration needs (the budget curve).
2. **Analytics teams that use probability thresholds.** The decision-loss and reliability views show whether a score is still safe to act on, separately from whether it still ranks well.
3. **Researchers.** A reproducible benchmark harness:
   - 400 paired conditions;
   - every failure and fallback counted;
   - a label firewall;
   - content-hashed artifacts.

   New calibration methods can be added and compared on equal terms. The repeat engine for multi-seed studies is included, tested on fabricated data.
4. **People building LLM features.** Reusable patterns, each with tests:
   - an assistant that may only call approved tools and never invents numbers, because Python renders every figure from stored records;
   - a hard daily spend ledger (reserve before each call, no retries, halt when the outcome is unknown);
   - at-most-once chat receipts that survive reloads;
   - a single-owner lock so two servers can't both spend.
5. **Students and teachers.** A hands-on way to see why Brier score and log loss can disagree, and how missingness patterns differ from missingness rates.

**What we will say plainly (limits):**
- Bank Marketing data only.
- Single-seed development results.
- No upload of private data.
- Not a new calibration algorithm.

**What would make it more useful (roadmap, after the deadline):**
1. Bring your own CSV, locally: a command-line evaluation on your own dataset that runs on your machine and needs no upload.
2. A pip-installable package for the evaluation core.
3. The multi-seed study on Bank and the Adult replication (Gates 8 and 9), once a scientific reviewer and data custodian are in place.

## 5. Model allowance for judges

50 calls and 100,000 tokens per UTC day, shared by every visitor. One Results-assistant question can use up to 8 calls, so the worst case is about 6 Results questions a day. A general-chat message uses 1. When the day's allowance is used up, both assistants say so, and runs, saved results and charts keep working. The allowance resets at 05:30 IST. The judge guide states this. Raising it later is an owner decision about spending.

## 6. Decisions needed from you now

1. Hosting: Oracle Always Free (recommended), Nebius AI Cloud (spends credits), or another option.
2. Access: SSH access for me, or you run the scripts I give you.
3. GitHub: repository name, and whether I push via the GitHub CLI or you push.
4. Video: which day you can record (needs about 30 minutes, after hosting is live).
