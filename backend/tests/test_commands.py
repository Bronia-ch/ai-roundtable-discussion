import pytest

from app.core import commands


async def _insert_session(conn):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'draft')"
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_register_command_first_time(conn):
    await _insert_session(conn)
    assert await commands.register_command(conn, "s1", "c1", "start") is True


@pytest.mark.asyncio
async def test_register_command_duplicate(conn):
    await _insert_session(conn)
    assert await commands.register_command(conn, "s1", "c1", "start") is True
    assert await commands.register_command(conn, "s1", "c1", "start") is False
    row = await (
        await conn.execute(
            "SELECT status FROM command_receipts WHERE session_id='s1' AND command_id='c1'"
        )
    ).fetchone()
    assert row[0] == "accepted"
