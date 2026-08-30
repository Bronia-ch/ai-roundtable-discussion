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


@pytest.mark.asyncio
async def test_track_duplicate_rejected_and_get_task():
    """契约：track 登记后台任务（首次 True、同 session 重复 False）；get_task 取回登记。"""
    assert hasattr(EngineRegistry, "track"), "契约：EngineRegistry.track(session_id, task) -> bool"
    assert hasattr(EngineRegistry, "get_task"), "契约：EngineRegistry.get_task(session_id)"
    assert hasattr(EngineRegistry, "stop"), "契约：EngineRegistry.stop(session_id)"
    assert hasattr(EngineRegistry, "shutdown"), "契约：EngineRegistry.shutdown()"
    reg = EngineRegistry()
    task = asyncio.create_task(asyncio.Event().wait())
    try:
        assert await reg.track("s1", task) is True, "首次 track 必须接受"
        assert await reg.track("s1", task) is False, "重复 track 必须拒绝（同 session 单任务）"
        assert reg.get_task("s1") is task
    finally:
        # 仅此一个 task；重复 track 被拒绝、不留登记。测试退出前取消，绝不留后台任务。
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_stop_cancels_task_and_cleans_up():
    """stop 契约：取消并等待任务确定性完成，随后清理登记。"""
    reg = EngineRegistry()
    started = asyncio.Event()

    async def worker():
        started.set()
        await asyncio.Event().wait()  # 永不自行结束

    task = asyncio.create_task(worker())
    await started.wait()
    await reg.track("s1", task)
    await reg.stop("s1")
    assert task.done(), "stop 必须取消并等待任务完成"
    assert task.cancelled(), "任务应被取消"
    assert reg.get_task("s1") is None, "stop 必须清理登记"


@pytest.mark.asyncio
async def test_stop_after_naturally_done_task_cleans_up():
    """stop 与任务自然完成竞争：已 done 的任务 stop 不抛错、登记被清理。"""
    reg = EngineRegistry()

    async def done_worker():
        return 42

    task = asyncio.create_task(done_worker())
    await task
    await reg.track("s1", task)
    await reg.stop("s1")
    assert reg.get_task("s1") is None


@pytest.mark.asyncio
async def test_shutdown_stops_all_tracked_tasks():
    """shutdown：遍历快照停止全部登记任务；全部完成后返回，不挂起。"""
    reg = EngineRegistry()
    tasks = [asyncio.create_task(asyncio.Event().wait()) for _ in range(3)]
    for sid, task in zip(("a", "b", "c"), tasks):
        assert await reg.track(sid, task) is True
    await reg.shutdown()
    assert all(t.done() for t in tasks), "shutdown 必须停止全部登记任务"
    assert reg.get_task("a") is None and reg.get_task("b") is None and reg.get_task("c") is None
