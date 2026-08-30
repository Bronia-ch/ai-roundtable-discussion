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
from app.core import transactions
from app.core.transactions import CommandOutcome

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
    await transactions.create_session(conn, session_id, body.topic, body.expert_count, created_at)
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


async def _apply_command(
    conn, session_id: str, command_type: str, command_id: str
) -> None:
    """命令共用路径：单一原子事务（receipt/状态/事件同生共死），路由层只做结果映射。

    NOT_FOUND → 404；UNKNOWN_COMMAND / CONFLICT → 409；DUPLICATE / APPLIED → 202。
    幂等命中发生在事务内部（重复 command_id 返回第一次接受的 202，不重复副作用）。
    T0.1 边界：命令的真实行为 = 状态机契约要求的状态变更与事件写入；
    领域执行体（阵容 LLM 生成、讨论引擎循环、finalizing 报告）属 T1/T5，另行接线。
    """
    outcome = await transactions.execute_command(conn, session_id, command_type, command_id)
    if outcome is CommandOutcome.NOT_FOUND:
        raise HTTPException(status_code=404, detail="session not found")
    if outcome is CommandOutcome.UNKNOWN_COMMAND:
        raise HTTPException(status_code=409, detail="unknown retry operation")
    if outcome is CommandOutcome.CONFLICT:
        raise HTTPException(status_code=409, detail="invalid state transition")
    # DUPLICATE / APPLIED → 202（幂等重放或首次应用）


@router.post("/sessions/{id}/panel/generate", status_code=202)
async def panel_generate(id: str, body: CommandRequest, request: Request):
    await _apply_command(request.app.state.conn, id, "panel/generate", body.command_id)


@router.post("/sessions/{id}/panel/confirm", status_code=202)
async def panel_confirm(id: str, body: CommandRequest, request: Request):
    await _apply_command(request.app.state.conn, id, "panel/confirm", body.command_id)


@router.post("/sessions/{id}/discussion/start", status_code=202)
async def discussion_start(id: str, body: CommandRequest, request: Request):
    await _apply_command(request.app.state.conn, id, "discussion/start", body.command_id)


@router.post("/sessions/{id}/discussion/pause", status_code=202)
async def discussion_pause(id: str, body: CommandRequest, request: Request):
    await _apply_command(request.app.state.conn, id, "discussion/pause", body.command_id)


@router.post("/sessions/{id}/discussion/resume", status_code=202)
async def discussion_resume(id: str, body: CommandRequest, request: Request):
    await _apply_command(request.app.state.conn, id, "discussion/resume", body.command_id)


@router.post("/sessions/{id}/discussion/end", status_code=202)
async def discussion_end(id: str, body: CommandRequest, request: Request):
    await _apply_command(request.app.state.conn, id, "discussion/end", body.command_id)


@router.post("/sessions/{id}/retry", status_code=202)
async def retry(id: str, body: CommandRequest, request: Request):
    """安全重试：retry_operation 在命令事务内解析（无路由外读取，无过期窗口）；
    重复 retry command_id 优先命中 receipt → 202；无待重试操作 → 409。"""
    await _apply_command(request.app.state.conn, id, "retry", body.command_id)


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
