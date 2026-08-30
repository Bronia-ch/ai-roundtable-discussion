import asyncio
import json
import os

import httpx
import pytest
import uvicorn

from app import main
from app.core import transactions
from app.core.engine_registry import EngineRegistry
from app.core.event_store import EventStore
from app.llm.fake import ScriptedLLMProvider
from app.llm.openai_compat import OpenAICompatProvider


ENGINE_SCRIPT = {
    "host": {"text": "欢迎来到圆桌讨论"},
    "intent": {"items": [{"participant_id": "e1", "intent_type": "answer", "willingness": 0.9}]},
    "utterance": {"text": "我认为这个观点值得探讨"},
    "insight": {"create": {"kind": "focus", "text": "AI 红利分配"}},
}


class GateProvider:
    """测试门控 provider（与 test_engine.GateLLMProvider 同契约，路由级测试局部定义）：
    每次 generate 先 set entered、再等待 gate；wait_entered 配对消费（后 clear）。
    每步放行前 wait_entered 确认引擎已实际进入对应 gate——无 sleep、无时序碰巧。"""

    def __init__(self, inner: ScriptedLLMProvider, gate: asyncio.Event):
        self.inner = inner
        self.gate = gate
        self.entered = asyncio.Event()

    async def generate(self, call_type: str, system: str, user: str):
        self.entered.set()
        await self.gate.wait()
        return await self.inner.generate(call_type, system, user)

    async def wait_entered(self, timeout: float = 2.0) -> None:
        """等待 engine 进入下一次 generate 调用（进入即 set；本次尚未被放行）。"""
        await asyncio.wait_for(self.entered.wait(), timeout=timeout)
        self.entered.clear()


async def _mount(conn, llm=None, registry=None):
    """把测试连接挂到共享 app 上（等价于生产 lifespan 的装配）；
    llm/registry 可选注入（CG-B 接线测试用；既有测试默认 None 不受影响）。
    注入过的测试必须在 finally 中经 _restore_state 恢复 app.state，避免污染其他测试。"""
    main.app.state.conn = conn
    main.app.state.event_store = EventStore(conn)
    if llm is not None:
        main.app.state.llm = llm
    if registry is not None:
        main.app.state.engine_registry = registry


def _restore_state(attr: str, prev) -> None:
    """恢复 app.state 属性为注入前状态（prev None 表示原本不存在——删除之）。
    Starlette State 的 __delattr__ 对缺失键抛 KeyError（非 AttributeError），一并捕获。"""
    if prev is None:
        try:
            delattr(main.app.state, attr)
        except (AttributeError, KeyError):
            pass
    else:
        setattr(main.app.state, attr, prev)


async def _seed(conn, sid):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, 't', 4, 'live')", (sid,)
    )
    await conn.commit()


async def _seed_ready(conn, sid):
    """discussion/start 的合法前置：会话处于 ready（state_machine.py:29 READY→LIVE）+ 1 host + 2 expert。
    （panel_ready 无 LIVE 出边，直接 start 会 409；本测试不模拟 confirm 两步流程。）"""
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


@pytest.fixture
async def live_server(tmp_path):
    """本地回环 uvicorn（随机端口）：真实 lifespan + 路由；启动/超时/关闭/端口回收全兜底。
    LLM 隔离：SQLite 走 tmp_path；API key 清空 + base_url 指向不可达回环地址——即使 .env
    存在真实 key 也绝不向真实 DeepSeek 地址发起网络请求；退出时保存/恢复原环境变量。"""
    db_path = tmp_path / "live.db"
    saved = {k: os.environ.get(k) for k in ("LLM_SQLITE_PATH", "LLM_API_KEY", "LLM_BASE_URL")}
    os.environ.update(
        LLM_SQLITE_PATH=str(db_path),
        LLM_API_KEY="",
        LLM_BASE_URL="http://127.0.0.1:9/v1",  # 不可达回环：任何误发请求立即连接失败
    )
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
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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


@pytest.mark.asyncio
async def test_discussion_start_applied_launches_engine_task(conn):
    """CG-B 接线契约：discussion/start 首次 APPLIED 后，路由启动引擎后台任务并登记到
    engine_registry——命令事务零 utterance，落库只能来自引擎任务。

    订阅先于 POST：快速 host 广播不丢失。精确顺序断言覆盖接线顺序——
    第 1 帧必须是本次命令的 session.state_changed(live)，其后才是引擎 utterance。
    收尾：registry.stop 确定性收尾（finally 兜底），绝不留后台任务。"""
    assert hasattr(EngineRegistry, "get_task"), "契约：EngineRegistry.get_task(session_id)"
    assert hasattr(EngineRegistry, "stop"), "契约：EngineRegistry.stop(session_id)"
    await _seed_ready(conn, "s1")
    llm = ScriptedLLMProvider(ENGINE_SCRIPT)
    registry = EngineRegistry()
    prev_llm = getattr(main.app.state, "llm", None)
    prev_registry = getattr(main.app.state, "engine_registry", None)
    await _mount(conn, llm=llm, registry=registry)
    q = main.app.state.event_store.subscribe("s1")  # 订阅先于命令——不丢快速广播
    task = None
    try:
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/start", json={"command_id": "c1"})
        assert r.status_code == 202
        task = registry.get_task("s1")
        assert task is not None, "路由必须把引擎任务登记到 engine_registry"
        # 精确顺序：本次命令的 state_changed(live) 必须先于引擎任何 utterance 广播
        first = await asyncio.wait_for(q.get(), timeout=5.0)
        assert first["event"] == "session.state_changed", "命令状态事件必须先于引擎 utterance"
        assert first["data"]["state"] == "live"
        second = await asyncio.wait_for(q.get(), timeout=5.0)
        assert second["event"] == "utterance.completed", "引擎第一条 utterance 紧随命令广播"
        count = (
            await (await conn.execute("SELECT COUNT(*) FROM utterances WHERE session_id='s1'")).fetchone()
        )[0]
        assert count >= 1, "引擎任务必须写入 utterance（命令事务零 utterance）"
    finally:
        await registry.stop("s1")  # 兜底：不留后台任务（无登记/已 done 为 no-op）
        _restore_state("llm", prev_llm)
        _restore_state("engine_registry", prev_registry)
    assert task is not None and task.done(), "registry.stop 后任务必须确定性完成"


@pytest.mark.asyncio
async def test_pause_resume_end_routes_signal_engine(conn):
    """CG-B 接线：discussion/pause/resume/end 路由把状态迁移与引擎信号接线。

    门控 provider 提供确定性同步（与 test_engine 同契约）：每步放行前 wait_entered
    确认引擎已进入对应 gate——无 sleep、无时序碰巧。帧顺序断言同时覆盖每个命令
    的 state_changed 先于其后的引擎 utterance。resume 为手动软暂停（error_code
    NULL）：不得增加 utterance_cap（仅软上限恢复 +10，CG-D）。收尾：end 路由
    确定性收尾引擎任务；finally 兜底 registry.stop，绝不留后台任务。"""
    assert hasattr(EngineRegistry, "get_task"), "契约：EngineRegistry.get_task(session_id)"
    assert hasattr(EngineRegistry, "stop"), "契约：EngineRegistry.stop(session_id)"
    await _seed_ready(conn, "s1")
    gate = asyncio.Event()
    provider = GateProvider(ScriptedLLMProvider(ENGINE_SCRIPT), gate)
    registry = EngineRegistry()
    prev_llm = getattr(main.app.state, "llm", None)
    prev_registry = getattr(main.app.state, "engine_registry", None)
    await _mount(conn, llm=provider, registry=registry)
    q = main.app.state.event_store.subscribe("s1")  # 订阅先于任何命令
    task = None

    def release() -> None:
        gate.set()
        gate.clear()

    async def finish_round(first_in_flight: bool) -> None:
        """放行一整轮（共 3 次调用）；首个在途时先放行，再等待/放行余下 2 次；
        放行总数恒为 3，绝不等待或放行到下一轮。"""
        if first_in_flight:
            release()
        for _ in range(2 if first_in_flight else 3):
            await provider.wait_entered()
            release()

    async def _status() -> str:
        return (
            await (await conn.execute("SELECT status FROM sessions WHERE id='s1'")).fetchone()
        )[0]

    try:
        # —— start：state_changed(live) 先于引擎广播；引擎卡在 host gate ——
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/start", json={"command_id": "c1"})
        assert r.status_code == 202
        task = registry.get_task("s1")
        assert task is not None, "路由必须把引擎任务登记到 engine_registry"
        f1 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f1["event"] == "session.state_changed" and f1["data"]["state"] == "live"
        await provider.wait_entered()          # 引擎已进入 host 调用（卡 gate）
        release()
        f2 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f2["event"] == "utterance.completed", "host 开场必须广播"
        await provider.wait_entered()          # 已进入 round1 intent（卡 gate）

        # —— pause：live→paused；round1 在途轮收尾后引擎停在下一轮检查点 ——
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/pause", json={"command_id": "c2"})
        assert r.status_code == 202
        assert await _status() == "paused"
        f3 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f3["event"] == "session.state_changed" and f3["data"]["state"] == "paused"
        await finish_round(first_in_flight=True)   # round1 在途轮收尾（intent 已确认进入）
        f4 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f4["event"] == "utterance.completed", "在途轮收尾后 expert 帧必须到达"
        release()                                  # 放行 round2 intent——引擎停在检查点
        with pytest.raises(asyncio.TimeoutError):
            await provider.wait_entered(timeout=0.5)

        # —— resume：paused→live；引擎恢复，round2 完成 ——
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/resume", json={"command_id": "c3"})
        assert r.status_code == 202
        assert await _status() == "live"
        f5 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f5["event"] == "session.state_changed" and f5["data"]["state"] == "live"
        cap = (await (await conn.execute(
            "SELECT utterance_cap FROM sessions WHERE id='s1'"
        )).fetchone())[0]
        assert cap == 40, "手动软暂停（error_code NULL）resume 不得增加 cap（仅软上限恢复 +10，CG-D）"
        await finish_round(first_in_flight=False)  # round2：等待/放行 3 次
        f6 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f6["event"] == "utterance.completed"
        await provider.wait_entered()              # 已进入 round3 intent（卡 gate）

        # —— end：live→finalizing；引擎任务确定性收尾 ——
        async with await _client() as c:
            r = await c.post("/sessions/s1/discussion/end", json={"command_id": "c4"})
        assert r.status_code == 202
        assert await _status() == "finalizing"
        f7 = await asyncio.wait_for(q.get(), timeout=5.0)
        assert f7["event"] == "session.state_changed" and f7["data"]["state"] == "finalizing"
        await asyncio.wait_for(task, timeout=5.0)
        assert task.done(), "end 后引擎任务必须被确定性收尾"
    finally:
        await registry.stop("s1")                  # 兜底：不留后台任务
        _restore_state("llm", prev_llm)
        _restore_state("engine_registry", prev_registry)


@pytest.mark.asyncio
async def test_live_server_lifespan_isolated_llm_and_registry(live_server):
    """CG-B 接线：lifespan 装配 engine_registry 与 llm 注入点；隔离 env 下 provider
    base_url 指向不可达回环、API key 为空——任何误发请求立即失败，绝不触达真实 DeepSeek。"""
    url, _ = live_server
    assert hasattr(main.app.state, "engine_registry"), "契约：lifespan 装配 engine_registry"
    llm = main.app.state.llm
    assert isinstance(llm, OpenAICompatProvider), "契约：lifespan 装配 OpenAICompatProvider"
    assert llm.settings.api_key == "", "隔离：live_server 下 API key 必须为空"
    assert llm.settings.base_url == "http://127.0.0.1:9/v1", "隔离：base_url 必须指向不可达回环地址"
