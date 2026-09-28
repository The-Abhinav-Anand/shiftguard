import type { MetricName, StoredStressExperiment, StressCondition, StressPayload } from "../api/types";
import { formatNumber, formatRate, methodLabel, predictorLabel, scenarioLabel, shortId } from "./charts/shared";

function selectedCondition(
  payload: StressPayload,
  predictor: string,
  scenario: string,
  method: string,
  budget: number,
): StressCondition | null {
  if (method === "all") return null;
  return payload.conditions[`${predictor}__${scenario}__b${budget}__${method}`] ?? null;
}

function maskSummary(payload: StressPayload, scenario: string): Record<string, number | null | undefined> | null {
  const keys: Record<string, string> = {
    history_block_0_50: "history_block_test_rates",
    mcar_matched_history: "mcar_matched_test_rates",
    mcar_0_10: "mcar_0_10_test_rates",
    mcar_0_30: "mcar_0_30_test_rates",
  };
  const key = keys[scenario];
  const value = key ? payload.masks?.[key] : null;
  return value && typeof value === "object" ? value as Record<string, number | null | undefined> : null;
}

function resolutionLabel(value: string): string {
  const labels: Record<string, string> = {
    fitted_bin_temperature: "Fitted bin temperature",
    source_remasked_temperature: "Source-remasked temperature",
    raw: "Raw",
    source_temperature: "Source temperature",
  };
  return labels[value] ?? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function countLabel(value: number | undefined): string {
  return value === undefined ? "Not recorded" : new Intl.NumberFormat("en-US").format(value);
}

function SparseBinDetails({ condition }: { condition: StressCondition }) {
  const diagnostics = condition.sparse_bin_diagnostics;
  if (!diagnostics) return null;
  const bins = [...new Set([
    ...Object.keys(diagnostics.bin_eval_counts),
    ...Object.keys(diagnostics.bin_fallback_counts),
    ...Object.keys(diagnostics.bin_support),
    ...Object.keys(diagnostics.bin_resolution_counts),
    ...Object.keys(diagnostics.bin_resolved_maps),
  ])].sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  const aggregateResolutions = Object.entries(diagnostics.resolution_counts)
    .map(([resolution, count]) => `${resolutionLabel(resolution)}: ${countLabel(count)}`)
    .join(" · ");

  return (
    <section className="sparse-bin-block" aria-label="Per-bin fallback diagnostics">
      <h3>Per-bin fallback</h3>
      <p><strong>Affected fallback rows: {countLabel(diagnostics.affected_fallback_rows)}</strong></p>
      <p>Aggregate resolution counts: {aggregateResolutions || "Not recorded"}</p>
      <p>Sparse prediction failures: {countLabel(diagnostics.sparse_prediction_failures)}</p>
      <div className="data-table-wrap">
      <table className="data-table" aria-label="Persisted per-bin fallback counts">
        <caption>Persisted evaluation, fallback, support, and map-resolution counts</caption>
        <thead><tr><th scope="col">Bin</th><th scope="col">Evaluation rows</th><th scope="col">Fallback rows</th><th scope="col">Support</th><th scope="col">Resolved map</th><th scope="col">Resolution counts</th></tr></thead>
        <tbody>{bins.map((bin) => {
          const resolutions = Object.entries(diagnostics.bin_resolution_counts[bin] ?? {})
            .map(([resolution, count]) => `${resolutionLabel(resolution)}: ${countLabel(count)}`)
            .join(" · ");
          return (
            <tr key={bin}>
              <th scope="row">Bin {bin}</th>
              <td>{countLabel(diagnostics.bin_eval_counts[bin])}</td>
              <td>{countLabel(diagnostics.bin_fallback_counts[bin])}</td>
              <td>{countLabel(diagnostics.bin_support[bin])}</td>
              <td>{diagnostics.bin_resolved_maps[bin] ? resolutionLabel(diagnostics.bin_resolved_maps[bin]) : "Not recorded"}</td>
              <td>{resolutions || "None recorded"}</td>
            </tr>
          );
        })}</tbody>
      </table>
      </div>
    </section>
  );
}

export function SelectedDiagnostics(props: {
  experiment: StoredStressExperiment;
  predictor: string;
  scenario: string;
  method: string;
  budget: number;
  metric: MetricName;
}) {
  const payload = props.experiment.payload;
  const condition = selectedCondition(payload, props.predictor, props.scenario, props.method, props.budget);
  const curvePoint = payload.payloads.budget_curve.scenarios[`${props.predictor}__${props.scenario}`]?.[props.method]
    ?.find((point) => point.budget === props.budget);
  const metrics = condition?.metrics;
  const mask = maskSummary(payload, props.scenario);
  const selection = `${predictorLabel(props.predictor)} · ${scenarioLabel(props.scenario)} · ${props.method === "all" ? "all methods" : methodLabel(props.method)} · ${props.budget} labels`;

  return (
    <section className="details-grid" aria-label="Selected persisted result details">
      <article className="detail-card detail-card--metrics">
        <div className="detail-card__heading">
          <div><p className="section-kicker">Selected record</p><h2>Diagnostics</h2></div>
          <span className="selection-line">{selection}</span>
        </div>
        {props.method === "all" ? (
          <p className="inline-empty">Choose one method to bind these diagnostics to a single persisted condition.</p>
        ) : !condition || !metrics || !curvePoint?.available ? (
          <p className="inline-empty">The selected condition is unavailable. No values have been substituted.</p>
        ) : (
          <>
            <dl className="metric-grid">
              <div><dt>{props.metric === "brier_score" ? "Brier score" : "Log loss"} · {props.budget} labels</dt><dd>{formatNumber(curvePoint[props.metric])}</dd></div>
              <div><dt>ROC-AUC</dt><dd>{formatNumber(curvePoint.roc_auc)}</dd></div>
              <div><dt>Average precision</dt><dd>{formatNumber(curvePoint.average_precision)}</dd></div>
              <div><dt>Prevalence</dt><dd>{formatRate(metrics.prevalence)}</dd></div>
              <div><dt>New missing cells · evaluation</dt><dd>{formatRate(condition.mask_rates.eval_new_missing_rate)}</dd></div>
              <div><dt>Final missing cells · all features</dt><dd>{formatRate(mask?.total_missing_rate_over_all_feature_cells)}</dd></div>
              <div><dt>Rows with new missingness</dt><dd>{formatRate(mask?.rows_with_new_missingness_fraction)}</dd></div>
              <div><dt>ECE</dt><dd>{formatNumber(curvePoint.ece)}</dd></div>
            </dl>
          </>
        )}
        {condition && <div className="fallback-block" aria-label="Actual fit and fallback details">
          <div><span>Requested → resolved</span><strong>{methodLabel(condition.requested_method)} → {methodLabel(condition.resolved_method)}</strong></div>
          <div><span>Fit status</span><strong>{condition.fit_status ?? "Not recorded"} · {condition.status}</strong></div>
          <div><span>Whole-condition fallback chain</span><strong>{condition.fallback_chain?.length ? condition.fallback_chain.map(methodLabel).join(" → ") : "None recorded"}</strong></div>
          <div><span>Fallback reason</span><strong>{condition.fallback_reason ?? "None recorded"}</strong></div>
          <div><span>Unique fit / prediction failures</span><strong>{condition.unique_fit_failures} / {condition.unique_prediction_failures}</strong></div>
        </div>}
        {condition && <SparseBinDetails condition={condition} />}
        <p className="record-note">Every value above is selected from the server payload. Missing or failed metrics stay unavailable.</p>
      </article>

      <article className="detail-card provenance-card">
        <div className="detail-card__heading">
          <div><p className="section-kicker">Run record</p><h2>Identity & provenance</h2></div>
          <span className={`result-source result-source--${props.experiment.source}`}>
            {props.experiment.source === "fresh-run" ? "Fresh computation" : props.experiment.source === "server-cache" ? "Server-persisted cache" : "Browser-cached result"}
          </span>
        </div>
        <dl className="provenance-list">
          <div><dt>Logical experiment</dt><dd title={props.experiment.experiment_id}>{props.experiment.experiment_id}</dd></div>
          <div><dt>Selected condition</dt><dd title={condition?.condition_id}>{condition?.condition_id ?? "Select one method"}</dd></div>
          <div><dt>Protocol</dt><dd>{payload.config.protocol_id || "Not recorded"}</dd></div>
          <div><dt>Dataset identity</dt><dd title={condition?.dataset_id}>{shortId(condition?.dataset_id, 18)}</dd></div>
          <div><dt>Evaluation rows</dt><dd title={condition?.evaluation_rows_id}>{shortId(condition?.evaluation_rows_id, 18)}</dd></div>
          <div><dt>Development seed</dt><dd>{payload.config.master_seed}</dd></div>
          <div><dt>Tier</dt><dd>{payload.config.evaluation_tier}</dd></div>
          <div><dt>Persisted at</dt><dd>{new Date(props.experiment.created_at).toLocaleString()}</dd></div>
        </dl>
        <details className="hash-details">
          <summary>Content hashes · {Object.keys(props.experiment.content_hashes).length} recorded</summary>
          <ul>
            {Object.entries(props.experiment.content_hashes).map(([name, digest]) => (
              <li key={name}><span>{name.split(/[\\/]/).at(-1)}</span><code>{digest}</code></li>
            ))}
          </ul>
        </details>
        <p className="illustrative-note">Single-seed development output · illustrative only. Identical configurations may reuse the same logical experiment ID; each submitted job has its own job identity.</p>
      </article>
    </section>
  );
}
