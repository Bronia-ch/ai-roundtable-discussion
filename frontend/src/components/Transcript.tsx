import type { Utterance } from "../types";

interface TranscriptProps {
  utterances: Utterance[];
  /** speaker_id → 姓名；缺省时展示 speaker_id。 */
  speakerNames?: Record<string, string>;
}

export function Transcript({ utterances, speakerNames }: TranscriptProps) {
  return (
    <div className="transcript" data-testid="transcript">
      {utterances.length === 0 ? (
        <p className="empty">暂无发言</p>
      ) : (
        utterances.map((u) => (
          <div key={u.id} className="utterance">
            <span className="utterance-speaker">{speakerNames?.[u.speaker_id] ?? u.speaker_id}</span>
            <p className="utterance-text">{u.text}</p>
          </div>
        ))
      )}
    </div>
  );
}
