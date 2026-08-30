import aiosqlite

from app.core.transactions import write_lock


async def reconcile(conn: aiosqlite.Connection) -> None:
    """启动幂等对账：修正遗留运行态、取消在途 turn、live→paused、重置在途洞察。"""
    lock = write_lock(conn)
    async with lock:
        await conn.execute(
            "UPDATE participants SET runtime_state='waiting' "
            "WHERE role='expert' AND runtime_state IN ('preparing','speaking')"
        )
        await conn.execute(
            "UPDATE participants SET runtime_state='idle' "
            "WHERE role='host' AND runtime_state IN ('preparing','speaking')"
        )
        await conn.execute(
            "UPDATE turns SET status='cancelled', cancelled_at=datetime('now'), "
            "generation_epoch=generation_epoch+1 WHERE status='generating'"
        )
        await conn.execute("UPDATE sessions SET status='paused' WHERE status='live'")
        await conn.execute(
            "UPDATE utterances SET insight_status='pending', insight_next_retry_at=datetime('now') "
            "WHERE insight_status IN ('pending','processing')"
        )
        await conn.commit()
