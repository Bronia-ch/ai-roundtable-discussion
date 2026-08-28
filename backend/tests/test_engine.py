import pytest

from app.core.engine import DiscussionEngine
from app.llm.fake import ScriptedLLMProvider


async def _setup(conn):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('s1', 't', 4, 'ready')"
    )
    for pid, role, sort in [("h1", "host", 0), ("e1", "expert", 1), ("e2", "expert", 2)]:
        await conn.execute(
            "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
            "VALUES (?, 's1', ?, 'n', 'p', 't', 's', '#111', '🤖', ?)",
            (pid, role, sort),
        )
    await conn.commit()


SCRIPT = {
    "host": {"text": "欢迎来到圆桌讨论"},
    "intent": {"items": [{"participant_id": "e1", "intent_type": "answer", "willingness": 0.9}]},
    "utterance": {"text": "我认为这个观点值得探讨"},
    "insight": {"create": {"kind": "focus", "text": "AI 红利分配"}},
    "report": {"summary": "讨论完成"},
}


@pytest.mark.asyncio
async def test_engine_lifecycle(conn):
    await _setup(conn)
    llm = ScriptedLLMProvider(SCRIPT)
    engine = DiscussionEngine("s1", llm, conn, max_turns=2)
    await engine.start()
    status = (await (await conn.execute("SELECT status FROM sessions WHERE id='s1'")).fetchone())[0]
    assert status == "live"
    count = (await (await conn.execute("SELECT COUNT(*) FROM utterances WHERE session_id='s1'")).fetchone())[0]
    assert count >= 2  # 开场 + 至少 1 专家发言
    await engine.end()
    status = (await (await conn.execute("SELECT status FROM sessions WHERE id='s1'")).fetchone())[0]
    assert status == "completed"
    reports = (
        await (await conn.execute("SELECT COUNT(*) FROM discussion_reports WHERE session_id='s1'")).fetchone()
    )[0]
    assert reports == 1
