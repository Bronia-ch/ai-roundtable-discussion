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
    // 会话切换先复位：清空上一会话的内容/错误码，杜绝残留（新快照加载前不触发任何命令）
    setState(initialState());
    void (async () => {
      let snap: Snapshot | null = null;
      try {
        snap = await getSnapshot(sessionId, deps.fetchImpl);
      } catch {
        // 加载失败：结束加载并暴露错误码；sessionId 保持 null → 命令门禁失效（不发命令、按钮禁用）
        if (!cancelled) setState((s) => ({ ...s, hydrated: true, errorCode: "session_load_failed" }));
        return;
      }
      if (cancelled) return;
      if (snap !== null) {
        setState((s) => applySnapshot(s, snap));
        disconnect = connectEvents({
          sessionId,
          afterSeq: snap.last_sequence,
          onEvent: (ev) => {
            if (!cancelled) setState((s) => applyEvent(s, ev));
          },
          EventSourceImpl: deps.EventSourceImpl,
        });
      } else {
        // 404：会话不存在；结束加载、暴露错误码、保持 sessionId null、不建立 SSE 连接
        if (!cancelled) setState((s) => ({ ...s, hydrated: true, errorCode: "session_not_found" }));
      }
    })();
    return () => {
      cancelled = true;
      disconnect?.();
    };
  }, [sessionId, deps.fetchImpl, deps.EventSourceImpl]);
  return state;
}
