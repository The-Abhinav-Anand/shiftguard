import { test, expect } from "../../frontend/e2e/fixtures";

test("[simulated] paused assistant displays inference notice while manual workbench controls remain functional", async ({ page }) => {
  await page.route("**/api/v1/agent/status", async (route) => {
    return route.fulfill({
      status: 200,
      json: {
        enabled: false,
        available: false,
        model: "nvidia/Nemotron-3_5-Lightning",
        max_turns: 6,
        max_calls: 8,
        active_requests_count: 0,
      },
    });
  });

  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();

  // Agent panel shows offline banner
  const agentPanel = page.locator(".agent-panel");
  await expect(agentPanel).toBeVisible();
  await expect(agentPanel.locator(".agent-status-badge")).toHaveText("Assistant paused");
  await expect(agentPanel.locator(".agent-notice.notice-offline")).toBeVisible();
  await expect(agentPanel.locator(".agent-notice.notice-offline")).toContainText("Paid inference is paused.");

  // Workbench manual controls remain completely enabled and functional
  await expect(page.getByRole("combobox", { name: "Approved preset", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Submit run" })).toBeEnabled();
});

test("[simulated] session expiration on agent submit triggers explicit error handling", async ({ page }) => {
  await page.route("**/api/v1/agent/status", async (route) => {
    return route.fulfill({
      status: 200,
      json: {
        enabled: true,
        available: true,
        model: "nvidia/Nemotron-3_5-Lightning",
        max_turns: 6,
        max_calls: 8,
        active_requests_count: 0,
      },
    });
  });

  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();

  // Intercept agent requests to simulate 401
  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 401,
        json: {
          error: {
            code: "SESSION_EXPIRED",
            message: "Authentication session has expired or capability token is invalid.",
          },
        },
      });
    }
    return route.continue();
  });

  const agentPanel = page.locator(".agent-panel");
  await agentPanel.locator("#agent-prompt").fill("Inspect dataset");
  await agentPanel.locator("button[type='submit']").click();

  // Error is surfaced clearly
  await expect(agentPanel.locator(".notice-error")).toBeVisible();
  await expect(agentPanel.locator(".notice-error")).toContainText("SESSION_EXPIRED");
});

test("[real agent] natural-language query triggers tool execution, real worker experiment run, auto-resume and grounded evidence display", async ({ page }) => {
  test.setTimeout(12 * 60 * 1000);
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();

  const agentPanel = page.locator(".agent-panel");
  await expect(agentPanel).toBeVisible();
  await expect(agentPanel.locator(".agent-status-badge")).toHaveText(/Nemotron-3_5-Lightning Active|Scripted Test Harness/);

  // Submit the explicitly approved outage preset command
  const promptInput = agentPanel.locator("#agent-prompt");
  await promptInput.fill("Run bank-outage-50");

  const submitPromise = page.waitForResponse(
    (response) => response.url().includes("/api/v1/agent/requests") && response.request().method() === "POST",
  );
  await agentPanel.locator("button[type='submit']").click();

  const submitResponse = await submitPromise;
  expect([200, 202]).toContain(submitResponse.status());
  const initialBody = await submitResponse.json();
  expect(initialBody.request_id).toBeTruthy();

  // Trace should be visible with tool execution
  await expect(agentPanel.locator(".agent-trace-section")).toBeVisible();
  await expect(agentPanel.locator(".trace-item").first()).toBeVisible();

  // Either in waiting for job or progressing to completion via embedded worker
  // Wait for the final grounded evidence section to appear
  const finalResponse = agentPanel.locator(".agent-final-response");
  await expect(finalResponse).toBeVisible({ timeout: 10 * 60 * 1000 });

  // Verify grounded deterministic claims table and single-seed disclaimer
  await expect(finalResponse.locator(".claims-heading")).toContainText("Empirical Observations");
  await expect(finalResponse.locator(".agent-disclaimer")).toContainText("31001");
  await expect(finalResponse.locator(".claims-table")).toBeVisible();

  // Verify evidence reference link exists and can be clicked to load into workbench
  const evidenceBtn = agentPanel.locator(".evidence-button");
  await expect(evidenceBtn.first()).toBeVisible();
  const expId = await evidenceBtn.first().textContent();
  expect(expId).toBeTruthy();

  await evidenceBtn.first().click();
  // Clicking the evidence link loads the experiment into the main result view
  await expect(page.getByRole("heading", { name: /^(Published preset result|Experiment result)$/ })).toBeVisible({ timeout: 15_000 });
});
