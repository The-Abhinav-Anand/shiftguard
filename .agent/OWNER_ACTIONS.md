# Owner actions (only these need you; everything else is automated)

Do them in any order, whenever you have 10 minutes. Write "DONE" next to each one you finish.
The autopilot checks this file every run.

1. **GitHub sign-in (2 min):** open a terminal on this PC and run `gh auth login`. Choose
   GitHub.com → HTTPS → "Login with a web browser", and approve in the browser. If `gh` is
   missing, install GitHub CLI from https://cli.github.com first. Status: DONE (15 Oct): signed in as `The-Abhinav-Anand` (scopes include repo and workflow). gh is at `C:\Program Files\GitHub CLI\gh.exe`.
2. **Hosting VM (15 min, free):**
   - Sign up at https://www.oracle.com/cloud/free/ (needs a card for identity checks; Always Free costs $0).
   - Create a Compute instance: Ampere A1 shape, Ubuntu 24.04, 2 OCPU / 12 GB.
   - When it asks for an SSH key, paste the contents of `C:\Users\Abhinav Anand\.ssh\id_ed25519.pub`.
   - In the VCN security list, allow inbound TCP 80 and 443.
   - Write the VM's public IP here: DONE (15 Oct): `130.210.3.156` (VM.Standard.E2.1.Micro, x86_64, 1 GB; Ampere was out of capacity in Mumbai). SSH as `ubuntu` with this PC's key works; DuckDNS repointed.
3. **Free domain (3 min):**
   - Sign in at https://www.duckdns.org.
   - Create a subdomain (e.g. `shiftguard`) and set its IP to the VM IP.
   - Write the domain here (e.g. `shiftguard.duckdns.org`): DONE (15 Oct): `shiftguard.duckdns.org`. It currently points at
     152.59.59.155, which is the owner's own internet connection, not a server. The DuckDNS token
     is stored outside the repo in `../.tools/duckdns.token`, so the autopilot repoints the domain
     to the VM IP itself (`https://www.duckdns.org/update?domains=shiftguard&token=<token>&ip=<VM IP>`).
     Never commit or print the token.
4. **API key on the server (1 min, after the VM is up):** either write "copy key: yes" here, so the autopilot copies `NEBIUS_API_KEY` from this PC's `.env` to the VM over SSH without displaying it, or put it in `deploy/judge.env` on the VM yourself. Status: DONE (15 Oct): owner wrote "copy key: yes". Copy NEBIUS_API_KEY from this PC's `.env` over SSH once the VM exists; never display it.
5. **Video upload (5 min) — READY NOW (updated 27 Oct):** upload
   `docs/submission/media/shiftguard-demo-live.webm` (2:35, captions, no audio, recorded on the live app
   with real Nemotron replies; it replaces the older scripted `shiftguard-demo.webm`) to YouTube:
   youtube.com → Create → Upload video → select the file → title "SHIFTGUARD: calibration under missing inputs"
   → "No, it's not made for kids" → Next ×3 → Visibility **Public** → Publish. Paste the link here:
6. **Submit (5 min, by 30 Oct 20:00 IST; official close 22:30 IST):** open the hackathon's Devpost page →
   Enter a submission (or edit your draft) → paste each field of `docs/submission/DEVPOST_FORM.md`, with
   the YouTube link from item 5 in "Video demo link" → upload the five gallery images it lists → open the
   live app, repository and judge guide links once from a private window → press **Submit**.
   Status: DONE (30 Oct): owner reported "submitted". The YouTube link has not been recorded in item 5.

7. **Publish the repository (2 min) — NEW, needed first:** the autopilot's session is not
   permitted to create a public repository (Claude Code's auto-mode safety check blocked it on
   15 Oct). The history secret scan passed on 15 Oct (37 commits: no API key, DuckDNS token,
   `.env` or database files). Note: commits show your name and `abhinav05005@gmail.com`. Either
   - run these in a terminal on this PC:
     ```
     cd "C:\Users\Abhinav Anand\Downloads\nvidia\shiftguard"
     gh repo create The-Abhinav-Anand/shiftguard --public --description "Calibration under missing inputs: rehearse input-field outages on a tabular model and measure calibration, decision loss and recovery cost."
     git remote add origin https://github.com/The-Abhinav-Anand/shiftguard.git
     git push origin implementation/gate-0:main
     ```
     then write "published" here; or
   - write "publish: allowed" here and add a Claude Code permission rule allowing `gh repo create`
     and `git push` for this project, and the next run publishes it.
   The VM bootstrap clones from this repository, so it is needed before deployment.
   Status: DONE (15 Oct, interactive session): published as https://github.com/The-Abhinav-Anand/shiftguard.

8. **Redeploy the Results assistant to the VM (5 min) — UPDATED 19 Oct:** unattended runs must not
   deploy (Claude Code's auto-mode check blocks "Production Deploy"), so this needs you or an
   interactive session. Autopilot run 13 built a fresh image from HEAD `3421378`. It includes the
   `55e75c4` Results assistant and the `f98c1ce` follow-ups. Image ID `sha256:0c666412404a…`; the
   offline release probe passed locally (0 model calls); the in-image secret scan found 0 hits for the API key.
   It is uploaded to the VM as `/tmp/sg-3421378.tar.gz`; SHA-256 matched after upload:
   `938f8ad21ebc909b3b5ccad6b29fe962bf4cedcd1fbaec83917010fb4e0a4712`.
   A read-only check (19 Oct) found: the VM is on `e249b72`; `deploy/.env` sets `SHIFTGUARD_IMAGE=shiftguard:judge`
   and both assistant flags `true`, so they survive the restart; the only untracked file is `deploy/backup.sh`.
   - **Easiest:** open an interactive Claude session and say "deploy now".
   - **Or run it yourself:** in a terminal on this PC, run
     `ssh -i "C:\Users\Abhinav Anand\.ssh\id_ed25519" ubuntu@130.210.3.156`, then on the VM:
     ```
     tmux new -A -s sg
     sha256sum /tmp/sg-redeploy-3421378.sh
     sudo bash /tmp/sg-redeploy-3421378.sh
     ```
     The `sha256sum` line must print `f595e424784830942ce76d5c3b2a0f1bfc1bc0b0cfd72a8d3756b0e59d542731`; if not, stop.
     Write "redeployed" here only if the last line printed starts with `REDEPLOY OK`.
     If SSH drops, reconnect and run `tmux attach -t sg`, or run the script again. If it stops with STOPPED after
     step 6 began and the site is down, run Rollback below.
     The script is also kept at `..\verification\autopilot-20261019-run13\sg-redeploy-3421378.sh`. What it does:
     - Stops at the first failed check, and is safe to run again.
     - Loads the image if it is not loaded yet, checking the tarball's SHA-256 first. Loading does not
       touch the running site.
     - Checks the image ID. This VM uses Docker's containerd store, so the ID shows as the manifest
       digest `sha256:c5cd193c…`. That is the same image as config `sha256:0c666412…`.
     - Tags the running e249b72 image (`sha256:bc1a73c4…`, full ID checked) as `shiftguard:judge-prev-e249b72`, once.
     - Moves the untracked pre-review `deploy/backup.sh` to `/root/pre-review/backup.sh.untracked-e249b72`.
     - Fast-forwards `/opt/shiftguard` to exactly `3421378`.
     - Takes a pre-deploy backup with the reviewed script, checks that a new backup set was written,
       and reinstalls the nightly cron. Its `source-commit.txt` will say 3421378 for data written by e249b72.
     - Switches the tag and restarts the stack. No separate migration step is needed: the schema is
       unchanged since e249b72.
     - Waits up to 5 minutes for all three: the api and worker containers run the new image, readiness
       is `ready`, and the page serves `index-Bk6b9ZMP.js`.
     Do not run plain `docker compose config` or an unfiltered `docker inspect`: they print secrets.
     The next run verifies the image, the served bundle, the flags and the container logs. Then it
     does the live checks (at most 17 paid calls within the daily cap) and removes the old `/tmp` tarballs.
     Rollback:
     `cd /opt/shiftguard && sudo docker tag shiftguard:judge-prev-e249b72 shiftguard:judge && sudo docker compose -f deploy/compose.judge.yaml up -d --remove-orphans && curl -fsS --resolve shiftguard.duckdns.org:443:127.0.0.1 https://shiftguard.duckdns.org/health/ready`
     After a rollback the source stays at `3421378`. That is harmless: `deploy/` differs only by the
     reviewed `backup.sh`, and there are no migrations.
   - **Or allow the autopilot to deploy:** add a Claude Code permission rule for this project that
     allows SSH deploy commands to `ubuntu@130.210.3.156`, and write "deploy: allowed" here.
   History: this upload supersedes the 16 Oct one (`/tmp/sg-55e75c4.tar.gz`, image `e10541…`).
   On 17 Oct, SSH on port 22 was blocked from one network, then reachable again the same day.
   Status: DONE (22 Oct, interactive session, SSH reachable again): `sudo bash /tmp/sg-redeploy-3421378.sh` → REDEPLOY OK (image `c5cd193c…`, commit `3421378`). Evidence `verification/gate10-redeploy-20261022T061002Z/`.

9. **Gate 8 real-Bank repeats: no action needed unless you object (17 Oct):** under your general
   delegation, the autopilot decided to run the declared 5×10 Gate 8 repeat schedule on real Bank.
   It is development tier only, labelled "Bank outcomes previously inspected; not confirmatory",
   and the labels stay on this PC. The record is
   `..\research\gate8-20261009\AUTHORIZATION-20261017-bank-development-repeats.md`. While SCI-03 is
   unresolved, the primary estimate is expected to come out as "missing evidence" by design.
   Real data will not be touched before 20 Oct. To stop it, write "gate8: no" here.
   Status:

10. **Commit and push the reviewed Gate 8 adapter change (2 min) — NEW, 17 Oct:** Claude Code's
    auto-mode safety check blocked `git commit` in the scheduled run ("Modify Shared Resources"),
    so it was not retried. The change is tested (365 passed) and Opus-reviewed (ACCEPT after
    corrections). The 10 changed files are all under `shiftguard/repeats/`, `tests/repeats/`
    and `tests/repeats_adapter/`. The commit message is ready in
    `..\verification\autopilot-20261017-run6\COMMIT_MESSAGE.txt`. In a terminal on this PC:
    ```
    cd "C:\Users\Abhinav Anand\Downloads\nvidia\shiftguard"
    git add shiftguard/repeats tests/repeats tests/repeats_adapter .agent
    git commit -F ..\verification\autopilot-20261017-run6\COMMIT_MESSAGE.txt
    git push origin implementation/gate-0:main
    ```
    Then write "committed" here. Alternatively, add a Claude Code permission rule allowing
    `git commit` and `git push` in this repository, and write "commit: allowed" here.
    Until then, autopilot runs leave these files alone and do not retry the commit.
    Status: DONE (17 Oct, interactive session): committed as `f71c42d` and pushed.

11. **Adult test file for Gate 9 (1 min), NEW 18 Oct.** The label-blind source-manifest builder
    needs the official UCI `adult.test` file. The autopilot needs your permission to download a file.
    Source: https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.test (about 2 MB).
    The autopilot then computes only file hashes, line ids and feature-only groups; it never reads the
    label column. Reading the file's bytes before the protocol lock is recorded as an exposure event,
    not as custodian evidence. Do one of these:
    - write "adult test download: yes" here; or
    - save the file yourself as `shiftguard\data\raw\adult.test` (git-ignored) and write "placed" here.
    Gate 9 is off the submission critical path, so this is optional before 30 Oct.
    Status:

12. **Commit and push the reviewed Gate 8 text update (2 min), NEW 22 Oct.** Claude Code's auto-mode
    safety check blocked `git commit`/`git push` in scheduled run 15 ("Git Destructive"), so the
    run did not retry it. The change is doc-only: claim C8 plus matching wording in `README.md`,
    `docs/README.md`, `SUBMISSION.md` and `DEVPOST_FORM.md`, which still said the repeat engine had
    run on fabricated data only. It also includes `.agent/session-state.md`, `.agent/AUTOPILOT_LOG.md`
    and this file. Opus review: ACCEPT after corrections. In a terminal on this PC:
    ```
    cd "C:\Users\Abhinav Anand\Downloads\nvidia\shiftguard"
    git add README.md docs/README.md docs/submission .agent
    git commit -F ..\verification\autopilot-20261022-run15\COMMIT_MESSAGE.txt
    git push origin implementation/gate-0:main
    ```
    Then write "committed" here. Alternatively, open an interactive session and say "commit run 15".
    Until then, scheduled runs leave these files alone.
    Status: DONE (22 Oct, interactive session): committed as `9e76c2d` and pushed.
