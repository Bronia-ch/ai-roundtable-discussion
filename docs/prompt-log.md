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

---

## 第 4 条 · Phase 1 复审与数据库约束纠偏

**阶段**：Phase 1 数据库约束修复
**技能**：superpowers:systematic-debugging + superpowers:test-driven-development

**意图**：修复 `utterances → turns` 外键引用非唯一列导致的 `foreign key mismatch`，并补全会话作用域外键约束。

**实际挑战与纠偏**：现有 `test_db.py` 只查表存在与 `PRAGMA foreign_keys`，未做真实关联写入，漏检了 `turns.id` 无 UNIQUE 导致的外键问题；本轮先写跨会话/未知会话引用的失败测试（真实 RED 暴露 `foreign key mismatch - "utterances" referencing "turns"`），再补 `UNIQUE(session_id, id)` 与复合外键修复。

### 原始 Prompt（原样保存）

```text
Phase 1 复审发现数据库最终 DDL 存在未被现有测试覆盖的外键问题。暂停进入 Phase 2，只进行一次 Phase 1 数据库约束修复。

请明确调用并遵循：

- `superpowers:systematic-debugging`
- `superpowers:test-driven-development`
- 完成前调用 `superpowers:verification-before-completion`

问题证据：

当前 `utterances` 使用：

`FOREIGN KEY(turn_id) REFERENCES turns(id)`

但 `turns.id` 当前不是 PRIMARY KEY，也没有 UNIQUE 约束。SQLite 可能允许创建表，但实际插入 utterance 时会产生 `foreign key mismatch`。现有 `test_db.py` 只检查表存在和 `PRAGMA foreign_keys=1`，没有真正插入关联数据，因此漏检。

本轮要求：

1. 先追加失败测试，不要先修改 Schema。至少覆盖：
   - 合法 session、participant、turn、utterance 能成功写入；
   - session A 的 utterance 不能引用 session B 的 turn；
   - session A 的 utterance 不能引用 session B 的 speaker；
   - turn 的 `selected_participant_id` 不能引用另一会话的 participant；
   - events 不能引用不存在的 session；
   - command_receipts 不能引用不存在的 session；
   - 合法测试数据写入后 `PRAGMA foreign_key_check` 返回空结果。

2. 运行新增测试并保存真实 RED 证据。预期应暴露 `foreign key mismatch` 或跨会话引用未被拒绝。

3. 对 `backend/app/schema.sql` 做最小修复：
   - `turns` 增加 `UNIQUE(session_id, id)`；
   - `utterances` 的 turn 外键改为：
     `FOREIGN KEY(session_id, turn_id) REFERENCES turns(session_id, id)`；
   - `turns.selected_participant_id` 增加会话内复合外键：
     `FOREIGN KEY(session_id, selected_participant_id) REFERENCES participants(session_id, id)`；
   - `events.session_id` 增加 FK → `sessions(id)`；
   - `command_receipts.session_id` 增加 FK → `sessions(id)`；
   - 不删除现有复合约束，不放宽测试；
   - 如 SQLite 对复合外键提出父键唯一性要求，按数据库规范补足对应 `UNIQUE(session_id, id)`，不要关闭 foreign_keys。

4. 修复后运行新增测试确认 GREEN，再运行：
   - `.venv/Scripts/python -m pytest backend/tests -v`
   - `npm --prefix frontend run test`
   - `npm --prefix frontend run build`

5. 将本条原始 Prompt 原样追加到 `docs/prompt-log.md`，标记为"Phase 1 复审与数据库约束纠偏"，附 1–2 句说明现有测试为何漏检以及如何通过真实关联写入测试修复。不得记录隐藏 thought。

6. 只提交本次相关文件：
   - `backend/app/schema.sql`
   - `backend/tests/test_db.py`，或新增的精确数据库约束测试文件
   - `docs/prompt-log.md`

7. 创建一个透明的修复提交：

`fix(db): enforce session-scoped foreign keys`

不要 amend、rebase 或重写已有 CG1–CG3 历史。本修复提交作为 Phase 1 审查发现后的独立纠偏证据，因此 Phase 1 最终实际提交数应更新为 4。

8. 完成前核验：
   - 新增测试真实经历 RED→GREEN；
   - 全部后端测试通过；
   - 前端测试和构建仍通过；
   - `PRAGMA foreign_key_check` 无结果；
   - 跨会话 turn/speaker/selected participant 引用均被数据库拒绝；
   - 未生成运行时数据库或真实 `.env`；
   - 工作区干净；
   - 未进入 Phase 2；
   - 未调用真实 LLM。

最终报告列出 RED 失败、Schema 修正、GREEN 结果、完整测试结果、新提交 hash 和 `git status --porcelain`，然后停止等待审查。
```

---

---

## 第 5 条 · DDD / UI UX Pro Max 与静态页面设计（Phase 2）

**阶段**：Phase 2 DDD / UI UX Pro Max 门禁与静态界面设计
**技能**：superpowers:executing-plans + superpowers:test-driven-development + ui-ux-pro-max:design-system

**意图**：安装并验证 UI UX Pro Max，生成演播厅设计系统，实现静态页面与组件状态，并做 Edge 视觉验收。

**实际挑战与纠偏**：`/plugin` 为用户级斜杠命令，代理改用等价的 `claude plugin` CLI 完成安装（`marketplace add` + `install --scope project -y`）；安装后技能未立即可调用，需用户执行 `/reload-plugins` 后 `ui-ux-pro-max:design-system` 才成功加载。

### 原始 Prompt（原样保存）

```text
现在开始执行已批准实施计划的 Phase 2：DDD / UI UX Pro Max 门禁与静态界面设计。

请严格遵循以下要求：

1. 明确调用并遵循 `superpowers:executing-plans`。
2. 完整读取并以以下文件为权威来源：
   - `docs/superpowers/specs/2026-08-28-ai-roundtable-mvp-design.md`
   - `docs/superpowers/plans/2026-08-28-ai-roundtable-mvp-implementation.md`
   - `docs/architecture.md`
3. 本轮只执行 Phase 2 的 Task 2.1–2.4。Task 2.5 为 P2：只有 2.1–2.4 全部通过且没有阻塞时才可执行，否则明确记录为待选增强。
4. 不得进入 Phase 3，不得实现状态机、调度器、DiscussionEngine、真实 SSE 或真实 LLM 调用。
5. 开始前确认：
   - 当前 HEAD 为 `450a45d214f7d4a431ed4fa368fad53bc54b47d9`；
   - 工作区干净；
   - Phase 1 后端 21 项测试通过；
   - 当前模型显示为 `deepseek-v4-pro[1M]`；
   - Superpowers 的 executing-plans、test-driven-development、systematic-debugging、verification-before-completion 可调用。
6. 将本条用户原始 Prompt 原样追加到 `docs/prompt-log.md`，作为“DDD / UI UX Pro Max 与静态页面设计”阶段记录。不得记录隐藏 thought、密钥或内部推理。

## Task 2.1：安装并验证 UI UX Pro Max

7. 必须使用官方来源：

`https://github.com/nextlevelbuilder/ui-ux-pro-max-skill`

在 Claude Code 中依次执行：

`/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill`

`/plugin install ui-ux-pro-max@ui-ux-pro-max-skill`

安装作用域选择：

`Install for all collaborators on this repository`

然后执行：

`/reload-plugins`

8. 重载后必须实际核验 UI UX Pro Max 技能可以调用。如果没有成功加载：
   - 立即调用 `superpowers:systematic-debugging`；
   - 不得用普通设计流程冒充；
   - 无法解决时停止并报告，不得继续 Task 2.2。
9. 创建 `docs/ui-ux-pro-max-install-evidence.md`，记录：
   - 官方来源；
   - 实际安装命令；
   - 安装作用域；
   - 插件/技能名称与版本（若可读取）；
   - `/reload-plugins` 结果；
   - 成功调用技能的可公开证据；
   - 日期与当前模型。
   不得写入 API Key、Token 或本地敏感配置。
10. 检查插件安装造成的项目文件变化：
    - 如果生成项目级 `.claude/settings.json`，仅在它只含插件启用信息且不含密钥时才可提交；
    - `.claude/settings.local.json` 必须继续忽略，不得提交；
    - 提交前显示 `.claude/` 中所有待提交文件内容和敏感信息扫描结果。

## Task 2.2：设计系统先行

11. 必须明确调用 UI UX Pro Max 技能，为本项目生成“中文 AI 圆桌演播厅 / 直播控制台”设计系统。
12. 创建设计系统文件 `design-system/MASTER.md`，至少明确：
    - 产品视觉定位与设计原则；
    - 中文字体栈；
    - 色彩 token、语义色和对比度；
    - 间距、圆角、阴影、边框；
    - 普通桌面与超宽屏网格；
    - 首页、阵容确认、演播厅、结果页的布局；
    - 主持人与专家席位；
    - waiting / preparing / speaking / idle 状态；
    - 9 种讨论状态；
    - Transcript、洞察侧栏和席位区域的独立滚动；
    - 键盘焦点；
    - 空状态、错误态、加载态和降级态；
    - `prefers-reduced-motion`；
    - 状态不得只靠颜色；
    - 禁止全页滚动、内容重叠和横向溢出；
    - 明确反模式。
13. 不要生成真实人物头像图片；使用颜色、首字母或 emoji 标识，符合 MVP 范围。
14. Task 2.1–2.2 完成并核验后统一创建 CG4 提交，不要分别提交。

## Task 2.3：静态页面与组件状态

15. 先调用并遵循 `superpowers:test-driven-development`。
16. 安装本阶段所需且仅限本阶段的前端测试依赖，例如：
    - `@testing-library/react`
    - `@testing-library/jest-dom`
    - `jsdom`
    - `@playwright/test`
    使用已有 Microsoft Edge，不下载 Chromium。
17. 先写失败测试并保存 RED 证据，再实现：
    - 首页讨论列表和新建入口；
    - 阵容确认页；
    - 演播厅；
    - 结果页；
    - DiscussionCard；
    - PanelCard；
    - ParticipantSeat；
    - Transcript；
    - InsightPanel。
18. 当前只使用类型安全的 Mock 数据，不接真实后端业务，不访问真实 LLM。
19. 静态界面必须覆盖：
    - 中文 UI；
    - 示例讨论明确标记；
    - 9 态卡片路由；
    - 主持人 idle/preparing/speaking；
    - 专家 waiting/preparing/speaking；
    - 当前关注点；
    - Transcript 仅显示实际发言；
    - 共识、分歧、焦点、未解决问题；
    - 结束结果和 JSON 展示；
    - 状态文本/图标与颜色共同表达；
    - 各区域独立滚动；
    - 无全页横向滚动。
20. Task 2.3 测试通过后创建一次 CG5 提交。

## Task 2.4：Edge 视觉与布局验收

21. 配置 Playwright 使用已安装的 Microsoft Edge：

`channel: "msedge"`

不得下载 Chromium。
22. 先写失败测试并保存 RED 证据，至少验证：
    - 1280×900 普通桌面；
    - 1920×1080 或更宽屏幕；
    - 页面无横向溢出；
    - 关键区域不重叠、不截断；
    - 页面整体不依赖全页滚动；
    - Transcript、洞察区等各自可滚动；
    - 键盘焦点可见；
    - `prefers-reduced-motion: reduce` 时禁用非必要动画；
    - 状态不是只靠颜色表达。
23. 如果测试失败，调用 `superpowers:systematic-debugging`，禁止通过删除断言、放宽视口或隐藏内容来使测试通过。
24. Task 2.5 仅在所有 P0 验证完成后执行；若执行，只允许做微动效、悬停态、空状态等小幅润色，不得扩大功能范围。
25. Task 2.4 与可选 2.5 完成后统一创建 CG6 提交，并把本阶段 Prompt 日志更新纳入该提交。

## 提交与验证

26. 本阶段最多三个逻辑提交：
    - CG4：UI UX Pro Max 安装证据 + 项目安全插件配置 + `design-system/MASTER.md`
    - CG5：静态页面、组件、样式及组件测试
    - CG6：Playwright Edge 视觉验收、可选视觉润色、Prompt 日志更新
27. 每个提交前展示：
    - 测试结果；
    - 暂存文件清单；
    - 是否包含依赖目录、构建产物、截图报告或敏感配置。
28. 完成后调用 `superpowers:verification-before-completion`，核验：
    - UI UX Pro Max 确实安装且可调用；
    - 设计系统无占位符；
    - `npm --prefix frontend run test` 全绿；
    - `npm --prefix frontend run build` 成功；
    - Playwright 使用 Edge 且视觉测试全绿；
    - 1280 和 1920 布局无横向溢出或重叠；
    - reduced-motion 验证通过；
    - 后端 `python -m pytest backend/tests -v` 仍为 21 项全绿；
    - Git 未跟踪 `node_modules`、`dist`、Playwright 报告、真实 `.env` 或密钥；
    - 工作区干净；
    - 未执行 Phase 3；
    - 未调用真实 LLM。
29. 完成 Phase 2 后停止，不得自动进入 Phase 3。

最终报告必须包含：

1. 完成的 Task 2.1–2.5及是否执行 P2；
2. UI UX Pro Max 安装与加载证据；
3. 设计系统核心决策；
4. 创建/修改文件；
5. 安装的依赖；
6. RED→GREEN 测试证据；
7. Vitest、构建、Playwright Edge 和后端回归结果；
8. 1280/1920/reduced-motion 验收结果；
9. CG4–CG6 的完整 commit hash、信息和统计；
10. 对计划错误或环境问题的修正；
11. `git status --porcelain`；
12. 明确说明未执行 Phase 3、未调用真实 LLM。

完成后停止，等待我审查。
```

---

---

## 第 6 条 · TDD 后端核心逻辑（Phase 3）

**阶段**：Phase 3 TDD 后端核心（Task 3.1–3.14，P0）
**技能**：superpowers:executing-plans + superpowers:test-driven-development

**意图**：以逻辑提交组为批次，先写失败测试再实现，落地会话状态机、事务三写、调度器、turns/registry/命令幂等、Transcript/洞察、上限/降级/对账/多会话隔离。

**实际挑战与纠偏**：（随组推进补充）

### 原始 Prompt（原样保存）

```text
Phase 2 复审通过。现在执行实施计划 Phase 3：TDD 后端核心逻辑。

请调用并遵循：

- `superpowers:executing-plans`
- `superpowers:test-driven-development`
- 出现非预期失败时使用 `superpowers:systematic-debugging`
- 完成前使用 `superpowers:verification-before-completion`

权威来源：

- `docs/superpowers/specs/2026-08-28-ai-roundtable-mvp-design.md`
- `docs/superpowers/plans/2026-08-28-ai-roundtable-mvp-implementation.md`
- `backend/app/schema.sql`
- `docs/architecture.md`

执行边界：

1. 本轮只执行 Phase 3 的 P0 Task 3.1–3.14。
2. Task 3.15 为 P1，默认不执行；仅在全部 P0 完成且无需额外调试时执行。
3. 不进入 Phase 4，不实现真实 LLM Provider、真实 SSE 传输或前端实时接入。
4. 不调用真实外部 API。
5. 当前仓库直接执行，不创建 worktree、不切换分支、不推送远端。
6. 开始前确认：
   - HEAD 为 `ca4805eec3ce4ee9cb0c9d46c3c48cdc00db4727`；
   - 工作区干净；
   - 后端 21 项测试通过；
   - 前端 17 项测试、构建、Edge 6 项测试通过。

## 提速后的 TDD 执行方式

7. 以逻辑提交组为批次执行，不为每个微任务单独等待：
   - 先为该组全部任务编写失败测试；
   - 统一运行该组测试并保存每类预期 RED 证据；
   - 实现该组最小代码；
   - 统一运行组级 GREEN；
   - 运行后端回归；
   - 展示暂存清单并提交。
8. RED 必须因目标功能缺失或行为错误而失败；测试夹具错误、导入路径错误、环境权限错误不算有效 RED，需先修复测试基础设施。
9. 已获授权的 Pytest、Vitest、build、E2E 和只读搜索命令直接执行，不重复请求。
10. 文件编辑和测试之间无需等待用户文字确认；仅在安装依赖、Git 提交、外部调用、破坏性操作或改变已确认设计时暂停。
11. 不删除测试、不放宽断言、不用 sleep 掩盖并发问题。

## CG7：Task 3.1–3.2

12. 实现九态会话状态机和原子状态/事件事务：
    - 严格迁移表；
    - completed/failed 终态；
    - 状态业务写入、`last_event_sequence` 递增、events 插入同一事务；
    - 提交成功后才允许广播；
    - 事件失败整体回滚；
    - 两会话 sequence 各自从 1 开始；
    - SQLite busy/locked 有限重试，但 LLM/网络调用不得位于事务内。
13. 测试必须包含正常迁移、非法迁移、终态、事务回滚、事件序号和跨会话独立。
14. GREEN 后创建一次 CG7 提交。

## CG8：Task 3.3–3.4

15. 实现纯函数、确定性的非固定轮流调度：
    - 输入为已校验的意图、立场、历史和公平性信号；
    - 模型不得直接指定最终发言者；
    - 上一位默认不得连续发言；
    - 仅明确点名追问允许例外；
    - 防长期饥饿；
    - 同输入和随机种子产生同结果；
    - 无可用意图时规则降级；
    - `willingness` 已钳制到 `[0,1]`。
16. 测试覆盖规格中的调度不变量，不回退固定轮询。
17. Task 3.15 的额外边界变体默认跳过并记录为 P1。
18. GREEN 后创建一次 CG8 提交。

## CG9：Task 3.5–3.7

19. 实现：
    - turns 与 generation_epoch；
    - 中断后迟到响应拒绝；
    - 原子 EngineRegistry，同一 session 最多一个运行 engine；
    - start/resume/retry 的 session 级锁；
    - command_receipts 持久化幂等；
    - 重复 `(session_id, command_id)` 返回原状态，不重复执行任务。
20. 必须有真实 asyncio 并发测试，证明并发 start/resume 不产生双 engine。
21. GREEN 后创建一次 CG9 提交。

## CG10：Task 3.8–3.10

22. 实现 Transcript 与洞察核心：
    - 发言非空、长度、speaker/turn 同会话校验；
    - utterance 会话内 ordinal；
    - 迟到 generation_epoch 不写入；
    - insight_evidence 作为共识/分歧计数真值；
    - support/oppose 按去重 participant 聚合；
    - LLM 不得直接返回计数；
    - 洞察状态 pending/processing/succeeded/retry_wait/permanently_failed；
    - 同会话按 ordinal 顺序领取；
    - 不同会话允许有限并行；
    - 条件更新防重复领取；
    - 洞察失败不阻塞下一轮发言。
23. 测试覆盖重复 evidence、跨会话 evidence、顺序处理、防重复领取和永久失败后不再领取。
24. GREEN 后创建一次 CG10 提交。

## CG11：Task 3.11–3.14

25. 实现并测试：
    - 40 条软上限自动 paused；
    - 每次继续增加 10；
    - 100 条绝对上限只能结束；
    - 失败分类与安全降级；
    - 仅会话级不可恢复持久化/一致性错误进入 failed 且带 error_code；
    - 启动对账幂等；
    - preparing/speaking 恢复为 waiting/idle；
    - generating turn 取消并递增 epoch；
    - live 重启后变 paused，不自动调用 LLM；
    - pending/processing 洞察恢复；
    - 多会话查询、状态、Transcript、洞察和任务互相隔离；
    - 一场暂停/失败不影响另一场。
26. 多会话隔离属于 P0，不得跳过。
27. 将本条原始 Prompt 原样追加到 `docs/prompt-log.md`，作为“TDD 后端核心逻辑”阶段记录，并附 1–2 句意图、挑战和纠偏；不得记录隐藏 thought。
28. GREEN 后创建一次 CG11 提交，包含 Prompt 日志更新。

## 每组提交规则

29. Phase 3 最多创建 5 个 P0 提交：CG7–CG11。
30. 每次 Git 提交仍使用单次授权，不申请长期 `git add`/`git commit` 权限。
31. 提交前展示：
    - 该组 RED 摘要；
    - GREEN 测试数量；
    - 完整后端回归结果；
    - 暂存文件清单；
    - 无数据库、`.env`、缓存或密钥。
32. 若 Task 3.15 被执行，合并进 CG8，不增加提交数量。

## Phase 3 最终核验

33. 调用 `superpowers:verification-before-completion`，至少确认：
    - 全部后端测试通过；
    - Phase 1 的 21 项测试仍通过；
    - 前端 17 项测试与构建仍通过；
    - 必要时 Edge 6 项视觉回归仍通过；
    - 状态机、事务、调度、并发 registry、命令幂等、Transcript、洞察、恢复、多会话隔离均有自动化测试；
    - SQLite `PRAGMA foreign_key_check` 无异常；
    - Git 未跟踪运行时数据库、`.env`、缓存或依赖目录；
    - 工作区干净；
    - Phase 3 P0 实际提交数为 5；
    - 未执行 Phase 4；
    - 未调用真实 LLM。

最终报告必须列出：

1. Task 3.1–3.15 的完成或跳过状态；
2. 每组 RED→GREEN 证据；
3. 核心设计实现摘要；
4. 并发与多会话测试证据；
5. 全部测试和构建结果；
6. CG7–CG11 完整 commit hash、信息和统计；
7. 计划或环境问题及修正；
8. `git status --porcelain`；
9. 明确说明未执行 Phase 4、未调用真实 LLM。

完成后停止等待审查。
```

---

（后续阶段：DDD 设计系统、TDD 核心逻辑、E2E、最终修复/验收的 Prompt 将按阶段追加。）
