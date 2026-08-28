import asyncio

import pytest

from app.core.engine_registry import EngineRegistry


@pytest.mark.asyncio
async def test_concurrent_get_or_create_single_engine():
    reg = EngineRegistry()
    created = []

    async def factory():
        created.append(1)
        await asyncio.sleep(0)  # 让出控制权，放大竞态
        return {"engine": len(created)}

    results = await asyncio.gather(*[reg.get_or_create("s1", factory) for _ in range(20)])
    assert len(created) == 1
    assert all(r is results[0] for r in results)


@pytest.mark.asyncio
async def test_remove_allows_recreate():
    reg = EngineRegistry()

    async def factory():
        return object()

    e1 = await reg.get_or_create("s1", factory)
    await reg.remove("s1")
    e2 = await reg.get_or_create("s1", factory)
    assert e1 is not e2


@pytest.mark.asyncio
async def test_slow_factory_a_does_not_block_b():
    reg = EngineRegistry()
    a_release = asyncio.Event()

    async def factory_a():
        await a_release.wait()
        return "engine_a"

    async def factory_b():
        return "engine_b"

    a_task = asyncio.create_task(reg.get_or_create("a", factory_a))
    await asyncio.sleep(0)  # 让 A 进入 factory 并卡在 a_release
    b_task = asyncio.create_task(reg.get_or_create("b", factory_b))
    b = await asyncio.wait_for(b_task, timeout=0.5)
    assert b == "engine_b"  # B 未受 A 阻塞
    a_release.set()
    a = await a_task
    assert a == "engine_a"
