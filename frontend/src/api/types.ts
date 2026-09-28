export type PresetName = "bank-outage-50" | "bank-stress" | "bank-baseline";
export type DevelopmentSeed = 31001;
export type MetricName = "brier_score" | "log_loss";
export type MaybeNumber = number | null;

export interface SessionCredentials {
  session_id: string;
  capability_token: string;
  created_at: string;
}

export interface SessionResponse extends SessionCredentials {
  status: string;
  nonce: string;
}

export interface ExperimentSubmitResponse {
  job_id: string;
  status: string;
  status_url: string;
  estimated_duration_seconds: number;
}

export interface JobStatus {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | string;
  experiment_id: string | null;
  session_id: string | null;
  attempt: number;
  max_attempts: number;
  cancel_requested: boolean;
  error: { code?: string; error_type?: string; message?: string } | null;
  result: { experiment_id?: string; preset_name?: string } | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface BudgetPoint {
  available: boolean;
  average_precision: MaybeNumber;
  brier_score: MaybeNumber;
  budget: number;
  condition_id: string | null;
  decision_loss_threshold_0_5: MaybeNumber;
  ece: MaybeNumber;
  labels_consumed: number;
  log_loss: MaybeNumber;
  requested_method: string;
  resolved_method: string;
  roc_auc: MaybeNumber;
  status: string;
}

export interface BudgetCurvePayload {
  scenarios: Record<string, Record<string, BudgetPoint[]>>;
}

export interface PatternMethodRecord {
  available: boolean;
  block_brier: MaybeNumber;
  block_condition_id: string | null;
  block_log_loss: MaybeNumber;
  cellwise_brier: MaybeNumber;
  cellwise_condition_id: string | null;
  cellwise_log_loss: MaybeNumber;
  comparison_qualified: boolean;
  matching_status: string | null;
  residual_mismatch: MaybeNumber;
  tolerance: MaybeNumber;
  qualification_reason?: string | null;
}

export interface PatternComparison {
  block_scenario: string;
  budget: number;
  cellwise_scenario: string;
  methods: Record<string, PatternMethodRecord>;
}

export interface PatternPayload {
  comparisons: Record<string, PatternComparison>;
  matching_report?: Record<string, unknown>;
}

export interface ReliabilityBin {
  count: number;
  lower: number;
  mean_probability: MaybeNumber;
  positive_fraction: MaybeNumber;
  upper: number;
}

export interface ReliabilityRecord {
  condition_id: string;
  ece: MaybeNumber;
  reliability_bins: ReliabilityBin[] | null;
}

export interface ReliabilityPayload {
  scenarios: Record<string, Record<string, ReliabilityRecord | null>>;
}

export interface DecisionLossPoint {
  fn_cost: number;
  fn_count: number;
  fp_cost: number;
  fp_count: number;
  loss: MaybeNumber;
  n_samples: number;
  threshold: MaybeNumber;
  tn_count: number;
  tp_count: number;
}

export interface DecisionLossRecord {
  condition_id: string;
  cost_grid_losses: DecisionLossPoint[] | null;
}

export interface DecisionLossPayload {
  scenarios: Record<string, Record<string, DecisionLossRecord | null>>;
}

export interface ConditionMetrics {
  average_precision: MaybeNumber;
  brier_score: MaybeNumber;
  decision_loss?: DecisionLossPoint[] | null;
  ece: MaybeNumber;
  log_loss: MaybeNumber;
  prevalence: MaybeNumber;
  reliability?: ReliabilityBin[] | null;
  roc_auc: MaybeNumber;
}

export interface SparseBinDiagnostics {
  affected_fallback_rows: number;
  resolution_counts: Record<string, number>;
  bin_eval_counts: Record<string, number>;
  bin_fallback_counts: Record<string, number>;
  bin_support: Record<string, number>;
  bin_resolution_counts: Record<string, Record<string, number>>;
  bin_resolved_maps: Record<string, string>;
  sparse_prediction_failures: number;
}

export interface StressCondition {
  condition_id: string;
  budget: number;
  predictor: string;
  scenario: string;
  method: string;
  requested_method: string;
  resolved_method: string;
  status: string;
  fit_status: string | null;
  fallback_reason: string | null;
  fallback_chain: string[];
  unique_fit_failures: number;
  unique_prediction_failures: number;
  sparse_bin_diagnostics?: SparseBinDiagnostics | null;
  mask_rates: Record<string, MaybeNumber>;
  dataset_id: string;
  evaluation_rows_id: string;
  metrics: ConditionMetrics | null;
}

export interface MaskRateSummary {
  observed_all_feature_cells_new_missing_rate?: MaybeNumber;
  observed_history_group_new_missing_rate?: MaybeNumber;
  total_missing_rate_over_all_feature_cells?: MaybeNumber;
  rows_with_new_missingness_fraction?: MaybeNumber;
  realized_selected_row_fraction?: MaybeNumber;
  requested_row_probability?: MaybeNumber;
  requested_rate?: MaybeNumber;
}

export interface StressConfigView {
  evaluation_tier: string;
  protocol_id: string;
  master_seed: number;
  predictors: string[];
  budgets: number[];
  cost_grid: [number, number][];
  calibration_methods: string[];
  run_type: string;
}

export interface StressPayload {
  config: StressConfigView;
  protocol: { version?: string; [key: string]: unknown };
  conditions: Record<string, StressCondition>;
  payloads: {
    budget_curve: BudgetCurvePayload;
    pattern_vs_rate: PatternPayload;
    reliability: ReliabilityPayload;
    decision_loss: DecisionLossPayload;
  };
  masks?: Record<string, MaskRateSummary | string | number | null>;
  roles?: Record<string, { count?: number; [key: string]: unknown }>;
  [key: string]: unknown;
}

export interface ExperimentEnvelope {
  experiment_id: string;
  created_at: string;
  payload: StressPayload | PresetPayload;
  content_hashes: Record<string, string>;
}

export interface PublishedExperimentSummary {
  experiment_id: string;
  created_at: string;
}

export interface SavedJob {
  job_id: string;
  session_id: string;
  preset_name: PresetName;
  seed: DevelopmentSeed;
  idempotency_key: string;
  status: JobStatus["status"];
  experiment_id: string | null;
  created_at: string;
  error_code?: string;
  error_type?: string;
  cancel_requested?: boolean;
  result_loaded?: boolean;
}

export interface PendingSubmission {
  session_id: string;
  preset_name: PresetName;
  seed: DevelopmentSeed;
  idempotency_key: string;
  started_at: string;
}

export interface StoredExperiment {
  experiment_id: string;
  created_at: string;
  content_hashes: Record<string, string>;
  payload: StressPayload | PresetPayload;
  source: "browser-cache" | "server-cache" | "fresh-run";
}

export interface PresetPayload {
  config: { master_seed: number; protocol_id?: string; evaluation_tier?: string; run_type?: string };
  metrics?: ConditionMetrics;
  conditions?: Record<string, {
    condition_id: string;
    status: string;
    metrics: ConditionMetrics | null;
    calibration?: { requested_method?: string; resolved_method?: string; fit_status?: string; fallback_reason?: string | string[] | null };
  }>;
}

export type StoredStressExperiment = StoredExperiment & { payload: StressPayload };

export interface WorkspaceSnapshot {
  version: 1;
  session: SessionCredentials | null;
  jobs: SavedJob[];
  pending_submission: PendingSubmission | null;
  cached_experiment: StoredExperiment | null;
}

export interface ActivityFact {
  id: string;
  at: string;
  path: string;
  outcome: string;
  kind: "request" | "result" | "recovery";
}
