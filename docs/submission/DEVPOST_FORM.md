# Devpost form — ready to paste

Owner action on 29–30 October: open the hackathon's Devpost page → **Enter a submission** (or
edit the draft) → paste each field below → check the three links open from a signed-out
browser → press **Submit** before **30 October 2026, 20:00 IST** (official close 22:30 IST).
Fields in `[brackets]` are filled by the autopilot once the item exists; do not submit while any
bracket remains, except the hosted URL as described under "Try it out".

---

## Project name

SHIFTGUARD

## Elevator pitch (max 200 characters)

When a model's inputs go missing, are its probabilities still trustworthy? SHIFTGUARD rehearses field outages and measures calibration, decision loss and recovery cost.

## Track

Best Apps and Agents

## Built with

python, fastapi, sqlalchemy, alembic, postgresql, sqlite, scikit-learn, numpy, scipy, react, typescript, plotly, vite, playwright, docker, caddy, nvidia-nemotron, nebius-token-factory, openai-python

## Try it out (links)

- Live app: https://shiftguard.duckdns.org
- Source code: https://github.com/The-Abhinav-Anand/shiftguard
- Judge guide: https://github.com/The-Abhinav-Anand/shiftguard/blob/main/docs/submission/JUDGE_GUIDE.md

If the hosted app is not live by submission time, replace the live-app line with:
"Hosted demo pending; run locally in about a minute with the README quickstart, or watch the
video."

## Video demo link

[YouTube URL from OWNER_ACTIONS item 5]

## Image gallery

Upload, in this order, from `docs/submission/media/`: `02-workbench.png`, `04-budget-curve.png`,
`06-pattern-rate.png`, `07-results-assistant.png`, `01-about.png`.

## About the project (Markdown)

```markdown
## Inspiration

A deployed scoring model keeps returning probabilities after an upstream field disappears: a
data feed breaks, a schema changes, a customer withdraws consent. Whether the model still ranks
well and whether its probabilities still match real outcome rates are different questions.
Teams that act on thresholds (credit, fraud, outreach, triage queues) usually find out late.

## What it does

SHIFTGUARD is a calibration-shift workbench on the public UCI Bank Marketing data (41,188 rows):

- It removes inputs in controlled ways: random cells at 10% or 30%, the whole history block for
  half the rows, and random cells matched to that block's realized removal rate.
- It compares eight calibration conditions on two frozen predictors at label budgets of 0 to
  200 new outcomes: 400 scored conditions, each linked to its exact data, split, mask and fit.
- Every saved run has reliability curves, budget curves, decision loss, a pattern-versus-rate
  comparison, fallback details and a provenance panel with content hashes.
- Two NVIDIA Nemotron assistants on Nebius Token Factory: a **Results assistant** that may
  only call approved tools (inspect the dataset, run an approved preset, read saved results)
  and whose numbers are rendered by Python from stored records, and a tool-free **general
  chat** labelled unverified.

What the single-seed development run found: at 50 target labels, temperature, Platt and Beta
maps lower mean Brier score against a zero-label source comparator in 4 of 8 shifted cells
each, but every one raises log loss in all 8. The answer depends on the metric, and the app
shows the adverse results too.

## How we built it

- FastAPI, SQLAlchemy and Alembic on PostgreSQL 16, with durable idempotent jobs, a separate
  experiment worker and hash-verified, publish-once artifacts.
- scikit-learn calibration maps behind a label firewall: final-test outcomes are read only by
  the evaluator.
- React, TypeScript and Plotly for the workbench; Playwright browser tests.
- Nemotron (`nvidia/Nemotron-3_5-Lightning`) through Token Factory's OpenAI-compatible API,
  with a hard daily ledger of 50 calls and 100,000 tokens: reserve before each call, zero
  retries, halt the day on an unknown outcome (a timeout is charged in full instead),
  at-most-once chat replies.
- Docker, with Caddy for HTTPS, on one small VM.

## Challenges we ran into

- Keeping the model from inventing numbers: the assistant chooses tools; Python renders
  every figure from the stored record.
- Spending safely: a timeout is charged in full and the day continues; any other unknown
  provider outcome halts the day instead of risking a duplicate paid call, and only one
  server process may own model dispatch for a database.
- Honest accounting: every condition is reported, including failures and fallbacks.

## Accomplishments that we're proud of

- 400 paired conditions with every artifact content-hashed and traceable to its inputs.
- A live adversarial test where Nemotron was asked for an invented result, a fake publication,
  arbitrary Python and final-test labels: the app denied each attempt and the model ended with
  an explicit refusal, with no data changed.
- Jobs survive a worker kill and an API restart and are still published exactly once.

## What we learned

Brier score and log loss can disagree about whether recalibration helped, and the pattern of
missingness matters, not only its rate. On the agent side, bounding turns and spending up front
is easier than recovering from an overspend.

## What's next for SHIFTGUARD

- Resolve the pool-qualification decision (SCI-03) that the Bank repeat study's primary estimate
  needs. The engine has run its declared 5×10 schedule on the real Bank data as development work
  (all 50 runs completed; Bank outcomes previously inspected; not confirmatory); without SCI-03
  the primary contrast is reported as missing evidence.
- An external replication on UCI Adult (adapter built; not yet run on real outcomes).
- A local command-line path to evaluate your own CSV with no upload.

## Limits

Bank Marketing data only; single-seed development results without confidence intervals; no
uploads; not a new calibration algorithm. The shared model allowance can run out on a busy day;
the rest of the app keeps working.
```

## Sponsor feedback (if the form has a field for it)

Paste the "Feedback on Nebius Token Factory and NVIDIA Nemotron" section of
[SUBMISSION.md](SUBMISSION.md).

## Eligibility and declarations (owner checks these himself)

- Team members listed match the registered team.
- The project was built during the hackathon period under its rules.
- Runtime inference uses an NVIDIA open model on Nebius Token Factory.
