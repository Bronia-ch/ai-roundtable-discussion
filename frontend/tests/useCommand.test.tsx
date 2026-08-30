import { describe, it, expect, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useStableCommand } from "../src/store/useCommand";

/** 提取最近一次 post 的 command_id。 */
function lastCommandId(post: ReturnType<typeof vi.fn>): string {
  const [, init] = post.mock.calls.at(-1)!;
  return JSON.parse(init.body).command_id;
}

describe("useStableCommand", () => {
  it("同 session 同 path：第一次失败后重试复用完全相同的 command_id", async () => {
    const post = vi.fn(async () => ({ ok: false, status: 409 }));
    const { result } = renderHook(() => useStableCommand("s1", post));
    await act(async () => {
      await result.current.run("panel/generate");
    });
    expect(post).toHaveBeenCalledTimes(1);
    const id1 = lastCommandId(post);
    expect(id1).toBeTruthy();
    await act(async () => {
      await result.current.run("panel/generate");
    });
    expect(post).toHaveBeenCalledTimes(2);
    expect(lastCommandId(post)).toBe(id1);
  });

  it("同 session 换 path：前一路径失败后，新路径使用新的 command_id", async () => {
    const post = vi.fn(async () => ({ ok: false, status: 409 }));
    const { result } = renderHook(() => useStableCommand("s1", post));
    await act(async () => {
      await result.current.run("panel/generate");
    });
    await act(async () => {
      await result.current.run("panel/confirm");
    });
    expect(post).toHaveBeenCalledTimes(2);
    const id1 = JSON.parse(post.mock.calls[0][1].body).command_id;
    const id2 = JSON.parse(post.mock.calls[1][1].body).command_id;
    expect(id2).not.toBe(id1);
  });

  it("pending 期间再次 run 返回 false，且只发生一次 post", async () => {
    let resolvePost!: (v: { ok: boolean; status: number }) => void;
    const post = vi.fn(
      () =>
        new Promise<{ ok: boolean; status: number }>((res) => {
          resolvePost = res;
        }),
    );
    const { result } = renderHook(() => useStableCommand("s1", post));
    let first: boolean | null = null;
    act(() => {
      void result.current.run("discussion/start").then((v) => {
        first = v;
      });
    });
    expect(result.current.pending).toBe(true);
    let second: boolean | null = null;
    act(() => {
      void result.current.run("discussion/start").then((v) => {
        second = v;
      });
    });
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolvePost({ ok: true, status: 202 });
    });
    expect(first).toBe(true);
    expect(second).toBe(false);
    expect(result.current.pending).toBe(false);
  });

  it("成功后清空旧 id：下一次同路径命令使用新 id", async () => {
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    const { result } = renderHook(() => useStableCommand("s1", post));
    await act(async () => {
      await result.current.run("panel/generate");
    });
    await act(async () => {
      await result.current.run("panel/generate");
    });
    expect(post).toHaveBeenCalledTimes(2);
    const id1 = JSON.parse(post.mock.calls[0][1].body).command_id;
    const id2 = JSON.parse(post.mock.calls[1][1].body).command_id;
    expect(id1).toBeTruthy();
    expect(id2).not.toBe(id1);
  });

  it("sessionId 为 null 时不发请求并返回 false", async () => {
    const post = vi.fn(async () => ({ ok: true, status: 202 }));
    const { result } = renderHook(() => useStableCommand(null, post));
    let ok: boolean | null = null;
    await act(async () => {
      ok = await result.current.run("discussion/start");
    });
    expect(ok).toBe(false);
    expect(post).not.toHaveBeenCalled();
  });
});
