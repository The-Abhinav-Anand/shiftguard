import { useEffect, useMemo, useState } from "react";
import type { MetricName, PresetName, StoredStressExperiment, StressPayload } from "./api/types";
import { api, isStressPayload } from "./api/client";
import { SelectedDiagnostics } from "./components/ResultDetails";
import { PresetResult } from "./components/PresetResult";
import { BudgetCurve } from "./components/charts/BudgetCurve";
import { DecisionLoss, costPairKey } from "./components/charts/DecisionLoss";
import { PatternVsRate } from "./components/charts/PatternVsRate";
import { Reliability } from "./components/charts/Reliability";
import { methodLabel, predictorLabel, scenarioLabel, shortId } from "./components/charts/shared";
import { useWorkbench } from "./hooks/useWorkbench";

const PRESETS: Array<{ value: PresetName; label: string; description: string }> = [
  { value: "bank-outage-50", label: "Bank outage · 50", description: "Approved default preset for a compact browser run." },
  { value: "bank-stress", label: "Bank stress", description: "Full persisted stress suite across the approved development configuration." },
  { value: "bank-baseline", label: "Bank baseline", description: "Baseline preset using the server's approved configuration." },
];

interface Selection {
  predictor: string;
  scenario: string;
  method: string;
  budget: number;
  metric: MetricName;
  cost: string;
}

function scenariosFor(payload: StressPayload, predictor: string): string[] {
  const prefix = `${predictor}__`;
  return Object.keys(payload.payloads.budget_curve.scenarios)
    .filter((key) => key.startsWith(prefix))
    .map((key) => key.slice(prefix.length));
}

function initialSelection(payload: StressPayload): Selection {
  const predictor = payload.config.predictors.includes("logistic_regression")
    ? "logistic_regression"
    : payload.config.predictors[0] ?? "";
  const scenarios = scenariosFor(payload, predictor);
  const scenario = scenarios.includes("history_block_0_50") ? "history_block_0_50" : scenarios[0] ?? "";
  const methods = Object.keys(payload.payloads.budget_curve.scenarios[`${predictor}__${scenario}`] ?? {});
  const method = methods.includes("target_temperature") ? "target_temperature" : methods[0] ?? "all";
  const points = payload.payloads.budget_curve.scenarios[`${predictor}__${scenario}`]?.[method] ?? [];
  const costRows = payload.payloads.decision_loss.scenarios[`${predictor}__${scenario}`]?.[method]?.cost_grid_losses ?? [];
  return {
    predictor,
    scenario,
    method,
    budget: points.some((point) => point.budget === 50) ? 50 : points[0]?.budget ?? 0,
    metric: "brier_score",
    cost: costRows.length ? costPairKey(costRows[0].fp_cost, costRows[0].fn_cost) : "all",
  };
}

function App() {
  const workbench = useWorkbench();
  const storedResult = workbench.workspace.cached_experiment;
  const experiment = storedResult && isStressPayload(storedResult.payload) ? storedResult as StoredStressExperiment : null;
  const [preset, setPreset] = useState<PresetName>("bank-outage-50");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [serverExperiments, setServerExperiments] = useState<Array<{ experiment_id: string; created_at: string }>>([]);
  const [healthError, setHealthError] = useState(false);
  const currentSelection = experiment ? selection ?? initialSelection(experiment.payload) : null;
  const scenarioOptions = experiment && currentSelection ? scenariosFor(experiment.payload, currentSelection.predictor) : [];
  const curveKey = currentSelection ? `${currentSelection.predictor}__${currentSelection.scenario}` : "";
  const methodOptions = experiment && currentSelection
    ? Object.keys(experiment.payload.payloads.budget_curve.scenarios[curveKey] ?? {})
    : [];
  const pointOptions = experiment && currentSelection
    ? experiment.payload.payloads.budget_curve.scenarios[curveKey]?.[currentSelection.method === "all" ? methodOptions[0] : currentSelection.method] ?? []
    : [];
  const selectedPreset = PRESETS.find((item) => item.value === preset) ?? PRESETS[0];

  useEffect(() => {
    if (experiment) setSelection(initialSelection(experiment.payload));
  }, [experiment?.experiment_id]);

  useEffect(() => {
    if (workbench.backend !== "online") return;
    let alive = true;
    const refresh = async () => {
      try {
        const { experiments } = await api.publishedExperiments();
        if (alive) {
          setServerExperiments(experiments);
          setHealthError(false);
        }
      } catch {
        if (alive) setHealthError(true);
      }
    };
    void refresh();
    return () => { alive = false; };
  }, [workbench.backend, experiment?.experiment_id]);

  const costOptions = useMemo(() => {
    if (!experiment || !currentSelection) return [];
    return experiment.payload.payloads.decision_loss.scenarios[curveKey]?.[currentSelection.method === "all" ? methodOptions[0] : currentSelection.method]?.cost_grid_losses ?? [];
  }, [currentSelection, curveKey, experiment]);

  const updateSelection = (patch: Partial<Selection>) => {
    if (!currentSelection) return;
    setSelection({ ...currentSelection, ...patch });
  };

  const changePredictor = (predictor: string) => {
    if (!experiment) return;
    const scenarios = scenariosFor(experiment.payload, predictor);
    const scenario = scenarios.includes(currentSelection?.scenario ?? "") ? currentSelection!.scenario : scenarios[0] ?? "";
    const methods = Object.keys(experiment.payload.payloads.budget_curve.scenarios[`${predictor}__${scenario}`] ?? {});
    const method = methods.includes(currentSelection?.method ?? "") ? currentSelection!.method : methods[0] ?? "all";
    const points = experiment.payload.payloads.budget_curve.scenarios[`${predictor}__${scenario}`]?.[method] ?? [];
    setSelection({
      predictor,
      scenario,
      method,
      budget: points.find((point) => point.budget === 50)?.budget ?? points[0]?.budget ?? 0,
      metric: currentSelection?.metric ?? "brier_score",
      cost: "all",
    });
  };

  const changeScenario = (scenario: string) => {
    if (!experiment || !currentSelection) return;
    const methods = Object.keys(experiment.payload.payloads.budget_curve.scenarios[`${currentSelection.predictor}__${scenario}`] ?? {});
    const method = methods.includes(currentSelection.method) ? currentSelection.method : methods[0] ?? "all";
    const points = experiment.payload.payloads.budget_curve.scenarios[`${currentSelection.predictor}__${scenario}`]?.[method] ?? [];
    setSelection({
      ...currentSelection,
      scenario,
      method,
      budget: points.find((point) => point.budget === currentSelection.budget)?.budget ?? points[0]?.budget ?? 0,
      cost: "all",
    });
  };

  return (
    <main className="app-shell">
      <header className="masthead">
        <a className="brand" href="#top" aria-label="SHIFTGUARD home"><span className="brand-mark" aria-hidden="true">S</span><span>SHIFTGUARD</span></a>
        <div className="masthead__right">
          <span className={`connection-pill connection-pill--${workbench.backend}`} role="status">
            <span className="status-dot" aria-hidden="true" />
            {workbench.backend === "checking" ? "Connecting" : workbench.backend === "online" ? "API connected" : "API unavailable"}
          </span>
          <span className="session-id" title={workbench.workspace.session?.session_id ?? "Session is being created"}>
            SESSION · {shortId(workbench.workspace.session?.session_id, 10)}
          </span>
          {workbench.backend === "offline" || (workbench.ready === false && workbench.backend !== "checking") ? <button className="text-button" onClick={() => void workbench.reconnect()}>Reconnect</button> : null}
        </div>
      </header>

      <section className="hero" id="top">
        <div className="hero__copy">
          <p className="eyebrow"><span className="eyebrow-line" /> CALIBRATION WORKBENCH <span className="version-tag">GATE 5 · BROWSER</span></p>
          <h1>See the shift.<br /><em>Trust the evidence.</em></h1>
          <p className="hero__lede">Run an approved bank preset, inspect what the server persisted, and keep the result beside its provenance.</p>
        </div>
        <div className="hero-index" aria-label="Development run identity"><span>DEVELOPMENT RUN</span><strong>31001</strong><small>Single seed · illustrative</small></div>
      </section>

      <section className="run-strip" aria-labelledby="run-heading">
        <div className="run-strip__intro">
          <p className="section-kicker">01 / Run control</p>
          <h2 id="run-heading">Start from an approved preset</h2>
          <p>{selectedPreset.description} The server fixes the development seed at 31001.</p>
        </div>
        <div className="run-controls">
          <label className="field-label" htmlFor="preset">Approved preset</label>
          <div className="run-controls__row">
            <select id="preset" value={preset} onChange={(event) => setPreset(event.target.value as PresetName)}>
              {PRESETS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <button
              className="button button--primary"
              onClick={() => void workbench.submitNew(preset)}
              disabled={!workbench.ready || workbench.backend !== "online" || Boolean(workbench.busyAction) || Boolean(workbench.workspace.pending_submission)}
            >
              {workbench.busyAction === "submit" ? <><span className="button-spinner" /> Sending…</> : "Submit run"}
              <span aria-hidden="true">↗</span>
            </button>
          </div>
          <div className="run-meta"><span>SERVER CONTROLLED</span><span>Same-origin API</span><span>New submit = new job identity</span></div>
        </div>
      </section>

      {workbench.errorNotice && (
        <section className="notice notice--error" role="alert">
          <span className="notice-icon" aria-hidden="true">!</span>
          <div><strong>{workbench.errorNotice.code}</strong><p>{workbench.errorNotice.message}</p></div>
          {workbench.workspace.pending_submission && workbench.workspace.session && workbench.ready && (
            <button className="button button--light" onClick={() => void workbench.retrySubmission()} disabled={Boolean(workbench.busyAction)}>
              Retry same submission
            </button>
          )}
        </section>
      )}
      {workbench.storageNotice && <p className="notice notice--storage" role="status">{workbench.storageNotice}</p>}
      {healthError && <p className="notice notice--storage" role="status">The experiment list is temporarily unavailable. Saved browser results remain usable.</p>}

      {workbench.workspace.pending_submission && !workbench.errorNotice && (
        <section className="notice notice--pending" role="status">
          <span className="button-spinner" />
          <div><strong>Submission response not confirmed</strong><p>Retry uses the same private idempotency key and cannot create a duplicate job.</p></div>
          <button className="button button--light" onClick={() => void workbench.retrySubmission()} disabled={Boolean(workbench.busyAction)}>Retry submit</button>
        </section>
      )}

      <section className="workspace-grid" aria-label="Job and result workspace">
        <aside className="job-rail" aria-labelledby="jobs-heading">
          <div className="rail-heading"><div><p className="section-kicker">02 / Execution</p><h2 id="jobs-heading">Job ledger</h2></div><span className="count-badge">{workbench.workspace.jobs.length.toString().padStart(2, "0")}</span></div>
          {workbench.workspace.jobs.length === 0 ? (
            <div className="empty-jobs"><span className="empty-ring" aria-hidden="true">↗</span><strong>No runs yet</strong><p>Your first submitted preset will appear here with live status and its own job ID.</p></div>
          ) : (
            <ol className="job-list">
              {[...workbench.workspace.jobs].reverse().map((job) => {
                const terminal = ["completed", "failed", "cancelled"].includes(job.status);
                const canCancel = ["queued", "running"].includes(job.status);
                return (
                  <li className="job-card" key={job.job_id}>
                    <div className="job-card__top"><span className={`job-status job-status--${job.status}`}>{job.status}</span><time>{new Date(job.created_at).toLocaleTimeString()}</time></div>
                    <strong>{PRESETS.find((item) => item.value === job.preset_name)?.label ?? job.preset_name}</strong>
                    <code className="job-id" title={job.job_id}>{job.job_id}</code>
                    <div className="job-card__foot">
                      <span>{job.experiment_id ? `Experiment · ${shortId(job.experiment_id, 11)}` : job.error_code ?? `Seed ${job.seed}`}</span>
                      {canCancel && <button className="text-button" onClick={() => void workbench.cancelJob(job)} disabled={job.cancel_requested || workbench.busyAction === `cancel:${job.job_id}`}>{job.cancel_requested ? "Cancel requested" : "Cancel"}</button>}
                      {terminal && job.experiment_id && <button className="text-button" onClick={() => void workbench.loadPublished(job.experiment_id!)} disabled={workbench.busyAction === "load-result"}>Open result</button>}
                    </div>
                    {terminal && <button className="text-button rerun-button" onClick={() => void workbench.submitNew(job.preset_name)} disabled={!workbench.ready || Boolean(workbench.busyAction) || Boolean(workbench.workspace.pending_submission)}>Rerun identical preset</button>}
                  </li>
                );
              })}
            </ol>
          )}
          <div className="rail-divider" />
          <div className="rail-heading rail-heading--small"><div><p className="section-kicker">PUBLISHED</p><h3>Server records</h3></div></div>
          {serverExperiments.length === 0 ? <p className="rail-empty">No published records found.</p> : (
            <ul className="published-list">
              {serverExperiments.slice(0, 5).map((item) => (
                <li key={item.experiment_id}>
                  <button onClick={() => void workbench.loadPublished(item.experiment_id)} disabled={workbench.busyAction === "load-result"}>
                    <span>{shortId(item.experiment_id, 13)}</span><time>{new Date(item.created_at).toLocaleDateString()}</time>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className="result-column">
          {!storedResult ? (
            <section className="welcome-panel" aria-labelledby="welcome-heading">
              <div className="welcome-art" aria-hidden="true"><span className="art-line art-line--one" /><span className="art-line art-line--two" /><span className="art-dot art-dot--one" /><span className="art-dot art-dot--two" /><span className="art-dot art-dot--three" /><span className="art-axis" /></div>
              <p className="section-kicker">03 / Evidence</p>
              <h2 id="welcome-heading">Your persisted result<br />will land here.</h2>
              <p>Submit a preset or open a published record. Metrics, calibration bins and operating costs will be read from its stored payload.</p>
              <div className="welcome-foot"><span className="welcome-spark" aria-hidden="true">✳</span><span>No series are generated in the browser.<br /><strong>First use is ready when you are.</strong></span></div>
            </section>
          ) : !experiment ? <PresetResult experiment={storedResult} /> : currentSelection && (
            <>
              <section className="result-heading" aria-labelledby="result-heading">
                <div><p className="section-kicker">03 / Persisted evidence</p><h2 id="result-heading">Experiment result</h2><p>Loaded from the server record · <code>{shortId(experiment.experiment_id, 18)}</code></p></div>
                <span className={`result-source result-source--${experiment.source}`}>{experiment.source === "fresh-run" ? "Fresh computation" : experiment.source === "server-cache" ? "Server-persisted cache" : "Browser-cached result"}</span>
              </section>
              <section className="filter-bar" aria-label="Result view filters">
                <label><span>Predictor</span><select value={currentSelection.predictor} onChange={(event) => changePredictor(event.target.value)}>{experiment.payload.config.predictors.map((item) => <option key={item} value={item}>{predictorLabel(item)}</option>)}</select></label>
                <label><span>Scenario</span><select value={currentSelection.scenario} onChange={(event) => changeScenario(event.target.value)}>{scenarioOptions.map((item) => <option key={item} value={item}>{scenarioLabel(item)}</option>)}</select></label>
                <label><span>Method</span><select value={currentSelection.method} onChange={(event) => updateSelection({ method: event.target.value, cost: "all" })}><option value="all">All methods</option>{methodOptions.map((item) => <option key={item} value={item}>{methodLabel(item)}</option>)}</select></label>
                <label><span>Budget · labels</span><select value={currentSelection.budget} onChange={(event) => updateSelection({ budget: Number(event.target.value) })}>{pointOptions.map((point) => <option key={point.budget} value={point.budget}>{point.budget}</option>)}</select></label>
                <label><span>Score view</span><select value={currentSelection.metric} onChange={(event) => updateSelection({ metric: event.target.value as MetricName })}><option value="brier_score">Brier score</option><option value="log_loss">Log loss</option></select></label>
                <label><span>Cost pair</span><select value={currentSelection.cost} onChange={(event) => updateSelection({ cost: event.target.value })}><option value="all">All persisted pairs</option>{costOptions.map((item) => <option key={costPairKey(item.fp_cost, item.fn_cost)} value={costPairKey(item.fp_cost, item.fn_cost)}>FP {item.fp_cost} · FN {item.fn_cost}</option>)}</select></label>
              </section>
              <p className="filter-note">Filters select records already in this experiment. Run configuration remains controlled by the approved preset; reliability and decision loss are persisted at budget 50.</p>
              <SelectedDiagnostics experiment={experiment} predictor={currentSelection.predictor} scenario={currentSelection.scenario} method={currentSelection.method} budget={currentSelection.budget} metric={currentSelection.metric} />
              <div className="chart-grid">
                <BudgetCurve payload={experiment.payload.payloads.budget_curve} predictor={currentSelection.predictor} scenario={currentSelection.scenario} method={currentSelection.method} metric={currentSelection.metric} selectedBudget={currentSelection.budget} />
                <PatternVsRate payload={experiment.payload.payloads.pattern_vs_rate} predictor={currentSelection.predictor} method={currentSelection.method} metric={currentSelection.metric} />
                <Reliability payload={experiment.payload.payloads.reliability} decisionLoss={experiment.payload.payloads.decision_loss} predictor={currentSelection.predictor} scenario={currentSelection.scenario} method={currentSelection.method} selectedBudget={currentSelection.budget} />
                <DecisionLoss payload={experiment.payload.payloads.decision_loss} predictor={currentSelection.predictor} scenario={currentSelection.scenario} method={currentSelection.method} selectedCost={currentSelection.cost} />
              </div>
            </>
          )}
        </div>
      </section>

      <section className="activity-panel" aria-labelledby="activity-heading">
        <div className="activity-heading"><div><p className="section-kicker">04 / Request facts</p><h2 id="activity-heading">Recent activity</h2></div><span>REQUESTS & RESULTS</span></div>
        {workbench.activities.length === 0 ? <p className="activity-empty">Server request and result facts will appear here. Capability credentials stay private.</p> : (
          <ol className="activity-list">
            {workbench.activities.map((row) => <li key={row.id}><time>{new Date(row.at).toLocaleTimeString()}</time><span className={`activity-kind activity-kind--${row.kind}`}>{row.kind}</span><code>{row.path}</code><p>{row.outcome}</p></li>)}
          </ol>
        )}
      </section>

      <footer className="page-footer"><span>SHIFTGUARD · CONTROLLED CALIBRATION EVIDENCE</span><span>Development output · seed 31001 · illustrative only</span></footer>
    </main>
  );
}

export default App;
