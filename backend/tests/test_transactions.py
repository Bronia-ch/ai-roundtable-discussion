import pytest

from app.core import transactions


async def _insert_session(conn, sid):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, 't', 4, 'draft')",
        (sid,),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_commit_event_persists_state_and_event(conn):
    await _insert_session(conn, "s1")
    seq = await transactions.commit_event(
        conn, "s1", "session.state_changed", {"state": "panel_ready"}, {"status": "panel_ready"}
    )
    assert seq == 1
    row = await (
        await conn.execute("SELECT status, last_event_sequence FROM sessions WHERE id='s1'")
    ).fetchone()
    assert row == ("panel_ready", 1)
    ev = await (
        await conn.execute("SELECT sequence, event_type FROM events WHERE session_id='s1'")
    ).fetchone()
    assert ev == (1, "session.state_changed")


@pytest.mark.asyncio
async def test_commit_event_rolls_back_on_event_failure(conn):
    await _insert_session(conn, "s1")
    # 预先插入 sequence=1，制造 events 表 UNIQUE 冲突
    await conn.execute(
        "INSERT INTO events (session_id, sequence, event_type, payload) VALUES ('s1', 1, 'x', '{}')"
    )
    await conn.commit()
    with pytest.raises(Exception):
        await transactions.commit_event(conn, "s1", "y", {}, {"status": "live"})
    status = (await (await conn.execute("SELECT status FROM sessions WHERE id='s1'")).fetchone())[0]
    assert status == "draft"


@pytest.mark.asyncio
async def test_sequences_independent_across_sessions(conn):
    await _insert_session(conn, "s1")
    await _insert_session(conn, "s2")
    a = await transactions.commit_event(conn, "s1", "a", {}, {})
    b = await transactions.commit_event(conn, "s2", "a", {}, {})
    assert a == 1 and b == 1
