import asyncio
import json

import aiosqlite


class EventStore:
    """进程内 SSE 订阅注册表（按 session 分桶）+ 从 events 表重放。广播发生在提交之后。"""

    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(session_id, set()).add(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(session_id)
        if subs:
            subs.discard(q)

    async def broadcast(self, session_id: str, envelope: dict) -> None:
        for q in list(self._subscribers.get(session_id, set())):
            await q.put(envelope)

    async def replay(self, session_id: str, after_seq: int) -> list[dict]:
        rows = await (
            await self.conn.execute(
                "SELECT sequence, event_type, schema_version, payload, created_at FROM events "
                "WHERE session_id=? AND sequence > ? ORDER BY sequence",
                (session_id, after_seq),
            )
        ).fetchall()
        return [
            {
                "event": r[1],
                "sequence": r[0],
                "schema_version": r[2],
                "session_id": session_id,
                "timestamp": r[4],
                "data": json.loads(r[3]),
            }
            for r in rows
        ]
