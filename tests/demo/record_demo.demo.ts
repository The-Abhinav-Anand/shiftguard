// Records docs/submission/media/shiftguard-demo.webm and the README screenshots.
// Runs against the scripted local harness: real Bank runs and saved records, and a scripted
// stand-in for the model. Every assistant shot carries a "recorded with test data" badge;
// nothing here is presented as a live Nemotron reply.
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { test, expect, openAnalysisOptions, openSeededStress, type Page } from "../../frontend/e2e/fixtures";

const MEDIA = path.resolve(__dirname, "../../docs/submission/media");

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
      right: "18px", top: "84px", padding: "8px 14px", background: "#5b2a86", color: "#ffffff",
      font: "700 15px/1.3 system-ui, 'Segoe UI', sans-serif", borderRadius: "8px",
    });
    tag.textContent = label ?? "";
    tag.style.display = label ? "block" : "none";
  }, [caption, badge ?? ""] as const);
}

const TEST_DATA = "Recorded with test data · scripted assistant, not a live Nemotron reply";

test("record the submission demo", async ({ page }) => {
  // The scripted harness only: against a hosted server this would send a real paid request
  // and still label it scripted.
  test.skip(Boolean(process.env.SG_E2E_BASE_URL), "scripted local harness only");
  test.setTimeout(15 * 60 * 1000);
  mkdirSync(MEDIA, { recursive: true });
  const started = Date.now();
  const marks: Array<{ at_seconds: number; shot: string }> = [];
  const mark = (shot: string) => marks.push({ at_seconds: Math.round((Date.now() - started) / 100) / 10, shot });
  const say = async (caption: string, ms: number, badge?: string) => {
    await overlay(page, caption, badge);
    await page.waitForTimeout(ms);
  };
  const shot = (name: string) => page.screenshot({ path: path.join(MEDIA, `${name}.png`), animations: "disabled" });

  // 1. The problem.
  mark("about");
  await page.goto("/about");
  await expect(page.getByRole("heading", { name: /When inputs/ })).toBeVisible();
  await say("", 300);
  await shot("01-about");
  await say("A deployed model keeps returning probabilities when a data feed drops fields. Are they still right?", 7000);
  await say("SHIFTGUARD rehearses input outages on a tabular model and measures what happens to calibration.", 7000);

  // 2. Run an approved analysis.
  mark("workbench");
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await say("The workbench runs approved analyses on the public UCI Bank Marketing data: 41,188 rows, hash-verified.", 6500);
  await shot("02-workbench");
  await page.getByRole("combobox", { name: "Approved preset", exact: true }).selectOption("bank-baseline");
  await say("Each run is a durable job on a separate worker. Here: the Bank baseline.", 3500);
  await page.getByRole("button", { name: "Submit run" }).click();
  await expect(page.locator(".job-card").first().locator(".job-status")).toHaveText("completed", { timeout: 120_000 });
  await expect(page.getByRole("heading", { name: "Published preset result" })).toBeVisible();
  await page.getByRole("heading", { name: "Published preset result" }).scrollIntoViewIfNeeded();
  await say("The result is published once, hash-verified, and every chart and table is read from that stored record.", 7000);
  await shot("03-baseline-result");

  // 3. The flagship stress result.
  mark("stress");
  await openSeededStress(page);
  await openAnalysisOptions(page);
  await page.getByRole("combobox", { name: "Budget · labels", exact: true }).selectOption("50");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("target_temperature");
  await page.getByRole("heading", { name: "Experiment result", exact: true }).scrollIntoViewIfNeeded();
  await say("The stress suite: no loss plus 4 outage patterns, × 8 calibration methods × 2 predictors × 5 label budgets = 400 conditions.", 7500);
  const article = (id: string) => page.locator(`article[aria-labelledby="${id}-title"]`);
  await article("budget-curve").scrollIntoViewIfNeeded();
  await say("The budget curve: how a recalibration map behaves as fresh labelled outcomes arrive, from 0 to 200.", 7000);
  await shot("04-budget-curve");
  await article("reliability").scrollIntoViewIfNeeded();
  await say("Reliability: predicted probability against the observed outcome rate, bin by bin.", 6500);
  await shot("05-reliability");
  await article("decision-loss").scrollIntoViewIfNeeded();
  await say("Decision loss at a stated false-positive / false-negative cost pair: is the score still safe to act on?", 6500);
  await article("pattern-rate").scrollIntoViewIfNeeded();
  await say("Pattern versus rate: losing a whole block of history fields compared with random loss at the same rate.", 6500);
  await shot("06-pattern-rate");
  await say("Single-seed finding at 50 labels: three target maps lower mean Brier score, yet every one raises log loss in all 8 shifted cells.", 8500);
  await say("The answer depends on the metric, and SHIFTGUARD shows the adverse results too.", 5000);

  // 4. Results assistant (scripted stand-in for Nemotron).
  mark("assistant");
  await page.getByRole("button", { name: "Results assistant", exact: true }).click();
  const agentPanel = page.locator(".agent-panel");
  await agentPanel.scrollIntoViewIfNeeded();
  await say("The Results assistant runs on NVIDIA Nemotron via Nebius Token Factory. Here a scripted stand-in drives it.", 6500, TEST_DATA);
  await agentPanel.locator("#agent-prompt").fill("Run bank-outage-50");
  await agentPanel.locator("button[type='submit']").click();
  await expect(agentPanel.locator(".trace-item").first()).toBeVisible({ timeout: 60_000 });
  await overlay(page, "It may only call approved tools: inspect the dataset, run an approved preset, read saved results.", TEST_DATA);
  await expect(agentPanel.locator(".agent-final-response")).toBeVisible({ timeout: 10 * 60 * 1000 });
  await agentPanel.locator(".agent-final-response").scrollIntoViewIfNeeded();
  await say("Every number in the answer is rendered by Python from the stored record, never generated by the model.", 7500, TEST_DATA);
  await shot("07-results-assistant");

  // 5. General chat and the spending cap.
  mark("general-chat");
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  await page.getByRole("heading", { name: "General chat", exact: true }).scrollIntoViewIfNeeded();
  await say("General chat is a separate, tool-free conversation, labelled unverified. No message is sent in this recording.", 6000, TEST_DATA);
  await say("Both assistants share a hard daily cap: 50 calls and 100,000 tokens, reserved before each call, zero retries.", 7000, TEST_DATA);
  await shot("08-general-chat");

  // 6. Close.
  mark("close");
  await page.goto("/about");
  await expect(page.getByRole("heading", { name: /When inputs/ })).toBeVisible();
  await say("Limits: Bank data only, single-seed development evidence, no uploads. Source: github.com/The-Abhinav-Anand/shiftguard", 7500);
  mark("end");

  writeFileSync(path.join(MEDIA, "demo-timeline.json"), `${JSON.stringify({ marks, total_seconds: (Date.now() - started) / 1000 }, null, 2)}\n`);
  const video = page.video();
  await page.close();
  if (video) await video.saveAs(path.join(MEDIA, "shiftguard-demo.webm"));
});
