"""CG-D RED：失败矩阵 + 降级阶梯 + 发言上限 + resume 恢复语义 + 幂等迁移
（§10.1 失败矩阵 / §10.3 发言终止条件 / §10.4 降级阶梯 / E3 验收）。

契约：
- 失败矩阵（§10.1）：host/utterance 的 AUTH/SCHEMA/重试耗尽 → 任务停止 + paused 迁移
  （error_code + last_stable_state='live'）；FATAL → 任务停止、状态保持不动（CG-B 契约，
  test_engine_llm_failure_stops_task_keeps_live 锁定）。
- 降级阶梯（§10.4）：intent 任何失败 → RuleScheduler 降级（used_rule_scheduler_count）
  讨论继续；insight 任何失败/结构非法 → utterance 标 permanently_failed（计数）讨论继续；
  降级事实经 session.degraded 事件持久化（sessions 降级列），finalize 报告带降级标记
  （degraded_components / 计数列 / report_generated_with_degraded_context）。
- 发言上限（§10.3/E3）：每轮落库后 count>=cap → 停止 + paused（cap<100：
  utterance_cap_reached；cap>=100：absolute_cap_reached）；恢复模式（count>0）不开场、
  ordinal 从 count+1 继续（不撞 UNIQUE(session_id, ordinal)）；count>=cap 启动即停
  （零新增发言，绝对上限防线）。
- resume 恢复语义（v3）：软上限（utterance_cap_reached）→ cap+10（MIN 封顶 100）并清码；
  失败暂停/手动软暂停不加 cap；绝对上限（absolute_cap_reached）→ execute_command 命令
  门禁 CONFLICT（409）：不迁移、不写 receipt、不 bump seq、不启动任务，会话仅可 end；
  重建以 registry 任务存活状态判别（task 不存在/已 done → remove + 重建）。
- schema 迁移：既有库（无 CG-D 5 列）init_db 幂等补列（DEFAULT 生效、数据保留、
  重复 init_db no-op）。

当前实现：引擎无 retries 参数/无 call_with_retry 包装/无 paused 迁移/无降级记账/无上限/
无恢复模式；resume 路由仅对在引擎发信号（get_engine 存在性判别）；execute_command 无
绝对上限门禁；sessions 无 5 列；db 无迁移 → 全部失败（有效 RED：行为/列缺失 +
hasattr 能力缺失守卫）。
"""

import asyncio
import json

import aiosqlite
import httpx
import pytest

from app import db
from app import main
from app.core import transactions
from app.core.engine import DiscussionEngine
from app.core.engine_registry import EngineRegistry
from app.core.errors import AuthError, SchemaError
from app.core.event_store import EventStore
from app.core.transactions import CommandOutcome
from app.llm.fake import ScriptedLLMProvider


SCRIPT = {
    "host": {"text": "欢迎来到圆桌讨论"},
    "intent": {"items": [{"participant_id": "e1", "intent_type": "answer", "willingness": 0.9}]},
    "utterance": {"text": "我认为这个观点值得探讨"},
    "insight": {"create": {"kind": "focus", "text": "AI 红利分配"}},
    "report": {"summary": "讨论完成", "key_consensus": ["共识一"]},
}


class FailingProvider:
    """脚本 provider + 按 call_type 抛异常：fail 恒定抛、fail_once 首次抛之后正常
    （R1 恢复场景）；calls 记录调用序列（D2 断言 AUTH 不重试恰 1 次）。
    retries=0 的引擎免退避 sleep——RECOVERABLE 立即上抛（call_with_retry 契约）。"""

    def __init__(self, script: dict, fail: dict | None = None, fail_once: dict | None = None):
        self.script = script
        self.fail = fail or {}
        self.fail_once = fail_once or {}
        self.calls: list[str] = []

    async def generate(self, call_type: str, system: str, user: str) -> dict:
        self.calls.append(call_type)
        if call_type in self.fail:
            raise self.fail[call_type]
        if call_type in self.fail_once:
            exc = self.fail_once.pop(call_type)
            raise exc
        if call_type not in self.script:
            raise KeyError(call_type)
        return self.script[call_type]


class GateProvider:
    """测试门控 provider（与 test_routes.GateProvider 同契约，本文件局部定义）：
    每次 generate 先 set entered、再等待 gate；wait_entered 配对消费（后 clear）。"""

    def __init__(self, inner, gate: asyncio.Event):
        self.inner = inner
        self.gate = gate
        self.entered = asyncio.Event()

    async def generate(self, call_type: str, system: str, user: str):
        self.entered.set()
        await self.gate.wait()
        return await self.inner.generate(call_type, system, user)

    async def wait_entered(self, timeout: float = 2.0) -> None:
        await asyncio.wait_for(self.entered.wait(), timeout=timeout)
        self.entered.clear()


async def _seed_ready(conn, sid):
    """discussion/start 的合法前置：ready + 1 host + 2 expert（与 test_routes 同构）。"""
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, 't', 4, 'ready')", (sid,)
    )
    for pid, role, sort in [("h1", "host", 0), ("e1", "expert", 1), ("e2", "expert", 2)]:
        await conn.execute(
            "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
            "VALUES (?, ?, ?, 'n', 'p', 't', 's', '#111', '🤖', ?)",
            (pid, sid, role, sort),
        )
    await conn.commit()


async def _seed_utterances(conn, sid, count):
    """注入 count 条既有 utterance（turns + utterances，ordinal 1..count，host 开场风格）。
    CG-D 恢复模式/上限 seed：直接落库不写事件（模拟历史数据，seq 不推进）。"""
    for i in range(1, count + 1):
        speaker, role = ("h1", "host") if i == 1 else ("e1", "expert")
        await conn.execute(
            "INSERT INTO turns (id, session_id, sequence, status, selected_participant_id, started_at) "
            "VALUES (?, ?, ?, 'completed', ?, datetime('now'))",
            (f"t{i}", sid, i, speaker),
        )
        await conn.execute(
            "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"u{i}", sid, f"t{i}", speaker, role, f"text{i}", i),
        )
    await conn.commit()


async def _mount(conn, llm=None, registry=None):
    """把测试连接挂到共享 app 上（等价于生产 lifespan 的装配）；llm/registry 可选注入。"""
    main.app.state.conn = conn
    main.app.state.event_store = EventStore(conn)
    if llm is not None:
        main.app.state.llm = llm
    if registry is not None:
        main.app.state.engine_registry = registry


def _restore_state(attr: str, prev) -> None:
    """恢复 app.state 属性为注入前状态（prev None 表示原本不存在——删除之）。"""
    if prev is None:
        try:
            delattr(main.app.state, attr)
        except (AttributeError, KeyError):
            pass
    else:
        setattr(main.app.state, attr, prev)


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")


async def _status(conn) -> str:
    return (await (await conn.execute("SELECT status FROM sessions WHERE id='s1'")).fetchone())[0]


async def _err(conn):
    return (await (await conn.execute("SELECT error_code FROM sessions WHERE id='s1'")).fetchone())[0]


async def _count(conn) -> int:
    return (await (await conn.execute(
        "SELECT COUNT(*) FROM utterances WHERE session_id='s1'"
    )).fetchone())[0]


# ================================================================ D1/D2：host 失败 → paused 迁移

@pytest.mark.asyncio
async def test_host_recoverable_exhausted_pauses_with_triple(conn):
    """host RECOVERABLE 耗尽（retries=0 → 立即上抛）→ 任务停止 + paused 迁移：
    error_code='host_opening_failed'、last_stable_state='live'、零 utterance；
    paused 帧精确 seq 连续（live 命令 seq1 → paused seq2）。"""
    await _seed_ready(conn, "s1")
    store = EventStore(conn)
    q = store.subscribe("s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1", event_store=store)
    engine = DiscussionEngine(
        "s1", FailingProvider(SCRIPT, fail={"host": TimeoutError()}), conn,
        max_turns=3, retries=0, event_store=store,
    )
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert task.exception() is None, "host 失败不得使任务异常结束（必须迁移后返回）"
    assert await _status(conn) == "paused", "host 失败必须迁移 paused（FATAL 才保持不动）"
    assert await _err(conn) == "host_opening_failed"
    lss = (await (await conn.execute(
        "SELECT last_stable_state FROM sessions WHERE id='s1'"
    )).fetchone())[0]
    assert lss == "live", "paused 迁移必须记录可恢复错误三元组（last_stable_state=live）"
    assert await _count(conn) == 0, "开场失败零 utterance"
    f1 = await asyncio.wait_for(q.get(), timeout=2.0)
    f2 = await asyncio.wait_for(q.get(), timeout=2.0)
    assert [f["event"] for f in (f1, f2)] == ["session.state_changed", "session.state_changed"]
    assert f2["data"]["state"] == "paused"
    assert f2["sequence"] == 2, "paused 帧必须精确 seq 连续（命令 seq1 之后）"


@pytest.mark.asyncio
async def test_host_auth_failure_pauses_without_retry(conn):
    """host AUTH（AuthError）→ paused 且调用恰 1 次（AUTH 不重试、无退避；
    默认 retries=3 亦立即上抛）。"""
    await _seed_ready(conn, "s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    provider = FailingProvider(SCRIPT, fail={"host": AuthError("no key")})
    engine = DiscussionEngine("s1", provider, conn, max_turns=3)
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert provider.calls.count("host") == 1, "AUTH 不得重试（恰 1 次调用）"
    assert await _status(conn) == "paused"
    assert await _err(conn) == "host_opening_failed"


# ================================================================ D3：utterance 失败 → paused + 降级记账

@pytest.mark.asyncio
async def test_utterance_failure_pauses_with_failed_turn_and_degrade(conn):
    """utterance SCHEMA 失败（retries=0 立即上抛）→ turn 标 failed + failed_turn_count=1 +
    degraded_components=['utterance'] + session.degraded 帧 + paused 迁移（utterance_generation_failed）；
    帧序精确 [live, host, degraded, paused]（degrade 记账先于 paused 迁移）。"""
    await _seed_ready(conn, "s1")
    store = EventStore(conn)
    q = store.subscribe("s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1", event_store=store)
    engine = DiscussionEngine(
        "s1", FailingProvider(SCRIPT, fail={"utterance": SchemaError("非字符串")}), conn,
        max_turns=3, retries=0, event_store=store,
    )
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert await _status(conn) == "paused"
    assert await _err(conn) == "utterance_generation_failed"
    lss = (await (await conn.execute(
        "SELECT last_stable_state FROM sessions WHERE id='s1'"
    )).fetchone())[0]
    assert lss == "live"
    assert await _count(conn) == 1, "失败轮不得写入 utterance（仅 host 开场）"
    failed_turns = (await (await conn.execute(
        "SELECT COUNT(*) FROM turns WHERE session_id='s1' AND status='failed'"
    )).fetchone())[0]
    assert failed_turns == 1, "失败轮必须落 failed turn（mark_turn_failed）"
    ft, comps = (await (await conn.execute(
        "SELECT failed_turn_count, degraded_components FROM sessions WHERE id='s1'"
    )).fetchone())
    assert ft == 1, "failed_turn_count 必须落库（降级记账）"
    assert json.loads(comps) == ["utterance"], "degraded_components 必须记录 utterance"
    frames = [await asyncio.wait_for(q.get(), timeout=2.0) for _ in range(4)]
    assert [f["event"] for f in frames] == [
        "session.state_changed", "utterance.completed", "session.degraded", "session.state_changed",
    ]
    assert frames[2]["data"]["component"] == "utterance" and frames[2]["data"]["count"] == 1
    assert frames[3]["data"]["state"] == "paused" and frames[3]["sequence"] == 4
    assert [f["sequence"] for f in frames] == [1, 2, 3, 4], "记账/迁移广播 seq 必须精确连续"


# ================================================================ D4/D5/D6：intent/insight 降级继续

@pytest.mark.asyncio
async def test_intent_failure_degrades_to_scheduler_and_continues(conn):
    """intent FATAL（KeyError）→ RuleScheduler 降级**继续**：全部轮次完成、
    used_rule_scheduler_count=max_turns=2、degraded_components=['rule_scheduler']、
    session.degraded 帧 ×2（count 1→2）、无 paused 迁移。"""
    await _seed_ready(conn, "s1")
    store = EventStore(conn)
    q = store.subscribe("s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1", event_store=store)
    engine = DiscussionEngine(
        "s1", FailingProvider(SCRIPT, fail={"intent": KeyError("intent")}), conn,
        max_turns=2, retries=0, event_store=store,
    )
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert await _status(conn) == "live", "intent 降级不得迁移状态（讨论继续）"
    assert await _count(conn) == 3, "全部轮次完成（host + 2 expert）"
    used, comps = (await (await conn.execute(
        "SELECT used_rule_scheduler_count, degraded_components FROM sessions WHERE id='s1'"
    )).fetchone())
    assert used == 2, "每轮 intent 失败必须记账一次"
    assert json.loads(comps) == ["rule_scheduler"], "degraded_components 必须记录（去重）"
    frames = [await asyncio.wait_for(q.get(), timeout=2.0) for _ in range(5)]
    degraded = [f for f in frames if f["event"] == "session.degraded"]
    assert len(degraded) == 2, "每轮降级必须广播 session.degraded"
    assert [d["data"]["count"] for d in degraded] == [1, 2], "降级计数必须递增记账"
    assert all(d["data"]["component"] == "rule_scheduler" for d in degraded)


@pytest.mark.asyncio
async def test_insight_failure_marks_permanently_failed_and_continues(conn):
    """insight RECOVERABLE 耗尽（retries=0）→ utterance 标 permanently_failed +
    permanently_failed_insight_count 落库 + session.degraded 帧，讨论继续（全部轮次完成）。"""
    await _seed_ready(conn, "s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    engine = DiscussionEngine(
        "s1", FailingProvider(SCRIPT, fail={"insight": TimeoutError()}), conn,
        max_turns=2, retries=0,
    )
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert await _status(conn) == "live", "insight 降级不得迁移状态（讨论继续）"
    assert await _count(conn) == 3
    pf = (await (await conn.execute(
        "SELECT COUNT(*) FROM utterances WHERE session_id='s1' AND insight_status='permanently_failed'"
    )).fetchone())[0]
    assert pf == 2, "每轮失败 insight 的 utterance 必须标 permanently_failed"
    n, comps = (await (await conn.execute(
        "SELECT permanently_failed_insight_count, degraded_components FROM sessions WHERE id='s1'"
    )).fetchone())
    assert n == 2
    assert json.loads(comps) == ["insight"]
    insights = (await (await conn.execute(
        "SELECT COUNT(*) FROM insights WHERE session_id='s1'"
    )).fetchone())[0]
    assert insights == 0, "失败轮不得产生 insight 行"


@pytest.mark.asyncio
async def test_insight_schema_invalid_degrades_and_continues(conn):
    """insight 结构非法（create 非 dict）→ 同一降级路径：permanently_failed + 计数 +
    讨论继续（绝不以结构非法中断讨论）。"""
    await _seed_ready(conn, "s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    script = dict(SCRIPT)
    script["insight"] = {"text": "无 create 结构"}
    engine = DiscussionEngine(
        "s1", ScriptedLLMProvider(script), conn, max_turns=1, retries=0,
    )
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert await _status(conn) == "live"
    assert await _count(conn) == 2, "讨论继续（host + 1 expert）"
    pf = (await (await conn.execute(
        "SELECT COUNT(*) FROM utterances WHERE session_id='s1' AND insight_status='permanently_failed'"
    )).fetchone())[0]
    assert pf == 1
    n = (await (await conn.execute(
        "SELECT permanently_failed_insight_count FROM sessions WHERE id='s1'"
    )).fetchone())[0]
    assert n == 1
    insights = (await (await conn.execute(
        "SELECT COUNT(*) FROM insights WHERE session_id='s1'"
    )).fetchone())[0]
    assert insights == 0


# ================================================================ D7/D8：报告降级上下文

@pytest.mark.asyncio
async def test_degraded_session_report_carries_degradation_context(conn):
    """降级会话（intent×2 + insight×2 失败）→ discussion/start（live）→ 引擎降级跑完
    （保持 live）→ discussion/end（finalizing）→ engine.end()（finalize_report）→
    报告落库降级上下文：degraded_components=['rule_scheduler','insight']（去重保序）、
    计数列精确、report_generated_with_degraded_context=1、恰 1 份、completed——
    report 必须从 finalizing 原子迁移 completed（commit_report CAS 前提）。"""
    await _seed_ready(conn, "s1")
    store = EventStore(conn)
    await transactions.execute_command(conn, "s1", "discussion/start", "c1", event_store=store)
    engine = DiscussionEngine(
        "s1", FailingProvider(SCRIPT, fail={"intent": KeyError("intent"), "insight": TimeoutError()}),
        conn, max_turns=2, retries=0, event_store=store,
    )
    await engine.start()
    assert await _status(conn) == "live", "降级期间必须保持 live（intent/insight 降级不迁移）"
    await transactions.execute_command(conn, "s1", "discussion/end", "c2", event_store=store)
    assert await _status(conn) == "finalizing", "end 命令必须先迁移 finalizing（live→finalizing）"
    await engine.end()
    assert await _status(conn) == "completed", "report 必须从 finalizing 原子迁移 completed"
    row = await (await conn.execute(
        "SELECT degraded_components, used_rule_scheduler_count, permanently_failed_insight_count, "
        "failed_turn_count, report_generated_with_degraded_context "
        "FROM discussion_reports WHERE session_id='s1'"
    )).fetchone()
    assert row is not None, "报告必须存在（恰 1 份）"
    comps, used, pf, ft, ctx = row
    assert json.loads(comps) == ["rule_scheduler", "insight"], "降级组件必须去重保序落库"
    assert used == 2 and pf == 2 and ft == 0
    assert ctx == 1, "降级上下文报告必须带标记（finalize 从 DB 构造 Degradation）"
    count = (await (await conn.execute(
        "SELECT COUNT(*) FROM discussion_reports WHERE session_id='s1'"
    )).fetchone())[0]
    assert count == 1


@pytest.mark.asyncio
async def test_clean_session_report_has_zero_degradation_markers(conn):
    """无降级会话 → discussion/start（live）→ 引擎完成 → discussion/end（finalizing）→
    engine.end() → 报告降级标记全零（CG-C 回归防御：finalize 读 DB 构造 Degradation，
    全零 → 零值落库）——report 必须从 finalizing 原子迁移 completed。"""
    await _seed_ready(conn, "s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCRIPT), conn, max_turns=1)
    await engine.start()
    await transactions.execute_command(conn, "s1", "discussion/end", "c2")
    assert await _status(conn) == "finalizing", "end 命令必须先迁移 finalizing（live→finalizing）"
    await engine.end()
    assert await _status(conn) == "completed", "report 必须从 finalizing 原子迁移 completed"
    row = await (await conn.execute(
        "SELECT degraded_components, used_rule_scheduler_count, permanently_failed_insight_count, "
        "failed_turn_count, report_generated_with_degraded_context "
        "FROM discussion_reports WHERE session_id='s1'"
    )).fetchone()
    assert json.loads(row[0]) == [] and row[1] == 0 and row[2] == 0 and row[3] == 0
    assert row[4] == 0, "无降级会话报告不得带降级标记"


# ================================================================ D9/D10/D12：发言上限

@pytest.mark.asyncio
async def test_soft_cap_pauses_with_utterance_cap_reached(conn):
    """软上限：cap=2 → 恰 2 条（host + 1 expert）后停止 + paused +
    error_code='utterance_cap_reached'；paused 帧精确 seq（live1, host2, expert3, paused4）。"""
    await _seed_ready(conn, "s1")
    store = EventStore(conn)
    q = store.subscribe("s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1", event_store=store)
    await conn.execute("UPDATE sessions SET utterance_cap=2 WHERE id='s1'")
    await conn.commit()
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCRIPT), conn, max_turns=5, event_store=store)
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert await _count(conn) == 2, "上限必须精确停在 cap 条（host + 1 expert）"
    assert await _status(conn) == "paused"
    assert await _err(conn) == "utterance_cap_reached", "cap<100 必须用软上限码"
    frames = [await asyncio.wait_for(q.get(), timeout=2.0) for _ in range(4)]
    assert [f["event"] for f in frames] == [
        "session.state_changed", "utterance.completed", "utterance.completed",
        "session.state_changed",
    ]
    assert frames[3]["data"]["state"] == "paused" and frames[3]["sequence"] == 4


@pytest.mark.asyncio
async def test_absolute_cap_pauses_at_100_with_absolute_code(conn):
    """绝对上限：99 条既有 utterance + cap=100 → 恢复模式第 100 条（ordinal 100）落库后
    停止 + paused + error_code='absolute_cap_reached'（cap>=100 用绝对码）。"""
    await _seed_ready(conn, "s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    await conn.execute("UPDATE sessions SET utterance_cap=100 WHERE id='s1'")
    await conn.commit()
    await _seed_utterances(conn, "s1", 99)
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCRIPT), conn, max_turns=3)
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert await _count(conn) == 100, "绝对上限恰停在第 100 条"
    assert await _status(conn) == "paused"
    assert await _err(conn) == "absolute_cap_reached", "cap>=100 必须用绝对上限码"
    last = (await (await conn.execute(
        "SELECT ordinal FROM utterances WHERE session_id='s1' ORDER BY ordinal DESC LIMIT 1"
    )).fetchone())[0]
    assert last == 100, "恢复模式 ordinal 从 count+1 继续（第 100 条）"


@pytest.mark.asyncio
async def test_start_at_cap_pauses_with_zero_new_utterances(conn):
    """启动即停防线：cap=100 + count=100 → start() 零新增 utterance 立即 paused +
    absolute_cap_reached（防不一致状态写入第 101 条）；帧序 [live, paused] 无 utterance 帧。"""
    await _seed_ready(conn, "s1")
    store = EventStore(conn)
    q = store.subscribe("s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1", event_store=store)
    await conn.execute("UPDATE sessions SET utterance_cap=100 WHERE id='s1'")
    await conn.commit()
    await _seed_utterances(conn, "s1", 100)
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCRIPT), conn, max_turns=5, event_store=store)
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert await _count(conn) == 100, "启动即停必须零新增发言"
    assert await _status(conn) == "paused"
    assert await _err(conn) == "absolute_cap_reached"
    f1 = await asyncio.wait_for(q.get(), timeout=2.0)
    f2 = await asyncio.wait_for(q.get(), timeout=2.0)
    assert f1["event"] == "session.state_changed" and f1["data"]["state"] == "live"
    assert f2["event"] == "session.state_changed" and f2["data"]["state"] == "paused"
    assert f2["sequence"] == 2, "paused 帧紧随命令帧（无任何 utterance 广播）"


# ================================================================ D11：恢复模式 ordinal 连续

@pytest.mark.asyncio
async def test_recovery_mode_skips_opening_and_continues_ordinal(conn):
    """恢复模式：3 条既有 utterance → 新引擎 start() → 不开场（无 host 帧）、
    下一轮 expert ordinal=4（不撞 UNIQUE(session_id, ordinal)）。"""
    await _seed_ready(conn, "s1")
    store = EventStore(conn)
    q = store.subscribe("s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1", event_store=store)
    await _seed_utterances(conn, "s1", 3)
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCRIPT), conn, max_turns=1, event_store=store)
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert await _count(conn) == 4, "恢复模式必须继续（不开场、不重复）"
    last = await (await conn.execute(
        "SELECT ordinal, role FROM utterances WHERE session_id='s1' ORDER BY ordinal DESC LIMIT 1"
    )).fetchone()
    assert last[0] == 4 and last[1] == "expert", "下一条必须 ordinal=4 且为 expert（无开场）"
    f1 = await asyncio.wait_for(q.get(), timeout=2.0)
    f2 = await asyncio.wait_for(q.get(), timeout=2.0)
    assert [f["event"] for f in (f1, f2)] == ["session.state_changed", "utterance.completed"]
    assert f2["sequence"] == 2, "恢复模式首帧即专家发言（无开场帧）"


# ================================================================ R1：失败暂停 → resume 重建

@pytest.mark.asyncio
async def test_resume_after_failure_rebuilds_engine_without_cap_increase(conn):
    """R1：失败暂停（utterance_generation_failed）→ resume 按任务存活判别（task done）
    → remove + 重建引擎：恢复模式（count=1 不开场）ordinal 从 2 继续、cap 不加（仍 40）、
    error_code 清空。帧序精确 [live1, host2, degraded3, paused4, live5, expert6] 锁定
    命令/记账/重建顺序；新任务身份必须变化（重建而非复用）。"""
    assert hasattr(transactions, "recover_soft_cap"), "契约：recover_soft_cap（仅软上限 +10）"
    await _seed_ready(conn, "s1")
    gate = asyncio.Event()
    provider = GateProvider(
        FailingProvider(SCRIPT, fail_once={"utterance": SchemaError("非字符串")}), gate
    )
    registry = EngineRegistry()
    prev_llm = getattr(main.app.state, "llm", None)
    prev_registry = getattr(main.app.state, "engine_registry", None)
    await _mount(conn, llm=provider, registry=registry)
    q = main.app.state.event_store.subscribe("s1")
    task = None
    try:
        # —— 第一次引擎：utterance 失败 → 降级记账 + paused ——
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/start", json={"command_id": "c1"})
        assert r.status_code == 202
        task = registry.get_task("s1")
        assert task is not None
        f1 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f1["event"] == "session.state_changed" and f1["data"]["state"] == "live"
        await provider.wait_entered()          # host
        gate.set(); gate.clear()
        f2 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f2["event"] == "utterance.completed" and f2["sequence"] == 2
        await provider.wait_entered()          # round1 intent
        gate.set(); gate.clear()
        await provider.wait_entered()          # round1 utterance（即将失败）
        gate.set(); gate.clear()
        f3 = await asyncio.wait_for(q.get(), timeout=5.0)
        f4 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f3["event"] == "session.degraded" and f3["data"]["component"] == "utterance"
        assert f4["event"] == "session.state_changed" and f4["data"]["state"] == "paused"
        assert f4["sequence"] == 4
        assert await _status(conn) == "paused"
        assert await _err(conn) == "utterance_generation_failed"
        await asyncio.wait_for(task, timeout=5.0)
        assert task.done(), "失败暂停后引擎任务必须确定性完成"

        # —— resume：task done → remove + 重建；恢复模式 ordinal 连续、cap 不加 ——
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/resume", json={"command_id": "c2"})
        assert r.status_code == 202
        f5 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f5["event"] == "session.state_changed" and f5["data"]["state"] == "live"
        assert f5["sequence"] == 5
        new_task = registry.get_task("s1")
        assert new_task is not None and new_task is not task, \
            "task 已 done → 必须重建新任务（任务存活判别，身份变化）"
        await provider.wait_entered()          # 重建引擎 round1 intent（count=1 无 host）
        cap = (await (await conn.execute(
            "SELECT utterance_cap FROM sessions WHERE id='s1'"
        )).fetchone())[0]
        assert cap == 40, "失败暂停 resume 不得增加 cap（仅软上限恢复 +10）"
        err = (await (await conn.execute(
            "SELECT error_code FROM sessions WHERE id='s1'"
        )).fetchone())[0]
        assert err is None, "恢复尝试必须清空 error_code"
        gate.set(); gate.clear()
        await provider.wait_entered()          # utterance（fail_once 已消费 → 成功）
        gate.set(); gate.clear()
        f6 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f6["event"] == "utterance.completed" and f6["sequence"] == 6
        last = await (await conn.execute(
            "SELECT ordinal, role FROM utterances WHERE session_id='s1' ORDER BY ordinal DESC LIMIT 1"
        )).fetchone()
        assert last[0] == 2 and last[1] == "expert", "恢复模式 ordinal 从 count+1 继续"
        await provider.wait_entered()          # insight
        gate.set(); gate.clear()
        await provider.wait_entered()          # round2 intent（卡 gate 收尾）
    finally:
        await registry.stop("s1")              # 兜底：不留后台任务
        _restore_state("llm", prev_llm)
        _restore_state("engine_registry", prev_registry)


# ================================================================ R2/R2b：软上限恢复 cap+10（封顶 100）

async def _seed_paused_cap(conn, sid, cap, error_code, count):
    """软/绝对上限暂停状态 seed：paused + 指定 cap/error_code + count 条既有 utterance。
    不经 start 命令（无引擎任务、无时序竞争）；resume 从 paused→live 直接可用。"""
    await _seed_ready(conn, sid)
    await conn.execute(
        "UPDATE sessions SET status='paused', utterance_cap=?, error_code=? WHERE id=?",
        (cap, error_code, sid),
    )
    await conn.commit()
    await _seed_utterances(conn, sid, count)


@pytest.mark.asyncio
async def test_resume_soft_cap_increases_cap_by_10_and_rebuilds(conn):
    """R2：软上限暂停（cap=39 + utterance_cap_reached）→ resume → cap=49 落库 +
    error_code 清空 + 任务重建（task done → remove + 重建）；恢复模式 ordinal=40 连续。"""
    assert hasattr(transactions, "recover_soft_cap"), "契约：recover_soft_cap（仅软上限 +10）"
    await _seed_paused_cap(conn, "s1", 39, "utterance_cap_reached", 39)
    gate = asyncio.Event()
    provider = GateProvider(ScriptedLLMProvider(SCRIPT), gate)
    registry = EngineRegistry()
    prev_llm = getattr(main.app.state, "llm", None)
    prev_registry = getattr(main.app.state, "engine_registry", None)
    await _mount(conn, llm=provider, registry=registry)
    q = main.app.state.event_store.subscribe("s1")
    try:
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/resume", json={"command_id": "c1"})
        assert r.status_code == 202
        f1 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f1["event"] == "session.state_changed" and f1["data"]["state"] == "live"
        assert f1["sequence"] == 1, "resume 命令事务 seq 精确（seed 无事件）"
        await provider.wait_entered()          # 重建引擎 round1 intent（count=39 无 host）
        cap, err = (await (await conn.execute(
            "SELECT utterance_cap, error_code FROM sessions WHERE id='s1'"
        )).fetchone())
        assert cap == 49, "软上限恢复必须 +10（39→49）"
        assert err is None, "软上限恢复必须清空 error_code"
        assert registry.get_task("s1") is not None, "resume 必须重建并登记新任务"
        gate.set(); gate.clear()
        await provider.wait_entered()          # utterance
        gate.set(); gate.clear()
        f2 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f2["event"] == "utterance.completed" and f2["sequence"] == 2
        last = await (await conn.execute(
            "SELECT ordinal FROM utterances WHERE session_id='s1' ORDER BY ordinal DESC LIMIT 1"
        )).fetchone()
        assert last[0] == 40, "恢复模式 ordinal 从 count+1 继续（39→40）"
        await provider.wait_entered()          # insight
        gate.set(); gate.clear()
        await provider.wait_entered()          # round2 intent（卡 gate 收尾）
    finally:
        await registry.stop("s1")
        _restore_state("llm", prev_llm)
        _restore_state("engine_registry", prev_registry)


@pytest.mark.asyncio
async def test_resume_soft_cap_clamps_at_100(conn):
    """R2b：cap=95 软上限恢复 → cap 封顶 100（MIN(cap+10, 100)，绝不越过绝对上限）。"""
    assert hasattr(transactions, "recover_soft_cap"), "契约：recover_soft_cap"
    await _seed_paused_cap(conn, "s1", 95, "utterance_cap_reached", 95)
    gate = asyncio.Event()
    provider = GateProvider(ScriptedLLMProvider(SCRIPT), gate)
    registry = EngineRegistry()
    prev_llm = getattr(main.app.state, "llm", None)
    prev_registry = getattr(main.app.state, "engine_registry", None)
    await _mount(conn, llm=provider, registry=registry)
    try:
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/resume", json={"command_id": "c1"})
        assert r.status_code == 202
        await provider.wait_entered()          # 重建引擎已进入 intent
        cap = (await (await conn.execute(
            "SELECT utterance_cap FROM sessions WHERE id='s1'"
        )).fetchone())[0]
        assert cap == 100, "cap+10 必须 MIN 封顶 100（95+10→100，非 105）"
    finally:
        await registry.stop("s1")
        _restore_state("llm", prev_llm)
        _restore_state("engine_registry", prev_registry)


# ================================================================ R4：绝对上限不可恢复（命令门禁）

@pytest.mark.asyncio
async def test_resume_absolute_cap_conflict_no_mutation_no_launch(conn):
    """R4：绝对上限暂停（cap=100 + absolute_cap_reached）→ resume 命令门禁 CONFLICT 409：
    status 仍 paused、零新事件、last_event_sequence 不变、零 receipt（门禁先于 receipt）、
    cap 仍 100、error_code 保留、registry 零任务（未启动引擎）；同 command_id 重发仍 409；
    仅 end 可离开（202 finalizing）——finalizing 帧经**先于 end 创建**的订阅队列断言；
    finalize 任务停在 report 调用（gate 未放行），finally 确定性收尾并恢复 app state。"""
    await _seed_paused_cap(conn, "s1", 100, "absolute_cap_reached", 100)
    gate = asyncio.Event()
    provider = GateProvider(ScriptedLLMProvider(SCRIPT), gate)  # gate 不放行：finalizer 卡在 report 调用
    registry = EngineRegistry()
    prev_llm = getattr(main.app.state, "llm", None)
    prev_registry = getattr(main.app.state, "engine_registry", None)
    await _mount(conn, llm=provider, registry=registry)
    q = main.app.state.event_store.subscribe("s1")  # 订阅先于任何命令：end 的 finalizing 帧不丢失
    try:
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/resume", json={"command_id": "c1"})
        assert r.status_code == 409, "绝对上限 resume 必须 409（不可恢复）"
        assert await _status(conn) == "paused", "拒绝不得迁移状态"
        events = (await (await conn.execute(
            "SELECT COUNT(*) FROM events WHERE session_id='s1'"
        )).fetchone())[0]
        assert events == 0, "拒绝不得产生任何事件"
        seq = (await (await conn.execute(
            "SELECT last_event_sequence FROM sessions WHERE id='s1'"
        )).fetchone())[0]
        assert seq == 0, "拒绝不得 bump last_event_sequence"
        receipts = (await (await conn.execute(
            "SELECT COUNT(*) FROM command_receipts WHERE session_id='s1' AND command_id='c1'"
        )).fetchone())[0]
        assert receipts == 0, "门禁先于 receipt：拒绝不得落 receipt（重发重过门禁）"
        cap, err = (await (await conn.execute(
            "SELECT utterance_cap, error_code FROM sessions WHERE id='s1'"
        )).fetchone())
        assert cap == 100, "绝对上限不得 +10"
        assert err == "absolute_cap_reached", "绝对上限 error_code 必须保留"
        assert registry.get_task("s1") is None and registry.get_engine("s1") is None, \
            "拒绝不得启动任何任务（仅 end 可离开）"

        # 同 command_id 重发：仍 409（无 receipt → 重新过门禁）
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/resume", json={"command_id": "c1"})
        assert r.status_code == 409
        seq2 = (await (await conn.execute(
            "SELECT last_event_sequence FROM sessions WHERE id='s1'"
        )).fetchone())[0]
        assert seq2 == 0, "重发拒绝同样零 seq"

        # 仅 end 可离开：finalizing 帧必须到达（订阅队列先于 end 创建，不丢快速广播）
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/end", json={"command_id": "c2"})
        assert r.status_code == 202
        assert await _status(conn) == "finalizing", "绝对上限会话仅 end 可离开（→ finalizing）"
        f = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f["event"] == "session.state_changed" and f["data"]["state"] == "finalizing"
        assert f["sequence"] == 1, "end 命令事务 seq 精确（拒绝零消耗）"
        finalize_task = registry.get_task("s1")
        assert finalize_task is not None and not finalize_task.done(), \
            "end 必须启动 finalize 任务且停在 report 调用（gate 未放行）"
    finally:
        await registry.stop("s1")              # 兜底：取消卡在 report 的 finalize 任务，不留后台任务
        _restore_state("llm", prev_llm)
        _restore_state("engine_registry", prev_registry)


# ================================================================ M1：既有库幂等迁移

@pytest.mark.asyncio
async def test_idempotent_migration_adds_cg_d_columns_to_legacy_db(tmp_path):
    """既有库（无 CG-D 5 列）→ db.init_db → 5 列补齐（DEFAULT 生效：既有行
    utterance_cap=40、计数=0）、数据保留；重复 init_db no-op（列/数据不变、不抛）。"""
    c = await aiosqlite.connect(tmp_path / "legacy.db")
    try:
        # 旧版 sessions 表（当前 schema 去掉 CG-D 5 列）+ 既有行
        await c.executescript(
            "CREATE TABLE sessions ("
            " id TEXT PRIMARY KEY,"
            " topic TEXT NOT NULL,"
            " expert_count INTEGER NOT NULL DEFAULT 4,"
            " status TEXT NOT NULL DEFAULT 'draft',"
            " last_stable_state TEXT,"
            " error_code TEXT,"
            " retry_operation TEXT,"
            " last_event_sequence INTEGER NOT NULL DEFAULT 0,"
            " is_sample INTEGER NOT NULL DEFAULT 0,"
            " created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            " updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ");"
        )
        await c.execute(
            "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'draft')"
        )
        await c.commit()
        await db.init_db(c)
        cols = {row[1] for row in await (await c.execute("PRAGMA table_info(sessions)")).fetchall()}
        for col in ("utterance_cap", "degraded_components", "used_rule_scheduler_count",
                    "failed_turn_count", "permanently_failed_insight_count"):
            assert col in cols, f"迁移必须补齐列 {col}"
        cap, comps, used, ft, pf = (await (await c.execute(
            "SELECT utterance_cap, degraded_components, used_rule_scheduler_count, "
            "failed_turn_count, permanently_failed_insight_count FROM sessions WHERE id='s1'"
        )).fetchone())
        assert cap == 40, "迁移必须带 DEFAULT（既有行 utterance_cap=40）"
        assert comps is None and used == 0 and ft == 0 and pf == 0
        await c.execute("UPDATE sessions SET utterance_cap=50 WHERE id='s1'")
        await c.commit()
        # 重复 init_db：no-op（不抛、列仍在、数据仍在）
        await db.init_db(c)
        cap2 = (await (await c.execute(
            "SELECT utterance_cap FROM sessions WHERE id='s1'"
        )).fetchone())[0]
        assert cap2 == 50, "重复 init_db 不得覆盖既有数据（幂等）"
    finally:
        await c.close()
