import type {
  ExperimentEnvelope,
  ExperimentSubmitResponse,
  JobStatus,
  PendingSubmission,
  PresetName,
  PublishedExperimentSummary,
  SessionCredentials,
  SessionResponse,
  StressCondition,
  StressPayload,
  PresetPayload,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly path: string;

  constructor(status: number, code: string, message: string, requestId: string | null, path: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.path = path;
  }
}

function errorFields(value: unknown): { code: string; message: string; requestId: string | null } {
  if (!value || typeof value !== "object") {
    return { code: "REQUEST_FAILED", message: "The request could not be completed.", requestId: null };
  }
  const outer = value as Record<string, unknown>;
  const detail = outer.error && typeof outer.error === "object"
    ? (outer.error as Record<string, unknown>)
    : outer.detail && typeof outer.detail === "object"
      ? ((outer.detail as Record<string, unknown>).error as Record<string, unknown> | undefined)
      : undefined;
  const source = detail ?? outer;
  return {
    code: typeof source.code === "string" ? source.code : "REQUEST_FAILED",
    message: typeof source.message === "string" ? source.message : "The request could not be completed.",
    requestId: typeof source.request_id === "string" ? source.request_id : null,
  };
}

async function request<T>(
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
      signal: AbortSignal.timeout(20_000),
    });
  } catch {
    throw new ApiError(0, "NETWORK_UNAVAILABLE", "The server could not be reached. Check the connection and retry.", null, path);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const fields = errorFields(body);
    throw new ApiError(response.status, fields.code, fields.message, fields.requestId, path);
  }
  return { value: body as T, status: response.status };
}

export const api = {
  async health(): Promise<void> {
    await request<{ status: string }>("/health/live");
  },

  async createSession(): Promise<{ session: SessionCredentials; status: number }> {
    const result = await request<SessionResponse>("/api/v1/agent/sessions", {
      method: "POST",
      body: JSON.stringify({ initial_state: { client: "gate5-browser" } }),
    });
    return {
      session: {
        session_id: result.value.session_id,
        capability_token: result.value.capability_token,
        created_at: result.value.created_at,
      },
      status: result.status,
    };
  },

  async validateSession(credentials: SessionCredentials): Promise<void> {
    await request<unknown>(`/api/v1/agent/sessions/${encodeURIComponent(credentials.session_id)}`, {}, credentials);
  },

  async submit(
    pending: PendingSubmission,
    credentials: SessionCredentials,
  ): Promise<{ submission: ExperimentSubmitResponse; status: number }> {
    const result = await request<ExperimentSubmitResponse>(
      "/api/v1/experiments",
      {
        method: "POST",
        headers: { "Idempotency-Key": pending.idempotency_key },
        body: JSON.stringify({ preset_name: pending.preset_name satisfies PresetName }),
      },
      credentials,
    );
    return { submission: result.value, status: result.status };
  },

  async job(jobId: string, credentials: SessionCredentials): Promise<{ job: JobStatus; status: number }> {
    const result = await request<JobStatus>(
      `/api/v1/jobs/${encodeURIComponent(jobId)}`,
      {},
      credentials,
    );
    return { job: result.value, status: result.status };
  },

  async cancel(jobId: string, credentials: SessionCredentials): Promise<{ status: number; outcome: string }> {
    const result = await request<{ job_id: string; status: string; message: string }>(
      `/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST" },
      credentials,
    );
    return { status: result.status, outcome: result.value.status };
  },

  async publishedExperiments(): Promise<{ experiments: PublishedExperimentSummary[]; status: number }> {
    const result = await request<{ experiments: PublishedExperimentSummary[] }>("/api/v1/experiments?limit=20");
    return { experiments: result.value.experiments, status: result.status };
  },

  async experiment(experimentId: string): Promise<{ experiment: ExperimentEnvelope; status: number }> {
    const result = await request<ExperimentEnvelope>(
      `/api/v1/experiments/${encodeURIComponent(experimentId)}`,
    );
    return { experiment: result.value, status: result.status };
  },
};

export function isStressPayload(payload: unknown): payload is StressPayload {
  if (!payload || typeof payload !== "object") return false;
  const value = payload as Partial<StressPayload>;
  const plots = value.payloads;
  return Boolean(
    value.config?.run_type === "stress_engine" &&
      plots?.budget_curve?.scenarios &&
      plots.pattern_vs_rate?.comparisons &&
      plots.reliability?.scenarios &&
      plots.decision_loss?.scenarios &&
      value.conditions,
  );
}

export function isPublishedPayload(payload: unknown): payload is StressPayload | PresetPayload {
  if (!payload || typeof payload !== "object") return false;
  const value = payload as PresetPayload;
  return typeof value.config?.master_seed === "number" && (isStressPayload(value) || Boolean(value.metrics || value.conditions));
}

export function sanitizeForBrowserCache(experiment: ExperimentEnvelope): StressPayload | PresetPayload {
  const payload = experiment.payload;
  if (!isStressPayload(payload)) {
    return {
      config: { master_seed: payload.config.master_seed, protocol_id: payload.config.protocol_id, evaluation_tier: payload.config.evaluation_tier, run_type: payload.config.run_type },
      metrics: payload.metrics,
      conditions: payload.conditions && Object.fromEntries(Object.entries(payload.conditions).map(([key, row]) => [key, {
        condition_id: row.condition_id, status: row.status, metrics: row.metrics, calibration: row.calibration,
      }])),
    };
  }
  const conditions: Record<string, StressCondition> = {};
  for (const [key, condition] of Object.entries(payload.conditions)) {
    conditions[key] = {
      condition_id: condition.condition_id,
      budget: condition.budget,
      predictor: condition.predictor,
      scenario: condition.scenario,
      method: condition.method,
      requested_method: condition.requested_method,
      resolved_method: condition.resolved_method,
      status: condition.status,
      fit_status: condition.fit_status,
      fallback_reason: condition.fallback_reason,
      fallback_chain: condition.fallback_chain,
      unique_fit_failures: condition.unique_fit_failures,
      unique_prediction_failures: condition.unique_prediction_failures,
      sparse_bin_diagnostics: condition.sparse_bin_diagnostics ? {
        affected_fallback_rows: condition.sparse_bin_diagnostics.affected_fallback_rows,
        resolution_counts: { ...condition.sparse_bin_diagnostics.resolution_counts },
        bin_eval_counts: { ...condition.sparse_bin_diagnostics.bin_eval_counts },
        bin_fallback_counts: { ...condition.sparse_bin_diagnostics.bin_fallback_counts },
        bin_support: { ...condition.sparse_bin_diagnostics.bin_support },
        bin_resolution_counts: Object.fromEntries(Object.entries(condition.sparse_bin_diagnostics.bin_resolution_counts).map(([bin, counts]) => [bin, { ...counts }])),
        bin_resolved_maps: { ...condition.sparse_bin_diagnostics.bin_resolved_maps },
        sparse_prediction_failures: condition.sparse_bin_diagnostics.sparse_prediction_failures,
      } : condition.sparse_bin_diagnostics ?? null,
      mask_rates: condition.mask_rates,
      dataset_id: condition.dataset_id,
      evaluation_rows_id: condition.evaluation_rows_id,
      metrics: condition.metrics,
    };
  }

  const masks: NonNullable<StressPayload["masks"]> = {};
  for (const [key, summary] of Object.entries(payload.masks ?? {})) {
    if (key.endsWith("_rates") && summary && typeof summary === "object") {
      masks[key] = summary as (typeof masks)[string];
    }
  }

  const roles: StressPayload["roles"] = {};
  for (const [key, role] of Object.entries(payload.roles ?? {})) {
    roles[key] = { count: role.count };
  }

  return {
    config: {
      evaluation_tier: payload.config.evaluation_tier, protocol_id: payload.config.protocol_id,
      master_seed: payload.config.master_seed, predictors: payload.config.predictors,
      budgets: payload.config.budgets, cost_grid: payload.config.cost_grid,
      calibration_methods: payload.config.calibration_methods, run_type: payload.config.run_type,
    },
    protocol: payload.protocol,
    conditions,
    payloads: payload.payloads,
    masks,
    roles,
  };
}
