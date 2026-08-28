import pytest

from app.core import insights


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
        "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal) "
        "VALUES ('u1', 's1', 't1', 'p1', 'expert', 'hi', 1)"
    )
    await conn.execute(
        "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal) "
        "VALUES ('u2', 's1', 't1', 'p1', 'expert', 'hi again', 2)"
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_create_insight(conn):
    await _setup(conn)
    iid = await insights.create_insight(conn, "s1", "consensus", "AI 提升效率")
    row = await (
        await conn.execute("SELECT kind, text FROM insights WHERE id=?", (iid,))
    ).fetchone()
    assert row == ("consensus", "AI 提升效率")


@pytest.mark.asyncio
async def test_duplicate_evidence_counted_once(conn):
    await _setup(conn)
    iid = await insights.create_insight(conn, "s1", "consensus", "AI 提升效率")
    await insights.add_evidence(conn, "s1", iid, "u1", "p1", "supports")
    await insights.add_evidence(conn, "s1", iid, "u1", "p1", "supports")  # 重复
    await insights.recompute_counts(conn, iid)
    row = await (
        await conn.execute("SELECT support_count, oppose_count FROM insights WHERE id=?", (iid,))
    ).fetchone()
    assert row == (1, 0)


@pytest.mark.asyncio
async def test_support_count_distinct_participant(conn):
    await _setup(conn)
    iid = await insights.create_insight(conn, "s1", "consensus", "AI 提升效率")
    # 同一参与者 p1 通过两条不同 utterance 支持同一 insight，只计 1
    await insights.add_evidence(conn, "s1", iid, "u1", "p1", "supports")
    await insights.add_evidence(conn, "s1", iid, "u2", "p1", "supports")
    await insights.recompute_counts(conn, iid)
    row = await (
        await conn.execute("SELECT support_count FROM insights WHERE id=?", (iid,))
    ).fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_support_oppose_separate(conn):
    await _setup(conn)
    iid = await insights.create_insight(conn, "s1", "divergence", "AI 是否加剧不平等")
    await insights.add_evidence(conn, "s1", iid, "u1", "p1", "supports")
    await insights.add_evidence(conn, "s1", iid, "u2", "p1", "opposes")
    await insights.recompute_counts(conn, iid)
    row = await (
        await conn.execute("SELECT support_count, oppose_count FROM insights WHERE id=?", (iid,))
    ).fetchone()
    assert row == (1, 1)
