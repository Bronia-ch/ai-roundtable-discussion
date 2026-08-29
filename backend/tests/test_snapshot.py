import pytest

from app.api.snapshot import get_session_snapshot
from app.core import transactions


@pytest.mark.asyncio
async def test_snapshot_returns_state(conn):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'live')"
    )
    await conn.commit()
    await transactions.commit_event(conn, "s1", "session.state_changed", {"state": "live"}, {"status": "live"})
    snap = await get_session_snapshot(conn, "s1")
    assert snap["session_id"] == "s1"
    assert snap["status"] == "live"
    assert snap["last_sequence"] == 1
    assert "transcript" in snap
    assert "insights" in snap
