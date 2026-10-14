import { ApiError } from "./client";
import type { SessionCredentials } from "./types";

/** A message exactly as the server persisted it. Identity is the server `id` and `ordinal`. */
export interface ChatMessage {
  id: string;
  ordinal: number;
  role: "user" | "assistant";
  content: string;
}

export interface ChatSendResponse {
  conversation_id: string;
  /** Compatibility alias of `assistant_message_id`. */
  message_id: string;
  receipt_id: string;
  user_message_id: string;
  assistant_message_id: string;
  user_ordinal: number;
  assistant_ordinal: number;
  status: "COMPLETED";
  reply: string;
  disclaimer: string;
  usage: Record<string, unknown>;
}

export interface ChatConversation {
  conversation_id: string;
  messages: ChatMessage[];
}

/** Two server records disagree about the same identity (or ordinal), or a record is malformed. */
export class ChatIdentityConflict extends Error {
  readonly code = "CHAT_IDENTITY_CONFLICT";

  constructor(message: string) {
    super(message);
    this.name = "ChatIdentityConflict";
  }
}

/**
 * The server returned a definite, replayable failure for a request that did reach the model
 * provider. The generic ApiError would discard the receipt metadata the client needs to tell
 * this apart from an ambiguous network error.
 */
export class ChatTerminalFailure extends ApiError {
  readonly receiptId: string;
  readonly conversationId: string;
  readonly userMessageId: string;

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string | null,
    path: string,
    identity: { receiptId: string; conversationId: string; userMessageId: string },
  ) {
    super(status, code, message, requestId, path);
    this.name = "ChatTerminalFailure";
    this.receiptId = identity.receiptId;
    this.conversationId = identity.conversationId;
    this.userMessageId = identity.userMessageId;
  }
}

/** The earlier request with this key is still unresolved on the server; nothing is resent. */
export class ChatReplyPending extends ApiError {
  readonly conversationId: string | null;
  readonly userMessageId: string | null;

  constructor(path: string, conversationId: string | null, userMessageId: string | null) {
    super(202, "CHAT_REPLY_PENDING", "The earlier request is still unresolved on the server and will not be sent again.", null, path);
    this.name = "ChatReplyPending";
    this.conversationId = conversationId;
    this.userMessageId = userMessageId;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function positiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function assertWellFormed(message: ChatMessage): void {
  if (!isRecord(message)
    || !nonEmptyString(message.id)
    || !positiveInteger(message.ordinal)
    || (message.role !== "user" && message.role !== "assistant")
    || typeof message.content !== "string") {
    throw new ChatIdentityConflict("A chat message record is missing its server identity.");
  }
}

/**
 * Merge two lists of server message records by stable identity.
 *
 * Records with the same `id` are one message and must agree on role, content and ordinal; two
 * different ids may never share an ordinal. The result is ordered by ordinal. Content, position
 * and list length are never used to decide that two records are the same message. Extra display
 * fields of a later duplicate (for example a disclaimer) are kept alongside the earlier record.
 */
export function mergeChatMessages<T extends ChatMessage>(existing: readonly T[], incoming: readonly T[]): T[] {
  const byId = new Map<string, T>();
  const byOrdinal = new Map<number, string>();
  for (const record of [...existing, ...incoming]) {
    assertWellFormed(record);
    const known = byId.get(record.id);
    if (known) {
      if (known.role !== record.role || known.content !== record.content || known.ordinal !== record.ordinal) {
        throw new ChatIdentityConflict(`The server returned conflicting records for chat message ${record.id}.`);
      }
      byId.set(record.id, { ...known, ...record });
      continue;
    }
    const occupant = byOrdinal.get(record.ordinal);
    if (occupant !== undefined) {
      throw new ChatIdentityConflict(`Chat messages ${occupant} and ${record.id} claim the same position.`);
    }
    byId.set(record.id, record);
    byOrdinal.set(record.ordinal, record.id);
  }
  return [...byId.values()].sort((left, right) => left.ordinal - right.ordinal);
}

/** The two messages a completion response contributes. The user text is the request's own text. */
export function completionMessages(
  response: ChatSendResponse,
  userContent: string,
): Array<ChatMessage & { disclaimer?: string }> {
  return [
    { id: response.user_message_id, ordinal: response.user_ordinal, role: "user", content: userContent },
    {
      id: response.assistant_message_id,
      ordinal: response.assistant_ordinal,
      role: "assistant",
      content: response.reply,
      disclaimer: response.disclaimer,
    },
  ];
}

type ErrorFactory = (status: number, body: unknown, path: string) => ApiError | null;

async function requestJson<T>(
  path: string,
  init: RequestInit,
  credentials: SessionCredentials,
  signal?: AbortSignal,
  errorFactory?: ErrorFactory,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  headers.set("X-Session-ID", credentials.session_id);
  headers.set("X-Session-Token", credentials.capability_token);

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) throw error;
    throw new ApiError(0, "NETWORK_UNAVAILABLE", "The server could not be reached. Check the connection and retry.", null, path);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const special = errorFactory?.(response.status, body, path);
    if (special) throw special;
    const outer = isRecord(body) ? body : {};
    const detail = isRecord(outer.detail) ? outer.detail : {};
    const error = (outer.error ?? detail.error ?? outer.detail ?? {}) as Record<string, unknown>;
    throw new ApiError(
      response.status,
      typeof error.code === "string" ? error.code : "REQUEST_FAILED",
      typeof error.message === "string" ? error.message : "The chat request failed.",
      typeof error.request_id === "string" ? error.request_id : null,
      path,
    );
  }

  return body as T;
}

function terminalFailureFactory(requestedConversationId: string | null): ErrorFactory {
  return (status, body, path) => {
    if (status < 400 || !isRecord(body) || body.status !== "FAILED") return null;
    const error = isRecord(body.error) ? body.error : null;
    if (!error
      || !nonEmptyString(body.receipt_id)
      || !nonEmptyString(body.conversation_id)
      || !nonEmptyString(body.user_message_id)
      || typeof error.code !== "string") return null;
    // A failure for some other conversation is not evidence about this request.
    if (requestedConversationId !== null && body.conversation_id !== requestedConversationId) return null;
    return new ChatTerminalFailure(
      status,
      error.code,
      typeof error.message === "string" ? error.message : "The chat request failed.",
      typeof error.request_id === "string" ? error.request_id : null,
      path,
      { receiptId: body.receipt_id, conversationId: body.conversation_id, userMessageId: body.user_message_id },
    );
  };
}

function parseCompletion(body: unknown, requestedConversationId: string | null, path: string): ChatSendResponse {
  const invalid = () => new ApiError(502, "INVALID_CHAT_RESPONSE", "The server returned an incomplete chat response.", null, path);
  if (!isRecord(body)
    || !nonEmptyString(body.conversation_id)
    || !nonEmptyString(body.message_id)
    || !nonEmptyString(body.receipt_id)
    || !nonEmptyString(body.user_message_id)
    || !nonEmptyString(body.assistant_message_id)
    || !positiveInteger(body.user_ordinal)
    || !positiveInteger(body.assistant_ordinal)
    || body.status !== "COMPLETED"
    || typeof body.reply !== "string"
    || typeof body.disclaimer !== "string"
    || !isRecord(body.usage)) throw invalid();
  if (body.message_id !== body.assistant_message_id
    || body.user_message_id === body.assistant_message_id
    || body.assistant_ordinal <= body.user_ordinal
    || (requestedConversationId !== null && body.conversation_id !== requestedConversationId)) throw invalid();
  return body as unknown as ChatSendResponse;
}

function parseConversation(value: unknown, expectedId: string): ChatConversation {
  const path = `/api/v1/chat/conversations/${expectedId}`;
  if (!isRecord(value) || value.conversation_id !== expectedId || !Array.isArray(value.messages)) {
    throw new ApiError(502, "INVALID_CHAT_RESPONSE", "The server returned an invalid conversation.", null, path);
  }
  const messages = value.messages.map((item): ChatMessage => {
    if (!isRecord(item)
      || (item.role !== "user" && item.role !== "assistant")
      || typeof item.content !== "string"
      || !nonEmptyString(item.id)
      || !positiveInteger(item.ordinal)) {
      throw new ApiError(502, "INVALID_CHAT_RESPONSE", "The server returned an invalid conversation message.", null, path);
    }
    return { id: item.id, ordinal: item.ordinal, role: item.role, content: item.content };
  });
  // Reject duplicate or conflicting records before any caller sees the list.
  return { conversation_id: expectedId, messages: mergeChatMessages([], messages) };
}

export const chatApi = {
  async sendMessage(
    prompt: string,
    idempotencyKey: string,
    conversationId: string | null,
    credentials: SessionCredentials,
    signal?: AbortSignal,
  ): Promise<ChatSendResponse> {
    const path = "/api/v1/chat/messages";
    const body = await requestJson<unknown>(path, {
      method: "POST",
      body: JSON.stringify({ prompt, idempotency_key: idempotencyKey, conversation_id: conversationId }),
    }, credentials, signal, terminalFailureFactory(conversationId));
    if (isRecord(body) && body.status === "PENDING") {
      throw new ChatReplyPending(
        path,
        nonEmptyString(body.conversation_id) ? body.conversation_id : null,
        nonEmptyString(body.user_message_id) ? body.user_message_id : nonEmptyString(body.message_id) ? body.message_id : null,
      );
    }
    return parseCompletion(body, conversationId, path);
  },

  async getConversation(
    conversationId: string,
    credentials: SessionCredentials,
    signal?: AbortSignal,
  ): Promise<ChatConversation> {
    const path = `/api/v1/chat/conversations/${encodeURIComponent(conversationId)}`;
    const body = await requestJson<unknown>(path, { method: "GET" }, credentials, signal);
    return parseConversation(body, conversationId);
  },
};
