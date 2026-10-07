# SHIFTGUARD frontend — Luna Extra High execution packet

Prepared 30 September 2026. **REVIEW PACKET ONLY. NOT AUTHORIZED TO EXECUTE IN THIS RUN.**

Recipient on a later parent dispatch: **GPT-6 Luna, `gpt-6-luna`, reasoning `xhigh`**. The parent owns dispatch, application-writer coordination, business-BYO/error-plan integration, independent review, acceptance and any commit/deployment authorization. Do not message other agents or launch another chat. Do not infer dispatch from the existence of this file.

## 1. Objective and controlling design

Implement [The Evidence Instrument](astra-frontend-design.md): warm ivory, green-black editorial type, vermilion registration marks, a precise missing-input lattice, and a readable benchmark workbench. Deliver the complete journeys in the batches below. Do not ask another design interview, offer alternative visual directions, start with a global CSS rewrite or turn this into a new application foundation.

The user explicitly permits this future Luna frontend assignment despite older no-Luna instructions. That exception is scoped to this packet; it does not assign Luna the Gate 6 backend corrections, BYO capability implementation, repository cleanup or governance. The current instruction is to deliver design and coding instructions first; no Luna execution or frontend source writing occurred while preparing this packet.

Read in dependency order: repository `AGENTS.md`; current `.agent/session-state.md`, `ownership.json`, `gates.json`; this packet and its design; `docs/blueprint-progress.md`, `gate5-acceptance.md`, `gate6-review.md`; only relevant frontend/grounding sections of `gate6-sol-review.md`; then the exact owner files in design §12. Parent's subsequently supplied BYO/error-state contract overrides planned placeholders only where its backend requirements are actually closed. It must not silently activate private uploads or arbitrary business-model support.

## 2. Mandatory preflight before any future edit

1. Confirm the parent has authorized frontend implementation and exclusive writing to the specific frontend/test paths below. Do not edit alongside the Gate 6 correction writer. If scopes overlap, stop that overlap and return a precise ownership dependency.
2. Record current HEAD, dirty/untracked paths and raw hashes of intended source/test/generated owners. Preserve the pre-existing dirty candidate. Never reset, clean, delete, change branch, restore accepted files over dirty files, or touch the frozen verification clone.
3. Re-read current gate evidence. Design-time accepted Gate 5 source was `f63116fedc2751493d79d44897ba913b6d28b0b5`; Gate 6 was pending with 25 findings, reviewed digest `4d392741d38da64eb480f5f04bc97a3221649ee9a7ef7b4e8ec13be4fcc9e1d8`, HEAD `83037b0f02eef62203c3f565a063d824af2722d7`. A changed baseline is not permission to relabel these historical records.
4. Inspect installed package metadata and `package-lock.json`. Design-time verified versions: React/React DOM 19.3.0; Plotly 4.1.1; react-plotly.js 4.1.0; Vite 7.3.6; TypeScript 5.9.3; Playwright 1.63.0. Three, GSAP and @gsap/react were absent. Keep the existing stack. Resolve and pin exact Three/GSAP versions only in the authorized dependency batch, using official package metadata and compatibility checks; preserve unrelated lock entries. Do not run `npm update`, `npm audit fix`, global installs or framework migrations.
5. Read the tests before moving DOM. Map each current invariant and locator to its new placement. Inspect any parent-provided baseline captures; if none exist, capture the existing UI only through an authorized local offline harness. Record unavailable checks as NOT_RUN or BLOCKED, never PASS.
6. Establish baseline typecheck and isolated build. A pre-existing Gate 6/harness failure belongs in the evidence ledger; do not erase it, weaken a test, or call the refresh regressed without comparing baseline.

Preflight is a short preparation step inside the first batch, not a request to restart the parent's history/cleanup review. It does not authorize live APIs or business backend work.

## 3. Ownership and target files

All paths below are relative to `C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard`. **These are future targets; no files in this table are created or edited by the design task.** The parent may narrow this list when dispatching.

| Existing owner | Future allowed change | Keep intact |
|---|---|---|
| `frontend/src/App.tsx` | Small route composition and extraction of workbench rendering to its own screen | Actual preset values, initial selections, filter transition logic, published loading and hook identity |
| `frontend/src/main.tsx`, `frontend/index.html` | Route entry, static branded boot/noscript, title/description, app error boundary | Same-origin entry; no API calls from loader |
| `frontend/src/styles.css` | Global reset and semantic token entry; import scoped files below | Do not leave conflicting old rules or replace arbitrary strings globally |
| `frontend/src/components/ResultDetails.tsx`, `PresetResult.tsx` | Layout, headings/labels, full-value disclosure and accessible styling | All fields, precision, condition binding, eight sparse diagnostics, nulls and adverse evidence |
| `frontend/src/components/charts/shared.tsx`, `Plot.tsx` | Theme, chart error containment and lazy boundary | Basic bundle, data-independent formatting, tables outside chart failure boundary |
| Four `frontend/src/components/charts/*.tsx` plot owners | Only stable color/dash/marker identities and necessary presentational sizing | Every data projection, fixed budget, filter, condition ID and availability rule |
| `frontend/package.json`, `package-lock.json`, `vite.config.ts` | Three/GSAP dependencies and measured chunk configuration | Existing runtime/framework versions and proxy behavior |
| Nine-case owners in `tests/e2e/test_flagship_preset.spec.ts`, `test_reload.spec.ts`, `test_job_errors.spec.ts`; `frontend/e2e/fixtures.ts` | Change workbench entry to `/demo`; adjust unavoidable presentational locators with documented equivalents | Real worker, persisted-payload comparisons, identity, cache, auth, failure and mobile assertions |
| `tests/integration/test_static_boundaries.py` | Only if code-splitting requires following the built import graph for existing product-content checks; parent must include this test in scope | Real JS MIME and API/asset 404 assertions; never add fake strings to entry bundle |

New frontend presentation owners, keep each responsibility coherent:

| Proposed new file | Responsibility |
|---|---|
| `frontend/src/routes.ts` | Explicit pathname classification and title; no auth/business logic |
| `frontend/src/pages/Overview.tsx` | Business introduction, chapters, actual/planned ledger |
| `frontend/src/pages/BenchmarkWorkbench.tsx` | Retained manual App composition; one `useWorkbench` instance, no rewritten controller |
| `frontend/src/pages/PlannedWorkspace.tsx` | Disabled planned-route explanation only |
| `frontend/src/pages/NotFound.tsx` | Custom client 404 with real links |
| `frontend/src/components/brand/Brand.tsx`, `RouteLoading.tsx` | Wordmark, local route fallback; no timed success |
| `frontend/src/components/brand/SceneFrame.tsx`, `SceneFallback.tsx` | Accessible conceptual figure, chapter controls, static states and failure boundary |
| `frontend/src/components/brand/MissingnessScene.tsx` | Optional Three instance and resource ownership; dynamic import |
| `frontend/src/components/brand/BlockedAssistant.tsx` | Visible under-review band without `useAgent`, inputs or provider calls |
| `frontend/src/components/ChartErrorBoundary.tsx`, `AppErrorBoundary.tsx` | Rendering/import failure surfaces; never reinterpret API status |
| `frontend/src/motion/useBrandMotion.ts` | Scoped GSAP lifecycle only; no workbench state imports |
| `frontend/src/styles/tokens.css`, `brand.css`, `workbench.css`, `motion.css` | Semantic tokens and scoped visual layers |
| `frontend/src/assets/brand/*` | Approved mark/static illustrations, locally bundled under emitted `/assets/` URLs |
| `frontend/src/assets/fonts/*` | Verified licensed Manrope WOFF2/license only if selected asset meets budget |
| `frontend/playwright.refresh.config.ts`, `frontend/e2e/refresh-fixtures.ts` | Visual-only harness against explicit local static preview URL; no seed/global setup/provider/server injection |
| `tests/e2e/test_product_refresh.spec.ts`, `test_refresh_faults.spec.ts` | New route, loading, fallback, accessibility, disposal and honesty contracts |

Freeze for visual batches: `hooks/useWorkbench.ts`, `state/workspace.ts`, `api/client.ts`, `api/types.ts`; existing unaccepted `hooks/useAgent.ts`, `api/agent.ts`, `components/AgentPanel.tsx`; all backend/scientific/config/migration/worker code; `.agent/*`, AGENTS/workflow/gate/history documents; research; parent verification; toolchains. Rendering the blocked assistant means removing its live hook invocation from the new public composition, not rewriting or deleting the agent implementation.

`frontend/playwright.config.ts`, `scripts/e2e-setup.ts`, `scripts/e2e-server.py`, `tests/e2e/test_agent_flow.spec.ts` remain with the parent/correction owner unless explicitly reassigned. The current harness defaults to scripted mode and the agent suite includes live-looking claims; do not inherit those as proof or silently change them to make a refresh report green.

Do not put assets only in `frontend/public` and assume arbitrary root asset paths are served correctly: the inspected server explicitly mounts `/assets`. Bundle referenced SVG/font files through Vite so emitted URLs follow that existing boundary. No backend mount changes.

## 4. Large vertical batch A — complete usable product in HTML

**Dependency:** parent dispatch + ownership + preflight. **Outcome:** complete public overview, honest route states, branded boot and 404, and the retained benchmark workbench in the new visual system, all usable with WebGL absent. Do this as one coherent batch, not a series of style-only handoffs.

Execution order:

1. Extract current workbench composition into `BenchmarkWorkbench.tsx`, moving its existing view-selection logic literally before visual restructuring. Keep `useWorkbench` at one stable location. Preserve controlled labels, initial preset `bank-outage-50`, seed copy, charts and tables. Native links route `/` to `/demo`; leaving `/demo` does not cancel jobs or clear storage.
2. Establish `/`, `/demo`, four disabled `/workspace...` routes and app not-found. No authenticated private state or fake upload. Marketing and planned/404 routes must make zero workbench/provider requests. `/api/*` and `/assets/*` remain entirely backend-owned. Preserve SPA's current HTTP-200 unknown-document limitation honestly.
3. Build the actual content and static conceptual diagrams from design §§2–5, including CTA destinations and planned/available labels. Do not create filler numbers, speculative business dashboard data or customer logos. Implement the static hero before Three imports.
4. Apply tokens/layout/type component by component. Desktop asymmetry and ruled chapters come first, then workbench hierarchy, then responsive layouts and table overflow. Keep diagnostics/provenance and source badges legible. Do not hide the API problem behind full-page loading.
5. Implement real-state loaders/error surfaces from the design. DOM entry placeholder clears only when route mounts. Cache is visible while connecting/fetching; charts load independently of tables. A chart import failure is contained. No artificial delay or fake percent. Do not add retry loops or request timeout changes to the accepted client.
6. Add the blocked assistant presentation without mounting `useAgent`. This release intentionally does not execute the unaccepted candidate. If parent has meanwhile accepted a corrected agent and explicitly authorizes integration, use the dependency branch in §7; do not infer that from an endpoint returning available.
7. Update only the nine Gate 5 tests' route entry/helper for `/demo`. Keep semantic assertions. Add route/404/planned/loading/table-failure tests and screenshots in the isolated visual harness. Test static brand/no-WebGL operation before introducing motion.

Batch A acceptance:

- Overview immediately answers purpose, current availability and next action; `/demo` controls visible without marketing scroll.
- No numeric or logic changes in chart transformations/cache/auth/job owners. Diff preserves preset values and transitions; the scientific trace arrays still equal persisted payload arrays.
- Planned routes have neither forms nor submission handlers and make no auth/private API calls. Direct load, refresh and back/forward work.
- Entry, chunk-failure, provider-blocked, record-not-found and unknown-route states differ. Legitimate API 404 does not navigate to app 404.
- 320/390/768/1024/1440px views, 200% zoom, keyboard and forced colors work; source badges, fallback and warnings survive.
- Typecheck + isolated production build succeed, or report a precisely evidenced pre-existing blocker. All required executable targeted cases pass; unexecutable cases explicitly BLOCKED.

Do not pause after implementing only the homepage. Finish the batch's routes, functional workbench preservation, states and checks before one review handoff.

## 5. Large vertical batch B — purposeful motion, real 3D and resilient loading

**Dependency:** Batch A functional/fallback checks pass and parent has authorized dependency changes. **Outcome:** exact Missingness Register scene and motion, with equal usability under failures.

1. Pin compatible Three/GSAP versions; add matching Three types only if required by its package. Use direct Three and GSAP core; optional ScrollTrigger limited to section reveals. @gsap/react is not required: use scoped matchMedia/React cleanup. Record version resolution and added gzip bytes; no unrelated upgrades.
2. Implement the specified geometry, orthographic framing, materials, lights, exact deterministic gap and equal measuring rails. Use shared/instanced geometry; one renderer only. The scene gets no workbench payload or network client. Its labels/buttons stay HTML. Never use it as a live model or scoring visualization.
3. Dynamic-import the scene after meaningful content and eligibility. Static SVG remains until first successful rendered frame, then 180ms crossfade. Add all four independent outcomes: ready, import failed, context unavailable/lost, and performance downgrade. Three “ready” is not app/data/model ready.
4. Implement hero/reveal/chapter transitions and small hover treatment to the exact timings. Motion is one-shot/on-demand. DOM content never depends on timeline completion. Reduced motion skips the Three import and uses static chapter states. Mobile static default has optional explicit 3D activation only when preferences permit.
5. Add pointer bounds, coarse-pointer exclusion, leave/blur reset, visibility pause, offscreen pause, context loss fallback and complete teardown. Scene disposed while import awaits cannot later attach a canvas. No perpetual RAF at rest, global cursor listener or duplicate tickers.
6. Measure emitted chunk groups, first-load route requests, buffer pixels/draw calls and visible animation frame pacing. Keep Three/GSAP out of `/demo` and Plotly out of `/`. Scientific tables precede the lazy Plotly bundle. If a budget fails, reduce visual complexity; do not remove evidence.
7. Complete the real failure tests and capture static/animated/reduced-motion variants. Include loader hold/release tests controlled by delayed resource responses, not screenshots of elapsed-time percentages.

Batch B acceptance:

- The same three concepts are understandable and controllable with SVG only, blocked WebGL, reduced motion, lost context and failed chunk download.
- Scene has a visible “Concept illustration — not experiment data” caption and no probabilistic outcome encoded by geometry.
- ≤12 draw calls, ≤20k triangles, capped resolution, zero scene animation frames while settled/hidden; no increase in live renderers/listeners after ten mount/unmount cycles. Do not require `renderer.info.memory` to be literally zero where engine caches are expected; demonstrate no continuing growth and disposed owned resources.
- Timings/eases/camera/materials match design. App controls never wait for a transition. No GSAP/Three event handler writes storage, credentials, routing, experiment selection or results.
- Production performance measured under design §11 conditions; results stated as measurements, not universal guarantees. If targets are unmet, report actual numbers and exact blocking cause.

## 6. Large vertical batch C — integrated candidate and independent acceptance

**Dependency:** A+B coherent candidate; safe parent-provided backend/test harness for API-linked checks. **Outcome:** one reviewable source delta with reproducible evidence, no self-acceptance.

1. Run the unaffected-owner hash comparison, targeted frontend typecheck, isolated build and all new presentation tests. Record new/modified/deleted paths and dependency diff. Do not “clean” unrelated working changes.
2. Reuse a parent-approved offline backend/harness serving the same candidate bytes; run all nine accepted workbench cases. The default real-worker harness seeds a stress record and starts a server, so do not accidentally use it for visual screenshots or start a duplicate service. No provider/live/hosted call is authorized.
3. Prove served asset identity. This is important: `npm run build` invokes `scripts/copy-static.mjs`, which recursively removes and replaces `shiftguard/static`. Do not execute it until the parent explicitly authorizes generated-output replacement and owns a snapshot. An isolated Vite build alone does not update the API-served browser app. If the backend serves old static bytes, browser evidence is NOT evidence for this refresh; stop the affected check.
4. Parent supplies or authorizes staging the candidate generated assets for integrated checks, then independently verifies the exact emitted set/hash/MIME. Do not preserve the old four-file-count requirement as a fixed count: intentional code splitting changes the set. Instead require the complete exact new build graph and its hashes, without orphan assets or mismatched index.
5. Run the five static-boundary cases against staged candidate assets in the authorized fixture. If `bank-stress`/`plotly` move out of the root JS entry, update the product-content assertion to inspect the actual emitted import graph reachable from index; still require correct MIME and valid served assets. Never insert sentinel words to appease an obsolete string assertion. Parent review must cover this small test change.
6. Deliver screenshots, measurements, exact commands/exits and all required case outcomes with source binding. Request one consolidated independent frontend review through the parent. Luna may resolve ordinary correction deltas inside its approved files, then rerun only affected checks. Parent owns broader full-suite and Gate 6/BYO acceptance.

Do not commit, stage, deploy, publish, call inference or change governance. Stop at the completed frontend candidate/parent-verification boundary. The parent can accept the visual candidate separately while Gate 6 or BYO remain pending; a missing required frontend contract cannot be relabeled “passed” by that separation.

## 7. Conditional dependencies; no fake integrations

**Agent:** the initial candidate is designed to show a blocked information band. Existing agent implementation files remain retained. To activate later, parent must supply the corrected durable-request, auth-recovery, safe-grounding and provider-kind contract plus independent evidence for affected findings. G6-P01/P02/P07 and S04–S07/S09–S12/S14/S17/S18 are relevant; the parent resolves the complete gate, not just this list. Mere `enabled && available` and a model string cannot label live Nemotron. Use explicit scripted/disabled/unverified/live states only when justified. G6 live proof is a separate account/model/budget-authorized run.

**Agent tests:** retain `test_agent_flow.spec.ts` and its failed/historical meaning. The current `[real agent]` test against scripted startup must not be treated as live proof. After default-disabled release composition it may no longer match the public UI; record it as BLOCKED_FOR_AGENT_INTEGRATION, and have the correction owner provide the corrected isolated harness/activation test branch. Do not skip, xfail, rename to conceal failure, or delete the case. The new blocked-surface tests explicitly prove no provider requests; they do not substitute for agent contract coverage.

**Business BYO:** parent owns real upload/account/tenancy/schema/model/retention/error-state design and backend acceptance. Reserve `/workspace...` and the visual error slots; render only “Planned — not available in this build.” No upload demo that accepts and discards a file, no fake progress/success, no silent use of public Bank data as uploaded data, no business-model dropdown claiming unsupported model families. When parent provides accepted contracts, integrate them as a separately authorized complete journey, with private server states and permission/error tests. This packet does not define or implement those APIs.

**Scientific numbers:** React selects/formats existing payload values; Three/GSAP use presentation state only. No frontend calibration, loss calculation, metric deltas, statistical inference, fallback inference, evidence compatibility logic or invented scores. Formatting percentages for existing rates remains with the existing formatter.

## 8. Preservation test matrix

Existing tests inspected, not executed during design:

| Owner/case | Must remain true |
|---|---|
| `test_flagship_preset.spec.ts`: stress run | Real worker output; all six filters; plotted y arrays equal persisted values; reliability sample size bound to condition; fixed 50 budget; cost pair/FP/FN values; deliberate rerun new key/job but deterministic experiment identity |
| Same file: outage and baseline cases | Each publishes its own readable persisted preset table; no invented stress charts |
| `test_reload.spec.ts`: cache/mobile/keyboard | Same session and cache after reload; all eight sparse fields survive; 9/8,229/9 fixture values; no `failed_attempts`; no secret in DOM/URL; four Plotly views; 390px no page overflow |
| Same file: submission auth | Recognized 401 exposes explicit Reconnect; rejected pending discarded on replacement; new deliberate key; business 403 keeps identity |
| Same file: unavailable/corrupt cache | Null/failed payload stays unavailable; corrupt storage recovers to usable empty state |
| `test_job_errors.spec.ts`: lost accepted response | Real API acceptance, simulated lost reply, reload and retry same key and same job |
| Same file: worker/cancel errors | Failed cancellation retained/retryable; cancel_requested distinct from terminal cancelled; failed job preserves cache |
| Same file: reload/session/network/storage | Existing initialization replacement behavior; offline cached plots; explicit reconnect; quota warning |
| `test_static_boundaries.py` | Entry/build assets genuine JS MIME; missing asset stays 404; `/api`, `/api/`, `/api/unknown` remain JSON 404 |

New independent presentation acceptance cases:

| ID | Probe and exact expected outcome |
|---|---|
| F01 | `/` heading/copy/CTA; `/demo` full manual UI; deep link/reload/back; marketing makes no `/api/` calls |
| F02 | Four `/workspace...` routes and disabled nav: planned text, demo exit, no form/file input/auth/upload/private-network request |
| F03 | `/does-not-exist` client 404 with two functional links and title; API result 404 stays inline; actual API/asset status unchanged |
| F04 | Hold root/route chunk pending then release: real loading state exits on resolution; no minimum delay; fail chunk shows recoverable screen; noscript explanation present |
| F05 | Hold result fetch with valid cached record: old evidence remains; completion changes source accurately; failed fetch preserves record and shows error |
| F06 | Hold/fail Plotly import: all four numeric tables remain; error boundary contains failure; no zero substitution |
| F07 | Block WebGL/Three chunk; synthesize context loss; slow-scene downgrade: static chapters/navigation remain operable, no app crash |
| F08 | Reduced motion before mount and toggled at runtime; coarse pointer; hidden tab; user pause: no parallax/continuous render, no duplicate cleanup subscriptions |
| F09 | 320, 390, 768, 1024, 1440 widths; 200% zoom; longest IDs/errors/method names: no page overflow or clipped controls; tables scroll locally |
| F10 | Keyboard-only all real routes/controls, named focus rings, screen-reader state announcements, forced colors; no focus stolen by poll or animation |
| F11 | Null/adverse/unqualified/fallback values and fixed-budget mismatch remain visible; filters do not change run configuration; eight-field cache exact after reload with refetch blocked |
| F12 | Ten scene mounts/unmounts and preference toggles: one or zero canvas as appropriate, no listener/RAF growth, stale import cannot attach after exit |
| F13 | Network/chunk and perf capture: `/` excludes Plotly, `/demo` excludes Three/GSAP; visible content precedes optional media; budgets reported |
| F14 | Blocked assistant makes zero status/submit/resume provider-path requests, contains no active query control; manual run remains usable |

Visual-only tests may use controlled network fixtures to exercise failure timing and must label them simulated. Those fixtures never claim real provider behavior or backend durability. Use real persisted fixture payloads from the authorized harness for scientific fidelity assertions; do not generate an aesthetically convenient chart dataset. Preserve strict console/page error assertions with only narrow expected blocked-resource handling in the specific simulated tests.

## 9. Safe commands for later execution

All commands here are **instructions only, not commands executed for this design**. Use PowerShell, repository cwd unless stated. Adapt evidence destination only to a parent-authorized location. No command below authorizes installing packages, replacing active static output, provisioning services or using a hosted endpoint.

Read-only baseline:

```powershell
git -c 'safe.directory=C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard' status --short
git -c 'safe.directory=C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard' rev-parse HEAD
git -c 'safe.directory=C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard' diff -- frontend tests/e2e tests/integration/test_static_boundaries.py
```

Frontend typecheck and isolated production build, from `frontend`:

```powershell
npm run typecheck
$sgRefreshBuild = Join-Path $env:TEMP ('shiftguard-refresh-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $sgRefreshBuild
npm exec --no -- vite build --configLoader native --outDir $sgRefreshBuild
```

Record both command exits, emitted paths and gzip sizes. This deliberately invokes Vite directly after typecheck, avoiding `scripts/copy-static.mjs`. Use a fresh unique output directory; no recursive deletion or `--emptyOutDir` is needed. Do not run `tsc -b` merely for isolated verification if it writes build metadata into a protected path.

New presentation harness, only after the parent supplies an explicit local static preview URL serving those exact emitted bytes:

```powershell
$env:SG_REFRESH_PREVIEW_URL = 'http://127.0.0.1:4173'
npm exec --no -- playwright test --config playwright.refresh.config.ts
```

The port above is a concrete default, not evidence a server exists. The config must require/validate this loopback URL, use the approved browser, select only the new refresh tests, disable existing global setup/webServer and write reports to a unique parent-approved directory. Never inherit `SG_E2E_BASE_URL` pointing to an unknown/hosted environment. The parent owns starting/reusing a preview process; when authorized, a preview may use the isolated Vite outDir, without serving APIs. Do not import the real seed helper into this harness. Controlled route mocks supply presentation-state fixtures where needed.

Gate 5 integrated browser preservation, **only against the parent's verified offline, provider-disabled, candidate-serving harness**:

```powershell
npm exec --no -- playwright test --config playwright.config.ts test_flagship_preset.spec.ts test_reload.spec.ts test_job_errors.spec.ts
```

The current config can create a server/database and defaults to scripted provider. Parent must first provide the safe harness/environment; do not blindly execute this line. If using an explicit prestarted local base URL, confirm its dataset isolation, no live-provider capability, real seed fixture and asset hashes before accepting results. Hosted mode skips the seed setup, so the fixture must already exist. Retain command provenance and label simulated transport versus real worker evidence separately.

Static boundaries, repository cwd, after authorized asset staging and a parent-confirmed disabled provider test environment:

```powershell
$sgRefreshTestTemp = Join-Path $env:TEMP ('sg-refresh-static-' + [guid]::NewGuid())
& .\.venv\Scripts\python.exe -B -m pytest tests/integration/test_static_boundaries.py -q -p no:cacheprovider --basetemp $sgRefreshTestTemp --tb=short
```

Do not run normal full backend tests, reproductions or Gate 6 live canaries as routine aesthetic checks. The parent determines affected wider evidence. Never advertise baseline reports as fresh checks.

## 10. Stop conditions and handoff

Stop only the affected integration, finish independent authorized frontend work, and report the exact dependency when:

- Parent has not dispatched Luna or has not resolved overlapping application ownership. With no dispatch, **all implementation remains stopped**.
- Backend/private upload/auth/model contracts are unfinished; planned routes remain disabled. No placeholder upload behavior.
- A required behavior change would touch frozen workbench/cache/transport or scientific owners. Describe the failing invariant for the parent; do not introduce a replacement owner.
- Agent recovery/grounding/provider-kind contracts remain defective; retain blocked assistant and existing finding status. Do not represent blocking as a mere visual issue.
- Build staging would overwrite unreviewed static artifacts without parent authorization, or browser is serving bytes different from the candidate. Isolated builds may continue; integrated verdict stays BLOCKED.
- Required tests cannot execute because of harness/provider/collection failures; preserve actual failure, do not skip or fabricate pass counts.
- A package/font is unavailable under authorized access. Preserve complete static experience and report that visual dependency; do not fetch from unofficial mirrors or install globally.
- A design would require scientific estimates, fake customers/ROI, supported business models or claims of live Nemotron without accepted evidence. Use the exact honest-state copy.

One compact final handoff to parent: intended model/settings; source HEAD/base/raw manifest; exact changed/new paths; protected-path hash comparison; dependency versions; per-command exit and per-case PASS/FAIL/BLOCKED/NOT_RUN; screenshots at specified sizes/states; measured bytes/performance; simulated-vs-real evidence labels; unresolved owner dependencies. Do not include capability tokens, raw data, server paths from results, environment secrets or provider credentials.

Independent review must verify behavioral preservation and the actual emitted/served source, not merely approve screenshots. Parent alone records source acceptance and any later Gate 6/BYO closure. This frontend packet changes none of the existing accepted, frozen, failed or pending evidence.
