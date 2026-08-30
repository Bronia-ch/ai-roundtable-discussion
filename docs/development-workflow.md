# 开发工作流（Claude Code + Superpowers 实际过程）

> 本文件记录本项目实际的开发工作流与纠偏过程。工具链：Claude Code（v2.1.250）+ DeepSeek V4 Pro[1M] 后端模型、Superpowers 技能集、ui-ux-pro-max 设计系统（v2.13.0）。**真实 DeepSeek API 从未在本项目执行过**——所有 LLM 验证均基于 FakeLLM/ScriptedLLM 替身；以下流程不包含任何虚构的真实 API 结果。

## 1. 总体流程：SDD → DDD → TDD → E2E

1. **SDD（规格先行）**：每阶段先写产品规格（`docs/superpowers/specs/`）与实施计划（`docs/superpowers/plans/2026-08-28-ai-roundtable-mvp-implementation.md`，6 阶段 51 任务），规格锁定 9 态状态机、Schema 与事件契约后才进入编码。
2. **DDD（领域驱动）**：按 bounded context 拆模块（会话生命周期/编排/转录/洞察/报告 + 事件/幂等/LLM/DB 基础设施），跨 context 只经事务与事件契约交互，禁止私有状态互访。
3. **TDD（RED→GREEN）**：每个任务先写失败测试（RED，用确定性的替身/触发器复刻故障窗口），获批后写最小实现（GREEN），再全量回归。每文件编辑单独批准、diff 先审后批、测试命令单独批准，`SMOKE_REAL_LLM=0` 纪律保证离线矩阵恒定不触网。
4. **UI UX Pro Max 门禁**：前端组件以 `design-system/MASTER.md` 设计 token 为准，静态页先行 + Edge 视觉验收（证据见 `docs/ui-ux-pro-max-install-evidence.md`）。
5. **E2E（Phase 5）**：Playwright webServer 自动编排——后端内存 SQLite + `LLM_BASE_URL=http://127.0.0.1:9/v1` 网络隔离（误触 LLM 也只能本机失败）+ vite dev；验证快照→SSE 增量→命令→最终报告全链路。
6. **Phase 6（交付）**：只读盘点 → 文档补齐 → 四类测试全量运行 → 敏感信息扫描 → 交付清单 → 展示 diff 与拟暂存清单，**停等批准**；不提交、不 push、不发邮件。

## 2. 真实问题与修复路径（节选）

**问题 1：恢复模式撞 UNIQUE(session_id, sequence)**（TDD GREEN 回归）
失败轮 t2 在 turns 表占位 `(s1, sequence=2, status='failed')`；恢复时引擎重建并 `create_turn(sequence=2)` → UNIQUE 冲突 → 后台任务崩溃、测试 wait_entered 超时。
修复：round 路径先查 `SELECT id FROM turns WHERE session_id=? AND sequence=? AND status='failed'`，命中复用占位 turn（状态改 generating），否则才新建；零测试改动（方案 C）。

**问题 2：D9 帧断言自相矛盾**
断言"count==2"与"paused 帧 sequence==3"不可同时成立——专家 utterance 必广播，上限 2 时事件帧必然多一条 utterance.completed。
修复：与用户确认后把 D9 修订为 4 帧 `[state_changed, utterance.completed, utterance.completed, state_changed]`、paused sequence==4，docstring 同步；其余断言（count==2、paused、error_code）原样保留。

**问题 3：漏传 self.conn 的 TypeError**
`mark_insight_state(uid, "permanently_failed")` 漏 `self.conn` → D5/D6/D7 定向测试 TypeError。属提交前自审漏检：批准 diff 有缺陷。
修复：补 `mark_insight_state(self.conn, ...)`，向用户说明缺陷来源后按批准落地。

**问题 4：门禁读扩列引发的替身失配（全量回归）**
CG-D 把门禁读从 2 列扩为 3 列（`status, retry_operation, error_code`，transactions.py），既有并发测试替身仍返回 2 元组 → 解包 ValueError → 500。
修复：测试替身 `_StaleStatusCursor` 补齐第 3 列（默认 None），生产代码零改动，B2 断言不动。

## 3. 关键纪律

- **每文件编辑单独批准、diff 先审后批、测试命令单独批准**；任何"未获批先跑"都不允许。
- **不得碰概率**：并发/竞态用可控替身复刻最坏交错（门禁读过期快照 + 无条件覆盖），而非靠真实并发碰运气。
- **不得伪造证据**：真实 LLM 未执行即如实标注；Prompt 日志无法逐字恢复的内容标"阶段摘要"。
