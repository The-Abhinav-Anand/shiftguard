import { randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(frontendRoot, "..");
const evidenceRoot = path.resolve(repoRoot, "..", "verification", "gate5");
const attemptDirectory = process.env.SG_GATE5_ATTEMPT_DIR || path.join(evidenceRoot, `attempt-${new Date().toISOString().replaceAll(/[:.]/g, "-")}-${randomUUID().slice(0, 8)}`);
process.env.SG_GATE5_ATTEMPT_DIR = attemptDirectory;
const screenshotDirectory = path.join(attemptDirectory, "screenshots");
mkdirSync(screenshotDirectory, { recursive: true });

const hostedBaseURL = process.env.SG_E2E_BASE_URL?.trim();
if (process.env.SG_E2E_BASE_URL && !hostedBaseURL) {
  throw new Error("SG_E2E_BASE_URL was explicitly set but is empty.");
}

const databasePath = path.join(attemptDirectory, "shiftguard.sqlite").replaceAll("\\", "/");
const pythonPath = path.join(repoRoot, ".venv", "Scripts", "python.exe");
const localHarnessEnv: Record<string, string> = {
  ...Object.fromEntries(Object.entries(process.env).filter((entry): entry is [string, string] => typeof entry[1] === "string")),
  SHIFTGUARD_ENVIRONMENT: "local",
  SHIFTGUARD_AGENT_ENABLED: "false",
  SHIFTGUARD_DB_URL: `sqlite:///${databasePath}`,
  SHIFTGUARD_ARTIFACT_ROOT: path.join(attemptDirectory, "artifacts"),
  SHIFTGUARD_EMBEDDED_WORKER: "true",
  OPENBLAS_NUM_THREADS: "1",
  OMP_NUM_THREADS: "1",
};
delete localHarnessEnv.SHIFTGUARD_AGENT_PROVIDER_MODE;
delete localHarnessEnv.SHIFTGUARD_ALLOW_TEST_SCRIPTED_PROVIDER;
delete localHarnessEnv.NEBIUS_API_KEY;

export default defineConfig({
  testDir: "../tests/e2e",
  testMatch: "test_*.spec.ts",
  globalSetup: "./scripts/e2e-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 15 * 60 * 1000,
  expect: { timeout: 12_000 },
  outputDir: path.join(attemptDirectory, "test-results"),
  reporter: [["list"], ["json", { outputFile: path.join(attemptDirectory, "playwright-report.json") }]],
  use: {
    baseURL: hostedBaseURL || "http://127.0.0.1:8765",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    actionTimeout: 15_000,
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    screenshot: "only-on-failure",
  },
  ...(hostedBaseURL ? {} : {
    webServer: {
      command: `"${pythonPath}" "${path.join(frontendRoot, "scripts", "e2e-server.py")}"`,
      cwd: repoRoot,
      url: "http://127.0.0.1:8765/health/live",
      timeout: 90_000,
      reuseExistingServer: false,
      env: localHarnessEnv,
    },
  }),
  metadata: {
    repoRoot,
    pythonPath,
    hosted: Boolean(hostedBaseURL),
    evidenceDirectory: attemptDirectory,
    screenshotDirectory,
    providerKind: hostedBaseURL ? "externally-supplied" : "scripted-test-harness",
    evidenceMode: hostedBaseURL ? "externally-supplied" : "scripted",
    liveProviderCalls: false,
    isolatedDatabase: hostedBaseURL ? "hosted mode; server isolation supplied externally" : databasePath,
  },
});
