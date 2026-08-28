import os

import aiosqlite


async def init_db(conn: aiosqlite.Connection) -> None:
    """Create all tables and enable pragmas from schema.sql. Idempotent."""
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "schema.sql"), encoding="utf-8") as f:
        await conn.executescript(f.read())
    await conn.commit()
