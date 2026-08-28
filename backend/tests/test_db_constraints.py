import sqlite3

import aiosqlite
import pytest

from app import db


@pytest.fixture
async def conn(tmp_path):
    c = await aiosqlite.connect(tmp_path / "t.db")
    await db.init_db(c)
    try:
        yield c
    finally:
        await c.close()


async def _insert_session(conn, sid, topic="t"):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, ?, 4, 'live')",
        (sid, topic),
    )


async def _insert_participant(conn, pid, sid, role="expert", sort_order=1):
    await conn.execute(
        "INSERT INTO participants "
        "(id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
        "VALUES (?, ?, ?, 'n', 'p', 't', 's', '#111', '🤖', ?)",
        (pid, sid, role, sort_order),
    )


@pytest.mark.asyncio
async def test_valid_entities_write_and_fk_check_clean(conn):
    await _insert_session(conn, "s1")
    await _insert_participant(conn, "s1_host", "s1", "host", 0)
    await _insert_participant(conn, "s1_e1", "s1", "expert", 1)
    await conn.execute(
        "INSERT INTO turns (id, session_id, sequence, status, selected_participant_id) "
        "VALUES ('t1', 's1', 1, 'generating', 's1_e1')"
    )
    await conn.execute(
        "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal) "
        "VALUES ('u1', 's1', 't1', 's1_e1', 'expert', 'hello', 1)"
    )
    await conn.execute(
        "INSERT INTO events (session_id, sequence, event_type, payload) "
        "VALUES ('s1', 1, 'x', '{}')"
    )
    await conn.execute(
        "INSERT INTO command_receipts (session_id, command_id, command_type) "
        "VALUES ('s1', 'c1', 'start')"
    )
    await conn.commit()
    rows = [r async for r in await conn.execute("PRAGMA foreign_key_check")]
    assert rows == []


@pytest.mark.asyncio
async def test_utterance_rejects_cross_session_turn(conn):
    await _insert_session(conn, "sA", "a")
    await conn.execute("INSERT INTO turns (id, session_id, sequence) VALUES ('tA', 'sA', 1)")
    await _insert_session(conn, "sB", "b")
    await _insert_participant(conn, "sB_e1", "sB", "expert", 1)
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal) "
            "VALUES ('u1', 'sB', 'tA', 'sB_e1', 'expert', 'x', 1)"
        )


@pytest.mark.asyncio
async def test_utterance_rejects_cross_session_speaker(conn):
    await _insert_session(conn, "sA", "a")
    await _insert_participant(conn, "sA_e1", "sA", "expert", 1)
    await _insert_session(conn, "sB", "b")
    await _insert_participant(conn, "sB_e1", "sB", "expert", 1)
    await conn.execute("INSERT INTO turns (id, session_id, sequence) VALUES ('tB', 'sB', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal) "
            "VALUES ('u1', 'sB', 'tB', 'sA_e1', 'expert', 'x', 1)"
        )


@pytest.mark.asyncio
async def test_turn_rejects_cross_session_selected_participant(conn):
    await _insert_session(conn, "sA", "a")
    await _insert_participant(conn, "sA_e1", "sA", "expert", 1)
    await _insert_session(conn, "sB", "b")
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO turns (id, session_id, sequence, selected_participant_id) "
            "VALUES ('tB', 'sB', 1, 'sA_e1')"
        )


@pytest.mark.asyncio
async def test_events_reject_unknown_session(conn):
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO events (session_id, sequence, event_type, payload) "
            "VALUES ('ghost', 1, 'x', '{}')"
        )


@pytest.mark.asyncio
async def test_command_receipts_reject_unknown_session(conn):
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO command_receipts (session_id, command_id, command_type) "
            "VALUES ('ghost', 'c1', 'start')"
        )
