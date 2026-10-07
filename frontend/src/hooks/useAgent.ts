import { useCallback, useEffect, useRef, useState } from "react";
import { agentApi, type AgentRequestRecord, type AgentStatus } from "../api/agent";
import { ApiError } from "../api/client";
import type { SessionCredentials } from "../api/types";

interface UseAgentProps {
  credentials: SessionCredentials | null;
  onExperimentSelected?: (experimentId: string) => void;
}

export type AgentIntentPhase =
  | "pending_acceptance"
  | "running"
  | "waiting_for_job"
  | "ready_to_resume"
  | "resuming"
  | "transport_error";

export type AgentRetryAction = "submit" | "reconcile" | "resume";

export interface StoredIntent {
  version: 2;
  ownerSessionId: string;
  prompt: string;
  idempotencyKey: string;
  requestId?: string;
  resumeNonce?: string;
  activeJobId?: string;
  phase: AgentIntentPhase;
  retryAction?: AgentRetryAction;
  serverStatus?: string;
  timestamp: number;
}

const SESSION_AUTH_CODES = new Set([
  "MISSING_SESSION_CREDENTIALS",
  "INVALID_SESSION_CREDENTIALS",
  "SESSION_EXPIRED",
  "INVALID_CAPABILITY_TOKEN",
]);
const TERMINAL_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED"]);
const TERMINAL_JOB_STATUSES = new Set(["completed", "failed", "cancelled"]);
const STORAGE_ERROR = "Unable to access saved agent recovery state. Clear the saved request or restore browser storage before continuing.";

function storageKey(sessionId: string): string {
  return `shiftguard_agent_intent_${sessionId}`;
}

function phaseForStatus(status: string): AgentIntentPhase {
  if (status === "WAITING_FOR_JOB") return "waiting_for_job";
  if (status === "READY_TO_RESUME") return "ready_to_resume";
  return "running";
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return `[${error.code}] ${error.message}`;
  return error instanceof Error ? error.message : "Failed to execute agent request.";
}

function parseIntent(raw: string, sessionId: string): StoredIntent {
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== "object") throw new Error("Saved agent recovery state is not an object.");
  const item = value as Record<string, unknown>;
  if (typeof item.prompt !== "string" || typeof item.idempotencyKey !== "string") {
    throw new Error("Saved agent recovery state is missing its original prompt or request key.");
  }
  if (typeof item.ownerSessionId === "string" && item.ownerSessionId !== sessionId) {
    throw new Error("Saved agent recovery state belongs to another session and was not loaded.");
  }

  const requestId = typeof item.requestId === "string" ? item.requestId : undefined;
  const rawStatus = typeof item.status === "string" ? item.status : undefined;
  const allowedPhases: AgentIntentPhase[] = [
    "pending_acceptance", "running", "waiting_for_job", "ready_to_resume", "resuming", "transport_error",
  ];
  let phase = allowedPhases.includes(item.phase as AgentIntentPhase)
    ? item.phase as AgentIntentPhase
    : requestId
      ? phaseForStatus(rawStatus ?? "RUNNING")
      : "pending_acceptance";
  if (!requestId) phase = "pending_acceptance";

  const retryAction = item.retryAction === "submit" || item.retryAction === "reconcile" || item.retryAction === "resume"
    ? item.retryAction
    : phase === "pending_acceptance"
      ? "submit"
      : phase === "resuming"
        ? "resume"
        : undefined;

  return {
    version: 2,
    ownerSessionId: sessionId,
    prompt: item.prompt,
    idempotencyKey: item.idempotencyKey,
    ...(requestId ? { requestId } : {}),
    ...(typeof item.resumeNonce === "string" && item.resumeNonce ? { resumeNonce: item.resumeNonce } : {}),
    ...(typeof item.activeJobId === "string" && item.activeJobId ? { activeJobId: item.activeJobId } : {}),
    phase,
    ...(retryAction ? { retryAction } : {}),
    ...(typeof item.serverStatus === "string" ? { serverStatus: item.serverStatus } : rawStatus ? { serverStatus: rawStatus } : {}),
    timestamp: typeof item.timestamp === "number" ? item.timestamp : Date.now(),
  };
}

export function useAgent({ credentials, onExperimentSelected }: UseAgentProps) {
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [activeRequest, setActiveRequest] = useState<AgentRequestRecord | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [recoveryIntent, setRecoveryIntent] = useState<StoredIntent | null>(null);
  const [storageError, setStorageError] = useState<string | null>(null);

  const principalId = credentials?.session_id ?? null;
  const credentialsRef = useRef(credentials);
  credentialsRef.current = credentials;
  const onExperimentSelectedRef = useRef(onExperimentSelected);
  onExperimentSelectedRef.current = onExperimentSelected;
  const intentRef = useRef<StoredIntent | null>(null);
  const activeRequestRef = useRef<AgentRequestRecord | null>(null);
  const epochRef = useRef(0);
  const mountedRef = useRef(true);
  const controllersRef = useRef(new Set<AbortController>());
  const pollTimerRef = useRef<number | null>(null);
  const operationInFlightRef = useRef(false);
  const reconcileRef = useRef<(
    intent: StoredIntent,
    currentCredentials: SessionCredentials,
    epoch: number,
    action: AgentRetryAction,
    manual: boolean,
  ) => Promise<void>>(async () => undefined);

  const isCurrent = useCallback((epoch: number, ownerSessionId: string) => (
    mountedRef.current
    && epochRef.current === epoch
    && credentialsRef.current?.session_id === ownerSessionId
  ), []);

  const invalidateOperations = useCallback(() => {
    epochRef.current += 1;
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    for (const controller of controllersRef.current) controller.abort();
    controllersRef.current.clear();
    operationInFlightRef.current = false;
    setIsSubmitting(false);
  }, []);

  const saveIntent = useCallback((intent: StoredIntent): boolean => {
    intentRef.current = intent;
    setRecoveryIntent(intent);
    try {
      window.localStorage.setItem(storageKey(intent.ownerSessionId), JSON.stringify(intent));
      setStorageError(null);
      return true;
    } catch {
      setStorageError(STORAGE_ERROR);
      return false;
    }
  }, []);

  const removeIntent = useCallback((ownerSessionId: string): boolean => {
    try {
      window.localStorage.removeItem(storageKey(ownerSessionId));
      setStorageError(null);
      return true;
    } catch {
      setStorageError(STORAGE_ERROR);
      return false;
    }
  }, []);

  const setRequest = useCallback((request: AgentRequestRecord | null) => {
    activeRequestRef.current = request;
    setActiveRequest(request);
  }, []);

  const scheduleReconcile = useCallback((intent: StoredIntent, epoch: number, delay = 1600) => {
    if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
    pollTimerRef.current = window.setTimeout(() => {
      pollTimerRef.current = null;
      const currentCredentials = credentialsRef.current;
      const currentIntent = intentRef.current;
      if (!currentCredentials || !currentIntent || currentIntent.ownerSessionId !== intent.ownerSessionId) return;
      if (!isCurrent(epoch, intent.ownerSessionId)) return;
      const action: AgentRetryAction = currentIntent.phase === "resuming"
        ? "resume"
        : currentIntent.phase === "pending_acceptance"
          ? "submit"
          : "reconcile";
      void reconcileRef.current(currentIntent, currentCredentials, epoch, action, false);
    }, delay);
  }, [isCurrent]);

  const reconcile = useCallback(async (
    intent: StoredIntent,
    currentCredentials: SessionCredentials,
    epoch: number,
    action: AgentRetryAction,
    manual: boolean,
  ) => {
    if (!isCurrent(epoch, intent.ownerSessionId) || operationInFlightRef.current) return;
    if (currentCredentials.session_id !== intent.ownerSessionId) return;
    operationInFlightRef.current = true;
    if (manual) setIsSubmitting(true);
    const controller = new AbortController();
    controllersRef.current.add(controller);

    const recoverableFailure = (failedIntent: StoredIntent, retryAction: AgentRetryAction, failure: unknown) => {
      if (!isCurrent(epoch, intent.ownerSessionId) || isAbortError(failure)) return;
      if (failure instanceof ApiError && SESSION_AUTH_CODES.has(failure.code)) setSessionExpired(true);
      const next: StoredIntent = {
        ...failedIntent,
        phase: "transport_error",
        retryAction,
        timestamp: Date.now(),
      };
      saveIntent(next);
      setError(errorText(failure));
    };

    const finishTerminal = (request: AgentRequestRecord, prior: StoredIntent) => {
      if (!isCurrent(epoch, intent.ownerSessionId)) return;
      setRequest(request);
      intentRef.current = null;
      setRecoveryIntent(null);
      removeIntent(prior.ownerSessionId);
      if (request.status === "FAILED" || request.status === "CANCELLED") {
        setError(request.error?.message ?? `Agent request ${request.status.toLowerCase()}.`);
      } else {
        setError(null);
      }
      const selected = request.evidence_refs?.[0];
      if (selected) onExperimentSelectedRef.current?.(selected);
    };

    const issueResume = async (request: AgentRequestRecord, prior: StoredIntent): Promise<void> => {
      if (!request.request_id || !prior.resumeNonce) {
        recoverableFailure({ ...prior, phase: "ready_to_resume" }, "reconcile", new Error("The server has not issued a continuation nonce yet. The request remains available for reconciliation."));
        return;
      }
      const resuming: StoredIntent = {
        ...prior,
        requestId: request.request_id,
        activeJobId: request.active_job_id ?? prior.activeJobId,
        phase: "resuming",
        retryAction: "resume",
        serverStatus: request.status,
        timestamp: Date.now(),
      };
      if (!saveIntent(resuming)) {
        setError("The continuation identity could not be saved, so the request was not resumed.");
        return;
      }
      try {
        const resumed = await agentApi.resumeRequest(
          resuming.requestId!,
          resuming.resumeNonce!,
          currentCredentials,
          controller.signal,
        );
        if (!isCurrent(epoch, intent.ownerSessionId)) return;
        await applyRequest(resumed.request, resuming);
      } catch (failure) {
        if (failure instanceof ApiError && failure.status === 500) {
          try {
            const terminal = await agentApi.getRequest(resuming.requestId!, currentCredentials, controller.signal);
            if (!isCurrent(epoch, intent.ownerSessionId)) return;
            if (terminal.request_id === resuming.requestId
                && terminal.session_id === resuming.ownerSessionId
                && TERMINAL_STATUSES.has(terminal.status)) {
              await applyRequest(terminal, resuming);
              return;
            }
          } catch (reconcileFailure) {
            recoverableFailure(resuming, "resume", reconcileFailure);
            return;
          }
        }
        recoverableFailure(resuming, "resume", failure);
      }
    };

    const applyRequest = async (request: AgentRequestRecord, prior: StoredIntent): Promise<void> => {
      if (!isCurrent(epoch, intent.ownerSessionId)) return;
      if (request.session_id !== prior.ownerSessionId || !request.request_id
          || (prior.requestId && request.request_id !== prior.requestId)) {
        const retryAction: AgentRetryAction = prior.requestId ? "reconcile" : "submit";
        recoverableFailure(
          prior,
          retryAction,
          new Error("The server response did not match the original session and request identity. Recovery remains bound to the saved session."),
        );
        return;
      }
      setRequest(request);
      if (TERMINAL_STATUSES.has(request.status)) {
        finishTerminal(request, prior);
        return;
      }

      const next: StoredIntent = {
        ...prior,
        requestId: request.request_id,
        ...(request.active_job_id ? { activeJobId: request.active_job_id } : request.active_job_id === null ? { activeJobId: undefined } : {}),
        ...(request.resume_nonce ? { resumeNonce: request.resume_nonce } : {}),
        phase: phaseForStatus(request.status),
        retryAction: request.status === "READY_TO_RESUME" ? "resume" : "reconcile",
        serverStatus: request.status,
        timestamp: Date.now(),
      };
      if (!saveIntent(next)) {
        setError("The latest server-issued request identity could not be saved. Automatic recovery is paused.");
        return;
      }

      if (request.status === "READY_TO_RESUME") {
        await issueResume(request, next);
        return;
      }

      if (request.status === "WAITING_FOR_JOB" && request.active_job_id) {
        try {
          const job = await agentApi.getJob(request.active_job_id, currentCredentials, controller.signal);
          if (!isCurrent(epoch, intent.ownerSessionId)) return;
          if (TERMINAL_JOB_STATUSES.has(job.status.toLowerCase())) {
            await issueResume(request, next);
            return;
          }
        } catch (failure) {
          recoverableFailure(next, "reconcile", failure);
          return;
        }
      }

      setError(null);
      scheduleReconcile(next, epoch);
    };

    try {
      if (action === "submit") {
        const pending: StoredIntent = {
          ...intent,
          phase: "pending_acceptance",
          retryAction: "submit",
          timestamp: Date.now(),
        };
        if (!saveIntent(pending)) {
          setError("The original prompt and request key could not be saved, so the request was not sent.");
          return;
        }
        const submitted = await agentApi.submitRequest(
          pending.prompt,
          pending.idempotencyKey,
          currentCredentials,
          controller.signal,
        );
        if (!isCurrent(epoch, intent.ownerSessionId)) return;
        await applyRequest(submitted.request, pending);
        return;
      }

      if (!intent.requestId) {
        recoverableFailure(intent, "submit", new Error("No accepted request ID is saved. Retry will use the original prompt and request key."));
        return;
      }

      if (action === "resume") {
        if (!intent.resumeNonce) {
          recoverableFailure(intent, "reconcile", new Error("No server-issued continuation nonce is saved. The request will be reconciled before another continuation."));
          return;
        }
        await issueResume({
          request_id: intent.requestId,
          session_id: intent.ownerSessionId,
          status: intent.serverStatus ?? "READY_TO_RESUME",
          prompt: intent.prompt,
          turn_count: 0,
          call_count: 0,
          repair_count: 0,
          tool_trace: [],
          evidence_refs: [],
          created_at: new Date(intent.timestamp).toISOString(),
          updated_at: new Date(intent.timestamp).toISOString(),
          active_job_id: intent.activeJobId,
          resume_nonce: intent.resumeNonce,
        }, intent);
        return;
      }

      const request = await agentApi.getRequest(intent.requestId, currentCredentials, controller.signal);
      if (!isCurrent(epoch, intent.ownerSessionId)) return;
      await applyRequest(request, intent);
    } catch (failure) {
      const retryAction: AgentRetryAction = action === "submit" ? "submit" : action === "resume" ? "resume" : "reconcile";
      recoverableFailure(intent, retryAction, failure);
    } finally {
      controllersRef.current.delete(controller);
      if (epochRef.current === epoch) {
        operationInFlightRef.current = false;
        if (manual) setIsSubmitting(false);
      }
    }
  }, [isCurrent, removeIntent, saveIntent, scheduleReconcile, setRequest]);
  reconcileRef.current = reconcile;

  useEffect(() => {
    mountedRef.current = true;
    invalidateOperations();
    if (!principalId || !credentials) return;

    setRequest(null);
    intentRef.current = null;
    setRecoveryIntent(null);
    setError(null);
    setSessionExpired(false);
    setStorageError(null);
    const epoch = epochRef.current;
    const ownerSessionId = principalId;
    const controller = new AbortController();
    controllersRef.current.add(controller);

    agentApi.getStatus(controller.signal).then((status) => {
      if (isCurrent(epoch, ownerSessionId)) setAgentStatus(status);
    }).catch(() => {
      if (isCurrent(epoch, ownerSessionId)) {
        setAgentStatus({
          enabled: false,
          available: false,
          model: "nvidia/Nemotron-3_5-Lightning",
          max_turns: 6,
          max_calls: 8,
        });
      }
    }).finally(() => controllersRef.current.delete(controller));

    try {
      const raw = window.localStorage.getItem(storageKey(ownerSessionId));
      if (raw) {
        const saved = parseIntent(raw, ownerSessionId);
        intentRef.current = saved;
        setRecoveryIntent(saved);
        const durable = saveIntent(saved);
        if (!durable) {
          setError("The saved request could not be refreshed in browser storage. Network recovery is paused.");
        } else if (saved.phase === "pending_acceptance") {
          setError("The server may have accepted this inquiry before its response was lost. Retry uses the saved prompt and request key.");
        } else if (saved.phase === "resuming") {
          void reconcileRef.current(saved, credentials, epoch, "resume", false);
        } else if (saved.phase === "transport_error") {
          setError("This request needs recovery. Retry will use its saved server identity.");
        } else if (saved.requestId) {
          void reconcileRef.current(saved, credentials, epoch, "reconcile", false);
        }
      }
    } catch (failure) {
      setStorageError(failure instanceof Error && failure.message !== "" ? `${STORAGE_ERROR} ${failure.message}` : STORAGE_ERROR);
      setError("Saved agent recovery state could not be read. No new inquiry will be sent until it is resolved.");
    }

    return () => {
      controller.abort();
      controllersRef.current.delete(controller);
      invalidateOperations();
    };
  }, [credentials, principalId, invalidateOperations, isCurrent, saveIntent, setRequest]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      invalidateOperations();
    };
  }, [invalidateOperations]);

  const submitQuery = useCallback(async (prompt: string) => {
    const currentCredentials = credentialsRef.current;
    if (!currentCredentials) {
      setError("Active session credentials are required to run an agent inquiry.");
      return;
    }
    if (!prompt.trim()) return;
    if (sessionExpired) return;
    if (storageError) {
      setError("Saved recovery state is unavailable. Clear or restore browser storage before sending another inquiry.");
      return;
    }
    const currentIntent = intentRef.current;
    if (currentIntent && currentIntent.ownerSessionId === currentCredentials.session_id) {
      setError("Recover or clear the existing inquiry before starting another one.");
      return;
    }

    invalidateOperations();
    setError(null);
    setSessionExpired(false);
    const idempotencyKey = `intent_${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}_${Math.random().toString(36).slice(2, 10)}`}`;
    const intent: StoredIntent = {
      version: 2,
      ownerSessionId: currentCredentials.session_id,
      prompt: prompt.trim(),
      idempotencyKey,
      phase: "pending_acceptance",
      retryAction: "submit",
      timestamp: Date.now(),
    };
    if (!saveIntent(intent)) {
      setError("The original prompt and request key could not be saved, so the request was not sent.");
      return;
    }
    setRequest(null);
    await reconcile(intent, currentCredentials, epochRef.current, "submit", true);
  }, [invalidateOperations, reconcile, saveIntent, sessionExpired, setRequest, storageError]);

  const retryQuery = useCallback(async () => {
    const intent = intentRef.current;
    const currentCredentials = credentialsRef.current;
    if (!intent || !currentCredentials || sessionExpired || storageError) return;
    if (currentCredentials.session_id !== intent.ownerSessionId) {
      setError("This inquiry belongs to a different session. It was not rebound to the current credentials.");
      return;
    }
    const action: AgentRetryAction = (!intent.requestId && intent.retryAction === "submit")
      ? "submit"
      : intent.phase === "pending_acceptance"
      ? "submit"
      : intent.phase === "resuming" || intent.retryAction === "resume"
        ? "resume"
        : "reconcile";
    setError(null);
    await reconcile(intent, currentCredentials, epochRef.current, action, true);
  }, [reconcile, sessionExpired, storageError]);

  const clearRequest = useCallback(() => {
    invalidateOperations();
    const ownerSessionId = intentRef.current?.ownerSessionId ?? credentialsRef.current?.session_id;
    if (ownerSessionId) removeIntent(ownerSessionId);
    intentRef.current = null;
    setRecoveryIntent(null);
    setRequest(null);
    setError(null);
  }, [invalidateOperations, removeIntent, setRequest]);

  const canRetry = Boolean(
    recoveryIntent
    && recoveryIntent.ownerSessionId === principalId
    && ["pending_acceptance", "resuming", "transport_error"].includes(recoveryIntent.phase),
  );
  const visibleIntent = recoveryIntent?.ownerSessionId === principalId ? recoveryIntent : null;
  const visibleRequest = activeRequest?.session_id === principalId ? activeRequest : null;

  return {
    agentStatus,
    activeRequest: visibleRequest,
    recoveryIntent: visibleIntent,
    storageError,
    isSubmitting,
    error,
    sessionExpired,
    canRetry,
    submitQuery,
    retryQuery,
    clearRequest,
  };
}
