# SHIFTGUARD operating contract

## Scope and continuity
- SHIFTGUARD is a calibration-shift research engine.
- Continue the retained repository; never recreate the foundation.
- Repository: C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard.
- Outer root: C:/Users/Abhinav Anand/Downloads/nvidia.
- Active branch: implementation/gate-0.
- Read .agent/session-state.md for the live subtask.
- Read .agent/gates.json for accepted and frozen commits.
- Read .agent/ownership.json before writing.
- Gate status and next authorized batch are recorded in .agent/gates.json and .agent/session-state.md.
- Never infer acceptance from passing author tests.
- No staging or commit before parent verification and authorization.

## Authoritative paths
- Current workflow: docs/loop-engineering.md (user-directed Antigravity coding / Astra Extra High review workflow, effective 28 September 2026).
- Next implementation packet: docs/next-execution.md (Gate 6; prepared, not started). Gate 4 closure records are historical accepted evidence.
- The 26 September Luna coding assignment is superseded by the 28 September Antigravity instruction; preserve historical authorship.
- Latest review: docs/gate5-correction-review.md; parent acceptance: docs/gate5-acceptance.md. Gate 4 evidence remains historical.
- Fix ledger: docs/fix-ledger.md.
- Blueprint: ../SHIFTGUARD_Implementation_Blueprint_v2_2026-09-09.md.
- Plan: ../docs/aegis/plans/2026-09-10-shiftguard-hackathon-execution-plan.md.
- Gate3 contract: docs/gate3-development-contract.md.
- Parent owns outer evidence and independent verification.
- Retrieve only relevant sections; no full-document reload.
- Scientific protocol and operational controls are separate.
- This file does not amend scientific choices.

## Ownership and escalation
- Assigned bulk writer: Antigravity, using the user-configured coding model; do not invent its model setting.
- One agent writes the application branch at a time.
- .agent/ownership.json is the canonical current writer assignment.
- Parent verifies evidence and may maintain governance/checkpoint files under user authorization.
- Independent planner/reviewer: GPT-6 Astra, reasoning effort `xhigh` (Extra High); never a concurrent application writer.
- Do not dispatch Luna, Terra or Sol as application writers under this assignment.
- Antigravity implements complete vertical batches and all ordinary corrections. Astra reviews one completed batch, then only correction deltas and affected invariants.
- Two correction cycles without verified progress trigger Astra root-cause diagnosis and a revised Antigravity brief, not an endless repeat or automatic acceptance.
- Complete coherent atomic batches before seeking review.
- Ordinary failures stay with the active writer.
- Capture the exact failure and make evidence-based fixes.
- Escalate protocol contradictions, leakage, or architecture decisions.
- Read .agent/handoff.json for current transfer status.
- Model ownership is a workflow assignment, not an acceptance claim.

## Resume and checkpoint
- Read AGENTS.md and .agent/session-state.md first.
- Inspect ownership and gate ledger.
- Inspect active-gate criteria, status, and relevant diff only.
- Preserve dirty and untracked work from the retained batch.
- Do not reset, clean, or switch the application checkout.
- Do not open or modify the frozen verification clone.
- Do not repeat literature or architecture discovery.
- Resume the recorded next task without restarting.
- Keep .agent/HANDOFF.md human-readable and compact.
- Keep .agent/handoff.json machine-readable and truthful.
- Record PASS, FAIL, or NOT_RUN explicitly.
- Inactive handoff files do not authorize a transfer.
- Keep exact commands and evidence references in session state.

## Verification and review
- Finish the batch, then run local targeted tests.
- Fix failures before handing the candidate to parent.
- Parent performs independent verification.
- One consolidated Astra Extra High review occurs at batch/gate exit.
- Do not repeatedly request ordinary code review.
- Do not rerun frozen gates without an affected invariant.
- Record affected frozen gates when shared behavior changes.
- Parent owns full-suite and clean-checkout verification.
- No duplicate Docker, PostgreSQL, or browser setup by the writer.
- Do not claim a clean checkout or live service check without running it.
- Record harmful and null evidence unchanged.
- Source acceptance requires the reviewer and parent, not this writer.
- Gate closure also requires a verified checkpoint/commit.

## Core implementation owners
- datasets/bank.py validates and cleans Bank inputs.
- protocol/splits.py owns disjoint role membership.
- protocol/acquisition.py owns label-blind target ordering/reveal.
- preprocessing/tabular.py owns training-fitted transformation.
- predictors/logistic.py owns the initial logistic predictor.
- missingness/base.py and block.py own raw history masks/rates.
- calibration/base.py and sklearn_maps.py own map fitting/fallback.
- experiments/config.py owns frozen run configuration.
- experiments/runner.py preserves Gate1 execution.
- experiments/outage_runner.py owns the bounded Gate2 slice.
- experiments/evaluator.py alone scores final-test outcomes.
- experiments/artifacts.py and ids.py own bytes and content identity.
- storage/repositories.py owns immutable records and execution audits.
- Extend these owners; do not add a general experiment framework.

## Scientific invariants
- Current execution is development only, seed 31001.
- Confirmatory runs remain forbidden until protocol lock.
- Bank inputs must match the frozen official manifest and hashes.
- Features: age, job, marital, education, default, housing, loan.
- Remaining features: pdays, previous, poutcome.
- Exclude all other predictors, including duration.
- Preserve literal unknown, pdays=999, and poutcome=nonexistent.
- Do not normalize structural sentinels during engineering fixes.
- Stable raw row IDs survive cleaning and splitting.
- Roles remain 55% train, 15% source calibration, 10% pool, 20% final.
- Preserve inherited stratification, rounding, and duplicate policy.
- Pool records are never development or predictor-training data.
- Fit preprocessing and logistic regression exclusively on train.
- Numeric median imputation and scaling remain frozen after fitting.
- Categorical missing handling and OHE vocabulary remain frozen.
- Held-out unknown categories transform without refitting.
- Both temperature maps wrap the same original fitted pipeline.
- Use FrozenEstimator and CalibratedClassifierCV(method="temperature").
- Source calibration uses unchanged source calibration rows.
- Target calibration is independent of the source calibrator fit.
- Target fit uses only the acquired masked target subset.
- History block is pdays, previous, poutcome.
- Gate2 requested row outage probability is 0.5.
- Mask raw features before frozen imputation.
- Freeze the full pool mask before label reveal.
- Acquire exactly the nested label-blind prefix of 50.
- Never redraw or enlarge a one-class/failed calibration sample.
- Use independent pool/test mask streams.
- Pair methods on the identical final-test mask and row order.
- Final labels remain inside the evaluator boundary.
- Resolve prediction fallbacks before accessing final outcomes.
- Source fallback is raw; target fallback is frozen source then raw.
- Failed raw prediction produces null metrics, never fake scores.
- Comparisons involving failed conditions are unavailable.

## Numerical and provenance invariants
- Binary Brier with scale_by_half=True is binary MSE.
- Log loss uses declared clipping at 1e-15.
- Reliability uses ten equal-width bins.
- Empty reliability bins have null observed statistics.
- Persist denominator counts for every missingness rate.
- Overall new missingness denominator is observed cells across all ten features.
- Name observed history-group eligibility separately.
- Persist full-pool, acquired-subset, and test rates separately.
- Fit failure counts are per unique calibrator.
- Prediction failures count unique map/regime attempts.
- Source fallback reuse must not double count failures.
- Persist dataset, split, mask, order, predictor, and map identities.
- Condition identities bind dataset and evaluation-row context.
- Artifact hashes are SHA-256 of actual saved UTF-8 bytes.
- Canonical JSON uses fixed LF newline.
- Keep logical content identity separate from file-byte hashes.
- UUID execution and Git/runtime audit metadata stay outside numerical identity.
- Identical reruns retain immutable content and append execution audits.
- Preserve old artifacts; use a durable exclusion/replacement ledger.
- Artifact 9f03fb4fb650104b54105f56 is INVALID for analysis/fallback rates.
- Artifact 8d89c7f4a2a7a31fe2ea9392 is an unaccepted initial review candidate.
- Ledger: docs/submission-evidence/gate2-artifact-status.json.

## Database and runtime
- Python 3.13 and scikit-learn 1.9.0 stay pinned.
- Canonical database setting is SHIFTGUARD_DB_URL.
- Local SQLite must be on local disk with a safe runtime and WAL.
- Refuse memory/unsupported URI modes and shared/network WAL storage.
- Hosted profile uses PostgreSQL16 with psycopg3.
- All application/direct migrations use validated settings and DB factory.
- Do not edit applied migrations; additions require new revisions.
- Gate2 reuses the existing experiment/audit schema.
- No global runtime installation or configuration.
- uv: ../.tools/uv-package/bin/uv.exe.
- Python: ../.tools/python/cpython-3.13-windows-x86_64-none/python.exe.
- UV_PYTHON_INSTALL_DIR: ../.tools/python.
- UV_CACHE_DIR: ../.tools/uv-cache.
- NPM_CONFIG_CACHE: ../.tools/npm-cache.
- Escalate narrowly when local executable ACLs block authorized commands.

## Current commands and protected boundaries
- Working directory for author commands is the application root (`shiftguard`).
- Targeted tests: `$t = Join-Path $env:TEMP ('sg-t-' + [guid]::NewGuid()); & .\.venv\Scripts\python.exe -B -m pytest <test-paths> -q -p no:cacheprovider --basetemp "$t" --tb=short`.
- Full suite: `$t = Join-Path $env:TEMP ('sg-t-' + [guid]::NewGuid()); & .\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp "$t" --tb=short`.
- Clean-commit verifier: `& .\.venv\Scripts\python.exe -B verification/verify_gate3_reproduction.py`.
- Use per-command git `-c safe.directory="C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard"`.
- Quote the entire safe.directory argument in PowerShell.
- Do not change global Git configuration.
- Gate 0 is frozen at a9d0aa0.
- Gate 1 is frozen at 6c4d682.
- Gate 2 is frozen at 937f33c (closure at c9cc001).
- Gate 3 hardened reproduction and Gate 4 acceptance are verified on 10170feab3c16c5eb61153d57d9e5879ba5a6fd6; see .agent/gates.json for evidence.
- Gate 5 is accepted on f63116fedc2751493d79d44897ba913b6d28b0b5; next is the prepared Gate 6 offline batch.
- Preserve research/*, including manuscript, builder, exports, and QA.
- Preserve ../SHIFTGUARD_Deep_Research.md, ../SHIFTGUARD_Deep_Research.pdf, ../SHIFTGUARD_Implementation_Blueprint_v2_2026-09-09.md.
- Preserve parent evidence, toolchain, and frozen verification clone.
- Do not access paid APIs, cloud services, or external publication.
- Do not log secrets or expose raw/final labels through artifacts.
- Do not bundle caches, secrets, or raw data in source control.
- Stop at the completed candidate and parent-verification boundary.

## Bounded Gate 4 closure
- Close R6-01 through R6-04 together using docs/gate4-closure.md and fixed I01-I08 contracts.
- Permanent guards: tests/acceptance/test_gate4_closure.py; do not xfail known defects.
- Evidence command: .venv/Scripts/python.exe -B scripts/check_gate4_closure.py.
- Run --candidate once guards, backend availability and clean-source prerequisites pass.
- Reuse exact-candidate evidence; repeat checks only for changed relevant source or a concrete uncovered contract.
- One compact handoff and acceptance review; do not restart broad codebase review for each patch.
- Missing service evidence is BLOCKED; author pass counts alone never close a finding.
- Optional cleanup, style and new features cannot expand this closure batch.
