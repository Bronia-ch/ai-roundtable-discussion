import asyncio
import json

import pytest

from app.api.sse import _sse_format, resolve_after_seq, sse_stream
from app.core import transactions
from app.core.event_store import EventStore


class MockRequest:
    def __init__(self):
        self._disconnected = False

    async def is_disconnected(self):
        return self._disconnected


class SettableRequest:
    def __init__(self):
        self.disconnected = False

    async def is_disconnected(self):
        return self.disconnected


class GappedEventStore:
    """确定性模拟 replay 查询期间提交的间隙事件：

    仅在"已订阅"时把间隙事件入队（真实实现中提交即广播）；
    因此当前实现（先 replay 后 subscribe）会丢失间隙事件，修复（先订阅再重放）不会。
    """

    def __init__(self, replay_rows, gap_events):
        self.replay_rows = replay_rows
        self.gap_events = gap_events
        self.queue = asyncio.Queue()
        self.subscribed = False

    def subscribe(self, session_id):
        self.subscribed = True
        return self.queue

    def unsubscribe(self, session_id, q):
        self.subscribed = False

    async def replay(self, session_id, after_seq):
        for ev in self.gap_events:
            if self.subscribed:
                await self.queue.put(dict(ev))
        return [dict(e) for e in self.replay_rows]


def _env(sequence):
    return {
        "event": "x",
        "sequence": sequence,
        "schema_version": 1,
        "session_id": "s1",
        "timestamp": "t",
        "data": {},
    }


def _seq(frame):
    for line in frame.splitlines():
        if line.startswith("id: "):
            return int(line[4:])
    return None


def test_resolve_after_seq_takes_max():
    assert resolve_after_seq("5", "3") == 5
    assert resolve_after_seq("3", "5") == 5


def test_resolve_after_seq_single_source():
    assert resolve_after_seq(None, "7") == 7
    assert resolve_after_seq("7", None) == 7


def test_resolve_after_seq_default_zero():
    assert resolve_after_seq(None, None) == 0


def test_resolve_after_seq_tolerates_malformed():
    # 畸形 after_seq：忽略该输入，不抛异常
    assert resolve_after_seq("abc", None) == 0
    assert resolve_after_seq("abc", "2") == 2
    # 畸形 Last-Event-ID：忽略该输入
    assert resolve_after_seq(None, "xyz") == 0
    assert resolve_after_seq("5", "xyz") == 5
    # 两者都畸形
    assert resolve_after_seq("abc", "xyz") == 0
    # 负数钳制到 0
    assert resolve_after_seq("-3", None) == 0


def test_sse_format_frame():
    envelope = {
        "event": "utterance.completed",
        "sequence": 5,
        "session_id": "s1",
        "schema_version": 1,
        "timestamp": "t",
        "data": {"text": "hi"},
    }
    frame = _sse_format(envelope)
    assert "id: 5\n" in frame
    assert "event: utterance.completed\n" in frame
    data_line = frame.split("data: ", 1)[1].split("\n", 1)[0]
    parsed = json.loads(data_line)
    assert parsed["sequence"] == 5
    assert parsed["data"] == {"text": "hi"}


@pytest.mark.asyncio
async def test_heartbeat_emitted(conn):
    store = EventStore(conn)
    req = MockRequest()
    gen = sse_stream(req, store, "s1", 0, heartbeat_interval=0.01)
    first = await gen.__anext__()
    assert "heartbeat" in first
    await gen.aclose()


async def _seed(conn, sid):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, 't', 4, 'live')", (sid,)
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_replay_uses_confirmed_sequence(conn):
    await _seed(conn, "s1")
    await transactions.commit_event(conn, "s1", "a", {}, {})
    await transactions.commit_event(conn, "s1", "b", {}, {})
    await transactions.commit_event(conn, "s1", "c", {}, {})
    store = EventStore(conn)
    confirmed = resolve_after_seq("1", "2")
    assert confirmed == 2
    rows = await store.replay("s1", confirmed)
    assert [r["sequence"] for r in rows] == [3]


@pytest.mark.asyncio
async def test_replay_without_subscribers(conn):
    await _seed(conn, "s1")
    await transactions.commit_event(conn, "s1", "a", {}, {})
    store = EventStore(conn)  # 无订阅者
    rows = await store.replay("s1", 0)
    assert [r["sequence"] for r in rows] == [1]


@pytest.mark.asyncio
async def test_disconnect_does_not_cancel_production(conn):
    await _seed(conn, "s1")
    store = EventStore(conn)
    q = store.subscribe("s1")
    store.unsubscribe("s1", q)  # 客户端断开
    await transactions.commit_event(conn, "s1", "x", {}, {})  # 生产不停止
    rows = await store.replay("s1", 0)
    assert [r["sequence"] for r in rows] == [1]


@pytest.mark.asyncio
async def test_gap_event_between_replay_and_subscribe_not_lost():
    """replay 与 subscribe 之间的间隙事件不能永久丢失：先订阅再重放，间隙事件经队列送达。"""
    store = GappedEventStore(replay_rows=[_env(1), _env(2)], gap_events=[_env(3), _env(4)])
    req = SettableRequest()

    async def consume():
        frames = []
        async for frame in sse_stream(req, store, "s1", 0, heartbeat_interval=0.01):
            frames.append(frame)
            if len(frames) == 4:
                req.disconnected = True
        return frames

    frames = await asyncio.wait_for(consume(), timeout=3)
    assert [_seq(f) for f in frames] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_gap_event_replayed_and_queued_not_duplicated():
    """间隙事件同时出现在 replay 结果与队列时只发送一次（按 sequence 跳过已发送事件）。"""
    store = GappedEventStore(replay_rows=[_env(1), _env(2), _env(3)], gap_events=[_env(3), _env(4)])
    req = SettableRequest()

    async def consume():
        frames = []
        async for frame in sse_stream(req, store, "s1", 0, heartbeat_interval=0.01):
            frames.append(frame)
            if len(frames) == 4:
                req.disconnected = True
        return frames

    frames = await asyncio.wait_for(consume(), timeout=3)
    assert [_seq(f) for f in frames] == [1, 2, 3, 4]
