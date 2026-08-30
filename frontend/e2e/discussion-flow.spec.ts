import { test, expect } from "@playwright/test";

// C 阶段离线全流程：LLM_FAKE=1 后端 + 真实浏览器。
// 创建 → 阵容自动生成 → 确认 → 开始 → 多轮发言 → 暂停（先等 UI 确认，容忍在途事件）
// → 继续 → 结束 → 结果页。
test("离线全流程：创建到结果页", async ({ page }) => {
  // 1. 首页创建会话（expert_count=4）
  await page.goto("/");
  await page.getByTestId("topic-input").fill("AI 与社会公平");
  await page.getByTestId("create-btn").click();
  await page.waitForURL(/#\/panel\?id=/);

  // 2. 阵容自动生成：panel-list 出现且 1 host + 4 expert 共 5 席
  await expect(page.getByTestId("panel-list")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("周明远")).toBeVisible();
  await expect(page.getByText("林晓")).toBeVisible();
  await expect(page.getByText("陈曦")).toBeVisible();
  await expect(page.getByText("王芳")).toBeVisible();
  await expect(page.getByText("赵磊")).toBeVisible();

  // 3. 确认阵容 → 演播厅（ready 状态）
  await page.getByTestId("confirm-btn").click();
  await page.waitForURL(/#\/studio\?id=/);

  // 4. 开始讨论 → transcript 增长到至少 2 条（host 开场 + 首轮专家）
  await page.getByTestId("start-btn").click();
  const utterance = page.locator('[data-testid="transcript"] .utterance');
  await expect.poll(() => utterance.count(), { timeout: 20000 }).toBeGreaterThanOrEqual(2);

  // 5. 暂停：先等 UI 进入 paused（resume 启用）再记录条数；允许一个在途事件完成后验证稳定
  await page.getByTestId("pause-btn").click();
  await expect(page.getByTestId("resume-btn")).toBeEnabled({ timeout: 15000 });
  const frozen = await utterance.count();
  await page.waitForTimeout(1500);
  await expect.poll(() => utterance.count()).toBeLessThanOrEqual(frozen + 1);

  // 6. 继续：条数继续增长（引擎恢复下一轮）
  await page.getByTestId("resume-btn").click();
  const beforeResume = await utterance.count();
  await expect
    .poll(() => utterance.count(), { timeout: 20000 })
    .toBeGreaterThanOrEqual(beforeResume + 1);

  // 7. 结束讨论 → 结果页：报告摘要可见（FakeLLM 固定输出）
  // exact: true——页面上「原始 JSON」section 也含相同子串，精确匹配只命中渲染的 <p>/<li>
  await page.getByTestId("end-btn").click();
  await page.waitForURL(/#\/result\?id=/);
  await expect(
    page.getByText("专家们一致认为 AI 应兼顾效率与公平。", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("AI 需要公平治理", { exact: true })).toBeVisible();
});
