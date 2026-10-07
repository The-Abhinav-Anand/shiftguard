import React, { useState } from "react";
import type { AgentRequestRecord, AgentStatus, ToolTraceEntry } from "../api/agent";

interface RecoveryIntentView {
  ownerSessionId: string;
  prompt: string;
  idempotencyKey: string;
  requestId?: string;
  activeJobId?: string;
  phase: string;
}

interface AgentPanelProps {
  agentStatus: AgentStatus | null;
  activeRequest: AgentRequestRecord | null;
  recoveryIntent?: RecoveryIntentView | null;
  storageError?: string | null;
  isSubmitting: boolean;
  error: string | null;
  sessionExpired?: boolean;
  canRetry?: boolean;
  onSubmitQuery: (prompt: string) => void;
  onRetryQuery?: () => void;
  onReconnect?: () => void;
  onSelectExperiment?: (experimentId: string) => void;
  onClear: () => void;
}

const PUBLIC_ERROR_CODE = /^[A-Z0-9_]{1,48}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function recordedText(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "Not recorded";
}

function recordedCount(value: unknown): number | "Not recorded" {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : "Not recorded";
}

function recordedCounts(value: unknown): string {
  if (!isRecord(value)) return "Not recorded";
  const entries = Object.entries(value);
  if (!entries.length || entries.some(([, count]) => recordedCount(count) === "Not recorded")) {
    return "Not recorded";
  }
  return entries.map(([name, count]) => `${name}: ${count}`).join(", ");
}

function displayToolError(error: ToolTraceEntry["error"]): string | null {
  if (typeof error === "string") {
    return error.trim().slice(0, 304) || null;
  }
  if (!error) return null;

  const code = typeof error.code === "string" && PUBLIC_ERROR_CODE.test(error.code)
    ? error.code
    : "REQUEST_FAILED";
  const message = typeof error.message === "string"
    ? error.message.trim().slice(0, 256)
    : "";
  return `${code}: ${message || "The operation failed."}`;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({
  agentStatus,
  activeRequest,
  recoveryIntent,
  storageError,
  isSubmitting,
  error,
  sessionExpired,
  canRetry,
  onSubmitQuery,
  onRetryQuery,
  onReconnect,
  onSelectExperiment,
  onClear,
}) => {
  const [promptText, setPromptText] = useState("");
  const [showTrace, setShowTrace] = useState(true);

  const isConfigured = agentStatus?.enabled && agentStatus?.available;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptText.trim() || isSubmitting) return;
    onSubmitQuery(promptText.trim());
  };

  const finalResponse = activeRequest?.final_response;
  const fallbackAnalysis = finalResponse?.fallback_analysis;
  const fallbackEntries = isRecord(fallbackAnalysis) ? Object.entries(fallbackAnalysis) : [];
  const toolTrace = activeRequest?.tool_trace || [];
  const status = activeRequest?.status;

  return (
    <section className="agent-panel" aria-label="Nemotron Research Assistant">
      <div className="agent-panel-header">
        <div className="agent-title-row">
          <h2 className="agent-heading">Nemotron Calibration Assistant</h2>
          <span
            className={`agent-status-badge ${isConfigured ? "badge-online" : "badge-offline"}`}
            aria-live="polite"
          >
            {!agentStatus?.enabled ? "Assistant paused" : !agentStatus.available ? "Provider unavailable" : (agentStatus.provider_kind === "scripted" ? "Scripted Test Harness" : "Nemotron-3_5-Lightning Active")}
          </span>
          {agentStatus?.provider_kind === "scripted" && (
            <span
              id="scripted-mode-badge"
              className="badge-scripted"
              style={{
                background: "#4a3b89",
                color: "#fff",
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "0.8rem",
                marginLeft: "8px",
                fontWeight: 600,
              }}
            >
              [Scripted Test Mode]
            </span>
          )}
        </div>
        <p className="agent-subtitle">
          Natural-language workflow grounded in deterministic verified records (Bank marketing, seed 31001).
        </p>
      </div>

      {sessionExpired && (
        <div className="agent-notice notice-session-expired" style={{ borderColor: "#f59e0b" }}>
          <span className="notice-icon">⚠️</span>
          <div>
            <strong>Session Expired:</strong> Your capability credentials are expired or invalid.
            {onReconnect && (
              <button
                id="agent-reconnect-btn"
                type="button"
                className="btn btn-warning"
                onClick={onReconnect}
                style={{ marginLeft: "12px", padding: "4px 12px" }}
              >
                Reconnect Session
              </button>
            )}
          </div>
        </div>
      )}

      {!isConfigured && !sessionExpired && (
        <div className="agent-notice notice-offline" role="status">
          <span className="notice-icon">ℹ</span>
          <div>
            {!agentStatus?.enabled ? (
              <><strong>Assistant paused:</strong> Paid inference is paused. Manual presets and saved results are available.</>
            ) : (
              <><strong>Provider unavailable:</strong> The assistant is enabled, but its provider is unavailable. Paid inference cannot run. Manual presets and saved results are available.</>
            )}
          </div>
        </div>
      )}

      {/* Query Input Form */}
      <form onSubmit={handleSubmit} className="agent-form">
        <label htmlFor="agent-prompt" className="agent-input-label">
          Inquiry or Instruction:
        </label>
        <div className="agent-input-group">
          <textarea
            id="agent-prompt"
            name="prompt"
            className="agent-textarea"
            rows={2}
            placeholder="Read-only: Inspect bank dataset or ask about published results. Run commands: Run bank-outage-50, Run bank-stress, or Run bank-baseline."
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            disabled={isSubmitting || !isConfigured || sessionExpired || Boolean(storageError)}
            aria-disabled={isSubmitting || !isConfigured || sessionExpired || Boolean(storageError)}
          />
          <div className="agent-button-bar">
            <button
              id="agent-submit-btn"
              type="submit"
              className="btn btn-primary agent-submit-btn"
              disabled={isSubmitting || !promptText.trim() || !isConfigured || sessionExpired || Boolean(storageError)}
            >
              {isSubmitting ? "Running..." : "Submit Query"}
            </button>
            {canRetry && onRetryQuery && (
              <button
                id="agent-retry-btn"
                type="button"
                className="btn btn-warning"
                onClick={onRetryQuery}
                disabled={isSubmitting || sessionExpired || Boolean(storageError)}
              >
                Retry Request
              </button>
            )}
            {(activeRequest || recoveryIntent || storageError) && (
              <button
                id="agent-clear-btn"
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setPromptText("");
                  onClear();
                }}
              >
                Clear
              </button>
            )}
          </div>
        </div>
      </form>

      {recoveryIntent && (
        <section className="agent-active-card" id="agent-recovery-card" aria-label="Saved inquiry recovery">
          <div className="agent-card-header">
            <strong>Saved inquiry recovery</strong>
            <span className={`status-pill status-${recoveryIntent.phase}`}>{recoveryIntent.phase.replaceAll("_", " ")}</span>
          </div>
          <p><strong>Original prompt:</strong> {recoveryIntent.prompt}</p>
          <p><strong>Original request key:</strong> <code>{recoveryIntent.idempotencyKey}</code></p>
          <p><strong>Owning session:</strong> <code>{recoveryIntent.ownerSessionId}</code></p>
          {recoveryIntent.requestId && <p><strong>Accepted request:</strong> <code>{recoveryIntent.requestId}</code></p>}
          {recoveryIntent.activeJobId && <p><strong>Background job:</strong> <code>{recoveryIntent.activeJobId}</code></p>}
        </section>
      )}

      {storageError && (
        <div className="agent-notice notice-error" id="agent-storage-error" role="alert">
          <strong>Recovery storage error:</strong> {storageError}
        </div>
      )}

      {/* Error Announcement */}
      {error && (
        <div className="agent-notice notice-error" role="alert" aria-live="assertive">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Active Request Details */}
      {activeRequest && (
        <div className="agent-active-card">
          <div className="agent-card-header">
            <div className="agent-counters">
              <span className="badge badge-meta">Turn: {activeRequest.turn_count}/6</span>
              <span className="badge badge-meta">Tool Calls: {activeRequest.call_count}/8</span>
              {activeRequest.repair_count > 0 && (
                <span className="badge badge-warning">Repairs: {activeRequest.repair_count}/1</span>
              )}
            </div>
            <span className={`status-pill status-${status?.toLowerCase()}`}>{status}</span>
          </div>

          {/* Job Waiting State */}
          {status === "WAITING_FOR_JOB" && (
            <div className="agent-waiting-state" role="status" aria-live="polite">
              <div className="spinner" aria-hidden="true" />
              <div>
                <strong>Waiting for background execution:</strong> Job <code>{activeRequest.active_job_id}</code> is
                running in the worker queue. Resuming automatically when complete.
              </div>
            </div>
          )}

          {/* Grounded Final Response */}
          {finalResponse && (
            <div className="agent-final-response">
              <h3 className="final-title">{finalResponse.title}</h3>
              <p className="final-summary">{finalResponse.summary}</p>

              {/* Claims Table */}
              {finalResponse.claims && finalResponse.claims.length > 0 && (
                <div className="claims-section">
                  <h4 className="claims-heading">Empirical Observations</h4>
                  <table className="claims-table" aria-label="Analytical Claims">
                    <thead>
                      <tr>
                        <th>Condition ID</th>
                        <th>Observation</th>
                        <th>Metric</th>
                        <th>Value</th>
                        <th>Delta vs Raw</th>
                        <th>Direction</th>
                      </tr>
                    </thead>
                    <tbody>
                      {finalResponse.claims.map((claim, idx) => (
                        <tr key={idx}>
                          <td><code>{recordedText(claim.condition_id)}</code></td>
                          <td>{claim.description}</td>
                          <td><code>{claim.metric_name || "—"}</code></td>
                          <td>{claim.value !== undefined && claim.value !== null ? claim.value.toFixed(4) : "—"}</td>
                          <td>
                            {claim.delta !== undefined && claim.delta !== null
                              ? `${claim.delta > 0 ? "+" : ""}${claim.delta.toFixed(4)}`
                              : "—"}
                          </td>
                          <td>
                            <span className={`direction-tag direction-${claim.direction || "neutral"}`}>
                              {claim.direction || "neutral"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Fallback Analysis */}
              <div className="fallback-section">
                <h4 className="fallback-heading">Fallback & Diagnostics</h4>
                {fallbackEntries.length === 0 ? (
                  <p><strong>Affected fallback rows:</strong> Not recorded</p>
                ) : fallbackEntries.map(([conditionKey, value]) => {
                  const condition = isRecord(value) ? value : {};
                  const diagnostics = isRecord(condition.sparse_bin_diagnostics)
                    ? condition.sparse_bin_diagnostics
                    : {};
                  return (
                    <div className="fallback-condition" key={conditionKey}>
                      <p><strong>Condition ID:</strong> <code>{recordedText(condition.condition_id)}</code></p>
                      <p><strong>Requested method:</strong> {recordedText(condition.requested_method)}</p>
                      <p><strong>Resolved method:</strong> {recordedText(condition.resolved_method)}</p>
                      <p><strong>Fallback reason:</strong> {recordedText(condition.fallback_reason)}</p>
                      <p><strong>Affected fallback rows:</strong> {recordedCount(diagnostics.affected_fallback_rows)}</p>
                      <p><strong>Sparse prediction failures:</strong> {recordedCount(diagnostics.sparse_prediction_failures)}</p>
                      <p><strong>Resolution counts:</strong> {recordedCounts(diagnostics.resolution_counts)}</p>
                    </div>
                  );
                })}
              </div>

              {/* Evidence References */}
              {finalResponse.evidence_references && finalResponse.evidence_references.length > 0 && (
                <div className="evidence-section">
                  <span className="evidence-label">Published Experiments:</span>
                  <div className="evidence-links">
                    {finalResponse.evidence_references.map((expId) => (
                      <button
                        key={expId}
                        id={`evidence-link-${expId}`}
                        type="button"
                        className="btn btn-link evidence-button"
                        onClick={() => onSelectExperiment?.(expId)}
                        title="View detailed scientific charts and sparse-bin fallback in workbench"
                      >
                        {expId}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Single seed disclaimer */}
              <div className="agent-disclaimer">
                <small>{finalResponse.disclaimer}</small>
              </div>
            </div>
          )}

          {/* Safe Tool Trace */}
          {toolTrace.length > 0 && (
            <div className="agent-trace-section">
              <button
                type="button"
                className="trace-toggle-btn"
                onClick={() => setShowTrace(!showTrace)}
                aria-expanded={showTrace}
              >
                {showTrace ? "Hide Approved Tool Trace" : `Show Tool Trace (${toolTrace.length})`}
              </button>
              {showTrace && (
                <div className="trace-list" role="log" aria-label="Tool Trace">
                  {toolTrace.map((entry: ToolTraceEntry) => {
                    const safeError = displayToolError(entry.error);
                    return (
                      <div key={entry.ordinal} className="trace-item">
                        <div className="trace-header">
                          <span className="trace-ordinal">#{entry.ordinal}</span>
                          <code className="trace-name">{entry.tool_name}</code>
                          <span className={`trace-status status-${entry.status.toLowerCase()}`}>{entry.status}</span>
                          {entry.job_id && <span className="trace-job">Job: {entry.job_id}</span>}
                        </div>
                        {safeError && <div className="trace-error">{safeError}</div>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
