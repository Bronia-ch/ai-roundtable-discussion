import pytest

from app.core.insight_worker import InsightWorker


async def _setup(conn):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'live')"
    )
    await conn.execute(
        "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
        "VALUES ('p1', 's1', 'expert', 'n', 'p', 't', 's', '#111', '🤖', 1)"
    )
    await conn.execute("INSERT INTO turns (id, session_id, sequence) VALUES ('t1', 's1', 1)")
    await conn.execute(
        "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal, insight_status) "
        "VALUES ('u1', 's1', 't1', 'p1', 'expert', 'a', 1, 'pending')"
    )
    await conn.execute(
        "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal, insight_status) "
        "VALUES ('u2', 's1', 't1', 'p1', 'expert', 'b', 2, 'pending')"
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_claim_picks_lowest_ordinal(conn):
    await _setup(conn)
    w = InsightWorker()
    assert await w.claim_next(conn, "s1") == "u1"


@pytest.mark.asyncio
async def test_claim_sets_processing(conn):
    await _setup(conn)
    w = InsightWorker()
    uid = await w.claim_next(conn, "s1")
    row = await (
        await conn.execute("SELECT insight_status FROM utterances WHERE id=?", (uid,))
    ).fetchone()
    assert row[0] == "processing"


@pytest.mark.asyncio
async def test_second_claim_returns_next(conn):
    await _setup(conn)
    w = InsightWorker()
    first = await w.claim_next(conn, "s1")
    second = await w.claim_next(conn, "s1")
    assert first == "u1"
    assert second == "u2"


@pytest.mark.asyncio
async def test_permanently_failed_not_reclaimed(conn):
    await _setup(conn)
    w = InsightWorker()
    uid = await w.claim_next(conn, "s1")
    for _ in range(3):
        await w.mark_failed(conn, uid, "boom")
    row = await (
        await conn.execute("SELECT insight_status FROM utterances WHERE id=?", (uid,))
    ).fetchone()
    assert row[0] == "permanently_failed"
    # 不再领取 u1，应领取下一条 u2
    assert await w.claim_next(conn, "s1") == "u2"
