import asyncio
import json
import os

import httpx
import pytest
import uvicorn

from app import main
from app.core import transactions
from app.core.event_store import EventStore


async def _mount(conn):
    """把测试连接挂到共享 app 上（等价于生产 lifespan 的装配）。"""
    main.app.state.conn = conn
    main.app.state.event_store = EventStore(conn)


async def _seed(conn, sid):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, 't', 4, 'live')", (sid,)
    )
    await conn.commit()


@pytest.fixture
async def live_server(tmp_path):
    """本地回环 uvicorn（随机端口）：真实 lifespan + 路由；启动/超时/关闭/端口回收全兜底。"""
    db_path = tmp_path / "live.db"
    os.environ["LLM_SQLITE_PATH"] = str(db_path)
    config = uvicorn.Config(
        "app.main:app", host="127.0.0.1", port=0, log_level="warning", lifespan="on"
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        try:
            await asyncio.wait_for(_await_started(server), timeout=10)
        except asyncio.TimeoutError:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=5)
            raise RuntimeError("uvicorn 未在 10s 内完成启动")
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}", db_path
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
        os.environ.pop("LLM_SQLITE_PATH", None)


async def _await_started(server) -> None:
    while not server.started:
        await asyncio.sleep(0.02)


async def _frames(resp, expected: int) -> list[dict]:
    """从 SSE 响应中解析出 expected 个完整帧（id/event/data）。"""
    frames = []
    current = {}
    async for line in resp.aiter_lines():
        if line.startswith("id: "):
            current["sequence"] = int(line[4:])
        elif line.startswith("event: "):
            current["event"] = line[7:]
        elif line.startswith("data: "):
            current["data"] = json.loads(line[6:])
        elif line == "" and current:
            frames.append(current)
            current = {}
            if len(frames) == expected:
                break
    return frames


async def _client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    )


@pytest.mark.asyncio
async def test_snapshot_route_returns_state_and_last_sequence(conn):
    await _seed(conn, "s1")
    await transactions.commit_event(
        conn, "s1", "session.state_changed", {"state": "live"}, {"status": "live"}
    )
    await _mount(conn)
    async with await _client() as c:
        r = await c.get("/sessions/s1")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s1"
    assert body["status"] == "live"
    assert body["last_sequence"] == 1
    assert body["transcript"] == []
    assert body["insights"] == []


@pytest.mark.asyncio
async def test_snapshot_route_404_unknown_session(conn):
    await _mount(conn)
    async with await _client() as c:
        r = await c.get("/sessions/nope")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_events_route_streams_replay_frames(live_server):
    import aiosqlite
    from app import db

    url, db_path = live_server
    conn = await aiosqlite.connect(db_path)
    try:
        await db.init_db(conn)
        await _seed(conn, "s1")
        await transactions.commit_event(conn, "s1", "utterance.completed", {"utterance_id": "u1"}, {})
        async with httpx.AsyncClient(base_url=url, timeout=5.0) as c:
            async with c.stream("GET", "/sessions/s1/events") as r:
                assert r.status_code == 200
                assert r.headers["content-type"].startswith("text/event-stream")
                frames = await _frames(r, 1)
    finally:
        await conn.close()
    assert frames[0]["sequence"] == 1
    assert frames[0]["event"] == "utterance.completed"
    assert frames[0]["data"]["data"]["utterance_id"] == "u1"


@pytest.mark.asyncio
async def test_events_route_404_unknown_session(conn):
    await _mount(conn)
    async with await _client() as c:
        async with c.stream("GET", "/sessions/nope/events") as r:
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_events_route_takes_max_of_after_seq_and_last_event_id(live_server):
    import aiosqlite
    from app import db

    url, db_path = live_server
    conn = await aiosqlite.connect(db_path)
    try:
        await db.init_db(conn)
        await _seed(conn, "s1")
        for name in ("a", "b", "c"):
            await transactions.commit_event(conn, "s1", "x", {"n": name}, {})
        async with httpx.AsyncClient(base_url=url, timeout=5.0) as c:
            async with c.stream(
                "GET",
                "/sessions/s1/events",
                params={"after_seq": "1"},
                headers={"last-event-id": "2"},
            ) as r:
                frames = await _frames(r, 1)
    finally:
        await conn.close()
    assert [f["sequence"] for f in frames] == [3]
    assert frames[0]["data"]["data"]["n"] == "c"


@pytest.mark.asyncio
async def test_events_route_last_event_id_alone(live_server):
    import aiosqlite
    from app import db

    url, db_path = live_server
    conn = await aiosqlite.connect(db_path)
    try:
        await db.init_db(conn)
        await _seed(conn, "s1")
        for name in ("a", "b", "c"):
            await transactions.commit_event(conn, "s1", "x", {"n": name}, {})
        async with httpx.AsyncClient(base_url=url, timeout=5.0) as c:
            async with c.stream(
                "GET", "/sessions/s1/events", headers={"last-event-id": "2"}
            ) as r:
                frames = await _frames(r, 1)
    finally:
        await conn.close()
    assert [f["sequence"] for f in frames] == [3]


@pytest.mark.asyncio
async def test_recovery_snapshot_then_sse_replay(live_server):
    """断线恢复循环（HTTP 端到端）：取快照 → 快照后间隙事件 → 以 last_sequence 续订只收更大序号。"""
    import aiosqlite
    from app import db

    url, db_path = live_server
    conn = await aiosqlite.connect(db_path)
    try:
        await db.init_db(conn)
        await _seed(conn, "s1")
        await transactions.commit_event(conn, "s1", "a", {}, {})
        async with httpx.AsyncClient(base_url=url, timeout=5.0) as c:
            snap = (await c.get("/sessions/s1")).json()
            assert snap["last_sequence"] == 1
            # 快照→建连间隙提交的事件 2、3
            await transactions.commit_event(conn, "s1", "b", {}, {})
            await transactions.commit_event(conn, "s1", "c", {}, {})
            async with c.stream(
                "GET", "/sessions/s1/events", params={"after_seq": snap["last_sequence"]}
            ) as r:
                frames = await _frames(r, 2)
    finally:
        await conn.close()
    assert [f["sequence"] for f in frames] == [2, 3]
