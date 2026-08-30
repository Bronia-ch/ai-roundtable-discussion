import asyncio

import pytest

from app.core import transactions
from app.core.event_store import EventStore


async def _seed(conn, sid):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, 't', 4, 'live')", (sid,)
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_broadcast_only_to_own_session(conn):
    store = EventStore(conn)
    q_a = store.subscribe("s1")
    q_b = store.subscribe("s2")
    await store.broadcast("s1", {"event": "x", "sequence": 1, "session_id": "s1", "data": {}})
    assert (await asyncio.wait_for(q_a.get(), timeout=0.1))["event"] == "x"
    assert q_b.empty()


@pytest.mark.asyncio
async def test_replay_after_seq(conn):
    await _seed(conn, "s1")
    await transactions.commit_event(conn, "s1", "a", {}, {})
    await transactions.commit_event(conn, "s1", "b", {}, {})
    await transactions.commit_event(conn, "s1", "c", {}, {})
    store = EventStore(conn)
    rows = await store.replay("s1", 1)
    assert [r["sequence"] for r in rows] == [2, 3]


@pytest.mark.asyncio
async def test_publish_reads_exact_seq_not_latest(conn):
    """G3 契约：publish 按精确 seq 读取该行事件并广播——广播 sequence 必须等于
    入参 seq，而非 session 的 last_event_sequence（读最新会错位广播）。"""
    assert hasattr(EventStore, "publish"), "契约：EventStore.publish(conn, session_id, seq)"
    await _seed(conn, "s1")
    await transactions.commit_event(conn, "s1", "a", {"n": 1}, {})  # seq 1
    await transactions.commit_event(conn, "s1", "b", {"n": 2}, {})  # seq 2（最新）
    store = EventStore(conn)
    q = store.subscribe("s1")
    await store.publish(conn, "s1", 1)  # 故意发布非最新 seq——读最新实现会错位为事件 b
    frame = await asyncio.wait_for(q.get(), timeout=0.5)
    assert frame["event"] == "a"
    assert frame["sequence"] == 1
    assert frame["data"]["n"] == 1


@pytest.mark.asyncio
async def test_publish_envelope_isomorphic_to_replay(conn):
    """publish 广播的 envelope 必须与 replay 行全等（同一事件两种通道同构）。"""
    await _seed(conn, "s1")
    await transactions.commit_event(conn, "s1", "a", {"n": 1}, {})
    store = EventStore(conn)
    rows = await store.replay("s1", 0)
    q = store.subscribe("s1")
    await store.publish(conn, "s1", 1)
    frame = await asyncio.wait_for(q.get(), timeout=0.5)
    assert frame == rows[0], "publish 构造的 envelope 必须与 replay 行同构"
