import pytest

from app.core.insight_worker import InsightWorker


async def _seed_session(conn, sid, uid):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, 't', 4, 'live')", (sid,)
    )
    await conn.execute(
        "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
        "VALUES (?, ?, 'expert', 'n', 'p', 't', 's', '#111', '🤖', 1)",
        (sid + "_p", sid),
    )
    await conn.execute("INSERT INTO turns (id, session_id, sequence) VALUES (?, ?, 1)", (sid + "_t", sid))
    await conn.execute(
        "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal, insight_status) "
        "VALUES (?, ?, ?, ?, 'expert', 'x', 1, 'pending')",
        (uid, sid, sid + "_t", sid + "_p"),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_worker_isolates_sessions(conn):
    await _seed_session(conn, "s1", "u1")
    await _seed_session(conn, "s2", "u2")
    w = InsightWorker()
    assert await w.claim_next(conn, "s1") == "u1"
    assert await w.claim_next(conn, "s2") == "u2"


@pytest.mark.asyncio
async def test_sequences_independent(conn):
    await _seed_session(conn, "s1", "u1")
    await _seed_session(conn, "s2", "u2")
    from app.core import transactions

    a = await transactions.commit_event(conn, "s1", "a", {}, {})
    b = await transactions.commit_event(conn, "s2", "a", {}, {})
    assert (a, b) == (1, 1)
