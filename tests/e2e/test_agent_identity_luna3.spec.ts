import { spawnSync } from "node:child_process";
import { test, expect, type Page } from "../../frontend/e2e/fixtures";

type SavedIntent = {
  ownerSessionId: string;
  prompt: string;
  idempotencyKey: string;
  requestId?: string;
  activeJobId?: string;
  resumeNonce?: string;
  phase: string;
  retryAction?: string;
};

type E2EMetadata = {
  hosted?: boolean;
  isolatedDatabase?: string;
  pythonPath?: string;
};

async function openAgent(page: Page) {
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await expect(page.locator(".agent-panel")).toBeVisible();
}

async function savedIntent(page: Page, sessionId: string): Promise<SavedIntent | null> {
  return page.evaluate((id) => {
    const raw = localStorage.getItem(`shiftguard_agent_intent_${id}`);
    return raw ? JSON.parse(raw) as SavedIntent : null;
  }, sessionId);
}

function expireLocalTestSession(metadata: E2EMetadata, sessionId: string) {
  if (metadata.hosted || !metadata.isolatedDatabase || !metadata.pythonPath) {
    throw new Error("This identity regression requires the owned local SQLite browser database.");
  }
  const code = "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); cur=db.execute('UPDATE agent_sessions SET status=? WHERE id=?', ('expired',sys.argv[2])); db.commit(); changed=cur.rowcount; db.close(); sys.exit(0 if changed == 1 else 3)";
  return spawnSync(metadata.pythonPath, ["-c", code, metadata.isolatedDatabase, sessionId], {
    encoding: "utf8",
    windowsHide: true,
  });
}

async function armWorkerScenario(page: Page, outcome: "pause_next" | "fail_next"): Promise<string> {
  const origin = new URL(page.url()).origin;
  const sessionId = await page.locator(".session-id").getAttribute("title");
  expect(sessionId, "An agent session must exist before arming a worker scenario").toBeTruthy();
  if (!sessionId || sessionId === "Session is being created") {
    throw new Error("Cannot arm a worker scenario before the server-issued agent session is ready.");
  }

  const response = await page.request.post(`${origin}/__test__/worker/scenarios`, {
    data: { outcome, session_id: sessionId },
  });
  const responseText = await response.text();
  let body: unknown;
  try {
    body = JSON.parse(responseText);
  } catch {
    body = responseText;
  }
  const diagnostic = `HTTP ${response.status()}: ${responseText || "<empty response body>"}`;
  expect(response.ok(), `Unable to arm ${outcome} worker scenario (${diagnostic})`).toBe(true);
  expect(body, `Invalid ${outcome} worker scenario response (${diagnostic})`).toMatchObject({
    scenario_id: expect.any(String),
  });
  const scenarioId = (body as { scenario_id: string }).scenario_id;
  expect(scenarioId, `Worker scenario response omitted scenario_id (${diagnostic})`).toBeTruthy();
  return scenarioId;
}

async function workerScenarioState(page: Page, scenarioId: string): Promise<string> {
  const origin = new URL(page.url()).origin;
  const response = await page.request.get(`${origin}/__test__/worker/scenarios/${encodeURIComponent(scenarioId)}`);
  if (!response.ok()) return `http_${response.status()}`;
  const body = await response.json() as { state: string };
  return body.state;
}

async function releaseWorkerScenario(page: Page, scenarioId: string) {
  const origin = new URL(page.url()).origin;
  const response = await page.request.post(`${origin}/__test__/worker/scenarios/${encodeURIComponent(scenarioId)}/release`);
  expect(response.ok()).toBe(true);
}

test("[simulated] transport loss after real acceptance reloads the original intent and retries the same API identity", async ({ page }) => {
  const attempts: Array<{ key: string; prompt: string; ownerSessionId: string; requestId: string; jobId: string | null; status: number }> = [];
  let dropFirstResponse = true;
  let releaseFirstAbort: (() => void) | undefined;
  const abortGate = new Promise<void>((resolve) => { releaseFirstAbort = resolve; });

  await page.addInitScript(() => {
    type PrePostSnapshot = { ownerSessionId: string; intent: unknown };
    const observedWindow = window as Window & { __shiftguardAgentPrePost?: PrePostSnapshot };
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const inputUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const requestUrl = new URL(inputUrl, window.location.href);
      const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
      if (requestUrl.pathname === "/api/v1/agent/requests" && method === "POST") {
        const headers = new Headers(input instanceof Request ? input.headers : undefined);
        new Headers(init?.headers).forEach((value, name) => headers.set(name, value));
        const ownerSessionId = headers.get("x-session-id");
        if (ownerSessionId) {
          const raw = window.localStorage.getItem(`shiftguard_agent_intent_${ownerSessionId}`);
          observedWindow.__shiftguardAgentPrePost = {
            ownerSessionId,
            intent: raw ? JSON.parse(raw) as SavedIntent : null,
          };
        }
      }
      return originalFetch(input, init);
    };
  });

  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const requestBody = route.request().postDataJSON() as { prompt: string; idempotency_key: string };
    const ownerSessionId = route.request().headers()["x-session-id"];
    const response = await route.fetch();
    const accepted = await response.json() as { request_id: string; active_job_id: string | null };
    const attempt = {
      key: requestBody.idempotency_key,
      prompt: requestBody.prompt,
      ownerSessionId,
      requestId: accepted.request_id,
      jobId: accepted.active_job_id,
      status: response.status(),
    };
    attempts.push(attempt);
    if (dropFirstResponse) {
      dropFirstResponse = false;
      await abortGate;
      return route.abort("failed");
    }
    return route.fulfill({ response });
  });

  await openAgent(page);
  const sessionId = await page.locator(".session-id").getAttribute("title");
  expect(sessionId).toBeTruthy();
  await page.locator("#agent-prompt").fill("Run bank-outage-50");
  await page.locator("#agent-submit-btn").click();

  // Hold the browser response until route.fetch has observed a successful real API acceptance.
  await expect.poll(() => attempts.length, { timeout: 15_000 }).toBe(1);
  try {
    const prePost = await page.evaluate(() => (
      window as Window & { __shiftguardAgentPrePost?: { ownerSessionId: string; intent: SavedIntent | null } }
    ).__shiftguardAgentPrePost ?? null);
    expect(prePost).toMatchObject({
      ownerSessionId: sessionId,
      intent: {
        ownerSessionId: sessionId,
        prompt: attempts[0].prompt,
        idempotencyKey: attempts[0].key,
        phase: "pending_acceptance",
      },
    });
    expect(attempts[0].prompt).toBe("Run bank-outage-50");
    expect(attempts[0].ownerSessionId).toBe(sessionId);
    expect([200, 202]).toContain(attempts[0].status);
    expect(attempts[0].requestId).toBeTruthy();
    expect(attempts[0].jobId).toBeTruthy();
  } finally {
    releaseFirstAbort?.();
  }

  await expect(page.locator("#agent-recovery-card")).toBeVisible();
  await expect(page.locator("#agent-retry-btn")).toBeVisible();
  expect(attempts).toHaveLength(1);

  await page.reload();
  await expect(page.locator("#agent-recovery-card")).toBeVisible();
  await expect(page.locator("#agent-retry-btn")).toBeVisible();
  await expect(page.locator("#agent-recovery-card")).toContainText("Run bank-outage-50");
  await expect(page.locator("#agent-recovery-card")).toContainText(attempts[0].key);
  const saved = await savedIntent(page, sessionId!);
  expect(saved?.ownerSessionId).toBe(sessionId);
  expect(saved?.idempotencyKey).toBe(attempts[0].key);
  expect(saved?.requestId).toBeUndefined();
  expect(attempts[0].ownerSessionId).toBe(sessionId);

  await page.locator("#agent-retry-btn").click();
  await expect.poll(() => attempts.length).toBe(2);
  expect(attempts[1].key).toBe(attempts[0].key);
  expect(attempts[1].prompt).toBe(attempts[0].prompt);
  expect(attempts[1].ownerSessionId).toBe(attempts[0].ownerSessionId);
  expect(attempts[1].requestId).toBe(attempts[0].requestId);
  expect(attempts[1].jobId).toBe(attempts[0].jobId);
});

test("actual WAITING request is rehydrated on reload with its job and server continuation identity", async ({ page }) => {
  const acceptedRequests: Array<{ request_id: string; status: string; active_job_id: string | null; resume_nonce: string | null }> = [];
  let holdRecoveryRead = false;
  let releaseRecoveryRead: (() => void) | undefined;
  let recoveryReadCount = 0;
  const recoveryReadHeld = new Promise<void>((resolve) => { releaseRecoveryRead = resolve; });

  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const response = await route.fetch();
    acceptedRequests.push(await response.json() as typeof acceptedRequests[number]);
    return route.fulfill({ response });
  });
  await page.route("**/api/v1/agent/requests/*", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() !== "GET" || !/\/requests\/[^/]+$/.test(url.pathname) || !holdRecoveryRead) {
      return route.continue();
    }
    const response = await route.fetch();
    recoveryReadCount += 1;
    await recoveryReadHeld;
    return route.fulfill({ response });
  });

  await openAgent(page);
  await page.locator("#agent-prompt").fill("Run bank-outage-50");
  await page.locator("#agent-submit-btn").click();
  await expect.poll(() => acceptedRequests.length).toBe(1);
  const accepted = acceptedRequests[0];
  expect(accepted.status).toBe("WAITING_FOR_JOB");
  expect(accepted.active_job_id).toBeTruthy();
  expect(accepted.resume_nonce).toBeTruthy();
  const sessionId = await page.locator(".session-id").getAttribute("title");
  expect(sessionId).toBeTruthy();
  await expect.poll(async () => (await savedIntent(page, sessionId!))?.requestId ?? null).toBe(accepted!.request_id);

  holdRecoveryRead = true;
  await page.reload();
  await expect.poll(() => recoveryReadCount).toBe(1);
  await expect(page.locator("#agent-recovery-card")).toBeVisible();
  await expect(page.locator("#agent-recovery-card")).toContainText(accepted!.request_id);
  await expect(page.locator("#agent-recovery-card")).toContainText(accepted!.active_job_id!);
  const restored = await savedIntent(page, sessionId!);
  expect(restored?.resumeNonce).toBe(accepted.resume_nonce);
  expect(restored?.ownerSessionId).toBe(sessionId);
  releaseRecoveryRead?.();
});

test("[simulated] actual accepted work remains bound to its expired session until an explicit reconnect", async ({ page }, testInfo) => {
  const metadata = testInfo.config.metadata as E2EMetadata;
  const accepted: Array<{ requestId: string; jobId: string | null; ownerSessionId: string }> = [];
  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const headers = route.request().headers();
    const ownerSessionId = headers["x-session-id"];
    const response = await route.fetch();
    const body = await response.json() as { request_id: string; active_job_id: string | null };
    const expired = expireLocalTestSession(metadata, ownerSessionId);
    expect(expired.status).toBe(0);
    accepted.push({ requestId: body.request_id, jobId: body.active_job_id, ownerSessionId });
    return route.fulfill({ response });
  });

  const postedSessionIds: string[] = [];
  let sessionCreations = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/agent/sessions") && request.method() === "POST") sessionCreations += 1;
    if (request.url().endsWith("/api/v1/agent/requests") && request.method() === "POST") {
      postedSessionIds.push(request.headers()["x-session-id"] ?? "");
    }
  });

  await openAgent(page);
  const initialSession = await page.locator(".session-id").getAttribute("title");
  expect(initialSession).toBeTruthy();
  await page.locator("#agent-prompt").fill("Run bank-outage-50");
  await page.locator("#agent-submit-btn").click();
  await expect(page.locator("#agent-reconnect-btn")).toBeVisible();
  expect(accepted).toHaveLength(1);
  expect(accepted[0].ownerSessionId).toBe(initialSession);
  expect(accepted[0].requestId).toBeTruthy();
  expect(accepted[0].jobId).toBeTruthy();
  const oldIntent = await savedIntent(page, initialSession!);
  expect(oldIntent?.requestId).toBe(accepted[0].requestId);
  const createsBeforeReconnect = sessionCreations;

  await page.locator("#agent-reconnect-btn").click();
  await expect.poll(async () => page.locator(".session-id").getAttribute("title")).not.toBe(initialSession);
  const newSession = await page.locator(".session-id").getAttribute("title");
  expect(newSession).toBeTruthy();
  await expect(page.locator("#agent-prompt")).toBeEnabled();
  await expect(page.locator("#agent-recovery-card")).toHaveCount(0);
  expect(sessionCreations).toBeGreaterThan(createsBeforeReconnect);
  expect(postedSessionIds).toEqual([initialSession]);
  expect(await savedIntent(page, initialSession!)).toMatchObject({
    ownerSessionId: initialSession,
    requestId: accepted[0].requestId,
    activeJobId: accepted[0].jobId,
  });
  expect(await savedIntent(page, newSession!)).toBeNull();
});

for (const failure of [
  { label: "provider 401", status: 401, code: "PROVIDER_AUTH_ERROR" },
  { label: "business 403", status: 403, code: "BUSINESS_RULE_REJECTED" },
]) {
  test(`[simulated] error envelope ${failure.label} does not expire browser capability`, async ({ page }) => {
    await page.route("**/api/v1/agent/requests", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      return route.fulfill({
        status: failure.status,
        json: { detail: { error: { code: failure.code, message: "The agent request was rejected." } } },
      });
    });
    await openAgent(page);
    await page.locator("#agent-prompt").fill("Inspect the dataset");
    await page.locator("#agent-submit-btn").click();
    await expect(page.locator(".agent-panel .notice-error")).toContainText(failure.code);
    await expect(page.locator("#agent-reconnect-btn")).toHaveCount(0);
    await expect(page.locator("#agent-prompt")).toBeEnabled();
    await expect(page.locator("#agent-retry-btn")).toBeEnabled();
  });
}

test("Clear suppresses a delayed response after the real queue accepted the original POST", async ({ page }) => {
  let resolveAccepted: (() => void) | undefined;
  let releaseResponse: (() => void) | undefined;
  let resolveDelivered: (() => void) | undefined;
  const acceptedReady = new Promise<void>((resolve) => { resolveAccepted = resolve; });
  const responseGate = new Promise<void>((resolve) => { releaseResponse = resolve; });
  const responseDelivered = new Promise<void>((resolve) => { resolveDelivered = resolve; });
  let acceptedRequestId = "";
  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const response = await route.fetch();
    const body = await response.json() as { request_id: string; active_job_id: string | null };
    acceptedRequestId = body.request_id;
    expect(body.active_job_id).toBeTruthy();
    resolveAccepted?.();
    await responseGate;
    await route.fulfill({ response });
    resolveDelivered?.();
  });

  await openAgent(page);
  const sessionId = await page.locator(".session-id").getAttribute("title");
  await page.locator("#agent-prompt").fill("Run bank-outage-50");
  await page.locator("#agent-submit-btn").click();
  await acceptedReady;
  await expect(page.locator("#agent-clear-btn")).toBeVisible();
  await page.locator("#agent-clear-btn").click();
  releaseResponse?.();
  await responseDelivered;
  await expect(page.locator("#agent-recovery-card")).toHaveCount(0);
  await expect(page.locator(".agent-active-card")).toHaveCount(0);
  expect(await savedIntent(page, sessionId!)).toBeNull();
  expect(acceptedRequestId).toBeTruthy();
});

test("cancellation of the real queued job is reflected by the resumed agent request", async ({ page }) => {
  const acceptedRequests: Array<{ request_id: string; active_job_id: string | null }> = [];
  const authority: Array<{ sessionId: string; token: string }> = [];
  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const headers = route.request().headers();
    const response = await route.fetch();
    const accepted = await response.json() as { request_id: string; active_job_id: string | null };
    acceptedRequests.push(accepted);
    authority.push({ sessionId: headers["x-session-id"] ?? "", token: headers["x-session-token"] ?? "" });
    return route.fulfill({ response });
  });

  await openAgent(page);
  const scenarioId = await armWorkerScenario(page, "pause_next");
  await page.locator("#agent-prompt").fill("Run bank-outage-50");
  await page.locator("#agent-submit-btn").click();
  await expect.poll(() => acceptedRequests.length).toBe(1);
  const jobId = acceptedRequests[0].active_job_id;
  expect(jobId).toBeTruthy();
  await expect.poll(() => workerScenarioState(page, scenarioId), { timeout: 30_000 }).toBe("paused");
  const origin = new URL(page.url()).origin;
  const cancellation = await page.request.post(`${origin}/api/v1/jobs/${encodeURIComponent(jobId!)}/cancel`, {
    headers: {
      "X-Session-ID": authority[0].sessionId,
      "X-Session-Token": authority[0].token,
    },
  });
  const cancellationBody = await cancellation.json() as { job_id?: string; status?: string };
  expect(cancellation.status()).toBe(202);
  expect(cancellationBody.job_id).toBe(jobId);
  await releaseWorkerScenario(page, scenarioId);
  await expect.poll(() => workerScenarioState(page, scenarioId), { timeout: 30_000 }).toBe("cancelled");
  await expect(page.locator(".agent-active-card:not(#agent-recovery-card) .status-pill")).toHaveText("CANCELLED", { timeout: 30_000 });
  await expect(page.locator(".agent-panel .notice-error")).toContainText(/cancel/i);
  const traceError = page.locator(".trace-error").first();
  await expect(traceError).toBeVisible();
  await expect(traceError).toContainText("JOB_CANCELLED");
  await expect(traceError).toContainText(/cancel/i);
});

test("[simulated] a real managed-worker failure is retained in the resumed agent request", async ({ page }) => {
  const acceptedRequests: Array<{ request_id: string; active_job_id: string | null }> = [];
  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const response = await route.fetch();
    acceptedRequests.push(await response.json() as { request_id: string; active_job_id: string | null });
    return route.fulfill({ response });
  });
  await openAgent(page);
  const scenarioId = await armWorkerScenario(page, "fail_next");
  await page.locator("#agent-prompt").fill("Run bank-outage-50");
  await page.locator("#agent-submit-btn").click();
  await expect.poll(() => acceptedRequests.length).toBe(1);
  expect(acceptedRequests[0].active_job_id).toBeTruthy();
  await expect.poll(() => workerScenarioState(page, scenarioId), { timeout: 60_000 }).toBe("failed");
  await expect(page.locator(".agent-active-card:not(#agent-recovery-card) .status-pill")).toHaveText("FAILED", { timeout: 60_000 });
  await expect(page.locator(".agent-panel .notice-error")).toContainText(/fail/i);
  const traceError = page.locator(".trace-error").first();
  await expect(traceError).toBeVisible();
  await expect(traceError).toHaveText(/^[A-Z0-9_]{1,48}: .+/);
});

test("[simulated] terminal API response renders structured and legacy tool errors safely", async ({ page }) => {
  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const sessionId = route.request().headers()["x-session-id"];
    return route.fulfill({
      status: 200,
      json: {
        request_id: "req_luna3_failed_terminal",
        session_id: sessionId,
        status: "FAILED",
        prompt: "Run a controlled test failure",
        turn_count: 1,
        call_count: 1,
        repair_count: 0,
        active_job_id: null,
        active_tool_call_id: null,
        resume_nonce: null,
        tool_trace: [
          {
            ordinal: 1,
            tool_name: "run_experiment",
            tool_call_id: "call_luna3_structured_error",
            arguments: {},
            status: "error",
            result: null,
            error: { code: "JOB_FAILED", message: "The managed job failed safely.", debug: "must not render" },
            job_id: "job_luna3_failed_terminal",
          },
          {
            ordinal: 2,
            tool_name: "read_experiment_results",
            tool_call_id: "call_luna3_legacy_error",
            arguments: {},
            status: "error",
            result: null,
            error: "Legacy safe error.",
            job_id: null,
          },
        ],
        evidence_refs: [],
        final_response: null,
        error: { code: "WORKER_FAILED", message: "The managed job failed." },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });
  });
  await openAgent(page);
  await page.locator("#agent-prompt").fill("Run a controlled test failure");
  await page.locator("#agent-submit-btn").click();
  await expect(page.locator(".agent-active-card .status-pill")).toHaveText("FAILED");
  await expect(page.locator(".agent-panel .notice-error")).toContainText("The managed job failed.");
  const traceErrors = page.locator(".trace-error");
  await expect(traceErrors).toHaveCount(2);
  await expect(traceErrors.nth(0)).toHaveText("JOB_FAILED: The managed job failed safely.");
  await expect(traceErrors.nth(0)).not.toContainText("must not render");
  await expect(traceErrors.nth(1)).toHaveText("Legacy safe error.");
});

test("[simulated] capability rejection Clear does not replace the expired authority", async ({ page }) => {
  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({
      status: 401,
      json: { error: { code: "SESSION_EXPIRED", message: "Session expired." } },
    });
  });
  await openAgent(page);
  await page.locator("#agent-prompt").fill("Inspect the dataset");
  await page.locator("#agent-submit-btn").click();
  await expect(page.locator("#agent-reconnect-btn")).toBeVisible();
  await page.locator("#agent-clear-btn").click();
  await expect(page.locator("#agent-reconnect-btn")).toBeVisible();
  await expect(page.locator("#agent-prompt")).toBeDisabled();
});

test("[simulated] transport loss after real resume retries the same server-issued request and nonce, then permits a second question", async ({ page }) => {
  const submissions: Array<{ key: string; requestId: string }> = [];
  const resumes: Array<{ requestId: string; nonce: string }> = [];
  let dropFirstResume = true;
  await page.route("**/api/v1/agent/requests", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const requestBody = route.request().postDataJSON() as { idempotency_key: string };
    const response = await route.fetch();
    const body = await response.json() as { request_id: string };
    submissions.push({ key: requestBody.idempotency_key, requestId: body.request_id });
    return route.fulfill({ response });
  });
  await page.route("**/api/v1/agent/requests/*/resume", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as { nonce: string };
    const requestId = new URL(route.request().url()).pathname.match(/\/requests\/([^/]+)\/resume$/)?.[1] ?? "";
    const response = await route.fetch();
    resumes.push({ requestId, nonce: body.nonce });
    if (dropFirstResume) {
      dropFirstResume = false;
      return route.abort("failed");
    }
    return route.fulfill({ response });
  });

  await openAgent(page);
  await page.locator("#agent-prompt").fill("Run bank-outage-50");
  await page.locator("#agent-submit-btn").click();
  await expect(page.locator(".agent-panel .notice-error")).toContainText("NETWORK_UNAVAILABLE", { timeout: 10 * 60 * 1000 });
  expect(resumes).toHaveLength(1);
  const sessionId = await page.locator(".session-id").getAttribute("title");
  const recovery = await savedIntent(page, sessionId!);
  expect(recovery?.phase).toBe("transport_error");
  expect(recovery?.retryAction).toBe("resume");
  expect(recovery?.requestId).toBe(resumes[0].requestId);
  expect(recovery?.resumeNonce).toBe(resumes[0].nonce);

  await page.reload();
  await expect(page.locator("#agent-recovery-card")).toBeVisible();
  await expect(page.locator("#agent-recovery-card")).toContainText(resumes[0].requestId);
  const reloadedRecovery = await savedIntent(page, sessionId!);
  expect(reloadedRecovery?.retryAction).toBe("resume");
  expect(reloadedRecovery?.resumeNonce).toBe(resumes[0].nonce);
  await page.locator("#agent-retry-btn").click();
  await expect.poll(() => resumes.length).toBe(2);
  expect(resumes[1]).toEqual(resumes[0]);
  await expect(page.locator(".agent-final-response")).toBeVisible({ timeout: 10 * 60 * 1000 });
  expect(submissions).toHaveLength(1);

  await page.locator("#agent-prompt").fill("Inspect the dataset");
  await page.locator("#agent-submit-btn").click();
  await expect.poll(() => submissions.length).toBe(2);
  expect(submissions[1].key).not.toBe(submissions[0].key);
  expect(submissions[1].requestId).not.toBe(submissions[0].requestId);
  await expect(page.locator(".agent-final-response")).toBeVisible({ timeout: 10 * 60 * 1000 });
});

test("[simulated] resume 500 cannot adopt a foreign terminal request or replace the saved nonce", async ({ page }) => {
  let continuation: { requestId: string; nonce: string } | null = null;
  await page.route("**/api/v1/agent/requests/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (route.request().method() === "POST" && pathname.endsWith("/resume")) {
      const body = route.request().postDataJSON() as { nonce: string };
      continuation = { requestId: pathname.split("/").at(-2)!, nonce: body.nonce };
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({
        error: { code: "EXECUTION_ERROR", message: "Simulated continuation failure." },
      }) });
    }
    if (route.request().method() === "GET" && continuation) {
      const response = await route.fetch();
      const record = await response.json();
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        ...record, request_id: "req_foreign_terminal", status: "FAILED",
      }) });
    }
    return route.continue();
  });
  await openAgent(page);
  const sessionId = await page.locator(".session-id").getAttribute("title");
  expect(sessionId).toBeTruthy();
  await page.locator("#agent-prompt").fill("Run bank-outage-50");
  await page.locator("#agent-submit-btn").click();
  await expect.poll(() => continuation, { timeout: 60_000 }).not.toBeNull();
  await expect(page.locator(".agent-panel .notice-error")).toContainText("Simulated continuation failure.");
  const saved = await savedIntent(page, sessionId!);
  expect(saved?.requestId).toBe(continuation!.requestId);
  expect(saved?.resumeNonce).toBe(continuation!.nonce);
  expect(saved?.phase).toBe("transport_error");
  await expect(page.locator(".agent-active-card:not(#agent-recovery-card) .status-pill")).not.toHaveText("FAILED");
  await expect(page.locator("#agent-recovery-card")).not.toContainText("req_foreign_terminal");
});

test("agent intent storage failure is visible and prevents an unsaved POST", async ({ page }) => {
  let postCount = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/agent/requests") && request.method() === "POST") postCount += 1;
  });
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key: string, value: string) {
      if (key.startsWith("shiftguard_agent_intent_")) throw new DOMException("blocked", "QuotaExceededError");
      return original.call(this, key, value);
    };
  });
  await openAgent(page);
  await page.locator("#agent-prompt").fill("Inspect the dataset");
  await page.locator("#agent-submit-btn").click();
  await expect(page.locator("#agent-storage-error")).toBeVisible();
  expect(postCount).toBe(0);
});
