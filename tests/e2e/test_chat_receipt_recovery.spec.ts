import { test, expect, type Page } from "../../frontend/e2e/fixtures";
import { ChatIdentityConflict, mergeChatMessages } from "../../frontend/src/api/chat";

/*
 * OR-01 / OR-03 browser regressions. The API is mocked; the mock models the server's
 * stable message identities and its idempotent receipts. Backend identity guarantees
 * are proven separately in tests/agent/test_chat_review_regressions.py.
 */

const SESSION = { session_id: "review-session", capability_token: "review-capability" };
const CHAT_KEY = "shiftguard_general_chat_v1";
const CONVERSATION = "conv-1";

interface Row { id: string; ordinal: number; role: "user" | "assistant"; content: string }
interface PostBody { prompt: string; idempotency_key: string; conversation_id: string | null }
type PostOutcome =
  | { kind: "abort" }
  | { kind: "json"; status: number; json: unknown };

const FIRST_TURN: Row[] = [
  { id: "msg-u1", ordinal: 1, role: "user", content: "First question" },
  { id: "msg-a1", ordinal: 2, role: "assistant", content: "First answer" },
];
const PENDING_USER: Row = { id: "msg-u2", ordinal: 3, role: "user", content: "Follow-up question" };
const REPLY_TEXT = "Recovered paid reply must remain visible";

function completionBody(conversationId: string, user: Row, assistant: Row, reply = assistant.content) {
  return {
    conversation_id: conversationId,
    message_id: assistant.id,
    receipt_id: `receipt-${user.id}`,
    user_message_id: user.id,
    assistant_message_id: assistant.id,
    user_ordinal: user.ordinal,
    assistant_ordinal: assistant.ordinal,
    status: "COMPLETED",
    reply,
    disclaimer: "Scripted browser-test response.",
    usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
  };
}

class FakeChatServer {
  rows: Row[];
  conversationId: string;
  posts: PostBody[] = [];
  historyReads = 0;
  private receipts = new Map<string, unknown>();
  private sequence = 0;
  /** Return an outcome to override the default idempotent behaviour for one POST. */
  onPost: (body: PostBody, attempt: number) => Promise<PostOutcome | undefined> | PostOutcome | undefined = () => undefined;

  constructor(rows: Row[] = [], conversationId = CONVERSATION) {
    this.rows = rows;
    this.conversationId = conversationId;
  }

  handlePost(body: PostBody): PostOutcome {
    const replay = this.receipts.get(body.idempotency_key);
    if (replay) return { kind: "json", status: 200, json: replay };
    this.sequence += 1;
    const conversationId = body.conversation_id ?? this.conversationId;
    const ordinal = this.rows.reduce((highest, row) => Math.max(highest, row.ordinal), 0);
    const user: Row = { id: `srv-u${this.sequence}`, ordinal: ordinal + 1, role: "user", content: body.prompt };
    const assistant: Row = { id: `srv-a${this.sequence}`, ordinal: ordinal + 2, role: "assistant", content: `Reply ${this.sequence}` };
    this.rows = [...this.rows, user, assistant];
    const json = completionBody(conversationId, user, assistant);
    this.receipts.set(body.idempotency_key, json);
    return { kind: "json", status: 200, json };
  }
}

async function mockApi(page: Page, server: FakeChatServer) {
  await page.route("**/health/**", (route) => route.fulfill({ status: 200, json: { status: "ok" } }));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/agent/sessions" && route.request().method() === "POST") {
      return route.fulfill({ status: 201, json: { ...SESSION, created_at: "2026-10-14T00:00:00Z" } });
    }
    if (url.pathname.startsWith("/api/v1/agent/sessions/")) return route.fulfill({ status: 200, json: { valid: true } });
    if (url.pathname === "/api/v1/experiments") return route.fulfill({ status: 200, json: { experiments: [] } });
    return route.fulfill({ status: 200, json: {} });
  });
  await page.route("**/api/v1/agent/status", (route) => route.fulfill({
    status: 200,
    json: {
      enabled: false,
      available: true,
      general_chat_enabled: true,
      ordinary_budget: { utc_day: "2026-10-14", calls_used: 2, calls_remaining: 8, tokens_committed: 100, tokens_remaining: 49900, halted: false },
      model: "scripted-chat-fixture",
      max_turns: 0,
      max_calls: 0,
    },
  }));
  await page.route("**/api/v1/chat/conversations/*", (route) => {
    server.historyReads += 1;
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    return route.fulfill({ status: 200, json: { conversation_id: id, messages: server.rows } });
  });
  let attempt = 0;
  await page.route("**/api/v1/chat/messages", async (route) => {
    const body = route.request().postDataJSON() as PostBody;
    server.posts.push(body);
    attempt += 1;
    const outcome = (await server.onPost(body, attempt)) ?? server.handlePost(body);
    if (outcome.kind === "abort") return route.abort("failed");
    return route.fulfill({ status: outcome.status, json: outcome.json });
  });
}

/** Seed the workspace session once; later navigations (reloads) keep whatever the app stored. */
async function seed(page: Page, chat: unknown | null) {
  await page.addInitScript(({ session, chat, chatKey }) => {
    if (sessionStorage.getItem("__seeded")) return;
    sessionStorage.setItem("__seeded", "1");
    localStorage.setItem("shiftguard.browser-workspace.v1", JSON.stringify({
      version: 1, session, jobs: [], pending_submission: null, cached_experiment: null,
    }));
    if (chat) sessionStorage.setItem(chatKey, JSON.stringify(chat));
  }, { session: SESSION, chat, chatKey: CHAT_KEY });
}

function storedChat(rows: Row[], prompt = PENDING_USER.content) {
  return {
    version: 2,
    ownerSessionId: SESSION.session_id,
    conversationId: CONVERSATION,
    messages: rows,
    failedTurns: [],
    pending: {
      ownerSessionId: SESSION.session_id,
      prompt,
      idempotencyKey: "original-key",
      conversationId: CONVERSATION,
      baseOrdinal: 2,
      userMessageId: null,
    },
  };
}

async function openChat(page: Page) {
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  return page.getByRole("list", { name: "General chat conversation" });
}

const retryButton = (page: Page) => page.getByRole("button", { name: "Retry same message", exact: true });

async function visibleIds(list: ReturnType<Page["locator"]>) {
  return list.locator("li[data-message-id]").evaluateAll((items) => items.map((item) => (item as HTMLElement).dataset.messageId));
}

async function storedState(page: Page) {
  return page.evaluate((key) => {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  }, CHAT_KEY);
}

test("[simulated] OR-01: a pending-only history is reconciled by identity and the paid reply appears exactly once", async ({ page }) => {
  const server = new FakeChatServer([...FIRST_TURN, PENDING_USER]);
  const reply: Row = { id: "msg-a2", ordinal: 4, role: "assistant", content: REPLY_TEXT };
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  server.onPost = async () => {
    await held;
    server.rows = [...server.rows, reply];
    return { kind: "json", status: 200, json: completionBody(CONVERSATION, PENDING_USER, reply) };
  };
  await seed(page, storedChat(FIRST_TURN));
  await mockApi(page, server);

  const list = await openChat(page);
  await expect(list.getByText("Follow-up question", { exact: true })).toHaveCount(1);
  await expect(list.locator("li")).toHaveCount(3);
  await expect(page.getByText("Not yet confirmed by the server")).toHaveCount(0);
  expect(server.posts).toHaveLength(0);

  await retryButton(page).click();
  await expect.poll(() => server.posts.length).toBe(1);
  // The retry UI stays until the completion has been reconciled.
  await expect(page.locator(".general-chat__pending")).toBeVisible();
  release();
  await expect(page.locator(".general-chat__pending")).toHaveCount(0);

  await expect(list.getByText(REPLY_TEXT, { exact: true })).toHaveCount(1);
  await expect(list.locator("li")).toHaveCount(4);
  expect(await visibleIds(list)).toEqual(["msg-u1", "msg-a1", "msg-u2", "msg-a2"]);
  expect(server.posts[0]).toEqual({ prompt: "Follow-up question", idempotency_key: "original-key", conversation_id: CONVERSATION });
  const stored = await storedState(page);
  expect(stored.pending).toBeNull();
  expect(stored.messages.map((message: Row) => message.id)).toEqual(["msg-u1", "msg-a1", "msg-u2", "msg-a2"]);
});

test("[simulated] OR-01: older id-less session state refetches server history and never auto-submits", async ({ page }) => {
  const server = new FakeChatServer([...FIRST_TURN, PENDING_USER]);
  const reply: Row = { id: "msg-a2", ordinal: 4, role: "assistant", content: REPLY_TEXT };
  server.onPost = () => {
    server.rows = [...server.rows, reply];
    return { kind: "json", status: 200, json: completionBody(CONVERSATION, PENDING_USER, reply) };
  };
  const legacy = {
    version: 1,
    ownerSessionId: SESSION.session_id,
    conversationId: CONVERSATION,
    messages: [{ role: "user", content: "First question" }, { role: "assistant", content: "First answer" }],
    messageCount: 2,
    pending: {
      ownerSessionId: SESSION.session_id,
      prompt: "Follow-up question",
      idempotencyKey: "original-key",
      conversationId: CONVERSATION,
      previousMessageCount: 2,
    },
  };
  await seed(page, legacy);
  await mockApi(page, server);

  const list = await openChat(page);
  await expect(list.locator("li")).toHaveCount(3);
  await expect.poll(() => server.historyReads).toBe(1);
  expect(await visibleIds(list)).toEqual(["msg-u1", "msg-a1", "msg-u2"]);
  await page.waitForTimeout(400);
  expect(server.posts).toHaveLength(0);

  await retryButton(page).click();
  await expect(list.getByText(REPLY_TEXT, { exact: true })).toHaveCount(1);
  await expect(list.locator("li")).toHaveCount(4);
  expect(server.posts).toHaveLength(1);
  expect(server.posts[0].idempotency_key).toBe("original-key");
  expect((await storedState(page)).version).toBe(2);
});

test("[simulated] OR-01: history that already holds both rows is not duplicated by the retry", async ({ page }) => {
  const reply: Row = { id: "msg-a2", ordinal: 4, role: "assistant", content: REPLY_TEXT };
  const server = new FakeChatServer([...FIRST_TURN, PENDING_USER, reply]);
  server.onPost = () => ({ kind: "json", status: 200, json: completionBody(CONVERSATION, PENDING_USER, reply) });
  await seed(page, storedChat(FIRST_TURN));
  await mockApi(page, server);

  const list = await openChat(page);
  await expect(list.locator("li")).toHaveCount(4);
  await expect(retryButton(page)).toBeVisible();
  await retryButton(page).click();
  await expect(page.locator(".general-chat__pending")).toHaveCount(0);
  await expect(list.locator("li")).toHaveCount(4);
  await expect(list.getByText(REPLY_TEXT, { exact: true })).toHaveCount(1);
  expect(await visibleIds(list)).toEqual(["msg-u1", "msg-a1", "msg-u2", "msg-a2"]);
  expect(server.posts[0].idempotency_key).toBe("original-key");
});

test("[simulated] OR-01: a response lost before the conversation id arrived is recovered with the original request", async ({ page }) => {
  const server = new FakeChatServer([], "conv-created-by-lost-response");
  server.onPost = (body, attempt) => {
    if (attempt === 1) {
      // The server processed the request (rows exist) but the browser never saw the reply.
      server.handlePost(body);
      return { kind: "abort" };
    }
    return undefined;
  };
  await seed(page, null);
  await mockApi(page, server);
  const list = await openChat(page);

  await page.getByLabel("Message").fill("Opening message");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(retryButton(page)).toBeVisible();
  await expect(list.getByText("Opening message", { exact: true })).toHaveCount(1);
  await expect(page.getByText("Not yet confirmed by the server", { exact: true })).toBeVisible();
  expect((await storedState(page)).conversationId).toBeNull();

  await retryButton(page).click();
  await expect(page.locator(".general-chat__pending")).toHaveCount(0);
  await expect(list.locator("li")).toHaveCount(2);
  await expect(list.getByText("Opening message", { exact: true })).toHaveCount(1);
  await expect(list.getByText("Reply 1", { exact: true })).toHaveCount(1);
  await expect(page.getByText("Not yet confirmed by the server", { exact: true })).toHaveCount(0);
  expect(server.posts).toHaveLength(2);
  expect(server.posts[1]).toEqual(server.posts[0]);
  expect(server.posts[0].conversation_id).toBeNull();
  expect((await storedState(page)).conversationId).toBe("conv-created-by-lost-response");

  await page.getByLabel("Message").fill("Second message");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(list.getByText("Reply 2", { exact: true })).toHaveCount(1);
  expect(server.posts[2].conversation_id).toBe("conv-created-by-lost-response");
  expect(server.posts[2].idempotency_key).not.toBe(server.posts[0].idempotency_key);
});

test("[simulated] OR-01: identical text in two different messages stays two messages", async ({ page }) => {
  const server = new FakeChatServer();
  server.onPost = (body) => {
    const outcome = server.handlePost(body);
    // Force identical content for every assistant reply.
    if (outcome.kind === "json") {
      const json = outcome.json as ReturnType<typeof completionBody>;
      json.reply = "ok";
      server.rows = server.rows.map((row) => (row.id === json.assistant_message_id ? { ...row, content: "ok" } : row));
    }
    return outcome;
  };
  await seed(page, null);
  await mockApi(page, server);
  const list = await openChat(page);

  for (const key of ["one", "two"]) {
    await page.getByLabel("Message").fill("hello");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await expect(list.getByText("ok", { exact: true })).toHaveCount(key === "one" ? 1 : 2);
  }
  await expect(list.getByText("hello", { exact: true })).toHaveCount(2);
  await expect(list.locator("li")).toHaveCount(4);
  expect(await visibleIds(list)).toEqual(["srv-u1", "srv-a1", "srv-u2", "srv-a2"]);

  // A reload merges the same history by id and does not collapse equal text.
  await page.reload();
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  await expect.poll(() => server.historyReads).toBeGreaterThan(0);
  await expect(list.locator("li")).toHaveCount(4);
  await expect(list.getByText("hello", { exact: true })).toHaveCount(2);
});

test("[simulated] OR-01: reloading twice keeps one pending identity and no duplicates", async ({ page }) => {
  const reply: Row = { id: "msg-a2", ordinal: 4, role: "assistant", content: REPLY_TEXT };
  const server = new FakeChatServer([...FIRST_TURN, PENDING_USER]);
  server.onPost = () => {
    server.rows = [...server.rows, reply];
    return { kind: "json", status: 200, json: completionBody(CONVERSATION, PENDING_USER, reply) };
  };
  await seed(page, storedChat(FIRST_TURN));
  await mockApi(page, server);

  let list = await openChat(page);
  await expect(list.locator("li")).toHaveCount(3);
  for (let reload = 0; reload < 2; reload += 1) {
    await page.reload();
    await expect(page.getByText("API connected", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "General chat", exact: true }).click();
    list = page.getByRole("list", { name: "General chat conversation" });
    await expect(list.locator("li")).toHaveCount(3);
    await expect(retryButton(page)).toBeVisible();
    expect((await storedState(page)).pending.idempotencyKey).toBe("original-key");
  }
  expect(server.posts).toHaveLength(0);
  await retryButton(page).click();
  await expect(page.locator(".general-chat__pending")).toHaveCount(0);
  await expect(list.locator("li")).toHaveCount(4);
  await expect(list.getByText(REPLY_TEXT, { exact: true })).toHaveCount(1);
  expect(server.posts.map((post) => post.idempotency_key)).toEqual(["original-key"]);
});

test("[simulated] OR-01: a failed session-storage write keeps the original key and still shows the reply once", async ({ page }) => {
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key: string, value: string) {
      if ((window as unknown as { __failStorage?: boolean }).__failStorage && key === "shiftguard_general_chat_v1") {
        throw new DOMException("quota", "QuotaExceededError");
      }
      return original.call(this, key, value);
    };
  });
  const server = new FakeChatServer([], "conv-storage");
  let breakStorageOnFirstPost = true;
  server.onPost = async (body) => {
    if (breakStorageOnFirstPost) {
      breakStorageOnFirstPost = false;
      await page.evaluate(() => { (window as unknown as { __failStorage?: boolean }).__failStorage = true; });
    }
    return server.handlePost(body);
  };
  await seed(page, null);
  await mockApi(page, server);
  const list = await openChat(page);

  await page.getByLabel("Message").fill("Save me");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("The reply arrived, but its completion could not be saved.", { exact: false })).toBeVisible();
  await expect(list.getByText("Reply 1", { exact: true })).toHaveCount(1);
  await expect(list.locator("li")).toHaveCount(2);
  await expect(retryButton(page)).toBeVisible();
  expect(server.posts).toHaveLength(1);

  await page.evaluate(() => { (window as unknown as { __failStorage?: boolean }).__failStorage = false; });
  await retryButton(page).click();
  await expect(page.locator(".general-chat__pending")).toHaveCount(0);
  await expect(list.getByText("Reply 1", { exact: true })).toHaveCount(1);
  await expect(list.locator("li")).toHaveCount(2);
  expect(server.posts).toHaveLength(2);
  expect(server.posts[1]).toEqual(server.posts[0]);
  expect((await storedState(page)).pending).toBeNull();

  await page.getByLabel("Message").fill("Next message");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(list.getByText("Reply 2", { exact: true })).toHaveCount(1);
  expect(server.posts[2].conversation_id).toBe("conv-storage");
});

test("[simulated] OR-01: when browser storage cannot be written nothing is sent", async ({ page }) => {
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key: string, value: string) {
      if (key === "shiftguard_general_chat_v1") throw new DOMException("quota", "QuotaExceededError");
      return original.call(this, key, value);
    };
  });
  const server = new FakeChatServer();
  await seed(page, null);
  await mockApi(page, server);
  await openChat(page);
  await page.getByLabel("Message").fill("Never sent");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("Chat state could not be saved in this tab. The message was not sent.").first()).toBeVisible();
  await page.waitForTimeout(300);
  expect(server.posts).toHaveLength(0);
});

test("[simulated] OR-01: a conflicting server record is a visible protocol error and keeps the pending identity", async ({ page }) => {
  const reply: Row = { id: "msg-a2", ordinal: 5, role: "assistant", content: REPLY_TEXT };
  const server = new FakeChatServer([...FIRST_TURN, PENDING_USER]);
  // The completion claims the pending user message sits at ordinal 4, contradicting the fetched history (3).
  server.onPost = () => ({
    kind: "json",
    status: 200,
    json: completionBody(CONVERSATION, { ...PENDING_USER, ordinal: 4 }, reply),
  });
  await seed(page, storedChat(FIRST_TURN));
  await mockApi(page, server);

  const list = await openChat(page);
  await expect(list.locator("li")).toHaveCount(3);
  await retryButton(page).click();
  await expect(page.getByText("[CHAT_IDENTITY_CONFLICT]", { exact: false })).toBeVisible();
  await expect(retryButton(page)).toBeVisible();
  await expect(list.getByText(REPLY_TEXT, { exact: true })).toHaveCount(0);
  await expect(list.locator("li")).toHaveCount(3);
  const stored = await storedState(page);
  expect(stored.pending.idempotencyKey).toBe("original-key");
  await retryButton(page).click();
  await expect.poll(() => server.posts.length).toBe(2);
  expect(server.posts[1].idempotency_key).toBe("original-key");
});

test("[simulated] OR-03: a definite terminal failure marks the turn and the conversation continues with a new key", async ({ page }) => {
  const server = new FakeChatServer([], "conv-failed");
  server.onPost = (body, attempt) => {
    if (attempt !== 1) return undefined;
    server.rows = [{ id: "failed-u1", ordinal: 1, role: "user", content: body.prompt }];
    return {
      kind: "json",
      status: 502,
      json: {
        status: "FAILED",
        receipt_id: "receipt-failed-1",
        conversation_id: "conv-failed",
        user_message_id: "failed-u1",
        error: { code: "CHAT_REPLY_TOO_LONG", message: "Provider reply exceeded the chat response limit.", request_id: "req-1" },
      },
    };
  };
  await seed(page, null);
  await mockApi(page, server);
  const list = await openChat(page);

  await page.getByLabel("Message").fill("Message with a rejected reply");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("[CHAT_REPLY_TOO_LONG] Provider reply exceeded the chat response limit.", { exact: false })).toBeVisible();
  // A definite failure is not an ambiguous network error: nothing is left to retry.
  await expect(retryButton(page)).toHaveCount(0);
  await expect(page.getByText("No reply was recorded for this message (CHAT_REPLY_TOO_LONG).", { exact: false })).toBeVisible();
  await expect(list.getByText("Message with a rejected reply", { exact: true })).toHaveCount(1);
  await expect.poll(() => server.historyReads).toBe(1);
  expect(await visibleIds(list)).toEqual(["failed-u1"]);
  const stored = await storedState(page);
  expect(stored.pending).toBeNull();
  expect(stored.conversationId).toBe("conv-failed");

  await page.getByLabel("Message").fill("Try again differently");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(list.getByText("Reply 1", { exact: true })).toHaveCount(1);
  expect(server.posts).toHaveLength(2);
  expect(server.posts[1].conversation_id).toBe("conv-failed");
  expect(server.posts[1].idempotency_key).not.toBe(server.posts[0].idempotency_key);
  await expect(list.locator("li")).toHaveCount(3);
  await expect(page.getByText("No reply was recorded for this message (CHAT_REPLY_TOO_LONG).", { exact: false })).toHaveCount(1);

  await page.reload();
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "General chat", exact: true }).click();
  await expect(list.locator("li")).toHaveCount(3);
  await expect(page.getByText("No reply was recorded for this message (CHAT_REPLY_TOO_LONG).", { exact: false })).toHaveCount(1);
});

test("mergeChatMessages deduplicates by identity, orders by ordinal and rejects contradictions", () => {
  const user: Row = { id: "a", ordinal: 1, role: "user", content: "same" };
  const assistant: Row = { id: "b", ordinal: 2, role: "assistant", content: "reply" };
  const twin: Row = { id: "c", ordinal: 3, role: "user", content: "same" };
  expect(mergeChatMessages([assistant, user], [user, twin, assistant]).map((row) => row.id)).toEqual(["a", "b", "c"]);
  expect(mergeChatMessages([], [])).toEqual([]);
  const withNote = mergeChatMessages([{ ...assistant, disclaimer: "note" } as Row], [assistant]);
  expect((withNote[0] as Row & { disclaimer?: string }).disclaimer).toBe("note");
  expect(() => mergeChatMessages([user], [{ ...user, content: "edited" }])).toThrow(ChatIdentityConflict);
  expect(() => mergeChatMessages([user], [{ ...user, ordinal: 4 }])).toThrow(ChatIdentityConflict);
  expect(() => mergeChatMessages([user], [{ ...user, role: "assistant" }])).toThrow(ChatIdentityConflict);
  expect(() => mergeChatMessages([user], [{ ...assistant, id: "z", ordinal: 1 }])).toThrow(ChatIdentityConflict);
  expect(() => mergeChatMessages([], [{ ...user, id: "" }])).toThrow(ChatIdentityConflict);
  expect(() => mergeChatMessages([], [{ ...user, ordinal: 0 }])).toThrow(ChatIdentityConflict);
});
