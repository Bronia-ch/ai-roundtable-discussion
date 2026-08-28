import { ParticipantSeat } from "../components/ParticipantSeat";
import { Transcript } from "../components/Transcript";
import { InsightPanel } from "../components/InsightPanel";
import type { Utterance, Insight } from "../types";

const SEATS = [
  { name: "周明远", role: "host" as const, title: "资深主编", stance: "中立理性", avatarColor: "#5B8DEF", avatarEmoji: "🎙️", runtimeState: "idle" as const },
  { name: "林晓", role: "expert" as const, title: "教授", stance: "担忧：AI 红利集中于资本方", avatarColor: "#E4572E", avatarEmoji: "📉", runtimeState: "speaking" as const },
  { name: "陈曦", role: "expert" as const, title: "实验室主任", stance: "乐观：AI 可普惠化", avatarColor: "#2EA66E", avatarEmoji: "🤖", runtimeState: "preparing" as const },
  { name: "王芳", role: "expert" as const, title: "副教授", stance: "警惕：数字鸿沟扩大", avatarColor: "#8E44AD", avatarEmoji: "🧭", runtimeState: "waiting" as const },
];

const UTTERANCES: Utterance[] = [
  { id: "u1", turn_id: "t1", speaker_id: "周明远", role: "host", text: "欢迎来到今天的圆桌讨论，我们聚焦人工智能与社会公平。", ordinal: 1 },
  { id: "u2", turn_id: "t2", speaker_id: "林晓", role: "expert", text: "AI 红利明显向资本方集中，这是结构性风险。", ordinal: 2 },
];

const INSIGHTS: Insight[] = [
  { id: "i1", kind: "consensus", text: "AI 提升整体效率", support_count: 3, oppose_count: 0, status: "active", version: 1 },
  { id: "i2", kind: "divergence", text: "AI 是否加剧不平等", support_count: 2, oppose_count: 2, status: "active", version: 1 },
  { id: "i3", kind: "open_question", text: "再培训体系如何落地", support_count: 0, oppose_count: 0, status: "active", version: 1 },
];

export function Studio() {
  return (
    <div className="page studio">
      <div className="seats">
        {SEATS.map((s) => (
          <ParticipantSeat key={s.name} {...s} />
        ))}
      </div>
      <div className="studio-body">
        <Transcript utterances={UTTERANCES} />
        <InsightPanel focus="AI 是否加剧社会不平等" insights={INSIGHTS} />
      </div>
      <div className="controls">
        <button className="btn btn-primary">开始讨论</button>
        <button className="btn">暂停</button>
        <button className="btn btn-danger">结束讨论</button>
      </div>
    </div>
  );
}
