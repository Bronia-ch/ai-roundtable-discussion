# AI 圆桌讨论 Web App（MVP）

> 面向真实业务场景的多智能体圆桌讨论：从主题输入到阵容生成、实时发言、观点聚合和最终报告，一条链路完成。

**演示状态：已完成真实 DeepSeek 最小演示** · **测试：226 pytest / 9 Playwright / 86 Vitest 全部通过**

项目仓库：<https://github.com/Bronia-ch/ai-roundtable-discussion>

## 为什么值得看

- **实时协作体验**：SSE 增量事件驱动 transcript、专家状态和洞察面板。
- **可靠性优先**：SQLite 连接级写锁、命令幂等、断线续订和可恢复状态机。
- **工程化交付**：SDD → DDD → TDD → E2E 完整开发链路，附 Prompt 记录和演示证据。
- **可替换模型层**：OpenAI 兼容 Provider，支持真实 DeepSeek 与离线 FakeLLM。
- **上下文感知发言**：主持人和专家获取议题、立场与最近发言，降低机械重复，提升讨论连贯性。
- **可用性优化**：会话状态、发言计数、自动跟随、操作反馈和移动端布局完整覆盖。
- **真实席位状态**：主持人与专家的准备、发言、等待/空闲状态由后端原子事件驱动，可实时推送与断线重放。

## 演示截图

最终结果页、演播厅发言和阵容确认截图见 `docs/evidence/`（或项目交付包）。

本地运行、前后端分离的中文 AI 圆桌讨论应用：用户输入主题与专家人数，系统编排主持人开场、专家多轮发言（非固定轮流，由调度器结合意愿/公平/多样性决定），实时产出 Transcript、共识与分歧，结束后生成结构化总结与 JSON 结果。

## 1. 环境要求

| 依赖 | 版本要求 | 开发环境实测 |
|------|----------|--------------|
| Python | 3.10+（`str \| None` 语法） | 3.13.13 |
| Node.js / npm | Node 18+ / npm 9+（Vite 5） | v24.18.0 / 11.16.0 |
| 浏览器（E2E） | Edge（Chromium 通道） | msedge channel |

- 开发平台：Windows（PowerShell）；命令已按 Windows 路径适配。
- E2E 使用 `channel: "msedge"`，需要本机安装 Microsoft Edge。

## 2. 安装

```powershell
# 后端
cd backend
python -m venv .venv                      # 或使用项目根 .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 前端
cd ..\frontend
npm install
```

## 3. 配置（.env.example）

```powershell
cd backend
copy .env.example .env     # 或 cp .env.example .env
```

`backend/.env` 由 `app/config.py`（pydantic-settings，前缀 `LLM_`）读取：

| 变量 | 说明 |
|------|------|
| `LLM_BASE_URL` | OpenAI 兼容 API 基址（默认 `https://api.deepseek.com/v1`） |
| `LLM_API_KEY` | API Key；**留空时真实调用必然失败**——测试全程使用 FakeLLM，不发起网络请求 |
| `LLM_MODEL` | 模型 ID，默认 `deepseek-chat` |
| `LLM_SQLITE_PATH` | SQLite 路径（默认 `./data/app.db`；E2E 使用 `:memory:`） |

> 密钥纪律：`.env` 与所有 `*.key/*.pem` 均在 `.gitignore` 中，严禁提交；本仓库从未读取或输出真实密钥。

## 4. 启动（单 worker 约束）

```powershell
# 后端（进程 1）
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端（进程 2）
cd frontend
npm run dev        # http://localhost:5173，/sessions 前缀经 vite 代理到 8000
```

**必须单 worker**：SSE 订阅桶（`EventStore`）与引擎任务登记（`EngineRegistry`）均为进程内共享状态，多 worker/多进程会分片事件流与后台任务。本项目不提供 uvicorn `--workers > 1` 部署形态。

## 5. 测试命令

```powershell
# 后端全量（离线矩阵：SMOKE_REAL_LLM=0 → 真实 smoke 恒定 SKIPPED）
cd backend; $env:SMOKE_REAL_LLM='0'; python -m pytest tests -q

# 前端单测（Vitest，排除 e2e）
cd frontend; npm test

# 前端生产构建（tsc --noEmit 类型检查 + vite build）
cd frontend; npm run build

# 全量 Playwright E2E（自动拉起：内存 SQLite 后端 + vite dev；LLM 网络隔离，
# LLM_BASE_URL 指向本机无效地址，绝不请求真实 DeepSeek）
cd frontend; npm run e2e
```

## 6. 技术选型

| 层 | 选型 | 说明 |
|----|------|------|
| 后端 | FastAPI + uvicorn（asyncio 单进程） | 自动编排引擎 + HTTP 命令 + SSE 推送 |
| 数据库 | SQLite（aiosqlite，WAL + 外键 + busy_timeout） | 唯一权威状态来源；9 张表 + 幂等补列迁移 |
| LLM 适配 | OpenAI 兼容 Provider + 可注入替身 | 六类调用：阵容/意图/发言/主持人/洞察/报告 |
| 可靠性 | 有限指数退避 + jitter、错误分级、Schema 修复 | 仅 RECOVERABLE 重试；AUTH/SCHEMA/FATAL 不重试 |
| 前端 | React 18 + TypeScript + Vite 5 | 快照初始化 → SSE 增量推进，三重幂等去重 |
| E2E | Playwright（Edge/Chromium） | webServer 自动编排，内存库 + 网络隔离 LLM |

## 7. 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/sessions` | 创建会话（201，draft） |
| POST | `/sessions/{id}/panel/generate` | 生成阵容（LLM） |
| POST | `/sessions/{id}/panel/confirm` | 确认阵容 |
| POST | `/sessions/{id}/discussion/start` | 开始讨论（引擎持续运行） |
| POST | `/sessions/{id}/discussion/pause` / `resume` / `end` | 中断 / 恢复 / 结束 |
| POST | `/sessions/{id}/retry` | 安全重试（报告等） |
| GET | `/sessions/{id}` | 快照（status/last_sequence/transcript/insights） |
| GET | `/sessions/{id}/events` | SSE 事件流（`after_seq` / `Last-Event-ID` 续订） |
| DELETE | `/sessions/{id}` | 停止后台任务并原子删除会话及从属数据 |
| GET | `/healthz` | 健康检查 |

命令均为 `POST {"command_id": "..."}`，经 `command_receipts` 幂等（重复 ID 返回 202 不重复副作用）。

## 8. 已完成能力

- **SDD**：产品规格、9 态状态机、Schema 与事件契约先行（`docs/superpowers/specs/`）；
- **DDD/UI**：UI UX Pro Max 设计系统（`design-system/MASTER.md`）+ 静态页面 + Edge 视觉验收；
- **TDD 核心**：状态机与事件同事务、确定性调度、turns/epoch、命令幂等、Transcript、洞察聚合、上限与错误分级、对账、多会话隔离；
- **LLM 集成**：OpenAI 兼容 Provider、重试矩阵、SSE 事件日志、快照与断线恢复、FakeLLM 离线端到端；
- **系统修复**：panel/命令原子化、引擎生命周期（start/pause/resume/end + finalize 重试）、降级阶梯（RuleScheduler/utterance/insight 降级记账）、软上限 40 +10 / 绝对上限 100、失败轮恢复复用。

## 9. 已知边界

- **真实 LLM**：演示阶段已用 `deepseek-chat` 完成真实最小请求；自动化 E2E 仍默认使用 FakeLLM 以保证离线、稳定和不消耗额度。API key 只由后端读取，绝不进入前端或仓库。
- **单 worker / 单机**：SSE 与引擎任务进程内共享，不支持多进程横向扩展；SQLite 为本地单写者模型。
- **生产部署未做**：仅本地 uvicorn + Vite；无容器化、无 CI、无鉴权（API Key 仅存在于后端进程）。
- **真实模型输出差异**：已兼容 Markdown JSON 代码块与主持/发言的自然语言返回；报告、阵容等结构化调用仍要求合法 JSON。
- **浏览器支持**：E2E 仅验证 Edge/Chromium 通道。

## 10. 文档索引

- `docs/architecture.md` —— 架构、bounded contexts、ER、数据库/迁移、API/SSE 契约、测试策略
- `docs/development-workflow.md` —— Claude Code + Superpowers + TDD 实际流程与典型问题
- `docs/prompt-log.md` —— 各阶段原始 Prompt 与纠偏记录
- `docs/delivery-checklist.md` —— 交付打包清单与排除项
