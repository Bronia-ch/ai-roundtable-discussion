import asyncio
import random
from typing import Any, Awaitable, Callable

from app.core.errors import ErrorClass


async def call_with_retry(
    fn: Callable[[], Awaitable[Any]],
    *,
    classify: Callable[[Exception], ErrorClass],
    max_retries: int = 3,
    base_delay: float = 1.0,
    jitter: float = 0.2,
) -> Any:
    """仅对 RECOVERABLE 错误做有限指数退避 + jitter 重试；auth/schema/fatal 立即抛出。"""
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as exc:
            cls = classify(exc)
            if cls != ErrorClass.RECOVERABLE or attempt >= max_retries:
                raise
            backoff = base_delay * (2 ** attempt)
            delay = backoff + random.uniform(0, backoff * jitter)
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")
