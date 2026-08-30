"""CG-A RED：panel 阵容生成接线（HTTP 行为契约）。

契约（规格 §5.1 迁移表 + §9.3 调用清单 #1）：
- panel/generate 成功：202 后，LLM 阵容响应落库 1 host + N expert（N=expert_count），
  状态 panel_generating → panel_ready。
- 首次生成失败（无旧阵容）：状态回到 draft，error_code 记录失败原因（可重新生成）。
- re-roll 失败（有旧阵容）：保持旧阵容 + 状态回 panel_ready，error_code 记录。

LLM 注入契约：路由从 request.app.state.llm 取 provider（测试挂 ScriptedLLMProvider；
GREEN 时 lifespan 装配真实 provider）。call_type="panel" 的响应形状：
{"host": {...}, "experts": [...]}（姓名/职业/Title/立场/头像颜色/头像 emoji）。

当前实现：panel/generate 仅执行纯状态迁移（draft→panel_generating）后停驻——
无 LLM 调用、无 participants 写入、无失败处理 → 三个场景全部失败（有效 RED）。

本文件只新增测试；不修改任何生产代码。
"""

import httpx
import pytest

from app import main
from app.core.event_store import EventStore
from app.llm.fake import ScriptedLLMProvider

HOST = {
    "name": "周明远",
    "profession": "科技评论员",
    "title": "资深主编",
    "stance": "中立理性",
    "avatar_color": "#5B8DEF",
    "avatar_emoji": "🎙️",
}
EXPERTS = [
    {"name": "林晓", "profession": "经济学家", "title": "教授", "stance": "担忧：AI 红利集中于资本方", "avatar_color": "#E4572E", "avatar_emoji": "📉"},
    {"name": "陈曦", "profession": "AI 研究员", "title": "实验室主任", "stance": "乐观：AI 可普惠化", "avatar_color": "#2EA66E", "avatar_emoji": "🤖"},
    {"name": "王芳", "profession": "社会学学者", "title": "副教授", "stance": "警惕：数字鸿沟扩大", "avatar_color": "#8E44AD", "avatar_emoji": "🧭"},
    {"name": "赵铁柱", "profession": "一线工人代表", "title": "工会委员", "stance": "关注：就业冲击与再培训", "avatar_color": "#B7791F", "avatar_emoji": "🔧"},
]
PANEL_OK = {"panel": {"host": HOST, "experts": EXPERTS}}
# 失败替身：脚本不含 "panel" 键 → ScriptedLLMProvider 抛 KeyError（无网络、无真实 LLM）
PANEL_FAIL = {}


async def _mount(conn, llm):
    """把测试连接与 LLM 替身挂到共享 app 上（生产 lifespan 的等价装配 + LLM 注入点）。"""
    main.app.state.conn = conn
    main.app.state.event_store = EventStore(conn)
    main.app.state.llm = llm


async def _seed(conn, sid, status="draft", topic="t", expert_count=4):
    await conn.execute(
        "INSERT INTO sessions (id, topic, expert_count, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, '2026-08-30T10:00:00Z', '2026-08-30T10:00:00Z')",
        (sid, topic, expert_count, status),
    )
    await conn.commit()


async def _old_panel(conn, sid):
    """插入"已有旧阵容"（re-roll 场景）：1 host + 2 expert。"""
    await conn.execute(
        "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
        "VALUES ('old_host', ?, 'host', '旧主持人', '职业', '头衔', '立场', '#111111', '🎙️', 0)",
        (sid,),
    )
    await conn.execute(
        "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
        "VALUES ('old_e1', ?, 'expert', '旧专家甲', '职业', '头衔', '立场', '#222222', '🤖', 1)",
        (sid,),
    )
    await conn.execute(
        "INSERT INTO participants (id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) "
        "VALUES ('old_e2', ?, 'expert', '旧专家乙', '职业', '头衔', '立场', '#333333', '🧠', 2)",
        (sid,),
    )
    await conn.commit()


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")


async def _session_row(conn, sid):
    return await (
        await conn.execute("SELECT status, error_code FROM sessions WHERE id=?", (sid,))
    ).fetchone()


async def _participants(conn, sid):
    rows = await (
        await conn.execute(
            "SELECT role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order "
            "FROM participants WHERE session_id=? ORDER BY sort_order",
            (sid,),
        )
    ).fetchall()
    return rows


# ---------------------------------------------------------------- 场景 1：生成成功

@pytest.mark.asyncio
async def test_panel_generate_success_persists_panel_and_panel_ready(conn):
    """202 后：1 host + 4 expert 落库（字段与脚本一致），状态进入 panel_ready。"""
    await _mount(conn, ScriptedLLMProvider(PANEL_OK))
    await _seed(conn, "s1")
    async with await _client() as c:
        r = await c.post("/sessions/s1/panel/generate", json={"command_id": "cmd-1"})
    assert r.status_code == 202
    status, error_code = await _session_row(conn, "s1")
    assert status == "panel_ready", f"生成成功后必须进入 panel_ready（当前：{status}）"
    assert error_code is None
    rows = await _participants(conn, "s1")
    assert len(rows) == 5, f"必须落库 1 host + 4 expert（当前：{len(rows)} 行）"
    assert [r[0] for r in rows] == ["host"] + ["expert"] * 4
    assert [r[7] for r in rows] == [0, 1, 2, 3, 4]
    assert rows[0][1] == HOST["name"]
    assert rows[0][4] == HOST["stance"]
    assert [r[1] for r in rows[1:]] == [e["name"] for e in EXPERTS]
    assert rows[1][2] == EXPERTS[0]["profession"]
    assert rows[1][3] == EXPERTS[0]["title"]
    assert rows[1][5] == EXPERTS[0]["avatar_color"]
    assert rows[1][6] == EXPERTS[0]["avatar_emoji"]


# ---------------------------------------------------------------- 场景 2：首次失败（无旧阵容）

@pytest.mark.asyncio
async def test_panel_generate_first_failure_returns_to_draft_with_error_code(conn):
    """生成失败且无旧阵容：回到 draft + error_code，零 participants 残留。"""
    await _mount(conn, ScriptedLLMProvider(PANEL_FAIL))
    await _seed(conn, "s1")
    async with await _client() as c:
        r = await c.post("/sessions/s1/panel/generate", json={"command_id": "cmd-1"})
    assert r.status_code == 202
    status, error_code = await _session_row(conn, "s1")
    assert status == "draft", f"首次生成失败且无旧阵容必须回到 draft（当前：{status}）"
    assert error_code, "失败必须记录 error_code"
    assert await _participants(conn, "s1") == []


# ---------------------------------------------------------------- 场景 3：re-roll 失败（有旧阵容）

@pytest.mark.asyncio
async def test_panel_reroll_failure_keeps_existing_panel_and_panel_ready(conn):
    """re-roll 失败但有旧阵容：保持 panel_ready + 旧阵容原样（不写入半成品），error_code 记录。"""
    await _mount(conn, ScriptedLLMProvider(PANEL_FAIL))
    await _seed(conn, "s1", status="panel_ready")
    await _old_panel(conn, "s1")
    async with await _client() as c:
        r = await c.post("/sessions/s1/panel/generate", json={"command_id": "cmd-1"})
    assert r.status_code == 202
    status, error_code = await _session_row(conn, "s1")
    assert status == "panel_ready", f"re-roll 失败必须保持 panel_ready（当前：{status}）"
    assert error_code, "失败必须记录 error_code"
    rows = await _participants(conn, "s1")
    assert len(rows) == 3, "旧阵容必须原样保留（1 host + 2 expert）"
    assert rows[0][1] == "旧主持人"
    assert [r[1] for r in rows[1:]] == ["旧专家甲", "旧专家乙"]


# ---------------------------------------------------------------- 场景 4：re-roll 成功（原子替换旧阵容）

@pytest.mark.asyncio
async def test_panel_reroll_success_replaces_old_panel_atomically(conn):
    """re-roll 成功：旧阵容被原子替换为新阵容（1 host + 4 expert），旧参与者无残留，无半成品/重复行。"""
    await _mount(conn, ScriptedLLMProvider(PANEL_OK))
    await _seed(conn, "s1", status="panel_ready")
    await _old_panel(conn, "s1")
    async with await _client() as c:
        r = await c.post("/sessions/s1/panel/generate", json={"command_id": "cmd-2"})
    assert r.status_code == 202
    status, error_code = await _session_row(conn, "s1")
    assert status == "panel_ready", f"re-roll 成功必须保持 panel_ready（当前：{status}）"
    assert error_code is None, "re-roll 成功必须清空 error_code"
    rows = await _participants(conn, "s1")
    assert len(rows) == 5, f"必须替换为 1 host + 4 expert（当前：{len(rows)} 行）"
    assert [r[0] for r in rows] == ["host"] + ["expert"] * 4
    assert [r[7] for r in rows] == [0, 1, 2, 3, 4], "sort_order 必须连续无重复（无半成品/重复行）"
    assert rows[0][1] == HOST["name"]
    assert [r[1] for r in rows[1:]] == [e["name"] for e in EXPERTS]
    names = {r[1] for r in rows}
    assert not ({"旧主持人", "旧专家甲", "旧专家乙"} & names), "旧阵容必须完全替换、无残留"
