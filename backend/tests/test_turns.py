import pytest

from app.core import turns


async def _insert_session(conn, sid="s1"):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES (?, 't', 4, 'live')",
        (sid,),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_create_turn(conn):
    await _insert_session(conn)
    tid = await turns.create_turn(conn, "s1", 1, None)
    assert tid
    row = await (
        await conn.execute("SELECT status, generation_epoch FROM turns WHERE id=?", (tid,))
    ).fetchone()
    assert row == ("generating", 1)


@pytest.mark.asyncio
async def test_cancel_turn_increments_epoch(conn):
    await _insert_session(conn)
    tid = await turns.create_turn(conn, "s1", 1, None)
    epoch = await turns.cancel_turn(conn, tid)
    assert epoch == 2
    row = await (
        await conn.execute("SELECT status, generation_epoch FROM turns WHERE id=?", (tid,))
    ).fetchone()
    assert row == ("cancelled", 2)


@pytest.mark.asyncio
async def test_is_epoch_valid(conn):
    await _insert_session(conn)
    tid = await turns.create_turn(conn, "s1", 1, None)
    assert await turns.is_epoch_valid(conn, tid, 1) is True
    await turns.cancel_turn(conn, tid)
    assert await turns.is_epoch_valid(conn, tid, 1) is False
    assert await turns.is_epoch_valid(conn, tid, 2) is True
