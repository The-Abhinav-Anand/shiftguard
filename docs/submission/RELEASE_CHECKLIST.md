# Release checklist

Status values: DONE (with evidence path), PENDING, BLOCKED (with the missing input and owner).
Dates are IST. Official deadline 30 October 2026 22:30; target submission 20:00.

| # | Item | Status | Evidence / owner |
|---|---|---|---|
| 1 | Correction batch (OR-01–OR-09) verified on one frozen source | PENDING | `verification/opus-corrections-…/correction-review.json` |
| 2 | Source commit of the verified tree | BLOCKED | Owner authorization |
| 3 | Linux image built from that commit; base-image digests and image ID recorded | PENDING | Gate 10 evidence |
| 4 | Linux ownership-lock (`fcntl`) path exercised in the image | PENDING | Gate 10 evidence |
| 5 | Hosting account/project and its cost approved | BLOCKED | Owner |
| 6 | HTTPS URL serving the exact image; PostgreSQL 16 and artifact volumes backed up together | PENDING | Gate 10 evidence |
| 7 | `scripts/check_hosted_release.py` PASS against the HTTPS URL | PENDING | probe report |
| 8 | Restart API and worker mid-job: correct final state, no duplicate publication | PENDING | Gate 10 evidence |
| 9 | Second provider-enabled API refused against the live database | PENDING | Gate 10 evidence |
| 10 | Secret scan: built assets, image history, logs, repository diff | PENDING | scan report (locations only) |
| 11 | Specific live allowance authorized; one general-chat and one Results exchange recorded | BLOCKED | Owner authorization; live record |
| 12 | Judge capacity/access arrangement agreed and written in JUDGE_GUIDE | BLOCKED | Owner |
| 13 | README setup verified from a clean checkout; THIRD_PARTY_NOTICES audited | PENDING | |
| 14 | Public repository published; visibility checked from a signed-out session | BLOCKED | Owner authorization |
| 15 | Demo video recorded from the release build, public on YouTube, under 3:00 | PENDING | Owner uploads |
| 16 | Devpost form: track, links, sponsor feedback; eligibility confirmed | BLOCKED | Owner (account holder) |
| 17 | Clean-profile rehearsal on a second device/network | PENDING | |
| 18 | Service and judge access kept available through 16 December 2026 01:30 IST | PENDING | Owner names who monitors hosting and credits |

Release identity (fill at release): commit `[sha]`, tag `[tag]`, image `[digest]`, source manifest `[path, sha256]`, published experiment used in the demo `[experiment_id]`.
