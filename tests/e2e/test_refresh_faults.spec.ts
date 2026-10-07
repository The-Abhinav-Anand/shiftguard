import { test, expect, chapterButton, conceptCaption, isProductChunk, refreshAudit, scriptAssets, isJavaScriptAsset, type Page } from "../../frontend/e2e/refresh-fixtures";

interface HeldScript {
  requested: Promise<string>;
  release(): void;
}

async function holdNextUnseenScript(page: Page, module: "workbench" | "scene"): Promise<HeldScript> {
  const existing = new Set((await scriptAssets(page)).map((asset) => asset.url));
  let signalRequested!: (url: string) => void;
  let releaseGate!: () => void;
  let held = false;
  const requested = new Promise<string>((resolve) => { signalRequested = resolve; });
  const gate = new Promise<void>((resolve) => { releaseGate = resolve; });

  await page.route("**/*", async (route) => {
    const url = route.request().url();
    if (held || existing.has(url) || !isJavaScriptAsset(url) || !isProductChunk(url, module)) {
      await route.fallback();
      return;
    }
    held = true;
    signalRequested(url);
    await gate;
    await route.fallback().catch(() => undefined);
  });

  return { requested, release: releaseGate };
}

async function failNextUnseenScript(page: Page, module: "workbench" | "scene"): Promise<Promise<string>> {
  const existing = new Set((await scriptAssets(page)).map((asset) => asset.url));
  let signalRequested!: (url: string) => void;
  let failed = false;
  const requested = new Promise<string>((resolve) => { signalRequested = resolve; });

  await page.route("**/*", async (route) => {
    const url = route.request().url();
    if (failed || existing.has(url) || !isJavaScriptAsset(url) || !isProductChunk(url, module)) {
      await route.fallback();
      return;
    }
    failed = true;
    const parsed = new URL(url);
    refreshAudit(page).mockedScriptFailures.push({
      pathname: parsed.pathname,
      url,
      failedAt: Date.now(),
      resourceErrorReported: false,
      importErrorReported: false,
    });
    signalRequested(url);
    await route.abort("failed");
  });
  return requested;
}

async function installSceneLifecycleProbe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const trackedTypes = new Set([
      "pointermove", "pointerleave", "visibilitychange", "webglcontextlost",
      "webglcontextrestored", "resize", "blur", "focus",
    ]);
    const listeners = new WeakMap<EventTarget, Map<string, Set<EventListenerOrEventListenerObject>>>();
    const stats = {
      activeListeners: 0,
      scheduledFrames: 0,
      completedFrames: 0,
      sceneDrawCalls: 0,
      sceneRenderCallbacks: 0,
      maxSceneDrawCallsPerRafCallback: 0,
      sceneRenderTimestamps: [] as number[],
    };
    let slowRafDelayMs = 0;
    let slowDrawDelayMs = 0;
    let visibility: DocumentVisibilityState = "visible";
    Object.defineProperty(window, "__refreshLifecycleProbe", { value: stats, configurable: false });
    Object.defineProperty(document, "visibilityState", { get: () => visibility, configurable: true });
    Object.defineProperty(document, "hidden", { get: () => visibility === "hidden", configurable: true });
    Object.defineProperty(window, "__setRefreshVisibility", {
      value: (next: DocumentVisibilityState) => {
        visibility = next;
        document.dispatchEvent(new Event("visibilitychange"));
      },
      configurable: false,
    });
    Object.defineProperty(window, "__setRefreshSlowMode", {
      value: (rafDelayMs: number, drawDelayMs: number) => {
        slowRafDelayMs = rafDelayMs;
        slowDrawDelayMs = drawDelayMs;
      },
      configurable: false,
    });

    const instrumentDrawMethods = (prototype: object) => {
      for (const method of ["drawArrays", "drawElements"] as const) {
        const descriptor = Object.getOwnPropertyDescriptor(prototype, method);
        if (!descriptor || typeof descriptor.value !== "function") continue;
        const original = descriptor.value as (...args: number[]) => void;
        Object.defineProperty(prototype, method, {
          ...descriptor,
          value: function (this: WebGLRenderingContext | WebGL2RenderingContext, ...args: number[]) {
            stats.sceneDrawCalls += 1;
            if (slowDrawDelayMs > 0) {
              const deadline = performance.now() + slowDrawDelayMs;
              while (performance.now() < deadline) { /* inject measurable work into real WebGL draws */ }
            }
            return original.apply(this, args);
          },
        });
      }
    };
    instrumentDrawMethods(WebGLRenderingContext.prototype);
    instrumentDrawMethods(WebGL2RenderingContext.prototype);

    const add = EventTarget.prototype.addEventListener;
    const remove = EventTarget.prototype.removeEventListener;
    EventTarget.prototype.addEventListener = function (type, callback, options) {
      if (callback && trackedTypes.has(type)) {
        const capture = typeof options === "boolean" ? options : Boolean(options?.capture);
        const key = `${type}:${capture}`;
        let byType = listeners.get(this);
        if (!byType) {
          byType = new Map();
          listeners.set(this, byType);
        }
        let callbacks = byType.get(key);
        if (!callbacks) {
          callbacks = new Set();
          byType.set(key, callbacks);
        }
        if (!callbacks.has(callback)) {
          callbacks.add(callback);
          stats.activeListeners += 1;
        }
      }
      return add.call(this, type, callback, options);
    };
    EventTarget.prototype.removeEventListener = function (type, callback, options) {
      if (callback && trackedTypes.has(type)) {
        const capture = typeof options === "boolean" ? options : Boolean(options?.capture);
        const callbacks = listeners.get(this)?.get(`${type}:${capture}`);
        if (callbacks?.delete(callback)) stats.activeListeners -= 1;
      }
      return remove.call(this, type, callback, options);
    };

    const requestFrame = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = (callback: FrameRequestCallback) => {
      stats.scheduledFrames += 1;
      return requestFrame((time) => {
        const invoke = (callbackTime: number) => {
          const drawsBefore = stats.sceneDrawCalls;
          stats.completedFrames += 1;
          callback(callbackTime);
          const draws = stats.sceneDrawCalls - drawsBefore;
          if (draws > 0) {
            stats.sceneRenderCallbacks += 1;
            stats.maxSceneDrawCallsPerRafCallback = Math.max(stats.maxSceneDrawCallsPerRafCallback, draws);
            stats.sceneRenderTimestamps.push(performance.now());
          }
        };
        if (slowRafDelayMs > 0) window.setTimeout(() => invoke(performance.now()), slowRafDelayMs);
        else invoke(time);
      });
    };
  });
}

function sceneFallback(page: Page) {
  return page.locator(".sg-scene__status").filter({ hasText: /^Static illustration\./ }).first();
}

async function expectSceneFallback(page: Page, reason: string): Promise<void> {
  const status = sceneFallback(page);
  await expect(status).toContainText(`Static illustration. ${reason}`);
  await expect(status.getByRole("button", { name: "Try 3D again", exact: true })).toBeVisible();
}

test("[simulated] F04 delayed /demo module exposes a real loading state and mounts on release", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/about");
  await expect(page.getByRole("heading", { level: 1, name: "When inputs shift, know what still holds." })).toBeVisible();
  const hold = await holdNextUnseenScript(page, "workbench");
  const started = Date.now();
  const click = page.locator(".overview-hero").getByRole("link", { name: "Explore benchmark demo", exact: true }).click({ noWaitAfter: true });
  try {
    const requestedURL = await hold.requested;
    expect(isJavaScriptAsset(requestedURL)).toBe(true);
    const loading = page.getByRole("status", { name: "Opening this page", exact: true });
    await expect(loading, "a delayed route chunk must leave an accessible loading state").toBeVisible();
    hold.release();
    await click;
    await expect(page.getByRole("heading", { name: "Bank calibration workbench", exact: true })).toBeVisible();
    expect(Date.now() - started, "route content must mount promptly after the chunk resolves").toBeLessThan(2_500);
  } finally {
    hold.release();
  }
  const metadata = test.info().config.metadata as { screenshotDirectory: string };
  await page.screenshot({ path: `${metadata.screenshotDirectory}/route-loading-released.png`, fullPage: true, animations: "disabled" });
});

test("[simulated] F04 failed /demo module shows recovery and the static entry explains JavaScript", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/about");
  await expect(page.getByRole("heading", { level: 1, name: "When inputs shift, know what still holds." })).toBeVisible();
  const noScriptText = await page.locator("noscript").textContent();
  expect(noScriptText).toMatch(/javascript/i);

  const failedRequest = failNextUnseenScript(page, "workbench");
  const click = page.locator(".overview-hero").getByRole("link", { name: "Explore benchmark demo", exact: true }).click({ noWaitAfter: true });
  const requestedURL = await failedRequest;
  expect(isJavaScriptAsset(requestedURL)).toBe(true);
  await click.catch(() => undefined);
  await expect(page.getByRole("heading", { name: "This page could not be loaded.", exact: true })).toBeVisible();
  await expect(page.getByText("Reload the page to try opening its content again.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reload page", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to SHIFTGUARD", exact: true })).toBeVisible();
});

test("[simulated] F07 unavailable WebGL keeps the caption, chapters, and static diagram usable", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext as (...args: unknown[]) => RenderingContext | null;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, kind: string, ...args: unknown[]) {
      if (/^webgl2?$|^experimental-webgl$/i.test(kind)) return null;
      return original.apply(this, [kind, ...args]);
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  await page.goto("/about");
  await expect(conceptCaption(page)).toBeVisible();
  await expectSceneFallback(page, "The 3D illustration is unavailable in this browser.");
  await chapterButton(page, 3).click();
  await expect(chapterButton(page, 3)).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".overview-hero").getByRole("link", { name: "Explore benchmark demo", exact: true })).toBeVisible();
});

test("[simulated] F07 context loss leaves a static fallback when a WebGL canvas is available", async ({ page }) => {
  await page.goto("/about");
  await expect(conceptCaption(page)).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause illustration", exact: true }), "the scene must render successfully before context loss is induced").toBeVisible();
  const canvas = page.locator(".sg-missingness-renderer canvas");
  await expect(canvas).toHaveCount(1);
  await canvas.evaluate((element) => element.dispatchEvent(new Event("webglcontextlost", { cancelable: true })));
  await expectSceneFallback(page, "The WebGL context was lost.");
  await expect(canvas).toHaveCount(0);
  await expect(chapterButton(page, 1)).toBeVisible();
});

test("[simulated] F07 sustained slow visible frames downgrade the optional scene", async ({ page }) => {
  await installSceneLifecycleProbe(page);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/about");
  await expect(conceptCaption(page)).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause illustration", exact: true }), "the scene must render successfully before slow frames are induced").toBeVisible();
  const canvas = page.locator(".sg-missingness-renderer canvas");
  await expect(canvas).toHaveCount(1);
  await page.waitForTimeout(5_500);
  const probe = await page.evaluate(() => {
    if (!window.__refreshLifecycleProbe || !window.__setRefreshSlowMode) throw new Error("Scene performance probe was not installed.");
    window.__setRefreshSlowMode(125, 3);
    return {
      startedAt: performance.now(),
      priorRenderCallbacks: window.__refreshLifecycleProbe.sceneRenderCallbacks,
      priorTimestampCount: window.__refreshLifecycleProbe.sceneRenderTimestamps.length,
    };
  });
  const host = page.locator(".sg-missingness-renderer");
  const bounds = await host.boundingBox();
  expect(bounds, "the visible WebGL scene must have an interaction target").not.toBeNull();
  const status = sceneFallback(page);
  const chapters = [2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1] as const;
  const movementDeadline = Date.now() + 12_000;
  for (let cycle = 0; cycle < chapters.length && Date.now() < movementDeadline; cycle += 1) {
    await chapterButton(page, chapters[cycle]).click();
    await page.mouse.move(
      bounds!.x + bounds!.width * (cycle % 2 === 0 ? 0.28 : 0.72),
      bounds!.y + bounds!.height * (cycle % 3 === 0 ? 0.34 : 0.68),
    );
    await page.waitForTimeout(350);
    if (await status.isVisible().catch(() => false)) break;
  }
  await expect(status, "repeated chapter and pointer motion must trip the real sustained slow-frame downgrade").toBeVisible({ timeout: 2_000 });
  await expect(status).toContainText("Static illustration. 3D was switched off because rendering was slow.");
  await expect(status.getByRole("button", { name: "Try 3D again", exact: true })).toBeVisible();
  const measurements = await page.evaluate(() => {
    if (!window.__refreshLifecycleProbe) throw new Error("Scene performance probe was not installed.");
    return window.__refreshLifecycleProbe;
  });
  const elapsed = performance.now() - probe.startedAt;
  const activeRenderTimes = measurements.sceneRenderTimestamps.slice(probe.priorTimestampCount);
  expect(elapsed, "slow-frame downgrade must follow two complete 2-second active windows").toBeGreaterThanOrEqual(4_000);
  expect(activeRenderTimes.some((time) => time >= probe.startedAt && time < probe.startedAt + 2_000), "the first 2-second window must contain actual scene renders").toBe(true);
  expect(activeRenderTimes.some((time) => time >= probe.startedAt + 2_000 && time < probe.startedAt + 4_000), "the second 2-second window must contain actual scene renders").toBe(true);
  expect(measurements.sceneRenderCallbacks - probe.priorRenderCallbacks).toBeGreaterThanOrEqual(2);
  expect(measurements.maxSceneDrawCallsPerRafCallback, "each measured scene render must remain within the renderer draw-call budget").toBeLessThanOrEqual(12);
  await expect(canvas).toHaveCount(0);
  await expect(chapterButton(page, 3)).toBeVisible();
});

test("[simulated] F12 a delayed scene import cannot attach a canvas after leaving the overview", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/about");
  await expect(conceptCaption(page)).toBeVisible();
  const hold = await holdNextUnseenScript(page, "scene");
  const activate = page.getByRole("button", { name: /view 3d illustration/i });
  await expect(activate, "mobile must require an explicit opt-in before requesting the scene").toBeVisible();
  expect((await scriptAssets(page)).some((asset) => asset.module === "scene")).toBe(false);
  const activation = activate.click({ noWaitAfter: true });
  const requestedURL = await hold.requested;
  expect(isJavaScriptAsset(requestedURL)).toBe(true);
  await expect(chapterButton(page, 2)).toBeVisible();
  await chapterButton(page, 2).click();
  await expect(chapterButton(page, 2)).toHaveAttribute("aria-pressed", "true");
  const navigation = page.locator(".overview-hero").getByRole("link", { name: "Explore benchmark demo", exact: true }).click({ noWaitAfter: true });
  hold.release();
  await activation.catch(() => undefined);
  await navigation.catch(() => undefined);
  await expect(page).toHaveURL(/\/demo\/?$/);
  await expect(page.getByRole("heading", { name: "Bank calibration workbench", exact: true })).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(0);
  expect(refreshAudit(page).providerAttempts).toEqual([]);
});

test("[simulated] F12 pause and chapter changes do not create duplicate scene canvases", async ({ page }) => {
  await page.goto("/about");
  await expect(conceptCaption(page)).toBeVisible();
  const pause = page.getByRole("button", { name: "Pause illustration", exact: true });
  await expect(pause, "duplicate-renderer checks require a mounted, successfully rendered scene").toBeVisible();
  await expect(page.locator(".sg-missingness-renderer canvas")).toHaveCount(1);
  await pause.click();
  await expect(page.getByRole("button", { name: "Resume illustration", exact: true })).toHaveAttribute("aria-pressed", "true");
  for (let cycle = 0; cycle < 10; cycle += 1) {
    const chapter = ([2, 3, 1] as const)[cycle % 3];
    await chapterButton(page, chapter).click();
    await expect(chapterButton(page, chapter)).toHaveAttribute("aria-pressed", "true");
    expect(await page.locator("canvas").count()).toBeLessThanOrEqual(1);
  }
});

test("[simulated] F08 and F12 settled, hidden, and paused scene states stop scheduling frames and retain bounded listeners", async ({ page }) => {
  await installSceneLifecycleProbe(page);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/about");
  await expect(conceptCaption(page)).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause illustration", exact: true }), "idle accounting begins after the scene's first successful frame").toBeVisible();
  await expect(page.locator(".sg-missingness-renderer canvas")).toHaveCount(1);
  await page.waitForTimeout(5_500);

  const settled = await page.evaluate(() => {
    if (!window.__refreshLifecycleProbe) throw new Error("Lifecycle probe was not installed.");
    return window.__refreshLifecycleProbe;
  });
  await page.waitForTimeout(750);
  const afterIdle = await page.evaluate(() => {
    if (!window.__refreshLifecycleProbe) throw new Error("Lifecycle probe was not installed.");
    return window.__refreshLifecycleProbe;
  });
  expect(afterIdle.scheduledFrames - settled.scheduledFrames, "settled illustration must not keep a global animation loop").toBe(0);
  expect(afterIdle.sceneDrawCalls - settled.sceneDrawCalls, "settled illustration must issue no WebGL draw calls").toBe(0);
  expect(settled.sceneRenderCallbacks, "the ready scene must have rendered before its idle budget is measured").toBeGreaterThan(0);
  expect(settled.maxSceneDrawCallsPerRafCallback, "scene render draw calls must remain within budget").toBeLessThanOrEqual(12);

  await page.evaluate(() => {
    if (!window.__setRefreshVisibility) throw new Error("Visibility probe was not installed.");
    window.__setRefreshVisibility("hidden");
  });
  const hiddenStart = await page.evaluate(() => {
    if (!window.__refreshLifecycleProbe) throw new Error("Lifecycle probe was not installed.");
    return window.__refreshLifecycleProbe.scheduledFrames;
  });
  await page.waitForTimeout(500);
  const hiddenEnd = await page.evaluate(() => {
    if (!window.__refreshLifecycleProbe) throw new Error("Lifecycle probe was not installed.");
    return window.__refreshLifecycleProbe.scheduledFrames;
  });
  expect(hiddenEnd - hiddenStart, "hidden illustration must remain paused").toBeLessThanOrEqual(2);
  const hiddenSceneDraws = await page.evaluate(() => window.__refreshLifecycleProbe?.sceneDrawCalls ?? -1);
  expect(hiddenSceneDraws, "hidden illustration must issue no WebGL draw calls").toBe(settled.sceneDrawCalls);
  await page.evaluate(() => {
    if (!window.__setRefreshVisibility) throw new Error("Visibility probe was not installed.");
    window.__setRefreshVisibility("visible");
  });

  const pause = page.getByRole("button", { name: "Pause illustration", exact: true });
  await expect(pause).toBeVisible();
  await pause.click();
  await expect(page.getByRole("button", { name: "Resume illustration", exact: true })).toHaveAttribute("aria-pressed", "true");
  const pausedStart = await page.evaluate(() => {
    if (!window.__refreshLifecycleProbe) throw new Error("Lifecycle probe was not installed.");
    return { scheduledFrames: window.__refreshLifecycleProbe.scheduledFrames, sceneDrawCalls: window.__refreshLifecycleProbe.sceneDrawCalls };
  });
  await page.waitForTimeout(500);
  const pausedEnd = await page.evaluate(() => {
    if (!window.__refreshLifecycleProbe) throw new Error("Lifecycle probe was not installed.");
    return window.__refreshLifecycleProbe;
  });
  expect(pausedEnd.scheduledFrames - pausedStart.scheduledFrames, "user pause must stop authored scene frames").toBeLessThanOrEqual(2);
  expect(pausedEnd.sceneDrawCalls, "user pause must stop scene WebGL draw calls").toBe(pausedStart.sceneDrawCalls);

  for (let cycle = 0; cycle < 10; cycle += 1) {
    const chapter = ([2, 3, 1] as const)[cycle % 3];
    await chapterButton(page, chapter).click();
    await expect(chapterButton(page, chapter)).toHaveAttribute("aria-pressed", "true");
    expect(await page.locator("canvas").count()).toBeLessThanOrEqual(1);
  }
  const finalProbe = await page.evaluate(() => {
    if (!window.__refreshLifecycleProbe) throw new Error("Lifecycle probe was not installed.");
    return window.__refreshLifecycleProbe;
  });
  expect(finalProbe.activeListeners, "chapter and preference interactions must not accumulate scene listeners").toBeLessThanOrEqual(settled.activeListeners + 1);
});
