"""panel/generate 执行体：LLM 生成阵容 → 原子落库 + 状态回写。

契约（规格 §9.3 调用清单 #1 + §5.1 迁移表）：
- 成功：1 host + N expert 原子落库，状态 panel_generating → panel_ready，error_code 清空。
- 首次失败（无旧阵容）：状态回 draft + error_code，零 participants。
- re-roll 失败（有旧阵容）：保留旧阵容原样，状态回 panel_ready + error_code。

LLM 输出不可信：经 _validate_panel 结构校验，非法按 SchemaError 走失败路径。
LLM/网络调用绝不发生在 DB 事务内；落库与状态回写由 transactions.commit_panel
单事务原子完成（re-roll 成功时替换旧阵容，失败时零触碰）。
"""

from typing import Any

from app.core import transactions
from app.core.errors import SchemaError, classify_error
from app.llm.reliability import call_with_retry

PANEL_SYSTEM = (
    "你是圆桌讨论的阵容导演。严格输出 JSON："
    '{"panel": {"host": <person>, "experts": [<person> × N]}}。'
    "person = {\"name\", \"profession\", \"title\", \"stance\", \"avatar_color\", \"avatar_emoji\"}，"
    "全部为字符串；stance 为中文立场；avatar_color 为 #RRGGBB。"
)
PERSON_FIELDS = ("name", "profession", "title", "stance", "avatar_color", "avatar_emoji")
PANEL_GENERATION_FAILED = "panel_generation_failed"


def _validate_person(p: Any) -> None:
    if not isinstance(p, dict):
        raise SchemaError("阵容成员不是对象")
    for f in PERSON_FIELDS:
        v = p.get(f)
        if not isinstance(v, str) or not v.strip():
            raise SchemaError(f"阵容成员缺少字段: {f}")


def _validate_panel(resp: Any, expert_count: int) -> tuple[dict, list[dict]]:
    """LLM 输出不可信：结构校验通过才返回 (host, experts)。

    契约（test_panel.py 注入形状）：call_type="panel" 的响应直接为
    {"host": {...}, "experts": [...]}（无外层包装）。
    """
    if not isinstance(resp, dict):
        raise SchemaError("阵容响应不是对象")
    host = resp.get("host")
    experts = resp.get("experts")
    _validate_person(host)
    if not isinstance(experts, list):
        raise SchemaError("experts 不是数组")
    if len(experts) != expert_count:
        raise SchemaError(f"experts 数量应为 {expert_count}，实际 {len(experts)}")
    for e in experts:
        _validate_person(e)
    return host, experts


def _as_rows(host: dict, experts: list[dict]) -> list[tuple]:
    """转换 (role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order) 行：
    host sort_order 0，专家 1..N。"""
    rows = [("host", *(host[f] for f in PERSON_FIELDS), 0)]
    rows += [
        ("expert", *(e[f] for f in PERSON_FIELDS), i)
        for i, e in enumerate(experts, start=1)
    ]
    return rows


async def _has_panel(conn, session_id: str) -> bool:
    row = await (
        await conn.execute(
            "SELECT 1 FROM participants WHERE session_id=? LIMIT 1", (session_id,)
        )
    ).fetchone()
    return row is not None


async def generate(conn, llm, session_id: str, event_store=None) -> None:
    """panel/generate 执行体：成功落库并回写 panel_ready；失败按有无旧阵容回退。
    event_store 注入点（G3）：commit_panel 回写事务提交后以精确 seq 广播 state_changed。"""
    row = await (
        await conn.execute(
            "SELECT topic, expert_count FROM sessions WHERE id=?", (session_id,)
        )
    ).fetchone()
    topic, expert_count = row
    try:
        resp = await call_with_retry(
            lambda: llm.generate(
                "panel",
                PANEL_SYSTEM,
                f"讨论主题：{topic}；专家人数：{expert_count}",
            ),
            classify=classify_error,
            max_retries=3,
        )
        host, experts = _validate_panel(resp, expert_count)
    except Exception:
        # 阵容失败（§10.4.4）：无旧阵容回 draft；有旧阵容保留旧阵容回 panel_ready
        error = PANEL_GENERATION_FAILED
        if await _has_panel(conn, session_id):
            await transactions.commit_panel(
                conn, session_id, None, "panel_ready", error,
                event_store=event_store,  # G3：re-roll 失败回退提交后广播
            )
        else:
            await transactions.commit_panel(
                conn, session_id, None, "draft", error,
                event_store=event_store,  # G3：首次失败回退提交后广播
            )
        return
    # 成功：替换式原子落库（首次无旧阵容时 DELETE 影响 0 行）+ 回写 panel_ready + 清空 error_code
    await transactions.commit_panel(
        conn, session_id, _as_rows(host, experts), "panel_ready", None,
        event_store=event_store,  # G3：成功回写提交后广播
    )
