import asyncio
from typing import Any, Awaitable, Callable


class EngineRegistry:
    """同一 session 最多一个运行中的 engine；start/resume/retry 走 session 级锁 get-or-create。"""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._engines: dict[str, Any] = {}

    async def get_or_create(self, session_id: str, factory: Callable[[], Awaitable[Any]]) -> Any:
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            if session_id in self._engines:
                return self._engines[session_id]
            engine = await factory()
            self._engines[session_id] = engine
            return engine

    async def remove(self, session_id: str) -> None:
        lock = self._locks.get(session_id)
        if lock is not None:
            async with lock:
                self._engines.pop(session_id, None)
        else:
            self._engines.pop(session_id, None)
