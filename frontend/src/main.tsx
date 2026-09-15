import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function App() {
  return (
    <main>
      <p className="eyebrow">Calibration-shift research engine</p>
      <h1>SHIFTGUARD</h1>
      <p>
        The Gate 1 CLI baseline is available. Browser experiments, calibration analysis,
        jobs, and agent tools are not yet implemented.
      </p>
      <a href="/api/v1/health">Check API health</a>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
