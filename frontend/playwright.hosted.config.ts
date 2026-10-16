/*
 * Hosted clean-browser smoke configuration for the LIVE server (SG_E2E_BASE_URL).
 *
 * Selection rule: product specs only, and NO paid calls. The live server has the real
 * model provider enabled behind a paid daily cap, so a test is selected only if every
 * route that could reach the Results assistant or general chat is fulfilled/aborted by
 * the test itself (page.route mock) or by the refresh audit fixture (which aborts every
 * /api/ request client-side), or if the test never has a path that sends one. Excluded:
 *   - tests that forward a real POST /api/v1/agent/requests or /chat/messages (route.fetch/continue),
 *   - tests that need the local scripted harness (metadata.repoRoot/pythonPath/isolatedDatabase,
 *     /__test__ worker scenarios, local sqlite edits, SHIFTGUARD_ALLOW_TEST_SCRIPTED_PROVIDER),
 *   - tests that rely only on an assertion ("expect no POST") instead of an interceptor,
 *   - the heavy bank-stress run and specs that are skipped without SG_NORMAL_EXPERIMENT_ID.
 * Every selected test is named in an exact-title ALLOWLIST (anchored regex), so a test added to
 * any file later is NOT run by default. Defence in depth: e2e/fixtures.ts blocks and fails on any
 * non-GET paid-endpoint request when metadata.hostedSmoke is true, and scripts/hosted-budget-tripwire.ts
 * (globalSetup) fails the run if the live ordinary budget changes.
 *
 * Operating rules:
 *   - Do NOT use --retries or --repeat-each: they multiply live Bank jobs (expected 3).
 *   - Expected test count is exactly 64 (verify with --list before running).
 *   - Set SG_GATE5_ATTEMPT_DIR to a dedicated folder under ../verification (not ../verification/gate5) for each hosted run;
 *     the tripwire refuses the Gate 5 folder and an already used folder.
 *   - The live server must hold a stress_engine record in its latest 20 experiments and run
 *     build 55e75c4 or later.
 * Live jobs created by the selected set: 3 Bank presets (job_errors lost-response test 1,
 * flagship bank-outage-50 1, flagship bank-baseline 1).
 */
import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

const raw = process.env.SG_E2E_BASE_URL?.trim();
if (!raw) {
  throw new Error("playwright.hosted.config.ts requires SG_E2E_BASE_URL (the live hosted origin).");
}
let hosted: URL;
try {
  hosted = new URL(raw);
} catch {
  throw new Error("SG_E2E_BASE_URL must be a valid absolute URL.");
}
if (hosted.protocol !== "https:") {
  throw new Error("SG_E2E_BASE_URL must be an https origin.");
}
if (hosted.username || hosted.password) {
  throw new Error("SG_E2E_BASE_URL must not contain credentials.");
}
if (hosted.pathname !== "/" || hosted.search || hosted.hash) {
  throw new Error("SG_E2E_BASE_URL must be a bare origin: pathname '/' with no search or hash.");
}
const hostname = hosted.hostname.toLowerCase().replace(/^\[|\]$/g, "");
const loopback = hostname === "localhost" || hostname.endsWith(".localhost") || hostname === "0.0.0.0" ||
  hostname === "::" || hostname === "::1" || /^127\./.test(hostname) ||
  /^::ffff:(?:127\.|7f[0-9a-f]{2}:)/.test(hostname) || hostname === "::ffff:0:0" || hostname === "::ffff:0.0.0.0";
if (loopback) {
  throw new Error("playwright.hosted.config.ts is for the live hosted server only; SG_E2E_BASE_URL must not be a loopback address.");
}

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Product specs selected for the hosted smoke (their tests are named below).
const files = [
  "test_agent_provider_status.spec.ts",
  "test_agent_surface_corrections.spec.ts",
  "test_chart_chunk_failure.spec.ts",
  "test_chat_receipt_recovery.spec.ts",
  "test_general_chat.spec.ts",
  "test_job_errors.spec.ts",
  "test_preset_graphs.spec.ts",
  "test_product_refresh.spec.ts",
  "test_refresh_faults.spec.ts",
  "test_reload.spec.ts",
  "test_result_discovery.spec.ts",
  "test_agent_flow.spec.ts",
  "test_agent_identity_luna3.spec.ts",
  "test_flagship_preset.spec.ts",
  "test_results_assistant_suggestions.spec.ts",
];

// Exact-title allowlist: every one of the 64 selected tests, grouped by file.
const titles = [
  // test_agent_provider_status.spec.ts
  "[simulated] paused with unavailable provider is truthful and makes no query POST",
  "[simulated] paused even when provider is available is truthful and makes no query POST",
  "[simulated] enabled provider unavailable is truthful and makes no query POST",
  "[simulated] active real-provider status is truthful and makes no query POST",
  "[simulated] active scripted status remains explicitly labelled is truthful and makes no query POST",
  // test_agent_surface_corrections.spec.ts
  "[simulated] same-page retry resubmits saved lost-submit identity",
  // test_chart_chunk_failure.spec.ts
  "[simulated] Plotly import failure preserves four persisted tables",
  // test_chat_receipt_recovery.spec.ts
  "[simulated] OR-01: a pending-only history is reconciled by identity and the paid reply appears exactly once",
  "[simulated] OR-01: older id-less session state refetches server history and never auto-submits",
  "[simulated] OR-01: history that already holds both rows is not duplicated by the retry",
  "[simulated] OR-01: a response lost before the conversation id arrived is recovered with the original request",
  "[simulated] OR-01: identical text in two different messages stays two messages",
  "[simulated] OR-01: reloading twice keeps one pending identity and no duplicates",
  "[simulated] OR-01: a failed session-storage write keeps the original key and still shows the reply once",
  "[simulated] OR-01: when browser storage cannot be written nothing is sent",
  "[simulated] OR-01: a conflicting server record is a visible protocol error and keeps the pending identity",
  "[simulated] OR-03: a definite terminal failure marks the turn and the conversation continues with a new key",
  "mergeChatMessages deduplicates by identity, orders by ordinal and rejects contradictions",
  // test_general_chat.spec.ts
  "[simulated] general chat stays disabled while paused or without a provider and tolerates missing budget fields",
  "[simulated] ordinary conversation sends only on submit, survives panel switching and reloads from history",
  "[simulated] unresolved reply is reported as pending and a new conversation releases the panel",
  "[simulated] failed chat submission keeps its idempotency key until explicit retry",
  // test_job_errors.spec.ts
  "[simulated] lost response after real acceptance retries the original job across reload",
  "[simulated] worker failure and cancellation outcomes retain cached evidence",
  "[simulated] expired session, network loss and storage failure recover explicitly",
  // test_preset_graphs.spec.ts
  "saved preset e90c4adbda3d53664a823f84 renders exact metric and reliability traces",
  "saved preset dd4c68fc6c73b128e23cfd97 renders exact metric and reliability traces",
  // test_product_refresh.spec.ts
  "[simulated] F01 overview explains the product and opens the independent workbench route",
  "F02 planned workspace routes remain informational and make no private requests",
  "F03 unknown app routes show the branded 404 with working recovery links",
  "F07 concept caption and chapter controls remain complete in the static illustration",
  "F08 reduced motion and coarse pointer retain static chapters without loading the scene",
  "F09 responsive overview and workbench reflow from 320px through 1440px and at 200% equivalent width",
  "F10 keyboard navigation and forced colors preserve named, operable route controls",
  "F13 public and workbench entry chunks stay separate from Plotly and optional scene modules",
  "F14 assistant stays paused while manual workbench controls stay available",
  // test_refresh_faults.spec.ts
  "[simulated] F04 delayed /demo module exposes a real loading state and mounts on release",
  "[simulated] F04 failed /demo module shows recovery and the static entry explains JavaScript",
  "[simulated] F07 unavailable WebGL keeps the caption, chapters, and static diagram usable",
  "[simulated] F07 context loss leaves a static fallback when a WebGL canvas is available",
  "[simulated] F07 sustained slow visible frames downgrade the optional scene",
  "[simulated] F12 a delayed scene import cannot attach a canvas after leaving the overview",
  "[simulated] F12 pause and chapter changes do not create duplicate scene canvases",
  "[simulated] F08 and F12 settled, hidden, and paused scene states stop scheduling frames and retain bounded listeners",
  // test_reload.spec.ts
  "persisted cache survives reload with private credentials and keyboard/mobile access",
  "[simulated] submission session expiry reconnects and allows a new authorized submission",
  "[simulated] unavailable records remain explicit and corrupt storage has a usable empty state",
  // test_result_discovery.spec.ts
  "visible saved result opens its charts and returns focus to the result heading",
  // test_agent_flow.spec.ts
  "[simulated] paused assistant displays inference notice while manual workbench controls remain functional",
  "[simulated] session expiration on agent submit triggers explicit error handling",
  // test_agent_identity_luna3.spec.ts
  "[simulated] error envelope provider 401 does not expire browser capability",
  "[simulated] error envelope business 403 does not expire browser capability",
  "[simulated] terminal API response renders structured and legacy tool errors safely",
  "[simulated] capability rejection Clear does not replace the expired authority",
  // test_flagship_preset.spec.ts
  "real bank-outage-50 preset publishes a readable result",
  "real bank-baseline preset publishes a readable result",
  // test_results_assistant_suggestions.spec.ts
  "[simulated] no saved result open shows the hint and the command-contract placeholder, with no suggestion buttons",
  "[simulated] suggestion buttons are disabled while the assistant is paused",
  "[simulated] a stress result lacking the budget-50 condition offers Summarize only",
  "[simulated] a COMPLETED guidance response shows a neutral Not answered notice and no success styling",
  "[simulated] a FAILED guidance response keeps the failure summary and labels the notice as advice",
  "[simulated] a CANCELLED guidance response keeps the cancellation summary and labels the notice as advice",
  "[simulated] a COMPLETED EXPERIMENT_NOT_PUBLISHED guidance response shows its message as a neutral notice",
  "[simulated] a COMPLETED response without guidance renders unchanged",
];

// Playwright matches grep against the space-joined title path (project, file, describes, title),
// so anchor each title at a whitespace boundary and at the end.
const exactTitles = new RegExp(`(?:^|\\s)(?:${titles.map(escapeRegExp).join("|")})$`);

const globs = (names: string[]) => names.map((name) => `**/${name}`);

export default defineConfig({
  ...base,
  globalSetup: "./scripts/hosted-budget-tripwire.ts",
  testMatch: globs(files),
  grep: exactTitles,
  // Never start a local server or the isolated-database harness against the live host.
  webServer: undefined,
  metadata: { ...base.metadata, hostedSmoke: true, liveProviderCalls: false },
  projects: [{ name: "hosted-smoke", testMatch: globs(files), grep: exactTitles }],
});
