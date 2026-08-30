import asyncio

import aiosqlite

from app.core.transactions import write_lock


class InsightWorker:
    """同会话按 ordinal 顺序领取洞察任务；条件更新防重复领取；洞察失败不阻塞下一轮发言。"""

    MAX_RETRY = 3

    def __init__(self, llm=None, concurrency: int = 4):
        self.llm = llm
        self.semaphore = asyncio.Semaphore(concurrency)

    async def claim_next(self, conn: aiosqlite.Connection, session_id: str) -> str | None:
        """严格 ordinal：最早未完成项阻塞后续；processing 或未到期 retry_wait 不可越过。"""
        lock = write_lock(conn)
        async with lock:
            row = await (
                await conn.execute(
                    "SELECT id, insight_status, insight_next_retry_at FROM utterances "
                    "WHERE session_id=? AND insight_status IN ('pending','processing','retry_wait') "
                    "ORDER BY ordinal LIMIT 1",
                    (session_id,),
                )
            ).fetchone()
            if row is None:
                return None
            uid, status, next_retry_at = row
            if status == "processing":
                return None
            if status == "retry_wait":
                due = (
                    await (await conn.execute("SELECT datetime('now') >= ?", (next_retry_at,))).fetchone()
                )[0] if next_retry_at else 1
                if not due:
                    return None
            cur = await conn.execute(
                "UPDATE utterances SET insight_status='processing' "
                "WHERE id=? AND insight_status IN ('pending','retry_wait')",
                (uid,),
            )
            await conn.commit()
            return uid if cur.rowcount == 1 else None

    async def mark_succeeded(self, conn: aiosqlite.Connection, utterance_id: str) -> None:
        lock = write_lock(conn)
        async with lock:
            await conn.execute(
                "UPDATE utterances SET insight_status='succeeded' WHERE id=?", (utterance_id,)
            )
            await conn.commit()

    async def mark_failed(self, conn: aiosqlite.Connection, utterance_id: str, error: str) -> None:
        lock = write_lock(conn)
        async with lock:
            row = await (
                await conn.execute(
                    "SELECT insight_retry_count FROM utterances WHERE id=?", (utterance_id,)
                )
            ).fetchone()
            count = row[0] + 1
            if count >= self.MAX_RETRY:
                await conn.execute(
                    "UPDATE utterances SET insight_status='permanently_failed', "
                    "insight_retry_count=?, insight_last_error=? WHERE id=?",
                    (count, error, utterance_id),
                )
            else:
                await conn.execute(
                    "UPDATE utterances SET insight_status='retry_wait', insight_retry_count=?, "
                    "insight_last_error=?, insight_next_retry_at=datetime('now', '+5 seconds') "
                    "WHERE id=?",
                    (count, error, utterance_id),
                )
            await conn.commit()
