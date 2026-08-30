import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    CommandRequest,
    CreateSessionRequest,
    SessionCreated,
    SessionListOut,
)
from app.api.snapshot import get_session_snapshot
from app.api.sse import resolve_after_seq, sse_stream
from app.core.engine import DiscussionEngine
from app.core import transactions
from app.core.transactions import CommandOutcome
from app.core import panel as panel_ops  # panel/generate 执行体（LLM 生成 + 原子回写）

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso(ts: str) -> str:
    """SQLite datetime('now') 为 "YYYY-MM-DD HH:MM:SS"；已是 ISO-8601 原样返回（幂等）。"""
    return ts.replace(" ", "T") + "Z" if " " in ts else ts


@router.post("/sessions", status_code=201, response_model=SessionCreated)
async def create_session(body: CreateSessionRequest, request: Request):
    """创建 draft 会话：同一事务写入会话行 + session.state_changed 事件（state=draft, sequence=1）。"""
    conn = request.app.state.conn
    session_id = uuid.uuid4().hex
    created_at = _now_iso()
    await transactions.create_session(
        conn, session_id, body.topic, body.expert_count, created_at,
        event_store=request.app.state.event_store,  # G3：draft 创建事件提交后精确 seq 广播
    )
    return {
        "session_id": session_id,
        "topic": body.topic,
        "expert_count": body.expert_count,
        "status": "draft",
        "created_at": created_at,
    }


@router.get("/sessions", response_model=SessionListOut)
async def list_sessions(request: Request):
    """会话列表：created_at 确定性排序（升序，id 兜底），严格五字段。"""
    conn = request.app.state.conn
    rows = await (
        await conn.execute(
            "SELECT id, topic, expert_count, status, created_at FROM sessions "
            "ORDER BY created_at, id"
        )
    ).fetchall()
    return {
        "sessions": [
            {
                "session_id": r[0],
                "topic": r[1],
                "expert_count": r[2],
                "status": r[3],
                "created_at": _iso(r[4]),
            }
            for r in rows
        ]
    }


async def _apply_command(request: Request, session_id: str, command_type: str, command_id: str) -> CommandOutcome:
    """命令共用路径：单一原子事务（receipt/状态/事件同生共死），路由层只做结果映射。
    事务提交后以精确 seq 广播 state_changed（G3：event_store 注入点）。

    NOT_FOUND → 404；UNKNOWN_COMMAND / CONFLICT → 409；DUPLICATE / APPLIED → 202。
    幂等命中发生在事务内部（重复 command_id 返回第一次接受的 202，不重复副作用）。
    返回值供 panel/generate 区分 APPLIED（触发执行体）与 DUPLICATE（幂等重放，不重复副作用）。
    """
    outcome = await transactions.execute_command(
        request.app.state.conn, session_id, command_type, command_id,
        event_store=request.app.state.event_store,
    )
    if outcome is CommandOutcome.NOT_FOUND:
        raise HTTPException(status_code=404, detail="session not found")
    if outcome is CommandOutcome.UNKNOWN_COMMAND:
        raise HTTPException(status_code=409, detail="unknown retry operation")
    if outcome is CommandOutcome.CONFLICT:
        raise HTTPException(status_code=409, detail="invalid state transition")
    # DUPLICATE / APPLIED → 202（幂等重放或首次应用）；返回 outcome 供调用方判断
    return outcome


@router.post("/sessions/{id}/panel/generate", status_code=202)
async def panel_generate(id: str, body: CommandRequest, request: Request):
    """阵容生成命令：命令事务（draft/panel_ready → panel_generating）后同步执行阵容生成。

    执行体（panel_ops.generate）在命令事务之外调用 LLM 并原子回写：
    成功 → panel_ready + 阵容落库 + error_code 清空；
    失败 → draft（无旧阵容）/ panel_ready（保留旧阵容）+ error_code。
    幂等重放（DUPLICATE）不触发执行体：副作用只发生一次，202 语义不变。
    """
    outcome = await _apply_command(request, id, "panel/generate", body.command_id)
    if outcome is CommandOutcome.APPLIED:
        await panel_ops.generate(
            request.app.state.conn, request.app.state.llm, id,
            event_store=request.app.state.event_store,  # G3：commit_panel 回写提交后广播
        )


@router.post("/sessions/{id}/panel/confirm", status_code=202)
async def panel_confirm(id: str, body: CommandRequest, request: Request):
    await _apply_command(request, id, "panel/confirm", body.command_id)


@router.post("/sessions/{id}/discussion/start", status_code=202)
async def discussion_start(id: str, body: CommandRequest, request: Request):
    """CG-B 接线：命令 APPLIED 后启动**持续运行**（max_turns=None）的引擎任务并登记
    registry；幂等重放（DUPLICATE）不重复启动；get_or_create 保证同 session 单引擎。
    track 拒绝（理论重复）时取消并等待新任务，绝不静默遗留重复任务。"""
    outcome = await _apply_command(request, id, "discussion/start", body.command_id)
    if outcome is CommandOutcome.APPLIED:
        registry = request.app.state.engine_registry

        async def _make_engine():
            return DiscussionEngine(
                id,
                request.app.state.llm,
                request.app.state.conn,
                max_turns=None,  # 生产持续运行（测试引擎显式 max_turns）
                event_store=request.app.state.event_store,
            )

        engine = await registry.get_or_create(id, _make_engine)
        task = asyncio.create_task(engine.start())
        if not await registry.track(id, task):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@router.post("/sessions/{id}/discussion/pause", status_code=202)
async def discussion_pause(id: str, body: CommandRequest, request: Request):
    """CG-B 接线：状态迁移 paused 后向引擎发暂停信号（阻塞下一轮检查点）；无引擎 no-op。"""
    outcome = await _apply_command(request, id, "discussion/pause", body.command_id)
    if outcome is CommandOutcome.APPLIED:
        engine = request.app.state.engine_registry.get_engine(id)  # 同步取
        if engine is not None:
            await engine.pause()


@router.post("/sessions/{id}/discussion/resume", status_code=202)
async def discussion_resume(id: str, body: CommandRequest, request: Request):
    """CG-B 接线：状态迁移 live 后向引擎发恢复信号（解除下一轮检查点）。"""
    outcome = await _apply_command(request, id, "discussion/resume", body.command_id)
    if outcome is CommandOutcome.APPLIED:
        engine = request.app.state.engine_registry.get_engine(id)
        if engine is not None:
            await engine.resume()


@router.post("/sessions/{id}/discussion/end", status_code=202)
async def discussion_end(id: str, body: CommandRequest, request: Request):
    """CG-B 接线：状态迁移 finalizing 后停止引擎并确定性收尾任务（cancel+await+清理，
    不遗留后台任务）；finalizing→completed 的 report 流程属 CG-C。"""
    outcome = await _apply_command(request, id, "discussion/end", body.command_id)
    if outcome is CommandOutcome.APPLIED:
        registry = request.app.state.engine_registry
        engine = registry.get_engine(id)
        if engine is not None:
            await engine.stop()  # 循环信号：下一 LLM 调用返回后检查点退出（不等待）
        await registry.stop(id)  # cancel+await+清理（引擎卡在 LLM 调用时 cancel 立即生效）


@router.post("/sessions/{id}/retry", status_code=202)
async def retry(id: str, body: CommandRequest, request: Request):
    """安全重试：retry_operation 在命令事务内解析（无路由外读取，无过期窗口）；
    重复 retry command_id 优先命中 receipt → 202；无待重试操作 → 409。"""
    await _apply_command(request, id, "retry", body.command_id)


@router.get("/sessions/{id}")
async def snapshot(id: str, request: Request):
    conn = request.app.state.conn
    snap = await get_session_snapshot(conn, id)
    if snap is None:
        raise HTTPException(status_code=404, detail="session not found")
    return snap


@router.get("/sessions/{id}/events")
async def events(id: str, request: Request, after_seq: str | None = None):
    conn = request.app.state.conn
    row = await (await conn.execute("SELECT 1 FROM sessions WHERE id=?", (id,))).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    # after_seq（首次/兼容）与 Last-Event-ID（浏览器自动重连）并存时取较大已确认序号
    seq = resolve_after_seq(after_seq, request.headers.get("last-event-id"))
    store = request.app.state.event_store
    return StreamingResponse(
        sse_stream(request, store, id, seq),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
