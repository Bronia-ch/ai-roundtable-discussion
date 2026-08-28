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
) -> str:
    """追加整句发言，原子写入 utterance + 事件；跨会话 speaker/turn 由复合外键拒绝。"""
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
        return uid
    except Exception:
        await conn.rollback()
        raise
