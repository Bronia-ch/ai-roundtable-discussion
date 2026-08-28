import type { Utterance } from "../types";

interface TranscriptProps {
  utterances: Utterance[];
}

export function Transcript({ utterances }: TranscriptProps) {
  return (
    <div className="transcript" data-testid="transcript">
      {utterances.length === 0 ? (
        <p className="empty">暂无发言</p>
      ) : (
        utterances.map((u) => (
          <div key={u.id} className="utterance">
            <span className="utterance-speaker">{u.speaker_id}</span>
            <p className="utterance-text">{u.text}</p>
          </div>
        ))
      )}
    </div>
  );
}
