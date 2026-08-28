# AI 圆桌讨论 Web App MVP — 产品规格与架构设计（SDD）

> **状态**：设计已确认（第 1A 阶段，需求澄清 + SDD 设计）
> **日期**：2026-08-28
> **方法**：SDD（Specification-Driven Development）+ Superpowers brainstorming 工作流

## 术语说明（避免概念混用）

- 本文档中的 **DDD 指 Design-Driven Development**（先确定视觉结构、组件状态与交互，再实现页面）。
- 文中出现的 **bounded context** 借用自 Domain-Driven Design 的概念，**仅用于描述架构模块边界**，不构成另一套 DDD 方法论；二者不混为一谈。
- **SDD** 指 Specification-Driven Development：先定义产品规格、数据模型、数据库 Schema、API 契约与 SSE 事件契约，再实现。

---

## 0. 文档目的与范围

本规格是"AI 圆桌讨论 Web App MVP"的单一事实来源，覆盖：产品目标、核心架构决策、用户流程、状态机、发言调度、SSE 契约、数据流与 Schema、多会话隔离、LLM 边界、异常恢复与终止条件、MVP 范围、验收标准与阶段门禁。

后续阶段（工程实现）将严格依据本规格，通过 writing-plans 生成实施计划。

---

## 1. 产品目标、核心价值与验收边界

### 1.1 产品目标
构建一个**本地运行、前后端分离**的中文 AI 圆桌讨论 Web App。用户输入讨论主题 + 专家人数（默认 4）→ 系统调用大模型生成主持人与专家阵容 → 用户确认后进入演播厅 → 主持人开场/追问/串场/收尾，专家动态回答/补充/反驳/澄清 → 全程实时生成 Transcript 并持续提取共识与分歧 → 用户结束后产出结构化结论 + JSON。

### 1.2 核心价值
把"问 LLM 一个观点"升级为"一群有立场、有人格、会互相交锋的专家围绕一个主题产生多视角碰撞"，最终沉淀为**结构化的共识/分歧视图**，而非单一答案。

### 1.3 验收边界（MVP 硬边界）
- 本地、中文 UI、桌面响应式（不含移动端）、演播厅各区域独立滚动、无全页滚动、普通/超宽屏不重叠。
- SSE 实时 + SQLite 持久化 + API Key 仅后端环境变量读取。
- 多讨论并行且状态/Transcript/SSE/洞察完全隔离。
- 技术栈锁死：Python 3.13 + FastAPI / React + TS + Vite / Pytest + Vitest + Playwright(Edge)。

---

## 2. 核心架构决策

| # | 决策 | 结论 |
|---|------|------|
| 1 | 发言调度 | 算法为主（LLM 仅产出结构化意图） |
| 2 | 意图产出 | 每发言决策周期一次批量调用 |
| 3 | 共识/分歧更新 | 逐条增量归类（结束全量重算兜底） |
| 4 | 发言推送粒度 | 整句事件 |
| 5 | 并发模型 | 单用户多讨论（进程内按 session_id 隔离） |

---

## 3. 架构方案（方案 A）

**后端 asyncio 自动编排 + SSE 推送 + HTTP 控制命令**（在方案 A/B/C 中选定）。

- 每场讨论一个 `DiscussionEngine`（asyncio 任务），仅持有该场当前的任务句柄、取消令牌与可丢弃缓存；**SQLite 是唯一权威状态来源**（状态、Transcript、洞察均以数据库为准）；SSE 订阅注册表为进程共享、按 session_id 分桶。
- 用户"开始"后 engine 自动连续推进：主持人开场 → 调度器选人 → 调 LLM 生成整句发言 → 推 SSE 事件 → 逐条增量更新洞察 → 主持人追问/串场 → …，直到"结束"或触发终止条件。
- 前端只做两件事：订阅 SSE 渲染 + 通过 HTTP POST 发控制命令。
- 状态实时持久化 SQLite，刷新/断线重连按事件序列补发。

**选定理由**：唯一同时满足"SSE 为主要通道、后端自动控场、状态可持久化恢复、单用户多讨论进程内隔离"的形态；状态机集中后端单一位置，契合 TDD；前端保持薄，利于 72h 内交付。

**备选方案（未采用）**：方案 B（前端驱动逐请求，后端轻）——前端状态机重、双状态机不一致、断线恢复难；方案 C（事件总线/任务队列）——对本地单用户明显过度设计。

---

## 4. 用户完整流程（设计第 1 节）

共 3 个页面/视图 + 结果态，全程中文、桌面响应式。

### 4.1 首页（讨论列表）
- 展示进行中与历史讨论卡片（主题、人数、状态徽章、创建时间）+ 新建讨论入口。
- 卡片按会话状态路由（见 §5.1 状态 → 路由表）。

### 4.2 阵容确认页
- 输入主题 + 专家人数（默认 4，范围 2–6）→ 生成。
- 后端调 LLM 生成 1 主持人 + N 专家（姓名、职业、Title、立场、头像标识）。
- 展示阵容卡片，提供**整组重新生成**（re-roll）；**单专家编辑/单独重生成列为后续改进（非 MVP）**。
- 用户点"确认阵容并进入演播厅"才进入下一页（硬门禁）。

### 4.3 演播厅
- 主持人与专家席位（每位专家独立状态：等待/准备/发言）。
- 中央 Transcript 实时追加实际发言；侧栏共识/分歧/焦点 + 当前关注点。
- 用户点"开始讨论"→ 主持人开场，进入自动连播。**进入演播厅不自动开始模型调用**。
- 可点"结束讨论"或"中断"（二者语义分离，见 §10）。

### 4.4 结果态
- 主持人收尾 → 全量重算生成结构化结论 + JSON → 保存 → 展示。
- 结果页含**中文可读**摘要、关键共识、主要分歧、未解决问题、建议行动，另附原始 JSON。

### 4.5 关键约束
- 阵容未确认 → 无法进入演播厅。
- 刷新后从后端重新获取权威状态、Transcript、当前洞察、事件序号，不依赖前端内存。
- 讨论一旦结束进入只读结果态。

---

## 5. 会话与专家状态机（设计第 2 节）

### 5.1 会话（Discussion）状态机 —— 9 态

| 状态 | 含义 | 首页卡片路由 |
|------|------|------------|
| `draft` | 已建讨论（有主题+人数），未生成阵容 | 阵容确认流程 |
| `panel_generating` | 正在调 LLM 生成阵容 | 阵容确认流程 |
| `panel_ready` | 阵容已生成，待用户确认 | 阵容确认流程 |
| `ready` | 已确认阵容、在演播厅、未开始 | 演播厅 |
| `live` | 讨论自动连播中 | 演播厅 |
| `paused` | 用户中断/触发暂停，已保存现场 | 演播厅 |
| `finalizing` | 正在收尾 + 全量重算 + 写报告 | 结果页（进度 + 重试态） |
| `completed` | 报告已成功保存（只读） | 结果页（只读） |
| `failed` | 会话级不可恢复错误 | 不可恢复错误页 |

> `finalizing` 页面不得展示尚未持久化的伪完成报告。

**迁移表**（触发者 + 持久化动作）：

| 从 → 到 | 触发 |
|---------|------|
| `draft` → `panel_generating` | 用户点"生成阵容" |
| `panel_generating` → `panel_ready` | 阵容生成成功 |
| `panel_generating` → `draft` | **首次**生成失败且无旧阵容（可重新生成） |
| `panel_ready` → `panel_generating` → `panel_ready` | re-roll；期间保留旧阵容 |
| `panel_generating` → `panel_ready` | **re-roll 失败**且有旧阵容（保留旧阵容 + 错误） |
| `panel_ready` → `ready` | 用户点"确认阵容并进入演播厅" |
| `ready` → `live` | 用户点"开始讨论" |
| `live` → `paused` | 用户中断 / 软上限 / LLM 重试耗尽 |
| `paused` → `live` | 用户点"继续" |
| `live` / `paused` → `finalizing` | 用户点"结束" |
| `finalizing` → `completed` | 收尾 + 全量重算 + 报告持久化全部成功 |
| `finalizing` → `finalizing` | 收尾失败，滞留并记录可恢复错误（提供"重试生成报告"） |
| `*` → `failed` | 会话级不可恢复错误（仅持久化损坏/数据一致性错误） |

**可恢复错误三元组**：持久化 `last_stable_state` / `error_code` / `retry_operation`，安全重试只执行失败操作，不重复写已成功发言/事件。

### 5.2 角色（Actor）状态机

**专家（Expert）**：`waiting`（等待）→ `preparing`（准备，生成整句发言中）→ `speaking`（发言事件已推送、当前发言人）→ `waiting`；失败/中断时 `preparing → waiting` 回退。

**主持人（Host）**：`idle` / `preparing` / `speaking`（与专家一致三态，保证生成期间有反馈）。

### 5.3 一轮（发言决策周期）生命周期

```
1. [可选] 主持人回合（开场/追问/串场/收尾）—— 时机由控场策略定
2. 批量意图调用：LLM 一次返回全体专家 {意图类型, 一句话, 意愿强度, target_*, public_focus}
3. 调度器（算法）结合立场/历史/意愿/公平性 → 选出下一位专家
4. 该专家 waiting → preparing
5. LLM 生成整句发言
6. 推 SSE「发言事件」→ preparing → speaking → waiting
7. 逐条增量洞察：LLM 归类该发言 → 推 SSE「洞察更新事件」
8. 回到 1（除非收到 结束/中断 命令）
```

**代际隔离**：持久化 `turn_id` / `generation_epoch`；中断后迟到模型响应因 epoch 不匹配被丢弃，不写 Transcript；恢复时创建新 turn，不复用已取消任务。

**原子提交**：状态迁移 + 事件记录在同一 SQLite 事务写入，提交成功后 SSE 按递增 sequence 推送。

---

## 6. 非固定轮流的发言调度策略（设计第 3 节）

### 6.1 定位
调度器是**纯函数、确定性、无副作用**组件，可完全 TDD。不调用 LLM，只消费 LLM 产出的结构化意图。

### 6.2 输入信号（每位专家 i）
- 意愿强度 `w_i ∈ [0,1]`
- 意图类型 `intent_i ∈ {回答, 补充, 反驳, 澄清}`
- `target_participant_id`、`target_claim_id`、`public_focus`（用于相关性计算与公开意图展示）
- 立场 `stance_i`（静态）
- 发言次数 `count_i`、距上次发言轮数 `gap_i`、是否上一位 `is_last_i`

### 6.3 打分与选人

```
score_i = α·w_i + β·relevance_i + γ·fairness_i + δ·stance_diversity_i
```
默认权重 `α=0.4, β=0.3, γ=0.2, δ=0.1`（常量可调）。

- `relevance_i`：意图与"当前焦点/分歧"匹配度。
- `fairness_i`：`gap_i` 归一化，越大加分越高（防冷落）。
- `stance_diversity_i`：最近 K 轮立场单一时异质立场加分（防垄断）。

**硬约束（先于打分过滤）**：
- 默认禁止专家连续两次直接发言；**主持人明确点名追问例外**；仅 1 名有效候选例外。
- 主持人插话**不得清空**专家公平性历史。
- **防饥饿**：某专家等待轮数达阈值获最低优先级保障，但不退化固定轮询。

**选人**：`argmax(score_i)`；平分时 `gap_i` 更久者优先，再平按伪随机（种子 = `session_id + turn_sequence`，同会话同轮重试结果一致）。仅从 `waiting` 且未取消、未退出的专家中选人。

### 6.4 主持人介入策略（规则驱动，不额外 LLM 调用）
| 介入类型 | 触发条件 |
|---------|---------|
| 开场 | `live` 开始第 1 个事件（必做一次） |
| 追问 | 最近洞察更新产生"新分歧/未解决问题"且未获回应；**必须关联具体未解决命题或当前焦点** |
| 串场 | 连续 T 轮无新焦点，或当前焦点洞察连续 K 次增量无变化 |
| 收尾 | 收到"结束"命令（必做一次） |

**节流**：除开场/收尾外主持人不得连续发言；两次普通介入间至少 N 次专家发言；介入规则只读已持久化 Transcript 与洞察。

### 6.5 LLM 意图字段为不可信输入
- Pydantic 严格校验；`w_i` 钳制 `[0,1]`；`participant_id`/`target_id` 必须属于当前会话；枚举非法则整批/单项降级。
- **模型不得直接指定最终发言者**；不得通过伪造 ID 越过会话边界。

### 6.6 降级路径
批量意图调用失败 → 规则调度器接管：意图类型由"上一条发言 vs 专家立场"推断（冲突→反驳，同向→补充，其余→回答/澄清），意愿强度以 `fairness_i` 替代。

### 6.7 可测试性质（TDD 用例）
P1 不出现固定顺序机械轮流；P2 上一位不被立即重选（非点名）；P3 窗口 W 内每位专家至少发言一次；P4 立场冲突+高意愿时反驳型优先；P5 意图降级仍产出合法下一位；P6 同输入同种子同结果；P7 点名追问例外生效；P8 无长期饥饿；P9 非法/缺失意图 JSON 安全降级；P10 伪造 ID 不越会话边界；P11 不退化固定轮询。

---

## 7. SSE 事件契约、持久化事件日志与断线恢复（设计第 4 节）

### 7.1 通信拓扑
- 下行：单一 SSE 连接/场（`GET /sessions/{id}/events`）。
- 上行：HTTP POST 命令，返回 `202 Accepted`，结果经 SSE 异步回传。

```
POST /sessions/{id}/panel/generate      # 生成阵容
POST /sessions/{id}/panel/confirm       # 确认阵容
POST /sessions/{id}/discussion/start    # 开始讨论
POST /sessions/{id}/discussion/pause    # 中断
POST /sessions/{id}/discussion/resume   # 继续
POST /sessions/{id}/discussion/end      # 结束
POST /sessions/{id}/retry               # 安全重试（带 retry_operation）
```

### 7.2 事件信封

```json
{
  "event": "<type>",
  "sequence": 42,
  "schema_version": 1,
  "session_id": "sess_xxx",
  "timestamp": "2026-08-28T12:00:00Z",
  "data": { "..." }
}
```

- `sequence` 为**会话内**单调递增；SSE 以 `id: <sequence>` 回传，供 EventSource 维护 `Last-Event-ID`。
- 投递为 at-least-once，客户端按 `sequence` 幂等去重。

### 7.3 事件类型

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

- `insight.updated` 计算是增量（逐条归类），传输携带完整累积快照（幂等、重连安全）；delta 传输列为后续优化。
- 所有错误消息为**公开安全摘要**，不含 API Key / 原始异常栈 / 模型内部内容。

### 7.4 持久化事件日志

```sql
events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,   -- 全局内部 ID
  session_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,              -- 会话内递增
  event_type TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(session_id, sequence)
);
```
- `sessions.last_event_sequence` 在同一事务中原子递增并写入事件。
- **同一事务三写**：业务状态（会话/参与者/Transcript/Insight）+ 递增 `last_event_sequence` + 插入 `events`；提交成功后才 SSE 广播；无在线订阅者时事件仍落库供补发。

### 7.5 断线恢复（无丢事件）
1. REST 重取权威状态：`GET /sessions/{id}` 返回状态、完整 Transcript、当前洞察、`last_sequence`（快照生成时的序号）。
2. 渲染快照后连接 `events?after_seq=last_sequence`；快照→建连间隙事件从事件表补发。
3. 客户端按 `sequence` 去重，忽略 ≤ 已应用序号的事件。

- SSE 同时支持 `after_seq`（首次/兼容）与 `Last-Event-ID`（自动重连）；并存时取较大已确认序号。
- heartbeat 周期保活 + 重连提示；**客户端断线不停止后端讨论**；MVP 事件日志永久保留，清理策略后置。

### 7.6 命令幂等
- `command_receipts` 表：`UNIQUE(session_id, command_id)`，存 `command_type`/`accepted_at`/`status`/`result`/`error`；重复 POST 返回原状态、不重启任务。
- `command_id` 客户端 UUID；**不在内存去重**。

### 7.7 可测不变量
两会话 sequence 各自从 1；状态写成功必有事件；事件写失败整体回滚；快照→建连事件不丢；重复事件不重复追加 Transcript；重复 command_id 不执行两次；重连只收当前 session 事件。

---

## 8. Transcript / 实时共识与分歧的数据流 + SQLite Schema（设计第 5 节）

### 8.1 实体关系

```
sessions 1 ──── * participants
sessions 1 ──── * turns
sessions 1 ──── * utterances (turn_id FK → turns)
sessions 1 ──── * insights
sessions 1 ──── * insight_evidence
sessions 1 ──── * events
sessions 1 ──── * command_receipts
sessions 1 ──── 0..1 discussion_reports
```

### 8.2 Schema 概览（非最终 DDL）

| 表 | 关键列 | 约束/说明 |
|----|--------|----------|
| `sessions` | `id`(PK), `topic`, `expert_count`, `status`, `last_stable_state`, `error_code`, `retry_operation`, `last_event_sequence`, `is_sample`, `created_at`, `updated_at` | `status` 为 9 态 |
| `participants` | `id`, `session_id`(FK), `role`(host/expert), `name`, `profession`, `title`, `stance`, `avatar_color`, `avatar_emoji`, `sort_order`, `runtime_state`, `public_focus`, `speech_count`, `last_spoke_turn`, `updated_at` | `UNIQUE(session_id, id)`, `UNIQUE(session_id, sort_order)` |
| `turns` | `id`, `session_id`(FK), `sequence`, `generation_epoch`, `status`(planning/preparing/generating/completed/cancelled/failed), `selected_participant_id`, `intent_snapshot`(JSON), `started_at`, `completed_at`, `cancelled_at` | `UNIQUE(session_id, sequence)` |
| `utterances` | `id`(PK), `session_id`(FK), `turn_id`(FK→turns), `speaker_id`, `role`, `text`, `ordinal`, `insight_status`, `insight_retry_count`, `insight_last_error`, `insight_next_retry_at`, `created_at` | `UNIQUE(session_id, ordinal)`; 复合 FK `(session_id, speaker_id)` |
| `insights` | `id`(PK), `session_id`(FK), `kind`(focus/consensus/divergence/open_question), `text`, `support_count`, `oppose_count`, `status`(active/resolved), `version`, `created_at`, `updated_at` | support/oppose 为缓存，真值来自 evidence |
| `insight_evidence` | `insight_id`, `utterance_id`, `participant_id`, `relation`(supports/opposes/mentions/resolves), `created_at` | `UNIQUE(insight_id, utterance_id, relation)`; 复合 FK 校验同 session |
| `events` | `id`(全局自增), `session_id`, `sequence`, `event_type`, `schema_version`, `payload`, `created_at` | `UNIQUE(session_id, sequence)` |
| `command_receipts` | `session_id`, `command_id`, `command_type`, `accepted_at`, `status`, `result`, `error` | 复合 PK / `UNIQUE(session_id, command_id)` |
| `discussion_reports` | `id`(PK), `session_id`(FK), `summary`, `key_consensus`(JSON), `main_divergence`(JSON), `unresolved_questions`(JSON), `suggested_actions`(JSON), `raw_json`, `degraded_components`, `permanently_failed_insight_count`, `used_rule_scheduler_count`, `failed_turn_count`, `report_generated_with_degraded_context`, `created_at` | `UNIQUE(session_id)` |

**完整性**：开启 `PRAGMA foreign_keys`；`topic`/`text`/`name` 等核心字段 NOT NULL；跨会话关联用复合约束在 DB 层杜绝（不依赖应用校验）。

**bounded contexts**（仅架构边界描述）：

- **业务上下文**：Session & Panel、Discussion Orchestration、Transcript、Insight & Reporting。
- **基础设施**：Persistent Event Log、Command Idempotency、LLM Provider、SSE Transport。

### 8.3 Transcript 数据流

```
调度器选人 → 专家 preparing
  → LLM 生成整句
  → 校验(text 非空/长度/speaker 归属会话)
  → 同一事务：INSERT utterances + 递增 last_event_sequence + INSERT events(utterance.completed)
  → 提交 → SSE 广播 → 前端按 utterance_id 去重追加
```

### 8.4 实时共识 / 分歧数据流（逐条增量）

```
utterance 持久化后 → 触发增量洞察提取（LLM）
  → 返回 delta：{ 创建/更新命题 + 当前发言与命题的关系 }
  → 校验(insight_id 归属会话、关系枚举合法)
  → 同一事务：UPDATE/INSERT insights + INSERT insight_evidence + version++ + 递增 last_event_sequence + INSERT events(insight.updated)
  → 提交 → SSE 广播(snapshot + version)
```

- **LLM 不得直接返回 `support/oppose ±`**；计数由后端按 `insight_evidence` 中**去重 participant_id** 确定性聚合；缓存到 `insights`，真值来源为 evidence。
- **洞察 LLM 不得自定 utterance_id/participant_id**；当前发言者由后端注入，模型只提命题、匹配 insight_id 与关系类型。
- 洞察失败降级：`insight_status` 进入可重试状态（见 §10），讨论继续。

### 8.5 种子数据（需求 11）
- 5 组高质量种子（主题 + 主持人 + 专家阵容），经**幂等 DB 初始化/seed 脚本**写入（非仅常量）。
- 样本会话 `is_sample=1`、状态 `panel_ready`；首页明确标注"示例讨论/示例阵容"，不冒充已完成历史。

---

## 9. 多会话隔离、后台任务恢复与 LLM 调用边界（设计第 6 节）

### 9.1 多会话隔离（进程内，按 session_id）

| 组件 | 性质 |
|------|------|
| SQLite 连接 | 共享（序列化写） |
| LLMClient | 共享（无状态） |
| SSE 订阅注册表 | 共享但按 session_id 分桶 |
| DiscussionEngine / 状态机 / 调度器 | 每会话独占 |

- **MVP 单进程 / 单 Uvicorn worker**：EngineRegistry、SSE 订阅、SQLite 写协调均在进程内；README 启动命令固定单 worker；多进程扩展列为后续改进。
- **SQLite 并发写**：单 `aiosqlite` 写连接 + `asyncio.Lock` 串行短事务；读用独立连接；`WAL` + `busy_timeout` + `foreign_keys`；**LLM 网络调用绝不发生在 DB 事务内**。
- **原子 EngineRegistry**：同一 session_id 最多一个运行中 engine；start/resume/retry 走 session 级锁 get-or-create；结束/暂停后移出注册表。

### 9.2 后台任务恢复（幂等对账）
服务启动时执行一次幂等对账：
1. 遗留 `preparing/speaking` → `waiting`（主持人 `idle`）。
2. 在途 turn（`generating`）→ `cancelled` + `generation_epoch` 递增。
3. `live` → `paused`（**不自动续跑**，用户点"继续"再恢复）。
4. `insight_status ∈ {pending, processing}` → 重置 `pending` + `next_retry_at=now`。
5. `finalizing` → 保持，暴露"重试生成报告"。

**洞察 Worker（进程级）**：同会话按 `ordinal` 严格顺序；不同会话有限并发；全局并发信号量控 API 压力；状态 + 条件更新防重复领取。

### 9.3 LLM 调用边界

**Provider 抽象**：单一 `LLMClient` 封装 OpenAI 兼容接口，`base_url`/`api_key`/`model` 仅由后端环境变量读取，**API key 永不进浏览器**。

**调用清单**：

| # | 调用 | 频率 |
|---|------|------|
| 1 | 阵容生成 | 首次生成及用户 re-roll 时 |
| 2 | 批量意图评估 | 1/发言决策周期 |
| 3 | 专家发言生成 | 1/发言 |
| 4 | 主持人回合 | 1/介入 |
| 5 | 洞察增量归类 | 1/发言 |
| 6 | 最终报告生成 | 1/场（finalizing） |

**统一可靠性策略**：每类调用明确 timeout；仅对超时/限流/可恢复服务错误做有限指数退避 + jitter；鉴权失败/余额不足/持续 schema 非法不无限重试；全局 + 每会话并发上限；重试复用 operation/turn 幂等标识；用户中断取消请求、迟到响应由 epoch 拒绝。

**边界规则**：LLM 输出一律不可信输入经 schema 校验；上下文由后端注入（Transcript 相关片段、立场、焦点、当前 utterance_id/speaker_id）；模型不触碰调度/隔离/计数/数据库；系统提示固定角色与输出 schema、用户主题作为数据注入；意图仅白名单枚举 + 公开短摘要，不回传 CoT。

**可观测性（两类 Prompt 记录严格分离）**：
- `docs/prompt-log.md`：记录 Claude Code + Superpowers 开发本项目时的核心原始 Prompt（作业交付物）。
- 运行时 LLM 日志：默认仅 `call_type`/`model`/`prompt_template_version`/`session_id`/`turn_id`/`status`/`token usage`/`latency`/`retry_count`/`error_code`/`trace_id`；**默认不持久化**主题全文、完整 Transcript、原始 Prompt、模型响应、API Key、隐藏推理；调试模式需显式开启且脱敏。

---

## 10. 异常恢复、讨论终止条件与安全降级（设计第 7 节）

### 10.1 失败分类与处理矩阵

| 失败源 | 即时处理 | 重试策略 | 终态/降级 |
|--------|---------|---------|----------|
| LLM 超时 / 429 / 5xx | 停止该调用 | 指数退避 + jitter（基数 1s、×2、≤3 次） | 耗尽→按调用类型降级 |
| 鉴权失败 / 余额不足 | 不重试 | 无 | 首次阵容(无旧)→`draft`+错误；re-roll(有旧)→`panel_ready`保留旧阵容；讨论→`paused`+提示 |
| Schema 非法 | 首次失败后最多 1 次结构化修复/重生成 | 与网络重试**不混算** | 二次仍非法→按调用类型降级 |
| 发言生成失败 | turn 标记 failed | 退避重试 | 耗尽→`paused`+可恢复错误 |
| 洞察失败 | `insight_status` 进重试态 | 后台重试 | 讨论继续，报告全量兜底 |
| 意图失败 | 规则调度器接管 | 无 | 降级调度，讨论继续 |
| 阵容失败 | 首次→`draft`；re-roll→保留旧阵容 | 退避重试 | 见状态机 |
| 主持人回合失败 | 同发言失败 | 退避重试 | 耗尽→`paused` |
| 最终报告失败 | 滞留 `finalizing` | 幂等重试（同 operation_id） | 绝不误标 `completed` |
| DB busy/locked | 事务回滚 | 有限重试 | — |
| DB 磁盘满/不可写/完整性异常 | 立即停当前操作 | 无 | 不广播未提交事件 |
| 数据一致性/持久化损坏 | 停该会话 | 无 | 会话 `failed`（仅此进 failed） |
| SSE 断线 | 后端继续 | 客户端重连补发 | 无丢失 |
| 服务重启 | 幂等对账 | — | `live→paused` |
| 用户中断 | 取消请求 | — | `paused`，迟到响应 epoch 拒绝 |

### 10.2 洞察重试生命周期
`pending → processing → succeeded`；可恢复失败进 `retry_wait`（`retry_count`/`next_retry_at`）；达上限进 `permanently_failed`；Worker 领取到期 pending/retry_wait；`permanently_failed` 不再耗额度，由 finalizing 全量报告兜底并记降级。

### 10.3 讨论终止条件
- **手动结束**（唯一"完成"路径）：`live/paused → finalizing → completed`。
- **发言数软上限**（后端强制）：默认 40 条自动 `paused`；用户点"继续"每次 +10；绝对上限 100 条只能结束；UI 显示当前数与剩余额度。
- **明确不做**：共识收敛自动结束、话题枯竭判定（避免不可测行为与额外成本）。

### 10.4 安全降级阶梯
1. 意图失败 → 规则调度器，UI 标注"降级调度中"。
2. 洞察失败 → 后台重试，最终报告全量兜底。
3. 单发言失败 → 重试 → 暂停（可继续）。
4. 阵容失败 → 保留旧阵容/回 draft，可重生成。
5. 主持人介入失败 → 重试 → 暂停。
6. 最终报告失败 → `finalizing` 滞留 + 幂等重试，绝不误标 completed。

**结构化降级字段**：`degraded_components`、`permanently_failed_insight_count`、`used_rule_scheduler_count`、`failed_turn_count`、`report_generated_with_degraded_context`；结果页仅展示简洁提示，不显示异常栈。

### 10.5 异常恢复可测不变量
各失败按矩阵进入正确终态，不越级进 `failed`（仅持久化损坏可进）；中断后迟到响应不写 Transcript、恢复新建 turn；finalizing 存在失败洞察仍能用完整 Transcript 生成带降级标记报告；对账幂等；软/绝对上限不可绕过；finalizing 重复重试仅一份报告；进 `failed` 必带不可恢复 `error_code`。

---

## 11. MVP 范围、明确不做、验收标准（设计第 8 节）

### 11.1 MVP 范围（In-scope）
- 首页讨论列表（按 9 态路由）+ 新建讨论。
- 阵容生成（首次 + 整组 re-roll）与确认门禁。
- 演播厅：主持人+专家状态、实时 Transcript、共识/分歧/焦点、当前关注点。
- 自动连播 + 算法调度 + 主持人控场。
- 结束 → finalizing → completed + 结构化结论 + JSON。
- SSE 实时 + HTTP 命令 + 断线恢复 + 事件日志。
- SQLite 持久化 + 5 组种子数据（`is_sample`）。
- 单用户多讨论隔离。
- Pytest + Vitest + Playwright(Edge)。
- `docs/prompt-log.md` + AI 开发工作流说明。
- **UI UX Pro Max 门禁**（见 §12）：正式前端实现前安装并验证项目级技能，生成并持久化演播厅设计系统。

### 11.2 明确不做（Out of scope）
移动端 UI；多用户/认证/鉴权；多进程/多 worker/水平扩展；WebSocket（已选 SSE）；token 级打字机流式发言；单专家编辑/单独重新生成；共识收敛自动结束 / 话题枯竭判定；事件日志清理策略；多 LLM provider 切换；头像真实图片生成；语音/视频；讨论对外分享（JSON 展示在结果页，不导出文件）。

### 11.3 验收标准

**A. 用户流程**
- A1 首页卡片按 **9 态**正确路由（draft/panel_generating/panel_ready→阵容；ready/live/paused→演播厅；finalizing→结果页进度+重试；completed→只读结果页；failed→不可恢复错误页）；finalizing 页不展示未持久化的伪完成报告。
- A2 未确认阵容无法进入演播厅；A3 进入演播厅不自动开始，须点"开始讨论"；A4 结束与中断语义分离、结束后只读；A5 结果页含中文摘要/关键共识/主要分歧/未解决/建议 + 原始 JSON。

**B. 调度与状态机**
- B1 非固定顺序（不回退轮询）、上一位不连续（点名例外）、无饥饿、同输入同种子同结果。
- B2 专家 waiting/preparing/speaking、主持人 idle/preparing/speaking 正确显示。
- B3 意图仅公开短摘要、不含 CoT、模型不能指定最终发言者、不能越会话边界。

**C. 实时 / SSE / 断线**
- C1 Transcript 只追加完整校验并持久化的发言；C2 每新发言后洞察实时增量更新；C3 断线补发无丢失、重复事件不重复追加、重连只收本会话事件；C4 重启后 live→paused、不自动调 LLM。

**D. 隔离 / 并发**
- D1 多场并行互不影响；D2 并发 start/resume 只创建单 engine、重复 command_id 不执行两次。

**E. 异常 / 降级**
- E1 各失败按矩阵进入正确终态、仅会话级不可恢复错误进 failed 且必带 error_code；E2 意图失败降级规则调度、洞察失败不阻塞发言、finalizing 失败可重试且仅一份报告；E3 40 条软上限 paused、继续 +10、100 条绝对上限只能结束（后端强制）。

**F. UI / 非功能**
- F1 中文、桌面响应式、无全页滚动、各区域独立滚动、普通/超宽屏不重叠。
- F2 API Key 仅后端环境变量，浏览器网络面板不可见。
- F3 键盘焦点清晰；状态不只能靠颜色表达；动画尊重 `prefers-reduced-motion`；中文在普通桌面与超宽屏不截断/不重叠；演播厅顶部/Transcript/洞察区滚动边界可直接经 Playwright 验证。

**G. 测试 / 工程**
- G1 Pytest 覆盖状态机/调度/隔离/洞察更新；Vitest 覆盖前端组件；Playwright 覆盖完整用户流程、并发会话、异常恢复。
- G2 单元测试与 E2E 默认使用 **FakeLLMProvider/ScriptedLLMProvider**（固定脚本响应），不调用真实付费模型；保留需显式环境变量开启的真实模型 smoke test。
- G3 每阶段独立 Git Commit；`docs/prompt-log.md` 与工作流说明持续维护。

---

## 12. 阶段门禁（后续阶段）

1. **UI UX Pro Max 门禁**：正式前端实现前，必须安装并验证项目级 `ui-ux-pro-max` 技能；使用该技能生成并持久化演播厅设计系统（至少定义色彩、字体、间距、布局网格、组件状态、响应式断点、滚动区域、可访问性与明确反模式）；其调用过程、输出及对最终界面的影响写入开发工作流文档。**当前阶段仅写入规格，不安装。**
2. **测试策略门禁**：实现前先落地 FakeLLMProvider/ScriptedLLMProvider；单元/E2E 默认不调用真实模型。
3. **SDD → DDD → TDD → E2E 顺序**：产品规格/数据模型/Schema/API 契约/SSE 契约 → 演播厅视觉结构与交互 → 核心状态机/调度/隔离/洞察先写测试 → 最后 E2E 验证。
4. 禁止单条 Prompt 一次性生成整个项目；每个阶段独立 Git Commit。

---

## 13. 交付物验收标准（H 类）

- **H1** 仓库含完整源代码、SQLite Schema/初始化脚本、≥5 组主题+嘉宾高质量种子数据。
- **H2** README 含环境要求、安装、启动、环境变量、单 worker 约束、测试命令、技术选型、主要 API、已完成能力与后续改进。
- **H3** docs 含产品规格、系统顶层架构、模块/业务边界、ER 图、数据库说明、API/SSE 契约、测试策略、完成/待办对照表。
- **H4** `docs/prompt-log.md` 至少记录 5 段核心原始开发 Prompt，覆盖 SDD、DDD、TDD、E2E、最终修复/验收；每段后附 1–2 句说明意图、挑战及如何引导 AI 修正。
- **H5** `docs/ai-development-workflow.md`（1–1.5 页）说明 Claude Code + DeepSeek V4 Pro + Superpowers + UI UX Pro Max 的真实使用方式，记录 ≥2–3 个典型问题及解决路径。
- **H6** Git 历史体现真实渐进过程（docs/schema → UI components → tests → feature logic → E2E → final docs），禁止最后一次性提交。
- **H7** `.env`、API Key、Token、调试日志、敏感数据不得入仓；仅提交 `.env.example`。
- **H8** 最终准备 zip、文档与 GitHub/Gitee 链接，按题目指定提交：收件地址 `xulei@wisquest.com`；邮件标题 `[远程作业提交]姓名`；内容为 zip 包 + 文档 + GitHub/Gitee 仓库链接；72 小时期限。**不得在仓库中记录任何邮箱凭据。**

---

## 14. 已锁定的关键决策与纠偏索引（供追溯）

- 核心架构 5 决策（§2）。
- 会话状态机 9 态 + 可恢复错误三元组 + 事务三写（§5）。
- 调度器纯函数化 + 不可信输入校验 + 防饥饿 + 种子幂等（§6）。
- SSE 序号模型（全局 id + 会话 sequence）+ 无丢事件刷新 + command_receipts（§7）。
- turns/insight_evidence 关系表 + 计数确定性聚合 + 复合约束（§8）。
- 单 worker + EngineRegistry + LLM 可靠性 + 两类 Prompt 分离（§9）。
- 失败矩阵 + 洞察重试生命周期 + 发言软/绝对上限 + 结构化降级（§10）。
- 9 态路由 + UI UX Pro Max 门禁 + FakeLLM + H 类交付物（§11–§13）。
