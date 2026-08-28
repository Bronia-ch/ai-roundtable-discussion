from enum import Enum


class SessionState(str, Enum):
    DRAFT = "draft"
    PANEL_GENERATING = "panel_generating"
    PANEL_READY = "panel_ready"
    READY = "ready"
    LIVE = "live"
    PAUSED = "paused"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


# 严格迁移表（规格 §5.1）
TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.DRAFT: {SessionState.PANEL_GENERATING, SessionState.FAILED},
    SessionState.PANEL_GENERATING: {
        SessionState.PANEL_READY,
        SessionState.DRAFT,
        SessionState.FAILED,
    },
    SessionState.PANEL_READY: {
        SessionState.PANEL_GENERATING,
        SessionState.READY,
        SessionState.FAILED,
    },
    SessionState.READY: {SessionState.LIVE, SessionState.FAILED},
    SessionState.LIVE: {SessionState.PAUSED, SessionState.FINALIZING, SessionState.FAILED},
    SessionState.PAUSED: {SessionState.LIVE, SessionState.FINALIZING, SessionState.FAILED},
    SessionState.FINALIZING: {SessionState.COMPLETED, SessionState.FAILED},
    SessionState.COMPLETED: set(),
    SessionState.FAILED: set(),
}


def can_transition(src: SessionState, dst: SessionState) -> bool:
    return dst in TRANSITIONS.get(src, set())
