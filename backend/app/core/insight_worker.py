import asyncio

import aiosqlite


class InsightWorker:
    """同会话按 ordinal 顺序领取洞察任务；条件更新防重复领取；洞察失败不阻塞下一轮发言。"""

    MAX_RETRY = 3

    def __init__(self, llm=None, concurrency: int = 4):
        self.llm = llm
        self.semaphore = asyncio.Semaphore(concurrency)

    async def claim_next(self, conn: aiosqlite.Connection, session_id: str) -> str | None:
        row = await (
            await conn.execute(
                "SELECT id FROM utterances WHERE session_id=? "
                "AND insight_status IN ('pending','retry_wait') "
                "AND (insight_next_retry_at IS NULL OR insight_next_retry_at <= datetime('now')) "
                "ORDER BY ordinal LIMIT 1",
                (session_id,),
            )
        ).fetchone()
        if row is None:
            return None
        uid = row[0]
        cur = await conn.execute(
            "UPDATE utterances SET insight_status='processing' "
            "WHERE id=? AND insight_status IN ('pending','retry_wait')",
            (uid,),
        )
        await conn.commit()
        return uid if cur.rowcount == 1 else None

    async def mark_succeeded(self, conn: aiosqlite.Connection, utterance_id: str) -> None:
        await conn.execute(
            "UPDATE utterances SET insight_status='succeeded' WHERE id=?", (utterance_id,)
        )
        await conn.commit()

    async def mark_failed(self, conn: aiosqlite.Connection, utterance_id: str, error: str) -> None:
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
