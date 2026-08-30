import type { Insight, Participant, SessionStatus, Utterance } from "../types";

/** 前端会话状态:由快照初始化,由 SSE 事件增量推进。 */
export interface SessionState {
  sessionId: string | null;
  status: SessionStatus;
  transcript: Utterance[];
  insights: Insight[];
  participants: Participant[];
  lastSequence: number;
  errorCode: string | null;
}

/** GET /sessions/{id} 的快照载荷。 */
export interface Snapshot {
  session_id: string;
  status: SessionStatus;
  last_sequence: number;
  topic: string;
  expert_count: number;
  transcript: Utterance[];
  insights: Insight[];
}
