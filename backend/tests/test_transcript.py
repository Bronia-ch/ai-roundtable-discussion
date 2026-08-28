import pytest

from app.core import transcript


async def _setup(conn):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'live')"
    )
    await conn.execute(
        "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
        "VALUES ('p1', 's1', 'expert', 'n', 'p', 't', 's', '#111', '🤖', 1)"
    )
    await conn.execute("INSERT INTO turns (id, session_id, sequence) VALUES ('t1', 's1', 1)")
    await conn.commit()


@pytest.mark.asyncio
async def test_append_utterance(conn):
    await _setup(conn)
    uid = await transcript.append_utterance(conn, "s1", "t1", "p1", "expert", "你好", 1)
    assert uid
    row = await (
        await conn.execute("SELECT text, ordinal FROM utterances WHERE id=?", (uid,))
    ).fetchone()
    assert row == ("你好", 1)


@pytest.mark.asyncio
async def test_append_utterance_rejects_empty(conn):
    await _setup(conn)
    with pytest.raises(ValueError):
        await transcript.append_utterance(conn, "s1", "t1", "p1", "expert", "   ", 1)


@pytest.mark.asyncio
async def test_append_utterance_rejects_cross_session_speaker(conn):
    await _setup(conn)
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s2', 't', 4, 'live')"
    )
    await conn.commit()
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        await transcript.append_utterance(conn, "s2", "t1", "p1", "expert", "越界", 1)
