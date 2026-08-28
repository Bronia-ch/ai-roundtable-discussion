import { test, expect } from "@playwright/test";

const VIEWPORTS = [
  { width: 1280, height: 900 },
  { width: 1920, height: 1080 },
];

for (const vp of VIEWPORTS) {
  test(`no horizontal overflow at ${vp.width}x${vp.height}`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto("/#/studio");
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth > document.documentElement.clientWidth ||
        document.body.scrollWidth > document.body.clientWidth,
    );
    expect(overflow).toBe(false);
  });
}

test("transcript and insight panel scroll independently", async ({ page }) => {
  await page.goto("/#/studio");
  const transcript = page.locator('[data-testid="transcript"]');
  const insight = page.locator('[data-testid="insight-panel"]');
  await expect(transcript).toBeVisible();
  await expect(insight).toBeVisible();
  const tOverflowY = await transcript.evaluate((el) => getComputedStyle(el).overflowY);
  const iOverflowY = await insight.evaluate((el) => getComputedStyle(el).overflowY);
  expect(["auto", "scroll"]).toContain(tOverflowY);
  expect(["auto", "scroll"]).toContain(iOverflowY);
});

test("keyboard focus is visible", async ({ page }) => {
  await page.goto("/#/studio");
  await page.keyboard.press("Tab");
  const visible = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return false;
    const s = getComputedStyle(el);
    return s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0;
  });
  expect(visible).toBe(true);
});

test("state is expressed with text, not color alone", async ({ page }) => {
  await page.goto("/#/studio");
  await expect(page.getByText("发言")).toBeVisible();
  await expect(page.getByText("等待")).toBeVisible();
});

test("reduced motion disables transitions", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/#/studio");
  const duration = await page
    .locator(".btn")
    .first()
    .evaluate((el) => getComputedStyle(el).transitionDuration);
  expect(duration).toBe("0s");
});
