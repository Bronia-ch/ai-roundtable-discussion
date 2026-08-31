import { test, expect } from "@playwright/test";

// T0.2 RED：浏览器经前端同源地址（baseURL 相对路径）访问真实后端。
//
// 步骤：POST /sessions → 201 + session_id → GET /sessions/{id} → 200 + 快照契约。
// 快照契约 = backend/app/api/snapshot.py get_session_snapshot 的返回形状：
// { session_id, status, last_sequence, topic, expert_count, transcript[], insights[] }。
//
// 当前基础设施预期（T0.2 有效 RED）：playwright.config.ts 的 webServer 仅启动
// 前端（npm run dev），vite.config.ts 无 server.proxy，后端未接入 → POST /sessions
// 到达 Vite dev server 后 404（无代理/无静态资源匹配），断言 201 失败。
// 测试自身错误（语法/导入/浏览器缺失/端口污染）属无效 RED，需先修复测试基础设施。
test("browser reaches the real backend via same-origin /sessions", async ({ page }) => {
  const topic = "T0.2 同源连通性契约测试";

  // 1. POST /sessions：合法 topic + expert_count=4 → 201（由前端同源地址发出）
  const create = await page.request.post("/sessions", {
    data: { topic, expert_count: 4 },
  });
  expect(
    create.status(),
    `POST /sessions 应 201，实际 ${create.status()}（body: ${await create.text()})`,
  ).toBe(201);
  const created = await create.json();
  expect(created.session_id).toBeTruthy();
  expect(created.status).toBe("draft");
  expect(created.topic).toBe(topic);
  expect(created.expert_count).toBe(4);

  // 2. 从响应取得 session_id
  const sessionId = created.session_id as string;

  // 3. GET /sessions/{session_id} → 200
  const get = await page.request.get(`/sessions/${sessionId}`);
  expect(
    get.status(),
    `GET /sessions/${sessionId} 应 200，实际 ${get.status()}（body: ${await get.text()})`,
  ).toBe(200);
  const snap = await get.json();

  // 4. 快照属于刚创建的会话，status=draft，响应结构遵循现有快照契约
  expect(snap.session_id).toBe(sessionId);
  expect(snap.status).toBe("draft");
  expect(snap.topic).toBe(topic);
  expect(snap.expert_count).toBe(4);
  expect(Object.keys(snap).sort()).toEqual([
    "expert_count",
    "insights",
    "last_sequence",
    "participants",
    "session_id",
    "status",
    "summary",
    "topic",
    "transcript",
  ]);
  expect(snap.last_sequence).toBe(1); // 创建事件 sequence=1
  expect(snap.transcript).toEqual([]);
  expect(snap.insights).toEqual([]);
});

test("首页可二次确认删除讨论及其后端数据", async ({ page }) => {
  const topic = `待删除讨论-${Date.now()}`;
  const create = await page.request.post("/sessions", {
    data: { topic, expert_count: 3 },
  });
  expect(create.status()).toBe(201);
  const { session_id: sessionId } = await create.json();

  await page.goto("/");
  await expect(page.getByText(topic)).toBeVisible();
  await page.getByRole("button", { name: `删除讨论：${topic}` }).click();
  await expect(page.getByText("确定删除？")).toBeVisible();
  await page.getByTestId(`confirm-delete-${sessionId}`).click();

  await expect(page.getByText(topic)).toHaveCount(0);
  expect((await page.request.get(`/sessions/${sessionId}`)).status()).toBe(404);
});
