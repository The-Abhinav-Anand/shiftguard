# Independent review of the Opus continuation — 14 October 2026

**Verdict: CORRECTIONS_REQUIRED for the current uncommitted continuation.** The existing suite passes, but independent probes expose material cases outside that suite. This does not reverse historical Gates 0–7 acceptance. Gate 8 and Gate 9 remain unaccepted engineering work.

Execution plan: [Claude correction and delivery plan](superpowers/plans/2026-10-14-opus-corrections-and-delivery.md). Evidence: [review directory](../../verification/opus-review-20261014/).

## 1. Source and scope

- Repository: `C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard`, branch `implementation/gate-0`.
- HEAD: `f3f696579345347884d547f7ec4c75a84ce21184`. HEAD is the historical baseline, not the identity of the dirty candidate.
- Review source inventory: 318 runtime, configuration, test and frontend files; digest `5bfb5f5815ad49ec215d265827a07270d6536c3afd646061ef8a0013928e83fe`. See `source-before.json` for the complete inventory and its deliberately bounded scope. Documentation and historical evidence are referenced separately.
- The after-review inventory has the same 318 paths and digest. The reviewed application source did not change during these checks.
- Reviewed the ordinary-chat store/API/provider/budget/frontend changes, migration and regression-fixture changes, Gate 7 comparison changes, repeat contracts/planning/seeds/aggregation/uncertainty/completion/store, the Bank development adapter, the Adult adapter, their tests, frozen scientific decisions, and the submitted execution/hosting claims.
- The accepted engine was exercised by the integrated suite. This was not a new unrelated Gate 4 audit or an external penetration test.
- No production fixes, source commits, gate acceptance changes, paid inference, real repeat campaign, Adult outcome access, deployment, or deletion were performed by this review.

## 2. What the evidence actually establishes

| Check | Independent result | Evidence |
|---|---|---|
| Integrated Python suite, SQLite and retained PostgreSQL 16 | **1,102 passed, 0 failed, 0 errors, 0 skipped**, two dependency warnings; 7,442.51 seconds | `full-suite.log`, `full-suite.xml`, `test-summary.json` |
| Pure repeat package plus Bank/Adult adapters | **279 passed**, 281.85 seconds; 93 adapter cases | `targeted-unrestricted.log`, `.xml` |
| Existing general-chat browser regressions against freshly rebuilt frontend, mocked APIs | **4 passed** | `chat-existing.log`, `.json` |
| Additional reload/retry browser regression | **FAIL: recovered reply absent after completion** | `chat-reload.spec.ts`, `browser-probe-02.log`, `.json`, screenshot/error context |
| TypeScript checks | PASS | `typecheck.log` |
| Independent frontend build | PASS; existing large-chunk warning | `frontend-build.log` |
| Built assets versus served package assets | **14/14 byte-identical**, no extra or missing files | `asset-comparison.json` |
| Protected backend comparison | 50/50 allowed comparisons; **48 byte-identical**, two narrowly identified ordinary-chat additions | `protected-comparison.json` |
| Historical migrations 0001–0011 | **11/11 byte-identical** | same comparison |
| Additional Python probes | Seven concrete acceptance/recovery observations listed below | `probe_review.py`, `probe-results.json` |
| Whitespace-only chat prompt / idempotency key | **Both return 500, rather than 422**; zero SDK dispatches | `probe_validation.py`, `validation-probe.json` |
| Live Nebius authentication/current model quality | NOT_RUN in this review | Zero paid calls |
| Hosted availability, installed Linux image, public repository visibility | NOT_VERIFIED | Local source/tests are not hosted proof |

The previous Opus 1,009-pass XML is genuine, but contains **zero adapter tests**. Its source binding precedes ten added adapter/test files and the repeat package description edit. The new 1,102-pass run closes that integration-test gap; it does not close the new findings.

The first adapter run had 13 failures because the Windows sandbox denied `os.link`. A bounded restart test reproduced `WinError 5`; the unrestricted isolated rerun passed all 279. These are not product defects. An initial browser probe had an ambiguous locator; that failed attempt is retained, and only attempt 02 demonstrates the application defect. Python TestClient probes also needed an unrestricted local event loop because the sandbox blocked its loopback socket pair. No evidence was overwritten to hide these distinctions.

## 3. Consolidated findings

Severity is relative to the feature being accepted. A Gate 8 numerical blocker does not imply that the already accepted single-seed Bank charts are wrong.

### OR-01 — P1: a successful paid reply disappears after pending-history recovery

**Location:** `frontend/src/hooks/useChat.ts:245–265`, especially `serverAlreadyHasReply = current.messageCount > pending.previousMessageCount`; related history contract in `frontend/src/api/chat.ts` and `shiftguard/agent/chat.py`.

**Reproduction:** An existing conversation has two completed messages. A follow-up reaches the server, which persists its user message before provider dispatch. The tab reloads while that message is pending; history now has three messages. A retry using the original idempotency key returns the completed assistant reply. The hook treats three messages as proof that the reply already exists, discards the returned reply, clears the pending receipt, and saves the incomplete history.

**Independent observation:** The retry button disappears, proving completion handling ran, while `Recovered paid reply must remain visible` is absent. The same case fails against the freshly built bundle; all four existing chat browser tests pass.

**Required fix:** Reconcile by stable message/receipt identity, not total count. Return stable message IDs and ordinals in history, expose the user and assistant IDs on completion, merge each exactly once, and preserve the original request key through lost responses and storage failures. A pending user row is not a completed assistant row. Add the failing browser test to the application suite, plus the already-completed-history variant.

### OR-02 — P1 for hosted activation: startup recovery steals a live ordinary reservation

**Location:** `shiftguard/api/main.py:47–50`; `shiftguard/agent/ordinary_budget.py:414–446`.

**Reproduction:** Instance A reserves a model call. While A still owns it, another app instance starts against the same database. Startup invokes `recover_unresolved()`, which considers every current-day `reserved` row abandoned without checking ownership or liveness.

**Independent observation:** `second_instance_recovered_active_call=true`, the daily ledger changes from unhalted to halted, and A's valid settlement raises `OrdinaryBudgetError`. No model request was needed to reproduce the state transition.

**Impact:** A second worker process or overlapping restart can discard a valid reply and disable both ordinary assistants for the UTC day. This fails closed on spending; the defect is availability and ownership, not proof of overspending.

**Required fix:** Enforce one database-scoped ordinary-dispatch owner for the judge deployment before recovery or provider creation. Reject a second live owner without mutating its ledger. Recover only after exclusive ownership is established. Keep the shared daily cap and conservative unknown-usage policy. The execution plan specifies a bounded single-owner implementation rather than silently promising multi-process provider dispatch.

### OR-03 — P2: known, settled reply rejection is retained as permanently pending

**Location:** `shiftguard/api/routes/chat.py:160–191`; `shiftguard/agent/chat.py` receipt lifecycle.

**Reproduction:** The provider returns valid usage and a response of 8,193 bytes. Accounting settles successfully; the route rejects it as `CHAT_REPLY_TOO_LONG` after dispatch. The receipt remains `PENDING` and the conversation remains claimed.

**Independent observation:** First response 502; same-key replay 202/PENDING forever; a new message in the same conversation receives 409/CONVERSATION_BUSY. Exactly one fake dispatch, budget not halted. A new conversation is a workaround, not resolution of that receipt.

**Required fix:** Persist terminal failures with their stable HTTP response once a provider response is known and validation has finished. Atomically release the conversation claim, replay the same failure without dispatch, and let a new key continue that conversation. Keep ambiguous transport failures conservative; never convert them into permission to resend.

### OR-04 — P1 for repeat-engine acceptance: impossible aggregate values produce intervals

**Location:** `shiftguard/repeats/aggregation.py:67–81`; `shiftguard/repeats/uncertainty.py:121–145,171–219`.

**Reproduction:** Start from a valid fabricated `PreparedAggregate`, replace its two group sums with `(1000.0,1000.0)` for every outer repeat while counts remain `(1,3)`, and replace the point estimate with `999.0`.

**Independent observation:** `paired_group_interval()` returns a lower bound of 333.3333333333333, upper bound of 1000.0, and point estimate 999.0. A difference of two binary Brier means must lie in [-1,1]. The reducer that normally creates this object validates earlier cells, but the interval entry point accepts a detached, replaceable object and does not repeat the essential checks.

**Required fix:** Validate every consumed aggregate: strict nonnegative counts, finite bounded sums, zero sum when membership is zero, positive required row mass, exact dimensions, and safe integer conversion. Derive the point estimate from validated counts/sums; do not trust an independently supplied field. Apply the same validation to chunked draws and weighted estimates. Preserve the reviewed bootstrap algorithm.

### OR-05 — P2: fixed-external mode checks counts, not fixed membership

**Location:** `shiftguard/repeats/uncertainty.py:181–182`; `PreparedAggregate` drops the required row/group membership identity.

**Reproduction:** Build five outer manifests with different evaluation row IDs but the same two group IDs and counts. Produce their legitimate aggregate and request `fixed_external`.

**Independent observation:** All five row memberships differ, but the interval is returned as `fixed_external`. Equal group counts are insufficient to prove the same evaluation cohort.

**Required fix:** Retain the ordered evaluation `(row_id, group_id)` membership, or a derived immutable identity validated against the plan, in the prepared aggregate. Fixed-external mode requires identical membership across all outer repeats; Bank overlap diagnostics remain explicitly separate. This is an engineering validation issue even though the current result is labelled synthetic.

### OR-06 — P2: condition inventory accepts impossible resolution accounting

**Location:** `shiftguard/repeats/models.py:530–562`; `shiftguard/repeats/validation.py:112–163`.

**Reproduction:** Supply all 20,000 declared terminal slots for a fabricated plan with four evaluation rows per outer repeat, but set each condition's resolution count to 999,999.

**Independent observation:** `full_grid_complete=true` and `primary_ready=true`. Duplicate resolution method entries, empty completed accounting and disagreement with the evaluation row count also lack a complete inventory-level contract.

**Required fix:** Completed conditions must have unique declared resolution entries summing to the bound evaluation row count; failed conditions must have no successful resolution or scored-row counts. Validate fallback edges and connect adapter-produced primary pairs to their terminal conditions before declaring a coordinate complete. Preserve per-row binned fallback accounting into summary metadata; a top-level method name alone cannot represent mixed bin resolution.

### OR-07 — P2: Adult MCAR accepts invalid random inputs as valid masks

**Location:** `shiftguard/adult_adapter/missingness.py:170–178`.

**Reproduction:** Call `build_mcar_mask()` with a correctly shaped uniform matrix filled with NaN, infinity, -1, or 1.

**Independent observation:** All inputs are accepted. NaN/infinity/1 yield no masked cells; -1 masks all 13. The generated mask receives a valid content identity, concealing invalid upstream random data.

**Required fix:** Require an explicitly supported floating dtype, correct shape, finite entries, and `0 <= u < 1` before comparison. Reject boolean, integer, object and complex arrays as typed adapter errors. Test both rejection and unchanged valid nested masks. This does not change the mask distribution.

### OR-08 — P2: the development scorer repairs an invalid scientific value

**Location:** `shiftguard/repeats/development_adapter.py:114,271–276`.

**Reproduction:** Inject an evaluator result giving a one-row paired sum of 1.0000000005.

**Independent observation:** The scorer silently returns 1.0 under `_ROUNDING_SLACK`. This is a controlled failure-injection probe, not evidence that valid current predictions naturally produce this value.

**Required fix:** Remove the clamp and reject non-finite or out-of-bound sums with the declared typed error. Any changed tolerance/repair policy requires the scientific amendment that is currently absent. Valid probabilities already give bounded binary losses; silent alteration is unnecessary for the engineering slice.

### OR-09 — P2: whitespace validation must remain a client error

**Location:** `shiftguard/api/routes/chat.py:42–50` and `shiftguard/api/main.py` validation exception handler.

The route raises a custom `ValueError` for whitespace-only prompt or idempotency key. The common exception handler passes `exc.errors()` directly into `JSONResponse`; those errors contain a non-JSON `ValueError` in `ctx`. Independent HTTP probes returned **500 / Internal Server Error for both inputs**, with **zero SDK dispatches**, as recorded in `validation-probe.json`. Treat this as a route-boundary correction, not a request to replace the complete API error architecture.

**Required fix:** Serialize a bounded public validation representation containing only JSON-safe field locations and error codes/messages; omit raw input and exception objects. Blank inputs must return 422 with zero receipt writes and zero dispatches. Preserve request IDs and ordinary non-custom validation errors. Add the whitespace cases; the current 4,001-character test does not exercise a custom validator exception.

## 4. Corrections to the narrative supplied with the work

1. **Grounding description is substantially accurate for accepted Bank results.** The registry is closed, tools read published records, and Python owns empirical rendering. General chat has no tool registry and does not feed plots. This review found no new path that lets general chat issue experiment tools.
2. **Neither new adapter is a completed experiment or public product integration.** They are imported by tests; the API, worker preset registry and assistant do not expose their outputs. The full suite now checks compatibility, not real repeat scientific validity.
3. **Exact-token grouping and unsupported-role reporting are already specified in the P1 decision packet.** `SCIENTIFIC_DECISIONS.md:116–122` preserves numeric spelling/case and requires `UNSUPPORTED_ROLE` for insufficient roles. These are not unexplained choices invented by the latest Adult agent. Technical agreement still does not supply human scientific approval.
4. **Real Bank repeats are not currently authorized by changing a label to “development.”** The packet explicitly keeps real outcomes outside its scope and requires separate authorization. SCI-03/SCI-04 authority, exposure and the confirmatory lock remain distinct. Do not remove synthetic gates to make a demonstration pass.
5. **The reported legacy Adult issues are real, but separate.** `datasets/adult.py:98–121` numbers nonblank records, its splitter does not group duplicates, and `docs/gate3-development-contract.md:220` lists 14 features while the prospective adapter/parser use 13. Preserve frozen evidence and document a prospective parser/mapping amendment before wiring real Adult data. Source line identity is not the same thing as cleaned-record ordinal.
6. **No upload capability is implemented.** The B0–B6 business plan remains a separate tenant/private-data scope. The existing public benchmark readers are not suitable private-business-data authorization. No upload UI should imply otherwise.
7. **Hosting has a scaffold, not acceptance evidence.** `Dockerfile`, `LICENSE` and `THIRD_PARTY_NOTICES.md` already exist. The Docker default does not enable the embedded worker, and data are excluded from its context. A judge deployment needs an explicit worker command/profile, verified Bank data provisioning, durable artifacts and PostgreSQL. Reuse and complete these files rather than claiming they do not exist or recreating them.
8. **Governance pointers drifted.** `.agent/session-state.md` contains 14 October progress, while `docs/next-execution.md`, handoff records and some ownership entries still direct the executor to earlier failures/roles. Update active pointers after this review; preserve the old packets. Neither a custom allowlist saying “authorized” nor an author's green test run is independent acceptance.

## 5. Submission requirements checked live

The official deadline is **30 October 2026, 10:00 PDT = 22:30 IST**. Runtime Token Factory inference satisfies the stated Nebius execution requirement; hosting the whole app on AI Cloud is optional. A working demo/test build, public licensed source with setup instructions, public YouTube demo under three minutes, track selection and sponsor feedback are required. Judge access must remain available through the end of judging, **16 December, 01:30 IST**. [Official rules](https://nebiusglobalaihackathon.devpost.com/rules), [official schedule](https://nebiusglobalaihackathon.devpost.com/details/dates), checked 14 October.

Therefore the delivery plan can prepare hosting and submission while the synthetic adapters are corrected. Neither confirmatory statistics nor Adult replication should be relabelled as completed to meet the deadline. The public-demo allowance also needs an explicit owner-approved access/capacity arrangement: the existing 10-call shared daily budget is a cost guard, not proof that judges can always exercise the model.

## 6. Closure rules

- One packet, OR-01 through OR-09; all discovered findings are recorded here. Close each against a regression derived from its reproduction, not a renamed author assertion.
- Product activation requires the chat fixes and affected invariant checks. Gate 8/9 engineering acceptance additionally requires their numerical/identity corrections. Hosting preparation can proceed independently of real scientific outcome access.
- Preserve this initial verdict and failed probe artifacts. Add a new exact-source correction result; do not edit this packet into a historical PASS.
- Commit source and record governance acceptance separately under the existing source-owner authority. No commit or acceptance is implied by this report.
- Stop broad re-review once the agreed matrix passes. Reopen scope only for a new reproducible failure, a source change affecting a protected invariant, or a missing required backend/evidence artifact.
