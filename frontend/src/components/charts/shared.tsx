import { lazy, Suspense } from "react";
import type { Data, Layout } from "plotly.js";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { ChartErrorBoundary } from "../ChartErrorBoundary";

const Plot = lazy(() => import("./Plot"));

export const chartColors = ["#2E704F", "#71529B", "#263A53", "#B44E77", "#317F7C", "#95720A", "#536378", "#B65035"];

type MethodStyle = {
  color: string;
  dash: "solid" | "dash" | "dot" | "longdash";
  marker: "circle" | "square" | "diamond" | "triangle-up" | "cross" | "star" | "hexagon" | "triangle-down";
};

const methodStyles: Record<string, MethodStyle> = {
  raw: { color: chartColors[0], dash: "solid", marker: "circle" },
  source_temperature: { color: chartColors[1], dash: "solid", marker: "square" },
  source_remasked_temperature: { color: chartColors[2], dash: "dash", marker: "diamond" },
  source_fraction_binned_temperature: { color: chartColors[3], dash: "dot", marker: "triangle-up" },
  target_temperature: { color: chartColors[4], dash: "solid", marker: "cross" },
  target_platt_logodds: { color: chartColors[5], dash: "dash", marker: "star" },
  target_beta: { color: chartColors[6], dash: "dot", marker: "hexagon" },
  target_isotonic: { color: chartColors[7], dash: "longdash", marker: "triangle-down" },
};

export function methodStyle(method: string): MethodStyle {
  const known = methodStyles[method];
  if (known) return known;
  let hash = 2166136261;
  for (const character of method) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  const index = (hash >>> 0) % chartColors.length;
  const dashStyles: MethodStyle["dash"][] = ["solid", "dash", "dot", "longdash"];
  const markerStyles: MethodStyle["marker"][] = ["circle", "square", "diamond", "triangle-up", "cross", "star", "hexagon", "triangle-down"];
  return { color: chartColors[index], dash: dashStyles[index % dashStyles.length], marker: markerStyles[index] };
}

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
      <ChartErrorBoundary>
        <Suspense fallback={<p className="chart-loading" role="status">Loading chart… Numeric values are available below.</p>}>
          <Plot
            data={props.data}
            layout={props.layout}
            config={{ displayModeBar: false, responsive: true, scrollZoom: false }}
            useResizeHandler
            style={{ width: "100%", height: "100%" }}
          />
        </Suspense>
      </ChartErrorBoundary>
    </div>
  );
}

export const chartLayout: Partial<Layout> = {
  autosize: true,
  height: 300,
  margin: { l: 58, r: 14, t: 12, b: 72 },
  font: { family: "Manrope, 'Segoe UI Variable', 'Segoe UI', sans-serif", color: "#263A53", size: 12 },
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  showlegend: true,
  legend: { orientation: "h", y: -0.24, x: 0, xanchor: "left", font: { size: 10 }, itemclick: "toggle", itemdoubleclick: "toggleothers" },
  hoverlabel: { bgcolor: "#263A53", bordercolor: "#263A53", font: { color: "#FFFFFF", size: 12 } },
  xaxis: { gridcolor: "#E1E4E8", zeroline: false, automargin: true, color: "#536378", tickfont: { size: 11 } },
  yaxis: { gridcolor: "#E1E4E8", zeroline: false, automargin: true, color: "#536378", tickfont: { size: 11 } },
};

export function AccessibleTable(props: { caption: string; children: ReactNode }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [overflows, setOverflows] = useState(false);

  useEffect(() => {
    const element = wrapRef.current;
    if (!element) return;
    const measure = () => setOverflows(element.scrollWidth > element.clientWidth + 1);
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      className="data-table-wrap"
      role={overflows ? "region" : undefined}
      aria-label={overflows ? props.caption : undefined}
      tabIndex={overflows ? 0 : undefined}
    >
      <table className="data-table">
        <caption>{props.caption}</caption>
        {props.children}
      </table>
    </div>
  );
}
