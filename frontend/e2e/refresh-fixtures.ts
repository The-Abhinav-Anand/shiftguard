import { test as base, expect, type Page, type TestInfo } from "@playwright/test";

export type ProductModule = "workbench" | "plotly" | "scene" | "other";

export interface ScriptAsset {
  url: string;
  pathname: string;
  module: ProductModule;
  bytes: number;
}

export interface RefreshAudit {
  apiAttempts: string[];
  providerAttempts: string[];
  mockedApiAborts: Array<{ method: string; pathname: string; url: string; abortedAt: number; consoleReported: boolean }>;
  mockedScriptFailures: Array<{ pathname: string; url: string; failedAt: number; resourceErrorReported: boolean; importErrorReported: boolean }>;
  transportSimulationErrors: string[];
  expectedFaultConsoleErrors: string[];
  externalRequests: string[];
  pageErrors: string[];
  consoleErrors: string[];
  scripts: ScriptAsset[];
  pendingScriptReads: Promise<void>[];
}

export type IllustrationChapter = 1 | 2 | 3;

const chapterLabels: Record<IllustrationChapter, string> = {
  1: "Inputs",
  2: "Missing block",
  3: "Compare evidence",
};

export function chapterButton(page: Page, chapter: IllustrationChapter) {
  const label = chapterLabels[chapter].replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return page.getByRole("group", { name: "Illustration chapters" }).getByRole("button", {
    name: new RegExp(`^(?:0?${chapter}\\s+${label}|0${chapter}${label})$`),
  });
}

export function chapterVisibleText(chapter: IllustrationChapter): RegExp {
  const label = chapterLabels[chapter].replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^0${chapter}\\s*${label}$`);
}

export function conceptCaption(page: Page) {
  return page.getByText(/^Concept illustration — not experiment data\.$/);
}

declare global {
  interface Window {
    __refreshLifecycleProbe?: {
      activeListeners: number;
      scheduledFrames: number;
      completedFrames: number;
      sceneDrawCalls: number;
      sceneRenderCallbacks: number;
      maxSceneDrawCallsPerRafCallback: number;
      sceneRenderTimestamps: number[];
    };
    __setRefreshVisibility?: (state: DocumentVisibilityState) => void;
    __setRefreshSlowMode?: (rafDelayMs: number, drawDelayMs: number) => void;
  }
}

export type { Page, TestInfo };

const audits = new WeakMap<Page, RefreshAudit>();

function classifyProductModule(pathname: string, source: string): ProductModule {
  const filename = pathname.split("/").at(-1)?.toLowerCase() ?? "";
  const body = source.toLowerCase();
  const plotChunk = /^(?:plot|plotly)(?:[-_.][a-z0-9_-]+)?\.m?js$/.test(filename);
  if (plotChunk && (/plotly\.register/.test(body) || /plotly\.js-style-/.test(body))) return "plotly";

  const sceneChunk = /^(?:missingnessscene|missingness-scene|scene)(?:[-_.][a-z0-9_-]+)?\.m?js$/.test(filename);
  if (sceneChunk && (/webglrenderer/.test(body) || /three\.module/.test(body) || /three\.js/.test(body))) return "scene";

  const workbenchChunk = /^(?:benchmarkworkbench|benchmark-workbench|workbench)(?:[-_.][a-z0-9_-]+)?\.m?js$/.test(filename);
  if (workbenchChunk && body.includes("approved preset") && body.includes("submit run")) return "workbench";
  return "other";
}

const workbenchChunkPath = /\/(?:benchmarkworkbench|benchmark-workbench|workbench)(?:[-_.][a-z0-9_-]+)?\.m?js(?:$|\?)/i;
const sceneChunkPath = /\/(?:missingnessscene|missingness-scene|scene)(?:[-_.][a-z0-9_-]+)?\.m?js(?:$|\?)/i;

export function isProductChunk(url: string, module: "workbench" | "scene"): boolean {
  const pattern = module === "workbench" ? workbenchChunkPath : sceneChunkPath;
  return pattern.test(new URL(url).pathname);
}

export function refreshAudit(page: Page): RefreshAudit {
  const audit = audits.get(page);
  if (!audit) throw new Error("The refresh network audit fixture was not installed for this page.");
  return audit;
}

export async function scriptAssets(page: Page): Promise<ScriptAsset[]> {
  const audit = refreshAudit(page);
  await Promise.all(audit.pendingScriptReads);
  return [...audit.scripts];
}

export function isJavaScriptAsset(url: string): boolean {
  try {
    return /\.(?:m?js)$/i.test(new URL(url).pathname);
  } catch {
    return false;
  }
}

export const test = base.extend<{ refreshNetworkAudit: RefreshAudit }>({
  refreshNetworkAudit: [async ({ page, baseURL }, use, testInfo) => {
    if (!baseURL) throw new Error("The refresh config must provide an explicit local preview URL.");
    const previewOrigin = new URL(baseURL).origin;
    const audit: RefreshAudit = {
      apiAttempts: [],
      providerAttempts: [],
      mockedApiAborts: [],
      mockedScriptFailures: [],
      transportSimulationErrors: [],
      expectedFaultConsoleErrors: [],
      externalRequests: [],
      pageErrors: [],
      consoleErrors: [],
      scripts: [],
      pendingScriptReads: [],
    };
    audits.set(page, audit);

    page.on("request", (request) => {
      const url = new URL(request.url());
      if ((url.protocol === "http:" || url.protocol === "https:") && url.origin !== previewOrigin) {
        audit.externalRequests.push(`${request.method()} ${url.origin}${url.pathname}`);
      }
      if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
        audit.apiAttempts.push(`${request.method()} ${url.pathname}`);
      }
      const workbenchSessionBootstrap = request.method() === "POST" && url.pathname === "/api/v1/agent/sessions";
      if (!workbenchSessionBootstrap && /\/(?:agent|provider|chat\/completions)(?:\/|$)/i.test(url.pathname)) {
        audit.providerAttempts.push(`${request.method()} ${url.pathname}`);
      }
    });

    page.on("response", (response) => {
      if (response.request().resourceType() !== "script") return;
      const task = response.body().then((body) => {
        const pathname = new URL(response.url()).pathname;
        const source = body.toString("utf8");
        audit.scripts.push({
          url: response.url(),
          pathname,
          module: classifyProductModule(pathname, source),
          bytes: body.byteLength,
        });
      }).catch(() => undefined);
      audit.pendingScriptReads.push(task);
    });

    page.on("pageerror", (error) => audit.pageErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const text = message.text();
      const location = message.location().url;
      if (/failed to load resource: net::err_blocked_by_client(?:\.inspector)?$/i.test(text)) {
        const matchedAbort = audit.mockedApiAborts.find((entry) => !entry.consoleReported && (
          location === entry.url ||
          (location !== "" && new URL(location, previewOrigin).pathname === entry.pathname) ||
          text.includes(entry.url) ||
          text.includes(entry.pathname)
        )) ?? audit.mockedApiAborts.find((entry) => !entry.consoleReported &&
          Date.now() - entry.abortedAt <= 1_000 &&
          (location === "" || new URL(location, previewOrigin).pathname === "/"));
        if (matchedAbort) {
          matchedAbort.consoleReported = true;
          audit.transportSimulationErrors.push(`${matchedAbort.method} ${matchedAbort.pathname}: ${text}`);
          return;
        }
      }
      const failedImport = audit.mockedScriptFailures.find((entry) => !entry.importErrorReported &&
        text === `TypeError: Failed to fetch dynamically imported module: ${entry.url}`);
      if (failedImport) {
        failedImport.importErrorReported = true;
        audit.expectedFaultConsoleErrors.push(`${failedImport.url}: ${text}`);
        return;
      }
      if (/^failed to load resource: net::err_failed(?:\.[a-z]+)?$/i.test(text)) {
        const failedResource = audit.mockedScriptFailures.find((entry) => !entry.resourceErrorReported && (
          location === entry.url ||
          (location !== "" && new URL(location, previewOrigin).pathname === entry.pathname) ||
          (Date.now() - entry.failedAt <= 1_000 && (location === "" || new URL(location, previewOrigin).pathname === "/"))
        ));
        if (failedResource) {
          failedResource.resourceErrorReported = true;
          audit.expectedFaultConsoleErrors.push(`${failedResource.url}: ${text}`);
          return;
        }
      }
      const expectedWebGLContextFailure = testInfo.title.includes("F07 unavailable WebGL") &&
        text === "THREE.WebGLRenderer: THREE.WebGLRenderer: Error creating WebGL context.";
      if (expectedWebGLContextFailure) audit.expectedFaultConsoleErrors.push(text);
      else audit.consoleErrors.push(text);
    });

    await page.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if ((url.protocol === "http:" || url.protocol === "https:") && url.origin !== previewOrigin) {
        await route.abort("blockedbyclient");
        return;
      }
      if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
        audit.mockedApiAborts.push({
          method: route.request().method(),
          pathname: url.pathname,
          url: url.href,
          abortedAt: Date.now(),
          consoleReported: false,
        });
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });

    await use(audit);
    await Promise.all(audit.pendingScriptReads);
    if (audit.transportSimulationErrors.length > 0 || audit.mockedApiAborts.length > 0) {
      const mockedRoutes = [...new Set(audit.mockedApiAborts.map(({ method, pathname }) => `${method} ${pathname}`))];
      testInfo.annotations.push({
        type: "transport-simulation",
        description: `Static preview blocked API transport for: ${mockedRoutes.join(", ") || "no API route"}. No backend or provider was contacted.`,
      });
    }
    if (audit.expectedFaultConsoleErrors.length > 0) {
      testInfo.annotations.push({
        type: "fault-simulation",
        description: `Explicit fault injection in this test induced: ${[...new Set(audit.expectedFaultConsoleErrors)].join("; ")}`,
      });
    }
    expect(audit.externalRequests, "Refresh tests must remain on the explicit local preview origin").toEqual([]);
    expect(audit.pageErrors, "Uncaught browser exceptions").toEqual([]);
    expect(audit.consoleErrors, "Unexpected browser console errors").toEqual([]);
  }, { auto: true }],
});

export { expect };
