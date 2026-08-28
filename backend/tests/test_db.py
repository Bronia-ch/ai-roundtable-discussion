import aiosqlite
import pytest

from app import db


@pytest.mark.asyncio
async def test_init_db_creates_all_tables(tmp_path):
    conn = await aiosqlite.connect(tmp_path / "t.db")
    await db.init_db(conn)
    names = {
        r[0]
        async for r in await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    for t in (
        "sessions",
        "participants",
        "turns",
        "utterances",
        "insights",
        "insight_evidence",
        "events",
        "command_receipts",
        "discussion_reports",
    ):
        assert t in names
    await conn.close()


@pytest.mark.asyncio
async def test_foreign_keys_enabled(tmp_path):
    conn = await aiosqlite.connect(tmp_path / "t.db")
    await db.init_db(conn)
    fk = (await (await conn.execute("PRAGMA foreign_keys")).fetchone())[0]
    assert fk == 1
    await conn.close()
