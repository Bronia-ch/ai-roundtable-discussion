import type { Snapshot } from "../store/types";

/** 可注入的 fetch 替身:便于测试注入桩实现。 */
export interface SnapshotLoader {
  (url: string): Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;
}

/** 取会话快照;404 视为会话不存在,返回 null。 */
export async function getSnapshot(
  sessionId: string,
  load: SnapshotLoader = fetch,
): Promise<Snapshot | null> {
  const res = await load(`/sessions/${sessionId}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`snapshot failed: ${res.status}`);
  return (await res.json()) as Snapshot;
}

export interface CommandPoster {
  (
    url: string,
    init: { method: string; headers: Record<string, string>; body: string },
  ): Promise<{ ok: boolean; status: number }>;
}

/** 发送会话命令(CG15 使用);非 2xx 抛错。 */
export async function postCommand(
  sessionId: string,
  path: string,
  commandId: string,
  post: CommandPoster = fetch,
): Promise<void> {
  const res = await post(`/sessions/${sessionId}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command_id: commandId }),
  });
  if (!res.ok) throw new Error(`command failed: ${res.status}`);
}
