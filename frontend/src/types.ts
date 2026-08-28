export type SessionStatus =
  | "draft"
  | "panel_generating"
  | "panel_ready"
  | "ready"
  | "live"
  | "paused"
  | "finalizing"
  | "completed"
  | "failed";

export interface Participant {
  id: string;
  session_id: string;
  role: "host" | "expert";
  name: string;
  profession: string;
  title: string;
  stance: string;
  avatar_color: string;
  avatar_emoji: string;
  runtime_state: string;
  public_focus: string;
}

export interface Utterance {
  id: string;
  turn_id: string;
  speaker_id: string;
  role: string;
  text: string;
  ordinal: number;
}

export interface Insight {
  id: string;
  kind: "focus" | "consensus" | "divergence" | "open_question";
  text: string;
  support_count: number;
  oppose_count: number;
  status: string;
  version: number;
}

export interface SSEEvent {
  event: string;
  sequence: number;
  schema_version: number;
  session_id: string;
  timestamp: string;
  data: any;
}
