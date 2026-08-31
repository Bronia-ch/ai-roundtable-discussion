import { useState } from "react";
import type { SessionStatus } from "../types";

const ROUTES: Record<SessionStatus, string> = {
  draft: "/panel",
  panel_generating: "/panel",
  panel_ready: "/panel",
  ready: "/studio",
  live: "/studio",
  paused: "/studio",
  finalizing: "/result", // 生成报告中 → 结果页展示进度
  completed: "/result",
  failed: "/result", // 失败 → 结果页展示错误
};

const BADGES: Record<SessionStatus, string> = {
  draft: "草稿",
  panel_generating: "生成阵容中",
  panel_ready: "待确认",
  ready: "已就绪",
  live: "进行中",
  paused: "已暂停",
  finalizing: "生成报告中",
  completed: "已完成",
  failed: "错误",
};

interface DiscussionCardProps {
  topic: string;
  status: SessionStatus;
  sessionId: string;
  isSample?: boolean;
  expertCount?: number;
  deleting?: boolean;
  onDelete?: () => void | Promise<void>;
}

export function DiscussionCard({
  topic,
  status,
  sessionId,
  isSample,
  expertCount = 4,
  deleting = false,
  onDelete,
}: DiscussionCardProps) {
  const [confirming, setConfirming] = useState(false);
  return (
    <article className="discussion-card">
      <a href={`#${ROUTES[status]}?id=${sessionId}`} data-testid="card-link" className="discussion-card-link">
        <h3 className="card-topic">{topic}</h3>
        <div className="card-meta">
          <span className="badge" data-status={status}>
            {BADGES[status]}
          </span>
          {isSample && <span className="sample-tag">示例讨论</span>}
          <span className="expert-count">{expertCount} 位专家</span>
        </div>
      </a>
      {onDelete && (
        <div className="card-actions">
          {confirming ? (
            <>
              <span>确定删除？</span>
              <button className="card-action danger" disabled={deleting} onClick={() => void onDelete()} data-testid={`confirm-delete-${sessionId}`}>
                {deleting ? "删除中…" : "确定"}
              </button>
              <button className="card-action" disabled={deleting} onClick={() => setConfirming(false)}>取消</button>
            </>
          ) : (
            <button className="card-action danger" onClick={() => setConfirming(true)} aria-label={`删除讨论：${topic}`} data-testid={`delete-${sessionId}`}>删除</button>
          )}
        </div>
      )}
    </article>
  );
}
