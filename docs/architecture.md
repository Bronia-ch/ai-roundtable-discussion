# 系统架构与契约（AI 圆桌讨论 Web App MVP）

> 本文档为架构与 API/SSE 契约的权威描述：顶层架构、bounded contexts、ER、数据库与迁移、契约与测试策略（Phase 6 完善版）。

## 1. 顶层架构

```
┌──────────────┐   HTTP(JSON) / SSE    ┌──────────────────────────────────┐
│  前端 (5173)  │ ────────────────────▶ │  后端 uvicorn 单 worker (8000)     │
│ React+TS+Vite│  vite proxy /sessions │  FastAPI                          │
│ 薄客户端      │ ◀──────────────────── │   ├─ routes（命令/快照/SSE）      │
│ 快照→SSE 增量 │                       │   ├─ DiscussionEngine（asyncio）   │
│ applyEvent    │                       │   ├─ EngineRegistry（任务登记）    │
│ 三重幂等去重   │                       │   ├─ EventStore（订阅桶+seq）      │
└──────────────┘                       │   └─ OpenAICompatProvider(Fake)   │
                                       └──────────────┬───────────────────┘
                                                      │ aiosqlite（WAL+FK）
                                               ┌──────▼──────┐
                                               │  SQLite 唯一 │
                                               │  权威状态源  │
                                               └─────────────┘
```

- **单 worker 约束**：`EventStore` 订阅桶与 `EngineRegistry` 任务登记是进程内共享状态；SSE 断线续订与引擎停机收尾依赖同一进程。多 worker 会分片事件流与后台任务，本项目不支持。
- **状态流转**：HTTP 命令在单个原子事务内完成「receipt 幂等 → 状态迁移（CAS）→ seq 递增 → 事件落库」；提交成功后才广播（事件/状态同生共死）。
- **LLM 调用**：永远发生在 DB 事务之外；引擎为 asyncio 持续运行任务，每轮 intent→utterance→insight，每轮开始 `_pause.wait()` 检查点，`/end` 后按 `_stop` 检查点优雅退出（LLM 在途取消仅当 stop 已发时返回 None）。

## 2. Bounded Contexts

### 2.1 业务上下文（backend/app/core + api）

| Context | 职责 | 关键模块 |
|---------|------|----------|
| 会话生命周期 | 9 态状态机（draft→panel_ready→live→paused→finalizing→completed/failed 等）、命令事务、CAS 并发保护 | `state_machine.py`、`transactions.py`、`commands.py` |
| 发言编排 | 非固定轮流：确定性调度（意愿/相关性/公平/多样性）、防连续、防饥饿；host 开场、turn/epoch | `engine.py`、`scheduler.py`、`turns.py` |
| 发言与转录 | utterance 原子写入（utterance+seq+事件）、speech_count 公平累计 | `transcript.py` |
| 洞察 | insight 增量创建、evidence 去重聚合、洞察 worker 后台处理 | `insights.py`、`insight_worker.py` |
| 上限与降级 | 软上限（utterance_cap，暂停后 resume +10，封顶 100）、绝对上限（100）、降级阶梯（rule_scheduler / utterance / insight）记账 | `engine.py`、`limits.py`、`transactions.recover_soft_cap` |
| 报告 | finalizing 收尾生成结构化总结；失败滞留 + retry 命令驱动重试；降级上下文带入报告 | `engine.finalize_report` |

### 2.2 基础设施上下文

| Context | 职责 | 关键模块 |
|---------|------|----------|
| 事件日志与快照 | 事件表持久化、精确 seq、提交后广播、快照重构、断线续订（after_seq / Last-Event-ID） | `event_store.py`、`api/sse.py`、`api/snapshot.py` |
| 命令幂等 | command_receipts 主键去重，重复 command_id 返回 202 不重复副作用 | `transactions.py` |
| LLM 适配与可靠性 | OpenAI 兼容 Provider；六类调用；错误分级（RECOVERABLE 指数退避+jitter / AUTH / SCHEMA / FATAL） | `llm/openai_compat.py`、`llm/reliability.py`、`core/errors.py` |
| 数据库与迁移 | schema.sql（DDL）+ `_migrate` 幂等补列（PRAGMA table_info → ALTER TABLE ADD COLUMN） | `db.py` |
| 配置 | pydantic-settings 读取 `LLM_*` 环境变量 / `.env` | `config.py` |
| 测试替身 | ScriptedLLMProvider / FakeLLMProvider / GateProvider / FailingProvider；EventStore 订阅断言 | `llm/fake.py`、tests |

## 3. 数据模型（Mermaid ER）

```mermaid
erDiagram
    sessions ||--o{ participants : "阵容/席位"
    sessions ||--o{ turns : "轮次"
    sessions ||--o{ utterances : "发言"
    sessions ||--o{ insights : "洞察"
    sessions ||--o{ insight_evidence : "证据"
    sessions ||--o{ events : "事件日志"
    sessions ||--o{ command_receipts : "命令幂等"
    sessions ||--o| discussion_reports : "报告"
    turns ||--o{ utterances : "所属轮"
    participants ||--o{ utterances : "发言者"
    participants ||--o{ insight_evidence : "表态者"
    insights ||--o{ insight_evidence : "证据关联"
    utterances ||--o{ insight_evidence : "来源发言"

    sessions {
        TEXT id PK
        TEXT topic
        INTEGER expert_count
        TEXT status "9 态状态机"
        TEXT last_stable_state "可恢复三元组"
        TEXT error_code
        TEXT retry_operation
        INTEGER last_event_sequence "全局 seq"
        INTEGER utterance_cap "软上限，默认 40"
        TEXT degraded_components
        INTEGER used_rule_scheduler_count
        INTEGER failed_turn_count
        INTEGER permanently_failed_insight_count
    }
    participants {
        TEXT id "UNIQUE(session_id, id)"
        TEXT role "host | expert"
        TEXT stance
        INTEGER sort_order "UNIQUE(session_id, sort_order)"
        TEXT runtime_state
        INTEGER speech_count "公平累计"
    }
    turns {
        TEXT id
        INTEGER sequence "UNIQUE(session_id, sequence)"
        TEXT status "planning|preparing|generating|completed|cancelled|failed"
        INTEGER generation_epoch "迟到响应拒绝"
        TEXT selected_participant_id
    }
    utterances {
        TEXT id
        INTEGER ordinal "UNIQUE(session_id, ordinal)"
        TEXT turn_id FK
        TEXT speaker_id FK
        TEXT role "host | expert"
        TEXT text "1~2 句，≤2000 字"
        TEXT insight_status "pending|processing|succeeded|retry_wait|permanently_failed"
    }
    insights {
        TEXT id
        TEXT kind "focus|consensus|divergence|open_question"
        INTEGER support_count
        INTEGER oppose_count
        INTEGER version "整体替换乐观锁"
    }
    insight_evidence {
        TEXT relation "supports|opposes|mentions|resolves"
        "UNIQUE(insight_id, utterance_id, relation)"
    }
    events {
        INTEGER sequence "UNIQUE(session_id, sequence)"
        TEXT event_type
        TEXT payload JSON
    }
    command_receipts {
        TEXT command_id "PK(session_id, command_id)"
        TEXT command_type
    }
    discussion_reports {
        TEXT summary
        INTEGER report_generated_with_degraded_context
        "降级计数快照"
    }
```

## 4. SQLite 表与迁移说明

- **9 张表**：`sessions`、`participants`、`turns`、`utterances`、`insights`、`insight_evidence`、`events`、`command_receipts`、`discussion_reports`（DDL 见 `backend/app/schema.sql`）。
- **关键约束**：
  - 会话作用域复合外键（`FOREIGN KEY(session_id, speaker_id) REFERENCES participants(session_id, id)`）杜绝跨会话引用；
  - `turns UNIQUE(session_id, sequence)`、`utterances UNIQUE(session_id, ordinal)`——恢复模式重试/复用必须绕开占位冲突（见 development-workflow 问题 #1）；
  - `events UNIQUE(session_id, sequence)`——seq 与状态/事件同事务递增，SSE 断线续订的单调性保证。
- **迁移**：新库由 `schema.sql` 全量建表；既有库由 `db.py:_migrate` 用 `PRAGMA table_info(sessions)` 读现存列，缺列则 `ALTER TABLE ADD COLUMN`（幂等，重复 init 零改动）。已落地一次迁移：CG-D 为 `sessions` 补 5 列（`utterance_cap`、`degraded_components`、三个降级计数列）。
- **PRAGMA**：`journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`。
- **初始化/种子**：`seed.py` 提供 5 组示例讨论（主题+主持人+4 立场互斥专家）；`is_sample` 标记。

## 5. HTTP/API 与 SSE 契约

### 5.1 HTTP 命令

所有命令 `POST`，请求体 `{"command_id": "..."}`；幂等命中（重复 command_id）返回 202 且不重复副作用；非法状态迁移返回 409；不存在返回 404。

| 方法 | 路径 | 状态迁移 / 语义 |
|------|------|------------------|
| POST | `/sessions` | 创建 → draft（201） |
| POST | `/sessions/{id}/panel/generate` | draft/panel_ready → panel_generating；执行体 LLM 生成阵容原子回写 |
| POST | `/sessions/{id}/panel/confirm` | → panel_ready（阵容锁定） |
| POST | `/sessions/{id}/discussion/start` | ready → live；启动持续运行引擎 |
| POST | `/sessions/{id}/discussion/pause` | live → paused；引擎暂停信号（不终止任务） |
| POST | `/sessions/{id}/discussion/resume` | paused → live；软上限 +10 清码 / 失败暂停重建引擎（恢复模式）|
| POST | `/sessions/{id}/discussion/end` | live/paused → finalizing；停止引擎 → 后台报告任务 |
| POST | `/sessions/{id}/retry` | 按 retry_operation 解析；'report' → 重启 finalize 任务 |
| GET | `/sessions/{id}` | 快照：`{session_id, status, last_sequence, topic, expert_count, transcript[], insights[]}` |
| GET | `/sessions/{id}/events` | SSE 事件流 |
| GET | `/healthz` | `{"ok": true}` |

**可恢复错误三元组**（sessions 列）：`last_stable_state` / `error_code` / `retry_operation`。`/resume` 对 `utterance_cap_reached` 执行 `cap = MIN(cap+10, 100)` 并清码；`absolute_cap_reached` 由命令门禁直接 409（仅 end 可离开）；其他错误码仅清码。

### 5.2 SSE 事件契约

| event | data 关键字段 |
|-------|--------------|
| `session.state_changed` | `state`, `prev_state`, `error_code?` |
| `panel.generated` | `host`, `experts[]` |
| `panel.generation_failed` | `error_code`, `message`, `retry_operation` |
| `participant.state_changed` | `participant_id`, `role`, `state`, `turn_id` |
| `utterance.completed` | `utterance_id`, `turn_id`, `speaker_id`, `role`, `text` |
| `intent.public` | `participant_id?`, `intent_type`, `public_focus`, `target_participant_id?`, `target_claim_id?` |
| `insight.updated` | `snapshot`, `version` |
| `error.recoverable` | `error_code`, `retry_operation`, `scope` |
| `discussion.finalizing` | `status`, `step` |
| `discussion.completed` | `summary`, `result_ref` |
| `session.degraded` | `component`, `count`（CG-D 降级记账） |
| `heartbeat` | `{}` |

- 事件信封：`{event, sequence, schema_version, session_id, timestamp, data}`。
- 订阅：`EventSource` 每 session 一桶，事件只发给当前 session 的订阅者；提交成功后才广播。
- 断线恢复：`after_seq` 与浏览器 `Last-Event-ID` 并存时取较大已确认序号；只重放大于该序号的事件；前端快照 `last_sequence` → `after_seq` 首次续订。
- 前端幂等：按 session / sequence / 实体 ID 三重去重（utterance_id 去重时仍推进 lastSequence）。

## 6. 测试策略

### 6.1 离线矩阵（默认、全量）

| 层 | 工具 | 说明 |
|----|------|------|
| 后端单元/集成 | pytest（asyncio_mode=auto） | 218 项：状态机、调度、事务、SSE、快照、引擎失败矩阵、上限、降级、隔离、迁移、路由 |
| LLM 替身 | `ScriptedLLMProvider` / `FakeLLMProvider`（llm/fake.py） | 按 call_type 返回脚本响应，**不访问网络、不读取密钥**；测试以 `_mount` 覆盖 app.state.llm |
| 故障注入 | `FailingProvider`（fail_once）、`GateProvider`（entered/gate 对） | 确定性复刻 LLM 失败与在途取消窗口 |
| 前端 | Vitest（jsdom） | 组件、SSE applyEvent 三重幂等、smoke |
| E2E | Playwright（Edge/Chromium） | `playwright.config.ts` webServer 自动编排：后端内存 SQLite（`LLM_SQLITE_PATH=:memory:`）+ vite dev；后端 `LLM_BASE_URL=http://127.0.0.1:9/v1`、`LLM_API_KEY=""`——**网络隔离，即使误触 LLM 路径也只能本机失败** |

### 6.2 真实 smoke（默认 SKIPPED，显式门禁）

- `backend/tests/test_smoke_real.py`：`skipif(SMOKE_REAL_LLM not in (1, true, yes))`——未设置、`0`、`false` 一律 SKIPPED，杜绝 `=0` 误触发真实请求。
- 获批后流程：建会话 → `OpenAICompatProvider(Settings())` → 引擎 start（live、开场+1 轮）→ end（completed、1 份报告）。
- **本项目截至交付从未执行真实 DeepSeek 调用**：无有效密钥、模型 ID 未验证；smoke 在离线矩阵中恒为 SKIPPED。
