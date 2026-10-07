import { test, expect } from "../../frontend/node_modules/@playwright/test";
import { openSeededStress } from "../../frontend/e2e/fixtures";

test("[simulated] Plotly import failure preserves four persisted tables", async ({ page }) => {
  const pageErrors: string[] = [];
  const unexpectedConsole: string[] = [];
  let blocked = 0;
  page.on("pageerror", error => pageErrors.push(error.message));
  page.on("console", message => {
    if (message.type() !== "error") return;
    const value = message.text();
    if (value === "Failed to load resource: net::ERR_FAILED") return;
    if (value.includes("Failed to fetch dynamically imported module:") && /\/assets\/Plot-[\w-]+\.js/.test(value)) return;
    unexpectedConsole.push(value);
  });
  await page.route(/\/assets\/Plot-[\w-]+\.js(?:\?.*)?$/, async route => {
    blocked += 1;
    await route.abort("failed");
  });
  const experiment = await openSeededStress(page);
  await expect(page.getByText("Chart unavailable.", { exact: true })).toHaveCount(4);
  expect(blocked).toBeGreaterThan(0);
  for (const id of ["budget-curve", "pattern-rate", "reliability", "decision-loss"]) {
    await expect(page.locator(`article[aria-labelledby='${id}-title'] table`)).toBeVisible();
  }
  const payload = experiment.payload;
  const predictor = await page.getByRole("combobox", { name: "Predictor", exact: true }).inputValue();
  const scenario = await page.getByRole("combobox", { name: "Scenario", exact: true }).inputValue();
  const method = await page.getByRole("combobox", { name: "Method", exact: true }).inputValue();
  const points = payload.payloads.budget_curve.scenarios[`${predictor}__${scenario}`][method];
  const rows = page.locator("article[aria-labelledby='budget-curve-title'] tbody tr");
  await expect(rows).toHaveCount(points.length);
  for (const [index, point] of points.entries()) {
    await expect(rows.nth(index).locator("td").nth(1)).toHaveText(String(point.budget));
    await expect(rows.nth(index).locator("td").last()).toHaveText(point.brier_score == null ? "Unavailable" : point.brier_score.toFixed(3));
  }
  expect(pageErrors).toEqual([]);
  expect(unexpectedConsole).toEqual([]);
});
