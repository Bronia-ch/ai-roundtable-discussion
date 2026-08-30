import { useEffect, useState } from "react";

import { getSnapshot } from "../api/client";
import type { SnapshotLoader } from "../api/client";
import { connectEvents } from "../api/sse";
import type { EventSourceLike } from "../api/sse";
import { applyEvent, applySnapshot, initialState } from "./applyEvent";
import type { SessionState, Snapshot } from "./types";

export interface SessionEventsDeps {
  fetchImpl?: SnapshotLoader;
  EventSourceImpl?: new (url: string) => EventSourceLike;
}

/** 快照初始化 → 以快照 last_sequence 续订 SSE → 事件增量推进;卸载断开。 */
export function useSessionEvents(
  sessionId: string | null,
  deps: SessionEventsDeps = {},
): SessionState {
  const [state, setState] = useState<SessionState>(initialState);
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    let disconnect: (() => void) | null = null;
    void (async () => {
      let snap: Snapshot | null = null;
      try {
        snap = await getSnapshot(sessionId, deps.fetchImpl);
      } catch {
        return; // 快照失败：保持初始状态、不创建订阅、无未处理拒绝；错误提示与重试留待后续阶段
      }
      if (cancelled) return;
      let afterSeq = 0;
      if (snap !== null) {
        setState((s) => applySnapshot(s, snap));
        afterSeq = snap.last_sequence;
      }
      disconnect = connectEvents({
        sessionId,
        afterSeq,
        onEvent: (ev) => {
          if (!cancelled) setState((s) => applyEvent(s, ev));
        },
        EventSourceImpl: deps.EventSourceImpl,
      });
    })();
    return () => {
      cancelled = true;
      disconnect?.();
    };
  }, [sessionId, deps.fetchImpl, deps.EventSourceImpl]);
  return state;
}
