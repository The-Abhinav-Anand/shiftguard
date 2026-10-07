import { lazy, Suspense, useState } from "react";
import type { Data } from "plotly.js";
import type { BudgetCurvePayload, MetricName } from "../../api/types";
import { ChartErrorBoundary } from "../ChartErrorBoundary";
import {
  AccessibleTable,
  ChartPanel,
  PersistedPlot,
  chartLayout,
  formatNumber,
  methodLabel,
  methodStyle,
  scenarioKey,
} from "./shared";

const BudgetVolume = lazy(() => import("./BudgetVolume"));

export function BudgetCurve(props: {
  payload: BudgetCurvePayload;
  predictor: string;
  scenario: string;
  method: string;
  metric: MetricName;
  selectedBudget: number;
}) {
  const [view, setView] = useState<"2d" | "3d">("2d");
  const methods = props.method === "all"
    ? Object.keys(props.payload.scenarios[scenarioKey(props.predictor, props.scenario)] ?? {})
    : [props.method];
  const series = methods.map((method) => ({
    method,
    points: props.payload.scenarios[scenarioKey(props.predictor, props.scenario)]?.[method] ?? [],
  }));
  const metricLabel = props.metric === "brier_score" ? "Brier score" : "Log loss";
  const data: Data[] = series.map(({ method, points }) => {
    const style = methodStyle(method);
    const selectedPoint = points.find((point) => point.budget === props.selectedBudget);
    const legendValue = selectedPoint?.available ? formatNumber(selectedPoint[props.metric]) : "Unavailable";
    return {
      type: "scatter",
      mode: "lines+markers",
      name: `${methodLabel(method)} · ${legendValue}`,
      x: points.map((point) => point.budget),
      y: points.map((point) => point.available ? point[props.metric] : null),
      connectgaps: false,
      line: { color: style.color, dash: style.dash, width: 2 },
      marker: { color: style.color, symbol: style.marker, size: 7 },
      hovertemplate: `${methodLabel(method)}<br>Target labels: %{x}<br>${metricLabel}: %{y:.4f}<extra></extra>`,
    };
  });

  return (
    <ChartPanel
      id="budget-curve"
      eyebrow="01 / Label budget"
      title="Probability quality by label budget"
      subtitle="Persisted scores by target label budget. Legend values follow the selected budget; choose a method in the legend to show or hide its series."
      badge={metricLabel}
    >
      <section className="budget-curve-view" aria-label="Budget result views">
        <div className="budget-view-switch" role="group" aria-label="Budget chart view">
          <span>View</span>
          <button type="button" aria-pressed={view === "2d"} onClick={() => setView("2d")}>2D chart</button>
          <button type="button" aria-pressed={view === "3d"} onClick={() => setView("3d")}>3D view</button>
        </div>
        {view === "2d" ? (
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
        ) : (
          <ChartErrorBoundary>
            <Suspense fallback={<p className="chart-loading" role="status">Loading the optional 3D budget view. Persisted values remain in the table below.</p>}>
              <BudgetVolume
                payload={props.payload}
                predictor={props.predictor}
                scenario={props.scenario}
                method={props.method}
                metric={props.metric}
              />
            </Suspense>
          </ChartErrorBoundary>
        )}
      </section>
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
