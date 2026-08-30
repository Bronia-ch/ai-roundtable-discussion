import aiosqlite


async def get_session_snapshot(conn: aiosqlite.Connection, session_id: str) -> dict | None:
    """权威快照：状态 + Transcript + 洞察 + 阵容 + 最终报告摘要 + last_sequence（刷新恢复契约）。

    - participants：按 sort_order 全量返回（与 panel.generated 事件同构——刷新后
      PanelSetup/Studio 与事件推送结果一致；无阵容 → 空数组）。
    - summary：discussion_reports.raw_json（验证后的报告 JSON 字符串；未完成/无报告
      为 None。与 discussion.completed 事件 data.summary 同源同串——Result 页可同时
      从快照与 SSE 恢复最终报告）。
    """
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
    participants = await (
        await conn.execute(
            "SELECT id, session_id, role, name, profession, title, stance, avatar_color, "
            "avatar_emoji, runtime_state, public_focus FROM participants "
            "WHERE session_id=? ORDER BY sort_order",
            (session_id,),
        )
    ).fetchall()
    report = await (
        await conn.execute(
            "SELECT raw_json FROM discussion_reports WHERE session_id=?", (session_id,)
        )
    ).fetchone()
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
        "participants": [
            {
                "id": p[0],
                "session_id": p[1],
                "role": p[2],
                "name": p[3],
                "profession": p[4],
                "title": p[5],
                "stance": p[6],
                "avatar_color": p[7],
                "avatar_emoji": p[8],
                "runtime_state": p[9],
                "public_focus": p[10],
            }
            for p in participants
        ],
        "summary": report[0] if report is not None else None,
    }
