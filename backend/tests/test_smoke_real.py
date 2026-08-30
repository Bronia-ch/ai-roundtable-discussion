"""Task 4.6 真实 LLM 冒烟测试（默认 SKIPPED）。

仅当环境变量 SMOKE_REAL_LLM=1/true/yes 时才发起真实 DeepSeek 请求（产生费用）。
冒烟流程：建会话 → OpenAICompatProvider(Settings()) → 引擎 start（live、开场+1 轮）
→ end（completed、1 份报告）。离线矩阵中必须保持 SKIPPED。
"""

import os

import pytest

from app.config import Settings
from app.core.engine import DiscussionEngine
from app.llm.openai_compat import OpenAICompatProvider

pytestmark = pytest.mark.skipif(
    os.environ.get("SMOKE_REAL_LLM", "").lower() not in ("1", "true", "yes"),
    reason="SMOKE_REAL_LLM 未设置为 1/true/yes：不发起真实 LLM 请求",
)


async def _setup(conn):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status) VALUES ('smoke1', '冒烟主题', 4, 'ready')"
    )
    for pid, role, sort in [("h1", "host", 0), ("e1", "expert", 1), ("e2", "expert", 2)]:
        await conn.execute(
            "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
            "VALUES (?, 'smoke1', ?, 'n', 'p', 't', 's', '#111', '🤖', ?)",
            (pid, role, sort),
        )
    await conn.commit()


@pytest.mark.asyncio
async def test_real_deepseek_discussion(conn):
    """真实 DeepSeek 完整讨论冒烟：start→live→发言→end→completed→报告。"""
    settings = Settings()
    assert settings.api_key, "LLM_API_KEY 未设置"
    await _setup(conn)
    llm = OpenAICompatProvider(settings)
    engine = DiscussionEngine("smoke1", llm, conn, max_turns=1)
    await engine.start()
    status = (
        await (await conn.execute("SELECT status FROM sessions WHERE id='smoke1'")).fetchone()
    )[0]
    assert status == "live"
    count = (
        await (await conn.execute("SELECT COUNT(*) FROM utterances WHERE session_id='smoke1'")).fetchone()
    )[0]
    assert count >= 2  # 开场 + 至少 1 专家发言
    await engine.end()
    status = (
        await (await conn.execute("SELECT status FROM sessions WHERE id='smoke1'")).fetchone()
    )[0]
    assert status == "completed"
    reports = (
        await (
            await conn.execute(
                "SELECT COUNT(*) FROM discussion_reports WHERE session_id='smoke1'"
            )
        ).fetchone()
    )[0]
    assert reports == 1
