import path from "node:path";
import { test, expect, openSeededStress } from "../../frontend/e2e/fixtures";
import type { StressPayload } from "../../frontend/src/api/types";

test("persisted cache survives reload with private credentials and keyboard/mobile access", async ({ page }, info) => {
  const experiment = await openSeededStress(page);
  const session = await page.locator(".session-id").getAttribute("title");
  await page.reload();
  await expect(page.locator(".result-heading .result-source")).toHaveText("Browser-cached result");
  await expect(page.locator(".session-id")).toHaveAttribute("title", session!);
  await page.getByLabel("Score view").focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Score view")).toHaveValue("log_loss");
  await expect(page.getByText("Log loss · 50 labels", { exact: true })).toBeVisible();

  const payload = experiment.payload as StressPayload;
  const conditionKey = "logistic_regression__mcar_0_30__b50__source_fraction_binned_temperature";
  const condition = payload.conditions[conditionKey];
  expect(condition.condition_id).toBe("a15856cfceebf15e4520aa08");
  const diagnostics = condition.sparse_bin_diagnostics!;
  expect(diagnostics).toMatchObject({
    affected_fallback_rows: 9,
    resolution_counts: {
      fitted_bin_temperature: 8229,
      source_remasked_temperature: 9,
      raw: 0,
      source_temperature: 0,
    },
    bin_eval_counts: { "8": 9 },
    bin_fallback_counts: { "8": 9 },
    bin_support: { "8": 8 },
    bin_resolution_counts: { "8": { source_remasked_temperature: 9 } },
    bin_resolved_maps: { "8": "source_remasked_temperature" },
  });
  expect(typeof diagnostics.sparse_prediction_failures).toBe("number");

  const selectSparseCondition = async () => {
    await page.getByRole("combobox", { name: "Predictor", exact: true }).selectOption("logistic_regression");
    await page.getByRole("combobox", { name: "Scenario", exact: true }).selectOption("mcar_0_30");
    await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("source_fraction_binned_temperature");
    await page.getByRole("combobox", { name: "Budget · labels", exact: true }).selectOption("50");
  };
  const expectSparseDetails = async () => {
    const details = page.getByLabel("Per-bin fallback diagnostics");
    await expect(details).toContainText("Affected fallback rows: 9");
    await expect(details).toContainText("Fitted bin temperature: 8,229");
    await expect(details).toContainText("Source-remasked temperature: 9");
    const binEight = details.locator("tbody tr").filter({ hasText: "Bin 8" });
    await expect(binEight).toContainText("9");
    await expect(binEight).toContainText("Source-remasked temperature: 9");
    await expect(page.locator(".fallback-block")).toContainText("Whole-condition fallback chain");
    await expect(page.locator(".fallback-block")).toContainText("None recorded");
  };
  const cachedDiagnostics = () => page.evaluate((key) => {
    const saved = JSON.parse(localStorage.getItem("shiftguard.browser-workspace.v1")!);
    return saved.cached_experiment.payload.conditions[key].sparse_bin_diagnostics;
  }, conditionKey);

  const expectedCachedDiagnostics = {
    affected_fallback_rows: diagnostics.affected_fallback_rows,
    resolution_counts: diagnostics.resolution_counts,
    bin_eval_counts: diagnostics.bin_eval_counts,
    bin_fallback_counts: diagnostics.bin_fallback_counts,
    bin_support: diagnostics.bin_support,
    bin_resolution_counts: diagnostics.bin_resolution_counts,
    bin_resolved_maps: diagnostics.bin_resolved_maps,
    sparse_prediction_failures: diagnostics.sparse_prediction_failures,
  };

  await selectSparseCondition();
  await expectSparseDetails();
  const cachedBeforeReload = await cachedDiagnostics();
  expect(cachedBeforeReload).toEqual(expectedCachedDiagnostics);
  expect("failed_attempts" in (cachedBeforeReload ?? {})).toBe(false);
  await page.reload();
  await expect(page.locator(".result-heading .result-source")).toHaveText("Browser-cached result");
  await selectSparseCondition();
  await expectSparseDetails();
  const cachedAfterReload = await cachedDiagnostics();
  expect(cachedAfterReload).toEqual(expectedCachedDiagnostics);
  expect("failed_attempts" in (cachedAfterReload ?? {})).toBe(false);

  const secretVisible = await page.evaluate(() => {
    const saved = JSON.parse(localStorage.getItem("shiftguard.browser-workspace.v1")!);
    return document.body.innerText.includes(saved.session.capability_token) || location.href.includes(saved.session.capability_token);
  });
  expect(secretVisible).toBe(false);
  await expect(page.locator(".js-plotly-plot")).toHaveCount(4);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Score view")).toBeVisible();
  try {
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  } catch (error) {
    const overflowing = await page.evaluate(() => Array.from(document.querySelectorAll("body *")).map((element) => ({ tag: element.tagName, class: element.getAttribute("class"), right: element.getBoundingClientRect().right, width: element.getBoundingClientRect().width })).filter((row) => row.right > innerWidth));
    await info.attach("overflow-elements", { body: JSON.stringify(overflowing), contentType: "application/json" });
    throw error;
  }
  await page.screenshot({ path: path.join(info.config.metadata.screenshotDirectory, "gate5-result-mobile.png"), fullPage: true, animations: "disabled" });
});

test("[simulated] submission session expiry reconnects and allows a new authorized submission", async ({ page }) => {
  await openSeededStress(page);
  const oldSession = await page.locator(".session-id").getAttribute("title");
  const idempotencyKeys: string[] = [];
  const submissionSessions: string[] = [];
  let submissions = 0;
  await page.route("**/api/v1/experiments", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submissions += 1;
    idempotencyKeys.push(route.request().headers()["idempotency-key"] ?? "");
    submissionSessions.push(route.request().headers()["x-session-id"] ?? "");
    if (submissions === 1) {
      return route.fulfill({ status: 401, json: { error: { code: "SESSION_EXPIRED", message: "Session expired." } } });
    }
    if (submissions === 2) return route.fulfill({ status: 202, json: { job_id: "reconnected-session-job", status: "queued" } });
    return route.fulfill({ status: 403, json: { error: { code: "BUSINESS_RULE_REJECTED", message: "This preset is unavailable." } } });
  });
  await page.route("**/api/v1/agent/sessions/*", (route) => route.request().method() === "GET"
    ? route.fulfill({ status: 401, json: { error: { code: "SESSION_EXPIRED", message: "Session expired." } } })
    : route.continue());
  await page.route("**/api/v1/jobs/reconnected-session-job", (route) => route.fulfill({ json: { job_id: "reconnected-session-job", status: "queued" } }));

  await page.getByRole("button", { name: "Submit run" }).click();
  await expect(page.getByRole("alert")).toContainText("SESSION_EXPIRED");
  await expect(page.getByRole("alert")).toContainText("pending submission will be discarded");
  await expect(page.getByRole("button", { name: "Reconnect" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry same submission" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Submit run" })).toBeDisabled();

  await page.getByRole("button", { name: "Reconnect" }).click();
  await expect(page.getByRole("alert")).toContainText("SESSION_REPLACED");
  await expect(page.locator(".session-id")).not.toHaveAttribute("title", oldSession!);
  await expect(page.locator(".result-heading .result-source")).toHaveText("Browser-cached result");
  await expect(page.getByRole("button", { name: "Submit run" })).toBeEnabled();
  await page.getByRole("button", { name: "Submit run" }).click();
  await expect(page.locator(".job-card")).toContainText("reconnected-session-job");
  expect(submissionSessions[1]).not.toBe(oldSession);
  expect(idempotencyKeys[1]).not.toBe(idempotencyKeys[0]);

  await page.getByRole("button", { name: "Submit run" }).click();
  await expect(page.getByRole("alert")).toContainText("BUSINESS_RULE_REJECTED");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reconnect" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry same submission" })).toBeVisible();
  expect(submissions).toBe(3);
});

test("[simulated] unavailable records remain explicit and corrupt storage has a usable empty state", async ({ page }) => {
  const experiment = await openSeededStress(page);
  const payload = experiment.payload;
  const key = "logistic_regression__history_block_0_50";
  const method = "target_temperature";
  // Shape-preserving failure fixture derived from the CLI's persisted result.
  payload.payloads.budget_curve.scenarios[key][method].forEach((point: { available: boolean; brier_score: number | null }) => { point.available = false; point.brier_score = null; });
  payload.payloads.reliability.scenarios[key][method] = null;
  payload.payloads.decision_loss.scenarios[key][method] = null;
  await page.route(`**/api/v1/experiments/${experiment.experiment_id}`, (route) => route.fulfill({ json: experiment }));
  await page.locator(".published-list button").filter({ hasText: experiment.experiment_id.slice(0, 13) }).click();
  await expect(page.getByText("No scored budget points are available for this selection.", { exact: true })).toBeVisible();
  await expect(page.getByText("Reliability bins are unavailable for this selection.", { exact: true })).toBeVisible();
  await expect(page.getByText("Decision-loss values are unavailable for this selection and cost setting.", { exact: true })).toBeVisible();
  await page.evaluate(() => localStorage.setItem("shiftguard.browser-workspace.v1", "not-json"));
  await page.reload();
  await expect(page.getByText(/Browser storage could not be read/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your persisted result will land here." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit run" })).toBeEnabled();
});
