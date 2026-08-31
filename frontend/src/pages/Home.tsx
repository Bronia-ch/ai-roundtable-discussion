import { useEffect, useState } from "react";
import { DiscussionCard } from "../components/DiscussionCard";
import { createSession, deleteSession, listSessions } from "../api/client";
import type { JsonPoster, SessionDeleter, SessionItem, SnapshotLoader } from "../api/client";
import type { SessionStatus } from "../types";

export interface HomeDeps {
  /** 测试注入替身；缺省走真实 fetch。 */
  load?: SnapshotLoader;
  post?: JsonPoster;
  remove?: SessionDeleter;
}

export function Home({ deps }: { deps?: HomeDeps }) {
  const [sessions, setSessions] = useState<SessionItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
  const [expertCount, setExpertCount] = useState(4);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listSessions(deps?.load)
      .then((list) => {
        if (!cancelled) {
          setSessions(list);
          setLoadError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError("会话列表加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [deps?.load]);

  const handleCreate = async () => {
    if (creating) return;
    const trimmed = topic.trim();
    if (!trimmed) {
      setFormError("请输入讨论主题");
      return;
    }
    setCreating(true);
    setFormError(null);
    try {
      const created = await createSession(trimmed, expertCount, deps?.post);
      window.location.hash = `#/panel?id=${created.session_id}`;
    } catch {
      setFormError("创建失败，请重试");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (sessionId: string) => {
    if (deletingId) return;
    setDeletingId(sessionId);
    setDeleteError(null);
    try {
      await deleteSession(sessionId, deps?.remove);
      setSessions((current) => current?.filter((item) => item.session_id !== sessionId) ?? []);
    } catch {
      setDeleteError("删除失败，请稍后重试");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="page home">
      <header className="home-header">
        <div className="hero-copy">
          <span className="eyebrow">MULTI-AGENT DISCUSSION STUDIO</span>
          <h1>把一个复杂问题，交给一桌不同立场的专家</h1>
          <p>输入议题，AI 将组织主持人和专家阵容，实时沉淀共识、分歧与可执行结论。</p>
        </div>
        <form
          className="setup-form"
          onSubmit={(e) => {
            e.preventDefault();
            void handleCreate();
          }}
        >
          <label>
            讨论主题
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="例如：AI 会加剧社会不平等吗"
              data-testid="topic-input"
            />
          </label>
          <label>
            专家人数
            <select
              value={expertCount}
              onChange={(e) => setExpertCount(Number(e.target.value))}
              data-testid="expert-select"
            >
              {[3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n} 位
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="btn btn-primary" disabled={creating} data-testid="create-btn">
            {creating ? "创建中…" : "新建讨论"}
          </button>
        </form>
      </header>
      {formError && (
        <p className="error" data-testid="form-error">
          {formError}
        </p>
      )}
      {deleteError && <p className="error" data-testid="delete-error">{deleteError}</p>}
      {loadError ? (
        <p className="error" data-testid="load-error">
          {loadError}
        </p>
      ) : sessions === null ? (
        <p className="empty loading-pulse">正在加载讨论记录…</p>
      ) : sessions.length === 0 ? (
        <div className="empty-state"><strong>暂无讨论，创建第一个吧</strong><span>从上方输入一个值得深入分析的问题开始。</span></div>
      ) : (
        <section><div className="section-heading"><h2>最近讨论</h2><span>{sessions.length} 个会话</span></div><div className="discussion-list">
          {sessions.map((s) => (
            <DiscussionCard
              key={s.session_id}
              topic={s.topic}
              status={s.status as SessionStatus}
              sessionId={s.session_id}
              expertCount={s.expert_count}
              deleting={deletingId === s.session_id}
              onDelete={() => handleDelete(s.session_id)}
            />
          ))}
        </div></section>
      )}
    </div>
  );
}
