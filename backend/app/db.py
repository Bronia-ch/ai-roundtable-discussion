import os

import aiosqlite


# CG-D：既有库幂等补列（定义与 schema.sql 的 sessions CREATE TABLE 一致；
# ALTER TABLE ADD COLUMN 追加到表尾——所有访问均按列名，顺序无关）。
_COLUMN_MIGRATIONS = (
    "utterance_cap INTEGER NOT NULL DEFAULT 40",
    "degraded_components TEXT",
    "used_rule_scheduler_count INTEGER NOT NULL DEFAULT 0",
    "failed_turn_count INTEGER NOT NULL DEFAULT 0",
    "permanently_failed_insight_count INTEGER NOT NULL DEFAULT 0",
)


async def _migrate(conn: aiosqlite.Connection) -> None:
    """既有库幂等迁移：PRAGMA table_info 读现存列，缺列则 ALTER TABLE ADD COLUMN。
    新库（schema.sql 已含全部列）与重复 init_db 均零改动（幂等）。"""
    existing = {
        row[1]
        for row in await (await conn.execute("PRAGMA table_info(sessions)")).fetchall()
    }
    for definition in _COLUMN_MIGRATIONS:
        column = definition.split(" ")[0]
        if column not in existing:
            await conn.execute(f"ALTER TABLE sessions ADD COLUMN {definition}")


async def init_db(conn: aiosqlite.Connection) -> None:
    """Create all tables and enable pragmas from schema.sql. Idempotent."""
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "schema.sql"), encoding="utf-8") as f:
        await conn.executescript(f.read())
    await conn.commit()
    await _migrate(conn)
    await conn.commit()
