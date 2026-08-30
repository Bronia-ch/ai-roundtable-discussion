import { test, expect, type Page } from "@playwright/test";

const VIEWPORTS = [
  { width: 1280, height: 900 },
  { width: 1920, height: 1080 },
];

/** 真实离线流程走到 live 演播厅（visual 断言在真实接线的页面上执行）。 */
async function gotoLiveStudio(page: Page) {
  await page.goto("/");
  await page.getByTestId("topic-input").fill("AI 与社会公平");
  await page.getByTestId("create-btn").click();
  await page.waitForURL(/#\/panel\?id=/);
  await expect(page.getByTestId("panel-list")).toBeVisible({ timeout: 15000 });
  await page.getByTestId("confirm-btn").click();
  await page.waitForURL(/#\/studio\?id=/);
  await page.getByTestId("start-btn").click();
  // 首轮发言渲染（live 状态 + seats 状态文本）
  await expect(page.getByText("发言").first()).toBeVisible({ timeout: 15000 });
}

for (const vp of VIEWPORTS) {
  test(`no horizontal overflow at ${vp.width}x${vp.height}`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await gotoLiveStudio(page);
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth > document.documentElement.clientWidth ||
        document.body.scrollWidth > document.body.clientWidth,
    );
    expect(overflow).toBe(false);
  });
}

test("transcript and insight panel scroll independently", async ({ page }) => {
  await gotoLiveStudio(page);
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
  await gotoLiveStudio(page);
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
  await gotoLiveStudio(page);
  // live 态同一时刻恰有一席发言、其余等待；两词同存（.first：等待可能多席命中）
  await expect(page.getByText("发言").first()).toBeVisible();
  await expect(page.getByText("等待").first()).toBeVisible();
});

test("reduced motion disables transitions", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await gotoLiveStudio(page);
  const duration = await page
    .locator(".btn")
    .first()
    .evaluate((el) => getComputedStyle(el).transitionDuration);
  expect(duration).toBe("0s");
});
