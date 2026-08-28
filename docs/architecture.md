# 系统架构与契约（AI 圆桌讨论 Web App MVP）

> 本文档为架构与 API/SSE 契约的权威描述，随实现逐步补充（bounded contexts、ER 图、数据库说明、测试策略见 Phase 6）。

## 1. 顶层架构

后端 FastAPI（单 worker asyncio 自动编排）+ SSE 推送 + HTTP 命令；前端 React+TS+Vite 薄客户端；SQLite 为唯一权威状态来源。

## 2. API 契约（HTTP 命令）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/sessions/{id}/panel/generate` | 生成阵容 |
| POST | `/sessions/{id}/panel/confirm` | 确认阵容 |
| POST | `/sessions/{id}/discussion/start` | 开始讨论 |
| POST | `/sessions/{id}/discussion/pause` | 中断 |
| POST | `/sessions/{id}/discussion/resume` | 继续 |
| POST | `/sessions/{id}/discussion/end` | 结束 |
| POST | `/sessions/{id}/retry` | 安全重试 |
| GET | `/sessions/{id}/events` | SSE 事件流 |

## 3. SSE 事件契约

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
| `heartbeat` | `{}` |

事件信封：`{event, sequence, schema_version, session_id, timestamp, data}`。
