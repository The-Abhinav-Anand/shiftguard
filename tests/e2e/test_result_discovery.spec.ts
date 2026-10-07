import { test, expect } from "../../frontend/e2e/fixtures";

test("visible saved result opens its charts and returns focus to the result heading", async ({ page }) => {
  const experimentSubmissions: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/v1/experiments") {
      experimentSubmissions.push(request.url());
    }
  });

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Saved results", exact: true })).toBeVisible();
  const savedRecord = process.env.SG_NORMAL_EXPERIMENT_ID
    ? page.locator(".saved-results-list li").filter({ hasText: process.env.SG_NORMAL_EXPERIMENT_ID })
    : page.locator(".saved-results-list li").first();
  await expect(savedRecord).toBeVisible();
  const experimentId = await savedRecord.locator("code").innerText();
  await expect(page.locator("details.job-history")).toHaveJSProperty("open", false);

  await savedRecord.getByRole("button").click();
  const resultHeading = page.getByRole("heading", { name: "Experiment result", exact: true });
  await expect(resultHeading).toBeFocused();
  await expect(page.locator("#results .chart-grid")).toBeVisible();
  await expect(savedRecord.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#results")).toContainText(experimentId.slice(0, 18));
  const headingTop = await resultHeading.evaluate((heading) => heading.getBoundingClientRect().top);
  expect(headingTop).toBeGreaterThanOrEqual(0);
  expect(headingTop).toBeLessThan(page.viewportSize()!.height);
  expect(experimentSubmissions).toEqual([]);
});
