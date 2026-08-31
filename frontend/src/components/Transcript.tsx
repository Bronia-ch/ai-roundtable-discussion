import { useEffect, useRef } from "react";
import type { Utterance } from "../types";

interface TranscriptProps {
  utterances: Utterance[];
  /** speaker_id → 姓名；缺省时展示 speaker_id。 */
  speakerNames?: Record<string, string>;
}

export function Transcript({ utterances, speakerNames }: TranscriptProps) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = endRef.current;
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [utterances.length]);
  return (
    <div className="transcript" data-testid="transcript">
      <div className="panel-heading"><span>实时发言</span><span>{utterances.length} 条</span></div>
      {utterances.length === 0 ? (
        <p className="empty">暂无发言</p>
      ) : (
        utterances.map((u, index) => (
          <div key={u.id} className="utterance">
            <span className="utterance-speaker">{speakerNames?.[u.speaker_id] ?? u.speaker_id}</span><span className="utterance-index">#{index + 1}</span>
            <p className="utterance-text">{u.text}</p>
          </div>
        ))
      )}
      <div ref={endRef} />
    </div>
  );
}
