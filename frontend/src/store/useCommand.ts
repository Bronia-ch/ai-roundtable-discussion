import { useCallback, useRef, useState } from "react";
import type { CommandPoster } from "../api/client";
import { postCommand } from "../api/client";

/** 生成稳定 command_id（jsdom 无 crypto.randomUUID 时回退）。 */
export function newCommandId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c?.randomUUID) return c.randomUUID();
  return `cmd-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export interface UseStableCommandResult {
  /** 执行路径命令；pending 中或无 sessionId 返回 false。 */
  run: (path: string) => Promise<boolean>;
  pending: boolean;
}

/**
 * 稳定 command_id + 防重入（后端幂等键 = (session_id, command_id)，不含命令类型，
 * 见 transactions.py command_receipts 查询）：
 * - 同路径重试复用同一 id → 后端 DUPLICATE 202 幂等，副作用只发生一次；
 * - 换路径必须换新 id，否则被旧 receipt 误判 DUPLICATE 吞掉新命令；
 * - 成功清空 id（下次用新 id）；失败保留 id+path（网络失败但命令已应用的场景靠重试自愈）；
 * - pendingRef 防重入：请求期间重复调用返回 false（按钮禁用由 pending 驱动，双保险）。
 */
export function useStableCommand(
  sessionId: string | null,
  post: CommandPoster = fetch,
): UseStableCommandResult {
  const idRef = useRef<string | null>(null);
  const pathRef = useRef<string | null>(null);
  const pendingRef = useRef(false);
  const [pending, setPending] = useState(false);

  const run = useCallback(
    async (path: string): Promise<boolean> => {
      if (pendingRef.current || !sessionId) return false;
      pendingRef.current = true;
      setPending(true);
      try {
        if (idRef.current == null || pathRef.current !== path) {
          idRef.current = newCommandId();
          pathRef.current = path;
        }
        await postCommand(sessionId, path, idRef.current, post);
        idRef.current = null;
        pathRef.current = null;
        return true;
      } catch {
        return false; // 失败 → 保留 id+path，同路径重试复用（幂等 202）
      } finally {
        pendingRef.current = false;
        setPending(false);
      }
    },
    [sessionId, post],
  );

  return { run, pending };
}
