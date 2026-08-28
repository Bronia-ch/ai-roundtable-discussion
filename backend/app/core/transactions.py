import json
from typing import Any

import aiosqlite

# 允许作为 state_updates 键的列（白名单，防注入）
_ALLOWED_COLUMNS = {
    "status",
    "last_stable_state",
    "error_code",
    "retry_operation",
    "is_sample",
    "expert_count",
}


async def commit_event(
    conn: aiosqlite.Connection,
    session_id: str,
    event_type: str,
    payload: dict[str, Any],
    state_updates: dict[str, Any] | None = None,
) -> int:
    """原子三写：应用业务状态 + 递增 last_event_sequence + 插入 events，返回新 sequence。

    任一写失败整体回滚。LLM/网络调用绝不可在本事务内发生。
    """
    await conn.execute("BEGIN IMMEDIATE")
    try:
        if state_updates:
            for key in state_updates:
                if key not in _ALLOWED_COLUMNS:
                    raise ValueError(f"不允许的 state_updates 列: {key}")
            cols = ", ".join(f"{k} = ?" for k in state_updates)
            await conn.execute(
                f"UPDATE sessions SET {cols} WHERE id = ?",
                (*state_updates.values(), session_id),
            )
        await conn.execute(
            "UPDATE sessions SET last_event_sequence = last_event_sequence + 1 WHERE id = ?",
            (session_id,),
        )
        row = await (
            await conn.execute(
                "SELECT last_event_sequence FROM sessions WHERE id = ?", (session_id,)
            )
        ).fetchone()
        seq = row[0]
        await conn.execute(
            "INSERT INTO events (session_id, sequence, event_type, schema_version, payload) "
            "VALUES (?, ?, ?, 1, ?)",
            (session_id, seq, event_type, json.dumps(payload, ensure_ascii=False)),
        )
        await conn.commit()
        return seq
    except Exception:
        await conn.rollback()
        raise
