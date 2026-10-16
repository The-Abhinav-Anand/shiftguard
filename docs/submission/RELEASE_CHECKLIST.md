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
| 6 | HTTPS URL serving the release image; PostgreSQL 16 and artifact volumes backed up together | PARTIAL | https://shiftguard.duckdns.org is live (Let's Encrypt, valid to 2027-01-13: `verification/gate10-hosted-cert-20261016/certificate.txt`). Backups: a first set was taken with a pre-review script (no saved evidence; treat as unverified). The reviewed `deploy/backup.sh` (atomic sets, locking, scoped retention, timezone check, `pg_restore --list` check) will be installed and verified at the next redeploy; evidence goes to `verification/gate10-backups-*` |
| 7 | `scripts/check_hosted_release.py` PASS against the HTTPS URL | DONE | All three presets PASS on the VM (`verification/gate10-hosted-20261015T100844Z/probe-*.json`). Baseline `5c1ec846…` and stress `09b7b8c0…` match the local Linux image probes (r3); outage-50 `ffd11467…` has no local Linux counterpart; Windows quickstart IDs differ by platform |
| 8 | Restart API and worker mid-job: correct final state, no duplicate publication | DONE | VM: worker killed mid-job and API restarted; the job completed on attempt 2 and published once (`verification/gate10-hosted-restart/per-job-publications.txt`: 2 jobs for the experiment, at most 1 publication per job); artifacts match before and after a stack restart. The original run's pass rule wrongly counted per experiment; the corrected verdict and the fixed script are in the same folder |
| 9 | Second provider-enabled API refused against the live database | DONE | VM: `OrdinaryOwnerUnavailable`, site stayed ready (same evidence file) |
| 10 | Secret scan: built assets, image history, logs, repository history | PARTIAL | Hosted container logs: 0 hits for the key, DB password or URL. The served-asset scan covered only the entry chunk; rescanning all static files inside the image, and saving the repository-history scan output, at the next redeploy |
| 11 | Live check: one general-chat and one Results exchange within 50 calls / 100,000 tokens | PARTIAL | General chat PASS live. Results assistant FAILED twice: a free-form prompt has no read authority, and a full 400-condition read overflows provider bounds. Fix in progress (plan `2026-10-15-results-assistant-and-remaining-gates.md`) |
| 12 | Judge capacity arrangement written in JUDGE_GUIDE | DONE | Shared daily allowance; stated in `JUDGE_GUIDE.md` |
| 13 | README setup verified from a clean checkout; THIRD_PARTY_NOTICES audited | DONE | Fresh clone 15 Oct: setup, readiness, probe PASS (`verification/quickstart-20261015T073708Z/`); notices audited in `4f3f2cc` |
| 14 | Public repository published; visibility checked signed out | DONE | https://github.com/The-Abhinav-Anand/shiftguard (public; raw files fetched anonymously by the VM bootstrap) |
| 15 | Demo video under 3:00, public on YouTube | PENDING | Recorded 2:07 (`8d94d07`); owner uploads (OWNER_ACTIONS item 5) |
| 16 | Devpost form: track, links, sponsor feedback; eligibility confirmed | PENDING | Text ready in `DEVPOST_FORM.md`; owner submits |
| 17 | Clean-profile rehearsal on a second device/network | PENDING | After the hosted release |
| 18 | Service kept available through 16 December 2026 01:30 IST | PENDING | Autopilot weekly health check after 30 Oct |

Release identity (fill at release): commit `[sha]`, tag `[tag]`, image `[digest]`, source manifest `[path, sha256]`, published experiment used in the demo `[experiment_id]`.
