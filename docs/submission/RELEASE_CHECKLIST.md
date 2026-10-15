# Release checklist

Status values: DONE (with evidence path), PENDING, BLOCKED (with the missing input and owner).
Dates are IST. Official deadline 30 October 2026 22:30; target submission 20:00.

| # | Item | Status | Evidence / owner |
|---|---|---|---|
| 1 | Correction batch (OR-01–OR-09) verified on one frozen source | DONE | `verification/opus-corrections-20261014T143057Z-…/correction-review.json` (executor verification, not an independent review) |
| 2 | Source commit of the verified tree | DONE | `9e39afd` (owner authorized commits on 15 Oct) |
| 3 | Linux image built from that commit; base-image digests and image ID recorded | DONE locally | `verification/gate10-image-20261014T184638Z-…/` (`base-images.txt`, image `c00425ec34d4`); rebuild on the VM at release |
| 4 | Linux ownership-lock (`fcntl`) path exercised in the image | DONE | `linux-owner-probe.json` in the Gate 10 evidence |
| 5 | Hosting account and VM | BLOCKED | Owner: Oracle Always Free VM (OWNER_ACTIONS item 2); cost $0; domain `shiftguard.duckdns.org` ready |
| 6 | HTTPS URL serving the release image; PostgreSQL 16 and artifact volumes backed up together | PENDING | `deploy/bootstrap-vm.sh` + Caddy ready (`7d84ae9`); needs item 5 |
| 7 | `scripts/check_hosted_release.py` PASS against the HTTPS URL | PENDING | Fresh local clone PASS for all three presets (15 Oct); hosted run needs item 5 |
| 8 | Restart API and worker mid-job: correct final state, no duplicate publication | DONE locally | `restart-probe-r3.json`; repeat on the VM |
| 9 | Second provider-enabled API refused against the live database | DONE locally | `second-owner-r3-image2.log`; repeat on the VM |
| 10 | Secret scan: built assets, image history, logs, repository history | PARTIAL | Local image/logs clean (Gate 10 evidence); git history scan before every push; hosted logs after deploy |
| 11 | Live check: one general-chat and one Results exchange within 50 calls / 100,000 tokens | PENDING | Allowance set by owner (`44210bb`); key copy approved; needs item 5 |
| 12 | Judge capacity arrangement written in JUDGE_GUIDE | DONE | Shared daily allowance; stated in `JUDGE_GUIDE.md` |
| 13 | README setup verified from a clean checkout; THIRD_PARTY_NOTICES audited | DONE | Fresh clone 15 Oct: setup, readiness, probe PASS (`verification/quickstart-20261015T073708Z/`); notices audited in `4f3f2cc` |
| 14 | Public repository published; visibility checked signed out | PENDING | `gh` signed in; push after the history secret scan |
| 15 | Demo video under 3:00, public on YouTube | PENDING | Recorded 2:07 (`8d94d07`); owner uploads (OWNER_ACTIONS item 5) |
| 16 | Devpost form: track, links, sponsor feedback; eligibility confirmed | PENDING | Text ready in `DEVPOST_FORM.md`; owner submits |
| 17 | Clean-profile rehearsal on a second device/network | PENDING | After the hosted release |
| 18 | Service kept available through 16 December 2026 01:30 IST | PENDING | Autopilot weekly health check after 30 Oct |

Release identity (fill at release): commit `[sha]`, tag `[tag]`, image `[digest]`, source manifest `[path, sha256]`, published experiment used in the demo `[experiment_id]`.
