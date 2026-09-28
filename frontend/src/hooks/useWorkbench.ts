import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, isPublishedPayload } from "../api/client";
import type {
  ExperimentEnvelope,
  PendingSubmission,
  PresetName,
  SavedJob,
  SessionCredentials,
  StoredExperiment,
  WorkspaceSnapshot,
} from "../api/types";
import { cacheExperiment, readWorkspace, writeWorkspace } from "../state/workspace";

export interface WorkbenchActivity {
  id: string;
  at: string;
  kind: "request" | "result" | "recovery";
  path: string;
  outcome: string;
}

function describeError(error: unknown): { message: string; code: string } {
  if (error instanceof ApiError) return { message: error.message, code: error.code };
  return { message: "The request could not be completed. Retry when the server is available.", code: "REQUEST_FAILED" };
}

const SESSION_AUTH_CODES = new Set([
  "MISSING_SESSION_CREDENTIALS",
  "INVALID_SESSION_CREDENTIALS",
  "SESSION_EXPIRED",
  "INVALID_CAPABILITY_TOKEN",
]);

function newId(): string {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function useWorkbench() {
  const initialRead = useRef(readWorkspace());
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot>(initialRead.current.workspace);
  const workspaceRef = useRef(workspace);
  const [activities, setActivities] = useState<WorkbenchActivity[]>([]);
  const [backend, setBackend] = useState<"checking" | "online" | "offline">("checking");
  const [ready, setReady] = useState(false);
  const [errorNotice, setErrorNotice] = useState<{ message: string; code: string } | null>(null);
  const [storageNotice, setStorageNotice] = useState<string | null>(initialRead.current.issue);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const completedJobs = useRef(new Set<string>());
  const inFlightPolls = useRef(new Set<string>());

  const commit = useCallback((transform: (current: WorkspaceSnapshot) => WorkspaceSnapshot) => {
    const next = transform(workspaceRef.current);
    workspaceRef.current = next;
    setWorkspace(next);
    const warning = writeWorkspace(next);
    if (warning) setStorageNotice(warning);
  }, []);

  const addActivity = useCallback((kind: WorkbenchActivity["kind"], path: string, outcome: string) => {
    const row: WorkbenchActivity = { id: newId(), at: new Date().toISOString(), kind, path, outcome };
    setActivities((current) => [row, ...current].slice(0, 12));
  }, []);

  const saveExperiment = useCallback((experiment: ExperimentEnvelope, source: StoredExperiment["source"]) => {
    if (!isPublishedPayload(experiment.payload)) {
      throw new Error("The published record is not a supported persisted payload.");
    }
    const cached = cacheExperiment(experiment, source);
    commit((current) => ({ ...current, cached_experiment: cached }));
  }, [commit]);

  const setJob = useCallback((job: SavedJob) => {
    commit((current) => {
      return { ...current, jobs: current.jobs.map((entry) => {
        if (entry.job_id !== job.job_id) return entry;
        if (["completed", "failed", "cancelled"].includes(entry.status) && ["queued", "running"].includes(job.status)) return entry;
        return { ...job, cancel_requested: entry.cancel_requested || job.cancel_requested };
      }) };
    });
  }, [commit]);

  const acceptSubmission = useCallback((pending: PendingSubmission, credentials: SessionCredentials, response: { job_id: string; status: string }) => {
    const job: SavedJob = {
      job_id: response.job_id,
      session_id: credentials.session_id,
      preset_name: pending.preset_name,
      seed: 31001,
      idempotency_key: pending.idempotency_key,
      status: response.status,
      experiment_id: null,
      created_at: pending.started_at,
    };
    commit((current) => ({
      ...current,
      jobs: [...current.jobs.filter((entry) => entry.job_id !== job.job_id), job].slice(-8),
      pending_submission: current.pending_submission?.idempotency_key === pending.idempotency_key ? null : current.pending_submission,
    }));
    addActivity("result", "/api/v1/experiments", `Job ${job.job_id} accepted · ${pending.preset_name}`);
    setErrorNotice(null);
    setBackend("online");
  }, [addActivity, commit]);

  const sendSubmission = useCallback(async (pending: PendingSubmission, credentials: SessionCredentials) => {
    setBusyAction("submit");
    addActivity("request", "/api/v1/experiments", `Submit ${pending.preset_name} · retry-safe key retained`);
    try {
      const { submission } = await api.submit(pending, credentials);
      acceptSubmission(pending, credentials, submission);
    } catch (error) {
      const issue = describeError(error);
      const sessionRejected = error instanceof ApiError && error.status === 401 && SESSION_AUTH_CODES.has(issue.code);
      if (sessionRejected) {
        setReady(false);
        setErrorNotice({
          code: issue.code,
          message: "This session no longer authorizes submissions. Reconnect to create a new session; the rejected pending submission will be discarded, private jobs from the old session cannot be resumed, and cached published results remain available.",
        });
        addActivity("recovery", "/api/v1/experiments", `${issue.code} · reconnect required; old submission will not be replayed`);
      } else {
        setErrorNotice(issue);
        setBackend(error instanceof ApiError && error.status !== 0 ? "online" : "offline");
        addActivity("recovery", "/api/v1/experiments", `${issue.code} · submission identity retained for retry`);
      }
    } finally {
      setBusyAction(null);
    }
  }, [acceptSubmission, addActivity]);

  const connecting = useRef(false);
  const reconnect = useCallback(async () => {
    if (connecting.current) return;
    connecting.current = true;
    setBackend("checking");
    setReady(false);
    let credentials = workspaceRef.current.session;
    let expired = false;
    try {
      if (credentials) {
        try { await api.validateSession(credentials); }
        catch (error) {
          if (!(error instanceof ApiError) || ![401, 403, 404].includes(error.status)) throw error;
          expired = true;
          credentials = null;
          commit((value) => ({ ...value, session: null, pending_submission: null }));
        }
      }
      if (!credentials) {
        credentials = (await api.createSession()).session;
        const session = credentials;
        commit((value) => ({ ...value, session }));
      }
      setBackend("online");
      setReady(true);
      setErrorNotice(expired ? { code: "SESSION_REPLACED", message: "The previous session was replaced. Its rejected pending submission was discarded; private jobs from that session cannot be resumed. Cached published results remain available." } : null);
      addActivity(expired ? "recovery" : "result", "/api/v1/agent/sessions", expired ? "Expired session replaced; published evidence retained" : "Server-issued browser session ready");
    } catch (error) {
      setBackend("offline");
      setErrorNotice(describeError(error));
    } finally { connecting.current = false; }
  }, [addActivity, commit]);

  useEffect(() => { void reconnect(); }, [reconnect]);

  const refreshJob = useCallback(async (job: SavedJob) => {
    const credentials = workspaceRef.current.session;
    if (!credentials || credentials.session_id !== job.session_id || inFlightPolls.current.has(job.job_id)) return;
    if (["failed", "cancelled"].includes(job.status) || (job.status === "completed" && job.result_loaded)) return;
    inFlightPolls.current.add(job.job_id);
    try {
      const { job: result } = await api.job(job.job_id, credentials);
      const refreshed: SavedJob = {
        ...job,
        status: result.status,
        experiment_id: result.experiment_id ?? result.result?.experiment_id ?? job.experiment_id,
        cancel_requested: result.cancel_requested || job.cancel_requested,
        ...(result.error?.code ? { error_code: result.error.code } : {}),
        ...(result.error?.error_type ? { error_type: result.error.error_type } : {}),
      };
      setJob(refreshed);
      setBackend("online");
      setErrorNotice((notice) => notice?.code === "NETWORK_UNAVAILABLE" ? null : notice);
      if (result.status === "completed" && refreshed.experiment_id && !completedJobs.current.has(job.job_id)) {
        completedJobs.current.add(job.job_id);
        try {
          const { experiment } = await api.experiment(refreshed.experiment_id);
          saveExperiment(experiment, "fresh-run");
          setJob({ ...refreshed, result_loaded: true });
          addActivity("result", `/api/v1/experiments/${experiment.experiment_id}`, `Published result loaded · job ${job.job_id}`);
          setErrorNotice(null);
        } catch (error) {
          completedJobs.current.delete(job.job_id);
          const issue = describeError(error);
          setErrorNotice(issue);
          addActivity("recovery", `/api/v1/experiments/${refreshed.experiment_id}`, `Job completed; persisted result fetch failed · ${issue.code}`);
        }
      } else if (["failed", "cancelled"].includes(result.status)) {
        addActivity("result", `/api/v1/jobs/${job.job_id}`, `Job ended · ${result.status}${result.error?.code ? ` · ${result.error.code}` : ""}`);
      }
    } catch (error) {
      const issue = describeError(error);
      setErrorNotice(issue);
      setBackend(error instanceof ApiError && error.status !== 0 ? "online" : "offline");
      if (error instanceof ApiError && [401, 403].includes(error.status)) {
        setReady(false);
        setErrorNotice({ message: "This job belongs to an expired session. The saved result remains available; start a new session to submit another run.", code: issue.code });
      }
    } finally {
      inFlightPolls.current.delete(job.job_id);
    }
  }, [addActivity, saveExperiment, setJob]);

  useEffect(() => {
    if (!ready) return;
    const timer = window.setInterval(() => {
      for (const job of workspaceRef.current.jobs) void refreshJob(job);
    }, 1800);
    for (const job of workspaceRef.current.jobs) void refreshJob(job);
    return () => window.clearInterval(timer);
  }, [ready, refreshJob]);

  const submitNew = useCallback(async (preset: PresetName) => {
    const credentials = workspaceRef.current.session;
    if (!credentials || workspaceRef.current.pending_submission) return;
    const pending: PendingSubmission = {
      session_id: credentials.session_id,
      preset_name: preset,
      seed: 31001,
      idempotency_key: newId(),
      started_at: new Date().toISOString(),
    };
    commit((current) => ({ ...current, pending_submission: pending, cached_experiment: current.cached_experiment ? { ...current.cached_experiment, source: "browser-cache" } : null }));
    await sendSubmission(pending, credentials);
  }, [commit, sendSubmission]);

  const retrySubmission = useCallback(async () => {
    const pending = workspaceRef.current.pending_submission;
    const credentials = workspaceRef.current.session;
    if (!pending || !credentials || pending.session_id !== credentials.session_id) return;
    await sendSubmission(pending, credentials);
  }, [sendSubmission]);

  const cancelJob = useCallback(async (job: SavedJob) => {
    const credentials = workspaceRef.current.session;
    if (!credentials || credentials.session_id !== job.session_id) return;
    setBusyAction(`cancel:${job.job_id}`);
    addActivity("request", `/api/v1/jobs/${job.job_id}/cancel`, `Cancellation requested · ${job.job_id}`);
    try {
      const result = await api.cancel(job.job_id, credentials);
      setJob({ ...job, cancel_requested: true, status: result.outcome === "cancelled" ? "cancelled" : job.status });
      addActivity("result", `/api/v1/jobs/${job.job_id}/cancel`, result.outcome === "cancelled" ? "Job cancelled" : "Cancellation requested; worker will report its terminal state.");
      setErrorNotice(null);
    } catch (error) {
      const issue = describeError(error);
      setErrorNotice(issue);
      addActivity("recovery", `/api/v1/jobs/${job.job_id}/cancel`, `${issue.code} · job state retained`);
    } finally {
      setBusyAction(null);
    }
  }, [addActivity, setJob]);

  const loadPublished = useCallback(async (experimentId: string) => {
    setBusyAction("load-result");
    try {
      const { experiment } = await api.experiment(experimentId);
      saveExperiment(experiment, "server-cache");
      addActivity("recovery", `/api/v1/experiments/${experimentId}`, "Persisted server result loaded into the browser workspace");
      setErrorNotice(null);
    } catch (error) {
      setErrorNotice(describeError(error));
    } finally {
      setBusyAction(null);
    }
  }, [addActivity, saveExperiment]);

  return {
    workspace,
    activities,
    backend,
    ready,
    errorNotice,
    storageNotice,
    busyAction,
    submitNew,
    retrySubmission,
    cancelJob,
    loadPublished,
    setErrorNotice,
    reconnect,
  };
}
