import uuid

import aiosqlite


async def create_turn(
    conn: aiosqlite.Connection,
    session_id: str,
    sequence: int,
    selected_participant_id: str | None,
) -> str:
    tid = uuid.uuid4().hex
    await conn.execute(
        "INSERT INTO turns (id, session_id, sequence, status, selected_participant_id, started_at) "
        "VALUES (?, ?, ?, 'generating', ?, datetime('now'))",
        (tid, session_id, sequence, selected_participant_id),
    )
    await conn.commit()
    return tid


async def cancel_turn(conn: aiosqlite.Connection, turn_id: str) -> int:
    """取消 turn 并递增 generation_epoch，返回新 epoch（迟到响应据此被拒绝）。"""
    await conn.execute(
        "UPDATE turns SET status='cancelled', cancelled_at=datetime('now'), "
        "generation_epoch = generation_epoch + 1 WHERE id = ?",
        (turn_id,),
    )
    await conn.commit()
    row = await (
        await conn.execute("SELECT generation_epoch FROM turns WHERE id=?", (turn_id,))
    ).fetchone()
    return row[0]


async def mark_turn_failed(conn: aiosqlite.Connection, turn_id: str) -> None:
    """CG-D 失败矩阵（D3）：utterance 生成失败的轮 → turn 标 failed。
    status 由 turns.status CHECK 约束校验（含 'failed'）；turns 表无 failed_at 列，
    不写时间戳。"""
    await conn.execute(
        "UPDATE turns SET status='failed' WHERE id = ?",
        (turn_id,),
    )
    await conn.commit()


async def is_epoch_valid(conn: aiosqlite.Connection, turn_id: str, epoch: int) -> bool:
    row = await (
        await conn.execute("SELECT generation_epoch FROM turns WHERE id=?", (turn_id,))
    ).fetchone()
    return row is not None and row[0] == epoch
