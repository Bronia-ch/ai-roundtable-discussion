# Prompt 日志（AI 开发工作流记录）

本文件记录使用 Claude Code + Superpowers 开发"AI 圆桌讨论 Web App MVP"过程中的核心原始 Prompt，以及关键决策与纠偏。每段原始 Prompt 后附 1–2 句说明当时的意图、挑战及如何引导 AI 修正。

> 说明：本日志仅记录用户提交的原始 Prompt 与最终锁定的决策/纠偏结论，不包含模型的内部 Thought、隐藏推理、API Key 或任何敏感配置。

## 本阶段元数据

- 日期：2026-08-28
- Claude Code：v2.1.250
- 模型：deepseek-v4-pro[1M]
- Superpowers skill：brainstorming

---

## 第 1 条 · SDD / 需求澄清与设计（第 1A 阶段）

**阶段**：SDD（Specification-Driven Development）——产品规格、数据模型、Schema、API 契约、SSE 契约先行。
**对应交付物**：`docs/superpowers/specs/2026-08-28-ai-roundtable-mvp-design.md`

**意图**：先完成规格、状态机、Schema 与事件契约，禁止提前生成代码。

**挑战与修正**：重点解决非固定轮流、实时洞察、会话隔离、断线恢复与错误降级，并通过逐节确认持续纠偏。

### 原始 Prompt（原样保存）

```text
请明确调用并遵循 Superpowers 的 brainstorming 技能，开始"AI 圆桌讨论 Web App MVP"的第 1A 阶段：需求澄清与 SDD 设计。

如果 brainstorming 技能没有成功加载，请立即停止并报告，不要继续使用普通流程代替。

当前阶段只允许分析、提问和设计。不要生成业务代码，不要初始化前后端项目，不要安装依赖，不要执行 Git Commit。设计获得我明确确认后，下一阶段才会创建文档和工程文件。

一、产品目标

构建一个本地运行、前后端分离的中文 AI 圆桌讨论 Web App。用户输入讨论主题和专家人数（默认 4 人），系统调用大模型生成主持人和专家阵容。用户确认阵容后进入演播厅，主持人负责开场、追问和控场，专家根据上下文进行回答、补充、反驳或澄清。讨论过程中实时生成 Transcript，并持续提取共识和分歧。用户结束讨论后生成结构化结论和 JSON 结果。

二、硬性功能要求

1. 首页展示当前及历史讨论，并支持新建讨论。
2. 根据主题和人数生成主持人与专家资料，包括姓名、职业、Title、立场和头像标识。
3. 用户确认阵容后才能进入演播厅。
4. 主持人负责开场、追问、串场和收尾。
5. 专家不能按照固定顺序机械轮流发言。
6. 下一位发言者必须结合讨论上下文、专家立场、发言意愿和公平性动态决定。
7. 发言类型至少包括回答、补充、反驳和澄清。
8. 每次专家发言控制为 1～2 句。
9. 每位专家独立显示等待、准备、发言等状态。
10. 可以展示"当前关注点"或"发言意图"，但不得展示模型隐藏思维链或真实 chain-of-thought。
11. Transcript 只展示实际发言，不展示等待、抢答等内部事件。
12. 每产生新发言后，增量更新当前共识、分歧和讨论焦点，不能只在讨论结束后统一生成。
13. 用户可以结束讨论，结束后生成结构化总结及 JSON 数据。
14. 多场讨论可以并行运行，状态、Transcript、SSE 连接、洞察数据必须相互隔离。

三、硬性技术要求

1. 中文 UI，响应式桌面布局。
2. 页面整体不依赖全页滚动，演播厅各区域应在自身容器内独立滚动。
3. 普通桌面和超宽屏不得出现内容重叠。
4. 前后端分离。
5. SQLite 持久化。
6. 大模型 API Key 只能由后端通过环境变量读取，不得暴露给浏览器。
7. 使用 SSE 作为主要实时通信方案；如果你认为某个场景必须使用 WebSocket，需要解释理由。
8. 后端暂定 Python 3.13 + FastAPI；前端暂定 React + TypeScript + Vite。
9. 后端使用 Pytest，前端使用 Vitest，完整流程使用 Playwright + Microsoft Edge。
10. 需要模型调用失败、超时、用户中断、SSE 断线恢复和服务重启后的合理处理方案。
11. 需要至少 5 组高质量种子数据，每组包含讨论主题及对应嘉宾阵容。
12. 题目中的 DDD 指 Design-Driven Development，但架构文档仍然需要描述模块边界和 bounded contexts，避免把两个概念混为一谈。

四、工程过程要求

整个项目必须体现：

1. SDD：先定义产品规格、数据模型、数据库 Schema、API 契约和 SSE 事件契约。
2. DDD（Design-Driven Development）：先确定演播厅视觉结构、组件状态和交互，再实现页面。
3. TDD：核心状态机、发言调度、会话隔离、洞察更新先写测试再实现。
4. E2E：最后验证完整用户流程、并发会话及异常恢复。
5. 使用 Superpowers 的 planning、TDD、systematic-debugging、verification-before-completion 等工作流。
6. 禁止使用单条 Prompt 一次性生成整个项目。
7. 每个阶段必须有独立、真实、逻辑清晰的 Git Commit。
8. 全程维护 Prompt 日志和 AI 开发工作流说明。

五、本轮需要完成的内容

请按照 brainstorming 工作流：

1. 先复述你理解的产品目标、核心价值和验收边界。
2. 标出题目中存在的歧义、冲突和高风险假设。
3. 如需澄清，每次只问我一个问题，不要一次提出一整组问题。
4. 给出 2～3 种可行架构方案，比较复杂度、实时性、可靠性和 72 小时内完成的风险。
5. 明确推荐方案，但在我确认前不要落盘、不要创建文件。
6. 设计至少应覆盖：用户完整流程；会话和专家状态机；非固定轮流的发言调度策略；SSE 事件流；Transcript、共识和分歧的数据流；多会话隔离；LLM 调用边界；异常恢复和讨论终止条件；MVP 范围与明确不做的功能；可直接验证的验收标准。
7. 不要生成页面代码、后端代码、数据库文件或测试代码。

现在从需求理解开始，并严格按照 brainstorming 技能一次推进一个设计决策。
```

### 本轮最重要的决策（第 1A 阶段产出）

1. **架构方案 A**：后端 asyncio 自动编排 + SSE 推送 + HTTP 控制命令（在 A/B/C 中选定）。
2. **核心 5 决策**：调度=算法为主；意图=每发言决策周期一次批量调用；洞察=逐条增量归类；发言=整句事件；并发=单用户多讨论。
3. **会话状态机 9 态**：draft / panel_generating / panel_ready / ready / live / paused / finalizing / completed / failed，含可恢复错误三元组（last_stable_state / error_code / retry_operation）与"状态+事件同事务三写"。
4. **调度器纯函数化**：确定性打分选人，LLM 意图字段全部视为不可信输入经 Pydantic 校验，模型不得指定最终发言者、不得越会话边界。
5. **SSE 序号模型**：全局 `id` + 会话内 `sequence`（`UNIQUE(session_id, sequence)`），无丢事件刷新，`command_receipts` 持久化命令幂等。
6. **数据模型**：新增 `turns`（代际隔离）与 `insight_evidence`（计数确定性聚合），跨会话复合约束在 DB 层杜绝关联。
7. **异常分级**：洞察重试生命周期（pending/processing/succeeded/retry_wait/permanently_failed）、发言软上限（40 默认/继续+10/绝对 100）、`failed` 仅限会话级不可恢复错误。

### 关键纠偏（设计过程中按用户要求修正）

- 发言调度不能由 LLM 主持人直接点名，改为**算法为主 + LLM 只产出结构化意图**（可 TDD）。
- 单次发言/洞察失败不得让整个会话进入 `failed`，改为**分级降级**。
- "增量更新"不能只是结束后统一生成，改为**逐条增量归类**，结束再全量重算兜底。
- 中断/结束必须分离，并引入 `turn_id`/`generation_epoch` 丢弃迟到响应。
- 事件序号必须**会话内递增**（全局自增会破坏每会话独立补发）。
- 洞察计数不得由 LLM 直接返回 ± 值，改为**后端按 evidence 去重聚合**。
- bounded contexts 须区分**业务上下文**与**基础设施**，并注明 DDD 指 Design-Driven Development。

---

---

## 第 2 条 · 实施计划 / writing-plans（第 1B 阶段）

**阶段**：writing-plans —— 生成可执行的分阶段实施计划。
**技能**：superpowers:writing-plans（Claude Code v2.1.250、模型 deepseek-v4-pro[1M]，见文件顶部元数据）。
**对应交付物**：`docs/superpowers/plans/2026-08-28-ai-roundtable-mvp-implementation.md`

**意图**：把已确认的规格转成可执行、可验证、分阶段提交的实施计划，禁止直接写业务代码或安装依赖。

**挑战与约束**：将 51 个任务映射到 A1–H8 验收编号，控制在 72 小时内并区分 P0/P1/P2；保证 TDD 先写失败测试、UI UX Pro Max 门禁先于前端实现、FakeLLM 隔离真实模型。

### 原始 Prompt（原样保存）

```text
请明确调用并遵循 `superpowers:writing-plans` 技能，开始"AI 圆桌讨论 Web App MVP"的第 1B 阶段：生成可执行的分阶段实施计划。

如果 writing-plans 技能未成功加载，请立即停止并报告，不得用普通流程代替。

一、权威输入

请完整读取并以以下文件为唯一规格来源：

- `docs/superpowers/specs/2026-08-28-ai-roundtable-mvp-design.md`
- `docs/prompt-log.md`
- `.gitignore`

同时检查当前 Git 状态和最近提交，确认：

- 根提交为 `3363e44bbf1f5933f115d9b367285dd1c196f80f`
- 当前没有业务代码和依赖
- 工作区干净
- 不读取或输出任何 API Key

二、本阶段限制

当前只创建实施计划和更新 Prompt 日志：

- 不安装任何依赖；
- 不安装 UI UX Pro Max；
- 不初始化 FastAPI、React 或数据库工程；
- 不生成业务代码、测试代码或配置密钥；
- 不执行实施计划；
- 不调用真实付费模型；
- 不创建 Git Commit，等待我审查后再提交；
- 不使用并行 subagents 或 worktree。

三、计划文件

创建：

`docs/superpowers/plans/2026-08-28-ai-roundtable-mvp-implementation.md`

计划必须使用 Superpowers writing-plans 的可执行任务格式，每项任务至少包含：

1. 目标和对应规格验收编号；
2. 准确的预期文件路径；
3. 前置条件；
4. 先写的失败测试；
5. 运行该测试的具体命令和预期失败原因；
6. 最小实现步骤；
7. 再次运行测试的命令和预期通过结果；
8. 本任务的人工检查点；
9. 本任务的独立 Git Commit 信息；
10. 失败时应调用的 `superpowers:systematic-debugging` 条件。

四、阶段顺序

计划必须严格按以下顺序组织，不能把整个项目压成一个任务：

### Phase 1：SDD 工程契约与骨架

- 后端、前端目录骨架；
- Python/Node 依赖定义；
- `.env.example`；
- SQLite 最终 DDL、幂等初始化与 5 组种子数据；
- ER 图；
- Pydantic 模型；
- API/SSE 事件契约；
- FakeLLMProvider/ScriptedLLMProvider；
- 基础启动和健康检查；
- 不实现完整讨论功能。

### Phase 2：DDD / UI UX Pro Max 设计门禁

- 从官方来源以项目作用域安装并验证 UI UX Pro Max；
- 保存安装及技能加载证据，但不得提交本地敏感配置；
- 使用 UI UX Pro Max 为"AI 演播厅/新闻直播控制台"生成设计系统；
- 持久化 `design-system/MASTER.md`；
- 明确颜色、字体、间距、布局网格、组件状态、响应式断点、独立滚动区域、键盘焦点、reduced-motion 和反模式；
- 先做静态页面、组件状态和 Mock 数据，不接真实 LLM；
- 覆盖首页、阵容确认页、演播厅、finalizing 与 completed 结果态；
- 普通桌面和超宽屏进行视觉验收。

### Phase 3：TDD 后端核心

必须显式调用 `superpowers:test-driven-development`，严格执行 RED → GREEN → REFACTOR：

- 会话状态机；
- 状态与事件同事务提交；
- 发言调度纯函数；
- 防连续发言、点名例外、防饥饿、确定性种子；
- turns/generation_epoch；
- EngineRegistry；
- command_receipts 幂等；
- Transcript；
- insight_evidence 确定性聚合；
- 洞察 Worker；
- 软上限与绝对上限；
- 错误分级和安全降级；
- 服务启动对账；
- 多会话隔离。

### Phase 4：LLM 与实时集成

- DeepSeek/OpenAI 兼容 Provider；
- API Key 只由后端环境变量读取；
- 阵容、批量意图、专家发言、主持人、洞察、最终报告六类调用；
- timeout、有限重试、jitter、Schema 修复、并发信号量；
- SSE 持久化事件日志；
- 快照 + after_seq/Last-Event-ID；
- 前端实时状态、Transcript、洞察和断线恢复；
- 默认测试继续使用 FakeLLM，不调用真实模型；
- 真实模型 smoke test 必须显式开启。

### Phase 5：E2E 与系统修复

必须覆盖：

- 创建讨论 → 生成阵容 → re-roll → 确认 → 进入演播厅 → 开始 → 多轮发言 → 实时洞察 → 中断 → 恢复 → 结束 → finalizing → 结果；
- 两场讨论并发且事件不串线；
- SSE 断线重连；
- 重复 command_id；
- 浏览器刷新恢复；
- 服务重启后 live → paused；
- LLM/洞察/最终报告失败降级；
- 软上限 40、继续 +10、绝对上限 100；
- Edge 浏览器；
- UI 独立滚动、普通桌面和超宽屏不重叠；
- 发现问题时调用 `superpowers:systematic-debugging`；
- 完成前调用 `superpowers:verification-before-completion`。

### Phase 6：文档与提交包

- README；
- 系统架构、bounded contexts、ER、数据库、API/SSE、测试策略；
- 已完成能力与后续改进；
- `docs/ai-development-workflow.md`；
- 至少 5 段核心 Prompt；
- 2～3 个典型问题及解决路径；
- Git 历史与敏感信息检查；
- SQLite 初始化和种子数据验证；
- zip、仓库链接和邮件提交清单；
- 不实际发送邮件或推送远程仓库，除非用户后续明确授权。

五、计划质量要求

- 控制在 72 小时内，标明 P0、P1 和明确可放弃的 P2；
- 前 64～68 小时完成 P0，保留最后 4～8 小时验收缓冲；
- 每个任务应足够小，通常可在 15～60 分钟内完成；
- 每个阶段设置停止点，必须验证通过才能进入下一阶段；
- 每次 Commit 只包含一个逻辑主题；
- 不允许先写实现再补测试；
- 不把 UI UX Pro Max、Superpowers 或 DeepSeek 使用仅写在文档里，计划必须包含真实调用与证据保存步骤；
- 明确哪些测试使用 FakeLLM，哪些 smoke test 才允许真实 API；
- 所有命令适配 Windows PowerShell 和当前路径 `C:\AI圆桌讨论APP`；
- 不使用 Bash 专属命令或 Unix 路径；
- 不在命令中显示或回显密钥。

六、更新 Prompt 日志

在 `docs/prompt-log.md` 追加第 2 条：

- 阶段：实施计划 / writing-plans；
- 当前这条完整原始 Prompt，使用唯一的 `text` 代码块保存；
- 1～2 句说明本轮意图、挑战与约束；
- 记录实际使用的 Claude Code 版本、DeepSeek 模型和 Superpowers skill；
- 不记录隐藏 Thought 或敏感配置。

七、完成前验证

创建计划并更新 Prompt 日志后，调用 `superpowers:verification-before-completion`，检查：

- 只有计划文档和 Prompt 日志发生变化；
- 没有业务代码、依赖或密钥；
- 计划覆盖规格 A1～H8；
- UI UX Pro Max 门禁在前端实现之前；
- TDD 任务明确包含失败测试和通过测试；
- 每个阶段都有验证命令与 Commit；
- 工作区尚未提交。

最后报告：

1. 创建/修改的文件；
2. 计划总阶段数和任务数；
3. P0/P1/P2 分布；
4. 预计时间；
5. 验收编号覆盖情况；
6. 验证结果；
7. `git diff --stat`；
8. 等待我审查，不要执行或提交计划。
```

---

### 最终产出 / 统计信息（第 1B 阶段）

- 阶段数：6
- 任务数：51
- P0 / P1 / P2：49 / 1 / 1
- 逻辑提交组：20
- 时间：计划内任务总计 42.75h（P0 41.75h + P1 0.5h + P2 0.5h，含 Phase 5=10.25h、Phase 6=6.00h）；风险及验收缓冲 10h；计划总占用 52.75h；距 72h 尚余 19.25h（超时保护）
- 验收覆盖：A1–H8 每个硬性验收均有具体 P0 任务 + 验证方法

---

---

## 第 3 条 · Phase 1 工程骨架与契约实现（executing-plans）

**阶段**：Phase 1 SDD 工程契约与骨架（Task 1.1–1.7）
**技能**：superpowers:executing-plans（Claude Code v2.1.250、模型 deepseek-v4-pro[1M]）

**意图**：执行已批准实施计划的 Phase 1，落地后端/前端骨架、SQLite DDL、5 组幂等种子、Pydantic 模型、API/SSE 契约与 FakeLLM，全程 TDD、三个提交组。

**挑战与约束**：严格 RED→GREEN；仅用 CG1/CG2/CG3 三个提交；不装 UI UX Pro Max、不调真实 LLM、不写真实密钥。

### 原始 Prompt（原样保存）

```text
现在开始执行已批准实施计划的 Phase 1：SDD 工程契约与骨架。

请严格遵循以下要求：

1. 明确调用并遵循 `superpowers:executing-plans`。
2. 完整读取并以这两个文件为权威来源：
   - `docs/superpowers/specs/2026-08-28-ai-roundtable-mvp-design.md`
   - `docs/superpowers/plans/2026-08-28-ai-roundtable-mvp-implementation.md`
3. 本轮只执行 Phase 1 的 Task 1.1–1.7，不得提前执行 Phase 2，不得安装 UI UX Pro Max。
4. 在当前仓库 `C:\AI圆桌讨论APP` 中执行，不创建新 worktree，不切换分支，不推送远端。
5. 开始前确认：
   - 当前 HEAD 为 `d4bc3446d2bb4cd8021fcb3b07992463b4de5d1e`；
   - 工作区干净；
   - 当前 Claude Code 会话模型显示为 `deepseek-v4-pro[1M]`；
   - Superpowers 的 executing-plans、test-driven-development、systematic-debugging、verification-before-completion 可调用。
6. 将本条用户原始 Prompt 原样追加到 `docs/prompt-log.md`，作为第 3 条“Phase 1 工程骨架与契约实现”记录；不得记录隐藏 thought、密钥或内部推理。
7. Phase 1 中涉及可测试逻辑的任务必须调用并遵循 `superpowers:test-driven-development`：
   - 先写测试；
   - 运行并确认测试因目标功能不存在而失败；
   - 再写最小实现；
   - 重新运行确认通过；
   - 禁止先写实现再补测试。
8. 按计划仅使用三个逻辑提交组：
   - CG1：Task 1.1–1.2，后端和前端工程骨架；
   - CG2：Task 1.3–1.4，SQLite DDL、初始化及 5 组幂等种子；
   - CG3：Task 1.5–1.7，Pydantic 模型、API/SSE 契约、FakeLLM/ScriptedLLM。
   同一提交组内不要提前提交，组级测试通过后只创建一次提交。
9. 可以创建虚拟环境并安装 Phase 1 所需依赖，但必须：
   - 使用已被 `.gitignore` 忽略的 `.venv`；
   - 不创建或提交真实 `.env`；
   - 不写入真实 API Key；
   - 不发起真实 LLM API 请求；
   - 前端依赖只写入正常的 `package.json` 和 lockfile；
   - 不安装 Phase 2 或后续阶段才需要的额外工具。
10. 每个任务按计划执行精确测试命令。如计划中的代码片段或命令存在语法、路径或版本错误：
    - 不要机械照抄；
    - 先调用 `superpowers:systematic-debugging` 找出原因；
    - 做满足规格的最小修正；
    - 在最终报告中记录“计划预期、实际问题、修正方式”。
11. SQLite Schema 必须落实规格中的核心约束，包括：
    - sessions、participants、turns、utterances、insights、insight_evidence、events、command_receipts、discussion_reports；
    - foreign_keys；
    - 会话内 sequence；
    - 必要 UNIQUE、复合 FK 和 NOT NULL；
    - finalizing、generation_epoch、last_stable_state、error_code、retry_operation；
    - 不允许跨会话关联。
12. 种子任务必须产生 5 组幂等示例数据：
    - 标记 `is_sample`；
    - 不冒充真实历史记录；
    - 重复运行后数量不增加。
13. FakeLLMProvider 和 ScriptedLLMProvider 不得访问网络，不得读取真实密钥。
14. 每个提交前运行对应组级测试；提交后确认提交内容和工作区状态。
15. Phase 1 全部任务完成后，调用 `superpowers:verification-before-completion`，执行停止点核验：
    - `python -m pytest backend/tests -v` 全绿；
    - `npm --prefix frontend run test` 全绿；
    - `npm --prefix frontend run build` 成功；
    - FastAPI `/healthz` 实际返回 HTTP 200；
    - SQLite 9 张核心表存在；
    - 种子数据重复执行后仍精确为 5 组；
    - FakeLLM 测试证明不访问网络；
    - Git 中无 `.env`、数据库运行文件、依赖目录或密钥；
    - 本阶段实际提交数精确为 3；
    - 工作区干净。
16. 遇到测试失败或环境问题时使用 `superpowers:systematic-debugging`，不要跳过测试、删除断言或伪造通过结果。
17. 完成 Phase 1 后停止，不得自动进入 Phase 2，不得安装 UI UX Pro Max。

最终报告必须包含：

1. 完成的 Task 1.1–1.7；
2. 创建/修改的文件；
3. 安装的依赖；
4. RED→GREEN 的实际测试证据；
5. SQLite 表和种子核验结果；
6. 前后端测试与构建结果；
7. `/healthz` 验证结果；
8. 三个提交的完整 hash、信息及文件统计；
9. 对计划中任何错误所做的修正；
10. `git status --porcelain`；
11. 明确说明未执行 Phase 2、未调用真实 LLM。

完成后停止，等待我审查。
```

---

**实际挑战与纠偏**：Windows 上 pytest 的 tmp_path 遇系统临时目录 `PermissionError [WinError 5]`，通过 pytest.ini 增加 `addopts = --basetemp=.pytest_tmp` 并将 `.pytest_tmp/` 加入 .gitignore 解决。其余最小修正：config 用 pydantic v2 的 `model_config`（替代 v1 `class Config`）；`.env.example` 用 `LLM_SQLITE_PATH` 匹配 `env_prefix=LLM_`；willingness 用 `field_validator` 钳制（规格要求"钳制"而非 `Field(ge,le)` 拒绝）；前端 Phase 1 仅装基础依赖（`@playwright/test`/`@testing-library`/`jsdom` 推迟到 Phase 2）；build 用 `tsc --noEmit`（单 tsconfig）；test_contract 修正 `r.methods`（集合）与字符串比较。

---

（后续阶段：DDD 设计系统、TDD 核心逻辑、E2E、最终修复/验收的 Prompt 将按阶段追加。）
