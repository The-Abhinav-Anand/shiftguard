import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MetricName, PresetName, PublishedExperimentSummary, StoredExperiment, StoredStressExperiment, StressPayload } from "../api/types";
import { api, isStressPayload } from "../api/client";
import { SelectedDiagnostics } from "../components/ResultDetails";
import { PresetResult } from "../components/PresetResult";
import { AgentPanel } from "../components/AgentPanel";
import { GeneralChatPanel } from "../components/GeneralChatPanel";
import { BudgetCurve } from "../components/charts/BudgetCurve";
import { DecisionLoss, costPairKey } from "../components/charts/DecisionLoss";
import { PatternVsRate } from "../components/charts/PatternVsRate";
import { Reliability } from "../components/charts/Reliability";
import { methodLabel, predictorLabel, scenarioLabel, shortId } from "../components/charts/shared";
import { Brand } from "../components/brand/Brand";
import { useAgent } from "../hooks/useAgent";
import { useWorkbench } from "../hooks/useWorkbench";

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

export default function BenchmarkWorkbench() {
  const workbench = useWorkbench();
  const agent = useAgent({
    credentials: workbench.workspace.session,
    onExperimentSelected: (experimentId) => { void workbench.loadPublished(experimentId); },
  });
  const storedResult = workbench.workspace.cached_experiment;
  const experiment = storedResult && isStressPayload(storedResult.payload) ? storedResult as StoredStressExperiment : null;
  const [preset, setPreset] = useState<PresetName>("bank-outage-50");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [serverExperiments, setServerExperiments] = useState<PublishedExperimentSummary[]>([]);
  const [healthError, setHealthError] = useState(false);
  const [resultsLoading, setResultsLoading] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [assistantMode, setAssistantMode] = useState<"results" | "general">("results");
  const [activityOpen, setActivityOpen] = useState(false);
  const [focusAttempt, setFocusAttempt] = useState<{ experimentId: string; previous: StoredExperiment | null; settled: boolean } | null>(null);
  const resultRequest = useRef(0);
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
  const chatDisabledReason = workbench.backend !== "online" || !workbench.ready
    ? "Connect to the server before using general chat."
    : !agent.agentStatus
      ? "Checking general chat availability…"
      : !agent.agentStatus.general_chat_enabled
        ? "General chat is paused."
        : !agent.agentStatus.available
          ? "Chat provider unavailable."
          : !workbench.workspace.session
            ? "A server session is required."
            : null;

  useEffect(() => {
    if (experiment) setSelection(initialSelection(experiment.payload));
  }, [experiment?.experiment_id]);

  const refreshSavedResults = useCallback(async (): Promise<PublishedExperimentSummary[] | null> => {
    const requestId = ++resultRequest.current;
    setResultsLoading(true);
    try {
      const { experiments } = await api.publishedExperiments();
      const newestFirst = [...experiments].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
      if (requestId === resultRequest.current) {
        setServerExperiments(newestFirst);
        setHealthError(false);
      }
      return newestFirst;
    } catch {
      if (requestId === resultRequest.current) setHealthError(true);
      return null;
    } finally {
      if (requestId === resultRequest.current) setResultsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (workbench.backend === "online") void refreshSavedResults();
    else if (workbench.backend === "offline") setResultsLoading(false);
  }, [workbench.backend, experiment?.experiment_id, refreshSavedResults]);

  const displayedResultRef = useRef(storedResult);
  displayedResultRef.current = storedResult;

  useEffect(() => {
    if (!focusAttempt) return;
    const replaced = storedResult !== focusAttempt.previous && storedResult?.experiment_id === focusAttempt.experimentId;
    if (replaced) {
      setFocusAttempt(null);
      requestAnimationFrame(() => {
        const heading = document.querySelector<HTMLElement>("#results .result-heading h2, #results .detail-card h2, #results .welcome-panel h2");
        if (!heading) return;
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
        heading.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
      });
    } else if (focusAttempt.settled) {
      setFocusAttempt(null);
    }
  }, [focusAttempt, storedResult]);

  const openSavedResult = (experimentId: string) => {
    const attempt = { experimentId, previous: displayedResultRef.current, settled: false };
    setFocusAttempt(attempt);
    const settle = () => setFocusAttempt((current) => current?.experimentId === experimentId ? { ...current, settled: true } : current);
    void workbench.loadPublished(experimentId).then(settle, settle);
  };

  const costOptions = useMemo(() => {
    if (!experiment || !currentSelection) return [];
    return experiment.payload.payloads.decision_loss.scenarios[curveKey]?.[currentSelection.method === "all" ? methodOptions[0] : currentSelection.method]?.cost_grid_losses ?? [];
  }, [currentSelection, curveKey, experiment]);

  const latestSavedRecord = serverExperiments[0];
  const latestJob = workbench.workspace.jobs[workbench.workspace.jobs.length - 1];
  const failedJobs = workbench.workspace.jobs.filter((job) => job.status === "failed").length;
  const activeJobs = workbench.workspace.jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  const hasActiveSubmission = Boolean(workbench.workspace.pending_submission) || activeJobs > 0;
  const latestRecovery = [...workbench.activities].reverse().find((row) => row.kind === "recovery");
  const latestCancellation = [...workbench.activities].reverse().find((row) => row.path.endsWith("/cancel"));
  const selectedWarnings: string[] = [];
  const displayedMethods = currentSelection?.method === "all" ? methodOptions : currentSelection ? [currentSelection.method] : [];
  for (const method of displayedMethods) {
    if (!experiment || !currentSelection) continue;
    const condition = experiment.payload.conditions[`${curveKey}__b${currentSelection.budget}__${method}`];
    const point = experiment.payload.payloads.budget_curve.scenarios[curveKey]?.[method]?.find((item) => item.budget === currentSelection.budget);
    const prefix = currentSelection.method === "all" ? `${methodLabel(method)}: ` : "";
    const warn = (message: string) => selectedWarnings.push(prefix + message);
    if (!point?.available || point[currentSelection.metric] == null) {
      warn("The selected score is unavailable in the saved record; no value is substituted.");
    }
    if (!condition) {
      warn("Condition details are unavailable in the saved record.");
      continue;
    }
    if (condition.status !== "scored") warn(`Condition status: ${condition.status}.`);
    if (condition.fallback_reason) warn(`Fallback: ${condition.fallback_reason}.`);
    else if (condition.fallback_chain.length) warn(`Fallback chain: ${condition.fallback_chain.join(" → ")}.`);
    if (condition.unique_fit_failures > 0) warn(`Unique fit failures: ${condition.unique_fit_failures}.`);
    if (condition.unique_prediction_failures > 0) warn(`Unique prediction failures: ${condition.unique_prediction_failures}.`);
    const sparse = condition.sparse_bin_diagnostics;
    if (sparse?.affected_fallback_rows) warn(`Affected fallback rows: ${sparse.affected_fallback_rows}.`);
    if (sparse?.sparse_prediction_failures) warn(`Sparse prediction failures: ${sparse.sparse_prediction_failures}.`);
  }

  useEffect(() => {
    if (hasActiveSubmission) setHistoryOpen(true);
  }, [hasActiveSubmission]);

  useEffect(() => {
    if (latestCancellation) setActivityOpen(true);
  }, [latestCancellation?.id]);

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
    <main className="workbench-page" id="main-content">
      <header className="masthead">
        <Brand />
        <nav className="workbench-nav" aria-label="Main navigation">
          <a href="#results">Results</a>
          <a href="/about">About SHIFTGUARD</a>
        </nav>
        <div className="masthead__right">
          <span className={`connection-pill connection-pill--${workbench.backend}`} role="status">
            <span className="status-dot" aria-hidden="true" />
            {workbench.backend === "checking" ? "Connecting" : workbench.backend === "online" ? "API connected" : "API unavailable"}
          </span>
          <details className="session-disclosure">
            <summary className="session-id" title={workbench.workspace.session?.session_id ?? "Session is being created"}>
              SESSION · {shortId(workbench.workspace.session?.session_id, 10)}
            </summary>
            <code>{workbench.workspace.session?.session_id ?? "Session is being created"}</code>
          </details>
          {workbench.backend === "offline" || (workbench.ready === false && workbench.backend !== "checking") ? <button className="text-button" onClick={() => void workbench.reconnect()}>Reconnect</button> : null}
        </div>
      </header>

      <section className="workbench-heading" aria-labelledby="workbench-title">
        <div>
          <p className="section-kicker">PRELOADED BANK DATASET · 41,188 ROWS · FROZEN HASH VERIFIED</p>
          <h1 id="workbench-title">Bank calibration workbench</h1>
          <p className="workbench-title-detail">Preloaded official Bank data · approved analyses · persisted results.</p>
          <p>Choose an approved analysis, run it, then inspect or reopen its saved result. Development seed 31001.</p>
        </div>
        <a className="button button--quiet" href="/about">About SHIFTGUARD</a>
      </section>

      <ol className="workflow-steps" aria-label="Three steps to a saved analysis">
        <li><span className="workflow-step__number">1</span><span><strong>Preloaded Bank dataset</strong><small>41,188 rows · frozen hash verified</small></span></li>
        <li><span className="workflow-step__number">2</span><span><strong>Choose approved analysis</strong><small>Bank outage · 50 selected by default</small></span></li>
        <li><span className="workflow-step__number">3</span><span><strong>Run analysis or open a saved record</strong><small>Results come from persisted server evidence</small></span></li>
      </ol>

      <section className="run-strip" aria-labelledby="run-heading">
        <div className="run-strip__intro">
          <p className="section-kicker">STEP 2 · APPROVED ANALYSIS</p>
          <h2 id="run-heading">Choose an approved analysis</h2>
          <p>{selectedPreset.description} Run configuration and the development seed are server controlled.</p>
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
              aria-label="Submit run"
            >
              {workbench.busyAction === "submit" ? <><span className="button-spinner" /> Starting…</> : "Run analysis"}
              <span aria-hidden="true">↗</span>
            </button>
          </div>
          <div className="run-actions">
            {latestSavedRecord && <button className="button button--quiet" type="button" onClick={() => { void refreshSavedResults().then((records) => { if (records?.[0]) openSavedResult(records[0].experiment_id); }); }} disabled={workbench.backend !== "online" || resultsLoading || workbench.busyAction === "load-result"}>Open latest saved record</button>}
            <a className="button button--quiet" href="#results">Go to results</a>
            <span className="run-meta">New submit creates a new job identity.</span>
          </div>
        </div>
      </section>

      <section className="saved-results-panel" aria-labelledby="saved-results-heading">
        <div className="saved-results-panel__header">
          <div><p className="section-kicker">PERSISTED SERVER RECORDS</p><h2 id="saved-results-heading">Saved results</h2></div>
          <button className="button button--quiet" type="button" onClick={() => void refreshSavedResults()} disabled={workbench.backend !== "online" || resultsLoading}>
            {resultsLoading ? "Loading saved results…" : healthError ? "Retry saved results" : "Refresh saved results"}
          </button>
        </div>
        <p className="saved-results-panel__note">Choose a saved record to display below. The approved analysis above applies to new runs.</p>
        {resultsLoading && <p role="status">Loading saved results…</p>}
        {healthError && <p className="saved-results-panel__status" role="alert">The saved-results list could not be loaded. Retry to check the server again.</p>}
        {!resultsLoading && !healthError && serverExperiments.length === 0 && <p className="saved-results-panel__status" role="status">No saved results are available yet.</p>}
        {serverExperiments.length > 0 && (
          <ul className="saved-results-list">
            {serverExperiments.map((item) => (
              <li key={item.experiment_id}>
                <button type="button" onClick={() => openSavedResult(item.experiment_id)} disabled={workbench.busyAction === "load-result"} aria-pressed={storedResult?.experiment_id === item.experiment_id}>
                  <code>{item.experiment_id}</code><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>
                  <span>{storedResult?.experiment_id === item.experiment_id ? "Displayed" : "Open result"}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {workbench.backend === "offline" && <p className="api-guidance" role="status">The API is unavailable. Start the local service with <code>.\scripts\start-local.ps1</code>, then select Reconnect.</p>}

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
      {workbench.busyAction === "load-result" && <p className="notice notice--loading" role="status">Opening saved evidence. The currently displayed result remains available until the replacement loads.</p>}

      {workbench.workspace.pending_submission && !workbench.errorNotice && (
        <section className="notice notice--pending" role="status">
          <span className="button-spinner" />
          <div><strong>Submission response not confirmed</strong><p>Retry uses the same private idempotency key and cannot create a duplicate job.</p></div>
          <button className="button button--light" onClick={() => void workbench.retrySubmission()} disabled={Boolean(workbench.busyAction)}>Retry submit</button>
        </section>
      )}

      <section className="workspace-grid" id="evidence" aria-label="Persisted experiment result">
        <div className="result-column" id="results" aria-label="Persisted experiment evidence">
          {!storedResult ? (
            <section className="welcome-panel" aria-labelledby="welcome-heading">
              <p className="section-kicker">STEP 3 · SAVED RESULT</p>
              <h2 id="welcome-heading">Your saved result appears here</h2>
              <p>Run the selected analysis or open the latest saved server record. Charts, tables, null values, and diagnostics are read from its persisted payload.</p>
            </section>
          ) : !experiment ? <PresetResult experiment={storedResult} /> : currentSelection && (
            <>
              <section className="result-heading" aria-labelledby="result-heading">
                <div><p className="section-kicker">03 / Persisted evidence</p><h2 id="result-heading">Experiment result</h2><p>Loaded from the server record · <code>{shortId(experiment.experiment_id, 18)}</code></p></div>
                <span className={`result-source result-source--${experiment.source}`}>{experiment.source === "fresh-run" ? "Fresh computation" : experiment.source === "server-cache" ? "Server-persisted cache" : "Browser-cached result"}</span>
              </section>
              <details className="filter-disclosure">
                <summary>Analysis options · {predictorLabel(currentSelection.predictor)} · {scenarioLabel(currentSelection.scenario)} · {currentSelection.budget} labels · {currentSelection.metric === "brier_score" ? "Brier score" : "Log loss"}</summary>
                <section className="filter-bar" aria-label="Result view filters">
                  <label><span>Predictor</span><select value={currentSelection.predictor} onChange={(event) => changePredictor(event.target.value)}>{experiment.payload.config.predictors.map((item) => <option key={item} value={item}>{predictorLabel(item)}</option>)}</select></label>
                  <label><span>Scenario</span><select value={currentSelection.scenario} onChange={(event) => changeScenario(event.target.value)}>{scenarioOptions.map((item) => <option key={item} value={item}>{scenarioLabel(item)}</option>)}</select></label>
                  <label><span>Method</span><select value={currentSelection.method} onChange={(event) => updateSelection({ method: event.target.value, cost: "all" })}><option value="all">All methods</option>{methodOptions.map((item) => <option key={item} value={item}>{methodLabel(item)}</option>)}</select></label>
                  <label><span>Budget · labels</span><select value={currentSelection.budget} onChange={(event) => updateSelection({ budget: Number(event.target.value) })}>{pointOptions.map((point) => <option key={point.budget} value={point.budget}>{point.budget}</option>)}</select></label>
                  <label><span>Score view</span><select value={currentSelection.metric} onChange={(event) => updateSelection({ metric: event.target.value as MetricName })}><option value="brier_score">Brier score</option><option value="log_loss">Log loss</option></select></label>
                  <label><span>Cost pair</span><select value={currentSelection.cost} onChange={(event) => updateSelection({ cost: event.target.value })}><option value="all">All persisted pairs</option>{costOptions.map((item) => <option key={costPairKey(item.fp_cost, item.fn_cost)} value={costPairKey(item.fp_cost, item.fn_cost)}>FP {item.fp_cost} · FN {item.fn_cost}</option>)}</select></label>
                </section>
                <p className="filter-note">These controls select saved records. The approved preset controls each run; reliability and decision loss remain fixed at 50 labels.</p>
              </details>
              {selectedWarnings.length > 0 && <p className="notice notice--scientific" role="status"><strong>Saved condition needs attention.</strong> {selectedWarnings.join(" ")}</p>}
              <details className="scientific-disclosure">
                <summary>Metrics, diagnostics, and run provenance{selectedWarnings.length > 0 ? " · attention required" : ""}</summary>
                <SelectedDiagnostics experiment={experiment} predictor={currentSelection.predictor} scenario={currentSelection.scenario} method={currentSelection.method} budget={currentSelection.budget} metric={currentSelection.metric} />
              </details>
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

      <details className="job-history" id="jobs" open={historyOpen} onToggle={(event) => setHistoryOpen(event.currentTarget.open)}>
        <summary>
          <span>Job history and saved records <span className="count-badge">{workbench.workspace.jobs.length.toString().padStart(2, "0")}</span></span>
          <span className="job-history__state">
            {latestJob && <>Latest run: <span className={`job-status job-status--${latestJob.status}`}>{latestJob.status}</span>{latestJob.error_code ? ` · ${latestJob.error_code}` : ""}</>}
            {failedJobs > 0 && <span className="job-history__warning"> · {failedJobs} failed</span>}
            {activeJobs > 0 && <span> · {activeJobs} active</span>}
          </span>
        </summary>
        <aside className="job-rail" aria-labelledby="jobs-heading">
          <div className="rail-heading"><div><p className="section-kicker">SAVED RUNS</p><h2 id="jobs-heading">Job ledger</h2></div></div>
          {workbench.workspace.jobs.length === 0 ? (
            <div className="empty-jobs"><strong>No runs yet</strong><p>Your submitted analyses appear here with their server job IDs and statuses.</p></div>
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
                      {terminal && job.experiment_id && <button className="text-button" onClick={() => openSavedResult(job.experiment_id!)} disabled={workbench.busyAction === "load-result"}>Open result</button>}
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
              {serverExperiments.map((item) => (
                <li key={item.experiment_id}>
                  <button onClick={() => openSavedResult(item.experiment_id)} disabled={workbench.busyAction === "load-result"}>
                    <span>{shortId(item.experiment_id, 13)}</span><time>{new Date(item.created_at).toLocaleDateString()}</time>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </details>

      <div className="assistant-mode-picker" role="group" aria-label="Choose assistant">
        <button type="button" aria-pressed={assistantMode === "general"} onClick={() => setAssistantMode("general")}>General chat</button>
        <button type="button" aria-pressed={assistantMode === "results"} onClick={() => setAssistantMode("results")}>Results assistant</button>
      </div>
      <div className="assistant-panel" hidden={assistantMode !== "general"}>
        <GeneralChatPanel
          credentials={workbench.workspace.session}
          enabled={chatDisabledReason === null}
          disabledReason={chatDisabledReason}
          ordinaryBudget={agent.agentStatus?.ordinary_budget}
        />
      </div>
      <div className="assistant-panel" hidden={assistantMode !== "results"}>
        <AgentPanel
          agentStatus={agent.agentStatus}
          activeRequest={agent.activeRequest}
          recoveryIntent={agent.recoveryIntent}
          storageError={agent.storageError}
          isSubmitting={agent.isSubmitting}
          error={agent.error}
          sessionExpired={agent.sessionExpired}
          canRetry={agent.canRetry}
          onSubmitQuery={(prompt) => { void agent.submitQuery(prompt); }}
          onRetryQuery={() => { void agent.retryQuery(); }}
          onReconnect={() => { void workbench.reconnect(); }}
          onSelectExperiment={(experimentId) => { void workbench.loadPublished(experimentId); }}
          onClear={agent.clearRequest}
        />
      </div>

      {latestRecovery && <p className="activity-recovery" role="status">Recent recovery: {latestRecovery.outcome}</p>}
      <details className="activity-disclosure" id="activity" open={activityOpen} onToggle={(event) => setActivityOpen(event.currentTarget.open)}>
        <summary>Recent activity · {workbench.activities.length} events</summary>
        <section className="activity-panel" aria-labelledby="activity-heading">
          <div className="activity-heading"><div><p className="section-kicker">REQUEST FACTS</p><h2 id="activity-heading">Recent activity</h2></div><span>REQUESTS & RESULTS</span></div>
          {workbench.activities.length === 0 ? <p className="activity-empty">Server request and result facts will appear here. Capability credentials stay private.</p> : (
            <ol className="activity-list">
              {workbench.activities.map((row) => <li key={row.id}><time>{new Date(row.at).toLocaleTimeString()}</time><span className={`activity-kind activity-kind--${row.kind}`}>{row.kind}</span><code>{row.path}</code><p>{row.outcome}</p></li>)}
            </ol>
          )}
        </section>
      </details>

      <footer className="page-footer"><span>SHIFTGUARD · BANK BENCHMARK</span><span>Single-seed development evidence · illustrative only</span></footer>
    </main>
  );
}
