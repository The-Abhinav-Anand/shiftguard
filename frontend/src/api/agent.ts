import { ApiError } from "./client";
import type { JobStatus, SessionCredentials } from "./types";

export interface AgentStatus {
  enabled: boolean;
  available: boolean;
  model: string;
  max_turns: number;
  max_calls: number;
  provider_kind?: string;
  is_test_harness?: boolean;
  active_requests_count?: number;
}

export interface PublicToolError {
  code: string;
  message: string;
}

export interface ToolTraceEntry {
  ordinal: number;
  tool_name: string;
  tool_call_id: string;
  arguments: Record<string, unknown>;
  status: string;
  result?: Record<string, unknown> | null;
  error?: string | PublicToolError | null;
  job_id?: string | null;
}

export interface EmpiricalClaim {
  claim_type: string;
  description: string;
  condition_id?: string | null;
  metric_name?: string;
  value?: number | null;
  baseline_value?: number | null;
  delta?: number | null;
  direction?: string;
  condition_key?: string;
  experiment_id?: string;
  method?: string;
  qualification_reason?: string | null;
}

export interface SparseBinDiagnostics {
  affected_fallback_rows?: number | null;
  resolution_counts?: Record<string, number> | null;
  bin_eval_counts?: Record<string, number> | null;
  bin_fallback_counts?: Record<string, number> | null;
  bin_support?: Record<string, number> | null;
  bin_resolution_counts?: Record<string, Record<string, number>> | null;
  bin_resolved_maps?: Record<string, string> | null;
  sparse_prediction_failures?: number | null;
}

export interface FallbackConditionAnalysis {
  condition_id?: string | null;
  requested_method?: string | null;
  resolved_method?: string | null;
  fallback_reason?: string | null;
  sparse_bin_diagnostics?: SparseBinDiagnostics | null;
}

export type FallbackAnalysis = Record<string, FallbackConditionAnalysis>;

export interface GroundedFinalResponse {
  title: string;
  summary: string;
  claims: EmpiricalClaim[];
  fallback_analysis?: FallbackAnalysis | null;
  decision_loss_points?: Array<Record<string, unknown>> | null;
  evidence_references: string[];
  disclaimer: string;
  provider_narrative?: string;
  budget_limit_reached?: string;
}

export interface AgentRequestRecord {
  request_id: string;
  session_id: string;
  status: "RUNNING" | "WAITING_FOR_JOB" | "READY_TO_RESUME" | "COMPLETED" | "FAILED" | "CANCELLED" | string;
  prompt: string;
  turn_count: number;
  call_count: number;
  repair_count: number;
  active_job_id?: string | null;
  active_tool_call_id?: string | null;
  resume_nonce?: string | null;
  tool_trace: ToolTraceEntry[];
  evidence_refs: string[];
  final_response?: GroundedFinalResponse | null;
  error?: { code?: string; message?: string; status_code?: number } | null;
  created_at: string;
  updated_at: string;
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  credentials?: SessionCredentials,
): Promise<{ value: T; status: number }> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (credentials) {
    headers.set("X-Session-ID", credentials.session_id);
    headers.set("X-Session-Token", credentials.capability_token);
  }

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch (error) {
    if (init.signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) throw error;
    throw new ApiError(0, "NETWORK_UNAVAILABLE", "The server could not be reached. Check the connection and retry.", null, path);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const outer = body && typeof body === "object" ? body as Record<string, unknown> : {};
    const detail = outer.detail && typeof outer.detail === "object" ? outer.detail as Record<string, unknown> : {};
    const err = (outer.error ?? detail.error ?? outer.detail ?? {}) as Record<string, unknown>;
    const code = typeof err.code === "string" ? err.code : "REQUEST_FAILED";
    const message = typeof err.message === "string" ? err.message : "Agent request failed";
    const requestId = typeof err.request_id === "string" ? err.request_id : null;
    throw new ApiError(response.status, code, message, requestId, path);
  }

  return { value: body as T, status: response.status };
}

export const agentApi = {
  async getStatus(signal?: AbortSignal): Promise<AgentStatus> {
    const res = await requestJson<AgentStatus>("/api/v1/agent/status", { signal });
    return res.value;
  },

  async submitRequest(
    prompt: string,
    idempotencyKey: string,
    credentials: SessionCredentials,
    signal?: AbortSignal,
  ): Promise<{ request: AgentRequestRecord; status: number }> {
    const res = await requestJson<AgentRequestRecord>(
      "/api/v1/agent/requests",
      {
        method: "POST",
        body: JSON.stringify({ prompt, idempotency_key: idempotencyKey }),
        signal,
      },
      credentials,
    );
    return { request: res.value, status: res.status };
  },

  async getRequest(
    requestId: string,
    credentials: SessionCredentials,
    signal?: AbortSignal,
  ): Promise<AgentRequestRecord> {
    const res = await requestJson<AgentRequestRecord>(
      `/api/v1/agent/requests/${encodeURIComponent(requestId)}`,
      { method: "GET", signal },
      credentials,
    );
    return res.value;
  },

  async getJob(jobId: string, credentials: SessionCredentials, signal?: AbortSignal): Promise<JobStatus> {
    const res = await requestJson<JobStatus>(
      `/api/v1/jobs/${encodeURIComponent(jobId)}`,
      { method: "GET", signal },
      credentials,
    );
    return res.value;
  },

  async resumeRequest(
    requestId: string,
    nonce: string,
    credentials: SessionCredentials,
    signal?: AbortSignal,
  ): Promise<{ request: AgentRequestRecord; status: number }> {
    const res = await requestJson<AgentRequestRecord>(
      `/api/v1/agent/requests/${encodeURIComponent(requestId)}/resume`,
      {
        method: "POST",
        body: JSON.stringify({ nonce }),
        signal,
      },
      credentials,
    );
    return { request: res.value, status: res.status };
  },
};
