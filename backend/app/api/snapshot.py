import aiosqlite


async def get_session_snapshot(conn: aiosqlite.Connection, session_id: str) -> dict | None:
    """权威快照：状态 + Transcript + 洞察 + last_sequence（供前端先取快照再订阅）。"""
    row = await (
        await conn.execute(
            "SELECT status, last_event_sequence, topic, expert_count FROM sessions WHERE id=?",
            (session_id,),
        )
    ).fetchone()
    if row is None:
        return None
    utterances = await (
        await conn.execute(
            "SELECT id, turn_id, speaker_id, role, text, ordinal FROM utterances "
            "WHERE session_id=? ORDER BY ordinal",
            (session_id,),
        )
    ).fetchall()
    insights = await (
        await conn.execute(
            "SELECT id, kind, text, support_count, oppose_count, status, version FROM insights "
            "WHERE session_id=?",
            (session_id,),
        )
    ).fetchall()
    return {
        "session_id": session_id,
        "status": row[0],
        "last_sequence": row[1],
        "topic": row[2],
        "expert_count": row[3],
        "transcript": [
            {"id": u[0], "turn_id": u[1], "speaker_id": u[2], "role": u[3], "text": u[4], "ordinal": u[5]}
            for u in utterances
        ],
        "insights": [
            {
                "id": i[0],
                "kind": i[1],
                "text": i[2],
                "support_count": i[3],
                "oppose_count": i[4],
                "status": i[5],
                "version": i[6],
            }
            for i in insights
        ],
    }
