import { useEffect, useState, type FormEvent } from "react";
import type { SessionCredentials } from "../api/types";
import { useChat } from "../hooks/useChat";
import "../styles/general-chat.css";

interface GeneralChatPanelProps {
  credentials: SessionCredentials | null;
  enabled: boolean;
  disabledReason: string | null;
  ordinaryBudget?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nonNegativeCount(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function budgetSummary(value: unknown): string | null {
  if (!isRecord(value)) return null;
  const callsUsedRaw = nonNegativeCount(value.calls_used);
  const callsRemainingRaw = nonNegativeCount(value.calls_remaining);
  const tokensUsedRaw = nonNegativeCount(value.tokens_committed);
  const tokensRemainingRaw = nonNegativeCount(value.tokens_remaining);
  const callsUsed = callsUsedRaw ?? (callsRemainingRaw !== null && callsRemainingRaw <= 10 ? 10 - callsRemainingRaw : null);
  const callsRemaining = callsRemainingRaw ?? (callsUsedRaw !== null && callsUsedRaw <= 10 ? 10 - callsUsedRaw : null);
  const tokensUsed = tokensUsedRaw ?? (tokensRemainingRaw !== null && tokensRemainingRaw <= 50_000 ? 50_000 - tokensRemainingRaw : null);
  const tokensRemaining = tokensRemainingRaw ?? (tokensUsedRaw !== null && tokensUsedRaw <= 50_000 ? 50_000 - tokensUsedRaw : null);
  const details: string[] = [];
  if (callsUsed !== null && callsUsed <= 10) {
    details.push(`${callsUsed}/10 calls used${callsRemaining !== null && callsRemaining <= 10 ? ` · ${callsRemaining} remaining` : ""}`);
  }
  if (tokensUsed !== null && tokensUsed <= 50_000) {
    details.push(`${tokensUsed.toLocaleString("en-US")}/50,000 tokens committed${tokensRemaining !== null && tokensRemaining <= 50_000 ? ` · ${tokensRemaining.toLocaleString("en-US")} remaining` : ""}`);
  }
  if (value.halted === true) details.push("budget halted");
  const day = typeof value.utc_day === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value.utc_day) ? value.utc_day : null;
  return `Shared UTC-day paid allowance${day ? ` · ${day}` : ""}: ${details.length ? details.join(" · ") : "allowance details unavailable"}.`;
}

export function GeneralChatPanel({ credentials, enabled, disabledReason, ordinaryBudget }: GeneralChatPanelProps) {
  const chat = useChat({ credentials, enabled });
  const [draft, setDraft] = useState("");
  const budget = budgetSummary(ordinaryBudget);

  useEffect(() => {
    if (chat.pending) setDraft(chat.pending.prompt);
    else if (!chat.isSubmitting) setDraft("");
  }, [chat.pending, chat.isSubmitting]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft.trim() || chat.pending || chat.isSubmitting || !enabled) return;
    void chat.submit(draft).then((accepted) => {
      if (accepted) setDraft("");
    });
  };

  const retryPending = () => {
    void chat.retry().then((accepted) => {
      if (accepted) setDraft("");
    });
  };

  const sendDisabled = !enabled
    || !draft.trim()
    || draft.trim().length > 4000
    || Boolean(chat.pending)
    || chat.isSubmitting
    || chat.historyLoading
    || Boolean(chat.storageError);

  return (
    <section className="general-chat" aria-labelledby="general-chat-heading">
      <header className="general-chat__header">
        <div>
          <p className="section-kicker">SEPARATE FROM RESULTS ASSISTANT</p>
          <h2 id="general-chat-heading">General chat</h2>
          <p>Ask a general question in a direct conversation.</p>
        </div>
        <span className={`general-chat__status${enabled ? " general-chat__status--ready" : ""}`} role="status">
          {enabled ? "Ready" : disabledReason ?? "General chat is unavailable."}
        </span>
      </header>

      {budget && <p className="general-chat__budget" role="status">{budget}</p>}
      {chat.historyLoading && <p className="general-chat__notice" role="status">Loading saved conversation…</p>}
      {chat.historyError && <p className="general-chat__notice" role="status">{chat.historyError}</p>}
      {chat.storageError && <p className="general-chat__error" role="alert">{chat.storageError}</p>}

      <ol className="general-chat__messages" aria-label="General chat conversation" aria-live="polite" aria-relevant="additions text">
        {chat.messages.length === 0 && !chat.historyLoading && (
          <li className="general-chat__empty">Your conversation will appear here after you send a message.</li>
        )}
        {chat.messages.map((message) => (
          <li
            className={`general-chat__message general-chat__message--${message.role}${message.local ? " general-chat__message--local" : ""}${message.failure ? " general-chat__message--failed" : ""}`}
            key={message.key}
            data-message-id={message.id ?? undefined}
            data-ordinal={message.ordinal ?? undefined}
            data-local={message.local}
          >
            <p className="general-chat__speaker">
              {message.role === "user" ? "You" : "AI response · not verified experiment evidence"}
            </p>
            <p className="general-chat__content">{message.content}</p>
            {message.role === "assistant" && message.disclaimer && (
              <p className="general-chat__disclaimer">{message.disclaimer}</p>
            )}
            {message.local && !message.failure && (
              <p className="general-chat__state">
                {message.local === "sending" ? "Sending…" : "Not yet confirmed by the server"}
              </p>
            )}
            {message.failure && (
              <p className="general-chat__failure">
                No reply was recorded for this message ({message.failure.code}). It stays in the conversation.
              </p>
            )}
          </li>
        ))}
      </ol>

      {chat.error && <p className="general-chat__error" role="alert">{chat.error}</p>}
      {chat.pending && (
        <div className="general-chat__pending" role="status">
          <span>The message may have reached the server. Retry will use the same message and request key.</span>
          <button className="button button--quiet" type="button" onClick={retryPending} disabled={!enabled || chat.isSubmitting || chat.historyLoading}>
            {chat.isSubmitting ? "Sending…" : "Retry same message"}
          </button>
        </div>
      )}

      <form className="general-chat__form" onSubmit={handleSubmit}>
        <label htmlFor="general-chat-prompt">Message</label>
        <textarea
          id="general-chat-prompt"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={4000}
          rows={4}
          placeholder={enabled ? "Write a message…" : "General chat is unavailable."}
          disabled={!enabled || Boolean(chat.pending) || chat.isSubmitting || chat.historyLoading || Boolean(chat.storageError)}
        />
        <div className="general-chat__form-footer">
          <span>{draft.length}/4000</span>
          <div className="general-chat__actions">
            {(chat.conversationId || chat.pending || chat.messages.length > 0) && (
              <button className="button button--quiet" type="button" onClick={() => { chat.startNewConversation(); }} disabled={chat.isSubmitting || chat.historyLoading}>
                New conversation
              </button>
            )}
            <button className="button button--primary" type="submit" disabled={sendDisabled}>
              {chat.isSubmitting ? "Sending…" : "Send message"}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
