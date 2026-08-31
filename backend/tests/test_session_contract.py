"""T0.1 会话契约测试（RED 阶段）：POST/GET /sessions + 7 个命令端点。

契约（用户批准的最小契约，测试即验收）：
- POST /sessions：201 + {session_id, topic, expert_count, status: draft, created_at}；
  按事件模型写入一条 session.state_changed（state=draft）；topic 非空、expert_count 2–6（规格 §line75）；
  客户端不得指定 session_id/status/created_at。
- GET /sessions：200 + {sessions: [...]}；多会话隔离；按 created_at 确定性排序；不泄露内部字段。
- 命令端点：合法状态 + 合法 command_id → 202；重复 command_id 幂等（返回第一次原结果、单条 receipt）；
  会话不存在 → 404；缺失/非法 command_id → 422；按状态机 TRANSITIONS 执行门禁（违例 → 409）。

仅新增测试文件；不修改任何生产代码；不修改/弱化现有测试。
"""

import json
from datetime import datetime

import httpx
import pytest

from app import main
from app.core.engine_registry import EngineRegistry
from app.core.event_store import EventStore
from app.llm.fake import FakeLLMProvider

# 命令 → 合法状态（按 state_machine.TRANSITIONS 推导）
VALID_STATES = [
    ("panel/generate", "draft"),  # draft → panel_generating
    ("panel/confirm", "panel_ready"),  # panel_ready → ready
    ("discussion/start", "ready"),  # ready → live
    ("discussion/pause", "live"),  # live → paused
    ("discussion/resume", "paused"),  # paused → live
    ("discussion/end", "live"),  # live → finalizing
]
# 命令 → 违例状态（同一命令专属违例，不用同一 fixture 掩盖不同命令的状态要求）
# resume 的违例是 live（自环非法，TRANSITIONS[LIVE] 不含 LIVE；ready→live 与 start 同构，合法）
INVALID_STATES = [
    ("panel/generate", "live"),
    ("panel/confirm", "draft"),
    ("discussion/start", "draft"),
    ("discussion/pause", "ready"),
    ("discussion/resume", "live"),
    ("discussion/end", "ready"),
]
ALL_PATHS = [p for p, _ in VALID_STATES] + ["retry"]


async def _mount(conn):
    """把测试连接挂到共享 app 上（等价于生产 lifespan 的装配）；返回 registry 供调用方收尾。"""
    main.app.state.conn = conn
    main.app.state.event_store = EventStore(conn)
    main.app.state.engine_registry = EngineRegistry()
    main.app.state.llm = FakeLLMProvider()  # discussion/start 启动引擎需要 llm
    return main.app.state.engine_registry


async def _seed(conn, sid, status="draft", topic="t", expert_count=4, created_at=None):
    """显式 created_at 保证排序测试确定性（schema 默认 datetime('now') 为秒级，两次插入可能同值）。"""
    ts = created_at or "2026-08-30T10:00:00Z"
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (sid, topic, expert_count, status, ts, ts),
    )
    await conn.commit()


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")


async def _events(conn, sid):
    rows = await (
        await conn.execute(
            "SELECT event_type, payload, sequence FROM events WHERE session_id=? ORDER BY sequence",
            (sid,),
        )
    ).fetchall()
    return [(r[0], json.loads(r[1]), r[2]) for r in rows]


# ---------------------------------------------------------------- POST /sessions

@pytest.mark.asyncio
async def test_post_sessions_201_contract_fields(conn):
    await _mount(conn)
    async with await _client() as c:
        r = await c.post("/sessions", json={"topic": "AI 与社会", "expert_count": 3})
    assert r.status_code == 201
    body = r.json()
    assert set(body.keys()) == {"session_id", "topic", "expert_count", "status", "created_at"}
    assert body["topic"] == "AI 与社会"
    assert body["expert_count"] == 3
    assert body["status"] == "draft"
    assert body["session_id"]  # 服务器生成
    assert body["created_at"]  # 服务器生成


@pytest.mark.asyncio
async def test_post_sessions_created_at_is_iso8601(conn):
    await _mount(conn)
    async with await _client() as c:
        r = await c.post("/sessions", json={"topic": "t", "expert_count": 3})
    assert r.status_code == 201
    created_at = r.json()["created_at"]
    # SQLite datetime('now') 为 "YYYY-MM-DD HH:MM:SS"，响应必须是 ISO-8601（T/Z）
    datetime.fromisoformat(created_at.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_post_sessions_persists_draft_and_state_changed_event(conn):
    await _mount(conn)
    async with await _client() as c:
        r = await c.post("/sessions", json={"topic": "AI 与社会", "expert_count": 3})
    sid = r.json()["session_id"]
    row = await (
        await conn.execute(
            "SELECT status, expert_count, last_event_sequence FROM sessions WHERE id=?", (sid,)
        )
    ).fetchone()
    assert row is not None
    assert row[0] == "draft"
    assert row[1] == 3
    assert row[2] == 1  # 创建事件已递增
    events = await _events(conn, sid)
    assert [(e[0], e[2]) for e in events] == [("session.state_changed", 1)]
    payload = events[0][1]
    assert payload["state"] == "draft"
    assert set(payload.keys()) <= {"state", "prev_state", "error_code"}


@pytest.mark.asyncio
async def test_post_sessions_rejects_empty_topic(conn):
    await _mount(conn)
    async with await _client() as c:
        r = await c.post("/sessions", json={"topic": "", "expert_count": 3})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_sessions_rejects_missing_topic(conn):
    await _mount(conn)
    async with await _client() as c:
        r = await c.post("/sessions", json={"expert_count": 3})
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("expert_count", [0, 1, 7, 100])
async def test_post_sessions_rejects_out_of_range_expert_count(conn, expert_count):
    """规格 §line75：专家人数范围 2–6。"""
    await _mount(conn)
    async with await _client() as c:
        r = await c.post("/sessions", json={"topic": "t", "expert_count": expert_count})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_sessions_ignores_client_controlled_fields(conn):
    """客户端不得指定 session_id / status / created_at：服务器生成值生效。"""
    await _mount(conn)
    async with await _client() as c:
        r = await c.post(
            "/sessions",
            json={
                "topic": "t",
                "expert_count": 3,
                "session_id": "client-picked",
                "status": "completed",
                "created_at": "1999-01-01T00:00:00Z",
            },
        )
    assert r.status_code == 201
    body = r.json()
    assert body["session_id"] != "client-picked"
    assert body["status"] == "draft"
    assert body["created_at"] != "1999-01-01T00:00:00Z"


# ---------------------------------------------------------------- GET /sessions

@pytest.mark.asyncio
async def test_get_sessions_200_wrapped_and_isolated(conn):
    await _mount(conn)
    await _seed(conn, "s1", created_at="2026-08-30T10:00:00Z")
    await _seed(conn, "s2", status="live", topic="话题 B", expert_count=5, created_at="2026-08-30T11:00:00Z")
    async with await _client() as c:
        r = await c.get("/sessions")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"sessions"}
    items = body["sessions"]
    assert len(items) == 2
    by_id = {it["session_id"]: it for it in items}
    assert set(by_id.keys()) == {"s1", "s2"}
    # 字段与内部数据一致且互不串扰
    assert set(by_id["s1"].keys()) == {"session_id", "topic", "expert_count", "status", "created_at"}
    assert by_id["s1"] == {
        "session_id": "s1",
        "topic": "t",
        "expert_count": 4,
        "status": "draft",
        "created_at": "2026-08-30T10:00:00Z",
    }
    assert by_id["s2"]["topic"] == "话题 B"
    assert by_id["s2"]["expert_count"] == 5
    assert by_id["s2"]["status"] == "live"


@pytest.mark.asyncio
async def test_get_sessions_no_internal_fields_leak(conn):
    """响应条目不得泄露内部数据库字段。"""
    await _mount(conn)
    await _seed(conn, "s1", status="failed", created_at="2026-08-30T10:00:00Z")
    await conn.execute(
        "UPDATE sessions SET error_code='fatal', last_stable_state='live', retry_operation='x', "
        "last_event_sequence=7, is_sample=1 WHERE id='s1'"
    )
    await conn.commit()
    async with await _client() as c:
        r = await c.get("/sessions")
    assert r.status_code == 200
    item = r.json()["sessions"][0]
    assert set(item.keys()) == {"session_id", "topic", "expert_count", "status", "created_at"}


@pytest.mark.asyncio
async def test_get_sessions_stable_ordering_by_created_at(conn):
    """列表顺序稳定：两次请求一致，且与 created_at 排序一致（方向由实现确定，任一方向即稳定）。"""
    await _mount(conn)
    await _seed(conn, "s1", created_at="2026-08-30T10:00:00Z")
    await _seed(conn, "s2", created_at="2026-08-30T09:00:00Z")  # s2 更早
    await _seed(conn, "s3", created_at="2026-08-30T11:00:00Z")  # s3 最晚
    async with await _client() as c:
        first = (await c.get("/sessions")).json()["sessions"]
        second = (await c.get("/sessions")).json()["sessions"]
    first_ids = [it["session_id"] for it in first]
    assert first_ids == [it["session_id"] for it in second]
    created = {it["session_id"]: it["created_at"] for it in first}
    assert first_ids == sorted(first_ids, key=lambda sid: created[sid]) or first_ids == sorted(
        first_ids, key=lambda sid: created[sid], reverse=True
    )


# ---------------------------------------------------------------- 命令端点

@pytest.mark.asyncio
async def test_delete_session_removes_session_and_related_events(conn):
    registry = await _mount(conn)
    async with await _client() as c:
        created = await c.post("/sessions", json={"topic": "待删除", "expert_count": 3})
        sid = created.json()["session_id"]
        response = await c.delete(f"/sessions/{sid}")
    assert response.status_code == 204
    assert await (await conn.execute("SELECT 1 FROM sessions WHERE id=?", (sid,))).fetchone() is None
    assert (await (await conn.execute("SELECT COUNT(*) FROM events WHERE session_id=?", (sid,))).fetchone())[0] == 0
    assert registry.get_engine(sid) is None


@pytest.mark.asyncio
async def test_delete_session_unknown_returns_404(conn):
    await _mount(conn)
    async with await _client() as c:
        response = await c.delete("/sessions/nope")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("path,valid_state", VALID_STATES)
async def test_command_202_in_valid_state(conn, path, valid_state):
    registry = await _mount(conn)  # start/end 会真启动引擎 task，须在同 loop 内收尾
    try:
        await _seed(conn, "s1", status=valid_state)
        async with await _client() as c:
            r = await c.post(f"/sessions/s1/{path}", json={"command_id": "cmd-1"})
        assert r.status_code == 202
    finally:
        await registry.shutdown()


@pytest.mark.asyncio
async def test_command_end_202_from_paused(conn):
    """discussion/end 在 live 与 paused 均合法（TRANSITIONS[PAUSED] 含 FINALIZING）。"""
    registry = await _mount(conn)
    try:
        await _seed(conn, "s1", status="paused")
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/end", json={"command_id": "cmd-1"})
        assert r.status_code == 202
    finally:
        await registry.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("path,invalid_state", INVALID_STATES)
async def test_command_gate_violation_409(conn, path, invalid_state):
    """状态门禁按 state_machine.TRANSITIONS：违例拒绝（409），且各命令违例状态各不相同。"""
    await _mount(conn)
    await _seed(conn, "s1", status=invalid_state)
    async with await _client() as c:
        r = await c.post(f"/sessions/s1/{path}", json={"command_id": "cmd-1"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_retry_202_with_pending_retry_operation(conn):
    """retry 仅在存在待重试操作（retry_operation 非空）时合法。"""
    await _mount(conn)
    await _seed(conn, "s1", status="draft")
    await conn.execute(
        "UPDATE sessions SET retry_operation='panel/generate', error_code='upstream_error' WHERE id='s1'"
    )
    await conn.commit()
    async with await _client() as c:
        r = await c.post("/sessions/s1/retry", json={"command_id": "cmd-r"})
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_retry_gate_violation_without_retry_operation(conn):
    await _mount(conn)
    await _seed(conn, "s1", status="live")
    async with await _client() as c:
        r = await c.post("/sessions/s1/retry", json={"command_id": "cmd-r"})
    assert r.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ALL_PATHS)
async def test_command_404_unknown_session(conn, path):
    await _mount(conn)
    async with await _client() as c:
        r = await c.post(f"/sessions/nope/{path}", json={"command_id": "cmd-1"})
    assert r.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ALL_PATHS)
async def test_command_missing_command_id_422(conn, path):
    await _mount(conn)
    await _seed(conn, "s1")
    async with await _client() as c:
        r = await c.post(f"/sessions/s1/{path}", json={})
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ALL_PATHS)
async def test_command_empty_command_id_422(conn, path):
    await _mount(conn)
    await _seed(conn, "s1")
    async with await _client() as c:
        r = await c.post(f"/sessions/s1/{path}", json={"command_id": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_command_id_idempotent(conn):
    """重复 command_id：返回第一次的原结果（202），不产生第二条 receipt。"""
    registry = await _mount(conn)  # start 会真启动引擎 task，须在同 loop 内收尾
    try:
        await _seed(conn, "s1", status="ready")
        async with await _client() as c:
            first = await c.post("/sessions/s1/discussion/start", json={"command_id": "cmd-dup"})
            second = await c.post("/sessions/s1/discussion/start", json={"command_id": "cmd-dup"})
        assert first.status_code == 202
        assert second.status_code == 202
    finally:
        await registry.shutdown()
    rows = await (
        await conn.execute(
            "SELECT COUNT(*) FROM command_receipts WHERE session_id='s1' AND command_id='cmd-dup'"
        )
    ).fetchone()
    assert rows[0] == 1
