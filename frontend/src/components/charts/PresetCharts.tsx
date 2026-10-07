import { useState } from "react";
import type { Data } from "plotly.js";
import type { ConditionMetrics, MetricName, ReliabilityBin } from "../../api/types";
import {
  AccessibleTable,
  ChartPanel,
  PersistedPlot,
  chartLayout,
  methodStyle,
} from "./shared";
import "./PresetCharts.css";

type PresetCondition = {
  id: string;
  label: string;
  status: string;
  metrics: ConditionMetrics | null;
};

function exactValue(value: number | null | undefined): string {
  return value === null || value === undefined ? "Not recorded" : String(value);
}

export function PresetCharts({ conditions }: { conditions: PresetCondition[] }) {
  const [selectedId, setSelectedId] = useState(() =>
    conditions.find((condition) => condition.status === "scored" && condition.metrics?.reliability?.length)?.id
      ?? conditions[0]?.id
      ?? "",
  );
  const selected = conditions.find((condition) => condition.id === selectedId) ?? null;
  const bins: ReliabilityBin[] = selected?.status === "scored" ? selected.metrics?.reliability ?? [] : [];
  const hasReliabilityPoints = bins.some((bin) => bin.mean_probability !== null && bin.positive_fraction !== null);
  const style = methodStyle("raw");

  const comparison = (metric: MetricName, title: string, testId: string) => {
    const values = conditions.map((condition) =>
      condition.status === "scored" ? condition.metrics?.[metric] ?? null : null,
    );
    const trace: Data = {
      type: "bar",
      name: title,
      x: conditions.map((condition) => condition.label.replaceAll("_", " ")),
      y: values,
      marker: { color: style.color },
      hovertemplate: `${title}<br>%{x}<br>Persisted value: %{y}<extra></extra>`,
    };

    return (
      <ChartPanel
        id={`preset-${metric}`}
        eyebrow="Persisted condition comparison"
        title={`${title} by condition`}
        subtitle="Bars use the stored condition scores; unscored or unrecorded values remain unavailable."
      >
        <PersistedPlot
          testId={testId}
          data={[trace]}
          emptyLabel={`${title} values are unavailable for this preset.`}
          layout={{
            ...chartLayout,
            height: 300,
            margin: { l: 58, r: 14, t: 12, b: 112 },
            xaxis: { ...chartLayout.xaxis, title: { text: "Persisted condition" }, tickangle: -35 },
            yaxis: { ...chartLayout.yaxis, title: { text: title }, rangemode: "tozero" },
          }}
        />
        <AccessibleTable caption={`Persisted ${title} by condition (exact saved values)`}>
          <thead><tr><th scope="col">Condition</th><th scope="col">Status</th><th scope="col">Condition ID</th><th scope="col">{title}</th></tr></thead>
          <tbody>{conditions.map((condition) => (
            <tr key={condition.id}>
              <th scope="row">{condition.label}</th>
              <td>{condition.status}</td>
              <td><code>{condition.id}</code></td>
              <td>{condition.status === "scored" ? exactValue(condition.metrics?.[metric]) : "Not scored"}</td>
            </tr>
          ))}</tbody>
        </AccessibleTable>
      </ChartPanel>
    );
  };

  const reference: Data = {
    type: "scatter",
    mode: "lines",
    name: "Perfect calibration reference",
    x: [0, 1],
    y: [0, 1],
    line: { color: "#56635B", dash: "dash", width: 1.5 },
    hoverinfo: "skip",
  };
  const reliability: Data = {
    type: "scatter",
    mode: "lines+markers",
    name: selected?.label ?? "Persisted condition",
    x: bins.map((bin) => bin.mean_probability),
    y: bins.map((bin) => bin.positive_fraction),
    connectgaps: false,
    line: { color: style.color, width: 1.8 },
    marker: { color: style.color, size: 7 },
    hovertemplate: `${selected?.label ?? "Condition"}<br>Mean prediction: %{x}<br>Observed fraction: %{y}<extra></extra>`,
  };

  return (
    <section className="preset-chart-grid" aria-label="Persisted preset graphs">
      {comparison("brier_score", "Brier score", "preset-plot-brier-score")}
      {comparison("log_loss", "Log loss", "preset-plot-log-loss")}
      <ChartPanel
        id="preset-reliability"
        eyebrow="Persisted calibration"
        title="Reliability curve"
        subtitle="Each point is a persisted probability bin. Empty bins remain gaps in the curve."
      >
        <label className="preset-chart-condition">
          <span>Reliability condition</span>
          <select aria-label="Reliability condition" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
            {conditions.map((condition) => <option key={condition.id} value={condition.id}>{condition.label.replaceAll("_", " ")} · {condition.status}</option>)}
          </select>
        </label>
        <PersistedPlot
          testId="preset-plot-reliability"
          data={hasReliabilityPoints ? [reference, reliability] : []}
          emptyLabel={selected?.status === "scored" ? "Reliability bins are unavailable for this condition." : "This condition was not scored; reliability values are unavailable."}
          layout={{
            ...chartLayout,
            xaxis: { ...chartLayout.xaxis, title: { text: "Mean predicted probability" }, range: [0, 1] },
            yaxis: { ...chartLayout.yaxis, title: { text: "Observed positive fraction" }, range: [0, 1] },
          }}
        />
        <AccessibleTable caption="Persisted reliability bins (exact saved values)">
          <thead><tr><th scope="col">Probability bin</th><th scope="col">Count</th><th scope="col">Mean probability</th><th scope="col">Observed fraction</th></tr></thead>
          <tbody>{bins.length ? bins.map((bin, index) => (
            <tr key={`${selectedId}-${index}`}>
              <th scope="row">{exactValue(bin.lower)}–{exactValue(bin.upper)}</th>
              <td>{bin.count}</td>
              <td>{exactValue(bin.mean_probability)}</td>
              <td>{exactValue(bin.positive_fraction)}</td>
            </tr>
          )) : <tr><td colSpan={4}>{selected?.status === "scored" ? "No reliability bins recorded." : "Condition not scored; values not recorded."}</td></tr>}</tbody>
        </AccessibleTable>
      </ChartPanel>
    </section>
  );
}
