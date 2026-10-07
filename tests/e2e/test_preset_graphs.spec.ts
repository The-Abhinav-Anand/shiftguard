import { readFileSync } from "node:fs";
import path from "node:path";
import { test, expect, type Page } from "../../frontend/e2e/fixtures";
import type { StoredExperiment } from "../../frontend/src/api/types";

// Render-only snapshots of actual local Bank results, trimmed to fields consumed by this view.
// Scientific identity/hash verification remains covered by the backend suites.
const snapshots = JSON.parse(readFileSync(path.join(__dirname, "fixtures/preset-results.json"), "utf8"));
const saved = (id: string): StoredExperiment => ({
  ...snapshots[id],
  source: "server-cache",
}) as StoredExperiment;

type SavedCondition = {
  condition_id?: string;
  status: string;
  metrics?: {
    brier_score: number | null;
    log_loss: number | null;
    reliability?: Array<{ lower: number; upper: number; count: number; mean_probability: number | null; positive_fraction: number | null }> | null;
  } | null;
};

async function plotTrace(page: Page, testId: string, traceIndex: number) {
  const graph = page.getByTestId(testId).locator(".js-plotly-plot");
  await expect(graph).toBeVisible();
  return graph.evaluate((element, index) => {
    const traces = (element as HTMLElement & { data: Array<{ x?: unknown; y?: unknown }> }).data;
    return traces[index];
  }, traceIndex);
}

for (const id of ["e90c4adbda3d53664a823f84", "dd4c68fc6c73b128e23cfd97"]) {
  test(`saved preset ${id} renders exact metric and reliability traces`, async ({ page }, info) => {
    const experiment = saved(id);
    await page.addInitScript((record) => {
      localStorage.setItem("shiftguard.browser-workspace.v1", JSON.stringify({
        version: 1,
        session: null,
        jobs: [],
        pending_submission: null,
        cached_experiment: record,
      }));
    }, experiment);

    await page.goto("/demo");
    await expect(page.getByRole("heading", { name: "Published preset result" })).toBeVisible();
    await expect(page.getByTestId("preset-plot-brier-score")).toBeVisible();
    await expect(page.getByTestId("preset-plot-log-loss")).toBeVisible();

    const payload = experiment.payload as unknown as {
      conditions?: Record<string, SavedCondition>;
      metrics?: SavedCondition["metrics"];
    };
    const rows: Array<[string, SavedCondition]> = payload.conditions
      ? Object.entries(payload.conditions)
      : [["baseline", { status: "scored", metrics: payload.metrics ?? null }]];
    const expected = (metric: "brier_score" | "log_loss") => rows.map(([, row]) =>
      row.status === "scored" ? row.metrics?.[metric] ?? null : null,
    );

    expect((await plotTrace(page, "preset-plot-brier-score", 0)).y).toEqual(expected("brier_score"));
    expect((await plotTrace(page, "preset-plot-log-loss", 0)).y).toEqual(expected("log_loss"));

    const selected = rows.find(([, row]) => row.status === "scored" && row.metrics?.reliability?.length);
    expect(selected).toBeTruthy();
    const selector = page.getByRole("combobox", { name: "Reliability condition" });
    await selector.selectOption(selected![1].condition_id ?? experiment.experiment_id);
    const bins = selected![1].metrics!.reliability!;
    const curve = await plotTrace(page, "preset-plot-reliability", 1);
    expect(curve.x).toEqual(bins.map((bin) => bin.mean_probability));
    expect(curve.y).toEqual(bins.map((bin) => bin.positive_fraction));
    expect(bins.some((bin) => bin.mean_probability === null || bin.positive_fraction === null)).toBe(true);

    const exactTable = page.getByRole("table", { name: "Persisted reliability bins (exact saved values)" });
    await expect(exactTable.locator("tbody tr")).toHaveCount(bins.length);
    await expect(page.getByRole("table", { name: "Persisted Brier score by condition (exact saved values)" }).locator("tbody tr")).toHaveCount(rows.length);
    await page.getByRole("heading", { name: "Published preset result" }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(info.config.metadata.screenshotDirectory, `preset-${id}.png`), animations: "disabled" });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}
