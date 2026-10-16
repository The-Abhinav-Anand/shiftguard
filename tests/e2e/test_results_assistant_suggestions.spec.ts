import { readFileSync } from "node:fs";
import path from "node:path";
import { test, expect, openSeededStress, type Page } from "../../frontend/e2e/fixtures";

const PRESET_ID = "e90c4adbda3d53664a823f84";
const snapshots = JSON.parse(readFileSync(path.join(__dirname, "fixtures/preset-results.json"), "utf8"));
const COMPARE_CONDITION_PREFIX = "logistic_regression__history_block_0_50__b50__";

const PLACEHOLDER =
  "Saved results are read through commands: use the buttons above or type Summarize experiment <id>. "
  + "Run commands: Run bank-baseline, Run bank-stress or Run bank-outage-50. Dataset facts: Inspect bank dataset.";
const NO_RESULT_HINT = "Open a saved result to ask about it, or type: Summarize experiment <id>";

function agentStatus(page: Page, enabled = true) {
  return page.route("**/api/v1/agent/status", (route) => route.fulfill({ status: 200, json: {
    enabled, available: true, general_chat_enabled: false, model: "nvidia/Nemotron-3_5-Lightning", max_turns: 6, max_calls: 8,
  } }));
}

async function mockOfflineList(page: Page) {
  await page.route("**/api/v1/experiments", (route) => route.request().method() === "GET"
    ? route.fulfill({ status: 200, json: { experiments: [] } })
    : route.continue());
}

async function seedBrowserResult(page: Page, id: string) {
  const record = { ...snapshots[id], source: "server-cache" };
  await page.addInitScript((value) => {
    localStorage.setItem("shiftguard.browser-workspace.v1", JSON.stringify({
      version: 1, session: null, jobs: [], pending_submission: null, cached_experiment: value,
    }));
  }, record);
}

function trackAssistantSends(page: Page) {
  const sends: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (request.method() === "POST" && (pathname === "/api/v1/agent/requests" || pathname === "/api/v1/chat/messages")) sends.push(pathname);
  });
  return sends;
}

test("[simulated] no saved result open shows the hint and the command-contract placeholder, with no suggestion buttons", async ({ page }) => {
  const sends = trackAssistantSends(page);
  await agentStatus(page);
  await mockOfflineList(page);
  await page.goto("/");
  await expect(page.locator(".agent-panel")).toBeVisible();
  await expect(page.getByText(NO_RESULT_HINT, { exact: true })).toBeVisible();
  await expect(page.getByRole("group", { name: "Ask about this result", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Summarize experiment/ })).toHaveCount(0);
  await expect(page.locator("#agent-prompt")).toHaveAttribute("placeholder", PLACEHOLDER);
  expect(sends).toEqual([]);
});

test("[simulated] an open saved preset result offers Summarize only; clicking inserts the exact command and never sends", async ({ page }) => {
  const sends = trackAssistantSends(page);
  await agentStatus(page);
  await mockOfflineList(page);
  await seedBrowserResult(page, PRESET_ID);
  await page.goto("/");
  const group = page.getByRole("group", { name: "Ask about this result", exact: true });
  await expect(group).toBeVisible();
  await expect(page.getByText(NO_RESULT_HINT, { exact: true })).toHaveCount(0);
  await expect(group.getByRole("button")).toHaveCount(1);
  await expect(group.getByRole("button", { name: /^Compare experiment/ })).toHaveCount(0);

  const summarize = group.getByRole("button", { name: `Summarize experiment ${PRESET_ID}`, exact: true });
  await expect(summarize).toHaveAttribute("type", "button");
  await expect(summarize).toBeEnabled();
  // Keyboard reachable: focus and activate with Enter.
  await summarize.focus();
  await expect(summarize).toBeFocused();
  await page.keyboard.press("Enter");
  const prompt = page.locator("#agent-prompt");
  await expect(prompt).toHaveValue(`Summarize experiment ${PRESET_ID}`);
  await expect(prompt).toBeFocused();
  await page.waitForTimeout(300);
  expect(sends).toEqual([]);
  await expect(page.locator("#agent-submit-btn")).toBeEnabled();
});

test("[simulated] suggestion buttons are disabled while the assistant is paused", async ({ page }) => {
  await agentStatus(page, false);
  await mockOfflineList(page);
  await seedBrowserResult(page, PRESET_ID);
  await page.goto("/");
  const group = page.getByRole("group", { name: "Ask about this result", exact: true });
  await expect(group).toBeVisible();
  await expect(group.getByRole("button", { name: `Summarize experiment ${PRESET_ID}`, exact: true })).toBeDisabled();
  await expect(page.locator("#agent-prompt")).toBeDisabled();
});

test("[simulated] an open stress result with the budget-50 condition also offers the exact Compare command", async ({ page }) => {
  const sends = trackAssistantSends(page);
  await agentStatus(page);
  await page.goto("/demo");
  const experiment = await openSeededStress(page);
  const id: string = experiment.experiment_id;
  expect(Object.keys(experiment.payload.conditions).some((key) => key.startsWith(COMPARE_CONDITION_PREFIX))).toBe(true);

  const group = page.getByRole("group", { name: "Ask about this result", exact: true });
  await expect(group.getByRole("button")).toHaveCount(2);
  const prompt = page.locator("#agent-prompt");
  await group.getByRole("button", { name: `Summarize experiment ${id}`, exact: true }).click();
  await expect(prompt).toHaveValue(`Summarize experiment ${id}`);
  await group.getByRole("button", { name: /^Compare experiment/ }).click();
  await expect(prompt).toHaveValue(
    `Compare experiment ${id} calibrators predictor logistic_regression scenario history_block_0_50 budget 50`,
  );
  await page.waitForTimeout(300);
  expect(sends).toEqual([]);
});

test("[simulated] a stress result lacking the budget-50 condition offers Summarize only", async ({ page }) => {
  await agentStatus(page);
  await page.route(/\/api\/v1\/experiments\/[0-9a-f]{24}$/, async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    if (body?.payload?.conditions) {
      for (const key of Object.keys(body.payload.conditions)) {
        if (key.startsWith(COMPARE_CONDITION_PREFIX)) delete body.payload.conditions[key];
      }
    }
    return route.fulfill({ response, json: body });
  });
  await page.goto("/demo");
  const experiment = await openSeededStress(page);
  const group = page.getByRole("group", { name: "Ask about this result", exact: true });
  await expect(group.getByRole("button")).toHaveCount(1);
  await expect(group.getByRole("button", { name: `Summarize experiment ${experiment.experiment_id}`, exact: true })).toBeVisible();
  await expect(group.getByRole("button", { name: /^Compare experiment/ })).toHaveCount(0);
});

// --- Guidance responses -----------------------------------------------------

const GUIDANCE_MESSAGE =
  "No saved experiment was selected. Ask: Summarize experiment <id>, or use the suggestion buttons.";

function agentRecord(sessionId: string, status: "COMPLETED" | "FAILED" | "CANCELLED", finalResponse: Record<string, unknown> | null, error: Record<string, string> | null = null) {
  const now = new Date().toISOString();
  return {
    request_id: `req_guidance_${status.toLowerCase()}`, session_id: sessionId, status,
    prompt: "explain the budget-50 comparison", turn_count: 1, call_count: 1, repair_count: 0,
    active_job_id: null, active_tool_call_id: null, resume_nonce: null,
    tool_trace: [], evidence_refs: [], final_response: finalResponse, error,
    created_at: now, updated_at: now,
  };
}

async function askAndAnswer(page: Page, build: (sessionId: string) => unknown) {
  await agentStatus(page);
  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({ status: 200, json: build(route.request().headers()["x-session-id"]) });
  });
  await page.goto("/");
  await expect(page.locator(".agent-panel")).toBeVisible();
  await page.locator("#agent-prompt").fill("explain the budget-50 comparison");
  await page.locator("#agent-submit-btn").click();
}

test("[simulated] a COMPLETED guidance response shows a neutral Not answered notice and no success styling", async ({ page }) => {
  await askAndAnswer(page, (sessionId) => agentRecord(sessionId, "COMPLETED", {
    title: "Experiment not selected", summary: "", claims: [], evidence_references: [], disclaimer: "",
    guidance: { code: "EXPERIMENT_NOT_SELECTED", message: GUIDANCE_MESSAGE },
  }));
  const notice = page.locator(".agent-guidance");
  await expect(notice).toHaveAttribute("role", "status");
  await expect(notice).toHaveText(`Not answered: ${GUIDANCE_MESSAGE}`);
  await expect(page.locator(".agent-active-card .status-pill.status-completed")).toHaveCount(0);
  await expect(page.locator(".agent-active-card .status-pill")).toHaveText("NOT ANSWERED");
  await expect(page.locator(".claims-table")).toHaveCount(0);
  await expect(page.locator(".agent-final-response")).toHaveCount(0);
});

test("[simulated] a FAILED guidance response keeps the failure summary and labels the notice as advice", async ({ page }) => {
  const summary = "One or more requested operations failed or were cancelled.";
  await askAndAnswer(page, (sessionId) => agentRecord(sessionId, "FAILED", {
    status: "FAILED", title: "Request failed", summary, claims: [], evidence_references: [], disclaimer: "",
    outcomes: [{ tool_name: "read_experiment_results", status: "error", code: "UNAUTHORIZED_EXPERIMENT_REFERENCE" }],
    guidance: { code: "EXPERIMENT_NOT_SELECTED", message: GUIDANCE_MESSAGE },
  }, { code: "FAILED", message: summary }));
  const notice = page.locator(".agent-guidance");
  await expect(notice).toHaveAttribute("role", "status");
  await expect(notice).toHaveText(`How to ask: ${GUIDANCE_MESSAGE}`);
  await expect(notice).not.toContainText("Not answered");
  await expect(notice).toHaveAttribute("data-guidance-code", "EXPERIMENT_NOT_SELECTED");
  await expect(page.locator(".agent-active-card .status-pill")).toHaveText("FAILED");
  await expect(page.locator(".agent-active-card .status-pill.status-failed")).toHaveCount(1);
  await expect(page.locator(".agent-panel .notice-error")).toContainText(summary);
  await expect(page.locator(".agent-final-response .final-title")).toHaveText("Request failed");
  await expect(page.locator(".agent-final-response .final-summary")).toHaveText(summary);
  await expect(page.locator(".claims-table")).toHaveCount(0);
});

test("[simulated] a CANCELLED guidance response keeps the cancellation summary and labels the notice as advice", async ({ page }) => {
  const summary = "The request was cancelled before it could be answered.";
  await askAndAnswer(page, (sessionId) => agentRecord(sessionId, "CANCELLED", {
    status: "CANCELLED", title: "Request cancelled", summary, claims: [], evidence_references: [], disclaimer: "",
    guidance: { code: "EXPERIMENT_NOT_SELECTED", message: GUIDANCE_MESSAGE },
  }));
  const notice = page.locator(".agent-guidance");
  await expect(notice).toHaveAttribute("role", "status");
  await expect(notice).toHaveText(`How to ask: ${GUIDANCE_MESSAGE}`);
  await expect(page.locator(".agent-active-card .status-pill")).toHaveText("CANCELLED");
  await expect(page.locator(".agent-final-response .final-summary")).toHaveText(summary);
  await expect(page.locator(".claims-table")).toHaveCount(0);
});

test("[simulated] a COMPLETED EXPERIMENT_NOT_PUBLISHED guidance response shows its message as a neutral notice", async ({ page }) => {
  const message = "Experiment 0123456789abcdef01234567 is not a published result on this server. Open a saved result and use its buttons.";
  await askAndAnswer(page, (sessionId) => agentRecord(sessionId, "COMPLETED", {
    status: "COMPLETED", title: "Experiment not published", summary: "", claims: [], evidence_references: [], disclaimer: "",
    guidance: { code: "EXPERIMENT_NOT_PUBLISHED", message },
  }));
  const notice = page.locator(".agent-guidance");
  await expect(notice).toHaveAttribute("role", "status");
  await expect(notice).toHaveAttribute("data-guidance-code", "EXPERIMENT_NOT_PUBLISHED");
  await expect(notice).toHaveText(`Not answered: ${message}`);
  await expect(page.locator(".agent-active-card .status-pill.status-completed")).toHaveCount(0);
  await expect(page.locator(".claims-table")).toHaveCount(0);
});

test("[simulated] a COMPLETED response without guidance renders unchanged", async ({ page }) => {
  await askAndAnswer(page, (sessionId) => agentRecord(sessionId, "COMPLETED", {
    title: "Grounded summary", summary: "Three conditions were scored.", evidence_references: [], disclaimer: "Single seed.",
    claims: [{ condition_id: "cond_a", description: "Brier fell", metric_name: "brier_score", value: 0.1, delta: -0.02, direction: "improved" }],
  }));
  await expect(page.locator(".agent-active-card .status-pill.status-completed")).toHaveText("COMPLETED");
  await expect(page.getByRole("heading", { name: "Grounded summary", exact: true })).toBeVisible();
  await expect(page.locator(".claims-table tbody tr")).toHaveCount(1);
  await expect(page.locator(".agent-guidance")).toHaveCount(0);
});
