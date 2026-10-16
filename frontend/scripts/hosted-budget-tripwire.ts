import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

interface BudgetReading {
  utc_day: string;
  calls_used: number;
  tokens_committed: number;
}

async function readBudget(origin: string): Promise<BudgetReading> {
  const url = new URL("/api/v1/agent/status", origin).toString();
  const response = await fetch(url, { signal: AbortSignal.timeout(20_000), headers: { accept: "application/json" } });
  if (!response.ok) throw new Error(`Budget tripwire: GET /api/v1/agent/status returned HTTP ${response.status}.`);
  const body = (await response.json()) as { ordinary_budget?: Partial<BudgetReading> | null };
  const budget = body?.ordinary_budget;
  if (!budget || typeof budget !== "object") throw new Error("Budget tripwire: ordinary_budget is missing or null; failing closed.");
  const { utc_day, calls_used, tokens_committed } = budget;
  if (typeof utc_day !== "string" || !Number.isInteger(calls_used) || !Number.isInteger(tokens_committed)) {
    throw new Error("Budget tripwire: ordinary_budget lacks utc_day, calls_used or tokens_committed; failing closed.");
  }
  return { utc_day, calls_used: calls_used as number, tokens_committed: tokens_committed as number };
}

export default async function globalSetup() {
  const origin = process.env.SG_E2E_BASE_URL?.trim();
  if (!origin) throw new Error("Budget tripwire requires SG_E2E_BASE_URL.");
  const attemptDirectory = process.env.SG_GATE5_ATTEMPT_DIR;
  if (!attemptDirectory) throw new Error("Budget tripwire requires SG_GATE5_ATTEMPT_DIR.");
  // The base config fills in a default under verification/gate5 when the operator sets none.
  if (/[\\/]verification[\\/]gate5(?:[\\/]|$)/i.test(path.resolve(attemptDirectory))) {
    throw new Error("Budget tripwire: set SG_GATE5_ATTEMPT_DIR to a dedicated hosted-smoke folder, not verification/gate5.");
  }
  if (existsSync(path.join(attemptDirectory, "hosted-budget-tripwire.json"))) {
    throw new Error("Budget tripwire: this attempt folder already holds a tripwire record; use a fresh folder.");
  }
  const before = await readBudget(origin);
  const report: Record<string, unknown> = { before, after: null, verdict: "pending" };
  const write = async () => {
    await mkdir(attemptDirectory, { recursive: true });
    await writeFile(path.join(attemptDirectory, "hosted-budget-tripwire.json"), `${JSON.stringify(report, null, 2)}\n`);
  };
  await write();
  return async () => {
    let after: BudgetReading;
    try {
      after = await readBudget(origin);
    } catch (error) {
      report.verdict = "unreadable";
      await write();
      throw error;
    }
    report.after = after;
    if (after.utc_day !== before.utc_day) {
      report.verdict = "inconclusive-utc-day-rollover";
      await write();
      throw new Error(`Budget tripwire inconclusive: utc_day rolled over (${before.utc_day} -> ${after.utc_day}). Rerun the hosted smoke.`);
    }
    if (after.calls_used !== before.calls_used || after.tokens_committed !== before.tokens_committed) {
      report.verdict = "budget-changed";
      await write();
      throw new Error(
        `Budget tripwire: ordinary budget changed during the hosted smoke (calls_used ${before.calls_used} -> ${after.calls_used}, tokens_committed ${before.tokens_committed} -> ${after.tokens_committed}).`,
      );
    }
    report.verdict = "unchanged";
    await write();
  };
}
