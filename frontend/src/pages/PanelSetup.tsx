import { useEffect, useRef, useState } from "react";
import { PanelCard } from "../components/PanelCard";
import { useSessionEvents } from "../store/useSessionEvents";
import { useStableCommand } from "../store/useCommand";
import type { SessionEventsDeps } from "../store/useSessionEvents";
import type { CommandPoster } from "../api/client";

/** 阵容阶段之后的会话状态 → 跳转页面（刷新一致性：不进错误页）。 */
const POST_PANEL: Record<string, string> = {
  ready: "/studio",
  live: "/studio",
  paused: "/studio",
  finalizing: "/result",
  completed: "/result",
  failed: "/result",
};

export interface PanelSetupDeps extends SessionEventsDeps {
  post?: CommandPoster;
}

export function PanelSetup({ sessionId, deps }: { sessionId: string; deps?: PanelSetupDeps }) {
  const state = useSessionEvents(sessionId, deps);
  const { run, pending } = useStableCommand(sessionId, deps?.post);
  const [commandError, setCommandError] = useState<string | null>(null);
  const autoTriggeredRef = useRef(false);

  // 成功快照（hydrated 且会话对齐）才视为已加载会话；失败/404 结束加载但 sessionId 仍 null → 不匹配
  const isLoadedSession = state.hydrated && state.sessionId === sessionId;

  // 自动生成门禁：已加载会话 + draft + 未触发过 + 非 pending
  useEffect(() => {
    if (isLoadedSession && state.status === "draft" && !autoTriggeredRef.current && !pending) {
      autoTriggeredRef.current = true;
      void run("panel/generate").then((ok) => {
        if (!ok) setCommandError("生成失败，请重试");
      });
    }
  }, [isLoadedSession, state.status, pending, run]);

  // 刷新一致性：已过阵容阶段的会话跳转到对应页面
  useEffect(() => {
    const target = POST_PANEL[state.status];
    if (target) window.location.hash = `#${target}?id=${sessionId}`;
  }, [state.status, sessionId]);

  const canGenerate = isLoadedSession && !pending && state.status !== "panel_generating";
  const canConfirm = isLoadedSession && !pending && state.status === "panel_ready";

  const handleGenerate = async () => {
    if (!isLoadedSession || pending) return; // 双保险：绕过 disabled 的调用路径也早退
    setCommandError(null);
    if (!(await run("panel/generate"))) setCommandError("生成失败，请重试");
  };

  const handleConfirm = async () => {
    if (!isLoadedSession || pending) return;
    setCommandError(null);
    if (!(await run("panel/confirm"))) {
      setCommandError("确认失败，请重试");
      return;
    }
    window.location.hash = `#/studio?id=${sessionId}`;
  };

  // 单一错误展示：后端错误码优先，其次本地命令错误
  const errorText = state.errorCode ?? commandError;

  return (
    <div className="page panel-setup">
      <h1>阵容确认</h1>
      <div className="setup-form">
        <label>
          讨论主题
          <input value={state.topic ?? ""} disabled data-testid="panel-topic" />
        </label>
        <label>
          专家人数
          <input value={state.expertCount ?? 4} disabled data-testid="panel-count" />
        </label>
      </div>
      {errorText && (
        <p className="error" data-testid="panel-error">
          {errorText}
        </p>
      )}
      {state.status === "draft" || state.status === "panel_generating" ? (
        <p className="empty" data-testid="panel-loading">
          {state.status === "panel_generating" ? "正在生成阵容…" : "准备生成阵容…"}
        </p>
      ) : (
        <div className="panel-list" data-testid="panel-list">
          {state.participants.map((p) => (
            <PanelCard
              key={p.id}
              name={p.name}
              role={p.role}
              profession={p.profession}
              title={p.title}
              stance={p.stance}
              avatarColor={p.avatar_color}
              avatarEmoji={p.avatar_emoji}
            />
          ))}
        </div>
      )}
      <div className="actions">
        <button
          className="btn"
          onClick={() => void handleGenerate()}
          disabled={!canGenerate}
          data-testid="regenerate-btn"
        >
          重新生成
        </button>
        <button
          className="btn btn-primary"
          onClick={() => void handleConfirm()}
          disabled={!canConfirm}
          data-testid="confirm-btn"
        >
          确认阵容并进入演播厅
        </button>
      </div>
    </div>
  );
}
