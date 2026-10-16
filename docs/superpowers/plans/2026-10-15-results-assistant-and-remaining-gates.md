# Plan: fix the Results assistant, finish Gates 10–11, then Gates 8–9 (15 October 2026)

The owner delegated all decisions to Claude: execute without asking. Implementation goes to Sonnet or Haiku subagents with disjoint files, and an Opus subagent at xhigh effort reviews every batch before commit and deploy. Deadline: Devpost submission by 30 Oct 2026 20:00 IST. Hosting must stay up until 16 Dec 2026.

## 1. Results assistant: diagnosis from two live runs on 15 Oct

| Run | Prompt | What happened | Root cause |
|---|---|---|---|
| A | Free-form: "For saved experiment 09b7…, summarize the budget-50 comparison…" | 6 turns of wandering tool calls; FAILED at the turn limit | **R1.** By design (Gate 7), a saved experiment is readable only when the prompt is an exact selection command (`Summarize experiment <id>`, `Read experiment <id> condition <key>`, `Compare experiment <id> calibrators predictor … scenario … budget …`). Free-form questions get `UNAUTHORIZED_EXPERIMENT_REFERENCE`. The UI gives users no way to form the command; its placeholder even invites free-form questions. **R2.** After the denial the model keeps trying other tools until the budget runs out. |
| B | Exact: "Summarize experiment 09b7…" | Metadata and full read succeeded; the third provider call was rejected (`PROVIDER_INVALID_RESPONSE`, not dispatched, not charged) | **R3.** `read_experiment_results` with no condition returns the entire 400-condition record (258 KB) as a tool message. Provider bounds are 16 KB per message and 64 KB per transcript, so the next request is refused. The model never needs that payload: Python renders every final fact from the stored tool execution. |

Also: a token cost of about 4.7k per call (system prompt, 12 tool schemas, history) means the planned allowance of 6 Results questions a day was wrong.

## 2. Fix (Batch R)

Backend (Sonnet, files `shiftguard/agent/controller.py`, `shiftguard/agent/prompts.py`, new tests):

1. **Bounded model-facing tool messages (R3).**
   - When a tool result is appended to the conversation, project it deterministically to at most 6 KB: keep status, error, ids and side-effect flags; replace large `data` with a digest (top-level keys, scalar fields, list lengths, a bounded prefix of condition ids), plus `data_truncated: true` and a short note.
   - The stored tool execution keeps the full result, so Python rendering is unchanged.
   - The transcript stays under the 64 KB provider bound across the 8-call limit.
2. **Saved-experiment procedure in the system prompt (R2):** for a selection command, call the one matching read or summary tool for that id, then return the final JSON plan straight away. Tool results may be truncated digests; Python renders all facts. On `UNAUTHORIZED_EXPERIMENT_REFERENCE`, stop calling tools and return the `failures` plan.
3. **Unauthorized-reference short-circuit (R1, R2).** If a decision's outcomes include `UNAUTHORIZED_EXPERIMENT_REFERENCE` and the request has no bound evidence, finish at once with no further provider calls. The status and code stay typed: `EXPERIMENT_NOT_SELECTED`, plus a public message telling the user to ask `Summarize experiment <id>` or use the suggestion buttons.
4. **Regression tests that replay both live runs** with the scripted provider, on SQLite and PostgreSQL:
   - run A ends after the denial with the guidance and spends no more provider turns;
   - run B completes with a grounded summary;
   - every transcript sent to the provider stays within its bounds.
   - The Gate 7 adversarial, authority, summary-oracle and rendering suites, plus `scripts/check_gate7_candidate.py` comparisons, must stay green.

Frontend (Sonnet, files `frontend/src/components/AgentPanel.tsx`, `frontend/src/pages/BenchmarkWorkbench.tsx` only where it passes the selected experiment, its CSS, and a new e2e spec). Gate 7-protected hooks and api clients are not touched.

5. When a saved result is open, the Results assistant shows suggestion buttons that insert the exact commands for that experiment:
   - `Summarize experiment <id>`;
   - `Compare experiment <id> calibrators predictor logistic_regression scenario history_block_0_50 budget 50`, for experiments that contain that condition.
   - The placeholder explains that saved results are read through these commands.
   - Browser test with mocked APIs.

Then:
- Opus xhigh review of the combined diff.
- Focused suites on both backends, plus the Gate 7 suites and browser specs.
- Commit and push.
- Rebuild the image, upload it resumably, redeploy.
- One live check per question type, within the daily cap: `Summarize experiment <id>` and the compare command. Record the calls and tokens per question, and correct JUDGE_GUIDE, SUBMISSION and DEVPOST_FORM with the measured number of questions per day.

## 3. Gate 10 completion (Batch H)

- On the VM:
  - restart and persistence check (kill the worker mid-job; restart the API);
  - second-owner refusal;
  - nightly `pg_dump` plus an artifact tarball under `/opt/shiftguard-backups`, keeping 7;
  - a weekly certificate and health check in the autopilot.
- Record the live URL and measured hosted times in README, JUDGE_GUIDE, SUBMISSION, DEVPOST_FORM and RELEASE_CHECKLIST.
- Clean-browser smoke test from this PC against the public URL: the full Playwright product specs in hosted mode, with `SG_E2E_BASE_URL` set.

## 4. Gate 11 freeze (Batch F, 27–28 Oct)

- Full Python suite once on the final source.
- Tag `hackathon-2026-submission`.
- Record the image digest and the VM image ID.
- Back up PostgreSQL and the artifacts together.
- Re-record the demo video with the live Results assistant: real Nemotron replies inside the cap, the scripted badge removed for live shots.
- Owner: YouTube upload and Devpost submit.

## 5. Gate 8: repeat study on Bank (Batch S8, 17–24 Oct, off the submission critical path)

Facts that cannot change: Bank outcomes were already inspected in the single-seed run, so no Bank analysis can be confirmatory. Gate 8's confirmatory clause therefore moves to the prospective Adult analysis in Gate 9. What Bank can honestly give is **development-tier robustness with uncertainty**.

1. Owner-delegated authorization recorded in `research/gate8-20261009/`: run the declared `gate8-nested-v1` 5×10 design on real Bank under the development tier, labelled "development; Bank outcomes previously inspected; not confirmatory".
2. Resource preflight (R1 of the delivery plan): one coordinate on 41,188 fabricated rows to measure time and memory. Then the full 50 coordinates locally, restartable through the synthetic-store contract extended to real records. Labels stay evaluator-private.
3. Aggregate the primary contrast (target temperature minus source-fraction-binned temperature, budget 50, Brier) with the declared conditional group bootstrap, labelled `bank_overlap_diagnostic`. Report every coordinate, including failures.
4. In the app, label single-seed runs "illustrative". Add the repeat summary to the paper's claims table and README only as development evidence.

## 6. Gate 9: Adult replication (Batch S9, 20–29 Oct, may continue after the deadline)

Prerequisites, done honestly:

1. **Custodian evidence:** build the training and test source manifest from the official UCI archive (hashes, physical line ids, feature-only duplicate and overlap groups). This uses no test labels.
2. **Author-locked protocol:**
   - write the prospective Adult protocol amendment (13 predictors, exact-token grouping, zero-observed-cell semantics, roles, budgets, the primary contrast and the analysis);
   - have it reviewed by the Opus reviewer for internal consistency;
   - commit and push it publicly *before* any test outcome is read. That commit hash and timestamp are the lock.
   - It is labelled "author-locked, not externally peer-reviewed". No claim of external scientific approval is made.
3. **Engine wiring:** route the Adult adapter through the engine with grouped quarantine and role allocation. Development runs use the training file only. Every protected numerical owner that changes must reproduce the Bank Gate 2/3 artifacts byte for byte.
4. **Unseal the official test file once,** run the locked analysis, and report whatever it shows, including null or adverse results.
5. If time runs short, Gate 9 continues after 30 Oct into the paper. It is never squeezed into the judged build at the last minute.

## 7. Order and stop rules

R → H → F-prep (Results fixes first, because judges see them), then S8 and S9 in parallel with doc work.

- A batch is done only after: tests green, the Opus review acted on, committed, pushed and (for R and H) deployed with live evidence.
- Two failed correction cycles on one problem trigger a root-cause write-up before the next attempt.
- Paid calls stay inside 50 calls / 100,000 tokens a day. Never reset the ledger.
