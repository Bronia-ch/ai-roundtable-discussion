import type { SessionStatus } from "../types";

const ROUTES: Record<SessionStatus, string> = {
  draft: "/panel",
  panel_generating: "/panel",
  panel_ready: "/panel",
  ready: "/studio",
  live: "/studio",
  paused: "/studio",
  finalizing: "/finalizing",
  completed: "/result",
  failed: "/failed",
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
  isSample?: boolean;
  expertCount?: number;
}

export function DiscussionCard({
  topic,
  status,
  isSample,
  expertCount = 4,
}: DiscussionCardProps) {
  return (
    <a href={ROUTES[status]} data-testid="card-link" className="discussion-card">
      <h3 className="card-topic">{topic}</h3>
      <div className="card-meta">
        <span className="badge" data-status={status}>
          {BADGES[status]}
        </span>
        {isSample && <span className="sample-tag">示例讨论</span>}
        <span className="expert-count">{expertCount} 位专家</span>
      </div>
    </a>
  );
}
