# Frontend results correction - 5 October 2026

The ordinary preloaded engine and saved results are available at http://127.0.0.1:8000/. The default outage and baseline results now display three graphs before the diagnostic table: Brier score by condition, log loss by condition, and the selected condition's reliability curve.

## Using the results

1. Open the local app. Saved results are visible beside the analysis controls.
2. Select **Open** on a saved run. The page scrolls to and focuses **Published preset result** after that specific result finishes loading.
3. Read the score graphs and select a condition for its reliability curve. Exact values remain available in accessible tables.
4. Use **Results** or **Go to results** to return to the result section. **Latest** refreshes the saved-result list before selecting a run.

Opening a saved run reads persisted artifacts; it does not submit a new experiment. No result is automatically selected on an empty initial page.

## Corrected behavior

| Defect | Correction |
| --- | --- |
| Default outage/baseline results showed only a table | Added three graphs from the actual persisted scores and reliability bins |
| Saved runs were hidden in folded history | Added visible saved-result controls with loading, retry and empty states |
| Opening a saved run left the viewport below its graphs | Focus and scroll occur only after the requested result replaces the previous selection |
| Latest selection could use stale records | Refresh the saved-result list before opening the latest run |

Null or unscored metrics are not converted into zero scores. Empty reliability bins remain gaps. Condition identity, fallback/provenance information and adverse outcomes remain visible. Reduced motion, accessible exact-value tables and a narrow mobile viewport are covered.

## Source and verification

Application changes: `PresetResult.tsx`, `PresetCharts.tsx`, `PresetCharts.css`, `BenchmarkWorkbench.tsx`, and `workbench.css`; two browser test files and a compact persisted-result fixture were added. Generated static assets were rebuilt.

Authoritative evidence: [`checkpoint.json`](../../verification/frontend-results-20261004/checkpoint.json), [`final-source.json`](../../verification/frontend-results-20261004/final-source.json), and [`runtime-20261005.json`](../../verification/frontend-results-20261004/runtime-20261005.json).

Final correction manifest digest: `7928447b18b9c9d5e2b68014450d6b58292647ba17a2b017caea5b2f0bec96b3`.

| Check | Actual result |
| --- | --- |
| Ordinary localhost browser: existing normal product cases plus preset graphs and discovery | 6 passed, 0 failed/skipped/flaky; 15.5 seconds |
| `tests/integration/test_static_boundaries.py` | 5 passed, 0 skipped; exit 0; 2 dependency warnings |
| `npm run typecheck` | PASS, exit 0 |
| `npm run build` and dist/static byte parity | PASS; existing large Plotly/Three.js chunk warning retained |
| GPT-6 Astra xhigh focused review | PASS; code read only; reviewed production hashes still match |
| Browser observation after restarting the existing local launcher | Three default-result graphs rendered; result heading focused; no console errors |

Browser evidence is in `browser2/playwright-report.json` and `browser2.log`. The initial import-resolution test collection failure remains in `browser.log`; test imports were corrected before the successful attempt. The final manifest explicitly records those test-only changes after the first source freeze.

The prior 611-test full suite belongs to the earlier exact Gate 6 source checkpoint; it was not rerun for this frontend correction. Backend and protected client files remain unchanged (96 compared files), as do accepted Gates 0-5 and applied migrations. Earlier Gate 6 evidence and original blocker verdicts remain intact.

## Remaining checkpoint

No active writer, source commit or deployment. Gate 6 remains **PENDING**. The user deferred Nebius credentials and live A7 verification on 4 October; no provider calls were made. Resume that bounded step only when the user resumes it and supplies the required local access and explicit call/token allowance. Current local results require neither a provider key nor the assistant.

Prior governance bytes are preserved in `../../verification/frontend-results-20261004/governance-before-20261005/`.
