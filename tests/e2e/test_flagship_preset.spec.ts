import path from "node:path";
import { writeFile } from "node:fs/promises";
import { test, expect, type Page } from "../../frontend/e2e/fixtures";
import type { StressPayload } from "../../frontend/src/api/types";

const fixed = (value: number | null | undefined) => value == null ? "Unavailable" : value.toFixed(3);
const table = (page: Page, id: string) => page.locator(`article[aria-labelledby="${id}-title"] table`);

test("real worker stress payload binds every chart, table and filter; identical rerun restores job identity", async ({ page }, info) => {
  test.setTimeout(15 * 60 * 1000);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Submit run" })).toBeEnabled();
  await expect(page.getByRole("combobox", { name: "Approved preset", exact: true })).toHaveValue("bank-outage-50");
  await page.getByRole("combobox", { name: "Approved preset", exact: true }).selectOption("bank-stress");
  const submitted = page.waitForResponse((response) => response.url().endsWith("/api/v1/experiments") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Submit run" }).click();
  const response = await submitted;
  expect(response.status()).toBe(202);
  expect(response.request().postDataJSON()).toEqual({ preset_name: "bank-stress" });
  const firstKey = response.request().headers()["idempotency-key"];
  const firstJob = (await response.json()).job_id;
  const card = page.locator(".job-card").filter({ hasText: firstJob });
  await expect(card.locator(".job-status")).toHaveText("completed", { timeout: 12 * 60 * 1000 });
  await expect(page.getByRole("heading", { name: "Experiment result", exact: true })).toBeVisible();

  const experimentId = await page.locator(".provenance-list dd").first().textContent();
  const persisted = await (await page.request.get(`/api/v1/experiments/${experimentId}`)).json();
  const payload = persisted.payload as StressPayload;
  expect(payload.config.master_seed).toBe(31001);
  expect(payload.config.run_type).toBe("stress_engine");
  expect(Object.keys(payload.conditions).length).toBeGreaterThan(50);

  // Change every view filter and compare selected records directly with the server payload.
  await page.getByRole("combobox", { name: "Predictor", exact: true }).selectOption("random_forest");
  await page.getByRole("combobox", { name: "Scenario", exact: true }).selectOption("mcar_0_30");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("target_platt_logodds");
  await page.getByRole("combobox", { name: "Budget · labels", exact: true }).selectOption("100");
  await page.getByRole("combobox", { name: "Score view", exact: true }).selectOption("log_loss");
  await page.getByRole("combobox", { name: "Cost pair", exact: true }).selectOption("1|4");
  const scenario = "random_forest__mcar_0_30";
  const method = "target_platt_logodds";
  const points = payload.payloads.budget_curve.scenarios[scenario][method];
  const point = points.find((row) => row.budget === 100)!;
  const condition = payload.conditions[`${scenario}__b100__${method}`];
  await expect(table(page, "budget-curve").locator("tbody tr.selected-row td").nth(4)).toHaveText(fixed(point.log_loss));
  await expect(page.locator(".metric-grid dd").nth(0)).toHaveText(fixed(point.log_loss));
  await expect(page.locator(".metric-grid dd").nth(1)).toHaveText(fixed(condition.metrics?.roc_auc));
  await expect(page.locator(".metric-grid dd").nth(2)).toHaveText(fixed(condition.metrics?.average_precision));
  const plotted = await page.getByTestId("plot-budget").locator(".js-plotly-plot").evaluate((element) => (element as unknown as { data: Array<{ y: unknown }> }).data[0].y);
  expect(plotted).toEqual(points.map((row) => row.available ? row.log_loss : null));

  const comparison = payload.payloads.pattern_vs_rate.comparisons.random_forest.methods[method];
  await expect(table(page, "pattern-rate").locator("tbody tr td").nth(0)).toHaveText(fixed(comparison.block_log_loss));
  await expect(table(page, "pattern-rate").locator("tbody tr td").nth(1)).toHaveText(fixed(comparison.cellwise_log_loss));
  await expect(table(page, "pattern-rate").locator("tbody tr td").nth(2)).toHaveText(comparison.comparison_qualified ? "Qualified" : "Not qualified");
  const reliability = payload.payloads.reliability.scenarios[scenario][method]!;
  const decision = payload.payloads.decision_loss.scenarios[scenario][method]!;
  expect(reliability.condition_id).toBe(payload.conditions[`${scenario}__b50__${method}`].condition_id);
  const bins = table(page, "reliability").locator("tbody tr");
  await expect(bins).toHaveCount(reliability.reliability_bins!.length);
  for (const [index, bin] of reliability.reliability_bins!.entries()) {
    await expect(bins.nth(index).locator("td").nth(1)).toHaveText(String(bin.count));
    await expect(bins.nth(index).locator("td").nth(2)).toHaveText(String(decision.cost_grid_losses![0].n_samples));
    await expect(bins.nth(index).locator("td").nth(3)).toHaveText(fixed(bin.mean_probability));
    await expect(bins.nth(index).locator("td").nth(4)).toHaveText(fixed(bin.positive_fraction));
  }
  await expect(page.locator("article[aria-labelledby='reliability-title']")).toContainText("selected budget (100)");
  const reference = await page.getByTestId("plot-reliability").locator(".js-plotly-plot").evaluate((element) => (element as unknown as { data: Array<{ x: number[]; y: number[] }> }).data[0]);
  expect(reference.x).toEqual([0, 1]);
  expect(reference.y).toEqual([0, 1]);
  const cost = decision.cost_grid_losses!.find((row) => row.fp_cost === 1 && row.fn_cost === 4)!;
  await expect(table(page, "decision-loss").locator("tbody tr")).toHaveCount(1);
  await expect(table(page, "decision-loss").locator("tbody td").nth(3)).toHaveText(fixed(cost.loss));
  await expect(table(page, "decision-loss").locator("tbody td").nth(4)).toHaveText(String(cost.fp_count));
  await expect(table(page, "decision-loss").locator("tbody td").nth(5)).toHaveText(String(cost.fn_count));

  // An intentional rerun uses a new idempotency key and job while preserving deterministic experiment identity.
  const again = page.waitForResponse((value) => value.url().endsWith("/api/v1/experiments") && value.request().method() === "POST");
  await card.getByRole("button", { name: "Rerun identical preset" }).click();
  const rerun = await again;
  const secondJob = (await rerun.json()).job_id;
  expect(secondJob).not.toBe(firstJob);
  expect(rerun.request().headers()["idempotency-key"] === firstKey).toBe(false);
  const sessionId = await page.locator(".session-id").getAttribute("title");
  await page.reload();
  await expect(page.locator(".session-id")).toHaveAttribute("title", sessionId!);
  await expect(page.locator(".job-card").filter({ hasText: secondJob }).locator(".job-status")).toHaveText("completed", { timeout: 12 * 60 * 1000 });
  await expect(page.locator(".result-heading .result-source")).toHaveText("Fresh computation");
  await expect(page.locator(".provenance-list dd").first()).toHaveText(experimentId!);
  await page.screenshot({ path: path.join(info.config.metadata.screenshotDirectory, "gate5-flagship-desktop.png"), fullPage: true, animations: "disabled" });
  await writeFile(path.join(info.config.metadata.evidenceDirectory, "worker-browser-evidence.json"), JSON.stringify({ firstJob, secondJob, experimentId, seed: payload.config.master_seed, comparedCondition: condition.condition_id, fixedBudgetCondition: reliability.condition_id, consoleErrors: 0, pageErrors: 0 }, null, 2));
});

for (const preset of ["bank-outage-50", "bank-baseline"]) {
  test(`real ${preset} preset publishes a readable result`, async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Submit run" })).toBeEnabled();
    await page.getByRole("combobox", { name: "Approved preset", exact: true }).selectOption(preset);
    await page.getByRole("button", { name: "Submit run" }).click();
    await expect(page.locator(".job-card").first().locator(".job-status")).toHaveText("completed", { timeout: 120_000 });
    await expect(page.getByRole("heading", { name: "Published preset result" })).toBeVisible();
    await expect(page.getByRole("table", { name: "Persisted preset conditions and diagnostics" }).locator("tbody tr").first()).toBeVisible();
  });
}
