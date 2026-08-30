import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import { applyEvent, applySnapshot, initialState } from "../src/store/applyEvent";
import { connectEvents } from "../src/api/sse";
import { createSession, listSessions, postCommand } from "../src/api/client";
import { useSessionEvents } from "../src/store/useSessionEvents";
import type { SSEEvent } from "../src/types";
import type { Snapshot } from "../src/store/types";

const SNAPSHOT: Snapshot = {
  session_id: "s1",
  status: "live",
  last_sequence: 5,
  topic: "t",
  expert_count: 4,
  transcript: [
    { id: "u1", turn_id: "t1", speaker_id: "p1", role: "host", text: "欢迎", ordinal: 1 },
  ],
  insights: [
    { id: "i1", kind: "consensus", text: "x", support_count: 1, oppose_count: 0, status: "active", version: 1 },
  ],
  participants: [],
  summary: null,
};

const envelope = (over: Partial<SSEEvent> = {}): SSEEvent => ({
  event: "x",
  sequence: 1,
  schema_version: 1,
  session_id: "s1",
  timestamp: "t",
  data: {},
  ...over,
});

const UTTERANCE = {
  utterance_id: "u9",
  turn_id: "t9",
  speaker_id: "p9",
  role: "expert",
  text: "新观点",
};

/** 真实 EventSource 的替身：记录 URL，支持按 `event:` 类型分发帧。 */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  onerror: ((ev: Event) => void) | null = null;
  private listeners = new Map<string, ((msg: { data: string }) => void)[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (msg: { data: string }) => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type)!.push(listener);
  }

  emit(type: string, data: string) {
    for (const fn of this.listeners.get(type) ?? []) fn({ data });
  }

  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
});

const HOST = { id: "h1", session_id: "s1", role: "host", name: "周", profession: "p", title: "t", stance: "s", avatar_color: "#111", avatar_emoji: "🎙️", runtime_state: "idle", public_focus: "" };
const EXPERT = { id: "e1", session_id: "s1", role: "expert", name: "林", profession: "p", title: "t", stance: "s", avatar_color: "#222", avatar_emoji: "🤖", runtime_state: "idle", public_focus: "" };

describe("applySnapshot", () => {
  it("初始化为快照状态：状态、Transcript、洞察、last_sequence", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    expect(state.sessionId).toBe("s1");
    expect(state.status).toBe("live");
    expect(state.lastSequence).toBe(5);
    expect(state.transcript).toEqual(SNAPSHOT.transcript);
    expect(state.insights).toEqual(SNAPSHOT.insights);
    expect(state.topic).toBe("t");
    expect(state.participants).toEqual([]);
    expect(state.summary).toBeNull();
  });

  it("快照恢复阵容与摘要（刷新恢复契约：与 panel.generated / discussion.completed 事件同构）", () => {
    const snap: Snapshot = {
      ...SNAPSHOT,
      participants: [HOST, EXPERT],
      summary: '{"summary": "讨论完成"}',
    };
    const state = applySnapshot(initialState(), snap);
    expect(state.participants).toEqual([HOST, EXPERT]);
    expect(state.summary).toBe('{"summary": "讨论完成"}');
  });

  it("切换到新会话快照时以新快照阵容替换（会话隔离；阵容随快照恢复）", () => {
    const stateA = applySnapshot(initialState(), SNAPSHOT);
    const withPanel = applyEvent(
      stateA,
      envelope({ event: "panel.generated", sequence: 6, data: { host: HOST, experts: [EXPERT] } }),
    );
    expect(withPanel.participants).toHaveLength(2);
    const snapB: Snapshot = { ...SNAPSHOT, session_id: "s2", participants: [] };
    const stateB = applySnapshot(withPanel, snapB);
    expect(stateB.participants).toEqual([]);
    expect(stateB.sessionId).toBe("s2");
  });
});

describe("applyEvent", () => {
  it("忽略其他 session 的事件", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    const next = applyEvent(state, envelope({ sequence: 6, session_id: "s2" }));
    expect(next).toBe(state);
  });

  it("忽略 sequence <= lastSequence 的重连补发事件", () => {
    const state = applySnapshot(initialState(), SNAPSHOT); // lastSequence = 5
    const equal = applyEvent(
      state,
      envelope({ sequence: 5, event: "session.state_changed", data: { state: "completed" } }),
    );
    expect(equal).toBe(state);
    const older = applyEvent(state, envelope({ sequence: 4 }));
    expect(older).toBe(state);
  });

  it("重连只应用更大 sequence：旧序号不追加，新序号追加", () => {
    const state = applySnapshot(initialState(), SNAPSHOT); // lastSequence = 5
    const stale = applyEvent(
      state,
      envelope({ event: "utterance.completed", sequence: 4, data: UTTERANCE }),
    );
    expect(stale.transcript).toHaveLength(1);
    const fresh = applyEvent(
      state,
      envelope({ event: "utterance.completed", sequence: 6, data: UTTERANCE }),
    );
    expect(fresh.transcript.map((t) => t.id)).toEqual(["u1", "u9"]);
  });

  it("utterance.completed 追加一次，同一 utterance_id 不重复追加 Transcript", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    const once = applyEvent(
      state,
      envelope({ event: "utterance.completed", sequence: 6, data: UTTERANCE }),
    );
    expect(once.transcript.map((t) => t.id)).toEqual(["u1", "u9"]);
    const again = applyEvent(
      once,
      envelope({ event: "utterance.completed", sequence: 7, data: UTTERANCE }),
    );
    expect(again.transcript.map((t) => t.id)).toEqual(["u1", "u9"]);
  });

  it("实体去重时仍推进 lastSequence（补发事件视为已应用）", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    const once = applyEvent(
      state,
      envelope({ event: "utterance.completed", sequence: 6, data: UTTERANCE }),
    );
    const again = applyEvent(
      once,
      envelope({ event: "utterance.completed", sequence: 7, data: UTTERANCE }),
    );
    expect(again.lastSequence).toBe(7);
  });

  it("insight.updated 以累积快照整体替换（幂等、重连安全）", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    const snapshot = [
      { id: "i2", kind: "divergence", text: "y", support_count: 2, oppose_count: 2, status: "active", version: 2 },
    ];
    const next = applyEvent(
      state,
      envelope({ event: "insight.updated", sequence: 6, data: { snapshot, version: 2 } }),
    );
    expect(next.insights).toEqual(snapshot);
  });

  it("session.state_changed 更新状态", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    const next = applyEvent(
      state,
      envelope({ event: "session.state_changed", sequence: 6, data: { state: "paused" } }),
    );
    expect(next.status).toBe("paused");
  });

  it("panel.generated 设置参与人", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    const next = applyEvent(
      state,
      envelope({ event: "panel.generated", sequence: 6, data: { host: HOST, experts: [EXPERT] } }),
    );
    expect(next.participants).toEqual([HOST, EXPERT]);
  });

  it("participant.state_changed 更新席位 runtime_state", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    const withPanel = applyEvent(
      state,
      envelope({ event: "panel.generated", sequence: 6, data: { host: HOST, experts: [EXPERT] } }),
    );
    const next = applyEvent(
      withPanel,
      envelope({
        event: "participant.state_changed",
        sequence: 7,
        data: { participant_id: "e1", state: "speaking" },
      }),
    );
    expect(next.participants.find((p) => p.id === "e1")?.runtime_state).toBe("speaking");
    expect(next.participants.find((p) => p.id === "h1")?.runtime_state).toBe("idle");
  });

  it("discussion.completed 保存最终报告摘要", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    const next = applyEvent(
      state,
      envelope({
        event: "discussion.completed",
        sequence: 6,
        data: { summary: '{"summary": "讨论完成"}', result_ref: "r1" },
      }),
    );
    expect(next.summary).toBe('{"summary": "讨论完成"}');
  });

  it("panel.generation_failed 记录 errorCode", () => {
    const state = applySnapshot(initialState(), SNAPSHOT);
    const next = applyEvent(
      state,
      envelope({
        event: "panel.generation_failed",
        sequence: 6,
        data: { error_code: "panel_generation_failed" },
      }),
    );
    expect(next.errorCode).toBe("panel_generation_failed");
  });
});

describe("createSession", () => {
  it("POST /sessions 携带 topic/expert_count，返回会话条目", async () => {
    const post = vi.fn(async () => ({
      ok: true,
      status: 201,
      json: async () => ({
        session_id: "s9",
        topic: "AI",
        expert_count: 3,
        status: "draft",
        created_at: "t",
      }),
    }));
    const created = await createSession("AI", 3, post);
    expect(post).toHaveBeenCalledWith(
      "/sessions",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(post.mock.calls[0][1].body)).toEqual({ topic: "AI", expert_count: 3 });
    expect(created.session_id).toBe("s9");
  });

  it("非 2xx 抛错", async () => {
    const post = vi.fn(async () => ({
      ok: false,
      status: 422,
      json: async () => undefined,
    }));
    await expect(createSession("", 3, post)).rejects.toThrow("422");
  });
});

describe("listSessions", () => {
  it("GET /sessions 返回条目数组", async () => {
    const load = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        sessions: [
          { session_id: "s1", topic: "t", expert_count: 4, status: "draft", created_at: "c" },
        ],
      }),
    }));
    const sessions = await listSessions(load);
    expect(load).toHaveBeenCalledWith("/sessions");
    expect(sessions).toEqual([
      { session_id: "s1", topic: "t", expert_count: 4, status: "draft", created_at: "c" },
    ]);
  });

  it("非 2xx 抛错", async () => {
    const load = vi.fn(async () => ({ ok: false, status: 500 }));
    await expect(listSessions(load)).rejects.toThrow("500");
  });
});

describe("connectEvents", () => {
  it("以 after_seq 建立订阅，按 event 类型分发并解析 JSON 信封", () => {
    const onEvent = vi.fn();
    const disconnect = connectEvents({
      sessionId: "s1",
      afterSeq: 3,
      onEvent,
      EventSourceImpl: FakeEventSource,
    });
    const es = FakeEventSource.instances[0];
    expect(es.url).toBe("/sessions/s1/events?after_seq=3");
    es.emit(
      "utterance.completed",
      JSON.stringify(envelope({ event: "utterance.completed", sequence: 4, data: UTTERANCE })),
    );
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent.mock.calls[0][0]).toMatchObject({
      event: "utterance.completed",
      sequence: 4,
    });
    disconnect();
    expect(es.closed).toBe(true);
  });

  it("连接错误时关闭 EventSource，避免浏览器无限重连", () => {
    connectEvents({
      sessionId: "s1",
      afterSeq: 0,
      onEvent: vi.fn(),
      EventSourceImpl: FakeEventSource,
    });
    const es = FakeEventSource.instances[0];
    act(() => {
      es.onerror?.(new Event("error"));
    });
    expect(es.closed).toBe(true);
  });
});

describe("postCommand", () => {
  it("POST 命令到 /sessions/{id}/{path} 携带 command_id；非 2xx 抛错", async () => {
    const post = vi.fn(
      async (_url: string, _init: { method: string; body: string }) => ({
        ok: true,
        status: 202,
      }),
    );
    await postCommand("s1", "discussion/start", "cmd-1", post);
    expect(post).toHaveBeenCalledWith(
      "/sessions/s1/discussion/start",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(post.mock.calls[0][1].body)).toEqual({ command_id: "cmd-1" });
    const bad = vi.fn(async () => ({ ok: false, status: 501 }));
    await expect(postCommand("s1", "discussion/start", "cmd-1", bad)).rejects.toThrow("501");
  });
});

describe("useSessionEvents", () => {
  it("先取快照再以 last_sequence 续订；实时事件追加；卸载断开", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => SNAPSHOT,
    }));
    const { result, unmount } = renderHook(() =>
      useSessionEvents("s1", { fetchImpl, EventSourceImpl: FakeEventSource }),
    );
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0];
    expect(fetchImpl).toHaveBeenCalledWith("/sessions/s1");
    expect(es.url).toBe("/sessions/s1/events?after_seq=5"); // 快照的 last_sequence
    expect(result.current.sessionId).toBe("s1");
    expect(result.current.transcript).toHaveLength(1);
    act(() => {
      es.emit(
        "utterance.completed",
        JSON.stringify(envelope({ event: "utterance.completed", sequence: 6, data: UTTERANCE })),
      );
    });
    await waitFor(() => expect(result.current.transcript).toHaveLength(2));
    unmount();
    expect(es.closed).toBe(true);
  });

  it("getSnapshot 失败时保持初始状态、不订阅、无未处理拒绝", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("network down");
    });
    const unhandled: unknown[] = [];
    const onUnhandled = (e: PromiseRejectionEvent) => {
      unhandled.push(e.reason);
    };
    window.addEventListener("unhandledrejection", onUnhandled);
    const { result, unmount } = renderHook(() =>
      useSessionEvents("s1", { fetchImpl, EventSourceImpl: FakeEventSource }),
    );
    await act(async () => {});
    expect(unhandled).toHaveLength(0);
    expect(FakeEventSource.instances).toHaveLength(0);
    expect(result.current.sessionId).toBeNull();
    window.removeEventListener("unhandledrejection", onUnhandled);
    unmount();
  });

  it("卸载早于快照返回时不建立订阅", async () => {
    let resolveFetch!: (v: { ok: boolean; status: number; json(): Promise<unknown> }) => void;
    const fetchImpl = vi.fn(
      () =>
        new Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>((res) => {
          resolveFetch = res;
        }),
    );
    const { unmount } = renderHook(() =>
      useSessionEvents("s1", { fetchImpl, EventSourceImpl: FakeEventSource }),
    );
    unmount();
    await act(async () => {
      resolveFetch({ ok: true, status: 200, json: async () => SNAPSHOT });
    });
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("sessionId 切换时关闭旧连接并重新订阅新会话", async () => {
    const fetchImpl = vi.fn(async (url: string) => ({
      ok: true,
      status: 200,
      json: async () => ({ ...SNAPSHOT, session_id: url.split("/")[2] }),
    }));
    const { rerender } = renderHook(
      ({ id }) => useSessionEvents(id, { fetchImpl, EventSourceImpl: FakeEventSource }),
      { initialProps: { id: "s1" } },
    );
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const first = FakeEventSource.instances[0];
    expect(first.url).toBe("/sessions/s1/events?after_seq=5");
    rerender({ id: "s2" });
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(2));
    expect(first.closed).toBe(true);
    expect(FakeEventSource.instances[1].url).toBe("/sessions/s2/events?after_seq=5");
  });

  it("sessionId 切换先复位：新会话快照失败时不残留旧会话内容/错误码", async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      if (url.includes("/s2")) throw new Error("network down");
      return { ok: true, status: 200, json: async () => SNAPSHOT };
    });
    const { result, rerender } = renderHook(
      ({ id }) => useSessionEvents(id, { fetchImpl, EventSourceImpl: FakeEventSource }),
      { initialProps: { id: "s1" } },
    );
    await waitFor(() => expect(result.current.topic).toBe("t"));
    rerender({ id: "s2" });
    await waitFor(() => expect(result.current.errorCode).toBe("session_load_failed"));
    expect(result.current.sessionId).toBeNull();
    expect(result.current.topic).toBeNull();
    expect(result.current.transcript).toHaveLength(0);
    expect(result.current.participants).toEqual([]);
  });

  it("快照 404：设置 session_not_found 且不建立 SSE 订阅", async () => {
    FakeEventSource.instances = []; // 以本次测试为基准，断言未新增订阅
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 404 }));
    const { result } = renderHook(() =>
      useSessionEvents("s1", { fetchImpl, EventSourceImpl: FakeEventSource }),
    );
    await waitFor(() => expect(result.current.errorCode).toBe("session_not_found"));
    expect(result.current.hydrated).toBe(true);
    expect(result.current.sessionId).toBeNull();
    expect(FakeEventSource.instances).toHaveLength(0); // 不存在的会话不订阅
  });
});
