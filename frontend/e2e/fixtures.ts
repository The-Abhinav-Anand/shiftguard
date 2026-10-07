import { test as base, expect } from "@playwright/test";

export const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    const pageErrors: string[] = [];
    const consoleErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      if (testInfo.title.includes("[simulated]") && message.text().startsWith("Failed to load resource:")) return;
      consoleErrors.push(message.text());
    });
    await use(page);
    expect(pageErrors, "Uncaught browser exceptions").toEqual([]);
    expect(consoleErrors, "Unexpected browser console errors").toEqual([]);
  },
});
export { expect };
export type { Page } from "@playwright/test";

export async function openAnalysisOptions(page: import("@playwright/test").Page) {
  const disclosure = page.locator("details.filter-disclosure");
  if (await disclosure.count() && !(await disclosure.evaluate((element) => (element as HTMLDetailsElement).open))) {
    await disclosure.locator(":scope > summary").click();
  }
  const scientific = page.locator("details.scientific-disclosure");
  if (await scientific.count() && !(await scientific.evaluate((element) => (element as HTMLDetailsElement).open))) {
    await scientific.locator(":scope > summary").click();
  }
}

export async function openSeededStress(page: import("@playwright/test").Page) {
  const response = await page.request.get("/api/v1/experiments?limit=20");
  expect(response.ok()).toBe(true);
  const { experiments } = await response.json();
  for (const record of experiments) {
    const result = await page.request.get(`/api/v1/experiments/${record.experiment_id}`);
    const experiment = await result.json();
    if (experiment.payload?.config?.run_type !== "stress_engine") continue;
    await page.goto("/demo");
    await expect(page.getByText("API connected", { exact: true })).toBeVisible();
    const history = page.locator("details.job-history");
    if (await history.count() && !(await history.evaluate((element) => (element as HTMLDetailsElement).open))) await history.locator(":scope > summary").click();
    await page.locator(".published-list button").filter({ hasText: record.experiment_id.slice(0, 13) }).click();
    await expect(page.getByRole("heading", { name: "Experiment result", exact: true })).toBeVisible();
    await openAnalysisOptions(page);
    return experiment;
  }
  throw new Error("No CLI-seeded stress record exists in the isolated E2E database");
}
