# Documentation

## Start here

| Document | What it covers |
|---|---|
| [../README.md](../README.md) | What SHIFTGUARD is, who it is for, quickstart, architecture, limits |
| [ordinary-chat.md](ordinary-chat.md) | The Results assistant, general chat and the shared daily model allowance |
| [../deploy/README.md](../deploy/README.md) | Hosting the judge stack: one-command VM setup, HTTPS, readiness, backups |
| [ADAPTING.md](ADAPTING.md) | What it takes to evaluate your own tabular dataset |
| [submission/JUDGE_GUIDE.md](submission/JUDGE_GUIDE.md) | A five-minute path through the live app |
| [submission/CLAIMS_AND_EVIDENCE.md](submission/CLAIMS_AND_EVIDENCE.md) | Every public claim, its evidence and its stated limits |
| [submission/](submission/) | Submission text, demo script and release checklist |

## Engineering log

Everything below is the record kept while building SHIFTGUARD. It is history, not user
documentation. The work was organised in gates: each gate had a written contract, an
implementation batch, a review, corrections where the review found problems, and an
acceptance record. The documents are kept as written at the time, including findings that
were later corrected and staffing that later changed, so some statements in them are out of
date. Where they disagree with the code or with the documents above, the code and the
documents above are current.

| Gate | Scope | Records |
|---|---|---|
| 0–2 | Bootstrap, deterministic Bank baseline, outage and recalibration slice | [submission-evidence/](submission-evidence/), [fix-ledger.md](fix-ledger.md) |
| 3 | 400-condition development stress engine | [gate3-development-contract.md](gate3-development-contract.md) |
| 4 | API and durable worker backend | [gate4-runtime-contract.md](gate4-runtime-contract.md), [gate4-closure.md](gate4-closure.md), [gate4-closure-review.md](gate4-closure-review.md), [gate4-acceptance.json](gate4-acceptance.json) |
| 5 | Browser workbench, saved results, scientific views | [gate5-implementation.md](gate5-implementation.md), [gate5-batch.md](gate5-batch.md), [gate5-review.md](gate5-review.md), [gate5-corrections.md](gate5-corrections.md), [gate5-correction-review.md](gate5-correction-review.md), [gate5-acceptance.md](gate5-acceptance.md) |
| 6 | Results assistant on Nemotron with approved tools | [gate6-execution-plan.md](gate6-execution-plan.md), [gate6-implementation.md](gate6-implementation.md), [gate6-batch.md](gate6-batch.md), reviews (`gate6-*review*.md`), corrections (`gate6-corrections*.md`), [gate6-live-verification.md](gate6-live-verification.md), [gate6-acceptance.md](gate6-acceptance.md) |
| 7 | Live policy and refusal evidence | [gate7-candidate-contract.md](gate7-candidate-contract.md), [gate7-execution-20261005.md](gate7-execution-20261005.md), [gate7-live-closure-20261008.md](gate7-live-closure-20261008.md), [gate7-acceptance.md](gate7-acceptance.md) |
| 8–9 | Multi-seed repeats (Gate 8: declared 5×10 schedule run on real Bank as development work, 50/50 completed, primary reported as missing evidence while SCI-03 is unresolved) and Adult replication (Gate 9: fabricated-data engineering only; pending) | [gate8-next-execution.md](gate8-next-execution.md), [research/gate8-run-manifest-bank-development-v1.json](research/gate8-run-manifest-bank-development-v1.json) |
| 10–11 | Hosted release and submission | [../deploy/README.md](../deploy/README.md), [submission/](submission/) |

Other working records:

- [blueprint-progress.md](blueprint-progress.md): progress against the implementation blueprint.
- [loop-engineering.md](loop-engineering.md), [antigravity-execution-prompt.md](antigravity-execution-prompt.md),
  [next-execution.md](next-execution.md): execution instructions for the agents that built it.
- [opus-review-20261014.md](opus-review-20261014.md): an executor's review that led to the
  OR-01 to OR-09 corrections.
- [frontend-results-fix-20261005.md](frontend-results-fix-20261005.md),
  [product-refresh-20260930/](product-refresh-20260930/): frontend redesign and cleanup records.
- [superpowers/plans/](superpowers/plans/): dated execution and launch plans.

Some engineering-log documents link to files outside this repository (the research workspace
and verification evidence). Those links do not resolve in the public repository.
