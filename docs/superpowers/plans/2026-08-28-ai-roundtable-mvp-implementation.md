# AI 圆桌讨论 Web App MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:executing-plans（本会话批量执行 + 检查点）或 superpowers:subagent-driven-development 逐任务实现。步骤使用 `- [ ]` 复选框跟踪。
> **禁止** 单条 Prompt 一次性生成整个项目；每任务归入逻辑提交组、组内测试通过后提交；TDD 任务严格 RED→GREEN→REFACTOR。

**Goal:** 实现一个本地运行、前后端分离的中文 AI 圆桌讨论 Web App MVP（算法调度 + SSE 实时 + SQLite 持久化 + 多讨论隔离 + 结构化共识/分歧）。

**Architecture:** 后端 FastAPI 单 worker asyncio 自动编排 + SSE 推送 + HTTP 命令；前端 React+TS+Vite 薄客户端（订阅 SSE + 发命令）；SQLite 为唯一权威状态来源，状态迁移 + 事件同一事务写入；LLM 经 FakeLLMProvider/ScriptedLLMProvider 默认隔离真实模型，真实模型仅显式 smoke test。

**Tech Stack:** Python 3.13 + FastAPI + aiosqlite + Pydantic；React + TypeScript + Vite + Vitest；Playwright + Microsoft Edge；SQLite(WAL)。

**Spec:** `docs/superpowers/specs/2026-08-28-ai-roundtable-mvp-design.md`（本计划从其论证，执行者需同时阅读该规格）

## Global Constraints（逐字摘自规格，每任务隐式包含）

- 会话状态机 9 态：`draft/panel_generating/panel_ready/ready/live/paused/finalizing/completed/failed`。
- 可恢复错误三元组：`last_stable_state` / `error_code` / `retry_operation`。
- 状态迁移 + 递增 `last_event_sequence` + 插入 `events` 三者在**同一 SQLite 事务**提交，提交后才 SSE 广播。
- `sequence` 会话内递增，`UNIQUE(session_id, sequence)`；SSE `id:` 用会话 sequence。
- 发言调度为**纯函数、确定性**（种子 = `session_id + turn_sequence`）；LLM 意图字段为不可信输入经 Pydantic 校验；模型不得指定最终发言者。
- 每次专家发言 1–2 句、整句事件推送（非 token 流式）。
- API Key 仅后端环境变量读取，永不进浏览器、永不入库、永不入日志。
- 单元/E2E 默认用 FakeLLM；真实模型 smoke test 显式启用、默认不耗额度、交付前必须实际执行一次并记录脱敏结果。
- 单进程单 Uvicorn worker；LLM 网络调用绝不发生在 DB 事务内。
- 错误消息为公开安全摘要；运行时不持久化原始 Prompt/模型响应/CoT/API Key。
- **所有命令从项目根目录 `C:\AI圆桌讨论APP` 经 Windows PowerShell 执行**，不依赖隐含 `cd`；后端测试经 `backend/pytest.ini`（`pythonpath = .`）运行；前端命令用 `npm --prefix frontend`。

---

## 阶段 / 任务 / 优先级 / 时间 总览

| Phase | 任务 | P0 | P1 | P2 | 预计 |
|-------|------|----|----|----|------|
| 1 SDD 工程契约与骨架 | 7 | 7 | 0 | 0 | 4.33h |
| 2 DDD / UI UX Pro Max 门禁 | 5 | 4 | 0 | 1 | 4.33h |
| 3 TDD 后端核心 | 15 | 14 | 1 | 0 | 11.75h |
| 4 LLM 与实时集成 | 6 | 6 | 0 | 0 | 6.08h |
| 5 E2E 与系统修复 | 10 | 10 | 0 | 0 | 10.25h |
| 6 文档与提交包 | 8 | 8 | 0 | 0 | 6.00h |
| **合计** | **51** | **49** | **1** | **1** | **42.75h（2565 min）** |

**时间分类（逐任务求和，无重复计算）：**

| 分类 | 时长 |
|------|------|
| 计划内任务总计（51 任务） | 42.75h |
| └ P0（49 任务） | 41.75h |
| └ P1（1 任务） | 0.50h |
| └ P2（1 任务） | 0.50h |
| 风险及最终验收缓冲 | 10.00h |
| **计划总占用** | **52.75h** |
| 距 72h 尚余（超时保护，不预先分配） | 19.25h |

> 说明：Phase 5（10.25h）已包含 E2E 集成与回归，Phase 6（6.00h）已包含最终材料整理，二者均计入 42.75h，不重复相加；P0+P1+P2 = 41.75 + 0.5 + 0.5 = 42.75h。

**优先级说明**：多会话隔离（3.14）、真实 DeepSeek 冒烟（4.6）、E2E 回归修复（5.10）、最终提交包核验（6.8）均为题目硬性要求，**全部 P0**。P1=调度器额外边界测试变体（3.15）；P2=演播厅视觉润色（2.5）。二者为仅有的可裁剪项。

---

## File Structure（待创建）

```
C:\AI圆桌讨论APP\
├─ README.md                        # 根目录（Task 6.1）
├─ backend\
│  ├─ requirements.txt
│  ├─ .env.example
│  ├─ pytest.ini                    # pythonpath = .
│  ├─ app\
│  │  ├─ __init__.py / main.py / config.py / db.py / schema.sql / seed.py
│  │  ├─ models\__init__.py
│  │  ├─ llm\base.py / openai_compat.py / fake.py / reliability.py
│  │  ├─ core\state_machine.py / scheduler.py / transactions.py / turns.py
│  │  │      / engine.py / engine_registry.py / event_store.py
│  │  │      / insight_worker.py / insights.py / transcript.py
│  │  │      / commands.py / limits.py / errors.py / reconciliation.py
│  │  └─ api\routes.py / sse.py / snapshot.py
│  └─ tests\conftest.py + test_*.py
├─ frontend\
│  ├─ package.json / vite.config.ts / tsconfig.json / index.html / playwright.config.ts
│  ├─ src\main.tsx / App.tsx / types.ts
│  ├─ src\api\client.ts / sse.ts
│  ├─ src\pages\Home.tsx / PanelSetup.tsx / Studio.tsx / Result.tsx
│  ├─ src\components\*.tsx
│  ├─ tests\*.test.ts(x)
│  └─ e2e\*.spec.ts
├─ design-system\MASTER.md
└─ docs\architecture.md / ai-development-workflow.md / prompt-log.md
```

**提交组（20 组，SDD→DDD→TDD→E2E→文档）：**

| 组 | 任务 | 主题 |
|----|------|------|
| CG1 | 1.1, 1.2 | 工程骨架（前后端） |
| CG2 | 1.3, 1.4 | 数据库 DDL + 种子 |
| CG3 | 1.5, 1.6, 1.7 | 模型 + 契约 + FakeLLM |
| CG4 | 2.1, 2.2 | UI UX Pro Max + 设计系统 |
| CG5 | 2.3 | 静态页面 |
| CG6 | 2.4, 2.5 | 视觉验收 + 润色 |
| CG7 | 3.1, 3.2 | 状态机 + 事务 |
| CG8 | 3.3, 3.4, 3.15 | 调度器 |
| CG9 | 3.5, 3.6, 3.7 | turn/registry/命令幂等 |
| CG10 | 3.8, 3.9, 3.10 | Transcript/洞察/Worker |
| CG11 | 3.11, 3.12, 3.13, 3.14 | 上限/错误/对账/隔离 |
| CG12 | 4.1, 4.2 | Provider + engine |
| CG13 | 4.3, 4.4 | SSE 事件日志 + 快照 |
| CG14 | 4.5, 4.6 | 前端实时 + smoke |
| CG15 | 5.1, 5.2 | E2E 全流程 + 实时 |
| CG16 | 5.3, 5.4, 5.5 | E2E 重连/隔离/降级 |
| CG17 | 5.6, 5.7, 5.8, 5.9 | E2E 上限/布局/密钥/重启 |
| CG18 | 5.10 | E2E 回归修复 |
| CG19 | 6.1–6.5 | 文档 |
| CG20 | 6.6–6.8 | 交付验收 |

---

# Phase 1：SDD 工程契约与骨架

> 停止点：`python -m pytest backend/tests -v` 全绿 + 后端健康检查 200 + `npm --prefix frontend run build` 通过。未通过不得进入 Phase 2。

### Task 1.1：后端目录骨架与依赖定义

**优先级**：P0　**预计**：25 min　**提交组**：CG1　**验收**：H1、F2

**Files:** Create `backend/requirements.txt`, `backend/.env.example`, `backend/pytest.ini`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`

**前置条件**：无（根提交已存在）。

**Interfaces:** Produces `config.Settings`、`main.app`（含 `/healthz`）。

- [ ] **Step 1: 写失败测试** — Create `backend/tests/test_config.py`:
```python
from app.config import Settings

def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    s = Settings()
    assert s.base_url == "https://example.test/v1"
    assert s.model == "test-model"

def test_settings_default_sqlite():
    assert Settings().sqlite_path.endswith("app.db")
```

- [ ] **Step 2: 运行测试确认失败**

Run（项目根）: `python -m pytest backend/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: 最小实现**

`backend/requirements.txt`:
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.2
pydantic-settings==2.5.2
aiosqlite==0.20.0
httpx==0.27.2
pytest==8.3.3
pytest-asyncio==0.24.0
```
`backend/.env.example`（占位为空，无真实密钥）:
```
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=
LLM_MODEL=deepseek-chat
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
SQLITE_PATH=./data/app.db
```
`backend/pytest.ini`:
```
[pytest]
pythonpath = .
asyncio_mode = auto
```
`backend/app/config.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    sqlite_path: str = "./data/app.db"
    class Config:
        env_prefix = "LLM_"
        env_file = ".env"
```
`backend/app/main.py`:
```python
from fastapi import FastAPI
app = FastAPI(title="AI Roundtable")

@app.get("/healthz")
async def healthz():
    return {"ok": True}
```

- [ ] **Step 4: 运行测试确认通过** — Run: `python -m pytest backend/tests/test_config.py -v` — Expected: PASS — 2 passed

- [ ] **Step 5: 人工检查点**：`.env.example` 无真实密钥；`pytest.ini` 设 `pythonpath = .`。

- [ ] **Step 6: 暂不提交**（归入 CG1；完成 CG1 全部任务并通过组级测试后，在 Task 1.2 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当 env 未读取或 `pythonpath` 未生效时。

---

### Task 1.2：前端目录骨架与依赖定义

**优先级**：P0　**预计**：30 min　**提交组**：CG1　**验收**：H1、F1

**Files:** Create `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/types.ts`

**前置条件**：Task 1.1。

**Interfaces:** Produces `frontend/src/types.ts` 类型。

- [ ] **Step 1: 写失败测试** — Create `frontend/tests/smoke.test.ts`:
```ts
import { describe, it, expect } from "vitest";
describe("smoke", () => { it("loads vitest", () => { expect(1 + 1).toBe(2); }); });
```

- [ ] **Step 2: 运行测试确认失败**

Run（项目根）: `npm --prefix frontend run test -- tests/smoke.test.ts`
Expected: FAIL — vitest 未安装 / Cannot find module

- [ ] **Step 3: 最小实现**

`frontend/package.json`:
```json
{
  "name": "ai-roundtable-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "e2e": "playwright test"
  },
  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1" },
  "devDependencies": {
    "@types/react": "^18.3.5", "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1", "typescript": "^5.5.4",
    "vite": "^5.4.3", "vitest": "^2.0.5", "@playwright/test": "^1.46.1",
    "@testing-library/react": "^16.0.0", "@testing-library/jest-dom": "^6.4.8",
    "jsdom": "^24.1.1"
  }
}
```
`frontend/vite.config.ts`（`plugins:[react()]` + `test:{environment:"jsdom"}`）。
`frontend/src/types.ts`（`SessionStatus`/`Participant`/`Utterance`/`Insight`/`SSEEvent`，见规格 §8.2）。
`frontend/src/main.tsx` / `App.tsx`（中文占位渲染）。

- [ ] **Step 4: 运行测试确认通过**

Run: `npm --prefix frontend run test -- tests/smoke.test.ts`；再 `npm --prefix frontend run build`
Expected: PASS — 1 passed；build 退出码 0

- [ ] **Step 5: 人工检查点**：`package.json` 无密钥；build 成功。

- [ ] **Step 6: 提交（CG1）**

```powershell
git add backend/requirements.txt backend/.env.example backend/pytest.ini backend/app/__init__.py backend/app/main.py backend/app/config.py backend/tests/test_config.py frontend/package.json frontend/vite.config.ts frontend/tsconfig.json frontend/index.html frontend/src/main.tsx frontend/src/App.tsx frontend/src/types.ts frontend/tests/smoke.test.ts
git commit -m "feat: project skeleton (backend + frontend)"
```

**失败时**：调用 `superpowers:systematic-debugging`，当 build 类型错误时。

---

### Task 1.3：SQLite 最终 DDL 与幂等初始化

**优先级**：P0　**预计**：50 min　**提交组**：CG2　**验收**：H1、§8.2

**Files:** Create `backend/app/schema.sql`, `backend/app/db.py`, `backend/tests/test_db.py`

**前置条件**：Task 1.1。

**Interfaces:** Produces `db.init_db(conn)`、`db.get_write_conn(path)`。

- [ ] **Step 1: 写失败测试** — Create `backend/tests/test_db.py`:
```python
import aiosqlite, pytest
from app import db

@pytest.mark.asyncio
async def test_init_db_creates_all_tables(tmp_path):
    conn = await aiosqlite.connect(tmp_path / "t.db")
    await db.init_db(conn)
    names = {r[0] async for r in await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("sessions","participants","turns","utterances","insights","insight_evidence","events","command_receipts","discussion_reports"):
        assert t in names
    await conn.close()

@pytest.mark.asyncio
async def test_foreign_keys_enabled(tmp_path):
    conn = await aiosqlite.connect(tmp_path / "t.db")
    await db.init_db(conn)
    fk = (await (await conn.execute("PRAGMA foreign_keys")).fetchone())[0]
    assert fk == 1
    await conn.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest backend/tests/test_db.py -v`
Expected: FAIL — `module 'app.db' has no attribute 'init_db'`

- [ ] **Step 3: 最小实现** — `backend/app/schema.sql` 落地 §8.2 全部 DDL（含 `UNIQUE(session_id,sequence)`、`UNIQUE(session_id)` on reports、复合外键 `FOREIGN KEY(session_id, speaker_id)`、`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;`）；`db.py` 实现 `init_db`（`executescript` + `commit`）。

- [ ] **Step 4: 运行测试确认通过** — Run: `python -m pytest backend/tests/test_db.py -v` — Expected: PASS — 2 passed

- [ ] **Step 5: 人工检查点**：全部 9 表 + 约束 + 复合外键 + `foreign_keys=ON`。

- [ ] **Step 6: 暂不提交**（归入 CG2；完成 CG2 全部任务并通过组级测试后，在 Task 1.4 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当外键/约束错误时。

---

### Task 1.4：5 组幂等种子数据

**优先级**：P0　**预计**：40 min　**提交组**：CG2　**验收**：H1、§8.5

**Files:** Create `backend/app/seed.py`, `backend/tests/test_seed.py`

**前置条件**：Task 1.3。

**Interfaces:** Produces `seed.run(conn)`（幂等写入 5 条 `is_sample=1`、`panel_ready`）。

- [ ] **Step 1: 写失败测试** — `test_seed_writes_5_samples`（COUNT=5、status=`panel_ready`）+ `test_seed_idempotent`（跑两次仍 5）。

- [ ] **Step 2: 运行测试确认失败** — Run: `python -m pytest backend/tests/test_seed.py -v` — Expected: FAIL — `No module named 'app.seed'`

- [ ] **Step 3: 最小实现** — `SAMPLES` 含 5 组中文主题（AI 与社会不平等 / 远程办公 / 禁售燃油车 / 短视频对青少年 / 加密货币）+ 每场 1 主持 + 4 专家（姓名/职业/Title/立场/avatar_color/avatar_emoji）；`INSERT OR IGNORE` + 已存在则跳过 participant。

- [ ] **Step 4: 运行测试确认通过** — Run: `python -m pytest backend/tests/test_seed.py -v` — Expected: PASS — 2 passed

- [ ] **Step 5: 人工检查点**：5 组立场互斥、`is_sample=1`、幂等。

- [ ] **Step 6: 提交（CG2）**

```powershell
git add backend/app/schema.sql backend/app/db.py backend/app/seed.py backend/tests/test_db.py backend/tests/test_seed.py
git commit -m "feat(db): final DDL, init and seed data"
```

**失败时**：调用 `superpowers:systematic-debugging`，当 `UNIQUE` 冲突或重复插入时。

---

### Task 1.5：Pydantic 模型与事件信封

**优先级**：P0　**预计**：40 min　**提交组**：CG3　**验收**：§7.2、§7.3、B3

**Files:** Create `backend/app/models/__init__.py`, `backend/tests/test_models.py`

**前置条件**：Task 1.1。

**Interfaces:** Produces `SSEEventEnvelope`、`IntentBatch`/`IntentItem`、`InsightDelta`/`InsightEvidenceDelta`、`SessionOut`/`ParticipantOut`/`UtteranceOut`/`InsightOut`。

- [ ] **Step 1: 写失败测试**（`test_event_envelope_requires_sequence`、`test_intent_willingness_clamped`、`test_intent_bad_enum_rejected`、`test_insight_delta_relation_enum`）。

- [ ] **Step 2: 运行测试确认失败** — `python -m pytest backend/tests/test_models.py -v` — FAIL — import error

- [ ] **Step 3: 最小实现** — 枚举 `IntentType`/`Relation`；`IntentItem.willingness` 用 `Field(ge=0.0, le=1.0)`；`SSEEventEnvelope` 必填 `sequence`/`schema_version=1`。

- [ ] **Step 4: 运行测试确认通过** — PASS — 4 passed

- [ ] **Step 5: 人工检查点**：`willingness` 钳制、枚举严格、`schema_version` 存在。

- [ ] **Step 6: 暂不提交**（归入 CG3；完成 CG3 全部任务并通过组级测试后，在 Task 1.7 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当校验规则未生效时。

---

### Task 1.6：API / SSE 事件契约与路由桩

**优先级**：P0　**预计**：30 min　**提交组**：CG3　**验收**：H3、§7.1

**Files:** Create `backend/app/api/__init__.py`, `backend/app/api/routes.py`, `docs/architecture.md`, `backend/tests/test_contract.py`

**前置条件**：Task 1.5。

**Interfaces:** Produces `routes.router`（7 命令端点 + 1 SSE 端点桩）。

- [ ] **Step 1: 写失败测试** — 断言 7 个 POST + 1 个 GET 路由已注册（见 §7.1）。

- [ ] **Step 2: 运行测试确认失败** — FAIL — routes 未注册

- [ ] **Step 3: 最小实现** — `routes.router` 声明 8 个端点桩（返回 501）；`main.py` `include_router`。

- [ ] **Step 4: 运行测试确认通过** — PASS — 1 passed

- [ ] **Step 5: 人工检查点**：路径与 §7.1 完全一致。

- [ ] **Step 6: 暂不提交**（归入 CG3；完成 CG3 全部任务并通过组级测试后，在 Task 1.7 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当路由路径不匹配时。

---

### Task 1.7：FakeLLMProvider / ScriptedLLMProvider

**优先级**：P0　**预计**：45 min　**提交组**：CG3　**验收**：G2、§9.3

**Files:** Create `backend/app/llm/__init__.py`, `backend/app/llm/base.py`, `backend/app/llm/fake.py`, `backend/tests/test_fake_llm.py`

**前置条件**：Task 1.5。

**Interfaces:** Produces `LLMProvider` 协议、`ScriptedLLMProvider(script)`、`FakeLLMProvider`。

- [ ] **Step 1: 写失败测试**（scripted 返回预设 / 缺 key 抛 KeyError / fake 无网络）。

- [ ] **Step 2: 运行测试确认失败** — FAIL — `No module named 'app.llm.fake'`

- [ ] **Step 3: 最小实现** — `base.LLMProvider`（Protocol）；`fake.py` 两个类，不 import httpx。

- [ ] **Step 4: 运行测试确认通过** — PASS — 3 passed

- [ ] **Step 5: 人工检查点**：无网络依赖、按 call_type 返回预设。

- [ ] **Step 6: 提交（CG3）**

```powershell
git add backend/app/models/__init__.py backend/app/api/__init__.py backend/app/api/routes.py backend/app/llm/__init__.py backend/app/llm/base.py backend/app/llm/fake.py backend/app/main.py backend/tests/test_models.py backend/tests/test_contract.py backend/tests/test_fake_llm.py docs/architecture.md
git commit -m "feat: models, API contract and fake LLM"
```

**失败时**：调用 `superpowers:systematic-debugging`，当 async 协议签名不符时。

---

### Phase 1 停止点检查

- [ ] `python -m pytest backend/tests -v` 全绿
- [ ] `npm --prefix frontend run build` 成功
- [ ] `python -m uvicorn app.main:app --app-dir backend --port 8000`（单 worker，默认）后 `GET /healthz` 返回 200（验证后停止）

---

# Phase 2：DDD / UI UX Pro Max 设计门禁

> 停止点：`design-system/MASTER.md` 存在 + 静态页面视觉验收通过。未通过不得进入 Phase 3。

### Task 2.1：安装并验证 UI UX Pro Max（项目作用域，证据保存）

**优先级**：P0　**预计**：40 min　**提交组**：CG4　**验收**：§12.1、H5

**Files:** Create `docs/ui-ux-pro-max-install-evidence.md`

**前置条件**：Phase 1 停止点通过。

**Interfaces:** Produces 证据文档 + 可调用的 `ui-ux-pro-max` 技能。

- [ ] **Step 1: 添加官方市场**

Run（项目根）: `/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill`

- [ ] **Step 2: 项目作用域安装**

Run: `/plugin install ui-ux-pro-max@ui-ux-pro-max-skill`；提示选择作用域时选 **"Install for all collaborators on this repository"**。

- [ ] **Step 3: 重载并核验**

Run: `/reload-plugins`；随后调用 `ui-ux-pro-max`（或对应命令）确认返回技能内容而非"未找到"。

- [ ] **Step 4: 保存证据** — `docs/ui-ux-pro-max-install-evidence.md` 记录上述 4 条命令、技能版本（若可得）、加载成功证据、会话日期与模型；**不写任何本地 settings 内容或密钥**。

- [ ] **Step 5: 人工检查点**：确为项目作用域；证据不含敏感配置。

- [ ] **Step 6: 暂不提交**（归入 CG4；完成 CG4 全部任务并通过组级测试后，在 Task 2.2 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当安装失败或加载"未找到"时（不绕过、不手写替代）。

---

### Task 2.2：生成并持久化演播厅设计系统

**优先级**：P0　**预计**：60 min　**提交组**：CG4　**验收**：§12.1

**Files:** Create `design-system/MASTER.md`

**前置条件**：Task 2.1。

**Interfaces:** Produces `design-system/MASTER.md` 设计 token 与组件状态定义。

- [ ] **Step 1: 调用技能** — `ui-ux-pro-max` 生成"AI 演播厅 / 新闻直播控制台"设计系统。

- [ ] **Step 2: 持久化** — 写入 `design-system/MASTER.md`，逐项覆盖：色彩（暗/亮）、字体、间距刻度、布局网格、组件状态（等待/准备/发言 + 卡片 9 态）、响应式断点（1280 / 1920+）、独立滚动区域（席位区/Transcript/洞察侧栏）、键盘焦点、`prefers-reduced-motion`、明确反模式（状态不得只靠颜色）。

- [ ] **Step 3: 人工检查点**：覆盖 §12.1 全部字段，无占位符。

- [ ] **Step 4: 提交（CG4）**

```powershell
git add docs/ui-ux-pro-max-install-evidence.md design-system/MASTER.md
git commit -m "docs(ui): ui-ux-pro-max evidence and design system"
```

**失败时**：调用 `superpowers:systematic-debugging`，当缺项或偏离主题时。

---

### Task 2.3：静态页面与组件状态（Mock 数据）

**优先级**：P0　**预计**：90 min　**提交组**：CG5　**验收**：A1、F1、F3、B2

**Files:** Create `frontend/src/pages/Home.tsx`, `PanelSetup.tsx`, `Studio.tsx`, `Result.tsx`, `frontend/src/components/DiscussionCard.tsx`, `PanelCard.tsx`, `ParticipantSeat.tsx`, `Transcript.tsx`, `InsightPanel.tsx`, `frontend/tests/pages.test.tsx`

**前置条件**：Task 2.2。

**Interfaces:** Consumes `design-system/MASTER.md`、`types.ts`；Produces 4 页面 + 5 组件。

- [ ] **Step 1: 写失败测试** — `pages.test.tsx`：`DiscussionCard` 对 `is_sample` 显示"示例讨论"；按 `status` 映射路由（draft/panel_generating/panel_ready→`/panel`、ready/live/paused→`/studio`、finalizing→`/finalizing`、completed→`/result`、failed→`/failed`）。

- [ ] **Step 2: 运行测试确认失败** — `npm --prefix frontend run test -- tests/pages.test.tsx` — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — 实现页面与组件；`ParticipantSeat` 三态含文本标签+图标（不单靠颜色）；各区域 `overflow:auto`；`.motion-safe` 包动画。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：4 页面静态渲染、9 态路由正确、无全页滚动。

- [ ] **Step 6: 提交（CG5）**

```powershell
git add frontend/src/pages frontend/src/components frontend/tests/pages.test.tsx frontend/vite.config.ts frontend/package.json
git commit -m "feat(ui): add static pages and component states"
```

**失败时**：调用 `superpowers:systematic-debugging`，当 jsdom 环境失败时。

---

### Task 2.4：普通桌面与超宽屏视觉验收

**优先级**：P0　**预计**：40 min　**提交组**：CG6　**验收**：F1、F3

**Files:** Create `frontend/e2e/visual.spec.ts`, `frontend/playwright.config.ts`

**前置条件**：Task 2.3。

- [ ] **Step 1: 写失败测试** — `visual.spec.ts`：对 1280/1920 断言 `document.documentElement.scrollWidth <= clientWidth`；`playwright.config.ts` 用 `channel: "msedge"` + `webServer`。

- [ ] **Step 2: 运行测试确认失败** — `npm --prefix frontend run e2e -- visual.spec.ts` — FAIL — 无路由/服务

- [ ] **Step 3: 最小实现** — 配 `webServer`（`npm run dev`）+ 路由；确保无横向溢出。

- [ ] **Step 4: 运行测试确认通过** — PASS — 2 passed

- [ ] **Step 5: 人工检查点**：Edge channel 启用；1280/1920 无横向滚动。

- [ ] **Step 6: 提交（CG6）**

```powershell
git add frontend/e2e/visual.spec.ts frontend/playwright.config.ts
git commit -m "test(e2e): add visual acceptance for desktop and ultrawide"
```

**失败时**：调用 `superpowers:systematic-debugging`，当横向溢出时。

---

### Task 2.5：演播厅视觉润色（P2，可裁剪）

**优先级**：P2　**预计**：30 min　**提交组**：CG6　**验收**：非必需（增强）

**Files:** Modify `frontend/src/components/*.tsx`

**前置条件**：Task 2.4。

- [ ] 过渡微动效、悬停态、空状态插画。仅当 P0 完成后有余力时执行；可整项放弃。提交并入 CG6。

---

### Phase 2 停止点检查

- [ ] `design-system/MASTER.md` 覆盖 §12.1 全部字段
- [ ] `npm --prefix frontend run test` + `npm --prefix frontend run e2e -- visual.spec.ts` 全绿

---

# Phase 3：TDD 后端核心

> 全局：本阶段**必须**先调用 `superpowers:test-driven-development`，每任务严格 RED→GREEN→REFACTOR；先写测试再实现，禁止先实现后补测试。
> 停止点：`python -m pytest backend/tests -v` 全绿，覆盖状态机/调度/事务/隔离/洞察。

### Task 3.1：会话状态机（9 态迁移）

**优先级**：P0　**预计**：40 min　**提交组**：CG7　**验收**：B1、E1、§5.1

**Files:** Create `backend/app/core/state_machine.py`, `backend/tests/test_state_machine.py`

**Interfaces:** Produces `SessionState` 枚举、`TRANSITIONS`、`can_transition(src, dst)`。

- [ ] **Step 1: 写失败测试** — `live→finalizing` 允许；`completed` 无出边；`panel_ready→live` 拒绝；`panel_generating→draft` 允许。

- [ ] **Step 2: 运行测试确认失败** — `python -m pytest backend/tests/test_state_machine.py -v` — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — 按 §5.1 迁移表编码 `TRANSITIONS`（含 `*→failed`）。

- [ ] **Step 4: 运行测试确认通过** — PASS — 4 passed

- [ ] **Step 5: 人工检查点**：`COMPLETED`/`FAILED` 无出边。

- [ ] **Step 6: 暂不提交**（归入 CG7；完成 CG7 全部任务并通过组级测试后，在 Task 3.2 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当迁移表不一致时。

---

### Task 3.2：状态 + 事件同事务三写

**优先级**：P0　**预计**：50 min　**提交组**：CG7　**验收**：§7.4、§7.7、C 类

**Files:** Create `backend/app/core/transactions.py`, `backend/tests/test_transactions.py`

**Interfaces:** Produces `async commit_event(conn, session_id, event_type, payload, state_updates) -> sequence`。

- [ ] **Step 1: 写失败测试** — 事务写后 state+event 一致；事件写冲突整体回滚；两会话 sequence 各自从 1。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — `BEGIN IMMEDIATE` → 应用 state_updates → `last_event_sequence+1` → UPDATE + INSERT events → COMMIT；异常 ROLLBACK 后重抛。

- [ ] **Step 4: 运行测试确认通过** — PASS — 3 passed

- [ ] **Step 5: 人工检查点**：写失败回滚；sequence 会话内独立。

- [ ] **Step 6: 提交（CG7）**

```powershell
git add backend/app/core/__init__.py backend/app/core/state_machine.py backend/app/core/transactions.py backend/tests/test_state_machine.py backend/tests/test_transactions.py
git commit -m "feat(core): state machine and atomic transactions"
```

**失败时**：调用 `superpowers:systematic-debugging`，当回滚/串线时。

---

### Task 3.3：发言调度纯函数

**优先级**：P0　**预计**：60 min　**提交组**：CG8　**验收**：B1、§6.3、§6.7

**Files:** Create `backend/app/core/scheduler.py`, `backend/tests/test_scheduler.py`

**Interfaces:** Produces `pick_speaker(candidates, intents, stances, history, *, seed) -> str`、`RuleScheduler`。

- [ ] **Step 1: 写失败测试** — 上一位排除；同种子确定性；防饥饿；规则降级。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — `score = 0.4w + 0.3rel + 0.2fair + 0.1div`；硬过滤上一位；防饥饿阈值；`random.Random(f"{seed}:{turn}")`。

- [ ] **Step 4: 运行测试确认通过** — PASS — 4 passed

- [ ] **Step 5: 人工检查点**：纯函数无 IO；确定性。

- [ ] **Step 6: 暂不提交**（归入 CG8；完成 CG8 全部任务并通过组级测试后，在 Task 3.4 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当确定性/防饥饿断言失败时。

---

### Task 3.4：点名例外 / 防连续 / 防饥饿 / 种子确定性

**优先级**：P0　**预计**：45 min　**提交组**：CG8　**验收**：B1、§6.3、§6.7

**Files:** Modify `backend/app/core/scheduler.py`, `backend/tests/test_scheduler.py`

- [ ] **Step 1: 写失败测试** — 主持人点名 `named_followup` 允许重复；单候选放行；`host_interjected` 不清空历史。

- [ ] **Step 2: 运行测试确认失败** — 新增断言失败

- [ ] **Step 3: 最小实现** — `named_followup` 跳过排他；单候选放行；`host_interjected` 不改 gap/counts。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：例外不误伤正常排他。

- [ ] **Step 6: 提交（CG8）**

```powershell
git add backend/app/core/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat(core): deterministic scheduler with followup exception"
```

**失败时**：调用 `superpowers:systematic-debugging`，当例外误伤时。

---

### Task 3.5：turns / generation_epoch

**优先级**：P0　**预计**：45 min　**提交组**：CG9　**验收**：§5.3、§8.2、E1

**Files:** Create `backend/app/core/turns.py`, `backend/tests/test_turns.py`

**Interfaces:** Produces `create_turn(...)`、`cancel_turn(...) -> new_epoch`、`is_epoch_valid(...)`。

- [ ] **Step 1: 写失败测试** — create 后 `generating`/`epoch=1`；cancel 后 `cancelled`/`epoch=2`；取消后旧 epoch 无效。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — INSERT turns；取消时 `generation_epoch+1`。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：epoch 单调递增。

- [ ] **Step 6: 暂不提交**（归入 CG9；完成 CG9 全部任务并通过组级测试后，在 Task 3.7 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当 epoch 未递增时。

---

### Task 3.6：EngineRegistry（原子 get-or-create）

**优先级**：P0　**预计**：45 min　**提交组**：CG9　**验收**：D2、§9.1

**Files:** Create `backend/app/core/engine_registry.py`, `backend/tests/test_engine_registry.py`

**Interfaces:** Produces `EngineRegistry`（`get_or_create`/`remove`，session 级锁）。

- [ ] **Step 1: 写失败测试** — 并发 get_or_create 只创建 1 个；remove 后可重建。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — `dict[session_id] -> (asyncio.Lock, engine)`。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：并发不产生双 engine。

- [ ] **Step 6: 暂不提交**（归入 CG9；完成 CG9 全部任务并通过组级测试后，在 Task 3.7 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当双 engine 时。

---

### Task 3.7：command_receipts 幂等

**优先级**：P0　**预计**：40 min　**提交组**：CG9　**验收**：D2、§7.6

**Files:** Create `backend/app/core/commands.py`, `backend/tests/test_commands.py`

**Interfaces:** Produces `register_command(conn, session_id, command_id, command_type) -> bool`。

- [ ] **Step 1: 写失败测试** — 首次 True；重复 False；重复不改 status。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — `INSERT ... ON CONFLICT(session_id,command_id) DO NOTHING` + `changes()`。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：不依赖内存去重。

- [ ] **Step 6: 提交（CG9）**

```powershell
git add backend/app/core/turns.py backend/app/core/engine_registry.py backend/app/core/commands.py backend/tests/test_turns.py backend/tests/test_engine_registry.py backend/tests/test_commands.py
git commit -m "feat(core): turns, engine registry and command idempotency"
```

**失败时**：调用 `superpowers:systematic-debugging`，当 ON CONFLICT 未生效时。

---

### Task 3.8：Transcript（utterances 追加）

**优先级**：P0　**预计**：45 min　**提交组**：CG10　**验收**：C1、§8.3

**Files:** Create `backend/app/core/transcript.py`, `backend/tests/test_transcript.py`

**Interfaces:** Produces `append_utterance(conn, session_id, turn_id, speaker_id, role, text, ordinal) -> id`。

- [ ] **Step 1: 写失败测试** — 空 text 拒绝；跨会话 speaker 拒绝；追加后 ordinal 递增 + 事件落库。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — 校验后事务内 INSERT + `commit_event(utterance.completed)`。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：只含完整已持久化发言。

- [ ] **Step 6: 暂不提交**（归入 CG10；完成 CG10 全部任务并通过组级测试后，在 Task 3.10 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当跨会话 speaker 未被拒绝时。

---

### Task 3.9：insight_evidence 确定性聚合

**优先级**：P0　**预计**：50 min　**提交组**：CG10　**验收**：§8.4、B3

**Files:** Create `backend/app/core/insights.py`, `backend/tests/test_insights.py`

**Interfaces:** Produces `apply_insight_delta(conn, session_id, utterance_id, participant_id, delta) -> version`、`recompute_counts(conn, insight_id)`。

- [ ] **Step 1: 写失败测试** — 同一 participant 重复 supports 只计 1；oppose 分开聚合；`UNIQUE(insight_id,utterance_id,relation)` 冲突不重复插。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — `INSERT OR IGNORE` evidence + `COUNT(DISTINCT participant_id)` 回写计数。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：真值来自 evidence、DISTINCT participant。

- [ ] **Step 6: 暂不提交**（归入 CG10；完成 CG10 全部任务并通过组级测试后，在 Task 3.10 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当重复 evidence 致计数膨胀时。

---

### Task 3.10：洞察 Worker（ordinal 顺序 + 并发信号量）

**优先级**：P0　**预计**：60 min　**提交组**：CG10　**验收**：§9.2、E2

**Files:** Create `backend/app/core/insight_worker.py`, `backend/tests/test_insight_worker.py`

**Interfaces:** Produces `InsightWorker`（`claim_next(session_id)` 状态条件更新防双领）。

- [ ] **Step 1: 写失败测试** — 同会话按 ordinal 领取；claim 后 `processing`；二次 claim 返回 None；达上限 `permanently_failed`。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — `UPDATE ... SET insight_status='processing' WHERE id=? AND insight_status IN ('pending','retry_wait')` + `changes()`。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：严格 ordinal；跨会话可并行（信号量）。

- [ ] **Step 6: 提交（CG10）**

```powershell
git add backend/app/core/transcript.py backend/app/core/insights.py backend/app/core/insight_worker.py backend/tests/test_transcript.py backend/tests/test_insights.py backend/tests/test_insight_worker.py
git commit -m "feat(core): transcript, insights and insight worker"
```

**失败时**：调用 `superpowers:systematic-debugging`，当重复领取时。

---

### Task 3.11：软上限与绝对上限

**优先级**：P0　**预计**：40 min　**提交组**：CG11　**验收**：E3、§10.3

**Files:** Create `backend/app/core/limits.py`, `backend/tests/test_limits.py`

**Interfaces:** Produces `check_limits(count, soft_limit, absolute_limit, granted_extra) -> (action, remaining)`。

- [ ] **Step 1: 写失败测试** — 39→continue；40→paused；+10 后继续；100→must_end。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — 纯函数；软上限=40+granted_extra，绝对 100。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：绝对上限不可绕过。

- [ ] **Step 6: 暂不提交**（归入 CG11；完成 CG11 全部任务并通过组级测试后，在 Task 3.14 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当绝对上限被绕过时。

---

### Task 3.12：错误分级与安全降级

**优先级**：P0　**预计**：60 min　**提交组**：CG11　**验收**：E1、E2、§10.1、§10.4

**Files:** Create `backend/app/core/errors.py`, `backend/tests/test_errors.py`

**Interfaces:** Produces `classify_error(exc) -> ErrorClass`（recoverable/auth/schema/fatal）+ 降级字段结构。

- [ ] **Step 1: 写失败测试** — 超时/429→recoverable；401/402→auth；schema→schema；磁盘满→fatal；`degraded_components` 记录。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — 异常→ErrorClass 映射 + 降级计数器。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：仅 fatal 进 failed；错误消息公开摘要。

- [ ] **Step 6: 暂不提交**（归入 CG11；完成 CG11 全部任务并通过组级测试后，在 Task 3.14 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当越级进 failed 时。

---

### Task 3.13：服务启动对账（幂等）

**优先级**：P0　**预计**：45 min　**提交组**：CG11　**验收**：C4、§9.2

**Files:** Create `backend/app/core/reconciliation.py`, `backend/tests/test_reconciliation.py`

**Interfaces:** Produces `reconcile(conn)`（幂等）。

- [ ] **Step 1: 写失败测试** — 遗留 preparing→waiting；在途 turn→cancelled；live→paused；幂等。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — 幂等 UPDATE 集合。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：重启后不自动调 LLM。

- [ ] **Step 6: 暂不提交**（归入 CG11；完成 CG11 全部任务并通过组级测试后，在 Task 3.14 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当非幂等时。

---

### Task 3.14：多会话隔离（并发自动化测试）

**优先级**：P0　**预计**：50 min　**提交组**：CG11　**验收**：D1、§9.1

**Files:** Create `backend/tests/test_isolation.py`

**前置条件**：Task 3.6。

**Interfaces:** 无新模块（验证现有 engine/registry 隔离）。

- [ ] **Step 1: 写失败测试** — 两 engine 各自独立推进；会话 A 慢 LLM 不阻塞 B 调度；B 的 SSE 不收到 A 的事件。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 隔离未实现/共享状态

- [ ] **Step 3: 最小实现** — 修复任何共享可变状态；确保 engine 状态互不共享。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：一场失败/暂停不影响另一场。

- [ ] **Step 6: 提交（CG11）**

```powershell
git add backend/app/core/limits.py backend/app/core/errors.py backend/app/core/reconciliation.py backend/tests/test_limits.py backend/tests/test_errors.py backend/tests/test_reconciliation.py backend/tests/test_isolation.py
git commit -m "feat(core): limits, errors, reconciliation and isolation"
```

**失败时**：调用 `superpowers:systematic-debugging`，当会话串线时。

---

### Task 3.15：调度器额外边界测试变体（P1，可裁剪）

**优先级**：P1　**预计**：30 min　**提交组**：CG8　**验收**：G1（增强覆盖）

**Files:** Modify `backend/tests/test_scheduler.py`

- [ ] 属性式/模糊化补充用例（随机输入不抛异常、恒返回合法候选）。仅 P0 完成后有余力时执行；可裁剪。

---

### Phase 3 停止点检查

- [ ] `python -m pytest backend/tests -v` 全绿
- [ ] 覆盖 §6.7 P1–P11 调度不变量

---

# Phase 4：LLM 与实时集成

> 停止点：SSE 端到端打通（后端事件 → 前端渲染），FakeLLM 全程可用。未通过不得进入 Phase 5。

### Task 4.1：OpenAI 兼容 Provider + 统一可靠性

**优先级**：P0　**预计**：50 min　**提交组**：CG12　**验收**：§9.3、F2、E1

**Files:** Create `backend/app/llm/openai_compat.py`, `backend/app/llm/reliability.py`, `backend/tests/test_reliability.py`

**Interfaces:** Produces `OpenAICompatProvider(settings)`、`call_with_retry(...)`。

- [ ] **Step 1: 写失败测试** — 用 httpx MockTransport：URL/头不泄 key；超时→退避；429→重试；401→不重试。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — httpx AsyncClient + `1s*2^n`+jitter（n≤3）；超时/429/5xx 重试；401/402 立即抛；全局+每会话信号量。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：key 不进入日志/前端；网络调用不在 DB 事务内。

- [ ] **Step 6: 暂不提交**（归入 CG12；完成 CG12 全部任务并通过组级测试后，在 Task 4.2 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当重试/退避不符矩阵时。

---

### Task 4.2：六类调用编排（engine 循环）

**优先级**：P0　**预计**：90 min　**提交组**：CG12　**验收**：§9.3、B2

**Files:** Create `backend/app/core/engine.py`, `backend/tests/test_engine.py`

**前置条件**：Task 3.3–3.10、4.1。

**Interfaces:** Produces `DiscussionEngine`（`start/pause/resume/end`）。

- [ ] **Step 1: 写失败测试** — 用 ScriptedLLM 跑整场：≥1 开场 + ≥1 专家发言 + 洞察事件，`live`；结束→`finalizing`→`completed`。

- [ ] **Step 2: 运行测试确认失败** — FAIL — engine 未实现

- [ ] **Step 3: 最小实现** — `while live: host_or_expert(); batch_intent(); pick(); generate(); insight()`；中断/结束检查点插在 LLM 调用之间。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：六类调用各就位；结束走 finalizing。

- [ ] **Step 6: 提交（CG12）**

```powershell
git add backend/app/llm/openai_compat.py backend/app/llm/reliability.py backend/app/core/engine.py backend/tests/test_reliability.py backend/tests/test_engine.py
git commit -m "feat: LLM provider reliability and engine loop"
```

**失败时**：调用 `superpowers:systematic-debugging`，当死锁/未检查中断时。

---

### Task 4.3：SSE 持久化事件日志 + 订阅注册表

**优先级**：P0　**预计**：60 min　**提交组**：CG13　**验收**：§7、C3

**Files:** Create `backend/app/core/event_store.py`, `backend/app/api/sse.py`, `backend/tests/test_sse.py`

**Interfaces:** Produces `EventStore`（`subscribe/broadcast/replay`）。

- [ ] **Step 1: 写失败测试** — 广播只达本 session；`after_seq` 只补发 > 序号；无订阅者事件仍落库。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — `dict[session_id, set[Queue]]`；SSE `StreamingResponse` + `id: <sequence>`，支持 `after_seq` 与 `Last-Event-ID` 取较大。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：heartbeat；断线不停止讨论。

- [ ] **Step 6: 暂不提交**（归入 CG13；完成 CG13 全部任务并通过组级测试后，在 Task 4.4 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当串线/补发丢失时。

---

### Task 4.4：REST 快照 + 重连补发

**优先级**：P0　**预计**：45 min　**提交组**：CG13　**验收**：C3、§7.5

**Files:** Create `backend/app/api/snapshot.py`, `backend/tests/test_snapshot.py`

**Interfaces:** Produces `get_session_snapshot(session_id) -> dict`（状态+Transcript+洞察+last_sequence）。

- [ ] **Step 1: 写失败测试** — 快照返回 `last_sequence` 且与事件表一致。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 未实现

- [ ] **Step 3: 最小实现** — 查询 sessions/utterances/insights + `last_event_sequence`。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：快照 last_sequence 供续订。

- [ ] **Step 6: 提交（CG13）**

```powershell
git add backend/app/core/event_store.py backend/app/api/sse.py backend/app/api/snapshot.py backend/tests/test_sse.py backend/tests/test_snapshot.py
git commit -m "feat(sse): event log and snapshot"
```

**失败时**：调用 `superpowers:systematic-debugging`，当快照序号不一致时。

---

### Task 4.5：前端实时渲染 + 断线恢复

**优先级**：P0　**预计**：90 min　**提交组**：CG14　**验收**：C1–C4、B2

**Files:** Create `frontend/src/api/sse.ts`, `frontend/src/api/client.ts`, `frontend/src/store/*`, `frontend/tests/sse.test.ts`

**Interfaces:** Produces `useSessionEvents(sessionId)`、`postCommand(...)`。

- [ ] **Step 1: 写失败测试** — `applyEvent` 对重复 sequence 幂等；`utterance.completed` 追加去重；重连用 `last_sequence`。

- [ ] **Step 2: 运行测试确认失败** — FAIL — 模块不存在

- [ ] **Step 3: 最小实现** — EventSource + Last-Event-ID；先 GET 快照再订阅。

- [ ] **Step 4: 运行测试确认通过** — PASS

- [ ] **Step 5: 人工检查点**：断线重连不丢事件、不重复。

- [ ] **Step 6: 暂不提交**（归入 CG14；完成 CG14 全部任务并通过组级测试后，在 Task 4.6 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当重复事件致 Transcript 重复时。

---

### Task 4.6：真实 DeepSeek API 冒烟验证（显式启用，交付前必执行一次）

**优先级**：P0　**预计**：30 min　**提交组**：CG14　**验收**：G2、§9.3

**Files:** Create `backend/tests/test_smoke_real.py`

**前置条件**：Task 4.1。

- [ ] **Step 1: 写失败测试** — `@pytest.mark.skipif(not os.environ.get("SMOKE_REAL_LLM"))` 包裹；真实调用一次 `chat/completions`，断言返回合法结构；默认跳过、不耗额度。

- [ ] **Step 2: 运行测试确认失败（默认跳过）** — `python -m pytest backend/tests/test_smoke_real.py -v` — Expected: SKIPPED（未设环境变量）

- [ ] **Step 3: 显式执行（交付前）** — 设置 `SMOKE_REAL_LLM=1` + 后端环境 `LLM_API_KEY`（仅本地 `.env`，不入仓）→ `python -m pytest backend/tests/test_smoke_real.py -v` — Expected: PASS；记录**脱敏**结果（仅 status/token/latency/error_code，不写 key/响应正文）。

- [ ] **Step 4: 人工检查点**：真实调用结果脱敏记录；key 未入仓。

- [ ] **Step 5: 提交（CG14）**

```powershell
git add frontend/src/api/sse.ts frontend/src/api/client.ts frontend/src/store frontend/tests/sse.test.ts backend/tests/test_smoke_real.py
git commit -m "feat(frontend): sse rendering and opt-in smoke test"
```

**失败时**：调用 `superpowers:systematic-debugging`，当真实调用返回异常结构时。

---

### Phase 4 停止点检查

- [ ] `python -m pytest backend/tests -v` + `npm --prefix frontend run test` 全绿
- [ ] FakeLLM 端到端可跑通一整场
- [ ] 真实 smoke（交付前）已执行并脱敏记录

---

# Phase 5：E2E 与系统修复

> 全程：发现问题调用 `superpowers:systematic-debugging`；完成前调用 `superpowers:verification-before-completion`。
> E2E 统一用 `npm --prefix frontend run e2e -- <spec>`，Playwright `webServer` 启动后端 + 前端，`channel: "msedge"`，后端用 FakeLLM。

### Task 5.1：完整用户流程 E2E

**优先级**：P0　**预计**：90 min　**提交组**：CG15　**验收**：A1–A5

**Files:** Create `frontend/e2e/full-flow.spec.ts`

**前置条件**：Phase 4 停止点。

- [ ] **Step 1: 写失败测试** — 断言链路：新建讨论 → 生成阵容 → re-roll 保留旧阵容 → **未确认无法进演播厅** → 确认进入 → 点"开始"才开场 → 多轮发言 → 暂停 → 继续 → 结束 → finalizing → 结果页含中文摘要 + 原始 JSON；结束后只读。
- [ ] **Step 2: 运行测试确认失败** — `npm --prefix frontend run e2e -- full-flow.spec.ts` — Expected: FAIL（链路上某断言未满足）
- [ ] **Step 3: 最小实现/修复** — 修复链路断点。
- [ ] **Step 4: 运行测试确认通过** — PASS
- [ ] **Step 5: 暂不提交**（归入 CG15；完成 CG15 全部任务并通过组级测试后，在 Task 5.2 统一提交）

**失败时**：调用 `superpowers:systematic-debugging`，当链路任一断言失败时。

---

### Task 5.2：实时 Transcript 与洞察 E2E

**优先级**：P0　**预计**：60 min　**提交组**：CG15　**验收**：C1、C2

**Files:** Create `frontend/e2e/realtime.spec.ts`

- [ ] **Step 1: 写失败测试** — 断言每发言后 Transcript 追加完整整句（不含内部事件）、侧栏共识/分歧/焦点随发言实时变化。
- [ ] **Step 2: 运行测试确认失败** — `npm --prefix frontend run e2e -- realtime.spec.ts` — Expected: FAIL
- [ ] **Step 3: 最小实现/修复** — 修复实时渲染。
- [ ] **Step 4: 运行测试确认通过** — PASS
- [ ] **Step 5: 提交（CG15）**

```powershell
git add frontend/e2e/full-flow.spec.ts frontend/e2e/realtime.spec.ts
git commit -m "test(e2e): full flow and realtime"
```

---

### Task 5.3：SSE 断线重连 + 去重 + 重复 command_id E2E

**优先级**：P0　**预计**：60 min　**提交组**：CG16　**验收**：C3、D2

**Files:** Create `frontend/e2e/reconnect.spec.ts`

- [ ] **Step 1: 写失败测试** — 断线重连后补发无丢失、无重复；重复 `command_id` 不双执行。
- [ ] **Step 2: 运行测试确认失败** — FAIL
- [ ] **Step 3: 最小实现/修复** — 修复补发/幂等。
- [ ] **Step 4: 运行测试确认通过** — PASS
- [ ] **Step 5: 暂不提交**（归入 CG16；完成 CG16 全部任务并通过组级测试后，在 Task 5.5 统一提交）

---

### Task 5.4：两场会话隔离 E2E

**优先级**：P0　**预计**：60 min　**提交组**：CG16　**验收**：D1

**Files:** Create `frontend/e2e/concurrency.spec.ts`

- [ ] **Step 1: 写失败测试** — 两场并发，事件不串线（各自 Transcript 只含本场发言）。
- [ ] **Step 2: 运行测试确认失败** — FAIL
- [ ] **Step 3: 最小实现/修复** — 修复串线。
- [ ] **Step 4: 运行测试确认通过** — PASS
- [ ] **Step 5: 暂不提交**（归入 CG16；完成 CG16 全部任务并通过组级测试后，在 Task 5.5 统一提交）

---

### Task 5.5：失败与降级路径 + finalizing 重试 E2E

**优先级**：P0　**预计**：60 min　**提交组**：CG16　**验收**：E1、E2

**Files:** Create `frontend/e2e/degradation.spec.ts`

- [ ] **Step 1: 写失败测试** — 注入 LLM 失败：意图→降级调度继续；洞察失败→不阻塞发言；最终报告失败→滞留 finalizing + 可重试且仅一份报告。
- [ ] **Step 2: 运行测试确认失败** — FAIL
- [ ] **Step 3: 最小实现/修复** — 修复降级。
- [ ] **Step 4: 运行测试确认通过** — PASS
- [ ] **Step 5: 提交（CG16）**

```powershell
git add frontend/e2e/reconnect.spec.ts frontend/e2e/concurrency.spec.ts frontend/e2e/degradation.spec.ts
git commit -m "test(e2e): reconnect, isolation and degradation"
```

---

### Task 5.6：软/绝对上限 E2E

**优先级**：P0　**预计**：45 min　**提交组**：CG17　**验收**：E3

**Files:** Create `frontend/e2e/limits.spec.ts`

- [ ] **Step 1: 写失败测试** — 40 条 → paused；点继续 +10；100 条只能结束。
- [ ] **Step 2: 运行测试确认失败** — FAIL
- [ ] **Step 3: 最小实现/修复** — 修复上限。
- [ ] **Step 4: 运行测试确认通过** — PASS
- [ ] **Step 5: 暂不提交**（归入 CG17；完成 CG17 全部任务并通过组级测试后，在 Task 5.9 统一提交）

---

### Task 5.7：布局 + reduced-motion + 滚动 E2E

**优先级**：P0　**预计**：60 min　**提交组**：CG17　**验收**：F1、F3

**Files:** Create `frontend/e2e/layout.spec.ts`

- [ ] **Step 1: 写失败测试** — 1280/1920 无重叠、无截断；席位区/Transcript/洞察区独立滚动；`prefers-reduced-motion` 下动画禁用。
- [ ] **Step 2: 运行测试确认失败** — FAIL
- [ ] **Step 3: 最小实现/修复** — 修复布局。
- [ ] **Step 4: 运行测试确认通过** — PASS
- [ ] **Step 5: 暂不提交**（归入 CG17；完成 CG17 全部任务并通过组级测试后，在 Task 5.9 统一提交）

---

### Task 5.8：API Key 不暴露 E2E

**优先级**：P0　**预计**：30 min　**提交组**：CG17　**验收**：F2

**Files:** Create `frontend/e2e/no-key.spec.ts`

- [ ] **Step 1: 写失败测试** — 捕获浏览器网络面板全部请求，断言响应/请求头不含 `LLM_API_KEY` 值或任何 `sk-...`。
- [ ] **Step 2: 运行测试确认失败** — FAIL（若泄漏）
- [ ] **Step 3: 最小实现/修复** — 确认 key 仅后端读取。
- [ ] **Step 4: 运行测试确认通过** — PASS
- [ ] **Step 5: 暂不提交**（归入 CG17；完成 CG17 全部任务并通过组级测试后，在 Task 5.9 统一提交）

---

### Task 5.9：刷新恢复 + 重启 live→paused E2E

**优先级**：P0　**预计**：60 min　**提交组**：CG17　**验收**：C4

**Files:** Create `frontend/e2e/restart.spec.ts`

- [ ] **Step 1: 写失败测试** — 刷新后权威状态恢复；重启后 live→paused 且不自动调 LLM。
- [ ] **Step 2: 运行测试确认失败** — FAIL
- [ ] **Step 3: 最小实现/修复** — 修复恢复。
- [ ] **Step 4: 运行测试确认通过** — PASS
- [ ] **Step 5: 提交（CG17）**

```powershell
git add frontend/e2e/limits.spec.ts frontend/e2e/layout.spec.ts frontend/e2e/no-key.spec.ts frontend/e2e/restart.spec.ts
git commit -m "test(e2e): limits, layout, key safety and restart"
```

---

### Task 5.10：E2E 回归修复（P0）

**优先级**：P0　**预计**：90 min　**提交组**：CG18　**验收**：G1

**Files:** Modify 受影响的实现文件 + `frontend/e2e/*.spec.ts`

- [ ] **Step 1: 全量 E2E** — `npm --prefix frontend run e2e` 跑全量，收集失败清单。
- [ ] **Step 2: 逐项修复** — 对每个失败调用 `superpowers:systematic-debugging` 定位并修复，禁止跳过或放宽断言。
- [ ] **Step 3: 复跑确认** — 全量 E2E 全绿。
- [ ] **Step 4: 提交（CG18）**

```powershell
git add frontend/e2e frontend/src backend/app
git commit -m "fix(e2e): resolve regression failures"
```

**失败时**：调用 `superpowers:systematic-debugging`（本任务核心动作）。

---

### Phase 5 停止点检查

- [ ] `npm --prefix frontend run e2e` 全绿（Edge channel）
- [ ] `superpowers:verification-before-completion` 通过（含 A1–H8 覆盖核对）

---

# Phase 6：文档与提交包

> 只能准备交付物，不自动发邮件、不推送远端、不提交招聘系统。文档任务无 RED/GREEN 测试，但每项有前置条件、精确文件、从根目录执行的 PowerShell 验证命令与预期证据；CG19/CG20 各只有一个 `git commit`，在组末位任务统一提交。

### Task 6.1：根目录 README

**优先级**：P0　**预计**：40 min　**提交组**：CG19　**验收**：H2

**Files:** Create `README.md`（项目根目录）

**前置条件**：Phase 5 停止点通过。

- [ ] **内容**：环境要求、安装、启动（`python -m uvicorn app.main:app --app-dir backend --port 8000`）、环境变量、**单 Uvicorn worker 约束**、测试命令、技术选型、主要 API、已完成能力与后续改进。
- [ ] **验证命令**（根目录）: `Get-Content README.md`
- [ ] **预期证据**：README 存在且含「单 worker」「环境变量」「测试命令」章节；无密钥。
- [ ] **提交**：暂不提交（归入 CG19，在 Task 6.5 统一提交）。

### Task 6.2：架构 / bounded contexts / ER / 数据库 / API/SSE / 测试策略

**优先级**：P0　**预计**：60 min　**提交组**：CG19　**验收**：H3

**Files:** Create/Modify `docs/architecture.md`

**前置条件**：Task 6.1。

- [ ] **内容**：系统顶层架构、业务/基础设施 bounded contexts（§8.2）、ER 图（mermaid）、数据库说明、API/SSE 契约（对齐 §7）、测试策略（FakeLLM 隔离 + smoke 显式）。
- [ ] **验证命令**: `Get-Content docs/architecture.md`；`Select-String -Path docs/architecture.md -Pattern 'bounded context','ER','SSE 契约'`
- [ ] **预期证据**：命中「bounded context」「ER」「SSE 契约」章节。
- [ ] **提交**：暂不提交（CG19）。

### Task 6.3：完成/待办对照表

**优先级**：P0　**预计**：30 min　**提交组**：CG19　**验收**：H3

**Files:** Modify `docs/architecture.md`（追加对照表）

**前置条件**：Task 6.2。

- [ ] **内容**：逐项列出 A1–H8 完成状态与验证命令，无"待办"占位。
- [ ] **验证命令**: `Select-String -Path docs/architecture.md -Pattern 'A1','A5','B1','C1','D1','E1','F1','G1','H1','H8'`
- [ ] **预期证据**：A1–H8 各验收号均命中且带验证命令。
- [ ] **提交**：暂不提交（CG19）。

### Task 6.4：ai-development-workflow.md

**优先级**：P0　**预计**：45 min　**提交组**：CG19　**验收**：H5

**Files:** Create `docs/ai-development-workflow.md`

**前置条件**：Task 6.1。

- [ ] **内容**：1–1.5 页：Claude Code + DeepSeek V4 Pro + Superpowers + UI UX Pro Max 真实使用方式，≥2–3 个典型问题及解决路径。
- [ ] **验证命令**: `Get-Content docs/ai-development-workflow.md`
- [ ] **预期证据**：含「UI UX Pro Max」「TDD」「E2E」关键词与问题/解决路径。
- [ ] **提交**：暂不提交（CG19）。

### Task 6.5：prompt-log 补齐 ≥5 段

**优先级**：P0　**预计**：40 min　**提交组**：CG19　**验收**：H4

**Files:** Modify `docs/prompt-log.md`

**前置条件**：Task 6.4。

- [ ] **内容**：补齐覆盖 SDD、DDD、TDD、E2E、最终修复/验收 5 段核心原始 Prompt，各附 1–2 句意图/挑战/纠偏。
- [ ] **验证命令**: `(Select-String -Path docs/prompt-log.md -Pattern '```text').Count`（原始 Prompt 代码块数 ≥ 5）
- [ ] **预期证据**：`text` 代码块数 ≥ 5；无隐藏推理/密钥。
- [ ] **提交（CG19）**：

```powershell
git add README.md docs/architecture.md docs/ai-development-workflow.md docs/prompt-log.md
git commit -m "docs: README, architecture and workflow"
```

### Task 6.6：Git 历史演进 + 敏感信息扫描

**优先级**：P0　**预计**：40 min　**提交组**：CG20　**验收**：H6、H7

**Files:** 无（验证任务）

**前置条件**：Task 6.5。

- [ ] **验证命令**（根目录）:
  - `git log --oneline`（核对演进顺序 docs/schema → UI → tests → feature → E2E → docs，禁止最后一次性提交）
  - `git grep -nE 'sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY' -- .`（应无命中）
  - `git ls-files | Select-String -Pattern '\.env$'`（应仅 `.env.example`）
- [ ] **预期证据**：git log 呈渐进式；无密钥/`.env`/Token/调试日志命中。
- [ ] **提交**：暂不提交（CG20）。

### Task 6.7：完整测试 + 构建 + 种子验证

**优先级**：P0　**预计**：60 min　**提交组**：CG20　**验收**：H1、G1

**Files:** 无（验证任务）

**前置条件**：Task 6.6。

- [ ] **验证命令**（根目录，记录实际结果）:
  - `python -m pytest backend/tests -v`
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run build`
  - `npm --prefix frontend run e2e`
  - `python -m pytest backend/tests/test_seed.py -v`（验证 5 组种子幂等，跑两次 COUNT=5）
- [ ] **预期证据**：四类测试全绿；种子幂等。
- [ ] **提交**：暂不提交（CG20）。

### Task 6.8：zip 内容检查 + 提交前检查清单

**优先级**：P0　**预计**：45 min　**提交组**：CG20　**验收**：H8

**Files:** 无（验证任务）

**前置条件**：Task 6.7。

- [ ] **创建 zip**（PowerShell，根目录，排除敏感/产物）:

```powershell
$exclude = '(\\node_modules\\|\\test-results\\|\\playwright-report\\|\\dist\\|\\__pycache__\\|\.db$|\.db-wal$|\.db-shm$|\.sqlite$)'
$files = Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch $exclude -and $_.Name -ne '.env' }
Compress-Archive -Path $files.FullName -DestinationPath ai-roundtable-mvp.zip -Force
```

- [ ] **zip 内容检查**: `tar -tf ai-roundtable-mvp.zip`
- [ ] **预期证据**：含 README/schema.sql/seed/5 组种子/`.env.example`；**不含** `.env`、`*.db`/`*.db-wal`/`*.db-shm`、`node_modules`、`test-results`/`playwright-report`。
- [ ] **提交前检查清单**：准备 GitHub/Gitee 链接与邮件清单（收件 `xulei@wisquest.com`、标题 `[远程作业提交]姓名`）；**不自动发邮件、不推送远端、不提交招聘系统**。
- [ ] **提交（CG20）**：

```powershell
git add ai-roundtable-mvp.zip
git commit -m "chore: final delivery package"
```

---

### Phase 6 停止点检查

- [ ] 全部 H1–H8 核验通过
- [ ] `superpowers:verification-before-completion` 通过

---

## 验收编号覆盖矩阵（每个硬性验收 → 具体 P0 任务 + 验证方法）

| 验收 | P0 任务 | 验证方法 |
|------|---------|---------|
| A1 9 态路由 | 2.3、5.1 | vitest 路由单测 + Playwright 卡片点击路由 |
| A2 未确认无法进入 | 5.1 | Playwright 断言门禁 |
| A3 不自动开始 | 4.2、5.1 | 单测 engine 不自动 start + E2E |
| A4 结束/中断分离、结束后只读 | 3.1、5.1 | 单测 completed 无出边 + E2E |
| A5 结果页中文摘要 + JSON | 5.1、6.2 | Playwright 断言字段 + JSON |
| B1 非固定顺序/不连续/无饥饿/确定性 | 3.3、3.4 | pytest 调度不变量 P1–P11 |
| B2 专家/主持三态显示 | 2.3、4.5 | vitest 组件 + E2E |
| B3 意图短摘要/无 CoT/不指定发言者/不越界 | 1.5、3.3 | pytest 校验 + 单测 |
| C1 Transcript 只追加完整持久化发言 | 3.8、5.2 | pytest + E2E |
| C2 每发言后洞察实时增量 | 3.9、3.10、5.2 | pytest + E2E |
| C3 断线补发/去重/只收本会话 | 4.3、4.4、4.5、5.3 | pytest SSE + E2E |
| C4 重启 live→paused 不自动 LLM | 3.13、5.9 | pytest 对账 + E2E |
| D1 多场并行互不影响 | 3.14、5.4 | pytest 隔离 + E2E |
| D2 并发单 engine / 重复 command 不双执行 | 3.6、3.7、5.3 | pytest + E2E |
| E1 失败矩阵正确终态 / 仅持久化损坏进 failed / 带 error_code | 3.12 | pytest |
| E2 意图降级 / 洞察不阻塞 / finalizing 单报告 | 3.10、3.12、5.5 | pytest + E2E |
| E3 40 软 / +10 / 100 绝对 | 3.11、5.6 | pytest + E2E |
| F1 中文/响应式/无全页滚动/独立滚动/不重叠 | 2.3、2.4、5.7 | Playwright |
| F2 API Key 仅后端 | 1.1、5.8 | E2E 网络面板断言 |
| F3 键盘焦点/非仅颜色/reduced-motion/不截断/滚动边界 | 2.3、2.4、5.7 | Playwright |
| G1 三层测试覆盖 | 3.x–5.x | pytest + vitest + playwright 全绿 |
| G2 FakeLLM 默认 / smoke 显式 | 1.7、4.6 | 测试隔离 + smoke 开关 |
| G3 每阶段独立 Commit / prompt-log 维护 | 各 CG + 6.5 | git log |
| H1 源码/schema/种子 | 1.3、1.4、6.7 | 文件存在 + 种子验证 |
| H2 README | 6.1 | README 内容核对 |
| H3 docs 架构/ER/契约/测试/对照 | 6.2、6.3 | 文档存在 + 内容 |
| H4 prompt-log ≥5 段 | 6.5 | 文件核对 |
| H5 ai-development-workflow | 6.4 | 文件核对 |
| H6 Git 演进 | 6.6 | git log 核对 |
| H7 敏感不入仓 | 6.6 | 扫描 |
| H8 zip + 清单 | 6.8 | zip 内容检查 |

## 自检结论

- 规格覆盖：A1–H8 每个硬性验收均有具体 P0 任务 + 明确验证方法（见上表）。
- 无占位符：Phase 5/6 已完整展开；无"稍后细化"/"到达该阶段再补"。
- UI UX Pro Max 门禁先于前端实现（Phase 2 先于 Phase 3/4/5）。
- 统计一致：6 阶段 / 51 任务 / P0=49、P1=1、P2=1 / 20 提交组。
- 命令均从 `C:\AI圆桌讨论APP` 根目录、Windows PowerShell 执行（`python -m pytest backend/tests`、`npm --prefix frontend`），未回显密钥。
- README 位于项目根目录 `README.md`。
