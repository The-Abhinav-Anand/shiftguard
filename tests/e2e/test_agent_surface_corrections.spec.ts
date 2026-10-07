import { test, expect } from "../../frontend/e2e/fixtures";

test("[simulated] same-page retry resubmits saved lost-submit identity", async ({ page }) => {
  const attempts: Array<{ body: { prompt: string; idempotency_key: string }; owner: string }> = [];
  await page.route("**/api/v1/agent/status", (route) => route.fulfill({ json: {
    enabled: true, available: true, model: "nvidia/Nemotron-3_5-Lightning", max_turns: 6, max_calls: 8,
  } }));
  await page.route("**/api/v1/agent/requests", async (route) => {
    const req = route.request();
    if (req.method() !== "POST") return route.continue();
    attempts.push({ body: req.postDataJSON(), owner: req.headers()["x-session-id"] });
    if (attempts.length < 3) return route.abort("failed");
    return route.fulfill({ json: {
      request_id: "req_surface_retry", session_id: attempts[0].owner, status: "COMPLETED",
      prompt: attempts[0].body.prompt, turn_count: 0, call_count: 0, repair_count: 0,
      tool_trace: [], evidence_refs: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    } });
  });
  await page.goto("/");
  await expect(page.locator(".agent-panel")).toBeVisible();
  await page.locator("#agent-prompt").fill("same saved prompt");
  await page.locator("#agent-submit-btn").click();
  await expect(page.locator("#agent-retry-btn")).toBeVisible();
  await page.locator("#agent-retry-btn").click();
  await expect(page.locator("#agent-retry-btn")).toBeVisible();
  await page.locator("#agent-retry-btn").click();
  await expect.poll(() => attempts.length).toBe(3);
  expect(attempts[1]).toEqual(attempts[0]);
  expect(attempts[2]).toEqual(attempts[0]);
  await expect(page.locator("#agent-recovery-card")).toHaveCount(0);
});
