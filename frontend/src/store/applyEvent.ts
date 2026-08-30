import type { SSEEvent, Utterance } from "../types";
import type { SessionState, Snapshot } from "./types";

export function initialState(): SessionState {
  return {
    sessionId: null,
    status: "draft",
    hydrated: false,
    transcript: [],
    insights: [],
    participants: [],
    lastSequence: 0,
    errorCode: null,
    topic: null,
    expertCount: null,
    summary: null,
  };
}

export function applySnapshot(state: SessionState, snap: Snapshot): SessionState {
  return {
    ...state,
    hydrated: true,
    sessionId: snap.session_id,
    errorCode: null, // 成功快照复位错误码：避免上一会话（或此前失败）的错误码残留
    status: snap.status,
    transcript: snap.transcript,
    insights: snap.insights,
    // 快照契约含阵容与摘要：刷新后与 panel.generated / discussion.completed 事件同构
    participants: snap.participants,
    topic: snap.topic,
    expertCount: snap.expert_count,
    summary: snap.summary,
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
    case "participant.state_changed": {
      const d = ev.data as { participant_id?: string; state?: string };
      if (d.participant_id && d.state) {
        const state = d.state; // 局部变量：闭包内保持 string 窄化（属性访问不保留窄化）
        next.participants = next.participants.map((p) =>
          p.id === d.participant_id ? { ...p, runtime_state: state } : p,
        );
      }
      break;
    }
    case "panel.generation_failed": {
      const d = ev.data as { error_code?: string };
      if (d.error_code != null) next.errorCode = d.error_code;
      break;
    }
    case "discussion.completed": {
      const d = ev.data as { summary?: string; result_ref?: string };
      if (typeof d.summary === "string") next.summary = d.summary;
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
