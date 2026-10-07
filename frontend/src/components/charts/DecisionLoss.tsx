import type { Data } from "plotly.js";
import type { DecisionLossPayload } from "../../api/types";
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

export function costPairKey(fpCost: number, fnCost: number): string {
  return `${fpCost}|${fnCost}`;
}

export function DecisionLoss(props: {
  payload: DecisionLossPayload;
  predictor: string;
  scenario: string;
  method: string;
  selectedCost: string;
}) {
  const scenario = props.payload.scenarios[scenarioKey(props.predictor, props.scenario)] ?? {};
  const methods = props.method === "all" ? Object.keys(scenario) : [props.method];
  const selected = methods.flatMap((method) => {
    const record = scenario[method];
    const rows = (record?.cost_grid_losses ?? []).filter((row) =>
      props.selectedCost === "all" || costPairKey(row.fp_cost, row.fn_cost) === props.selectedCost,
    );
    return rows.length ? [{ method, rows }] : [];
  });
  const categories = Array.from(new Set(selected.flatMap(({ rows }) => rows.map((row) => `FP ${row.fp_cost} · FN ${row.fn_cost}`))));
  const traces: Data[] = selected.map(({ method, rows }) => {
    const style = methodStyle(method);
    return {
      type: "bar",
      name: methodLabel(method),
      x: rows.map((row) => `FP ${row.fp_cost} · FN ${row.fn_cost}`),
      y: rows.map((row) => row.loss),
      marker: { color: style.color },
      hovertemplate: `${methodLabel(method)}<br>%{x}<br>Persisted loss: %{y:.4f}<extra></extra>`,
    };
  });

  return (
    <ChartPanel
      id="decision-loss"
      eyebrow="04 / Operating costs"
      title="Decision loss at recorded cost settings"
      subtitle="This persisted panel is fixed at 50 target labels. The cost selector filters stored FP/FN cost pairs and does not change a run."
      badge="50 labels · fixed"
    >
      <PersistedPlot
        testId="plot-decision-loss"
        data={traces}
        emptyLabel="Decision-loss values are unavailable for this selection and cost setting."
        layout={{
          ...chartLayout,
          barmode: "group",
          xaxis: { ...chartLayout.xaxis, title: { text: "Persisted false-positive and false-negative costs" }, categoryorder: "array", categoryarray: categories },
          yaxis: { ...chartLayout.yaxis, title: { text: "Persisted decision loss" } },
        }}
      />
      <AccessibleTable caption="Persisted decision-loss values and confusion counts at each cost pair">
        <thead>
          <tr><th scope="col">Method</th><th scope="col">FP cost</th><th scope="col">FN cost</th><th scope="col">Threshold</th><th scope="col">Loss</th><th scope="col">False positives</th><th scope="col">False negatives</th><th scope="col">Sample size</th></tr>
        </thead>
        <tbody>
          {selected.flatMap(({ method, rows }) => rows.map((row) => (
            <tr key={`${method}-${costPairKey(row.fp_cost, row.fn_cost)}`}>
              <th scope="row">{methodLabel(method)}</th>
              <td>{formatNumber(row.fp_cost, 2)}</td>
              <td>{formatNumber(row.fn_cost, 2)}</td>
              <td>{formatNumber(row.threshold, 2)}</td>
              <td>{formatNumber(row.loss)}</td>
              <td>{row.fp_count}</td>
              <td>{row.fn_count}</td>
              <td>{row.n_samples}</td>
            </tr>
          )))}
        </tbody>
      </AccessibleTable>
    </ChartPanel>
  );
}
