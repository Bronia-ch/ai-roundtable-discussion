const SUMMARY = "与会专家普遍认为 AI 提升了整体效率，但对红利分配与社会公平存在显著分歧。";
const CONSENSUS = ["AI 提升整体效率"];
const DIVERGENCE = ["AI 是否加剧社会不平等"];
const OPEN_QUESTIONS = ["再培训体系如何落地"];
const ACTIONS = ["建议建立劳动者再培训基金", "建议对 AI 红利征税用于社会保障"];

const RAW_JSON = JSON.stringify(
  { summary: SUMMARY, consensus: CONSENSUS, divergence: DIVERGENCE, openQuestions: OPEN_QUESTIONS, actions: ACTIONS },
  null,
  2,
);

export function Result() {
  return (
    <div className="page result">
      <h1>讨论结果</h1>
      <section className="result-section">
        <h2>摘要</h2>
        <p>{SUMMARY}</p>
      </section>
      <section className="result-section">
        <h2>关键共识</h2>
        <ul>{CONSENSUS.map((c) => <li key={c}>{c}</li>)}</ul>
      </section>
      <section className="result-section">
        <h2>主要分歧</h2>
        <ul>{DIVERGENCE.map((d) => <li key={d}>{d}</li>)}</ul>
      </section>
      <section className="result-section">
        <h2>未解决问题</h2>
        <ul>{OPEN_QUESTIONS.map((q) => <li key={q}>{q}</li>)}</ul>
      </section>
      <section className="result-section">
        <h2>建议行动</h2>
        <ul>{ACTIONS.map((a) => <li key={a}>{a}</li>)}</ul>
      </section>
      <section className="result-section">
        <h2>原始 JSON</h2>
        <pre className="json">{RAW_JSON}</pre>
      </section>
    </div>
  );
}
