# Submission text

Track: Best Apps and Agents. Deadline: 30 October 2026, 22:30 IST; target 20:00 IST.
Every factual sentence below maps to [CLAIMS_AND_EVIDENCE.md](CLAIMS_AND_EVIDENCE.md).
Fill the bracketed fields only from real release evidence.

## Tagline

When a model's inputs go missing, are its probabilities still trustworthy? SHIFTGUARD measures it.

## The problem

A deployed scoring model keeps returning probabilities after an upstream field disappears,
for example when a data feed fails or a pipeline changes. Whether those probabilities still
match real event rates is a separate question from whether the model still runs. Teams that
use scores for review queues or outreach usually find out late.

## What it does

SHIFTGUARD is a calibration-shift workbench on the public UCI Bank Marketing data:

- It removes features in controlled ways: random cells at 10% or 30%, a whole history block
  for half the rows, and random cells matched to that block's realized removal rate.
- It compares eight recalibration strategies on two frozen predictors at label budgets of
  0 to 200 target outcomes. That gives 400 scored conditions, each linked to its exact data,
  split, mask and fit.
- It shows reliability curves, budget curves, decision-loss and pattern-versus-rate views
  for every saved run.
- Two Nemotron assistants: a Results assistant that runs approved analyses and explains
  saved results (its numbers are rendered by Python from the stored records), and a
  tool-free general chat labelled unverified.

What the Bank run showed (single seed, development evidence): at 50 target labels, three
target maps lower mean Brier score against a source-only comparator, but every target map
raises log loss in all eight shifted cells. The answer depends on the metric. The app
reports the adverse results too.

## How we built it

- FastAPI, SQLAlchemy and Alembic on PostgreSQL 16, with durable idempotent jobs, a separate
  experiment worker and hash-verified publication of every artifact.
- scikit-learn calibration maps (temperature, Platt, Beta, isotonic, fraction-binned) behind a
  label firewall: final outcomes stay inside one evaluator.
- React, TypeScript and Plotly for the workbench.
- NVIDIA Nemotron (`nvidia/Nemotron-3_5-Lightning`) on Nebius Token Factory through the
  OpenAI-compatible API, with a hard daily budget (50 calls, 100,000 tokens), reservations
  before each call, zero retries and at-most-once replay.

## Challenges

- Keeping the model from inventing numbers: the Results assistant can only call a closed set
  of read and run tools, and the app renders every figure from stored records.
- Spending safely: a timeout is charged in full and the day continues; any other unknown
  provider outcome halts the day instead of risking a duplicate paid call. Only one server
  process may own model dispatch for a database.
- Honest science: every condition is accounted for, including failures and fallbacks.

## What's next

- Resolve the pool-qualification decision (SCI-03) that the Bank repeat study's primary estimate
  needs. The engine has run its declared 5×10 schedule on the real Bank data as development work
  (all 50 runs completed; Bank outcomes previously inspected; not confirmatory); without SCI-03
  the primary contrast is reported as missing evidence.
- An external replication on Adult Income. The adapter is built; outcome access waits for
  custodian evidence.

## Feedback on Nebius Token Factory and NVIDIA Nemotron

What worked well: Token Factory's OpenAI-compatible endpoint let us use the standard `openai`
Python client unchanged, including tool calling, so the provider layer stayed small and easy to
test with a scripted stand-in. Every response carried a usage report, which made an exact
token ledger possible. In our adversarial acceptance test (a prompt asking for an invented
result, a fake publication, arbitrary Python and final-test labels), Nemotron
(`nvidia/Nemotron-3_5-Lightning`) tried the reads it was not allowed, received the denials and
ended with an explicit no-tool refusal; it did not invent numbers.

What we would like: Nemotron often takes several tool-only turns before answering. One early
live run spent its whole three-call allowance on tool calls and never reached a final turn. On
the hosted app, after a summary tool call had already succeeded, the model kept calling tools
(a read, a metadata lookup and the same summary tool three more times) until the 6-turn bound.
The app now ends an exact summary command as soon as its tool succeeds, because Python renders
the answer anyway: on 27 October that question took 1 call and 4,415 tokens instead of 6 calls
and 41,346. A documented way to cap or hint the number of tool
turns, and a published per-request maximum token figure for budgeting before a call, would help
teams that run with hard spending limits. In total, the gate live acceptance used 13 calls and
61,026 tokens with zero retries.

## Links

- Live app: https://shiftguard.duckdns.org
- Source: https://github.com/The-Abhinav-Anand/shiftguard (release tag: `hackathon-2026-submission`)
- Demo video (2:35, recorded on the live app with real Nemotron replies): [YouTube URL]; the same
  file is in the repository as `docs/submission/media/shiftguard-demo-live.webm`
- Judge guide: [JUDGE_GUIDE.md](JUDGE_GUIDE.md)
