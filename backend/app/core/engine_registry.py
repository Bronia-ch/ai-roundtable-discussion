import asyncio
from typing import Any, Awaitable, Callable


class EngineRegistry:
    """同一 session 最多一个运行中的 engine；start/resume/retry 走 session 级锁 get-or-create；
    后台任务登记经 track/get_task/stop/shutdown（CG-B：确定性收尾）。"""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._engines: dict[str, Any] = {}
        self._tasks: dict[str, asyncio.Task] = {}

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

    def get_engine(self, session_id: str):
        """已登记 engine 引用（pause/resume/end 发信号）；未创建则 None。
        同步纯读（与 get_task 同约定）：路由直接取、不 await。"""
        return self._engines.get(session_id)

    async def track(self, session_id: str, task: asyncio.Task) -> bool:
        """登记引擎后台任务：首次 True、同 session 重复 False（单任务约束）。
        dict 读写无 await 交错点（asyncio 协作式原子），与 stop 并发安全。"""
        if session_id in self._tasks:
            return False
        self._tasks[session_id] = task
        return True

    def get_task(self, session_id: str) -> asyncio.Task | None:
        """同步返回登记任务（RED 契约：`registry.get_task(...) is task` 直接比较，非 await）。"""
        return self._tasks.get(session_id)

    async def stop(self, session_id: str) -> None:
        """取消并等待任务确定性完成，随后清理登记；无登记为 no-op。
        已 done 任务跳过 cancel 直接清理（与自然完成竞争安全）。"""
        task = self._tasks.pop(session_id, None)
        if task is None:
            return
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def shutdown(self) -> None:
        """遍历快照停止全部登记任务（先快照后逐项 stop：并发 track/stop 不遗漏、不双停）。"""
        for sid in list(self._tasks):
            await self.stop(sid)
