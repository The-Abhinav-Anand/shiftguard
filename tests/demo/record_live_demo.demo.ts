// Records docs/submission/media/shiftguard-demo-live.webm against the LIVE hosted app.
// Unlike record_demo.demo.ts, the assistant shots are real NVIDIA Nemotron replies on Nebius
// Token Factory, spent from the shared daily allowance (expected: 2 Results calls, 1 chat call).
// Run only with SG_E2E_BASE_URL=https://shiftguard.duckdns.org and SG_DEMO_LIVE=1, after the
// live check, with the allowance shown before and after recorded in the evidence folder.
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { test, expect, openAnalysisOptions, type Page } from "../../frontend/e2e/fixtures";

const MEDIA = path.resolve(__dirname, "../../docs/submission/media");
const EXPERIMENT = process.env.SG_DEMO_EXPERIMENT_ID ?? "09b7b8c05c08cde62645dea8";
const COMPARE = `Compare experiment ${EXPERIMENT} calibrators predictor logistic_regression scenario history_block_0_50 budget 50`;
const CHAT_QUESTION = "In two sentences: why can a model rank cases well but still give badly calibrated probabilities?";
const LIVE = "Live: NVIDIA Nemotron on Nebius Token Factory";

async function overlay(page: Page, caption: string, badge?: string) {
  await page.evaluate(([text, label]) => {
    const make = (id: string, style: Partial<CSSStyleDeclaration>) => {
      let element = document.getElementById(id);
      if (!element) {
        element = document.createElement("div");
        element.id = id;
        Object.assign(element.style, {
          position: "fixed", zIndex: "2147483647", pointerEvents: "none",
          fontFamily: "system-ui, 'Segoe UI', sans-serif", ...style,
        });
        document.body.appendChild(element);
      }
      return element;
    };
    const box = make("sg-demo-caption", {
      left: "50%", bottom: "24px", transform: "translateX(-50%)", width: "min(1080px, 92vw)",
      padding: "14px 22px", background: "rgba(16, 24, 22, 0.92)", color: "#ffffff",
      font: "600 21px/1.4 system-ui, 'Segoe UI', sans-serif", borderRadius: "10px",
      textAlign: "center", boxShadow: "0 6px 24px rgba(0,0,0,0.25)",
    });
    box.textContent = text;
    box.style.display = text ? "block" : "none";
    const tag = make("sg-demo-badge", {
      right: "18px", top: "84px", padding: "8px 14px", background: "#1f6f43", color: "#ffffff",
      font: "700 15px/1.3 system-ui, 'Segoe UI', sans-serif", borderRadius: "8px",
    });
    tag.textContent = label ?? "";
    tag.style.display = label ? "block" : "none";
  }, [caption, badge ?? ""] as const);
}

// SG_DEMO_DRY=1 walks every screen and selector but sends no model request and writes no media.
const DRY = process.env.SG_DEMO_DRY === "1";

test("record the live submission demo", async ({ page }) => {
  test.skip(process.env.SG_DEMO_LIVE !== "1" && !DRY, "spends live model calls; set SG_DEMO_LIVE=1 deliberately");
  test.skip(process.env.SG_E2E_BASE_URL !== "https://shiftguard.duckdns.org", "records the hosted judge app only");
  test.setTimeout(15 * 60 * 1000);
  mkdirSync(MEDIA, { recursive: true });
  const started = Date.now();
  const marks: Array<{ at_seconds: number; shot: string }> = [];
  const mark = (shot: string) => marks.push({ at_seconds: Math.round((Date.now() - started) / 100) / 10, shot });
  const say = async (caption: string, ms: number, badge?: string) => {
    await overlay(page, caption, badge);
    await page.waitForTimeout(DRY ? 100 : ms);
  };

  // 1. The problem.
  mark("about");
  await page.goto("/about");
  await expect(page.getByRole("heading", { name: /When inputs/ })).toBeVisible();
  await say("A deployed model keeps returning probabilities when a data feed drops fields. Are they still right?", 7000);
  await say("SHIFTGUARD rehearses input outages on a tabular model and measures what happens to calibration.", 6500);

  // 2. Run an approved analysis on the live server.
  mark("workbench");
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await say("This is the live app at shiftguard.duckdns.org, on the public UCI Bank Marketing data: 41,188 rows, hash-verified.", 6500);
  await page.getByRole("combobox", { name: "Approved preset", exact: true }).selectOption("bank-baseline");
  await say("Each run is a durable job on a separate worker. Here: the Bank baseline.", 3500);
  await page.getByRole("button", { name: "Submit run" }).click();
  await expect(page.locator(".job-card").first().locator(".job-status")).toHaveText("completed", { timeout: 180_000 });
  await expect(page.getByRole("heading", { name: "Published preset result" })).toBeVisible();
  await page.getByRole("heading", { name: "Published preset result" }).scrollIntoViewIfNeeded();
  await say("The result is published once, hash-verified, and every chart and table is read from that stored record.", 6500);

  // 3. The saved 400-condition stress result.
  mark("stress");
  await page.goto("/demo");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  const history = page.locator("details.job-history");
  if (await history.count() && !(await history.evaluate((element) => (element as HTMLDetailsElement).open))) {
    await history.locator(":scope > summary").click();
  }
  await page.locator(".published-list button").filter({ hasText: EXPERIMENT.slice(0, 13) }).click();
  // The 400-condition record is large; give the live server time to send it.
  await expect(page.getByRole("heading", { name: "Experiment result", exact: true })).toBeVisible({ timeout: 60_000 });
  await openAnalysisOptions(page);
  await page.getByRole("combobox", { name: "Budget · labels", exact: true }).selectOption("50");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("target_temperature");
  await page.getByRole("heading", { name: "Experiment result", exact: true }).scrollIntoViewIfNeeded();
  await say("The saved stress suite: no loss plus 4 outage patterns, × 8 calibration conditions × 2 predictors × 5 label budgets = 400 conditions.", 7500);
  const article = (id: string) => page.locator(`article[aria-labelledby="${id}-title"]`);
  await article("budget-curve").scrollIntoViewIfNeeded();
  await say("The budget curve: how a recalibration map behaves as fresh labelled outcomes arrive, from 0 to 200.", 6500);
  await article("reliability").scrollIntoViewIfNeeded();
  await say("Reliability: predicted probability against the observed outcome rate, bin by bin.", 6000);
  await article("decision-loss").scrollIntoViewIfNeeded();
  await say("Decision loss at a stated false-positive / false-negative cost pair: is the score still safe to act on?", 6000);
  await article("pattern-rate").scrollIntoViewIfNeeded();
  await say("Pattern versus rate: losing a whole block of history fields compared with random loss at the same rate.", 6000);
  await say("Single-seed finding at 50 labels: against a zero-label source comparator, three target maps lower mean Brier score, yet each has higher log loss in all 8 shifted cells.", 8500);

  // 4. Results assistant, live.
  mark("assistant");
  await page.getByRole("button", { name: "Results assistant", exact: true }).click();
  const agentPanel = page.locator(".agent-panel");
  await agentPanel.scrollIntoViewIfNeeded();
  const group = page.getByRole("group", { name: "Ask about this result", exact: true });
  await say("The Results assistant runs live on NVIDIA Nemotron via Nebius Token Factory. Saved results are read through exact commands.", 6500, LIVE);
  await group.getByRole("button", { name: /^Compare experiment/ }).click();
  await expect(page.locator("#agent-prompt")).toHaveValue(COMPARE);
  await say("Compare all 8 calibration conditions: logistic regression, history-block outage, 50 new labels. The button only fills in the command.", 5000, LIVE);
  await expect(page.locator("#agent-submit-btn")).toBeEnabled();
  if (DRY) {
    await page.getByRole("button", { name: "General chat", exact: true }).click();
    await expect(page.locator("#general-chat-prompt")).toBeEditable();
    await expect(page.getByRole("button", { name: "Send message", exact: true })).toBeVisible();
    await page.close();
    return;
  }
  await page.locator("#agent-submit-btn").click();
  await say("Nemotron may only call approved tools: inspect the dataset, run an approved preset, read saved results.", 3000, LIVE);
  await expect(agentPanel.locator(".agent-final-response")).toBeVisible({ timeout: 4 * 60 * 1000 });
  await expect(page.locator(".agent-active-card .status-pill")).toHaveText(/completed/i);
  await page.locator(".agent-active-card").evaluate((element) => element.scrollIntoView({ block: "start" }));
  await say("A live answer. Every number in it is rendered by Python from the stored record, never generated by the model.", 7500, LIVE);
  await agentPanel.locator(".claims-table").evaluate((element) => element.scrollIntoView({ block: "center" }));
  await say("In this one cell, all four target maps score a worse Brier than raw at 50 labels; the source-only maps stay at or just below raw.", 8000, LIVE);
  const trace = agentPanel.locator(".trace-item").first();
  if (await trace.count()) {
    await trace.evaluate((element) => element.scrollIntoView({ block: "center" }));
    await say("The tool trace shows exactly which approved tools the model called.", 5000, LIVE);
  }

  // 5. General chat, live, and the spending cap.
  mark("general-chat");
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  await page.getByRole("heading", { name: "General chat", exact: true }).scrollIntoViewIfNeeded();
  await say("General chat is a separate, tool-free Nemotron conversation, labelled unverified.", 4500, LIVE);
  await page.locator("#general-chat-prompt").fill(CHAT_QUESTION);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const reply = page.locator(".general-chat__message--assistant").last();
  await expect(reply.locator(".general-chat__content")).not.toBeEmpty({ timeout: 2 * 60 * 1000 });
  await reply.scrollIntoViewIfNeeded();
  await say("A real reply, marked as AI text and not verified experiment evidence.", 7000, LIVE);
  await page.locator(".general-chat__budget").scrollIntoViewIfNeeded();
  await say("Both assistants share a hard daily cap: 50 calls and 100,000 tokens, reserved before each call, zero retries.", 7000, LIVE);

  // 6. Close.
  mark("close");
  await page.goto("/about");
  await expect(page.getByRole("heading", { name: /When inputs/ })).toBeVisible();
  await say("Limits: Bank data only, single-seed development evidence, no uploads. Source: github.com/The-Abhinav-Anand/shiftguard", 7500);
  mark("end");

  writeFileSync(path.join(MEDIA, "demo-live-timeline.json"), `${JSON.stringify({ marks, total_seconds: (Date.now() - started) / 1000 }, null, 2)}\n`);
  const video = page.video();
  await page.close();
  if (video) await video.saveAs(path.join(MEDIA, "shiftguard-demo-live.webm"));
});
