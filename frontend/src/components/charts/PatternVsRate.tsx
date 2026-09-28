import type { Data } from "plotly.js";
import type { MetricName, PatternPayload } from "../../api/types";
import {
  AccessibleTable,
  ChartPanel,
  PersistedPlot,
  chartColors,
  chartLayout,
  formatNumber,
  methodLabel,
  scenarioLabel,
} from "./shared";

export function PatternVsRate(props: {
  payload: PatternPayload;
  predictor: string;
  method: string;
  metric: MetricName;
}) {
  const comparison = props.payload.comparisons[props.predictor];
  const methods = comparison
    ? props.method === "all" ? Object.keys(comparison.methods) : [props.method]
    : [];
  const selected = methods.map((method) => ({ method, record: comparison?.methods[method] })).filter(
    (item): item is { method: string; record: NonNullable<typeof item.record> } => Boolean(item.record),
  );
  const blockField = props.metric === "brier_score" ? "block_brier" : "block_log_loss";
  const cellField = props.metric === "brier_score" ? "cellwise_brier" : "cellwise_log_loss";
  const data: Data[] = [
    {
      type: "bar",
      name: scenarioLabel(comparison?.block_scenario ?? "History block"),
      x: selected.map(({ method }) => methodLabel(method)),
      y: selected.map(({ record }) => record.available ? record[blockField] : null),
      marker: { color: chartColors[0] },
      hovertemplate: "%{x}<br>Persisted score: %{y:.4f}<extra></extra>",
    },
    {
      type: "bar",
      name: scenarioLabel(comparison?.cellwise_scenario ?? "Matched-rate MCAR"),
      x: selected.map(({ method }) => methodLabel(method)),
      y: selected.map(({ record }) => record.available ? record[cellField] : null),
      marker: { color: chartColors[1] },
      hovertemplate: "%{x}<br>Persisted score: %{y:.4f}<extra></extra>",
    },
  ];
  const metricLabel = props.metric === "brier_score" ? "Brier score" : "Log loss";
  const qualification = selected.some(({ record }) => !record.comparison_qualified);

  return (
    <ChartPanel
      id="pattern-rate"
      eyebrow="02 / Missingness pattern"
      title="Amount versus pattern"
      subtitle="The stored matched comparison pairs a history-group block with cellwise MCAR at the persisted matched rate. Its budget is fixed by the payload."
      badge={`Budget ${comparison?.budget ?? "—"}`}
    >
      {qualification && <p className="qualification-note" role="status">At least one selected comparison is unqualified. Its observed values remain visible with the qualification state.</p>}
      <PersistedPlot
        testId="plot-pattern"
        data={data}
        emptyLabel="No matched pattern-versus-rate comparison is available for this predictor."
        layout={{
          ...chartLayout,
          barmode: "group",
          xaxis: { ...chartLayout.xaxis, title: { text: "Calibration method" } },
          yaxis: { ...chartLayout.yaxis, title: { text: metricLabel } },
        }}
      />
      <AccessibleTable caption="Persisted matched pattern comparison and qualification state">
        <thead>
          <tr><th scope="col">Method</th><th scope="col">History block</th><th scope="col">Matched-rate cellwise</th><th scope="col">Comparison</th><th scope="col">Matching status</th><th scope="col">Residual mismatch</th><th scope="col">Tolerance</th></tr>
        </thead>
        <tbody>
          {selected.map(({ method, record }) => (
            <tr key={method}>
              <th scope="row">{methodLabel(method)}</th>
              <td>{record.available ? formatNumber(record[blockField]) : "Unavailable"}</td>
              <td>{record.available ? formatNumber(record[cellField]) : "Unavailable"}</td>
              <td>{record.comparison_qualified ? "Qualified" : "Not qualified"}</td>
              <td>{record.matching_status ?? "Not recorded"}</td>
              <td>{formatNumber(record.residual_mismatch)}</td>
              <td>{formatNumber(record.tolerance)}</td>
            </tr>
          ))}
        </tbody>
      </AccessibleTable>
    </ChartPanel>
  );
}
