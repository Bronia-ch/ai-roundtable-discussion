import asyncio
import json


def resolve_after_seq(after_seq_param: str | None, last_event_id: str | None) -> int:
    """after_seq 与 Last-Event-ID 并存时取较大已确认序号。"""
    seq = 0
    if after_seq_param:
        try:
            seq = max(seq, int(after_seq_param))
        except ValueError:
            pass
    if last_event_id:
        try:
            seq = max(seq, int(last_event_id))
        except ValueError:
            pass
    return seq


def _sse_format(envelope: dict) -> str:
    return f"id: {envelope['sequence']}\nevent: {envelope['event']}\ndata: {json.dumps(envelope, ensure_ascii=False)}\n\n"


async def sse_stream(request, event_store, session_id: str, after_seq: int, heartbeat_interval: float = 15.0):
    """先补发 after_seq 之后的事件，再订阅后续事件；心跳保活；断线不停止讨论。"""
    for ev in await event_store.replay(session_id, after_seq):
        yield _sse_format(ev)
    q = event_store.subscribe(session_id)
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                ev = await asyncio.wait_for(q.get(), timeout=heartbeat_interval)
                yield _sse_format(ev)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        event_store.unsubscribe(session_id, q)
