import { test, expect } from "../../frontend/e2e/fixtures";
import type { AgentStatus } from "../../frontend/src/api/agent";

const cases = [
  { name: "paused with unavailable provider", enabled: false, available: false, provider_kind: "nebius", badge: "Assistant paused" },
  { name: "paused even when provider is available", enabled: false, available: true, provider_kind: "nebius", badge: "Assistant paused" },
  { name: "enabled provider unavailable", enabled: true, available: false, provider_kind: "nebius", badge: "Provider unavailable" },
  { name: "active real-provider status", enabled: true, available: true, provider_kind: "nebius", badge: "Nemotron-3_5-Lightning Active" },
  { name: "active scripted status remains explicitly labelled", enabled: true, available: true, provider_kind: "scripted", badge: "Scripted Test Harness" },
] as const;

for (const scenario of cases) {
  test(`[simulated] ${scenario.name} is truthful and makes no query POST`, async ({ page }) => {
    const queryPosts: string[] = [];
    // Prevent every query/continuation POST from reaching a provider, even on regression.
    await page.route("**/api/v1/agent/requests**", async (route) => {
      if (route.request().method() === "POST") {
        queryPosts.push(route.request().url());
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });
    const status: AgentStatus = {
      enabled: scenario.enabled,
      available: scenario.available,
      provider_kind: scenario.provider_kind,
      model: "nvidia/Nemotron-3_5-Lightning",
      max_turns: 6,
      max_calls: 8,
    };
    await page.route("**/api/v1/agent/status", (route) => route.fulfill({ status: 200, json: status }));

    await page.goto("/");
    await expect(page.getByText("API connected", { exact: true })).toBeVisible();
    const panel = page.locator(".agent-panel");
    const notice = panel.locator(".notice-offline");
    const prompt = panel.locator("#agent-prompt");
    const submit = panel.locator("#agent-submit-btn");
    await expect(panel.locator(".agent-status-badge")).toHaveText(scenario.badge);

    if (!scenario.enabled || !scenario.available) {
      await expect(prompt).toBeDisabled();
      await expect(submit).toBeDisabled();
      await expect(notice).toBeVisible();
      await expect(notice).not.toContainText(/credentials|unconfigured|key configured|key verified/i);
      if (!scenario.enabled) {
        await expect(notice.locator("div")).toHaveText("Assistant paused: Paid inference is paused. Manual presets and saved results are available.");
        await expect(notice).not.toContainText("Provider unavailable");
      } else {
        await expect(notice.locator("div")).toHaveText("Provider unavailable: The assistant is enabled, but its provider is unavailable. Paid inference cannot run. Manual presets and saved results are available.");
        await expect(notice).not.toContainText(/paused|disabled/i);
      }
    } else {
      await expect(notice).toBeHidden();
      await expect(prompt).toBeEnabled();
      await expect(submit).toBeDisabled();
      await prompt.fill("Inspect bank dataset");
      await expect(submit).toBeEnabled();
      if (scenario.provider_kind === "scripted") {
        await expect(panel.locator("#scripted-mode-badge")).toHaveText("[Scripted Test Mode]");
      } else {
        await expect(panel.locator("#scripted-mode-badge")).toHaveCount(0);
      }
    }

    await expect(page.getByRole("combobox", { name: "Approved preset", exact: true })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Submit run", exact: true })).toBeEnabled();
    expect(queryPosts, "Status display and editing must not dispatch inference").toEqual([]);
  });
}
