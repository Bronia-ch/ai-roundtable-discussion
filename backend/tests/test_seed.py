import aiosqlite
import pytest

from app import db, seed


@pytest.mark.asyncio
async def test_seed_writes_5_samples(tmp_path):
    conn = await aiosqlite.connect(tmp_path / "t.db")
    await db.init_db(conn)
    await seed.run(conn)
    n = (
        await (
            await conn.execute("SELECT COUNT(*) FROM sessions WHERE is_sample=1")
        ).fetchone()
    )[0]
    assert n == 5
    for sid in [
        r[0]
        for r in await (
            await conn.execute("SELECT id FROM sessions WHERE is_sample=1")
        ).fetchall()
    ]:
        s = await (
            await conn.execute("SELECT status FROM sessions WHERE id=?", (sid,))
        ).fetchone()
        assert s[0] == "panel_ready"
    await conn.close()


@pytest.mark.asyncio
async def test_seed_idempotent(tmp_path):
    conn = await aiosqlite.connect(tmp_path / "t.db")
    await db.init_db(conn)
    await seed.run(conn)
    await seed.run(conn)
    n = (
        await (
            await conn.execute("SELECT COUNT(*) FROM sessions WHERE is_sample=1")
        ).fetchone()
    )[0]
    assert n == 5
    await conn.close()
