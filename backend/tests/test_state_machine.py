from app.core.state_machine import SessionState, can_transition


def test_live_to_finalizing_allowed():
    assert can_transition(SessionState.LIVE, SessionState.FINALIZING)


def test_completed_is_terminal():
    assert not can_transition(SessionState.COMPLETED, SessionState.LIVE)
    assert not can_transition(SessionState.COMPLETED, SessionState.FAILED)


def test_failed_is_terminal():
    assert not can_transition(SessionState.FAILED, SessionState.LIVE)


def test_direct_panel_ready_to_live_rejected():
    assert not can_transition(SessionState.PANEL_READY, SessionState.LIVE)


def test_panel_generating_to_draft_allowed():
    assert can_transition(SessionState.PANEL_GENERATING, SessionState.DRAFT)


def test_ready_to_live_allowed():
    assert can_transition(SessionState.READY, SessionState.LIVE)
