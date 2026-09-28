import type { Data } from "plotly.js";
import type { BudgetCurvePayload, MetricName } from "../../api/types";
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

export function BudgetCurve(props: {
  payload: BudgetCurvePayload;
  predictor: string;
  scenario: string;
  method: string;
  metric: MetricName;
  selectedBudget: number;
}) {
  const methods = props.method === "all"
    ? Object.keys(props.payload.scenarios[scenarioKey(props.predictor, props.scenario)] ?? {})
    : [props.method];
  const series = methods.map((method) => ({
    method,
    points: props.payload.scenarios[scenarioKey(props.predictor, props.scenario)]?.[method] ?? [],
  }));
  const data: Data[] = series.map(({ method, points }, index) => ({
    type: "scatter",
    mode: "lines+markers",
    name: methodLabel(method),
    x: points.map((point) => point.budget),
    y: points.map((point) => point.available ? point[props.metric] : null),
    connectgaps: false,
    line: { color: chartColors[index % chartColors.length], width: 2 },
    marker: { color: chartColors[index % chartColors.length], size: 7 },
    hovertemplate: `${methodLabel(method)}<br>Budget: %{x}<br>${props.metric === "brier_score" ? "Brier" : "Log loss"}: %{y:.4f}<extra></extra>`,
  }));
  const metricLabel = props.metric === "brier_score" ? "Brier score" : "Log loss";

  return (
    <ChartPanel
      id="budget-curve"
      eyebrow="01 / Label budget"
      title="Probability quality by label budget"
      subtitle="Values and unavailable points come directly from the persisted budget-curve payload. The selected budget marks the diagnostic row below."
      badge={metricLabel}
    >
      <PersistedPlot
        testId="plot-budget"
        data={data}
        emptyLabel="No scored budget points are available for this selection."
        layout={{
          ...chartLayout,
          xaxis: { ...chartLayout.xaxis, title: { text: "Target label budget" } },
          yaxis: { ...chartLayout.yaxis, title: { text: metricLabel } },
        }}
      />
      <AccessibleTable caption={`Persisted ${metricLabel} by method and label budget`}>
        <thead>
          <tr><th scope="col">Method</th><th scope="col">Budget</th><th scope="col">Labels</th><th scope="col">Status</th><th scope="col">Resolved method</th><th scope="col">{metricLabel}</th></tr>
        </thead>
        <tbody>
          {series.flatMap(({ method, points }) => points.map((point) => (
            <tr key={`${method}-${point.budget}`} className={point.budget === props.selectedBudget ? "selected-row" : undefined}>
              <th scope="row">{methodLabel(method)}</th>
              <td>{point.budget}</td>
              <td>{point.labels_consumed}</td>
              <td>{point.available ? "Scored" : point.status || "Unavailable"}</td>
              <td>{methodLabel(point.resolved_method)}</td>
              <td>{point.available ? formatNumber(point[props.metric]) : "Unavailable"}</td>
            </tr>
          )))}
        </tbody>
      </AccessibleTable>
    </ChartPanel>
  );
}
