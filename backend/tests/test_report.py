"""CG-C RED：finalizing 报告生成与 retry 语义恢复（§5.1 行 128-130 + §10.4 阶梯 6 + §10.1）。

契约：
- 可达时序：ready --discussion/start--> live --discussion/end--> finalizing
  --engine.end()/finalize_report--> completed（commit_report 单事务：报告行 + completed
  迁移 + 清空错误三元组 + 事件 + 精确 seq 广播）。
- 失败（LLM 异常/结构非法）→ 滞留 finalizing + error_code/retry_operation='report' +
  error.recoverable（绝不误标 completed）；安全重试只重放失败操作（retry 命令 + 路由分派）。
- 幂等：discussion_reports UNIQUE(session_id) 重复生成仅一份；retry 同 command_id → DUPLICATE。
- "report" 命令在 finalizing 下自迁移滞留（receipt + 事件），其余状态 CONFLICT。

当前实现：end() 仅 stop、无 finalize_report、_COMMANDS 无 "report"、路由无分派 →
全部失败（有效 RED：行为缺失 / hasattr 能力缺失守卫）。
"""

import asyncio
import json

import httpx
import pytest

from app import main
from app.core import engine as engine_module
from app.core import transactions
from app.core.engine import DiscussionEngine
from app.core.engine_registry import EngineRegistry
from app.core.event_store import EventStore
from app.core.transactions import CommandOutcome
from app.llm.fake import ScriptedLLMProvider


SUCCESS_SCRIPT = {
    "host": {"text": "欢迎来到圆桌讨论"},
    "intent": {"items": [{"participant_id": "e1", "intent_type": "answer", "willingness": 0.9}]},
    "utterance": {"text": "我认为这个观点值得探讨"},
    "insight": {"create": {"kind": "focus", "text": "AI 红利分配"}},
    "report": {"summary": "讨论完成", "key_consensus": ["共识一"]},
}
# report 键缺失 → KeyError → classify_error 判 FATAL（call_with_retry 立即抛出，无退避等待）
NO_REPORT_SCRIPT = {
    "host": {"text": "欢迎来到圆桌讨论"},
    "intent": {"items": [{"participant_id": "e1", "intent_type": "answer", "willingness": 0.9}]},
    "utterance": {"text": "我认为这个观点值得探讨"},
    "insight": {"create": {"kind": "focus", "text": "AI 红利分配"}},
}
# 结构非法：summary 非字符串 → SchemaError（SCHEMA 不重试，立即抛出）
SCHEMA_SCRIPT = {"report": {"summary": 123}}


class GateProvider:
    """测试门控 provider（与 test_routes.GateProvider 同契约，本文件局部定义）：
    每次 generate 先 set entered、再等待 gate；wait_entered 配对消费（后 clear）。
    每步放行前 wait_entered 确认任务已实际进入对应 gate——无 sleep、无时序碰巧。"""

    def __init__(self, inner: ScriptedLLMProvider, gate: asyncio.Event):
        self.inner = inner
        self.gate = gate
        self.entered = asyncio.Event()

    async def generate(self, call_type: str, system: str, user: str):
        self.entered.set()
        await self.gate.wait()
        return await self.inner.generate(call_type, system, user)

    async def wait_entered(self, timeout: float = 2.0) -> None:
        """等待任务进入下一次 generate 调用（进入即 set；本次尚未被放行）。"""
        await asyncio.wait_for(self.entered.wait(), timeout=timeout)
        self.entered.clear()


async def _seed_ready(conn, sid):
    """discussion/start 的合法前置：ready + 1 host + 2 expert（与 test_routes._seed_ready 同构）。"""
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


async def _seed_finalizing(conn, sid="s1"):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, 't', 4, 'finalizing')", (sid,)
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


async def _report_summary(conn):
    row = await (
        await conn.execute("SELECT summary FROM discussion_reports WHERE session_id='s1'")
    ).fetchone()
    return row[0] if row is not None else None


# ---------------- T1：可达时序 end → completed + 恰 1 份报告 + 精确 seq 广播 ----------------

@pytest.mark.asyncio
async def test_end_reaches_completed_with_single_report(conn):
    """可达时序：ready --start--> live --end--> finalizing --engine.end()--> completed；
    帧序 [live, finalizing, completed] 精确连续（seq 1/2/3）；summary 直接落库（非 JSON 包装）。"""
    await _seed_ready(conn, "s1")
    store = EventStore(conn)
    q = store.subscribe("s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1", event_store=store)
    await transactions.execute_command(conn, "s1", "discussion/end", "c2", event_store=store)
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SUCCESS_SCRIPT), conn, event_store=store)
    await engine.end()
    frames = [await asyncio.wait_for(q.get(), timeout=2.0) for _ in range(3)]
    assert [f["event"] for f in frames] == [
        "session.state_changed", "session.state_changed", "session.state_changed",
    ]
    assert [f["data"]["state"] for f in frames] == ["live", "finalizing", "completed"]
    assert [f["sequence"] for f in frames] == [1, 2, 3], "命令与 report 广播 seq 必须精确连续"
    assert await _status(conn) == "completed"
    assert await _report_summary(conn) == "讨论完成", "summary 必须直接落库（非 JSON 包装）"
    count = (
        await (await conn.execute("SELECT COUNT(*) FROM discussion_reports WHERE session_id='s1'")).fetchone()
    )[0]
    assert count == 1, "finalizing 收尾恰 1 份报告"


# ---------------- T2：LLM 失败 → 滞留 finalizing + 三元组 + error.recoverable ----------------

@pytest.mark.asyncio
async def test_finalize_llm_failure_stays_finalizing_with_retry_triple(conn):
    """LLM FATAL（report 键缺失 → KeyError）→ 滞留 finalizing + 错误三元组 +
    error.recoverable 事件广播；绝不误标 completed；零报告行。"""
    await _seed_finalizing(conn)
    store = EventStore(conn)
    q = store.subscribe("s1")
    engine = DiscussionEngine("s1", ScriptedLLMProvider(NO_REPORT_SCRIPT), conn, event_store=store)
    await engine.end()
    assert await _status(conn) == "finalizing", "失败必须滞留 finalizing（绝不误标 completed）"
    err, retry_op = (
        await (await conn.execute(
            "SELECT error_code, retry_operation FROM sessions WHERE id='s1'"
        )).fetchone()
    )
    assert err == "report_generation_failed"
    assert retry_op == "report", "必须记录可恢复错误三元组供安全重试"
    frame = await asyncio.wait_for(q.get(), timeout=2.0)
    assert frame["event"] == "error.recoverable"
    assert frame["sequence"] == 1, "失败事件必须精确 seq 广播"
    assert frame["data"]["error_code"] == "report_generation_failed"
    assert frame["data"]["retry_operation"] == "report"
    assert frame["data"]["scope"] == "report"
    count = (
        await (await conn.execute("SELECT COUNT(*) FROM discussion_reports WHERE session_id='s1'")).fetchone()
    )[0]
    assert count == 0, "失败不得产生报告行"


# ---------------- T3：结构非法（summary 非 str）→ 同一滞留路径 ----------------

@pytest.mark.asyncio
async def test_finalize_schema_invalid_stays_finalizing(conn):
    """结构非法（summary 非字符串）→ SchemaError（SCHEMA 不重试）→ 同一滞留路径。"""
    await _seed_finalizing(conn)
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCHEMA_SCRIPT), conn)
    await engine.end()
    assert await _status(conn) == "finalizing"
    err, retry_op = (
        await (await conn.execute(
            "SELECT error_code, retry_operation FROM sessions WHERE id='s1'"
        )).fetchone()
    )
    assert err == "report_generation_failed"
    assert retry_op == "report"


# ---------------- T4a：commit_report 清空三元组 + 幂等（重复重试仅一份报告） ----------------

@pytest.mark.asyncio
async def test_commit_report_idempotent_and_clears_error_triple(conn):
    """commit_report 契约：报告行 + completed 迁移 + 清空错误三元组原子；重复调用幂等
    （UNIQUE(session_id)：不重复迁移、不重复事件、恰 1 份报告）。"""
    assert hasattr(transactions, "commit_report"), "契约：commit_report（报告行+completed+清空三元组）"
    assert hasattr(transactions, "mark_report_failed"), "契约：mark_report_failed（滞留+三元组）"
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status, error_code, retry_operation) "
        "VALUES ('s1', 't', 4, 'finalizing', 'report_generation_failed', 'report')"
    )
    await conn.commit()
    seq = await transactions.commit_report(
        conn, "s1", {"summary": "讨论完成"}, '{"summary": "讨论完成"}', None
    )
    assert seq == 1
    assert await _status(conn) == "completed"
    err, retry_op = (
        await (await conn.execute(
            "SELECT error_code, retry_operation FROM sessions WHERE id='s1'"
        )).fetchone()
    )
    assert err is None, "重试成功的报告必须清空 error_code"
    assert retry_op is None, "重试成功的报告必须清空 retry_operation"
    assert await _report_summary(conn) == "讨论完成"
    dup = await transactions.commit_report(
        conn, "s1", {"summary": "讨论完成"}, '{"summary": "讨论完成"}', None
    )
    assert dup == 0, "幂等重放返回 0（不重复迁移）"
    count = (
        await (await conn.execute("SELECT COUNT(*) FROM discussion_reports WHERE session_id='s1'")).fetchone()
    )[0]
    assert count == 1, "重复生成仅一份报告（UNIQUE(session_id)）"
    changed = (
        await (await conn.execute(
            "SELECT COUNT(*) FROM events WHERE session_id='s1' AND event_type='session.state_changed' "
            "AND payload LIKE '%completed%'"
        )).fetchone()
    )[0]
    assert changed == 1, "completed 迁移只发生一次"


# ---------------- T4b：commit_report CAS 守卫（失败不留行） ----------------

@pytest.mark.asyncio
async def test_commit_report_cas_failure_leaves_no_report_row(conn):
    """CAS 守卫：状态已离开 finalizing（live）时 commit_report 不得迁移、不得留下 report 行。"""
    assert hasattr(transactions, "commit_report"), "契约：commit_report"
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'live')"
    )
    await conn.commit()
    outcome = await transactions.commit_report(
        conn, "s1", {"summary": "讨论完成"}, '{"summary": "讨论完成"}', None
    )
    assert outcome is None, "CAS 失败必须返回 None"
    assert await _status(conn) == "live", "CAS 失败不得迁移状态"
    count = (
        await (await conn.execute("SELECT COUNT(*) FROM discussion_reports WHERE session_id='s1'")).fetchone()
    )[0]
    assert count == 0, "CAS 失败不得留下新 report 行（整体回滚）"


# ---------------- T5/T6："report" 命令自迁移滞留 + 门禁 ----------------

@pytest.mark.asyncio
async def test_report_command_applied_on_finalizing_self_migration(conn):
    """retry 目标命令 "report"：finalizing 下 APPLIED 且状态原地不动（自迁移滞留），
    receipt 与 state_changed(finalizing) 事件落库；同 command_id 重放 → DUPLICATE 不递增 seq。"""
    await _seed_finalizing(conn)
    store = EventStore(conn)
    q = store.subscribe("s1")
    outcome = await transactions.execute_command(conn, "s1", "report", "c1", event_store=store)
    assert outcome is CommandOutcome.APPLIED, "finalizing 下 report 命令必须 APPLIED（滞留重试）"
    assert await _status(conn) == "finalizing", "report 命令不得迁移状态（滞留）"
    seq = (await (await conn.execute(
        "SELECT last_event_sequence FROM sessions WHERE id='s1'"
    )).fetchone())[0]
    assert seq == 1, "滞留命令仍递增 seq（receipt + 事件）"
    frame = await asyncio.wait_for(q.get(), timeout=2.0)
    assert frame["event"] == "session.state_changed" and frame["data"]["state"] == "finalizing"
    receipt = await (
        await conn.execute(
            "SELECT 1 FROM command_receipts WHERE session_id='s1' AND command_id='c1'"
        )
    ).fetchone()
    assert receipt is not None, "report 命令必须落 receipt（幂等）"
    dup = await transactions.execute_command(conn, "s1", "report", "c1", event_store=store)
    assert dup is CommandOutcome.DUPLICATE
    seq2 = (await (await conn.execute(
        "SELECT last_event_sequence FROM sessions WHERE id='s1'"
    )).fetchone())[0]
    assert seq2 == 1, "DUPLICATE 不递增 seq"


@pytest.mark.asyncio
async def test_report_command_conflict_when_not_finalizing(conn):
    """非 finalizing（ready）下 report 命令 → CONFLICT（滞留命令门禁）。"""
    await _seed_ready(conn, "s1")
    outcome = await transactions.execute_command(conn, "s1", "report", "c1")
    assert outcome is CommandOutcome.CONFLICT, "非 finalizing 下 report 命令必须 CONFLICT"


# ---------------- T7：end 路由启动 finalize 任务 → completed ----------------

@pytest.mark.asyncio
async def test_end_route_launches_finalize_task_to_completed(conn):
    """路由级可达时序：start 放行 host 后卡 round1 intent → end POST（finalizing）→
    引擎任务确定性收尾 → 路由启动 finalize 任务（登记 registry、独立于引擎任务）→
    放行 report gate → completed 帧 + 报告落库。"""
    assert hasattr(engine_module, "finalize_report"), "契约：engine.finalize_report 执行体"
    await _seed_ready(conn, "s1")
    gate = asyncio.Event()
    provider = GateProvider(ScriptedLLMProvider(SUCCESS_SCRIPT), gate)
    registry = EngineRegistry()
    prev_llm = getattr(main.app.state, "llm", None)
    prev_registry = getattr(main.app.state, "engine_registry", None)
    await _mount(conn, llm=provider, registry=registry)
    q = main.app.state.event_store.subscribe("s1")
    task = None
    try:
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/start", json={"command_id": "c1"})
        assert r.status_code == 202
        task = registry.get_task("s1")
        assert task is not None, "路由必须把引擎任务登记到 engine_registry"
        f1 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f1["event"] == "session.state_changed" and f1["data"]["state"] == "live"
        await provider.wait_entered()          # 引擎已进入 host 调用（卡 gate）
        gate.set()
        gate.clear()
        f2 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f2["event"] == "utterance.completed", "host 开场必须广播"
        await provider.wait_entered()          # 已进入 round1 intent（卡 gate）

        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/end", json={"command_id": "c2"})
        assert r.status_code == 202
        assert await _status(conn) == "finalizing"
        f3 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f3["event"] == "session.state_changed" and f3["data"]["state"] == "finalizing"
        await asyncio.wait_for(task, timeout=5.0)
        assert task.done(), "end 后引擎任务必须被确定性收尾"

        finalize_task = registry.get_task("s1")
        assert finalize_task is not None, "end 路由必须启动并登记 finalize 任务"
        assert finalize_task is not task, "finalize 任务必须独立于引擎任务"
        await provider.wait_entered()          # finalize 已进入 report 调用（卡 gate）
        gate.set()
        gate.clear()
        f4 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f4["event"] == "session.state_changed" and f4["data"]["state"] == "completed"
        assert f4["sequence"] == 4, "completed 帧必须精确 seq 连续"
        await asyncio.wait_for(finalize_task, timeout=5.0)
        assert finalize_task.done()
        assert await _status(conn) == "completed"
        assert await _report_summary(conn) == "讨论完成"
    finally:
        await registry.stop("s1")              # 兜底：不留后台任务
        _restore_state("llm", prev_llm)
        _restore_state("engine_registry", prev_registry)


# ---------------- T8：retry 路由按 retry_operation 分派，恢复后 completed ----------------

@pytest.mark.asyncio
async def test_retry_route_regenerates_report_after_failure(conn):
    """失败滞留 → retry 命令（自迁移滞留事件）→ 路由按 retry_operation='report' 分派新的
    finalize 任务 → 恢复后成功 completed；报告仍恰 1 份；绝无误标 completed。"""
    assert hasattr(engine_module, "finalize_report"), "契约：engine.finalize_report 执行体"
    await _seed_ready(conn, "s1")
    script = dict(NO_REPORT_SCRIPT)            # 可变脚本：失败后注入 report 键恢复
    gate = asyncio.Event()
    provider = GateProvider(ScriptedLLMProvider(script), gate)
    registry = EngineRegistry()
    prev_llm = getattr(main.app.state, "llm", None)
    prev_registry = getattr(main.app.state, "engine_registry", None)
    await _mount(conn, llm=provider, registry=registry)
    q = main.app.state.event_store.subscribe("s1")
    task = None
    try:
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/start", json={"command_id": "c1"})
        assert r.status_code == 202
        task = registry.get_task("s1")
        assert task is not None
        f1 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f1["event"] == "session.state_changed" and f1["data"]["state"] == "live"
        await provider.wait_entered()
        gate.set()
        gate.clear()
        f2 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f2["event"] == "utterance.completed"
        await provider.wait_entered()          # 已进入 round1 intent（卡 gate）

        # —— end：finalizing；finalize 任务失败（脚本无 report）→ 滞留 + 三元组 + 事件 ——
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/end", json={"command_id": "c2"})
        assert r.status_code == 202
        f3 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f3["event"] == "session.state_changed" and f3["data"]["state"] == "finalizing"
        await asyncio.wait_for(task, timeout=5.0)
        assert task.done()
        finalize_task = registry.get_task("s1")
        assert finalize_task is not None, "end 路由必须启动并登记 finalize 任务"
        await provider.wait_entered()          # finalize 进入 report 调用（卡 gate）
        gate.set()
        gate.clear()
        f4 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f4["event"] == "error.recoverable"
        assert f4["data"]["error_code"] == "report_generation_failed"
        assert f4["data"]["retry_operation"] == "report"
        await asyncio.wait_for(finalize_task, timeout=5.0)
        assert await _status(conn) == "finalizing", "失败必须滞留 finalizing"
        err, retry_op = (
            await (await conn.execute(
                "SELECT error_code, retry_operation FROM sessions WHERE id='s1'"
            )).fetchone()
        )
        assert err == "report_generation_failed"
        assert retry_op == "report"

        # —— retry：自迁移滞留事件；分派新 finalize；恢复后成功 ——
        script["report"] = {"summary": "讨论完成"}   # 注入恢复脚本（同一 dict 引用）
        async with await _client() as c:
            r = await c.post("/sessions/s1/retry", json={"command_id": "c3"})
        assert r.status_code == 202
        f5 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f5["event"] == "session.state_changed" and f5["data"]["state"] == "finalizing"
        await provider.wait_entered()          # 新 finalize 进入 report 调用（卡 gate）
        gate.set()
        gate.clear()
        f6 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f6["event"] == "session.state_changed" and f6["data"]["state"] == "completed"
        await asyncio.wait_for(registry.get_task("s1"), timeout=5.0)
        assert await _status(conn) == "completed"
        assert await _report_summary(conn) == "讨论完成"
        count = (
            await (await conn.execute("SELECT COUNT(*) FROM discussion_reports WHERE session_id='s1'")).fetchone()
        )[0]
        assert count == 1, "重试成功仍恰 1 份报告（UNIQUE 幂等）"
    finally:
        await registry.stop("s1")
        _restore_state("llm", prev_llm)
        _restore_state("engine_registry", prev_registry)


# ---------------- T9：重复 retry command_id 幂等 ----------------

@pytest.mark.asyncio
async def test_retry_idempotent_same_command_id(conn):
    """重复 retry command_id：第二次命中 receipt → DUPLICATE 202，不重复分派 finalize、
    不递增 seq、不产生新帧；报告恒 0 份、状态仍滞留 finalizing。"""
    assert hasattr(engine_module, "finalize_report"), "契约：engine.finalize_report 执行体"
    await _seed_ready(conn, "s1")
    gate = asyncio.Event()
    provider = GateProvider(ScriptedLLMProvider(NO_REPORT_SCRIPT), gate)
    registry = EngineRegistry()
    prev_llm = getattr(main.app.state, "llm", None)
    prev_registry = getattr(main.app.state, "engine_registry", None)
    await _mount(conn, llm=provider, registry=registry)
    q = main.app.state.event_store.subscribe("s1")
    task = None
    try:
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/start", json={"command_id": "c1"})
        assert r.status_code == 202
        task = registry.get_task("s1")
        assert task is not None
        f1 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f1["event"] == "session.state_changed" and f1["data"]["state"] == "live"
        await provider.wait_entered()
        gate.set()
        gate.clear()
        f2 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f2["event"] == "utterance.completed"
        await provider.wait_entered()          # 已进入 round1 intent（卡 gate）

        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/end", json={"command_id": "c2"})
        assert r.status_code == 202
        f3 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f3["event"] == "session.state_changed" and f3["data"]["state"] == "finalizing"
        await asyncio.wait_for(task, timeout=5.0)
        assert task.done()
        assert registry.get_task("s1") is not None, "end 路由必须启动并登记 finalize 任务"
        await provider.wait_entered()
        gate.set()
        gate.clear()
        f4 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f4["event"] == "error.recoverable"   # 首次 finalize 失败滞留
        await asyncio.wait_for(registry.get_task("s1"), timeout=5.0)

        # —— 首次 retry：APPLIED（自迁移滞留事件）+ 新 finalize 再失败 ——
        async with await _client() as c:
            r = await c.post("/sessions/s1/retry", json={"command_id": "c3"})
        assert r.status_code == 202
        f5 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f5["event"] == "session.state_changed" and f5["data"]["state"] == "finalizing"
        await provider.wait_entered()
        gate.set()
        gate.clear()
        f6 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f6["event"] == "error.recoverable"   # 重试分派再次失败
        await asyncio.wait_for(registry.get_task("s1"), timeout=5.0)
        seq_before = (await (await conn.execute(
            "SELECT last_event_sequence FROM sessions WHERE id='s1'"
        )).fetchone())[0]
        assert seq_before == 6

        # —— 重复 retry 同 command_id：DUPLICATE 202，纯 no-op ——
        async with await _client() as c:
            r = await c.post("/sessions/s1/retry", json={"command_id": "c3"})
        assert r.status_code == 202, "重复 retry command_id 必须仍返回 202（幂等）"
        assert await _status(conn) == "finalizing", "DUPLICATE 不得改变状态"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(q.get(), timeout=0.5)   # 缺席断言：无新广播
        seq_after = (await (await conn.execute(
            "SELECT last_event_sequence FROM sessions WHERE id='s1'"
        )).fetchone())[0]
        assert seq_after == seq_before, "DUPLICATE 不递增 seq"
        receipts = (
            await (await conn.execute(
                "SELECT COUNT(*) FROM command_receipts WHERE session_id='s1' AND command_id='c3'"
            )).fetchone()
        )[0]
        assert receipts == 1, "同 command_id 只落一次 receipt"
        count = (
            await (await conn.execute("SELECT COUNT(*) FROM discussion_reports WHERE session_id='s1'")).fetchone()
        )[0]
        assert count == 0, "失败重试期间报告恒 0 份"
    finally:
        await registry.stop("s1")
        _restore_state("llm", prev_llm)
        _restore_state("engine_registry", prev_registry)
