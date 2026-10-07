import type { StoredExperiment } from "../api/types";
import { isStressPayload } from "../api/client";
import { AccessibleTable, formatNumber, methodLabel } from "./charts/shared";
import { PresetCharts } from "./charts/PresetCharts";

export function PresetResult({ experiment }: { experiment: StoredExperiment }) {
  const payload = experiment.payload;
  if (isStressPayload(payload)) return null;
  const rows = Object.entries(payload.conditions ?? (payload.metrics ? { baseline: { condition_id: experiment.experiment_id, status: "scored", metrics: payload.metrics, calibration: undefined } } : {}));
  return <section className="detail-card" aria-labelledby="preset-result-heading">
    <p className="section-kicker">03 / Persisted evidence</p>
    <h2 id="preset-result-heading">Published preset result</h2>
    <p className="filter-note">{payload.config.run_type ?? "Baseline"} · development seed {payload.config.master_seed}. Comparisons and calibration bins below come from this saved preset payload.</p>
    <span className={`result-source result-source--${experiment.source}`}>{experiment.source === "fresh-run" ? "Fresh computation" : experiment.source === "server-cache" ? "Server-persisted cache" : "Browser-cached result"}</span>
    <PresetCharts
      key={experiment.experiment_id}
      conditions={rows.map(([name, row]) => ({
        id: row.condition_id,
        label: name,
        status: row.status,
        metrics: row.metrics,
      }))}
    />
    <AccessibleTable caption="Persisted preset conditions and diagnostics">
      <thead><tr><th scope="col">Condition</th><th scope="col">Status</th><th scope="col">Brier score</th><th scope="col">Log loss</th><th scope="col">ROC-AUC</th><th scope="col">Average precision</th><th scope="col">Resolved method / fallback</th></tr></thead>
      <tbody>{rows.map(([name, row]) => <tr key={name}><th scope="row">{name.replaceAll("_", " ")}</th><td>{row.status}</td><td>{formatNumber(row.metrics?.brier_score)}</td><td>{formatNumber(row.metrics?.log_loss)}</td><td>{formatNumber(row.metrics?.roc_auc)}</td><td>{formatNumber(row.metrics?.average_precision)}</td><td>{row.calibration?.resolved_method ? methodLabel(row.calibration.resolved_method) : "Not recorded"} / {row.calibration?.fallback_reason ? String(row.calibration.fallback_reason) : "None recorded"}</td></tr>)}</tbody>
    </AccessibleTable>
    <dl className="provenance-list"><div><dt>Logical experiment</dt><dd title={experiment.experiment_id}>{experiment.experiment_id}</dd></div><div><dt>Protocol</dt><dd>{payload.config.protocol_id ?? "Not recorded"}</dd></div></dl>
    <details className="hash-details"><summary>Content hashes · {Object.keys(experiment.content_hashes).length} recorded</summary><ul>{Object.entries(experiment.content_hashes).map(([key, value]) => <li key={key}><span>{key.split(/[\\/]/).at(-1)}</span><code>{value}</code></li>)}</ul></details>
    <p className="illustrative-note">Single-seed development output · illustrative only. Identical configurations may reuse the logical experiment ID; reruns have fresh job identity.</p>
  </section>;
}
