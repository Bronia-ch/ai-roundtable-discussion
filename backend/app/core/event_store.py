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
        return [self._envelope(r, session_id) for r in rows]

    @staticmethod
    def _envelope(row, session_id: str) -> dict:
        """replay 行 → 广播 envelope。publish 与 replay 共用同一构造——两通道必然同构。"""
        return {
            "event": row[1],
            "sequence": row[0],
            "schema_version": row[2],
            "session_id": session_id,
            "timestamp": row[4],
            "data": json.loads(row[3]),
        }

    async def publish(self, conn: aiosqlite.Connection, session_id: str, seq: int) -> None:
        """事务提交后以精确 seq 广播：读 WHERE session_id=? AND sequence=? 的**该行**
        构造 envelope 后 broadcast——绝不通过"读取最新事件"推断（读最新会错位广播）。
        无该行 → KeyError（调用方事务已提交，广播失败由调用方/重放自愈）。"""
        row = await (
            await conn.execute(
                "SELECT sequence, event_type, schema_version, payload, created_at FROM events "
                "WHERE session_id=? AND sequence=?",
                (session_id, seq),
            )
        ).fetchone()
        if row is None:
            raise KeyError(f"publish: no event at {session_id}:{seq}")
        await self.broadcast(session_id, self._envelope(row, session_id))
