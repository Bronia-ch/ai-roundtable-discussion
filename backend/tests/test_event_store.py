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
