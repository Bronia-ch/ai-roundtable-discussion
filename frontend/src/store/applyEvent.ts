import type { SSEEvent, Utterance } from "../types";
import type { SessionState, Snapshot } from "./types";

export function initialState(): SessionState {
  return {
    sessionId: null,
    status: "draft",
    transcript: [],
    insights: [],
    participants: [],
    lastSequence: 0,
    errorCode: null,
  };
}

export function applySnapshot(state: SessionState, snap: Snapshot): SessionState {
  return {
    ...state,
    sessionId: snap.session_id,
    status: snap.status,
    transcript: snap.transcript,
    insights: snap.insights,
    // 快照契约暂不含阵容；清空防止 A→B 会话切换时阵容串线（刷新恢复阵容为已知契约缺口，留待扩展快照契约）
    participants: [],
    lastSequence: snap.last_sequence,
  };
}

/**
 * 增量应用一个 SSE 事件。
 * - session 隔离:事件来自其他会话则原样返回;
 * - sequence 幂等:sequence <= lastSequence(重连补发)则原样返回;
 * - 实体幂等:utterance.completed 按 utterance_id 只追加一次,去重时仍推进 lastSequence;
 * - insight.updated 以累积快照整体替换。
 */
export function applyEvent(state: SessionState, ev: SSEEvent): SessionState {
  if (state.sessionId && ev.session_id !== state.sessionId) return state;
  if (ev.sequence <= state.lastSequence) return state;
  const next: SessionState = { ...state, lastSequence: ev.sequence };
  switch (ev.event) {
    case "session.state_changed": {
      next.status = ev.data.state;
      if (ev.data.error_code != null) next.errorCode = ev.data.error_code;
      break;
    }
    case "panel.generated": {
      next.participants = [ev.data.host, ...ev.data.experts];
      break;
    }
    case "utterance.completed": {
      const u = ev.data as {
        utterance_id: string;
        turn_id: string;
        speaker_id: string;
        role: string;
        text: string;
      };
      if (!next.transcript.some((t) => t.id === u.utterance_id)) {
        const utterance: Utterance = {
          id: u.utterance_id,
          turn_id: u.turn_id,
          speaker_id: u.speaker_id,
          role: u.role,
          text: u.text,
          ordinal: next.transcript.length + 1,
        };
        next.transcript = [...next.transcript, utterance];
      }
      break;
    }
    case "insight.updated": {
      next.insights = ev.data.snapshot;
      break;
    }
    default:
      break;
  }
  return next;
}
