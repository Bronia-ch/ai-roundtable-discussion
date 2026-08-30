import type { SSEEvent } from "../types";

/** EventSource 的最小接口:真实 EventSource 与测试替身都满足。 */
export interface EventSourceLike {
  url: string;
  onerror: ((ev: Event) => void) | null;
  addEventListener(type: string, listener: (msg: { data: string }) => void): void;
  close(): void;
}

export interface ConnectOptions {
  sessionId: string;
  afterSeq: number;
  onEvent: (ev: SSEEvent) => void;
  onError?: () => void;
  EventSourceImpl?: new (url: string) => EventSourceLike;
}

/** 服务端会广播的帧类型;EventSource 按 `event:` 分发到 addEventListener,onmessage 不触发。 */
const EVENT_TYPES = [
  "session.state_changed",
  "panel.generated",
  "panel.generation_failed",
  "participant.state_changed",
  "utterance.completed",
  "intent.public",
  "insight.updated",
  "error.recoverable",
  "discussion.finalizing",
  "discussion.completed",
] as const;

/** 以 after_seq 续订 SSE;返回断开函数。 */
export function connectEvents(opts: ConnectOptions): () => void {
  const ES = opts.EventSourceImpl ?? window.EventSource;
  const es = new ES(`/sessions/${opts.sessionId}/events?after_seq=${opts.afterSeq}`);
  for (const type of EVENT_TYPES) {
    es.addEventListener(type, (msg) => {
      try {
        opts.onEvent(JSON.parse(msg.data) as SSEEvent);
      } catch {
        // 畸形帧忽略:浏览器自动重连 + after_seq 兜底
      }
    });
  }
  // 连接错误先关闭再通知,避免浏览器无限重连;回调自身异常不影响关闭
  es.onerror = () => {
    es.close();
    opts.onError?.();
  };
  return () => es.close();
}
