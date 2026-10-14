import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import {
  ChatIdentityConflict,
  ChatReplyPending,
  ChatTerminalFailure,
  chatApi,
  completionMessages,
  mergeChatMessages,
  type ChatMessage,
  type ChatSendResponse,
} from "../api/chat";
import type { SessionCredentials } from "../api/types";

const STORAGE_KEY = "shiftguard_general_chat_v1";
const STORAGE_VERSION = 2;
const MAX_HISTORY_MESSAGES = 100;
const MAX_FAILED_TURNS = 20;
const MAX_PROMPT_LENGTH = 4000;
const STORAGE_ERROR = "Chat state could not be saved in this tab. The message was not sent.";

/** A server-persisted message plus display-only extras the history endpoint does not carry. */
export interface StoredChatMessage extends ChatMessage {
  disclaimer?: string;
}

/** A turn the server definitively refused after the model returned; its user message stays in history. */
export interface FailedChatTurn {
  receiptId: string;
  userMessageId: string;
  prompt: string;
  code: string;
  message: string;
}

export interface PendingChatMessage {
  ownerSessionId: string;
  prompt: string;
  idempotencyKey: string;
  conversationId: string | null;
  /** Highest server ordinal known when the message was submitted; only used to recognise its own row. */
  baseOrdinal: number;
  /** Learned from a completion or a PENDING receipt; never inferred. */
  userMessageId: string | null;
}

/** What the panel renders: confirmed server records, plus clearly local, unconfirmed entries. */
export interface DisplayChatMessage {
  key: string;
  id: string | null;
  ordinal: number | null;
  role: "user" | "assistant";
  content: string;
  disclaimer?: string;
  /** Local-only entry for a request whose server row has not been seen yet. */
  local?: "sending" | "unconfirmed";
  failure?: { code: string; message: string };
}

interface ChatState {
  conversationId: string | null;
  messages: StoredChatMessage[];
  failedTurns: FailedChatTurn[];
  pending: PendingChatMessage | null;
  isSubmitting: boolean;
  historyLoading: boolean;
  error: string | null;
  historyError: string | null;
  storageError: string | null;
}

interface StoredChatState {
  version: typeof STORAGE_VERSION;
  ownerSessionId: string;
  conversationId: string | null;
  messages: StoredChatMessage[];
  failedTurns: FailedChatTurn[];
  pending: PendingChatMessage | null;
}

function emptyState(): ChatState {
  return {
    conversationId: null,
    messages: [],
    failedTurns: [],
    pending: null,
    isSubmitting: false,
    historyLoading: false,
    error: null,
    historyError: null,
    storageError: null,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function positiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

/** Only records that carry a server identity survive; older id-less history is refetched instead. */
function identifiedMessages(value: unknown): StoredChatMessage[] {
  if (!Array.isArray(value)) return [];
  const candidates = value.filter((item): item is StoredChatMessage => (
    isRecord(item)
    && typeof item.id === "string"
    && item.id.length > 0
    && positiveInteger(item.ordinal)
    && (item.role === "user" || item.role === "assistant")
    && typeof item.content === "string"
    && (item.disclaimer === undefined || typeof item.disclaimer === "string")
  ));
  try {
    return mergeChatMessages([], candidates).slice(-MAX_HISTORY_MESSAGES);
  } catch {
    // Contradictory local copies are discarded; the authorized server history replaces them.
    return [];
  }
}

function parseFailedTurns(value: unknown): FailedChatTurn[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is FailedChatTurn => (
    isRecord(item)
    && typeof item.receiptId === "string" && item.receiptId.length > 0
    && typeof item.userMessageId === "string" && item.userMessageId.length > 0
    && typeof item.prompt === "string"
    && typeof item.code === "string"
    && typeof item.message === "string"
  )).slice(-MAX_FAILED_TURNS);
}

function parsePending(value: unknown, ownerSessionId: string): PendingChatMessage | null {
  if (!isRecord(value)
    || value.ownerSessionId !== ownerSessionId
    || typeof value.prompt !== "string"
    || !value.prompt.trim()
    || value.prompt.length > MAX_PROMPT_LENGTH
    || typeof value.idempotencyKey !== "string"
    || !value.idempotencyKey
    || !(typeof value.conversationId === "string" || value.conversationId === null)) return null;
  // Earlier builds stored a message count; it is only a display hint for recognising the pending row.
  const hint = value.baseOrdinal ?? value.previousMessageCount;
  const baseOrdinal = typeof hint === "number" && Number.isSafeInteger(hint) && hint >= 0 ? hint : 0;
  return {
    ownerSessionId,
    prompt: value.prompt,
    idempotencyKey: value.idempotencyKey,
    conversationId: value.conversationId,
    baseOrdinal,
    userMessageId: typeof value.userMessageId === "string" && value.userMessageId ? value.userMessageId : null,
  };
}

function readStoredState(ownerSessionId: string): StoredChatState | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || value.ownerSessionId !== ownerSessionId) return null;
    if (value.version !== 1 && value.version !== STORAGE_VERSION) return null;
    return {
      version: STORAGE_VERSION,
      ownerSessionId,
      conversationId: typeof value.conversationId === "string" ? value.conversationId : null,
      // Version 1 history has no server identities, so it is dropped and refetched from the server.
      messages: value.version === 1 ? [] : identifiedMessages(value.messages),
      failedTurns: value.version === 1 ? [] : parseFailedTurns(value.failedTurns),
      pending: parsePending(value.pending, ownerSessionId),
    };
  } catch {
    return null;
  }
}

function storeState(ownerSessionId: string, state: ChatState): boolean {
  try {
    const stored: StoredChatState = {
      version: STORAGE_VERSION,
      ownerSessionId,
      conversationId: state.conversationId,
      messages: state.messages.slice(-MAX_HISTORY_MESSAGES),
      failedTurns: state.failedTurns.slice(-MAX_FAILED_TURNS),
      pending: state.pending,
    };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
    return true;
  } catch {
    return false;
  }
}

function makeIdempotencyKey(): string {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) return `[${error.code}] ${error.message}`;
  if (error instanceof ChatIdentityConflict) return `[${error.code}] ${error.message}`;
  return error instanceof Error ? error.message : "The chat request could not be completed.";
}

function highestOrdinal(messages: readonly ChatMessage[]): number {
  return messages.reduce((highest, message) => Math.max(highest, message.ordinal), 0);
}

/** The pending message's own server row, recognised by a learned id or by its exact expected position. */
function findPendingUserRow(state: ChatState, pending: PendingChatMessage): StoredChatMessage | undefined {
  const failedIds = new Set(state.failedTurns.map((turn) => turn.userMessageId));
  return state.messages.find((message) => {
    if (message.role !== "user" || failedIds.has(message.id)) return false;
    if (pending.userMessageId) return message.id === pending.userMessageId;
    return message.ordinal === pending.baseOrdinal + 1 && message.content === pending.prompt;
  });
}

/** Merge a completion's two records into the known history, or throw if the server contradicts itself. */
function reconcileCompletion(
  current: ChatState,
  pending: PendingChatMessage,
  response: ChatSendResponse,
): StoredChatMessage[] {
  if ((pending.conversationId !== null && response.conversation_id !== pending.conversationId)
    || (current.conversationId !== null && response.conversation_id !== current.conversationId)) {
    throw new ChatIdentityConflict("The reply belongs to a different conversation than this message.");
  }
  const known = current.messages.find((message) => message.id === response.user_message_id);
  return mergeChatMessages(
    current.messages,
    completionMessages(response, known?.content ?? pending.prompt),
  ).slice(-MAX_HISTORY_MESSAGES);
}

export function useChat({ credentials, enabled }: { credentials: SessionCredentials | null; enabled: boolean }) {
  const [state, setState] = useState<ChatState>(emptyState);
  const stateRef = useRef(state);
  const credentialsRef = useRef(credentials);
  credentialsRef.current = credentials;
  const ownerSessionIdRef = useRef<string | null>(credentials?.session_id ?? null);
  ownerSessionIdRef.current = credentials?.session_id ?? null;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const activeSessionRef = useRef<string | null>(null);
  const initializedSessionRef = useRef(false);
  const epochRef = useRef(0);
  const inFlightRef = useRef(false);
  const controllersRef = useRef(new Set<AbortController>());

  const commit = useCallback((next: ChatState) => {
    stateRef.current = next;
    setState(next);
  }, []);

  /** Fetch authorized server history and merge it into the known records by identity. */
  const loadHistory = useCallback((conversationId: string, ownerSessionId: string, epoch: number) => {
    const currentCredentials = credentialsRef.current;
    if (!currentCredentials || currentCredentials.session_id !== ownerSessionId) return;
    const controller = new AbortController();
    controllersRef.current.add(controller);
    void chatApi.getConversation(conversationId, currentCredentials, controller.signal).then((conversation) => {
      if (epochRef.current !== epoch || credentialsRef.current?.session_id !== ownerSessionId) return;
      const current = stateRef.current;
      if (current.conversationId !== conversationId) return;
      const messages = mergeChatMessages(current.messages, conversation.messages).slice(-MAX_HISTORY_MESSAGES);
      const next: ChatState = { ...current, messages, historyLoading: false, historyError: null };
      if (storeState(ownerSessionId, next)) commit(next);
      else commit({ ...next, historyError: "Conversation history loaded but could not be saved in this tab." });
    }).catch((error: unknown) => {
      if (epochRef.current !== epoch || controller.signal.aborted) return;
      commit({
        ...stateRef.current,
        historyLoading: false,
        historyError: `Saved conversation history could not be refreshed. ${describeError(error)}`,
      });
    }).finally(() => controllersRef.current.delete(controller));
  }, [commit]);

  useEffect(() => {
    const ownerSessionId = credentials?.session_id ?? null;
    const previousSessionId = activeSessionRef.current;
    const hadSession = initializedSessionRef.current;
    initializedSessionRef.current = true;
    activeSessionRef.current = ownerSessionId;
    const epoch = ++epochRef.current;
    inFlightRef.current = false;
    for (const controller of controllersRef.current) controller.abort();
    controllersRef.current.clear();
    const cleanup = () => {
      for (const controller of controllersRef.current) controller.abort();
      controllersRef.current.clear();
    };

    if (hadSession && previousSessionId !== ownerSessionId) {
      try { window.sessionStorage.removeItem(STORAGE_KEY); } catch { /* session reset still clears in-memory state */ }
      commit(emptyState());
      return cleanup;
    }
    if (!ownerSessionId || !credentials) {
      commit(emptyState());
      return cleanup;
    }

    const restored = readStoredState(ownerSessionId);
    if (!restored) {
      commit(emptyState());
      return cleanup;
    }

    commit({
      ...emptyState(),
      conversationId: restored.conversationId,
      messages: restored.messages,
      failedTurns: restored.failedTurns,
      pending: restored.pending,
      historyLoading: Boolean(restored.conversationId),
    });
    if (restored.conversationId) loadHistory(restored.conversationId, ownerSessionId, epoch);

    return cleanup;
  }, [credentials?.session_id, commit, loadHistory]);

  const executePending = useCallback(async (pending: PendingChatMessage): Promise<boolean> => {
    const currentCredentials = credentialsRef.current;
    const ownerSessionId = pending.ownerSessionId;
    const epoch = epochRef.current;
    if (!enabledRef.current || !currentCredentials || currentCredentials.session_id !== ownerSessionId || inFlightRef.current) return false;

    inFlightRef.current = true;
    commit({ ...stateRef.current, isSubmitting: true, error: null, historyError: null });
    const controller = new AbortController();
    controllersRef.current.add(controller);
    try {
      const response = await chatApi.sendMessage(
        pending.prompt,
        pending.idempotencyKey,
        pending.conversationId,
        currentCredentials,
        controller.signal,
      );
      if (epochRef.current !== epoch || credentialsRef.current?.session_id !== ownerSessionId) return false;

      const current = stateRef.current;
      const messages = reconcileCompletion(current, pending, response);
      const completed: ChatState = {
        ...current,
        conversationId: response.conversation_id,
        messages,
        pending: null,
        isSubmitting: false,
        error: null,
        historyError: null,
        storageError: null,
      };
      if (!storeState(ownerSessionId, completed)) {
        // Show the confirmed reply, but keep the original request identity so a retry replays it.
        commit({
          ...completed,
          pending: { ...pending, userMessageId: response.user_message_id },
          error: "The reply arrived, but its completion could not be saved. Retry the same message to keep the original request identity.",
          storageError: STORAGE_ERROR,
        });
        return false;
      }
      commit(completed);
      return true;
    } catch (error) {
      if (epochRef.current !== epoch || controller.signal.aborted) return false;
      const current = stateRef.current;
      let failed: ChatState;
      if (error instanceof ChatTerminalFailure
        && (pending.conversationId === null || error.conversationId === pending.conversationId)
        && (current.conversationId === null || error.conversationId === current.conversationId)) {
        // A definite, replayable failure: the key is spent, the user message stays in the
        // conversation, and the conversation remains usable for the next explicit message.
        const turn: FailedChatTurn = {
          receiptId: error.receiptId,
          userMessageId: error.userMessageId,
          prompt: pending.prompt,
          code: error.code,
          message: error.message,
        };
        failed = {
          ...current,
          conversationId: error.conversationId,
          failedTurns: [...current.failedTurns.filter((item) => item.receiptId !== turn.receiptId), turn].slice(-MAX_FAILED_TURNS),
          pending: null,
          isSubmitting: false,
          error: `${describeError(error)} Your message was kept; send a new message to continue.`,
        };
        const stored = storeState(ownerSessionId, failed);
        commit(stored ? failed : { ...failed, storageError: STORAGE_ERROR });
        loadHistory(error.conversationId, ownerSessionId, epoch);
        return false;
      }
      failed = {
        ...current,
        isSubmitting: false,
        error: describeError(error),
        pending: error instanceof ChatReplyPending && error.userMessageId && current.pending && !current.pending.userMessageId
          ? { ...current.pending, userMessageId: error.userMessageId }
          : current.pending,
      };
      if (storeState(ownerSessionId, failed)) commit(failed);
      else commit({ ...failed, storageError: STORAGE_ERROR });
      return false;
    } finally {
      controllersRef.current.delete(controller);
      if (epochRef.current === epoch) inFlightRef.current = false;
    }
  }, [commit, loadHistory]);

  const submit = useCallback(async (prompt: string): Promise<boolean> => {
    const currentCredentials = credentialsRef.current;
    const current = stateRef.current;
    const normalizedPrompt = prompt.trim();
    if (!enabledRef.current
      || !currentCredentials
      || !normalizedPrompt
      || normalizedPrompt.length > MAX_PROMPT_LENGTH
      || current.pending
      || current.isSubmitting
      || current.historyLoading
      || current.storageError) return false;

    const pending: PendingChatMessage = {
      ownerSessionId: currentCredentials.session_id,
      prompt: normalizedPrompt,
      idempotencyKey: makeIdempotencyKey(),
      conversationId: current.conversationId,
      baseOrdinal: highestOrdinal(current.messages),
      userMessageId: null,
    };
    const next: ChatState = { ...current, pending, error: null, historyError: null };
    if (!storeState(currentCredentials.session_id, next)) {
      commit({ ...current, storageError: STORAGE_ERROR, error: STORAGE_ERROR });
      return false;
    }
    commit(next);
    return executePending(pending);
  }, [commit, executePending]);

  const retry = useCallback(async (): Promise<boolean> => {
    const pending = stateRef.current.pending;
    const currentCredentials = credentialsRef.current;
    if (!pending
      || !currentCredentials
      || pending.ownerSessionId !== currentCredentials.session_id
      || !enabledRef.current
      || stateRef.current.isSubmitting
      || stateRef.current.historyLoading) return false;
    return executePending(pending);
  }, [executePending]);

  // The server keeps the earlier conversation and any unresolved receipt; only this tab lets go of them.
  const startNewConversation = useCallback((): boolean => {
    const current = stateRef.current;
    if (!credentialsRef.current || current.isSubmitting || current.historyLoading) return false;
    try { window.sessionStorage.removeItem(STORAGE_KEY); } catch { /* the in-memory reset still applies */ }
    commit(emptyState());
    return true;
  }, [commit]);

  const messages = useMemo<DisplayChatMessage[]>(() => {
    const failedByUserId = new Map(state.failedTurns.map((turn) => [turn.userMessageId, turn]));
    const display: DisplayChatMessage[] = state.messages.map((message) => {
      const failure = failedByUserId.get(message.id);
      return {
        key: message.id,
        id: message.id,
        ordinal: message.ordinal,
        role: message.role,
        content: message.content,
        ...(message.disclaimer ? { disclaimer: message.disclaimer } : {}),
        ...(failure ? { failure: { code: failure.code, message: failure.message } } : {}),
      };
    });
    const known = new Set(state.messages.map((message) => message.id));
    for (const turn of state.failedTurns) {
      if (known.has(turn.userMessageId)) continue;
      display.push({
        key: `local:failed:${turn.receiptId}`,
        id: null,
        ordinal: null,
        role: "user",
        content: turn.prompt,
        local: "unconfirmed",
        failure: { code: turn.code, message: turn.message },
      });
    }
    if (state.pending && !findPendingUserRow(state, state.pending)) {
      display.push({
        key: `local:${state.pending.idempotencyKey}`,
        id: null,
        ordinal: null,
        role: "user",
        content: state.pending.prompt,
        local: state.isSubmitting ? "sending" : "unconfirmed",
      });
    }
    return display;
  }, [state]);

  return { ...state, messages, submit, retry, startNewConversation };
}
