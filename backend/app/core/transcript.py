import json
import uuid

import aiosqlite

MAX_TEXT_LENGTH = 2000


async def append_utterance(
    conn: aiosqlite.Connection,
    session_id: str,
    turn_id: str,
    speaker_id: str,
    role: str,
    text: str,
    ordinal: int,
    event_store=None,
) -> str:
    """追加整句发言，原子写入 utterance + 事件；跨会话 speaker/turn 由复合外键拒绝。
    event_store 注入点（G3）：事务提交后以本地精确 seq 广播 utterance.completed。
    speech_count 累计（仅 expert——host 不参与调度公平）与 utterance/事件/seq 在
    同一 BEGIN IMMEDIATE 事务内原子提交：崩溃时整笔回滚，绝不出现"已有发言、统计未更新"。
    发言者非 expert 时 speech_count 零触碰（防御：非法 role 由外键/校验拒绝）。"""
    if not text or not text.strip():
        raise ValueError("发言不能为空")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError("发言过长")

    uid = uuid.uuid4().hex
    await conn.execute("BEGIN IMMEDIATE")
    try:
        await conn.execute(
            "INSERT INTO utterances (id, session_id, turn_id, speaker_id, role, text, ordinal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, session_id, turn_id, speaker_id, role, text, ordinal),
        )
        if role == "expert":
            await conn.execute(
                "UPDATE participants SET speech_count = speech_count + 1 "
                "WHERE id = ? AND role = 'expert'",
                (speaker_id,),
            )
        await conn.execute(
            "UPDATE sessions SET last_event_sequence = last_event_sequence + 1 WHERE id = ?",
            (session_id,),
        )
        seq = (
            await (
                await conn.execute(
                    "SELECT last_event_sequence FROM sessions WHERE id = ?", (session_id,)
                )
            ).fetchone()
        )[0]
        await conn.execute(
            "INSERT INTO events (session_id, sequence, event_type, schema_version, payload) "
            "VALUES (?, ?, 'utterance.completed', 1, ?)",
            (
                session_id,
                seq,
                json.dumps(
                    {
                        "utterance_id": uid,
                        "turn_id": turn_id,
                        "speaker_id": speaker_id,
                        "role": role,
                        "text": text,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    if event_store is not None:
        await event_store.publish(conn, session_id, seq)  # 已提交；广播失败不触发回滚
    return uid
