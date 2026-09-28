import { test, expect, openSeededStress } from "../../frontend/e2e/fixtures";

test("[simulated] lost response after real acceptance retries the original job across reload", async ({ page }) => {
  await openSeededStress(page);
  const keys: string[] = [];
  const ids: string[] = [];
  await page.route("**/api/v1/experiments", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    keys.push(route.request().headers()["idempotency-key"] ?? "");
    const realResponse = await route.fetch();
    expect(realResponse.ok()).toBe(true);
    ids.push((await realResponse.json()).job_id);
    if (ids.length === 1) return route.fulfill({ status: 503, json: { error: { code: "SIMULATED_RESPONSE_LOSS", message: "Acceptance response was lost." } } });
    return route.fulfill({ response: realResponse });
  });
  await page.getByRole("button", { name: "Submit run" }).click();
  await expect(page.getByRole("alert")).toContainText("SIMULATED_RESPONSE_LOSS");
  await expect(page.locator(".result-heading .result-source")).toHaveText("Browser-cached result");
  await page.reload();
  await expect(page.getByRole("button", { name: "Retry submit", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Retry submit", exact: true }).click();
  await expect(page.locator(".job-card")).toHaveCount(1);
  expect(keys.length).toBe(2);
  expect(keys[0].length > 0 && keys[0] === keys[1]).toBe(true);
  expect(ids[0]).toBe(ids[1]);
  await expect(page.locator(".job-card .job-status")).toHaveText("completed", { timeout: 120_000 });
});

test("[simulated] worker failure and cancellation outcomes retain cached evidence", async ({ page }) => {
  await openSeededStress(page);
  let status = "running";
  let cancelAttempts = 0;
  let submission = 0;
  await page.route("**/api/v1/experiments", (route) => route.request().method() === "POST" ? route.fulfill({ status: 202, json: { job_id: `simulated-job-${++submission}`, status: "queued" } }) : route.continue());
  await page.route("**/api/v1/jobs/simulated-job-*", (route) => route.fulfill({ json: { job_id: route.request().url().split("/").at(-1), status, error: status === "failed" ? { code: "SIMULATED_WORKER_FAILURE" } : null } }));
  await page.route("**/api/v1/jobs/simulated-job-*/cancel", (route) => {
    if (++cancelAttempts === 1) return route.fulfill({ status: 500, json: { error: { code: "SIMULATED_CANCEL_ERROR", message: "Cancellation could not be stored." } } });
    status = "cancelled";
    return route.fulfill({ status: 202, json: { status: "cancel_requested" } });
  });
  await page.getByRole("button", { name: "Submit run" }).click();
  const job = page.locator(".job-card").first();
  await expect(job.locator(".job-status")).toHaveText("running");
  await job.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("SIMULATED_CANCEL_ERROR");
  await job.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByText("Cancellation requested; worker will report its terminal state.", { exact: true })).toBeVisible();
  await expect(job.locator(".job-status")).toHaveText("cancelled");
  status = "failed";
  await page.getByRole("button", { name: "Submit run" }).click();
  await expect(page.locator(".job-card").first().locator(".job-status")).toHaveText("failed");
  await expect(page.locator(".job-card").first()).toContainText("SIMULATED_WORKER_FAILURE");
  await expect(page.getByRole("heading", { name: "Experiment result", exact: true })).toBeVisible();
  await expect(page.locator(".result-heading .result-source")).toHaveText("Browser-cached result");
});

test("[simulated] expired session, network loss and storage failure recover explicitly", async ({ page }) => {
  await openSeededStress(page);
  const oldSession = await page.locator(".session-id").getAttribute("title");
  await page.route("**/api/v1/agent/sessions/*", (route) => route.fulfill({ status: 401, json: { error: { code: "SESSION_EXPIRED", message: "Session expired." } } }));
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("SESSION_REPLACED");
  expect(await page.locator(".session-id").getAttribute("title")).not.toBe(oldSession);
  await expect(page.getByTestId("plot-budget")).toBeVisible();
  await page.unroute("**/api/v1/agent/sessions/*");
  await page.route("**/api/**", (route) => route.abort("internetdisconnected"));
  await page.reload();
  await expect(page.getByText("API unavailable", { exact: true })).toBeVisible();
  await expect(page.getByTestId("plot-budget")).toBeVisible();
  await page.unroute("**/api/**");
  await page.getByRole("button", { name: "Reconnect" }).click();
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.addInitScript(() => { Storage.prototype.setItem = () => { throw new DOMException("Storage disabled", "QuotaExceededError"); }; });
  await page.reload();
  // Loading another persisted record exercises a write without changing scientific state.
  await page.locator(".published-list button").first().click();
  await expect(page.getByText(/Browser storage is unavailable or full/)).toBeVisible();
});
