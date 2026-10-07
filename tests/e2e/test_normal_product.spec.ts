import path from "node:path";
import { test, expect } from "../../frontend/e2e/fixtures";
import type { StressPayload } from "../../frontend/src/api/types";

const normalExperiment = process.env.SG_NORMAL_EXPERIMENT_ID;
test.skip(!normalExperiment, "Explicit normal-server experiment evidence is required.");

test("normal server root opens the manual engine, preserves saved evidence and renders actual 3D values", async ({ page }, info) => {
  const submissions: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/v1/experiments")) submissions.push(request.url());
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Submit run" })).toBeEnabled();
  await expect(page.getByRole("combobox", { name: "Approved preset", exact: true })).toHaveValue("bank-outage-50");
  await expect(page.getByRole("link", { name: "About SHIFTGUARD", exact: true }).first()).toHaveAttribute("href", "/about");
  expect(submissions).toEqual([]);
  const response = await page.request.get(`/api/v1/experiments/${normalExperiment}`);
  expect(response.ok()).toBe(true);
  const persisted = await response.json();
  const payload = persisted.payload as StressPayload;
  expect(Object.keys(payload.conditions)).toHaveLength(400);
  await page.getByRole("button", { name: "Open latest saved record" }).click();
  const history = page.locator("details.job-history");
  if (!(await history.evaluate((element) => (element as HTMLDetailsElement).open))) await history.locator(":scope > summary").click();
  await page.locator(".published-list button").filter({ hasText: normalExperiment!.slice(0, 13) }).click();
  await expect(page.getByRole("heading", { name: "Experiment result", exact: true })).toBeVisible();
  await page.locator("details.filter-disclosure > summary").click();
  await page.getByRole("combobox", { name: "Scenario", exact: true }).selectOption("mcar_0_30");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("source_fraction_binned_temperature");
  const points = payload.payloads.budget_curve.scenarios.logistic_regression__mcar_0_30.source_fraction_binned_temperature;
  await page.getByTestId("plot-budget").locator(".js-plotly-plot").waitFor();
  const plotted = await page.getByTestId("plot-budget").locator(".js-plotly-plot").evaluate((element) => (element as unknown as { data: Array<{ y: unknown }> }).data[0].y);
  expect(plotted).toEqual(points.map((point) => point.available ? point.brier_score : null));
  await page.screenshot({ path: path.join(info.config.metadata.screenshotDirectory, "normal-engine-workbench.png"), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "3D view", exact: true }).click();
  await expect(page.getByRole("button", { name: "Reset view", exact: true })).toBeVisible();
  const items = page.getByRole("list", { name: "Persisted budget values" }).locator("li");
  await expect(items).toHaveCount(points.length);
  for (const [index, point] of points.entries()) {
    await expect(items.nth(index)).toContainText(`Budget ${point.budget}`);
    await expect(items.nth(index)).toContainText(`Condition ID: ${point.condition_id}`);
    if (point.available && point.brier_score !== null) await expect(items.nth(index)).toContainText(`Brier score: ${String(point.brier_score)}`);
  }
  await page.getByRole("button", { name: "Rotate view right" }).click();
  await page.getByRole("button", { name: "Reset view", exact: true }).click();
  await expect(page.locator("article[aria-labelledby='budget-curve-title'] table tbody tr")).toHaveCount(points.length);
  await page.screenshot({ path: path.join(info.config.metadata.screenshotDirectory, "normal-persisted-3d.png"), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "2D chart", exact: true }).click();
  await expect(page.locator(".budget-volume canvas")).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".result-heading .result-source")).toHaveText("Browser-cached result");
  expect(submissions).toEqual([]);
});

test("normal server reduced motion keeps the exact data table when optional 3D is disabled", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("button", { name: "Open latest saved record" }).click();
  const history = page.locator("details.job-history");
  if (!(await history.evaluate((element) => (element as HTMLDetailsElement).open))) await history.locator(":scope > summary").click();
  await page.locator(".published-list button").filter({ hasText: normalExperiment!.slice(0, 13) }).click();
  await page.getByRole("button", { name: "3D view", exact: true }).click();
  await expect(page.locator(".budget-volume__fallback")).toContainText("current display preferences");
  await expect(page.locator(".budget-volume canvas")).toHaveCount(0);
  await expect(page.locator("article[aria-labelledby='budget-curve-title'] table tbody tr")).toHaveCount(5);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("all-method view retains each displayed method's adverse evidence outside folded diagnostics", async ({ page }) => {
  await page.goto("/");
  const history = page.locator("details.job-history");
  if (!(await history.evaluate((element) => (element as HTMLDetailsElement).open))) await history.locator(":scope > summary").click();
  await page.locator(".published-list button").filter({ hasText: normalExperiment!.slice(0, 13) }).click();
  await page.locator("details.filter-disclosure > summary").click();
  await page.getByRole("combobox", { name: "Scenario", exact: true }).selectOption("mcar_0_30");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("source_fraction_binned_temperature");
  const notice = page.locator(".notice--scientific");
  await expect(notice).toContainText("Affected fallback rows: 9");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("all");
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("Source fraction binned: Affected fallback rows: 9");
  await expect(page.locator("details.scientific-disclosure > summary")).toContainText("attention required");
  expect(await page.locator("details.scientific-disclosure").evaluate((element) => (element as HTMLDetailsElement).open)).toBe(false);
  await page.getByRole("combobox", { name: "Budget · labels", exact: true }).selectOption("0");
  await expect(notice).toContainText("Target temperature: Fallback:");
  await expect(notice).toContainText("Target Platt: Fallback:");
});
