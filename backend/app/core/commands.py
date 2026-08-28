import aiosqlite


async def register_command(
    conn: aiosqlite.Connection, session_id: str, command_id: str, command_type: str
) -> bool:
    """持久化命令幂等：首次返回 True，重复 (session_id, command_id) 返回 False（不重启任务）。"""
    cur = await conn.execute(
        "INSERT INTO command_receipts (session_id, command_id, command_type) VALUES (?, ?, ?) "
        "ON CONFLICT(session_id, command_id) DO NOTHING",
        (session_id, command_id, command_type),
    )
    await conn.commit()
    return cur.rowcount == 1
