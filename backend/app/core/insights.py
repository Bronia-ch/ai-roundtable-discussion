import uuid

import aiosqlite


async def create_insight(conn: aiosqlite.Connection, session_id: str, kind: str, text: str) -> str:
    iid = uuid.uuid4().hex
    await conn.execute(
        "INSERT INTO insights (id, session_id, kind, text) VALUES (?, ?, ?, ?)",
        (iid, session_id, kind, text),
    )
    await conn.commit()
    return iid


async def add_evidence(
    conn: aiosqlite.Connection,
    session_id: str,
    insight_id: str,
    utterance_id: str,
    participant_id: str,
    relation: str,
) -> bool:
    """记录证据（INSERT OR IGNORE，靠 UNIQUE(insight_id, utterance_id, relation) 去重）。"""
    cur = await conn.execute(
        "INSERT OR IGNORE INTO insight_evidence "
        "(session_id, insight_id, utterance_id, participant_id, relation) VALUES (?, ?, ?, ?, ?)",
        (session_id, insight_id, utterance_id, participant_id, relation),
    )
    await conn.commit()
    return cur.rowcount == 1


async def recompute_counts(conn: aiosqlite.Connection, insight_id: str) -> int:
    """按去重 participant_id 聚合 support/oppose 计数并回写，真值来自 evidence。"""
    support = (
        await (
            await conn.execute(
                "SELECT COUNT(DISTINCT participant_id) FROM insight_evidence "
                "WHERE insight_id=? AND relation='supports'",
                (insight_id,),
            )
        ).fetchone()
    )[0]
    oppose = (
        await (
            await conn.execute(
                "SELECT COUNT(DISTINCT participant_id) FROM insight_evidence "
                "WHERE insight_id=? AND relation='opposes'",
                (insight_id,),
            )
        ).fetchone()
    )[0]
    await conn.execute(
        "UPDATE insights SET support_count=?, oppose_count=?, version=version+1, "
        "updated_at=datetime('now') WHERE id=?",
        (support, oppose, insight_id),
    )
    await conn.commit()
    return (
        await (await conn.execute("SELECT version FROM insights WHERE id=?", (insight_id,))).fetchone()
    )[0]
