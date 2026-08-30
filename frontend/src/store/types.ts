import type { Insight, Participant, SessionStatus, Utterance } from "../types";

/** 前端会话状态:由快照初始化,由 SSE 事件增量推进。 */
export interface SessionState {
  sessionId: string | null;
  status: SessionStatus;
  /** 快照已加载（或确认不存在/失败）；此前为 initial draft，不得据此触发命令。 */
  hydrated: boolean;
  transcript: Utterance[];
  insights: Insight[];
  participants: Participant[];
  lastSequence: number;
  errorCode: string | null;
  topic: string | null;
  /** 后端 expert_count；快照恢复（PanelSetup 展示用）。 */
  expertCount: number | null;
  /** 最终报告 JSON 字符串（discussion.completed 事件 / 快照恢复；未完成时为 null）。 */
  summary: string | null;
}

/** GET /sessions/{id} 的快照载荷（刷新恢复契约：含阵容与最终报告摘要）。 */
export interface Snapshot {
  session_id: string;
  status: SessionStatus;
  last_sequence: number;
  topic: string;
  expert_count: number;
  transcript: Utterance[];
  insights: Insight[];
  participants: Participant[];
  summary: string | null;
}
