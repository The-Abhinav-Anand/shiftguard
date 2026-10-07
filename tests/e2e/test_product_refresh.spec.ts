import path from "node:path";
import { test, expect, chapterButton, chapterVisibleText, conceptCaption, refreshAudit, scriptAssets, type Page, type TestInfo } from "../../frontend/e2e/refresh-fixtures";

const responsiveWidths = [320, 390, 768, 1024, 1440] as const;

function heroDemoLink(page: Page) {
  return page.locator(".overview-hero").getByRole("link", { name: "Explore benchmark demo", exact: true });
}

function evidencePath(testInfo: TestInfo, filename: string): string {
  const metadata = testInfo.config.metadata as { screenshotDirectory: string };
  return path.join(metadata.screenshotDirectory, filename);
}

async function saveScreenshot(page: Page, testInfo: TestInfo, filename: string): Promise<void> {
  await page.screenshot({ path: evidencePath(testInfo, filename), fullPage: true, animations: "disabled" });
}

async function expectNoDocumentOverflow(page: Page, testInfo: TestInfo, label: string): Promise<void> {
  const overflow = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    elements: Array.from(document.querySelectorAll("body *"))
      .map((element) => ({
        tag: element.tagName,
        role: element.getAttribute("role"),
        className: typeof element.className === "string" ? element.className : "",
        left: Math.round(element.getBoundingClientRect().left),
        right: Math.round(element.getBoundingClientRect().right),
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth,
      }))
      .filter((item) => item.left < 0 || item.right > document.documentElement.clientWidth),
  }));
  if (overflow.document > overflow.viewport) {
    await testInfo.attach(`${label}-overflow`, { body: JSON.stringify(overflow, null, 2), contentType: "application/json" });
  }
  expect(overflow.document, `${label}: document width must fit the CSS viewport`).toBeLessThanOrEqual(overflow.viewport);
}

async function tabTo(page: Page, locator: ReturnType<Page["getByRole"]>, limit = 60): Promise<void> {
  for (let index = 0; index < limit; index += 1) {
    if (await locator.evaluate((element) => element === document.activeElement).catch(() => false)) return;
    await page.keyboard.press("Tab");
  }
  await expect(locator, "control must be reachable by keyboard").toBeFocused();
}

test("[simulated] F01 overview explains the product and opens the independent workbench route", async ({ page }) => {
  const audit = refreshAudit(page);
  await page.goto("/about");
  await expect(page.getByRole("heading", { level: 1, name: "When inputs shift, know what still holds." })).toBeVisible();
  await expect(page.getByText("Available today: Bank benchmark presets. Single-seed development evidence. Private-data workflows are planned.", { exact: true })).toBeVisible();
  await expect(heroDemoLink(page)).toHaveAttribute("href", "/demo");
  await expect(page.getByRole("link", { name: "How evidence is built", exact: true })).toHaveAttribute("href", "#method");

  await page.getByRole("link", { name: "How evidence is built", exact: true }).click();
  await expect(page).toHaveURL(/#method$/);
  await expect(page.locator("#method")).toBeVisible();
  const overviewScripts = await scriptAssets(page);
  expect(overviewScripts.some((asset) => asset.module === "plotly"), "Plotly must stay out of the public overview").toBe(false);
  expect(overviewScripts.some((asset) => asset.module === "workbench"), "the workbench route must remain lazy").toBe(false);
  expect(audit.apiAttempts, "marketing must not start workbench or provider requests").toEqual([]);
  await saveScreenshot(page, test.info(), "overview-desktop-1440.png");

  await heroDemoLink(page).click();
  await expect(page).toHaveURL(/\/demo\/?$/);
  await expect(page.getByRole("heading", { name: "Bank calibration workbench", exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Approved preset", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit run" })).toBeVisible();
  const demoScripts = await scriptAssets(page);
  expect(demoScripts.some((asset) => asset.module === "workbench"), "entering /demo must load its route module").toBe(true);
  expect(demoScripts.some((asset) => asset.module === "plotly"), "an empty workbench must not eagerly download Plotly").toBe(false);
  expect(audit.providerAttempts).toEqual([]);
});

test("F02 planned workspace routes remain informational and make no private requests", async ({ page }) => {
  const audit = refreshAudit(page);
  const plannedRoutes = ["/workspace", "/workspace/onboarding", "/workspace/dashboard", "/workspace/upload"];
  for (const route of plannedRoutes) {
    const apiStart = audit.apiAttempts.length;
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1, name: "Private workspace", exact: true })).toBeVisible();
    await expect(page.getByText("Planned — not available in this build", { exact: true })).toBeVisible();
    await expect(page.getByText("Private workspaces are planned. This build supports the Bank benchmark demo.", { exact: true })).toBeVisible();
    await expect(page.locator("form, input[type='file'], input[type='password'], textarea")).toHaveCount(0);
    await expect(page.locator("a[href='/demo']").first()).toBeVisible();
    expect(audit.apiAttempts.slice(apiStart), `${route} must not create private or workbench requests`).toEqual([]);
  }
  expect(audit.providerAttempts).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await saveScreenshot(page, test.info(), "planned-workspace-390.png");
});

test("F03 unknown app routes show the branded 404 with working recovery links", async ({ page }) => {
  const response = await page.goto("/does-not-exist");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle("Page not found · SHIFTGUARD");
  await expect(page.getByRole("heading", { level: 1, name: "This route has no record." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to SHIFTGUARD", exact: true })).toHaveAttribute("href", "/");
  await expect(page.getByRole("link", { name: "Open benchmark demo", exact: true })).toHaveAttribute("href", "/demo");
  await saveScreenshot(page, test.info(), "not-found-desktop-1440.png");
});

test("F07 concept caption and chapter controls remain complete in the static illustration", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/about");
  const caption = conceptCaption(page);
  await expect(caption).toBeVisible();
  expect(await caption.evaluate((element) => element.closest("canvas"))).toBeNull();

  for (const chapter of [1, 2, 3] as const) {
    const control = chapterButton(page, chapter);
    await expect(control).toBeVisible();
    await expect(control).toHaveText(chapterVisibleText(chapter));
    await control.click();
    await expect(control).toHaveAttribute("aria-pressed", "true");
    if (chapter > 1) await expect(chapterButton(page, (chapter - 1) as 1 | 2)).toHaveAttribute("aria-pressed", "false");
    await expect(caption).toBeVisible();
    await expect(page.getByText(`Chapter ${chapter}: ${["", "Inputs", "Missing block", "Compare evidence"][chapter]}`, { exact: true })).toBeVisible();
  }
  await saveScreenshot(page, test.info(), "overview-reduced-motion.png");
});

test("F08 reduced motion and coarse pointer retain static chapters without loading the scene", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/about");
  await expect(conceptCaption(page)).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(0);
  await chapterButton(page, 2).click();
  await expect(chapterButton(page, 2)).toHaveAttribute("aria-pressed", "true");
  expect((await scriptAssets(page)).some((asset) => asset.module === "scene")).toBe(false);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await chapterButton(page, 3).click();
  await expect(chapterButton(page, 3)).toHaveAttribute("aria-pressed", "true");

  await page.addInitScript(() => {
    const original = window.matchMedia.bind(window);
    window.matchMedia = ((query: string) => {
      if (query !== "(pointer: coarse)" && query !== "(pointer: fine)") return original(query);
      const matches = query === "(pointer: coarse)";
      return {
        matches,
        media: query,
        onchange: null,
        addListener() {},
        removeListener() {},
        addEventListener() {},
        removeEventListener() {},
        dispatchEvent() { return false; },
      } as MediaQueryList;
    }) as typeof window.matchMedia;
  });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/about");
  await expect(chapterButton(page, 1)).toBeVisible();
  expect((await scriptAssets(page)).some((asset) => asset.module === "scene")).toBe(false);
});

test("F09 responsive overview and workbench reflow from 320px through 1440px and at 200% equivalent width", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/about");
  for (const width of responsiveWidths) {
    await page.setViewportSize({ width, height: 1000 });
    await expectNoDocumentOverflow(page, test.info(), `overview-${width}`);
    if (width === 320 || width === 390 || width === 1440) {
      await saveScreenshot(page, test.info(), `overview-${width}.png`);
    }
  }

  // A 720 CSS-pixel viewport is the reflow width of a 1440px view at 200% browser zoom.
  await page.setViewportSize({ width: 720, height: 1000 });
  await expectNoDocumentOverflow(page, test.info(), "overview-200-percent-equivalent");
  await saveScreenshot(page, test.info(), "overview-200-percent-equivalent.png");

  await page.goto("/demo");
  for (const width of responsiveWidths) {
    await page.setViewportSize({ width, height: 1000 });
    await expect(page.getByRole("heading", { name: "Bank calibration workbench", exact: true })).toBeVisible();
    await expectNoDocumentOverflow(page, test.info(), `workbench-${width}`);
    if (width === 390 || width === 1440) await saveScreenshot(page, test.info(), `workbench-${width}.png`);
  }
});

test("F10 keyboard navigation and forced colors preserve named, operable route controls", async ({ page }) => {
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await page.goto("/about");
  const demoLink = heroDemoLink(page);
  await tabTo(page, demoLink);
  await expect(demoLink).toBeFocused();
  await saveScreenshot(page, test.info(), "overview-forced-colors.png");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/demo\/?$/);
  await expect(page.getByRole("combobox", { name: "Approved preset", exact: true })).toBeVisible();
  const preset = page.getByRole("combobox", { name: "Approved preset", exact: true });
  await tabTo(page, preset);
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(preset).toHaveValue("bank-stress");
});

test("F13 public and workbench entry chunks stay separate from Plotly and optional scene modules", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/about");
  await expect(page.getByRole("heading", { level: 1, name: "When inputs shift, know what still holds." })).toBeVisible();
  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: "Bank calibration workbench", exact: true })).toBeVisible();
  const initialModules = await scriptAssets(page);
  expect(initialModules.some((asset) => asset.module === "workbench"), "the /demo route chunk must be emitted and loaded").toBe(true);
  expect(initialModules.some((asset) => asset.module === "plotly"), "no persisted result is loaded by the isolated preview").toBe(false);
  expect(initialModules.some((asset) => asset.module === "scene"), "the workbench must not load Three or GSAP scene modules").toBe(false);
});

test("F14 assistant remains blocked while manual workbench controls stay available", async ({ page }) => {
  const audit = refreshAudit(page);
  await page.goto("/demo");
  await expect(page.getByText(/Assistant integration under review/)).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Approved preset", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit run" })).toBeVisible();
  await expect(page.locator("input, textarea, [contenteditable='true']")).toHaveCount(0);
  expect(audit.providerAttempts, "blocked assistant UI must not call status, submit, or resume endpoints").toEqual([]);
});
