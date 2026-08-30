import { beforeEach, describe, it, expect, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Home } from "../src/pages/Home";
import { PanelSetup } from "../src/pages/PanelSetup";
import { Result } from "../src/pages/Result";
import { Studio } from "../src/pages/Studio";
import type { SSEEvent } from "../src/types";
import type { Snapshot } from "../src/store/types";

const SESSION = {
  session_id: "s1",
  topic: "AI",
  expert_count: 4,
  status: "draft",
  created_at: "c",
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

const envelope = (over: Partial<SSEEvent> = {}): SSEEvent => ({
  event: "x",
  sequence: 1,
  schema_version: 1,
  session_id: "s1",
  timestamp: "t",
  data: {},
  ...over,
});

const SNAP_DRAFT: Snapshot = {
  session_id: "s1",
  status: "draft",
  last_sequence: 0,
  topic: "AI 公平",
  expert_count: 4,
  transcript: [],
  insights: [],
  participants: [],
  summary: null,
};

const HOST = { id: "h1", session_id: "s1", role: "host", name: "周明远", profession: "科技评论员", title: "资深主编", stance: "中立理性", avatar_color: "#5B8DEF", avatar_emoji: "🎙️", runtime_state: "idle", public_focus: "" };
const EXPERT = { id: "e1", session_id: "s1", role: "expert", name: "林晓", profession: "经济学家", title: "教授", stance: "担忧", avatar_color: "#E4572E", avatar_emoji: "📉", runtime_state: "idle", public_focus: "" };

const SNAP_READY: Snapshot = { ...SNAP_DRAFT, status: "ready", participants: [HOST, EXPERT] };
const SNAP_LIVE: Snapshot = {
  ...SNAP_DRAFT,
  status: "live",
  last_sequence: 3,
  participants: [HOST, { ...EXPERT, runtime_state: "speaking" }],
  transcript: [
    { id: "u1", turn_id: "t1", speaker_id: "h1", role: "host", text: "欢迎讨论", ordinal: 1 },
  ],
  insights: [
    { id: "i1", kind: "consensus", text: "AI 提升效率", support_count: 3, oppose_count: 0, status: "active", version: 1 },
  ],
};
const SNAP_PAUSED: Snapshot = { ...SNAP_LIVE, status: "paused", last_sequence: 4 };

const REPORT_RAW = JSON.stringify({
  summary: "专家认为 AI 提升效率",
  key_consensus: ["AI 提升效率"],
  main_divergence: ["AI 加剧不平等"],
  unresolved_questions: ["再培训如何落地"],
  suggested_actions: ["建立再培训基金"],
});
const SNAP_COMPLETED: Snapshot = {
  ...SNAP_DRAFT,
  status: "completed",
  summary: REPORT_RAW,
  last_sequence: 6,
};

describe("Home", () => {
  it("列表加载成功：渲染会话卡片并带 hash 链接", async () => {
    const load = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ sessions: [SESSION] }),
    }));
    render(<Home deps={{ load }} />);
    expect(await screen.findByText("AI")).toBeInTheDocument();
    expect(screen.getByTestId("card-link").getAttribute("href")).toBe("#/panel?id=s1");
  });

  it("列表失败：显示「会话列表加载失败」，不被加载中遮蔽", async () => {
    const load = vi.fn(async () => ({ ok: false, status: 500 }));
    render(<Home deps={{ load }} />);
    expect(await screen.findByTestId("load-error")).toHaveTextContent("会话列表加载失败");
    expect(screen.queryByText("加载中…")).not.toBeInTheDocument();
  });

  it("空主题阻止提交：不调用 post 并显示校验错误", async () => {
    const load = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ sessions: [] }),
    }));
    const post = vi.fn();
    render(<Home deps={{ load, post }} />);
    await screen.findByText("暂无讨论，创建第一个吧");
    fireEvent.click(screen.getByTestId("create-btn"));
    expect(await screen.findByTestId("form-error")).toHaveTextContent("请输入讨论主题");
    expect(post).not.toHaveBeenCalled();
  });

  it("创建成功跳转 #/panel?id=…，请求体携带 topic/expert_count", async () => {
    const load = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ sessions: [] }),
    }));
    const post = vi.fn(async () => ({
      ok: true,
      status: 201,
      json: async () => ({ ...SESSION, session_id: "s9" }),
    }));
    render(<Home deps={{ load, post }} />);
    await screen.findByText("暂无讨论，创建第一个吧");
    fireEvent.change(screen.getByTestId("topic-input"), { target: { value: "新主题" } });
    fireEvent.click(screen.getByTestId("create-btn"));
    await waitFor(() => expect(window.location.hash).toBe("#/panel?id=s9"));
    expect(JSON.parse(post.mock.calls[0][1].body)).toEqual({ topic: "新主题", expert_count: 4 });
  });

  it("creating 期间防重复提交：只发一次 post", async () => {
    let resolvePost!: (v: { ok: boolean; status: number; json(): Promise<unknown> }) => void;
    const post = vi.fn(
      () =>
        new Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>((res) => {
          resolvePost = res;
        }),
    );
    const load = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ sessions: [] }),
    }));
    render(<Home deps={{ load, post }} />);
    await screen.findByText("暂无讨论，创建第一个吧");
    fireEvent.change(screen.getByTestId("topic-input"), { target: { value: "主题" } });
    fireEvent.click(screen.getByTestId("create-btn"));
    fireEvent.click(screen.getByTestId("create-btn")); // pending 中再点
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolvePost({ ok: true, status: 201, json: async () => ({ ...SESSION, session_id: "s9" }) });
    });
  });
});

describe("PanelSetup", () => {
  it("draft 快照：快照返回前不触发生成，返回后自动生成一次且不重复", async () => {
    let resolveFetch!: (v: { ok: boolean; status: number; json(): Promise<unknown> }) => void;
    const fetchImpl = vi.fn(
      () =>
        new Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>((res) => {
          resolveFetch = res;
        }),
    );
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<PanelSetup sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    expect(post).not.toHaveBeenCalled(); // 快照返回前：initial draft 不得触发
    await act(async () => {
      resolveFetch({ ok: true, status: 200, json: async () => SNAP_DRAFT });
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/sessions/s1/panel/generate");
    // 阵容与状态事件落地：渲染卡片，状态流转后不重复触发
    act(() => {
      FakeEventSource.instances[0].emit(
        "panel.generated",
        JSON.stringify(
          envelope({ event: "panel.generated", sequence: 1, data: { host: HOST, experts: [EXPERT] } }),
        ),
      );
      FakeEventSource.instances[0].emit(
        "session.state_changed",
        JSON.stringify(envelope({ event: "session.state_changed", sequence: 2, data: { state: "panel_ready" } })),
      );
    });
    expect(await screen.findByText("周明远")).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("快照获取失败：显示 session_load_failed，按钮禁用且点击不发命令", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("network down");
    });
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<PanelSetup sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByTestId("panel-error")).toHaveTextContent("session_load_failed");
    expect(screen.getByTestId("regenerate-btn")).toBeDisabled();
    expect(screen.getByTestId("confirm-btn")).toBeDisabled();
    fireEvent.click(screen.getByTestId("regenerate-btn"));
    fireEvent.click(screen.getByTestId("confirm-btn"));
    expect(post).not.toHaveBeenCalled();
  });

  it("快照 404：显示 session_not_found，按钮禁用、点击不发命令、不订阅 SSE", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 404 }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<PanelSetup sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByTestId("panel-error")).toHaveTextContent("session_not_found");
    expect(screen.getByTestId("regenerate-btn")).toBeDisabled();
    expect(screen.getByTestId("confirm-btn")).toBeDisabled();
    fireEvent.click(screen.getByTestId("regenerate-btn"));
    fireEvent.click(screen.getByTestId("confirm-btn"));
    expect(post).not.toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(0); // 不存在的会话不订阅
  });

  it("自动生成失败：提示「生成失败，请重试」且不自动重试", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_DRAFT }));
    const post = vi.fn(async () => ({ ok: false, status: 503 }));
    render(<PanelSetup sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByTestId("panel-error")).toHaveTextContent("生成失败，请重试");
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(post).toHaveBeenCalledTimes(1); // 不自动重试
  });

  it("panel_ready 快照恢复：快照返回前后均不触发生成；确认后跳转演播厅", async () => {
    let resolveFetch!: (v: { ok: boolean; status: number; json(): Promise<unknown> }) => void;
    const fetchImpl = vi.fn(
      () =>
        new Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>((res) => {
          resolveFetch = res;
        }),
    );
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<PanelSetup sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    expect(post).not.toHaveBeenCalled(); // 快照返回前
    await act(async () => {
      resolveFetch({
        ok: true,
        status: 200,
        json: async () => ({ ...SNAP_DRAFT, status: "panel_ready", participants: [HOST, EXPERT] }),
      });
    });
    expect(post).not.toHaveBeenCalled(); // panel_ready 恢复不触发生成
    expect(await screen.findByText("周明远")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("confirm-btn"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/sessions/s1/panel/confirm");
    await waitFor(() => expect(window.location.hash).toBe("#/studio?id=s1"));
  });

  it("pending 期间两个按钮均禁用，命令完成后恢复", async () => {
    let resolvePost!: (v: { ok: boolean; status: number; json(): Promise<unknown> }) => void;
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_DRAFT }));
    const post = vi.fn(
      () =>
        new Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>((res) => {
          resolvePost = res;
        }),
    );
    render(<PanelSetup sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1)); // 自动生成已触发、处于 pending
    expect(screen.getByTestId("regenerate-btn")).toBeDisabled();
    expect(screen.getByTestId("confirm-btn")).toBeDisabled();
    await act(async () => {
      resolvePost({ ok: true, status: 202, json: async () => undefined });
    });
    expect(screen.getByTestId("regenerate-btn")).toBeEnabled();
  });

  it("panel.generation_failed 事件：显示后端错误码", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_DRAFT }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<PanelSetup sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => {
      FakeEventSource.instances[0].emit(
        "panel.generation_failed",
        JSON.stringify(
          envelope({ event: "panel.generation_failed", sequence: 1, data: { error_code: "panel_generation_failed" } }),
        ),
      );
    });
    expect(await screen.findByTestId("panel-error")).toHaveTextContent("panel_generation_failed");
  });

  it("live 快照刷新：跳转 #/studio（不进错误页）", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...SNAP_DRAFT, status: "live" }),
    }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<PanelSetup sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    await waitFor(() => expect(window.location.hash).toBe("#/studio?id=s1"));
    expect(post).not.toHaveBeenCalled();
  });
});

describe("Studio", () => {
  it("live 快照渲染：席位/转录/洞察；仅暂停与结束可用", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_LIVE }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByText("资深主编")).toBeInTheDocument();
    expect(screen.getByText("发言")).toBeInTheDocument(); // 林晓 runtime_state=speaking
    expect(screen.getByText("欢迎讨论")).toBeInTheDocument(); // transcript
    expect(screen.getByText("AI 提升效率")).toBeInTheDocument(); // insight 共识
    expect(screen.getByText("AI 公平")).toBeInTheDocument(); // topic → focus
    expect(screen.getByTestId("pause-btn")).toBeEnabled();
    expect(screen.getByTestId("end-btn")).toBeEnabled();
    expect(screen.getByTestId("resume-btn")).toBeDisabled();
    expect(screen.getByTestId("start-btn")).toBeDisabled();
  });

  it("ready 快照：仅开始可用；点击开始发 POST，事件 live 后按钮切换", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_READY }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    await screen.findByText("资深主编");
    expect(screen.getByTestId("start-btn")).toBeEnabled();
    expect(screen.getByTestId("pause-btn")).toBeDisabled();
    expect(screen.getByTestId("resume-btn")).toBeDisabled();
    expect(screen.getByTestId("end-btn")).toBeDisabled();
    fireEvent.click(screen.getByTestId("start-btn"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/sessions/s1/discussion/start");
    act(() => {
      FakeEventSource.instances[0].emit(
        "session.state_changed",
        JSON.stringify(envelope({ event: "session.state_changed", sequence: 1, data: { state: "live" } })),
      );
    });
    await waitFor(() => expect(screen.getByTestId("pause-btn")).toBeEnabled());
    expect(screen.getByTestId("start-btn")).toBeDisabled();
  });

  it("paused 快照：仅继续与结束可用；点击继续发 POST", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_PAUSED }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    await screen.findByText("资深主编");
    expect(screen.getByTestId("resume-btn")).toBeEnabled();
    expect(screen.getByTestId("end-btn")).toBeEnabled();
    expect(screen.getByTestId("pause-btn")).toBeDisabled();
    expect(screen.getByTestId("start-btn")).toBeDisabled();
    fireEvent.click(screen.getByTestId("resume-btn"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/sessions/s1/discussion/resume");
  });

  it("live 点击暂停：POST pause；事件 paused 后按钮切换", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_LIVE }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    await screen.findByText("资深主编");
    fireEvent.click(screen.getByTestId("pause-btn"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/sessions/s1/discussion/pause");
    act(() => {
      FakeEventSource.instances[0].emit(
        "session.state_changed",
        JSON.stringify(envelope({ event: "session.state_changed", sequence: 4, data: { state: "paused" } })),
      );
    });
    await waitFor(() => expect(screen.getByTestId("resume-btn")).toBeEnabled());
    expect(screen.getByTestId("pause-btn")).toBeDisabled();
  });

  it("live 点击结束：POST end；事件 completed 后跳转结果页", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_LIVE }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    await screen.findByText("资深主编");
    fireEvent.click(screen.getByTestId("end-btn"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/sessions/s1/discussion/end");
    act(() => {
      FakeEventSource.instances[0].emit(
        "session.state_changed",
        JSON.stringify(envelope({ event: "session.state_changed", sequence: 4, data: { state: "completed" } })),
      );
    });
    await waitFor(() => expect(window.location.hash).toBe("#/result?id=s1"));
  });

  it("命令失败显示本地错误；后端错误码优先覆盖", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_LIVE }));
    const post = vi.fn(async () => ({ ok: false, status: 503 }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    await screen.findByText("资深主编");
    fireEvent.click(screen.getByTestId("pause-btn"));
    expect(await screen.findByTestId("studio-error")).toHaveTextContent("暂停失败，请重试");
    act(() => {
      FakeEventSource.instances[0].emit(
        "session.state_changed",
        JSON.stringify(
          envelope({
            event: "session.state_changed",
            sequence: 4,
            data: { state: "live", error_code: "transition_failed" },
          }),
        ),
      );
    });
    await waitFor(() =>
      expect(screen.getByTestId("studio-error")).toHaveTextContent("transition_failed"),
    );
  });

  it("阵容阶段快照刷新：draft/panel_ready → 阵容页；finalizing → 结果页", async () => {
    for (const status of ["draft", "panel_ready"]) {
      const fetchImpl = vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ ...SNAP_DRAFT, status }),
      }));
      render(<Studio sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
      await waitFor(() => expect(window.location.hash).toBe("#/panel?id=s1"));
    }
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...SNAP_DRAFT, status: "finalizing" }),
    }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    await waitFor(() => expect(window.location.hash).toBe("#/result?id=s1"));
  });

  it("快照尚未返回时不改 hash；live 落地后仍停在 Studio", async () => {
    let resolveFetch!: (v: { ok: boolean; status: number; json(): Promise<unknown> }) => void;
    const fetchImpl = vi.fn(
      () =>
        new Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>((res) => {
          resolveFetch = res;
        }),
    );
    window.location.hash = "#/studio?id=s1"; // 模拟用户已位于演播厅页
    render(<Studio sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    await act(async () => {}); // 冲刷 effect：初始 draft 不得触发重定向
    expect(window.location.hash).toBe("#/studio?id=s1");
    await act(async () => {
      resolveFetch({ ok: true, status: 200, json: async () => SNAP_LIVE });
    });
    await waitFor(() => expect(screen.getByText("资深主编")).toBeInTheDocument());
    expect(window.location.hash).toBe("#/studio?id=s1"); // live 不在跳转分支
  });

  it("绕过 UI 的不合法状态 handler 不发送 POST", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => SNAP_READY }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    await screen.findByText("资深主编");
    // ready 下 pause/resume/end 非法：移除 disabled 保护直达 handler，状态早退必须拦截
    screen.getByTestId("pause-btn").removeAttribute("disabled");
    fireEvent.click(screen.getByTestId("pause-btn"));
    screen.getByTestId("resume-btn").removeAttribute("disabled");
    fireEvent.click(screen.getByTestId("resume-btn"));
    screen.getByTestId("end-btn").removeAttribute("disabled");
    fireEvent.click(screen.getByTestId("end-btn"));
    // start 在 ready 下合法 → 唯一应发出的请求
    screen.getByTestId("start-btn").removeAttribute("disabled");
    fireEvent.click(screen.getByTestId("start-btn"));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/sessions/s1/discussion/start");
  });

  it("快照获取失败：session_load_failed、四按钮禁用、绕过 UI 点击不发 POST", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("network down");
    });
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByTestId("studio-error")).toHaveTextContent("session_load_failed");
    for (const id of ["start-btn", "pause-btn", "resume-btn", "end-btn"]) {
      expect(screen.getByTestId(id)).toBeDisabled();
      screen.getByTestId(id).removeAttribute("disabled");
      fireEvent.click(screen.getByTestId(id));
    }
    expect(post).not.toHaveBeenCalled();
  });

  it("快照 404：session_not_found、四按钮禁用、绕过 UI 点击不发 POST", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 404 }));
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    render(<Studio sessionId="s1" deps={{ fetchImpl, post, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByTestId("studio-error")).toHaveTextContent("session_not_found");
    for (const id of ["start-btn", "pause-btn", "resume-btn", "end-btn"]) {
      expect(screen.getByTestId(id)).toBeDisabled();
      screen.getByTestId(id).removeAttribute("disabled");
      fireEvent.click(screen.getByTestId(id));
    }
    expect(post).not.toHaveBeenCalled();
  });
});

describe("Result", () => {
  it("completed 渲染报告：五区块 + 原始 JSON，无错误", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => SNAP_COMPLETED,
    }));
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByText("专家认为 AI 提升效率")).toBeInTheDocument();
    expect(screen.getByText("AI 提升效率")).toBeInTheDocument(); // key_consensus
    expect(screen.getByText("AI 加剧不平等")).toBeInTheDocument(); // main_divergence
    expect(screen.getByText("再培训如何落地")).toBeInTheDocument(); // unresolved
    expect(screen.getByText("建立再培训基金")).toBeInTheDocument(); // suggested_actions
    expect(screen.getByText(REPORT_RAW)).toBeInTheDocument(); // pre.json 原始 JSON
    expect(screen.queryByTestId("result-error")).not.toBeInTheDocument();
  });

  it("finalizing：仅显示报告生成中", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...SNAP_DRAFT, status: "finalizing" }),
    }));
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByText("报告生成中…")).toBeInTheDocument();
    expect(screen.queryByTestId("result-error")).not.toBeInTheDocument();
  });

  it("finalizing + 滞留错误码：加载提示与错误码同屏，仅一个 result-error", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...SNAP_DRAFT, status: "finalizing" }),
    }));
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    await screen.findByTestId("result-loading");
    act(() => {
      FakeEventSource.instances[0].emit(
        "session.state_changed",
        JSON.stringify(
          envelope({
            event: "session.state_changed",
            sequence: 1,
            data: { state: "finalizing", error_code: "report_generation_failed" },
          }),
        ),
      );
    });
    expect(await screen.findByTestId("result-error")).toHaveTextContent("report_generation_failed");
    expect(screen.getByTestId("result-loading")).toHaveTextContent("报告生成中…");
    expect(screen.getAllByTestId("result-error")).toHaveLength(1);
  });

  it("failed：兜底文案先行，事件错误码覆盖", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...SNAP_DRAFT, status: "failed" }),
    }));
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByText("讨论失败，请重新开始")).toBeInTheDocument();
    act(() => {
      FakeEventSource.instances[0].emit(
        "session.state_changed",
        JSON.stringify(
          envelope({
            event: "session.state_changed",
            sequence: 1,
            data: { state: "failed", error_code: "report_generation_failed" },
          }),
        ),
      );
    });
    await waitFor(() =>
      expect(screen.getByTestId("result-error")).toHaveTextContent("report_generation_failed"),
    );
    expect(screen.getAllByTestId("result-error")).toHaveLength(1);
  });

  it('summary "{}"：报告暂不可用，不渲染空报告', async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...SNAP_DRAFT, status: "completed", summary: "{}" }),
    }));
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByTestId("result-unavailable")).toHaveTextContent("报告暂不可用");
    expect(screen.queryByTestId("result-error")).not.toBeInTheDocument();
  });

  it('summary "[]"：数组拒绝，报告暂不可用', async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...SNAP_DRAFT, status: "completed", summary: "[]" }),
    }));
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByTestId("result-unavailable")).toHaveTextContent("报告暂不可用");
    expect(screen.queryByTestId("result-error")).not.toBeInTheDocument();
  });

  it("刷新跳转：live → 演播厅；draft → 阵容页；finalizing 停留", async () => {
    for (const [status, target] of [
      ["live", "#/studio?id=s1"],
      ["draft", "#/panel?id=s1"],
    ] as [string, string][]) {
      const fetchImpl = vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ ...SNAP_DRAFT, status }),
      }));
      render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
      await waitFor(() => expect(window.location.hash).toBe(target));
    }
    window.location.hash = "#/result?id=s1"; // 模拟用户已在结果页
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...SNAP_DRAFT, status: "finalizing" }),
    }));
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    await screen.findByText("报告生成中…");
    expect(window.location.hash).toBe("#/result?id=s1"); // finalizing 停留结果页
  });

  it("快照尚未返回：hash 不变且显示加载中；completed 落地后停留", async () => {
    let resolveFetch!: (v: { ok: boolean; status: number; json(): Promise<unknown> }) => void;
    const fetchImpl = vi.fn(
      () =>
        new Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>((res) => {
          resolveFetch = res;
        }),
    );
    window.location.hash = "#/result?id=s1";
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    await act(async () => {}); // 冲刷 effect：初始 draft 不得触发重定向
    expect(window.location.hash).toBe("#/result?id=s1");
    expect(screen.getByTestId("result-loading")).toHaveTextContent("加载结果中…");
    await act(async () => {
      resolveFetch({ ok: true, status: 200, json: async () => SNAP_COMPLETED });
    });
    await waitFor(() => expect(screen.getByText("专家认为 AI 提升效率")).toBeInTheDocument());
    expect(window.location.hash).toBe("#/result?id=s1"); // completed 停留结果页
  });

  it("快照获取失败：统一错误分支显示错误码，无不可用/加载提示", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("network down");
    });
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByTestId("result-error")).toHaveTextContent("session_load_failed");
    expect(screen.queryByTestId("result-unavailable")).not.toBeInTheDocument();
    expect(screen.queryByTestId("result-loading")).not.toBeInTheDocument();
  });

  it("快照 404：统一错误分支显示错误码，无不可用/加载提示", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 404 }));
    render(<Result sessionId="s1" deps={{ fetchImpl, EventSourceImpl: FakeEventSource }} />);
    expect(await screen.findByTestId("result-error")).toHaveTextContent("session_not_found");
    expect(screen.queryByTestId("result-unavailable")).not.toBeInTheDocument();
    expect(screen.queryByTestId("result-loading")).not.toBeInTheDocument();
  });
});
