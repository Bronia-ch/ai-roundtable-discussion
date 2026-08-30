import uuid

import aiosqlite

from app.core.transactions import write_lock


async def create_insight(conn: aiosqlite.Connection, session_id: str, kind: str, text: str) -> str:
    iid = uuid.uuid4().hex
    lock = write_lock(conn)
    async with lock:
        await conn.execute(
            "INSERT INTO insights (id, session_id, kind, text) VALUES (?, ?, ?, ?)",
            (iid, session_id, kind, text),
        )
        await conn.commit()
    return iid


async def mark_insight_state(
    conn: aiosqlite.Connection,
    utterance_id: str,
    state: str,
) -> int:
    """CG-D 降级记账（D5/D6）：insight 失败/结构非法 → 所属 utterance 标
    permanently_failed（insights 表零行、讨论继续）。state 由 utterances.insight_status
    CHECK 约束校验（含 'permanently_failed'）；返回受影响行数（utterance 不存在 → 0）。"""
    lock = write_lock(conn)
    async with lock:
        cur = await conn.execute(
            "UPDATE utterances SET insight_status = ? WHERE id = ?",
            (state, utterance_id),
        )
        await conn.commit()
        return cur.rowcount


async def add_evidence(
    conn: aiosqlite.Connection,
    session_id: str,
    insight_id: str,
    utterance_id: str,
    participant_id: str,
    relation: str,
) -> bool:
    """记录证据（INSERT OR IGNORE，靠 UNIQUE(insight_id, utterance_id, relation) 去重）。"""
    lock = write_lock(conn)
    async with lock:
        cur = await conn.execute(
            "INSERT OR IGNORE INTO insight_evidence "
            "(session_id, insight_id, utterance_id, participant_id, relation) VALUES (?, ?, ?, ?, ?)",
            (session_id, insight_id, utterance_id, participant_id, relation),
        )
        await conn.commit()
        return cur.rowcount == 1


async def recompute_counts(conn: aiosqlite.Connection, insight_id: str) -> int:
    """按去重 participant_id 聚合 support/oppose 计数并回写，真值来自 evidence。"""
    lock = write_lock(conn)
    async with lock:
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
