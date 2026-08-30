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
    # 刷新恢复契约：阵容/摘要字段始终存在（无阵容 → 空数组；无报告 → None）
    assert snap["participants"] == []
    assert snap["summary"] is None


@pytest.mark.asyncio
async def test_snapshot_includes_panel_after_generation(conn):
    """刷新恢复契约：panel/generate 落库后快照返回全量阵容（与 panel.generated 事件同构）。"""
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'panel_ready')"
    )
    await conn.execute(
        "INSERT INTO participants (id, session_id, role, name, profession, title, stance, "
        "avatar_color, avatar_emoji, sort_order, runtime_state, public_focus) VALUES "
        "('h1','s1','host','周','AI 研究者','教授','支持 AI','#111111','🎙️',0,'idle',''),"
        "('e1','s1','expert','林','律师','合伙人','审慎','#222222','🤖',1,'waiting','')"
    )
    await conn.commit()
    snap = await get_session_snapshot(conn, "s1")
    assert [p["name"] for p in snap["participants"]] == ["周", "林"]
    assert snap["participants"][0]["role"] == "host"
    assert snap["participants"][0]["runtime_state"] == "idle"
    assert snap["participants"][1]["avatar_color"] == "#222222"
    assert snap["summary"] is None


@pytest.mark.asyncio
async def test_snapshot_includes_report_summary_after_completion(conn):
    """刷新恢复契约：completed 会话快照返回最终报告 raw_json
    （与 discussion.completed 事件 data.summary 同源同串）。"""
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'finalizing')"
    )
    await conn.commit()
    seq = await transactions.commit_report(
        conn, "s1", {"summary": "讨论完成", "key_consensus": ["共识一"]},
        '{"summary": "讨论完成", "key_consensus": ["共识一"]}',
    )
    assert seq == 2  # 事件对：state_changed(completed) + discussion.completed
    snap = await get_session_snapshot(conn, "s1")
    assert snap["status"] == "completed"
    assert snap["last_sequence"] == 2
    assert snap["summary"] == '{"summary": "讨论完成", "key_consensus": ["共识一"]}'
