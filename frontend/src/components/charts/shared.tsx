import { lazy, Suspense } from "react";
import type { Data, Layout } from "plotly.js";
import type { ReactNode } from "react";

const Plot = lazy(() => import("./Plot"));

export const chartColors = ["#177b73", "#335fbd", "#bd6d36", "#8c5e9c", "#4c7e4e", "#bd5470", "#6b7d8c", "#b09437"];

export function methodLabel(method: string | null | undefined): string {
  if (!method) return "Unavailable";
  const labels: Record<string, string> = {
    raw: "Raw predictor",
    source_temperature: "Source temperature",
    source_remasked_temperature: "Source remasked",
    source_fraction_binned_temperature: "Source fraction binned",
    target_temperature: "Target temperature",
    target_platt_logodds: "Target Platt",
    target_beta: "Target beta",
    target_isotonic: "Target isotonic",
  };
  return labels[method] ?? method.replaceAll("_", " ");
}

export function scenarioLabel(scenario: string): string {
  const labels: Record<string, string> = {
    baseline: "Baseline",
    history_block_0_50: "History block · 50% rows",
    mcar_matched_history: "Matched-rate cellwise MCAR",
    mcar_0_10: "Cellwise MCAR · 10%",
    mcar_0_30: "Cellwise MCAR · 30%",
  };
  return labels[scenario] ?? scenario.replaceAll("_", " ");
}

export function predictorLabel(predictor: string): string {
  return predictor === "logistic_regression" ? "Logistic regression" : predictor.replaceAll("_", " ");
}

export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Unavailable";
  return new Intl.NumberFormat("en", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}

export function formatRate(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Not recorded";
  return `${formatNumber(value * 100, 1)}%`;
}

export function shortId(value: string | null | undefined, length = 12): string {
  return value ? `${value.slice(0, length)}…` : "Unavailable";
}

export function scenarioKey(predictor: string, scenario: string): string {
  return `${predictor}__${scenario}`;
}

export function ChartPanel(props: {
  id: string;
  eyebrow: string;
  title: string;
  subtitle: string;
  badge?: string;
  children: ReactNode;
}) {
  return (
    <article className="chart-panel" aria-labelledby={`${props.id}-title`}>
      <header className="chart-panel__header">
        <div>
          <p className="chart-panel__eyebrow">{props.eyebrow}</p>
          <h2 id={`${props.id}-title`}>{props.title}</h2>
        </div>
        {props.badge && <span className="panel-badge">{props.badge}</span>}
      </header>
      <p className="chart-panel__subtitle">{props.subtitle}</p>
      {props.children}
    </article>
  );
}

export function PersistedPlot(props: {
  testId: string;
  data: Data[];
  layout: Partial<Layout>;
  emptyLabel: string;
}) {
  const hasPoints = props.data.some((trace) => {
    const y = "y" in trace ? trace.y : undefined;
    return Array.isArray(y) && y.some((value) => value !== null && value !== undefined);
  });
  if (!hasPoints) {
    return <div className="chart-empty" role="status">{props.emptyLabel}</div>;
  }
  return (
    <div className="plotly-frame" data-testid={props.testId} aria-label="Interactive persisted-data chart; numeric values follow in the table.">
      <Suspense fallback={<p role="status">Loading chart… Numeric values are available below.</p>}>
      <Plot
        data={props.data}
        layout={props.layout}
        config={{ displayModeBar: false, responsive: true, scrollZoom: false }}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
      </Suspense>
    </div>
  );
}

export const chartLayout: Partial<Layout> = {
  autosize: true,
  height: 310,
  margin: { l: 58, r: 18, t: 16, b: 68 },
  font: { family: "Inter, ui-sans-serif, system-ui, sans-serif", color: "#314452", size: 11 },
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  showlegend: true,
  legend: { orientation: "h", y: -0.31, x: 0, font: { size: 10 } },
  xaxis: { gridcolor: "#e8edf0", zeroline: false, automargin: true },
  yaxis: { gridcolor: "#e8edf0", zeroline: false, automargin: true },
};

export function AccessibleTable(props: { caption: string; children: ReactNode }) {
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <caption>{props.caption}</caption>
        {props.children}
      </table>
    </div>
  );
}
