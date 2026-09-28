import type { Data } from "plotly.js";
import type { DecisionLossPayload, ReliabilityPayload } from "../../api/types";
import {
  AccessibleTable,
  ChartPanel,
  PersistedPlot,
  chartColors,
  chartLayout,
  formatNumber,
  methodLabel,
  scenarioKey,
} from "./shared";

export function Reliability(props: {
  payload: ReliabilityPayload;
  decisionLoss: DecisionLossPayload;
  predictor: string;
  scenario: string;
  method: string;
  selectedBudget: number;
}) {
  const key = scenarioKey(props.predictor, props.scenario);
  const methods = props.method === "all"
    ? Object.keys(props.payload.scenarios[key] ?? {})
    : [props.method];
  const series = methods.map((method) => ({ method, record: props.payload.scenarios[key]?.[method] ?? null }));
  const reference: Data = {
    type: "scatter",
    mode: "lines",
    name: "Perfect calibration reference",
    x: [0, 1],
    y: [0, 1],
    line: { color: "#96a7ad", dash: "dash", width: 1.5 },
    hoverinfo: "skip",
  };
  const points: Data[] = series.flatMap(({ method, record }, index) => {
    if (!record?.reliability_bins?.some((bin) => bin.mean_probability !== null && bin.positive_fraction !== null)) return [];
    return [{
      type: "scatter",
      mode: "lines+markers",
      name: methodLabel(method),
      x: record.reliability_bins.map((bin) => bin.mean_probability),
      y: record.reliability_bins.map((bin) => bin.positive_fraction),
      connectgaps: false,
      line: { color: chartColors[index % chartColors.length], width: 1.8 },
      marker: { color: chartColors[index % chartColors.length], size: 7 },
      hovertemplate: `${methodLabel(method)}<br>Mean prediction: %{x:.3f}<br>Observed fraction: %{y:.3f}<extra></extra>`,
    }];
  });
  const sampleSize = (method: string, conditionId: string): number | null => {
    const decisionRecord = props.decisionLoss.scenarios[key]?.[method];
    if (!decisionRecord || decisionRecord.condition_id !== conditionId) return null;
    return decisionRecord.cost_grid_losses?.[0]?.n_samples ?? null;
  };

  return (
    <ChartPanel
      id="reliability"
      eyebrow="03 / Calibration"
      title="Reliability by probability bin"
      subtitle={`The reliability payload is persisted at 50 target labels. Your selected budget (${props.selectedBudget}) applies to the budget diagnostics; this panel remains at its recorded budget.`}
      badge="50 labels · fixed"
    >
      <PersistedPlot
        testId="plot-reliability"
        data={points.length ? [reference, ...points] : []}
        emptyLabel="Reliability bins are unavailable for this selection."
        layout={{
          ...chartLayout,
          xaxis: { ...chartLayout.xaxis, title: { text: "Mean predicted probability" }, range: [0, 1] },
          yaxis: { ...chartLayout.yaxis, title: { text: "Observed positive fraction" }, range: [0, 1] },
        }}
      />
      <AccessibleTable caption="Persisted reliability bins, counts, sample size, and expected calibration error">
        <thead>
          <tr><th scope="col">Method</th><th scope="col">Probability bin</th><th scope="col">Bin count</th><th scope="col">Sample size</th><th scope="col">Mean probability</th><th scope="col">Observed fraction</th><th scope="col">ECE</th></tr>
        </thead>
        <tbody>
          {series.flatMap(({ method, record }) => record?.reliability_bins?.map((bin, index) => (
            <tr key={`${method}-${index}`}>
              <th scope="row">{methodLabel(method)}</th>
              <td>{formatNumber(bin.lower, 1)}–{formatNumber(bin.upper, 1)}</td>
              <td>{bin.count}</td>
              <td>{sampleSize(method, record.condition_id) ?? "Not recorded"}</td>
              <td>{formatNumber(bin.mean_probability)}</td>
              <td>{formatNumber(bin.positive_fraction)}</td>
              <td>{formatNumber(record.ece)}</td>
            </tr>
          )) ?? [<tr key={method}><th scope="row">{methodLabel(method)}</th><td colSpan={6}>Unavailable</td></tr>])}
        </tbody>
      </AccessibleTable>
    </ChartPanel>
  );
}
