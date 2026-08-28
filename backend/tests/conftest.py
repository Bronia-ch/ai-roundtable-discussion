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
