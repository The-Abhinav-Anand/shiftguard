# Claims and evidence

Every sentence in the submission, README, video and judge guide that states a result or a
capability must map to a row here. If a row's evidence changes, change the sentence.

| # | Claim we make | Evidence | Limits we state |
|---|---|---|---|
| C1 | SHIFTGUARD simulates feature loss on the UCI Bank Marketing data (cellwise MCAR at 10% and 30%, history-block removal at 50% row probability, and cellwise removal matched to the block's realized rate) and compares eight requested calibration conditions on two frozen predictors at five label budgets: 400 scored conditions. | Accepted Bank stress artifact; `research/SHIFTGUARD_Working_Paper_v0.3.md` §3 | One dataset, one seed (31001), one 8,238-row evaluation partition |
| C2 | At budget 50, target temperature, Platt and Beta maps have lower mean Brier score than the zero-target-label source-fraction-binned comparator; each is lower in 4 of 8 fixed predictor-by-shift cells and has higher log loss in all 8. Isotonic is worse on mean Brier against that comparator. | Working paper v0.3 abstract and results section; `research/CLAIM_EVIDENCE_v0.3.json` | Single-seed development result; dependent cells; the Brier summary depends on which zero-label comparator is used; no confidence intervals, significance or general-efficacy claim |
| C3 | Every result shown in the app is read from a published, hash-verified record; charts and the Results assistant's numbers come from those records, not from the model. | Gate 5 to 7 acceptance (`.agent/gates.json`); `docs/ordinary-chat.md`; deterministic rendering tests | The model chooses which approved read tools to call; Python renders every number |
| C4 | Experiments run as durable jobs on a separate worker, survive restarts, and replay idempotently. | Gate 4 acceptance; `tests/integration/test_worker_lifecycle.py`; hosted probe report (Gate 10) | One API process and one worker in the judge deployment |
| C5 | The model is NVIDIA Nemotron (`nvidia/Nemotron-3_5-Lightning`) served by Nebius Token Factory through its OpenAI-compatible API. | `shiftguard/agent/provider.py`; hosted live checks on the freeze build `112012e`, 27 Oct 2026: Summarize PASS (1 call, 4,415 tokens) and Compare PASS (2 calls, 13,676 tokens), both completed and grounded in the selected experiment; the live demo recording (`docs/submission/DEMO_SCRIPT.md`) | One Summarize run and two Compare runs (2 and 3 model calls; the second in the demo recording); token use varies with the model's output |
| C6 | Model use is capped at 50 calls and 100,000 tokens per UTC day across both assistants, reserved before each call, with zero retries; a timeout is charged at its full reserved upper bound and the day continues, while any other unknown outcome halts the day instead of risking a resend. | `shiftguard/agent/ordinary_budget.py`; `tests/agent/test_ordinary_budget.py`; `tests/agent/test_ordinary_timeout_policy.py`; `tests/agent/test_general_chat_timeout_route.py`; `tests/agent/test_ordinary_owner.py` | A judge may reach the cap; the app then says so and the manual workbench keeps working |
| C7 | General chat is tool-free and labelled unverified; it cannot read jobs, labels, files or results. | `shiftguard/api/routes/chat.py` system prompt and no tool registry; `tests/agent/test_general_chat.py` | It is ordinary model text |
| C8 | The multi-seed repeat engine (Gate 8) ran its declared 5×10 schedule (5 outer seeds × 10 inner repeats) on the real Bank data on 21–22 Oct 2026 IST as development work: all 50 runs completed, none failed. The primary contrast is reported as missing evidence with no estimate or interval, because the pool-qualification decision (SCI-03) is unresolved. | Frozen run manifest `docs/research/gate8-run-manifest-bank-development-v1.json` (committed `ab46015` before the run; manifest digest `3bb107f7…a30b`); `scripts/gate8_run_development.py`; read-only report from `scripts/gate8_report_development.py` (report digest `0eec31a0…1bc0`; counts and digests only) | Development tier: Bank outcomes were previously inspected, so not confirmatory. No estimate, interval, hypothesis decision or coverage claim. Not exposed in the app |

## Claims we do not make

- No confirmatory or replicated finding. The Gate 8 Bank repeats (C8) are development work on
  outcomes already inspected and give no primary estimate. The Adult adapter (Gate 9) is tested
  on fabricated data only and not run on real outcomes. Neither is exposed in the app.
- No business, ROI or causal benefit. No customer data or uploads are supported.
- No statistical significance or confidence intervals for the Bank results.
- No new calibration algorithm. The comparison uses established maps.
