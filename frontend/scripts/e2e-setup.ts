import { spawn } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { FullConfig } from "@playwright/test";
import { setTimeout as delay } from "node:timers/promises";

export default async function setup(config: FullConfig) {
  const { hosted, repoRoot, pythonPath, evidenceDirectory, isolatedDatabase } = config.metadata;
  if (hosted) return;
  const source = await readFile(path.join(repoRoot, "configs", "bank-stress.yaml"), "utf8");
  const configFile = path.join(evidenceDirectory, "seed-stress.yaml");
  const artifactRoot = path.join(evidenceDirectory, "artifacts");
  await writeFile(configFile, `${source}\nartifact_root: ${JSON.stringify(artifactRoot)}\n`);
  const databaseURL = `sqlite:///${isolatedDatabase}`;
  // Use the existing CLI unchanged. Both this persisted fixture and browser jobs use development seed 31001.
  const run = spawn(pythonPath, ["-c", "from shiftguard.cli import main; main()", "--db-url", databaseURL, "run", "--config", configFile], {
    cwd: repoRoot, windowsHide: true,
    env: { ...process.env, SHIFTGUARD_DB_URL: databaseURL, SHIFTGUARD_ARTIFACT_ROOT: artifactRoot, OPENBLAS_NUM_THREADS: "1", OMP_NUM_THREADS: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  run.stdout.on("data", (data) => { stdout += data; });
  run.stderr.on("data", (data) => { stderr += data; });
  const timer = setTimeout(() => run.kill(), 10 * 60 * 1000);
  const status = await new Promise<number | null>((resolve, reject) => { run.on("error", reject); run.on("close", resolve); });
  clearTimeout(timer);
  await writeFile(path.join(evidenceDirectory, "seed-cli.log"), stdout + stderr);
  if (status !== 0) {
    await writeFile(path.join(evidenceDirectory, "server.stop"), "seed failed");
    throw new Error(`Existing CLI seed failed (${status}); see ${path.join(evidenceDirectory, "seed-cli.log")}`);
  }
  process.stdout.write(`Isolated CLI seed complete. Evidence: ${evidenceDirectory}\n`);
  // The Windows sandbox can leave Python descendants behind when taskkill targets the shell.
  // Stop the test server itself before Playwright tears down its command process.
  return async () => {
    await writeFile(path.join(evidenceDirectory, "server.stop"), "tests finished");
    for (let attempt = 0; attempt < 50; attempt += 1) {
      try { await fetch("http://127.0.0.1:8765/health/live", { signal: AbortSignal.timeout(1000) }); }
      catch { return; }
      await delay(200);
    }
    throw new Error("Managed FastAPI server did not stop after test teardown");
  };
}
