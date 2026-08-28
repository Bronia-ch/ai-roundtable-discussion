import { DiscussionCard } from "../components/DiscussionCard";
import type { SessionStatus } from "../types";

const DISCUSSIONS: {
  topic: string;
  status: SessionStatus;
  isSample?: boolean;
  expertCount: number;
}[] = [
  { topic: "人工智能是否会加剧社会不平等", status: "panel_ready", isSample: true, expertCount: 4 },
  { topic: "远程办公是未来主流还是过渡方案", status: "live", expertCount: 4 },
  { topic: "是否应该全面禁止燃油车", status: "completed", expertCount: 4 },
  { topic: "短视频对青少年的影响利大于弊吗", status: "paused", expertCount: 4 },
];

export function Home() {
  return (
    <div className="page home">
      <header className="home-header">
        <h1>AI 圆桌讨论</h1>
        <button className="btn btn-primary">新建讨论</button>
      </header>
      <div className="discussion-list">
        {DISCUSSIONS.map((d) => (
          <DiscussionCard key={d.topic} {...d} />
        ))}
      </div>
    </div>
  );
}
