// Records the submission demo video and screenshots against the scripted local harness.
// Not part of the test suite: run with `npx playwright test --config playwright.demo.config.ts`.
import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

export default defineConfig({
  ...base,
  testDir: "../tests/demo",
  testMatch: "*.demo.ts",
  timeout: 20 * 60 * 1000,
  use: {
    ...base.use,
    viewport: { width: 1280, height: 800 },
    video: { mode: "on", size: { width: 1280, height: 800 } },
    screenshot: "off",
  },
});
