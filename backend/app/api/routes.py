from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.snapshot import get_session_snapshot
from app.api.sse import resolve_after_seq, sse_stream

router = APIRouter()


def _not_implemented() -> None:
    raise HTTPException(status_code=501, detail="not implemented")


@router.post("/sessions/{id}/panel/generate")
async def panel_generate(id: str):
    _not_implemented()


@router.post("/sessions/{id}/panel/confirm")
async def panel_confirm(id: str):
    _not_implemented()


@router.post("/sessions/{id}/discussion/start")
async def discussion_start(id: str):
    _not_implemented()


@router.post("/sessions/{id}/discussion/pause")
async def discussion_pause(id: str):
    _not_implemented()


@router.post("/sessions/{id}/discussion/resume")
async def discussion_resume(id: str):
    _not_implemented()


@router.post("/sessions/{id}/discussion/end")
async def discussion_end(id: str):
    _not_implemented()


@router.post("/sessions/{id}/retry")
async def retry(id: str):
    _not_implemented()


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
