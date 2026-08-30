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
    """先订阅再补发 after_seq 之后的事件：replay→subscribe 间隙的提交经队列送达不丢失；
    已补发事件按 last_sent_sequence 跳过，避免竞态重复；心跳保活；断线不停止讨论。"""
    q = event_store.subscribe(session_id)
    try:
        replayed = await event_store.replay(session_id, after_seq)
        last_sent_sequence = replayed[-1]["sequence"] if replayed else after_seq
        for ev in replayed:
            yield _sse_format(ev)
        while True:
            if await request.is_disconnected():
                break
            try:
                ev = await asyncio.wait_for(q.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if ev["sequence"] <= last_sent_sequence:
                continue
            last_sent_sequence = ev["sequence"]
            yield _sse_format(ev)
    finally:
        event_store.unsubscribe(session_id, q)
