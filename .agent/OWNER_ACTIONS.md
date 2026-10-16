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
5. **Video upload (5 min) — READY NOW:** upload `docs/submission/media/shiftguard-demo.webm` (2:07, captions, no audio)
   to YouTube: youtube.com → Create → Upload video → select the file → title "SHIFTGUARD: calibration under missing inputs"
   → "No, it's not made for kids" → Next ×3 → Visibility **Public** → Publish. Paste the link here:
6. **Submit (5 min, on 29–30 Oct):** paste `docs/submission/DEVPOST_FORM.md` into the Devpost form and press Submit.

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

8. **Redeploy the fixed Results assistant to the VM (5 min) — NEW, 16 Oct:** the autopilot built
   and uploaded the image, but Claude Code's auto-mode safety check blocked the production deploy
   step ("Production Deploy"), so it was not retried. Commit `55e75c4` is pushed. The image
   `sha256:e10541032e38…` (amd64) is uploaded to the VM as `/tmp/sg-55e75c4.tar.gz`, and its
   SHA-256 matched after the upload: `69999977309f6b22ce778605d35574bdb48199c831fc4262cfe62607f3e2e4c4`.
   Do one of these:
   - **Run it yourself:** in a terminal on this PC, run
     `ssh -i "C:\Users\Abhinav Anand\.ssh\id_ed25519" ubuntu@130.210.3.156`, then on the VM:
     ```
     cd /opt/shiftguard
     sudo mkdir -p /root/pre-review && sudo mv deploy/backup.sh /root/pre-review/backup.sh.untracked-e249b72
     sudo git -c safe.directory=/opt/shiftguard pull --ff-only
     sudo bash deploy/backup.sh --install
     sudo docker tag shiftguard:judge shiftguard:judge-prev-e249b72
     gunzip -c /tmp/sg-55e75c4.tar.gz | sudo docker load
     sudo docker compose -f deploy/compose.judge.yaml up -d --remove-orphans
     ```
     Then write "redeployed" here. The second line moves aside an untracked pre-review copy that
     would otherwise block the pull. The backup line takes a pre-deploy backup with the reviewed
     script and reinstalls the nightly cron. The next run verifies the result and does the live
     checks, at most 17 paid calls within the daily cap.
     Rollback: `sudo docker tag shiftguard:judge-prev-e249b72 shiftguard:judge`, then the same `up -d` command.
   - **Or allow the autopilot to deploy:** add a Claude Code permission rule for this project that
     allows SSH deploy commands to `ubuntu@130.210.3.156`, and write "deploy: allowed" here.
   Status:
