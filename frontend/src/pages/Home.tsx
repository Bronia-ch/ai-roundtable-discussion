import { useEffect, useState } from "react";
import { DiscussionCard } from "../components/DiscussionCard";
import { createSession, listSessions } from "../api/client";
import type { JsonPoster, SessionItem, SnapshotLoader } from "../api/client";
import type { SessionStatus } from "../types";

export interface HomeDeps {
  /** 测试注入替身；缺省走真实 fetch。 */
  load?: SnapshotLoader;
  post?: JsonPoster;
}

export function Home({ deps }: { deps?: HomeDeps }) {
  const [sessions, setSessions] = useState<SessionItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
  const [expertCount, setExpertCount] = useState(4);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

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

  return (
    <div className="page home">
      <header className="home-header">
        <h1>AI 圆桌讨论</h1>
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
      {loadError ? (
        <p className="error" data-testid="load-error">
          {loadError}
        </p>
      ) : sessions === null ? (
        <p className="empty">加载中…</p>
      ) : sessions.length === 0 ? (
        <p className="empty">暂无讨论，创建第一个吧</p>
      ) : (
        <div className="discussion-list">
          {sessions.map((s) => (
            <DiscussionCard
              key={s.session_id}
              topic={s.topic}
              status={s.status as SessionStatus}
              sessionId={s.session_id}
              expertCount={s.expert_count}
            />
          ))}
        </div>
      )}
    </div>
  );
}
