import type { Insight } from "../types";

interface InsightPanelProps {
  focus: string;
  insights: Insight[];
}

function Section({ title, items }: { title: string; items: Insight[] }) {
  return (
    <section className="insight-section">
      <h4>{title}</h4>
      {items.length === 0 ? (
        <p className="empty">暂无</p>
      ) : (
        items.map((i) => <p key={i.id}>{i.text}</p>)
      )}
    </section>
  );
}

export function InsightPanel({ focus, insights }: InsightPanelProps) {
  const consensus = insights.filter((i) => i.kind === "consensus");
  const divergence = insights.filter((i) => i.kind === "divergence");
  const openQuestions = insights.filter((i) => i.kind === "open_question");
  return (
    <aside className="insight-panel" data-testid="insight-panel">
      <div className="focus">
        <h4>当前关注点</h4>
        <p>{focus}</p>
      </div>
      <Section title="共识" items={consensus} />
      <Section title="分歧" items={divergence} />
      <Section title="未解决问题" items={openQuestions} />
    </aside>
  );
}
