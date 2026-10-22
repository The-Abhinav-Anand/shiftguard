# Release checklist

Status values: DONE (with evidence path), PENDING, BLOCKED (with the missing input and owner).
Dates are IST. Official deadline 30 October 2026 22:30; target submission 20:00.

| # | Item | Status | Evidence / owner |
|---|---|---|---|
| 1 | Correction batch (OR-01–OR-09) verified on one frozen source | DONE | `verification/opus-corrections-20261014T143057Z-…/correction-review.json` (executor verification, not an independent review) |
| 2 | Source commit of the verified tree | DONE | `9e39afd` (owner authorized commits on 15 Oct) |
| 3 | Linux image built from that commit; base-image digests and image ID recorded | DONE locally | `verification/gate10-image-20261014T184638Z-…/` (`base-images.txt`, image `c00425ec34d4`); rebuild on the VM at release |
| 4 | Linux ownership-lock (`fcntl`) path exercised in the image | DONE | `linux-owner-probe.json` in the Gate 10 evidence |
| 5 | Hosting account and VM | DONE | Oracle Always Free VM.Standard.E2.1.Micro (x86_64, 1 GB + 2 GB swap); `shiftguard.duckdns.org`; cost $0 |
| 6 | HTTPS URL serving the release image; PostgreSQL 16 and artifact volumes backed up together | DONE | https://shiftguard.duckdns.org serves the release image from `3421378` (VM image `sha256:c5cd193c…`, bundle `index-Bk6b9ZMP.js`), deployed 22 Oct with the reviewed script (`verification/gate10-redeploy-20261022T061002Z/redeploy.log`: REDEPLOY OK). The reviewed `deploy/backup.sh` took a pre-deploy set (checksums OK; it only keeps a set after `pg_restore --list` passes) and installed the 03:15 UTC cron (`backup-evidence.txt`). Certificate valid to 2027-01-13 |
| 7 | `scripts/check_hosted_release.py` PASS against the HTTPS URL | DONE | All three presets PASS on the VM (`verification/gate10-hosted-20261015T100844Z/probe-*.json`). Baseline `5c1ec846…` and stress `09b7b8c0…` match the local Linux image probes (r3); outage-50 `ffd11467…` has no local Linux counterpart; Windows quickstart IDs differ by platform |
| 8 | Restart API and worker mid-job: correct final state, no duplicate publication | DONE | VM: worker killed mid-job and API restarted; the job completed on attempt 2 and published once (`verification/gate10-hosted-restart/per-job-publications.txt`: 2 jobs for the experiment, at most 1 publication per job); artifacts match before and after a stack restart. The original run's pass rule wrongly counted per experiment; the corrected verdict and the fixed script are in the same folder |
| 9 | Second provider-enabled API refused against the live database | DONE | VM: `OrdinaryOwnerUnavailable`, site stayed ready (same evidence file) |
| 10 | Secret scan: built assets, image history, logs, repository history | DONE | Image `0c666412…` (served as `c5cd193c…`): config, history and all 15 layers, 0 hits (`verification/autopilot-20261019-run13/TRIAGE.md`). Repository object store and bundle: 0 hits. Containers running the released image (api, worker, postgres, caddy) on 22 Oct: 0 hits for the API key, DB password or URL (`verification/gate10-redeploy-20261022T061002Z/hosted-secret-scan.txt`). Open nits: 105 compressed in-image files not decompressed; local test-DB password rotation |
| 11 | Live check: one general-chat and one Results exchange within 50 calls / 100,000 tokens | PARTIAL | General chat PASS (15 Oct). Results on the fixed build, 22 Oct: the first provider call exceeded the 25 s timeout, so the halt-on-unknown policy stopped the day's ledger (1 call, 17,233 tokens reserved and charged; no fabricated output). The VM timeout is raised to 55 s (network to Nebius is 0.4 s). Recheck after the 05:30 IST reset (`verification/gate10-redeploy-20261022T061002Z/live-summarize.json`) |
| 12 | Judge capacity arrangement written in JUDGE_GUIDE | DONE | Shared daily allowance; stated in `JUDGE_GUIDE.md` |
| 13 | README setup verified from a clean checkout; THIRD_PARTY_NOTICES audited | DONE | Fresh clone 15 Oct: setup, readiness, probe PASS (`verification/quickstart-20261015T073708Z/`); notices audited in `4f3f2cc` |
| 14 | Public repository published; visibility checked signed out | DONE | https://github.com/The-Abhinav-Anand/shiftguard (public; raw files fetched anonymously by the VM bootstrap) |
| 15 | Demo video under 3:00, public on YouTube | PENDING | Recorded 2:07 (`8d94d07`); owner uploads (OWNER_ACTIONS item 5) |
| 16 | Devpost form: track, links, sponsor feedback; eligibility confirmed | PENDING | Text ready in `DEVPOST_FORM.md`; owner submits |
| 17 | Clean-profile rehearsal on a second device/network | PENDING | After the hosted release |
| 18 | Service kept available through 16 December 2026 01:30 IST | PENDING | Autopilot weekly health check after 30 Oct |

Release identity (fill at release): commit `[sha]`, tag `[tag]`, image `[digest]`, source manifest `[path, sha256]`, published experiment used in the demo `[experiment_id]`.
