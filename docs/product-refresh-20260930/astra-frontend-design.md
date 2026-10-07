# SHIFTGUARD — The Evidence Instrument

Design specification · 30 September 2026 · reviewable proposal, not implemented.

Requested design assignment: GPT-6 Astra Extra High (`gpt-6-astra`, `xhigh`). Execution recipient, only after parent authorization: GPT-6 Luna Extra High (`gpt-6-luna`, `xhigh`). These are requested roles, not an attestation of this chat's runtime model. This packet does not dispatch either model.

## 1. Scope and source of truth

Deliver one distinctive business-facing introduction and a restyled, scientifically faithful benchmark workbench. The visual identity is a precision instrument on warm paper: deep green-black type, vermilion registration marks, narrow technical rules, generous editorial space, and one dimensional missing-data lattice. The website should make a practical question legible: when model inputs disappear, what happens to probability quality and recorded decision loss, and what evidence supports the answer?

This directory is design documentation and standalone brand studies only. No application code, packages, build output, backend, governance, historical evidence, commits, deployment or API calls are authorized by creating it. The parent's whole-history review, cleanup and business-BYO planning remain separate.

Inspected current sources: repository `AGENTS.md`; `.agent/session-state.md`, `ownership.json`, `gates.json`, `handoff.json`; `docs/blueprint-progress.md`, `gate5-acceptance.md`, `gate6-review.md`; frontend-affecting sections of `gate6-sol-review.md`; the frontend and tests mapped below. Observed HEAD: `83037b0f02eef62203c3f565a063d824af2722d7`, with existing dirty/untracked Gate 6 work. This is an inspection snapshot, not a new source freeze.

- Gate 5 accepted source remains `f63116fedc2751493d79d44897ba913b6d28b0b5`, source digest `0e961a563ca38f02074b86a95c67fac8267b26f27182a8dab9a2f1256e28f492`.
- Gate 6 remains **PENDING / REVIEW_FAILED_CORRECTIONS_REQUIRED / BLOCKERS**, 25 findings, reviewed digest `4d392741d38da64eb480f5f04bc97a3221649ee9a7ef7b4e8ec13be4fcc9e1d8`. Live evidence remains `BLOCKED_REQUIRED_LIVE_EVIDENCE`.
- Historical Gate 5 evidence: author 9 browser cases; parent 3 affected browser and 5 static cases; reviewer 8 probes. None were rerun for this design. An aesthetic refresh neither accepts Gate 6 nor changes accepted backend/scientific evidence.
- The user's scoped Astra/Luna assignment overrides older local role exclusions for this design/packet only. It does not change repository governance or appoint an application writer now.

## 2. Audience, story and honest product states

Primary reader: a model owner or operations lead evaluating whether SHIFTGUARD's benchmark evidence addresses their missing-input problem. Secondary reader: the analyst checking records, qualifications and provenance. Audience intent is a design assumption, not evidence of customers or supported industries.

Exact opening copy:

> **When inputs shift, know what still holds.**
>
> Inspect how missing inputs affect probability quality and decision loss. Explore reproducible Bank benchmark runs, compare recorded calibration results, and trace each result to its saved evidence.
>
> **Explore benchmark demo** · **How evidence is built**
>
> Available today: Bank benchmark presets. Single-seed development evidence. Private-data workflows are planned.

The primary action opens `/demo`; the secondary action goes to `/#method`. Neither submits a run. “Decision loss” means the persisted weighted false-positive/false-negative calculation under recorded cost pairs; it is not currency, realized savings or measured ROI. Explain Brier/log loss in brief tooltips or adjacent text without renaming scientific fields. Say “Lower recorded loss” only when that value and comparison are actually available and qualified; never headline adaptation as guaranteed improvement. Accepted evidence includes an unfavorable target-adaptation outcome.

| Feature | Real state at inspection | Public presentation for refresh | Activation boundary |
|---|---|---|---|
| Approved Bank baseline, outage-50 and stress runs | Implemented Gate 5 browser capability | Available benchmark demo; server fixes seed 31001 | Existing API/session availability |
| Four comparative plots and numeric tables | Persisted Bank stress payload only | Budget, missingness pattern, reliability, decision loss | Actual loaded stress record; baseline/outage retain their own result table |
| Browser-cached/server-persisted results; job retry/cancel | Accepted bounded semantics | Explicit cache source, job status, retry and reconnect controls | Existing owners below |
| Natural-language assistant | Offline candidate exists; Gate 6 blocked | “Assistant integration under review”; manual controls remain available | Parent-approved corrected contracts and independent evidence; live labeling additionally requires exact-model live proof |
| Scripted assistant in a test harness | Simulation; existing live-looking label is G6-P07 | “Scripted test provider” in isolated tests, never “live” | Corrected isolated harness/provider-kind contract |
| Private workspace and business dashboard | Planned, not implemented | Disabled “Private workspace · Planned” nav item, explained by visible text | Parent's BYO/auth/tenancy contract and acceptance |
| Upload private data or a business model | Planned; no accepted upload or arbitrary-model support | No file picker/drop zone, credentials field, sample upload or fake success | Parent closes backend requirements; separate authorization |
| Onboarding/schema mapping/validation and private runs | Planned, not implemented | Static three-step preview marked “Planned” | Parent-owned real contracts for schema, roles, errors and lifecycle |
| Customer deployments, pricing, ROI, monitoring alerts, compliance guarantees | No evidence in inspected scope | Omit logos, claims, pricing and badges | Separate substantiation and scope |

Business narrative has three chapters, not a feature-card wall: **01 Expose the gap** (missing-input structure); **02 Compare the evidence** (recorded calibration methods, including failures); **03 Inspect the consequence** (recorded cost settings with provenance). Pair each with one clear sentence and a ruled diagram. No fabricated metrics, live counters, testimonials, “trusted by”, supported-industry grids or mock portfolios.

## 3. Information architecture and layouts

### Routes

| Location | Concrete design |
|---|---|
| `/` | Public introduction, conceptual 3D, method chapters, capability ledger, planned-workspace preview, final demo CTA |
| `/#method`, `/#availability` | Native anchors; header-offset scroll margin; reduced motion uses immediate scroll |
| `/demo` | Accepted manual workbench presentation; actual session/API state, no marketing hero blocking controls |
| `/workspace`, `/workspace/onboarding`, `/workspace/dashboard`, `/workspace/upload` | Recognized but disabled planned routes. Informational availability screen only; no hooks, session creation, private API, data selection or submission |
| Any other app pathname | Custom app 404 described below |
| `/api`, `/api/*`, `/assets/*`, existing health endpoints | Backend owns response and status; frontend must never intercept or substitute an app screen |

Use normal same-origin links and an explicit small pathname allowlist in the frontend; no router dependency is necessary for this scope. Full-document navigation is acceptable. Preserve hash anchors, back/forward and direct load/reload. Unknown query parameters never grant features or auto-submit. `/demo` initializes the workbench once; other routes do not create sessions. Jobs continue on the server while a user leaves the workbench, and existing storage restores their identity on return. No new routing callback may submit, resume an agent, or cancel jobs.

### Desktop composition, 1440 × 1000 reference

Content width: `min(1312px, viewport - 128px)`; 64px side margins at 1440. Twelve columns, 24px gutters. Header: 80px high, logo left, Method/Availability text links, outlined “Explore demo” right. No floating blurred navbar. Header remains in normal flow on marketing pages.

Hero begins 64px below header. Left five columns: small “CALIBRATION UNDER MISSING INPUTS” eyebrow, 80px heading in three deliberate lines, 18px description, primary vermilion CTA and quiet underlined method link. Right seven columns: 600 × 460 scene viewport, softly bounded only by corner registration marks; one large coordinate-like vertical rule anchors the composition. Caption and HTML chapter buttons beneath. Never place copy behind the canvas.

Hero height is content-driven, approximately 600px excluding header; no enforced full-screen height. The bottom of the first desktop view includes a full-width dark forest evidence strip: “Bank benchmark / Development evidence / Traceable records”, typographic labels rather than status claims. It has no sample numbers. The next section's heading is partially visible, signaling normal scrolling.

Method section: 112px top/bottom spacing. Three consecutive rows, each with a 72px index rail, five-column heading/body and six-column technical illustration; thin horizontal rules divide rows. The single 3D scene stays in the hero. Method rows use static SVG diagrams, with no second renderer or pinned reading sequence.

Availability section: one generous two-column ledger headed “What you can use today.” Left: three real benchmark abilities; right: a slightly inset planned-workspace drawing with visible “Planned — not available” eyebrow. No active signup or upload CTA. Footer repeats the demo action and a concise development-evidence limitation. Version/gate IDs belong in an expandable technical-details area, not the sales headline.

### `/demo` composition

Header 72px; content max 1488px with 32px gutters at desktop. Compact title row: “Benchmark workbench”, subtitle “Bank presets · development seed 31001”, API state, session ID disclosure and Reconnect when the current owner requires it. Keep `.session-id` and its non-secret session-ID title available to existing tests; never expose capability tokens.

Run control spans the page: existing Approved preset select, Submit run, seed explanation. Error/recovery notice immediately follows; do not bury a retry below charts. Below it, use a 272px job/publication rail, 24px gap and a fluid evidence column. Preserve `.job-card`, `.job-status`, `.published-list`, `.result-heading`, `.result-source` during first extraction. Keep “Experiment result” and “Published preset result” accessible headings.

Evidence column order: source badge and record heading → six labeled filters → fixed-budget explanation → selected diagnostics and identity/provenance → four plot/table panels. Charts are two columns only when each receives ≥460px; otherwise one column, even at a wide viewport with the rail. Tables remain directly under their plots and visible without hover or modal. Use scrolling inside wide tables, never whole-page horizontal scroll. A thin section index links to Evidence / Jobs / Activity; it does not hide evidence in tabs.

The assistant is a subordinate, non-alert informational band after evidence and before activity: “Assistant integration under review. Use the benchmark controls above.” Current release mode does not mount `useAgent` or enable a query. Retain the unaccepted agent files intact for their correction owner. Future corrected assistant view can expand here using the state contract in §8; visual work does not repair the agent runtime.

## 4. Brand system and exact tokens

Logo: **the displaced register**. Three square-ended horizontal strokes form an angular S; the middle stroke shifts by one module. Two corner brackets hold the figure to a stable frame. It communicates a changed input inside a retained reference, not a claim of cybersecurity protection. Standalone [shiftguard-mark.svg](shiftguard-mark.svg) defines the master 64-unit geometry. Clear space 8 units; minimum icon 24px; favicon uses the mark alone. No animated logo while users read measurements.

Wordmark: SHIFTGUARD in Manrope 700, uppercase, tracking 0.08em, mark left at 32px with 12px gap; wordmark 17px. On dark forest, use ivory strokes with a citron middle register. All monochrome uses one ink. The companion [shiftguard-brand-study.svg](shiftguard-brand-study.svg) is a static review board, not a screenshot or application implementation. Its system-font rendering is a fallback; normative typography is below.

| Token | Value | Use |
|---|---|---|
| paper | `#F4F1E9` | Main background |
| surface | `#FFFEFA` | Tables and workbench panels |
| ink | `#182922` | Headings/body |
| muted | `#56635B` | Secondary copy |
| accent | `#B84224` | Primary CTA, registration stroke, active chapter |
| forest | `#11271F` | Evidence strip and footer inset |
| citron | `#DDE88A` | Small accents on forest only |
| rule | `#D6D9CE` | Decorative dividers; not a control's sole boundary |
| control-line | `#7C877D` | Input/control boundaries |
| success | `#276548` | Confirmed completed status, paired with text |
| warning | `#825500` | Unqualified/fallback/waiting state, paired with text |
| error | `#A5322D` | Failed operation, paired with icon and text |
| info/focus | `#285C8E` | Informational state, 3px visible focus ring on light surfaces |

Computed flat-color contrast: ink/paper 13.49:1; muted/paper 5.58; accent/paper 4.84; surface/accent 5.42; citron/forest 11.98; success/warning/error/info on paper 6.12/5.73/6.01/6.18. Control-line/surface 3.70. Rule/surface is only 1.42, hence decorative only. No opacity reduction on enabled text. Dark-surface focus uses citron. Recheck actual composed backgrounds in browser.

Typography: Manrope variable 400–800 for all UI/headings, self-hosted Latin WOFF2 after license/source verification; fallback `Segoe UI Variable`, `Segoe UI`, sans-serif. Mono: `ui-monospace`, `SFMono-Regular`, `Consolas`, monospace; no extra font download. Existing CSS names Manrope/DM Sans/DM Mono but inspected index has no font loading: do not assume they currently render.

| Style | Desktop | Mobile | Rules |
|---|---|---|---|
| Hero | 80/84px, 600 | 42/46px, 600 | Tracking −0.05em; max 11ch line |
| Section title | 44/50px, 600 | 30/36px | Tracking −0.035em |
| Workbench title | 32/38px, 650 | 26/32px | One hierarchy below hero |
| Panel title | 20/27px, 650 | 19/26px | Sentence case |
| Body | 16/26px, 400 | 16/25px | Text columns max 62ch |
| UI/table | 14/21px, 500/400 | 14/21px | No critical 9px text |
| Caption/metadata | 12/18px mono | 12/18px | No tracking on long IDs |
| Metric | 28/34px, 600 | 24/30px | Tabular numerals; no count-up animation |

Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64, 96, 112px. Panel padding 24px desktop/16px mobile. Radius: buttons/inputs 4px, panels 8px, labels 2px; no pill treatment except small connection marker. Buttons 48px minimum height, 20px horizontal padding; compact controls still 44px. Borders 1px. Default panels have no shadow; overlays only use `0 12px 32px` ink at 10% opacity. Avoid glass, bloom, gradients behind text, glowing outlines and nested card stacks.

Chart treatment is quiet: off-white plot area, understated grid, 14px axis/legend labels where panel size allows, method-specific line dash/marker plus color. Preserve trace order and name binding. Palette by existing trace order: `#276548`, `#285C8E`, `#B84224`, `#75518A`, `#62652D`, `#9D3F62`, `#475965`, `#825500`. Assign persistent method styles from method IDs, not whichever method becomes first after filtering. Pattern comparison colors represent block versus cellwise, not methods. Never encode “good” or “bad” by calibrator color. Preserve metric precision and null handling.

## 5. Purposeful Three.js scene: the Missingness Register

This is a **concept illustration, not experiment data**. Display that caption outside the canvas at all times. Three.js never receives payloads, probabilities, labels, IDs, credentials or API clients. Scene props are only chapter, reduced-motion and visibility. Its state cannot modify workbench selectors or scientific values.

Geometry, world units:

- A 10-column × 8-row specimen grid in the XY plane: cube centers `x=(column−4.5)×0.34`, `y=(3.5−row)×0.34`, `z=0`; each cube 0.24 × 0.24 × 0.16, beveled edges unnecessary. Use shared BoxGeometry and at most three InstancedMesh groups. Eight rows are illustrative marks, not sample counts.
- Seven columns form the ordinary-feature region; rightmost three form the history-input region. A fine bracket and HTML label identify “History inputs”. Do not encode the actual missingness rate of a run in this object.
- Reference backplate: 3.72 × 3.08 × 0.035 at z=−0.20, matte ivory. Thin edge bars and corner registration marks establish the fixed reference; no embossed text meshes.
- In chapter 1, all 80 pieces sit in the grid. Chapter 2 withdraws the 12 pieces at columns 7–9, rows 2–5 to z=0.72 and x plus 0.28, with vermilion sides; empty positions retain flat outline squares. This exact deterministic mask is a conceptual block, never a “50% result”. Chapter 3 keeps the gap visible and places a narrow green measuring rail below the grid. Nothing returns to its slot as a purported “AI repair”.
- Calibration comparison is represented by three parallel short measuring rails below the backplate, lengths identical. Their labels are HTML “Raw / Source / Target”. Equal lengths deliberately carry no quality ranking; the real workbench provides measured comparisons.
- Maximum 6 shared geometries, 6 materials, 12 draw calls, 20k triangles. No GLB, textures, particle field, physics, environment-map download, postprocessing or large 3D font.

Camera: orthographic, position `(5.2, 3.6, 7.5)`, looking at `(0, 0, 0.10)`; vertical frustum span 5.2, horizontal span derived from container aspect, near 0.1/far 30. Group rotated −8° about Z. Refit view on resize without stretching; portrait uses span 6.0 and centered object, caption below. Keep the object within 80% of canvas width and height. The browser owns CSS dimensions; update drawing buffer and camera from actual container size. [Three.js responsive design](https://threejs.org/manual/pages/responsive.html).

Material: MeshStandardMaterial, roughness 0.78, metalness 0.08, opaque. Ordinary cubes pale sage `#9EAC9A`; stationary history cubes ink; withdrawn cubes vermilion; frame dark forest; backplate ivory. Hemisphere light sky ivory/ground sage at 2.0, directional key at `(-3, 5, 6)` intensity 2.5, fill at `(4, 1, 2)` intensity 0.7. No real-time shadow map; a single flat low-opacity elliptical floor mark is permissible. Linear tone mapping, sRGB output, exposure 1.0; check the chosen installed Three revision's APIs before coding. These are starting art-direction constants, not scientific quantities.

Renderer: one WebGLRenderer, alpha background over paper, antialias on, drawing-buffer cap 1.5 megapixels and effective DPR ≤1.5 desktop/1.25 tablet. Mobile defaults to the static illustration; “View 3D illustration” is explicit optional enhancement when motion/data preferences permit. No WebGL on the workbench.

Pointer: fine-pointer devices only; container-local coordinates produce ≤±3° X/±5° Y tilt. No custom cursor, pointer lock, dragging or orbit controls. Reset to canonical pose over 300ms on leave/blur. HTML chapter buttons (“1 Inputs”, “2 Missing block”, “3 Compare evidence”) work with Tab/Enter/Space and expose pressed state. Chapter text is always visible in DOM. Static fallback swaps matching SVG/HTML diagram states on the same buttons; no interaction is exclusive to canvas.

Lifecycle: render on demand during entry, chapter tween, pointer movement or resize. Stop after settling; pause when offscreen, tab hidden or illustration paused. On unmount/reconfiguration remove pointer/visibility/context listeners, disconnect ResizeObserver and IntersectionObserver, cancel RAF, revert GSAP contexts, dispose unique geometries/materials/renderer, remove canvas and clear references. Removing a mesh is insufficient disposal. [Three.js disposal](https://threejs.org/manual/pages/how-to-dispose-of-objects.html), [cleanup](https://threejs.org/manual/pages/cleanup.html).

Import failure, unsupported context, context loss or sustained slow rendering switches immediately to the static conceptual illustration; it never blocks navigation or workbench. Show unobtrusive “Static illustration” and one user-initiated “Try 3D again” when applicable. No auto-retry loop. Stale async completion after unmount must dispose its resources rather than attach a new canvas.

## 6. GSAP motion score

Use GSAP core for authored transitions; ScrollTrigger only for the three method-row reveals if actually needed. No smooth-scroll library, scroll hijack, pinned reading sequence, split-letter text or animation of chart data. Content is readable before animation initialization. Optional animation loading never keeps HTML at opacity zero.

| Trigger | Sequence | End condition / reduced-motion substitute |
|---|---|---|
| Route HTML ready | Registration rule reveals over 360ms; hero blocks move 12px to rest over 520ms with 70ms stagger; CTA is already clickable | Total ≤850ms, no wait before use; reduced motion: final positions immediately |
| Three renderer's first successful frame | Crossfade static illustration to matching canvas over 180ms, same dimensions | If not ready, keep SVG indefinitely; no blank canvas |
| Chapter selection | Withdraw pieces in 480ms; measuring rail enters over 320ms; max 35ms row stagger | Total ≤700ms, ease `power2.inOut`; reduced motion: SVG changes instantly |
| Method row enters at 85% viewport | 16px translate and opacity over 400ms, once | No scroll scrub; reading unaffected; reduced motion: no transform |
| Control hover/focus | Underline extends over 140ms; primary background darkens without scaling text | Keyboard focus is immediate; touch has no hover dependency |
| New result received | Thin result-header rule appears over 180ms | Numbers/tables render immediately; no chart drawing/count-up |
| Notice inserted | Optional 120ms opacity only, no height tween | Focus remains with initiating control; error text immediate |

Use scoped `gsap.matchMedia()` for viewport/motion conditions and revert on cleanup; explicitly remove listeners created inside callbacks. [GSAP matchMedia](https://gsap.com/docs/v3/GSAP/gsap.matchMedia()/). React effects must mirror their setup with cleanup, including the development setup-cleanup-setup case. [React useEffect](https://react.dev/reference/react/useEffect). Use the existing React version, not a framework migration.

## 7. Real brand loading states

Loader motif: the logo's three horizontal registers and one text stage. Filled registers indicate completed known tasks; current register is outlined with a traveling accent only while an actual operation is pending. Never show a time-derived percent, count 0→100, invent worker substeps, or hold ready content for a minimum animation duration. The same static mark plus status text is the reduced-motion form.

| Scope | Source of truth | Exact treatment |
|---|---|---|
| Initial route | HTML shell → module resolved → route mounted | Branded route placeholder in `index.html`; clear at mount. With fast load it may never be visible. At 10s still pending, say “This is taking longer than expected” with Reload; do not claim failure from elapsed time alone |
| JavaScript unavailable | `noscript` | Logo, public value statement, “Enable JavaScript to use the interactive benchmark workbench.” No false working controls |
| `/demo` session | `workbench.backend`/`ready`, real owner state | “Connecting to benchmark service”; cached result shown immediately, never covered by loader. Success removes notice; actual failure exposes Reconnect |
| Published record | `busyAction === load-result`; response validated by existing owner | “Opening saved evidence”; keep old result and its source badge until replacement succeeds. No blank-screen skeleton over cached evidence |
| Fresh submission | Persisted pending intent, HTTP acceptance, job status | “Sending request” → “Queued” → “Running” → “Opening published result” → “Evidence ready”; some stages may be skipped. `completed` job alone is not loaded evidence |
| Ambiguous acceptance | Existing pending submission and typed error | “Submission response not confirmed”; use existing Retry submit/Retry same submission and original key. Never reset to fresh submit |
| Plotly chunk | React lazy/Suspense + local error boundary | “Loading chart — numeric values below”; tables render first. On chunk failure show “Chart unavailable — numeric values below” and non-destructive reload/view-table action |
| 3D chunk/context | Module resolved → renderer created → first frame | Inline “Preparing illustration”; retain static SVG. No percent because runtime chunk transfer/compilation has no reliable shared denominator |
| Assistant/provider | Current public mode blocked; future corrected status contract | “Assistant integration under review”; do not show “model loading”. Future real states: checking provider, disabled, unverified provider type, scripted test, available, request working, waiting for job, failed |

Use an ordered list for known workflow stages, text labels and `aria-current="step"`. Do not set progressbar `aria-valuenow` when total work is unknown. Announce stage changes in one polite status region, not every poll. A failure ends its spinner, exposes the relevant action and preserves cached evidence. Long waits do not become completed/failure states on a timer.

## 8. Errors, assistant boundary and planned private workflows

| State | Presentation / behavior |
|---|---|
| API unreachable | API unavailable; Reconnect; existing cached evidence remains usable with browser-cache badge |
| Submission 401 recognized by accepted owner | Existing four-code behavior: explicit Reconnect, no automatic replacement on submit, old rejected intent discarded only through accepted recovery; new deliberate submit required |
| Initial saved-session invalidation on reload | Preserve existing Gate 5 initialization behavior and SESSION_REPLACED notice; do not incorrectly generalize submit-time explicit-reconnect rules to rewrite initialization |
| Business 403 | Existing error and retained session/identity; no “sign in again” or credential rotation |
| Job failure / cancellation requested / cancelled | Distinct text states; cancellation request does not assert cancellation completed; published cache retained |
| Storage unavailable/corrupt/full | Current notice; explain reload limitation; current result remains readable; no clearing valid cache to fix appearance |
| Missing experiment/API 404 | Inline record-not-found/request error in workbench; preserve server JSON/status; never route to marketing 404 |
| Missing or failed metric | “Unavailable”; no zero, dash posing as a number, interpolation, hidden row or cheerful empty chart |
| Unqualified comparison / fallback | Visible warning next to value with reason, requested→resolved method and details; never deem it a successful recovery because a request completed |
| Parent-controlled planned private route | “Private workspaces are planned. This build supports the Bank benchmark demo.” CTA “Open benchmark demo”; no upload or account form |

Gate 6 constraints that affect presentation: G6-P01 pending request identity/reload/retry is defective; P02 automatically reconnects on agent 401; P07 confuses scripted and live providers. S04–S07 affect resume correctness; S09–S12 and S14 affect grounded/qualified evidence; S17 affects safe trace size/content; S18 confuses terminal dialogue and job outcome. **A design cannot solve these.** The release presentation keeps assistant execution disabled until the parent supplies corrected, independently reviewed contracts. Never duplicate these fixes inside a animation hook or hide a failed finding with new copy.

Future corrected assistant view must show provider kind, truthful availability, original durable request/job identity, bounded recovery, persisted counters (never hardcoded “/6” or “/8” when contract differs), safe trace, explicit unavailable values, adverse findings, qualification reasons and evidence links. Missing fallback count is “Not recorded”, not zero. Neither configured model string nor `enabled && available` proves a live provider. Existing `AgentStatus` has no provider-kind field; therefore the refresh cannot infer it. Keep blocked mode until that dependency is resolved by its owner. No unchecked provider narrative, raw tool arguments or server paths may be newly exposed.

Planned BYO design envelope, for the parent to integrate: a private workspace shell with a left navigation rail, a dataset/model-context summary above dashboard evidence, and onboarding steps “Define context → Validate inputs → Review run”. All are labeled **Planned** in this packet and disabled in the proposed initial release. File formats, model families, upload limits, account model, retention policy, permissions, tenancy, validation codes, private result access and deletion rules are intentionally owned by the parent; this packet does not invent them. A blank dashboard says “No private workspace is available in this build”, never fills with fake customers or fabricated run history. Error slots reserve a heading, safe reason, retryability text and action; the parent's real error plan determines their eventual behavior.

## 9. Custom 404

Title: **This route has no record.** Large static “404” aligned to the editorial grid; displaced-register mark with its middle bar outside the frame; one thin vermilion rule. Body: “The page may have moved, or the address may be incomplete.” Actions: “Back to SHIFTGUARD” → `/`, “Open benchmark demo” → `/demo`. No automatic redirect, fake search, random suggested datasets or WebGL download. Document title “Page not found · SHIFTGUARD”; focus the h1 after a client route transition. Never echo raw query strings or capability-bearing URLs.

The inspected `shiftguard/api/main.py` serves the SPA index for non-API/non-asset unknown paths. Consequently the frontend custom 404 is an **app not-found screen with the existing document HTTP 200**, not a newly correct HTTP 404. No backend routing change is authorized by this refresh. Preserve real `/api` and missing `/assets/*` 404 status/MIME and health endpoints. Private planned paths use the planned-feature screen, not this unknown-route screen.

## 10. Responsive and accessible operation

| Width | Layout and behavior |
|---|---|
| ≥1200px | 12-column marketing; hero 5/7 split; workbench rail; charts two columns only above 460px per plot |
| 900–1199px | 40px marketing gutters, 8 columns, hero 1/1 split with 56px heading; workbench 232px rail, single-column plots; filters 3 columns |
| 600–899px | 24px gutters; hero and workbench stack; static illustration default; filter grid 2 columns; job ledger follows run controls before evidence in DOM |
| 320–599px | 16px gutters; 42px hero heading reduced to 36px below 360px; 44/48px controls; filters one column below 380px, otherwise two; plots 300px minimum height; local table scrolling |

Mobile nav uses a native details disclosure (“Menu”), links in DOM; Escape closes and returns focus, outside-pointer close optional, no modal trap. Keep one clear demo link visible. No fixed bottom bar covering errors. Run status is near the submit control; mobile ledger is compact but does not hide active jobs. DOM reading order remains useful without CSS reordering. At 200% zoom it reflows; at 320 CSS pixels the page itself has no horizontal overflow. Long IDs wrap in expanded provenance; truncated IDs have an explicit accessible full-value disclosure, not only hover title.

Target WCAG 2.2 AA: 4.5:1 ordinary text, 3:1 large text and meaningful control graphics; 44px targets by design; keyboard-visible focus; native labeled controls; headings/landmarks/skip link; status updates without stolen focus; use text plus shape/icon for status. Decorative canvas has `aria-hidden`; its meaning and controls live in HTML. Tables retain captions and scope headers, with named keyboard-focusable scroll regions only when overflowing. [WCAG 2.2](https://www.w3.org/TR/WCAG22/).

Reduced motion removes parallax, translation, scroll reveal and animated loading marks; charts still render their persisted data. A visible “Pause illustration” control stops authored movement immediately and keeps the canonical pose, with state honored during that page visit. Default sequence is one-shot, no perpetual ambient animation. Forced-colors mode uses system colors and the monochrome diagram; do not rely on canvas, fill-only badges or faint rules. Text never appears inside canvas. No audio or flashing effects.

WebGL-off acceptance means all HTML business content, route navigation, presets, job controls, cached evidence, four tables and ordinary SVG/canvas Plotly charts still operate. JavaScript-off is explicitly limited to the static entry explanation; do not claim the interactive workbench works without JS.

## 11. Performance and dependency budget

Locally verified installed and lockfile versions match: React/React DOM **19.3.0**, Plotly **4.1.1**, react-plotly.js **4.1.0**, Vite **7.3.6**, TypeScript **5.9.3**, Playwright **1.63.0**. `package.json` declares ranges, not these exact versions. Three.js, GSAP and `@gsap/react` are **not installed**. This design does not pick an unverified “latest” version. Luna must resolve exact compatible Three/GSAP releases through official package metadata during authorized implementation and commit their reviewed lockfile change only when the parent authorizes commits. Direct Three integration plus GSAP core is sufficient; do not add React Three Fiber, Drei or another router.

| Budget | Target and measurement |
|---|---|
| Critical marketing HTML+CSS+JS | ≤220 KiB gzip, excluding optional scene and font; measure Vite emitted files/actual network |
| Fonts | One Manrope variable Latin WOFF2 ≤70 KiB, swap; network failure uses system fallback without hidden text |
| Standalone brand/static illustrations | ≤35 KiB total gzip; no remote images or video |
| Optional Three/GSAP scene chunk group | ≤240 KiB gzip combined; loaded after first content and only when eligible/visible |
| Workbench Plotly | Preserve lazy basic bundle in `charts/Plot.tsx`; never load full Plotly in root, never load Plotly on `/` |
| Performance acceptance | Cold production build, 390×844, 4× CPU slowdown, 1.6 Mbps down/150ms RTT: target LCP ≤2.5s, CLS ≤0.05; lab interaction latency ≤200ms for local control changes. Report actual setup/results; these are targets, not measured claims |
| Scene | ≤12 draw calls, ≤20k triangles, ≤1.5M buffer pixels; zero animation render frames while settled/hidden; target ≥30fps during intentional movement on constrained device |

Scientific JSON transfer/parse costs are measured separately and must not be hidden by excluding them from the workbench experience. Existing `plotly-basic.min.js` on disk is 1,191,749 bytes uncompressed; that is not a built gzip/network measurement. Establish actual baseline chunk sizes before prescribing Plotly savings. Do not shrink evidence, cache projection or tables to meet visual budgets.

Chunk groups: initial public shell; lazy workbench/chart components; existing lazy Plotly basic; optional Three scene and GSAP motion. The scene is isolated from request/state code. Slow-scene downgrade: after two consecutive 2-second visible animation windows below 24fps, stop and use static illustration; document this as a visual fallback, not API failure. Preferences for reduced motion/data saving select static immediately when available. Do not fingerprint GPU hardware.

## 12. Inspected ownership map and preservation contract

Paths are relative to `C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard`; these are existing owners, not proposed duplicates.

| Existing file | Responsibility inspected | Refresh boundary |
|---|---|---|
| `frontend/src/App.tsx` | Presets, view selections, published list, composition, agent wiring | Extract retained workbench composition; preserve selectors/filter transitions; add public route composition |
| `frontend/src/styles.css` | Entire current UI; 1150/820/600 breakpoints; agent styles | Replace deliberately by scoped semantic tokens/layout, not global bulk search/replace |
| `frontend/src/hooks/useWorkbench.ts` | Session validation/reconnect, bounded persisted intent, submit/retry, 1800ms polling, terminal monotonicity, cancellation, result fetch/cache | Keep behavior and hook source unchanged for aesthetic batches |
| `frontend/src/state/workspace.ts` | `shiftguard.browser-workspace.v1`, last eight jobs, cached source restoration, bounded sanitized record | Preserve schema/storage key, retention and errors |
| `frontend/src/api/client.ts`, `api/types.ts` | Same-origin API/errors, 20s timeout, credential headers, published payload and exact cache projection | Preserve; no second client or numeric projection |
| `frontend/src/components/ResultDetails.tsx` | Selected condition, eight sparse diagnostics, fallback chain, metrics and provenance | Layout/legibility only; preserve all evidence |
| `frontend/src/components/PresetResult.tsx` | Baseline/outage result tables distinct from stress | Keep separate; do not invent four plots for these records |
| `frontend/src/components/charts/BudgetCurve.tsx` | Stored points, selected-budget diagnostic row, available→null gaps | No smoothing/resampling or invented points |
| `frontend/src/components/charts/PatternVsRate.tsx` | Persisted matched comparison, budget, qualification/residual/tolerance | Keep unqualified values and warnings together |
| `frontend/src/components/charts/Reliability.tsx` | Fixed budget 50, null bins, counts, condition-matched sample size, reference diagonal | Never imply selected budget changes this panel |
| `frontend/src/components/charts/DecisionLoss.tsx` | Fixed budget 50, recorded costs/thresholds/loss/FP/FN/sample counts | Selector filters existing pairs only |
| `frontend/src/components/charts/shared.tsx`, `Plot.tsx` | Formatting, accessible tables, lazy Plotly basic, null handling | Add visual theme/error boundary without changing numbers |
| `frontend/src/hooks/useAgent.ts`, `api/agent.ts`, `components/AgentPanel.tsx` | Unaccepted agent state/transport/presentation | Correction owner retains behavioral work; initial refresh does not mount execution; future shell consumes only accepted contract |
| `frontend/src/main.tsx`, `frontend/index.html` | React root; currently empty entry placeholder | Route-aware shell, static boot explanation, no API behavior |
| `frontend/package.json`, `package-lock.json`, `vite.config.ts` | Dependencies/build/proxy | Dependency/chunk change only in later authorized batch |
| `frontend/scripts/copy-static.mjs` | Build copies dist and recursively replaces `shiftguard/static` | Do not run standard build in this design run; isolated build path in execution packet |
| `frontend/playwright.config.ts`, `frontend/e2e/fixtures.ts`, `frontend/scripts/e2e-setup.ts`, `e2e-server.py` | Browser harness, error assertions, real CLI seed/server; current scripted-provider default | Parent owns harness/provider correction; use safe isolated visual config later |
| `tests/e2e/test_flagship_preset.spec.ts`, `test_reload.spec.ts`, `test_job_errors.spec.ts` | Nine accepted browser cases | Preserve assertions/real-worker identities; route entry changes only |
| `tests/e2e/test_agent_flow.spec.ts` | Three current agent cases, including misleading `[real agent]` title under scripted harness | Do not treat as live proof or weaken to accept known defects |
| `tests/integration/test_static_boundaries.py`, `shiftguard/api/main.py` | Five static cases and current SPA/API/asset boundaries | Preserve 404/MIME guarantees; backend file unchanged |

Eight-field sparse projection must remain: `affected_fallback_rows`, `resolution_counts`, `bin_eval_counts`, `bin_fallback_counts`, `bin_support`, `bin_resolution_counts`, `bin_resolved_maps`, `sparse_prediction_failures`; internal `failed_attempts` stays excluded. Fixture values 9 affected rows / 8,229 fitted-bin / 9 source-remasked are preservation evidence, never homepage marketing statistics.

## 13. Design acceptance

Review this specification together with the static brand study and [Luna execution packet](luna-frontend-execution.md). A faithful implementation has: the exact editorial visual system; one purposeful and disposable scene; honest feature states; real route/data/provider loading; a branded client 404; accessible static fallback; intact persisted-data behavior; and measured performance. Visual completion is a separate verdict from source acceptance, Gate 6 correction, live-provider proof and business-BYO readiness.

Preparation verification: **PASS** — both standalone SVGs parse as XML with no scripts or external images; the brand study was rendered in memory and visually inspected; local installed/lockfile versions agree; flat-color contrast was calculated; 43 inspected frontend/static/browser-test path states match their pre-write hashes, including already-absent tracked assets. **NOT_RUN by scope** — application build, browser/backend tests, live APIs and runtime performance. This task authored only the two Markdown packets and two standalone SVGs in this directory. Other concurrently authored parent files are not this task's deliverables.
