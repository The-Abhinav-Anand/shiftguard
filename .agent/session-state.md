# Current execution — correction batch checkpoint, 15 October 2026

Executor: Claude Code (claude-opus-5-5), with two Sonnet implementation subagents on disjoint files (chat A1/A2; repeat/Adult B1–B3). Executor verification only; this is not an independent review, and nothing has been committed.

- **Correction batch OR-01–OR-09:** all nine closed by executor verification.
  - Frozen source: `7c5027db…19b3e2`, 331 files, identical before and after the runs.
  - Checks: full suite 1,307 passed with 0 skipped (159 PostgreSQL cases); browser 67 passed with 3 real-server skips; asset parity 14/14; installed wheel PASS; corrected probes 8/8; numerical engine owners unchanged.
  - Record: `../../verification/opus-corrections-20261014T143057Z-e00915d6b06f4ca29296a9687592c006/correction-review.json` (sha256 `f14284c9…772f`). The initial review (CORRECTIONS_REQUIRED) is unchanged. Two earlier finalize outputs with a node-key bug are kept beside it under `attempt*` names.
- **Local runtime:** the server was restarted on the corrected code at http://127.0.0.1:8000. It holds the SQLite ordinary-owner lock `var/shiftguard.db.ordinary-owner.lock`. Readiness PASS; ledger 0/10 calls; no paid call made.
- **Gate 10 preparation (not acceptance):**
  - Files: `deploy/compose.judge.yaml`, the env examples, `deploy/README.md`, a nonroot single-worker `Dockerfile`, `.dockerignore`.
  - Readiness now checks the database, migration head, storage and the verified Bank dataset.
  - `scripts/check_hosted_release.py` is an offline probe with no model calls. It passed in-process against a real Bank job.
  - Not yet done: Linux image build and the `fcntl` ownership path.
- **Gate 11 drafts:** `docs/submission/` (claims, submission text, demo script, judge guide, release checklist).
- **Gates 8 and 9:** fabricated-data engineering only. Pending.

- **Gate 10 local Linux evidence:** `../../verification/gate10-image-20261014T184638Z-e606f2d016c8/`.
  - Image `shiftguard:judge-candidate`, ID `sha256:435e9e39…5efa`. Nonroot uid 10001, one Uvicorn worker. Frontend byte-identical to the served build. Image history has no secrets. Base digests are in `base-images.txt`.
  - Linux `fcntl` owner probe: PASS (`linux-owner-probe.json`).
  - CLI failure output leaks neither the password nor the API key marker (`cli-leak-before.txt`).
  - Local stack r3 (`run_stack.sh`, host networking because this daemon has no container DNS): offline release probe PASS (`probe-r3-baseline.json`).
  - 15 October, same stack: `restart-probe-r3.json` PASS. A bank-stress job survived a worker kill and an API restart and was published once. The same-key replay returned the same job. 10/10 artifact digests matched before and after an API redeploy. Cancellation worked.
  - Second provider-enabled API refused on PostgreSQL (`second-owner-r3-image2.log`). Peak memory: worker 315 MiB, API 161 MiB, PostgreSQL 37 MiB. Container logs and the served frontend: no password or URL.
  - Fixed and committed (`5d5671a`): alembic `fileConfig` had been disabling existing loggers at in-process startup.
  - Rebuilt image `c00425ec34d4`. Stack r3 torn down.

**15 October commits (owner authorized commits):**
- `9e39afd` corrections and scaffold.
- `44210bb` allowance raised to 50 calls / 100,000 tokens (owner-set; local server restarted on it).
- `2366e7c` launch plan: `docs/superpowers/plans/2026-10-15-launch-plan.md`.
- `5d5671a` logging fix.

Nothing pushed. Git history scan: no API key, `.env` or database files in any commit.

Next (launch plan Phase A): add a Caddy HTTPS service and `deploy/bootstrap-vm.sh`. Then the owner's hosting choice (Oracle Always Free recommended), GitHub repository and push method, and video date.

Open, in the owner's hands: source-commit authorization; hosting account and cost; a specific live allowance; the judge access/capacity arrangement; Devpost eligibility and submission.

# Previous checkpoint — Claude continuation, 12 October 2026

Executor: Claude Code (claude-opus-5-5). Everything below is executor verification. No independent review, source commit, paid provider call, flag change, deployment or scientific approval occurred. HEAD is still f3f696579345347884d547f7ec4c75a84ce21184 and is not the source identity. Frozen working tree: source_tree_sha256 `4fc45b03cc1d051b19dbc89e9de62bd665006ee0546a5f309d4bebf8324bd287`, served assets `87ba56100ae2b9402d29393be9c9ac0279e25736a36fc5a03768fd1e514f74ad`, identical before and after the evidence runs. Evidence: `../../verification/claude-continuation-5308e5ade8554dc2a1098e32c5f3aaf0/` (`summary.json`, both `source-binding-frozen-*.json`).

**Ordinary chat — IMPLEMENTED_DELTA_NOT_ACCEPTED.**

- Migration fixture closed: a rejected downgrade stays at 0012 on PostgreSQL (transactional DDL) and at 0011 on SQLite; the assertion is now dialect-specific with a matching table-presence check. No applied migration edited.
- Fixed test-first: a message rejected before any dispatch left a permanent PENDING receipt and a busy conversation. The provider now marks whether a request could have left the process and the route forgets only a definite non-dispatch.
- Fixed test-first: the general-chat flag alone let `/api/v1/agent/requests` dispatch. The provider now gates each mode on its own flag (`chat` for the results assistant, tool-free `general_chat`).
- Frontend: an unresolved reply is reported as pending and "New conversation" releases the panel; production assets rebuilt and reproduce byte-for-byte. `test_result_discovery` no longer depends on the kind of the newest saved record.
- Counts on the frozen tree: focused backend 67/67 on both backends; full suite 1004 = 1002 pass, 2 fail, 0 skip (119 PostgreSQL cases); full browser 55 pass, 1 fail, 3 skip; real API and embedded worker on an isolated replica of the runtime state 4/4 browser checks, job `f523d5d4-f098-4e66-9667-c6610ede3277` republished experiment `e90c4adbda3d53664a823f84`. The real `var/shiftguard.db` was not opened for writing and is still at revision 0011.

Open before acceptance and local activation (flags remain false/false):

1. `tests/agent/test_gate7_candidate_evidence.py` fails twice: the retained delta changes two Gate 7 protected contracts, `shiftguard/settings.py` and `shiftguard/api/main.py` (48/50 match, 11/11 applied migrations match). Extending that protected baseline is an acceptance decision and was not self-authorized.
2. Independent backend/science and frontend reviews: NOT_RUN.
3. `tests/e2e/test_product_refresh.spec.ts` F14 expects the pre-Gate-6 blocked-assistant banner; `BlockedAssistant` has been unmounted since 950d5cd, so it fails on HEAD as well. Left untouched.
4. Live provider proof: NOT_RUN (no current call/token ceiling).

For the reviewer, observed and not changed: 0012's downgrade drops the ordinary ledger without a data guard; a dispatched reply that is then rejected stays PENDING; a conversation is bounded by the provider's 64-message limit; no test yet for concurrent same-key chat replay, the cancelled-coroutine path or cross-session append.

**Gate 8 P2 — IMPLEMENTED_SYNTHETIC_ONLY_NOT_ACCEPTED.** `shiftguard/repeats/` (models, seeds, planning, validation, aggregation, uncertainty, completion, synthetic_store) with `tests/repeats/` (186 pass; golden seed digest `68900ea10536435e183f1f57d47154281f7c32db34a5f837b369330693bbffee`; 93–98% line coverage per module by the standard-library tracer). Fabricated fixtures only; no loader, runner, evaluator, label or provider is imported or reached. The plan's `test_validation.py` is named `test_repeat_validation.py` because `tests/unit/test_validation.py` already owns that basename. Gate 8 stays PROTOCOL_PREPARATION_IN_PROGRESS and DRAFT_NOT_LOCKED; EXT-HUMAN-APPROVER, EXT-CUSTODIAN-EXPOSURE, EXT-SCI-03/04-AUTHORITY, EXT-EVALUATION-BINDING and EXT-FEATURE-GROUP-AUDIT are unchanged and INT-RESOURCE-PREFLIGHT is unmeasured.

**Governance and document follow-ups, same day (no source change; frozen tree digest unaffected).**

- `.agent/gates.json` gate_7: `acceptance_record` and `next` now follow the final live packet `../verification/gate7-live-completion-20261008/acceptance.json` (sha256 `33bd1908…dbc23`, status ACCEPTED_COMPLETED_LIVE_POLICY_DENIAL). The earlier pointer and prose are kept as `superseded_*`; no status or binding changed.
- Faculty guide: `../../verification/faculty-docx-reconciliation-20261012/record.json`. Markdown and PDF match their 10 October record and the PDF contains every source block. The DOCX does not: Word re-saved it at 16:09 on 10 October, four minutes after the record, with the title shortened to "SHIFTGUARD" and the Purpose paragraph, "How to use this guide" and the 27-entry Contents removed (36 of 709 text blocks). The other 673 blocks, 27 chapter bookmarks, 55 questions and 8 metric deltas are intact. The DOCX and the historical record were not modified.

**14 October 2026 — user instructed "make this work"; all suites green, activation not yet performed.** Frozen tree `6a3c4bcf06a52cde3053efbc0be786dbf00df454a244c9077e7fb4b64f8ba801` (served assets unchanged, `87ba5610…`), identical before and after the runs. Evidence: `../../verification/claude-activation-158abcc270004800946a88716f5096f0/`.

- `scripts/check_gate7_candidate.py` now accepts exactly the default-off ordinary-chat additions to `shiftguard/settings.py` and `shiftguard/api/main.py` (50/50 protected contracts, 48 byte-identical, 11/11 migrations); new negative probes reject a default-on flag and any other app-factory change. This closes item 1 above on the user's instruction, without an independent review.
- F14 rewritten for the accepted post-Gate-6 UI (paused assistant, inputs disabled, only the status read attempted). Added a cross-session append/replay test.
- Full backend suite 1009/1009 on both backends, 0 skipped; full browser suite 56 pass, 0 fail, 3 skip (the real-server tests).
- Activation (flags to true in `.env`, backup of `var/shiftguard.db`, `scripts/start-local.ps1`) was blocked by the session's permission policy and did NOT happen: flags are still false/false, no server is running, the real database is still at 0011. Independent review and live provider proof remain NOT_RUN.

Next bounded action: the user runs the activation commands or permits them; then one real chat message as live proof. `handoff.json` and `HANDOFF.md` were not edited and still describe the pre-execution transfer state.

## Retained transfer note — 12 October 2026

The user requested transfer to Claude Code Opus 5.5. Receiving instructions are in ../CLAUDE.md and ../../deliverables/claude-handoff-20261012/PROJECT_HANDOFF.md; execution plan: ../docs/superpowers/plans/2026-10-12-claude-project-continuation.md. Previous model staffing below is historical. Transfer preparation changes no source implementation, accepted gate, runtime flag, paid allowance or scientific lock. Claude has not yet executed the plan.

## Retained cleanup checkpoint — 11 October 2026

Project cleanup is complete: 12,213 disposable files removed; 40 offline product tests and frontend typechecking PASS. Next resume the unfinished ordinary Nemotron chat and Gate 8 work. This cleanup does not accept that candidate, enable local flags, spend provider credits or change scientific policy.

Resume implementation from `../../docs/aegis/work/2026-10-09-nemotron-gate8/20-checkpoint.md` in the outer workspace after cleanup. Ordinary chat is implemented but awaits the remaining migration-fixture check, parent frontend build/integration verification and independent review. Flags were verified False/False on 10 October; no current enablement is inferred from source files.

Gate 8 P1 technical review is complete, with all 15 P/U decisions mapped. P2 seed/aggregation engineering is not implemented. Protocol remains DRAFT_NOT_LOCKED; synthetic engineering is permitted under the existing packet, while confirmatory scoring requires the actual custodian, scientific approval and exposure evidence.

Retained source baseline: f3f696579345347884d547f7ec4c75a84ce21184 on implementation/gate-0. Preserve all dirty and untracked code. Gates 0–7 retain their accepted/frozen evidence; use .agent/gates.json for exact bindings. Historical paid allowances are sealed.

The implementation roles remain the 9 October assignment: Hegel / GPT-6 Luna xhigh backend/chat, Nash / GPT-6 Luna xhigh frontend, Kant / GPT-6 Astra xhigh scientific decision review. Parent owns integration, runtime, evidence and governance; Astra reviews backend/science, Sol6.1 xhigh reviews affected frontend. No Antigravity. Old assignments in the history archive are superseded.

Current work evidence: `../../verification/nemotron-gate8-20261009/`. Cleanup evidence: `../../verification/cleanup-20261011/`. The faculty guide and research manuscripts remain retained. No automatic paid checks, installation, deployment, push or outcome access is part of cleanup.

## Retained history

Repeated and superseded checkpoints from these four files are preserved byte-for-byte in `history/checkpoints-before-cleanup-20261011.zip`, including an internal SHA-256 manifest. Current acceptance reports, test reports, usage ledgers and scientific artifacts remain at their original paths. Archived instructions cannot revive old allowances or writer assignments.
