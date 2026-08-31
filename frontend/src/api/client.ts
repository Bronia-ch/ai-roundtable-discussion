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

/** GET /sessions 列表条目（严格五字段，见后端 SessionItem）。 */
export interface SessionItem {
  session_id: string;
  topic: string;
  expert_count: number;
  status: string;
  created_at: string;
}

/** 带 JSON 响应体的可注入 POST 替身（createSession 用；真实 fetch 满足）。 */
export interface JsonPoster {
  (
    url: string,
    init: { method: string; headers: Record<string, string>; body: string },
  ): Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;
}

export interface SessionDeleter {
  (url: string, init: { method: "DELETE" }): Promise<{ ok: boolean; status: number }>;
}

/** 新建会话：POST /sessions {topic, expert_count} → 201 会话条目（后端生成 id/时间）。 */
export async function createSession(
  topic: string,
  expertCount: number,
  post: JsonPoster = fetch,
): Promise<SessionItem> {
  const res = await post("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, expert_count: expertCount }),
  });
  if (!res.ok) throw new Error(`create session failed: ${res.status}`);
  return (await res.json()) as SessionItem;
}

/** 会话列表：GET /sessions → 条目数组（服务端按 created_at 稳定排序）。 */
export async function listSessions(load: SnapshotLoader = fetch): Promise<SessionItem[]> {
  const res = await load("/sessions");
  if (!res.ok) throw new Error(`list sessions failed: ${res.status}`);
  const body = (await res.json()) as { sessions: SessionItem[] };
  return body.sessions;
}

/** 删除会话及其发言、洞察和报告。 */
export async function deleteSession(
  sessionId: string,
  remove: SessionDeleter = fetch,
): Promise<void> {
  const res = await remove(`/sessions/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`delete session failed: ${res.status}`);
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
