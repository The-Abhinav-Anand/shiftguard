import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(frontendRoot, "..");
const outerRoot = path.resolve(repoRoot, "..");

const previewValue = process.env.SG_REFRESH_PREVIEW_URL?.trim();
if (!previewValue) {
  throw new Error("Set SG_REFRESH_PREVIEW_URL to the explicit loopback Vite preview URL.");
}

let preview: URL;
try {
  preview = new URL(previewValue);
} catch {
  throw new Error("SG_REFRESH_PREVIEW_URL must be a valid loopback URL.");
}

if (
  preview.protocol !== "http:" ||
  !["127.0.0.1", "localhost", "[::1]", "::1"].includes(preview.hostname) ||
  preview.username ||
  preview.password ||
  preview.pathname !== "/" ||
  preview.search ||
  preview.hash
) {
  throw new Error("SG_REFRESH_PREVIEW_URL must be an HTTP loopback origin without credentials, path, query, or fragment.");
}

const requestedReportRoot = process.env.SG_REFRESH_ATTEMPT_DIR?.trim();
if (process.env.SG_REFRESH_ATTEMPT_DIR !== undefined && !requestedReportRoot) {
  throw new Error("SG_REFRESH_ATTEMPT_DIR was set but is empty.");
}
const reportRoot = path.resolve(
  requestedReportRoot || path.join(
    outerRoot,
    "verification",
    "product-execution-20261001",
    "frontend-cleanup-major-01",
    "luna-tests",
  ),
);
const screenshotDirectory = path.join(reportRoot, "screenshots");
mkdirSync(screenshotDirectory, { recursive: true });

export default defineConfig({
  testDir: "../tests/e2e",
  testMatch: ["test_product_refresh.spec.ts", "test_refresh_faults.spec.ts"],
  globalSetup: undefined,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 8_000 },
  outputDir: path.join(reportRoot, "test-results"),
  reporter: [
    ["list"],
    ["json", { outputFile: path.join(reportRoot, "playwright-report.json") }],
  ],
  use: {
    baseURL: preview.origin,
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    screenshot: "only-on-failure",
  },
  metadata: {
    reportRoot,
    screenshotDirectory,
    previewOrigin: preview.origin,
    previewMode: "loopback static Vite preview; API route aborts are transport simulation; no backend, seed, provider, or global setup",
    liveProviderCalls: false,
  },
});
