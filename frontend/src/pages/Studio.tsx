import { useEffect, useState } from "react";
import { ParticipantSeat } from "../components/ParticipantSeat";
import { Transcript } from "../components/Transcript";
import { InsightPanel } from "../components/InsightPanel";
import { useSessionEvents } from "../store/useSessionEvents";
import { useStableCommand } from "../store/useCommand";
import type { SessionEventsDeps } from "../store/useSessionEvents";
import type { CommandPoster } from "../api/client";

export interface StudioDeps extends SessionEventsDeps {
  post?: CommandPoster;
}

export function Studio({ sessionId, deps }: { sessionId: string; deps?: StudioDeps }) {
  const state = useSessionEvents(sessionId, deps);
  const { run, pending } = useStableCommand(sessionId, deps?.post);
  const [commandError, setCommandError] = useState<string | null>(null);

  // 成功快照（hydrated 且会话对齐）才视为已加载会话；失败/404 结束加载但 sessionId 仍 null → 不匹配
  const isLoadedSession = state.hydrated && state.sessionId === sessionId;

  // 刷新一致性：先门禁，避免初始 draft 在快照返回前把 #/studio?id=… 误重定向到阵容页
  useEffect(() => {
    if (!isLoadedSession) return;
    if (
      state.status === "draft" ||
      state.status === "panel_generating" ||
      state.status === "panel_ready"
    ) {
      window.location.hash = `#/panel?id=${sessionId}`;
    } else if (
      state.status === "finalizing" ||
      state.status === "completed" ||
      state.status === "failed"
    ) {
      window.location.hash = `#/result?id=${sessionId}`;
    }
  }, [isLoadedSession, state.status, sessionId]);

  // 四枚按钮各自独立门控
  const canStart = isLoadedSession && !pending && state.status === "ready";
  const canPause = isLoadedSession && !pending && state.status === "live";
  const canResume = isLoadedSession && !pending && state.status === "paused";
  const canEnd =
    isLoadedSession && !pending && (state.status === "live" || state.status === "paused");

  // handler 早退：isLoadedSession/pending 之外，还各自校验状态（绕过 disabled 的调用路径也不发命令）
  const handleStart = async () => {
    if (!isLoadedSession || pending || state.status !== "ready") return;
    setCommandError(null);
    if (!(await run("discussion/start"))) setCommandError("开始失败，请重试");
  };
  const handlePause = async () => {
    if (!isLoadedSession || pending || state.status !== "live") return;
    setCommandError(null);
    if (!(await run("discussion/pause"))) setCommandError("暂停失败，请重试");
  };
  const handleResume = async () => {
    if (!isLoadedSession || pending || state.status !== "paused") return;
    setCommandError(null);
    if (!(await run("discussion/resume"))) setCommandError("继续失败，请重试");
  };
  const handleEnd = async () => {
    if (!isLoadedSession || pending || (state.status !== "live" && state.status !== "paused"))
      return;
    setCommandError(null);
    if (!(await run("discussion/end"))) setCommandError("结束失败，请重试");
  };

  // 单一错误展示：后端错误码优先，其次本地命令错误
  const errorText = state.errorCode ?? commandError;
  const statusLabel = ({ ready: "等待开始", live: "讨论进行中", paused: "已暂停" } as Record<string, string>)[state.status] ?? "同步中";

  // 发言席 speaker_id → 姓名（Transcript 展示用）
  const speakerNames: Record<string, string> = {};
  for (const p of state.participants) speakerNames[p.id] = p.name;

  return (
    <div className="page studio">
      <header className="studio-header">
        <div><span className="eyebrow">LIVE STUDIO</span><h1>圆桌演播厅</h1></div>
        <span className={`session-status status-${state.status}`}><i />{statusLabel}</span>
      </header>
      {errorText && (
        <p className="error" data-testid="studio-error">
          {errorText}
        </p>
      )}
      <div className="seats">
        {state.participants.map((p) => (
          <ParticipantSeat
            key={p.id}
            name={p.name}
            role={p.role}
            title={p.title}
            stance={p.stance}
            avatarColor={p.avatar_color}
            avatarEmoji={p.avatar_emoji}
            runtimeState={p.runtime_state}
          />
        ))}
      </div>
      <div className="studio-body">
        <Transcript utterances={state.transcript} speakerNames={speakerNames} />
        <InsightPanel focus={state.topic ?? ""} insights={state.insights} />
      </div>
      <div className="controls">
        <span className="control-hint">{pending ? "正在执行操作…" : statusLabel}</span>
        <button
          className="btn btn-primary"
          onClick={() => void handleStart()}
          disabled={!canStart}
          data-testid="start-btn"
        >
          开始讨论
        </button>
        <button
          className="btn"
          onClick={() => void handlePause()}
          disabled={!canPause}
          data-testid="pause-btn"
        >
          暂停
        </button>
        <button
          className="btn"
          onClick={() => void handleResume()}
          disabled={!canResume}
          data-testid="resume-btn"
        >
          继续
        </button>
        <button
          className="btn btn-danger"
          onClick={() => void handleEnd()}
          disabled={!canEnd}
          data-testid="end-btn"
        >
          结束讨论
        </button>
      </div>
    </div>
  );
}
