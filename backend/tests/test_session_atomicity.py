"""B1/B2/空白 command_id 的 RED 测试（提交阻断审查的后续取证）。

背景：只读审查发现 B1（receipt 与业务效果非原子，register_command 提前独立 COMMIT）
与 B2（门禁读在事务外、commit_event 无条件 UPDATE，并发下状态迁移基于过期状态）。
本文件为修复前的确定性 RED 证据。不修改任何生产代码。

设计说明：
- B1：AFTER INSERT ON events 触发器 RAISE(ABORT) 确定性注入失败——
  精确落在"receipt 已提交、状态/事件写入失败"的崩溃窗口（等价于进程崩溃）。
- B2：StaleStatusConn 可控测试替身——第二个命令的门禁读确定性地返回过期 live。
  真实 HTTP 并发下两个请求交错顺序非确定（end 先提交时旧实现恰好单成功，pause
  先提交时双 202，结果取决于调度），违反"不得碰概率"约束；替身复刻并发窗口的
  最坏交错（两个请求的门禁都基于同一初始 live 通过），与真实并发在数据库层面等价：
  门禁读在事务外、提交内容（无条件 UPDATE + 事件）不含任何状态校验。
- 空白 command_id：契约补充——" " / "   " 必须 422 且零副作用。
  当前 Field(min_length=1) 不 strip，单空格长度 1 会放行进入路由，预期真实 RED。
"""

import json

import httpx
import pytest

from app import main
from app.core.event_store import EventStore

# 与 test_session_contract 相同的 7 个命令路径（独立复制，避免测试文件间耦合）
ALL_PATHS = [
    "panel/generate",
    "panel/confirm",
    "discussion/start",
    "discussion/pause",
    "discussion/resume",
    "discussion/end",
    "retry",
]


async def _mount(conn):
    """把测试连接挂到共享 app 上（等价于生产 lifespan 的装配）。"""
    main.app.state.conn = conn
    main.app.state.event_store = EventStore(conn)


async def _seed(conn, sid, status="draft", topic="t", expert_count=4, created_at=None):
    ts = created_at or "2026-08-30T10:00:00Z"
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (sid, topic, expert_count, status, ts, ts),
    )
    await conn.commit()


async def _client():
    # raise_app_exceptions=False：Starlette 0.38.6 的 ServerErrorMiddleware 在发送 500
    # 响应后总是 re-raise 异常（供 TestClient 调试），httpx 默认会把服务端异常传播到
    # 测试。B1 需要断言 500 响应本身，必须关闭该传播（生产 uvicorn 行为不受影响）。
    transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _events(conn, sid):
    rows = await (
        await conn.execute(
            "SELECT event_type, payload, sequence FROM events WHERE session_id=? ORDER BY sequence",
            (sid,),
        )
    ).fetchall()
    return [(r[0], json.loads(r[1]), r[2]) for r in rows]


# ---------------------------------------------------------------- B1：receipt 与业务效果原子性

@pytest.mark.asyncio
async def test_b1_mid_transaction_failure_leaves_no_receipt_or_effect(conn):
    """事件写入阶段注入确定性失败：首次请求必须失败，且 receipt/状态/事件零残留。

    正确行为（GREEN 目标）：receipt 注册与业务效果同一事务——任一失败整体回滚。
    当前实现：register_command 提前独立 COMMIT，receipt 残留。
    """
    await _mount(conn)
    await _seed(conn, "s1", status="ready")
    # 注入：events 表任何 INSERT 都失败（发生在 commit_event 的最后一步）
    await conn.execute(
        "CREATE TRIGGER fail_event_insert AFTER INSERT ON events "
        "BEGIN SELECT RAISE(ABORT, 'injected: event write failure'); END"
    )
    await conn.commit()
    try:
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/start", json={"command_id": "cmd-b1"})
    finally:
        await conn.execute("DROP TRIGGER IF EXISTS fail_event_insert")
        await conn.commit()
    # 首次请求必须失败，不能报告成功
    assert r.status_code == 500
    # 失败后：receipt 不存在（当前实现：register_command 已独立提交 → 残留 1 条）
    receipts = await (
        await conn.execute(
            "SELECT COUNT(*) FROM command_receipts WHERE session_id='s1' AND command_id='cmd-b1'"
        )
    ).fetchone()
    assert receipts[0] == 0, (
        "receipt 已提前独立提交（register_command 在 commit_event 之前单独 COMMIT），"
        "崩溃窗口成立：重试将永远 202 而无业务效果"
    )
    # 状态 / sequence / 事件均未变化
    row = await (
        await conn.execute("SELECT status, last_event_sequence FROM sessions WHERE id='s1'")
    ).fetchone()
    assert row[0] == "ready"
    assert row[1] == 0
    assert await _events(conn, "s1") == []


@pytest.mark.asyncio
async def test_b1_retry_same_command_id_applies_effect_once(conn):
    """清理故障后重试同一 command_id：202 + 恰好一次迁移 + 一条事件 + sequence 连续。

    正确行为（GREEN 目标）：首次失败整体回滚 → 重试走完整路径执行效果。
    当前实现：receipt 残留 → 幂等短路 → 重试 202 但状态/事件永远缺失。
    """
    await _mount(conn)
    await _seed(conn, "s1", status="ready")
    # 首次：注入失败（无副作用残留）
    await conn.execute(
        "CREATE TRIGGER fail_event_insert AFTER INSERT ON events "
        "BEGIN SELECT RAISE(ABORT, 'injected: event write failure'); END"
    )
    await conn.commit()
    async with await _client() as c:
        await c.post("/sessions/s1/discussion/start", json={"command_id": "cmd-b1"})
    await conn.execute("DROP TRIGGER IF EXISTS fail_event_insert")
    await conn.commit()
    # 重试：同 command_id
    async with await _client() as c:
        r = await c.post("/sessions/s1/discussion/start", json={"command_id": "cmd-b1"})
    assert r.status_code == 202
    row = await (
        await conn.execute("SELECT status, last_event_sequence FROM sessions WHERE id='s1'")
    ).fetchone()
    assert row[0] == "live", (
        "重试必须真正执行状态迁移（当前：首次失败残留的 receipt 命中幂等短路，"
        "202 但效果永久缺失，会话停留在 ready）"
    )
    assert row[1] == 1  # sequence 恰好 +1（连续）
    events = await _events(conn, "s1")
    assert [(e[0], e[2]) for e in events] == [("session.state_changed", 1)]
    assert events[0][1]["state"] == "live"
    receipts = await (
        await conn.execute(
            "SELECT COUNT(*) FROM command_receipts WHERE session_id='s1' AND command_id='cmd-b1'"
        )
    ).fetchone()
    assert receipts[0] == 1  # 恰好一条


# ---------------------------------------------------------------- B2：并发状态迁移保护

class _StaleStatusCursor:
    """伪造门禁读结果：(status, retry_operation, error_code)。"""

    def __init__(self, status: str, retry_operation: str | None = None,
                 error_code: str | None = None):
        self._status = status
        self._retry_operation = retry_operation
        self._error_code = error_code

    async def fetchone(self):
        return (self._status, self._retry_operation, self._error_code)


class _StaleStatusConn:
    """可控测试替身：仅拦截 _apply_command 的门禁读（SELECT status FROM sessions），
    返回过期 live；其余 SQL 全部透传真实连接。

    复刻并发窗口：两个请求的门禁都基于同一初始 live 通过（第二个请求读到的是
    第一个请求提交前的事务外快照），随后第二个请求以无条件 UPDATE 覆盖提交。
    与真实并发在数据库层面完全等价——提交内容不含任何状态校验。
    """

    def __init__(self, real, stale_status: str):
        self._real = real
        self._stale = stale_status

    async def execute(self, sql, parameters=None):
        # 事务入口的状态读为 "SELECT status, retry_operation FROM sessions ..."
        if sql.startswith("SELECT status") and " FROM sessions" in sql:
            return _StaleStatusCursor(self._stale, None)
        return await self._real.execute(sql, parameters)

    async def commit(self):
        return await self._real.commit()

    async def rollback(self):
        return await self._real.rollback()


@pytest.mark.asyncio
async def test_b2_concurrent_pause_end_one_winner(conn):
    """并发 pause+end（同一初始 live）：只能一个 202，另一个必须因状态已变化 409。

    正确行为（GREEN 目标）：提交时校验状态未变化（expected_state 条件更新），
    过期状态提交被拒 → 单 receipt、单事件、sequence 仅 +1，终态 = 成功命令的 paused。
    当前实现：第二个命令基于过期 live 通过门禁并无条件覆盖提交 → 双 202、双事件、
    receipt×2、sequence+2。
    """
    await _mount(conn)
    await _seed(conn, "s1", status="live")
    main.app.state.conn = _StaleStatusConn(conn, "live")
    try:
        async with await _client() as c:
            r1 = await c.post("/sessions/s1/discussion/pause", json={"command_id": "cmd-p"})
            r2 = await c.post("/sessions/s1/discussion/end", json={"command_id": "cmd-e"})
    finally:
        main.app.state.conn = conn
    assert r1.status_code == 202  # pause 成功：live → paused
    assert r2.status_code == 409, (
        "第二个命令必须因状态已变化被拒（当前：基于过期 live 的门禁通过后，"
        "commit_event 无条件覆盖提交，产生本应互斥的第二次迁移）"
    )
    row = await (
        await conn.execute("SELECT status, last_event_sequence FROM sessions WHERE id='s1'")
    ).fetchone()
    assert row[0] == "paused"  # 终态 = 唯一成功命令（pause）的结果
    assert row[1] == 1  # last_event_sequence 只增加 1
    events = await _events(conn, "s1")
    assert len(events) == 1
    assert events[0][1]["state"] == "paused"
    receipts = await (
        await conn.execute("SELECT COUNT(*) FROM command_receipts WHERE session_id='s1'")
    ).fetchone()
    assert receipts[0] == 1  # 只新增一条 receipt


# ---------------------------------------------------------------- 空白 command_id 契约补充

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,blank", [(p, b) for p in ALL_PATHS for b in (" ", "   ")]
)
async def test_command_blank_command_id_422_no_side_effects(conn, path, blank):
    """契约补充：空白 command_id 必须 422，且零副作用（无 receipt / 状态不变 / 无事件）。

    当前实现：Field(min_length=1) 不 strip，" "（长度 1）放行进入路由 → 202 或 409，
    非 422 → 有效 RED，指向 schemas.py 缺少 strip。
    """
    await _mount(conn)
    await _seed(conn, "s1", status="ready")
    async with await _client() as c:
        r = await c.post(f"/sessions/s1/{path}", json={"command_id": blank})
    assert r.status_code == 422
    # 422 必须零副作用
    receipts = await (
        await conn.execute("SELECT COUNT(*) FROM command_receipts WHERE session_id='s1'")
    ).fetchone()
    assert receipts[0] == 0
    row = await (await conn.execute("SELECT status FROM sessions WHERE id='s1'")).fetchone()
    assert row[0] == "ready"
    assert await _events(conn, "s1") == []
