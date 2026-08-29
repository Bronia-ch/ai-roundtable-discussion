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


def test_resolve_after_seq_takes_max():
    assert resolve_after_seq("5", "3") == 5
    assert resolve_after_seq("3", "5") == 5


def test_resolve_after_seq_single_source():
    assert resolve_after_seq(None, "7") == 7
    assert resolve_after_seq("7", None) == 7


def test_resolve_after_seq_default_zero():
    assert resolve_after_seq(None, None) == 0


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
