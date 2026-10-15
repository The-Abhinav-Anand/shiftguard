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
