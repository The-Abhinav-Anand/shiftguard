# Submission text (draft)

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
  OpenAI-compatible API, with a hard daily budget (10 calls, 50,000 tokens), reservations
  before each call, zero retries and at-most-once replay.

## Challenges

- Keeping the model from inventing numbers: the Results assistant can only call a closed set
  of read and run tools, and the app renders every figure from stored records.
- Spending safely: an unknown provider outcome halts the day instead of risking a duplicate
  paid call. Only one server process may own model dispatch for a database.
- Honest science: every condition is accounted for, including failures and fallbacks.

## What's next

- A pre-registered multi-seed repeat study on Bank. The repeat engine is built and tested
  on fabricated data only.
- An external replication on Adult Income. The adapter is built; outcome access waits for
  custodian evidence.

## Links

- Live app: [HTTPS URL — set after Gate 10 acceptance]
- Source: [public repository URL and release tag]
- Demo video (under 3 minutes): [YouTube URL]
- Judge guide: [JUDGE_GUIDE.md](JUDGE_GUIDE.md)
