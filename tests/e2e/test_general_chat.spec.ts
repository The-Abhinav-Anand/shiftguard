import { test, expect, type Page } from "../../frontend/e2e/fixtures";

async function mockWorkbenchApi(page: Page) {
  await page.route("**/health/live", (route) => route.fulfill({ status: 200, json: { status: "ok" } }));
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/agent/sessions" && request.method() === "POST") {
      return route.fulfill({ status: 201, json: {
        session_id: "scripted-browser-session",
        capability_token: "scripted-browser-capability",
        created_at: "2026-10-09T00:00:00Z",
      } });
    }
    if (url.pathname.startsWith("/api/v1/agent/sessions/")) {
      return route.fulfill({ status: 200, json: { valid: true } });
    }
    if (url.pathname === "/api/v1/experiments") {
      return route.fulfill({ status: 200, json: { experiments: [] } });
    }
    return route.fulfill({ status: 200, json: {} });
  });
}

// Completion responses carry the server's stable message identities (OR-01).
function completionJson(conversationId: string, turn: number, reply: string, firstOrdinal = 1) {
  return {
    conversation_id: conversationId,
    message_id: `scripted-assistant-${turn}`,
    receipt_id: `scripted-receipt-${turn}`,
    user_message_id: `scripted-user-${turn}`,
    assistant_message_id: `scripted-assistant-${turn}`,
    user_ordinal: firstOrdinal,
    assistant_ordinal: firstOrdinal + 1,
    status: "COMPLETED",
    reply,
    disclaimer: "Scripted browser-test response.",
    usage: { input_tokens: 0, output_tokens: 0 },
  };
}

function mockStatus(page: Page, overrides: Record<string, unknown> = {}) {
  return page.route("**/api/v1/agent/status", (route) => route.fulfill({
    status: 200,
    json: {
      enabled: false,
      available: true,
      general_chat_enabled: true,
      ordinary_budget: {
        utc_day: "2026-10-09",
        calls_used: 2,
        calls_remaining: 8,
        tokens_committed: 1250,
        tokens_remaining: 48750,
        halted: false,
      },
      model: "scripted-chat-fixture",
      max_turns: 0,
      max_calls: 0,
      ...overrides,
    },
  }));
}

test("[simulated] general chat stays disabled while paused or without a provider and tolerates missing budget fields", async ({ page }) => {
  await mockWorkbenchApi(page);
  await mockStatus(page, { available: false, general_chat_enabled: false, ordinary_budget: {} });
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "General chat", exact: true }).click();

  await expect(page.getByRole("heading", { name: "General chat", exact: true })).toBeVisible();
  await expect(page.getByText("General chat is paused.", { exact: true })).toBeVisible();
  await expect(page.getByText("Shared UTC-day paid allowance: allowance details unavailable.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send message", exact: true })).toBeDisabled();
  await expect(page.locator("#general-chat-prompt")).toBeDisabled();
});

test("[simulated] ordinary conversation sends only on submit, survives panel switching and reloads from history", async ({ page }) => {
  const sent: Array<{ body: { prompt: string; idempotency_key: string; conversation_id: string | null }; sessionHeadersPresent: boolean }> = [];
  let conversationMessages: Array<{ id: string; ordinal: number; role: "user" | "assistant"; content: string }> = [];
  let historyReads = 0;
  await mockWorkbenchApi(page);
  await mockStatus(page);
  await page.route("**/api/v1/chat/messages", async (route) => {
    const request = route.request();
    const body = request.postDataJSON() as { prompt: string; idempotency_key: string; conversation_id: string | null };
    const headers = request.headers();
    sent.push({ body, sessionHeadersPresent: Boolean(headers["x-session-id"] && headers["x-session-token"]) });
    const reply = sent.length === 1 ? "Literal text: <img src=x onerror=alert(1)>" : "Second scripted reply.";
    const firstOrdinal = conversationMessages.length + 1;
    conversationMessages = [
      ...conversationMessages,
      { id: `scripted-user-${sent.length}`, ordinal: firstOrdinal, role: "user", content: body.prompt },
      { id: `scripted-assistant-${sent.length}`, ordinal: firstOrdinal + 1, role: "assistant", content: reply },
    ];
    return route.fulfill({ status: 200, json: completionJson("scripted-conversation-1", sent.length, reply, firstOrdinal) });
  });
  await page.route("**/api/v1/chat/conversations/scripted-conversation-1", async (route) => {
    historyReads += 1;
    return route.fulfill({ status: 200, json: {
      conversation_id: "scripted-conversation-1",
      messages: conversationMessages,
    } });
  });

  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  const prompt = page.getByLabel("Message");
  await expect(prompt).toBeEnabled();
  await expect(page.getByText("Shared UTC-day paid allowance · 2026-10-09: 2/10 calls used · 8 remaining · 1,250/50,000 tokens committed · 48,750 remaining.", { exact: true })).toBeVisible();
  await prompt.fill("First explicit message");
  await expect.poll(() => sent.length).toBe(0);
  await page.getByRole("button", { name: "Send message", exact: true }).click();

  await expect(page.getByText("Literal text: <img src=x onerror=alert(1)>", { exact: true })).toBeVisible();
  await expect(page.locator(".general-chat__messages img")).toHaveCount(0);
  await expect(page.getByText("AI response · not verified experiment evidence", { exact: true })).toBeVisible();
  expect(sent[0].body).toEqual({
    prompt: "First explicit message",
    idempotency_key: expect.any(String),
    conversation_id: null,
  });
  expect(sent[0].sessionHeadersPresent).toBe(true);

  await page.getByRole("button", { name: "Results assistant", exact: true }).click();
  await expect(page.locator(".agent-panel")).toBeVisible();
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  await expect(page.getByText("First explicit message", { exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  await expect(page.getByText("First explicit message", { exact: true })).toBeVisible();
  await expect.poll(() => historyReads).toBe(1);

  await prompt.fill("Follow-up question");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("Second scripted reply.", { exact: true })).toBeVisible();
  expect(sent[1].body.prompt).toBe("Follow-up question");
  expect(sent[1].body.conversation_id).toBe("scripted-conversation-1");
  expect(sent[1].body.idempotency_key).not.toBe(sent[0].body.idempotency_key);
});

test("[simulated] unresolved reply is reported as pending and a new conversation releases the panel", async ({ page }) => {
  const attempts: Array<{ prompt: string; idempotency_key: string; conversation_id: string | null }> = [];
  await mockWorkbenchApi(page);
  await mockStatus(page);
  await page.route("**/api/v1/chat/messages", async (route) => {
    attempts.push(route.request().postDataJSON());
    if (attempts.length === 1) {
      return route.fulfill({ status: 504, json: { error: { code: "PROVIDER_TIMEOUT", message: "Provider request timed out. Please try again." } } });
    }
    if (attempts.length === 2) {
      return route.fulfill({ status: 202, json: { conversation_id: "unresolved-conversation", message_id: "unresolved-message", status: "PENDING" } });
    }
    return route.fulfill({ status: 200, json: completionJson("fresh-conversation", 3, "Reply in the new conversation.") });
  });

  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  await page.getByLabel("Message").fill("Message with an unknown outcome");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("[PROVIDER_TIMEOUT] Provider request timed out. Please try again.", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Retry same message", exact: true }).click();
  await expect(page.getByText("[CHAT_REPLY_PENDING] The earlier request is still unresolved on the server and will not be sent again.", { exact: true })).toBeVisible();
  expect(attempts[1]).toEqual(attempts[0]);

  await page.getByRole("button", { name: "New conversation", exact: true }).click();
  await expect(page.getByRole("button", { name: "Retry same message", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Message")).toHaveValue("");
  await page.getByLabel("Message").fill("Message in a new conversation");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("Reply in the new conversation.", { exact: true })).toBeVisible();
  expect(attempts).toHaveLength(3);
  expect(attempts[2].conversation_id).toBeNull();
  expect(attempts[2].idempotency_key).not.toBe(attempts[0].idempotency_key);
});

test("[simulated] failed chat submission keeps its idempotency key until explicit retry", async ({ page }) => {
  const attempts: Array<{ body: unknown; sessionHeadersPresent: boolean }> = [];
  await mockWorkbenchApi(page);
  await mockStatus(page);
  await page.route("**/api/v1/chat/messages", async (route) => {
    const request = route.request();
    attempts.push({
      body: request.postDataJSON(),
      sessionHeadersPresent: Boolean(request.headers()["x-session-id"] && request.headers()["x-session-token"]),
    });
    if (attempts.length === 1) return route.abort("failed");
    return route.fulfill({ status: 200, json: completionJson("retry-conversation", 2, "Recovered with the same request identity.") });
  });

  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  await page.getByLabel("Message").fill("Retry this exact message");
  await page.getByRole("button", { name: "Send message", exact: true }).click();

  await expect(page.getByRole("button", { name: "Retry same message", exact: true })).toBeVisible();
  await expect.poll(() => attempts.length).toBe(1);
  await expect(page.getByRole("button", { name: "Send message", exact: true })).toBeDisabled();
  await page.waitForTimeout(150);
  expect(attempts).toHaveLength(1);

  await page.getByRole("button", { name: "Retry same message", exact: true }).click();
  await expect(page.getByText("Recovered with the same request identity.", { exact: true })).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[1]).toEqual(attempts[0]);
  expect(attempts[0].sessionHeadersPresent).toBe(true);
});
