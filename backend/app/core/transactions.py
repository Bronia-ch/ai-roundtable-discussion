import asyncio
import json
import uuid
from enum import Enum
from typing import Any

import aiosqlite

from app.core.errors import Degradation
from app.core.state_machine import SessionState, can_transition

# 允许作为 state_updates 键的列（白名单，防注入）
_ALLOWED_COLUMNS = {
    "status",
    "last_stable_state",
    "error_code",
    "retry_operation",
    "is_sample",
    "expert_count",
}

# 命令 → 目标状态（按 state_machine.TRANSITIONS 推导；can_transition 校验合法性）。
# 位于事务层：execute_command 在 BEGIN IMMEDIATE 之后于事务内解析（含 retry 重放）。
_COMMANDS: dict[str, SessionState] = {
    "panel/generate": SessionState.PANEL_GENERATING,  # draft/panel_ready → panel_generating（含 re-roll）
    "panel/confirm": SessionState.READY,  # panel_ready → ready
    "discussion/start": SessionState.LIVE,  # ready → live
    "discussion/pause": SessionState.PAUSED,  # live → paused
    "discussion/resume": SessionState.LIVE,  # paused → live
    "discussion/end": SessionState.FINALIZING,  # live/paused → finalizing
    "report": SessionState.FINALIZING,  # finalizing 重试生成报告（自迁移滞留，见 execute_command 特判）
}


class CommandOutcome(str, Enum):
    """execute_command 的结果（路由层映射为 HTTP）。"""

    NOT_FOUND = "not_found"
    UNKNOWN_COMMAND = "unknown_command"
    CONFLICT = "conflict"
    DUPLICATE = "duplicate"
    APPLIED = "applied"


_FALLBACK_LOCK: asyncio.Lock | None = None


def _write_lock(conn: aiosqlite.Connection) -> asyncio.Lock:
    """连接级最小写锁：BEGIN IMMEDIATE → COMMIT/ROLLBACK 完整区间串行化。

    惰性挂载到连接对象（首次调用创建；无 await，并发首调用不会双创建）。
    共享同一连接的协程若同时 BEGIN IMMEDIATE，SQL 会交错进入同一事务或抛
    "cannot start a transaction within a transaction"；锁保证单连接上完整写事务
    不可交错。测试连接（conftest fixture）首次调用自动获得同一把锁，
    不依赖 lifespan 装配。
    """
    lock = getattr(conn, "_ai_write_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        try:
            setattr(conn, "_ai_write_lock", lock)
        except AttributeError:
            global _FALLBACK_LOCK
            if _FALLBACK_LOCK is None:
                _FALLBACK_LOCK = asyncio.Lock()
            lock = _FALLBACK_LOCK
    return lock


async def commit_event(
    conn: aiosqlite.Connection,
    session_id: str,
    event_type: str,
    payload: dict[str, Any],
    state_updates: dict[str, Any] | None = None,
    event_store=None,
) -> int:
    """原子三写：应用业务状态 + 递增 last_event_sequence + 插入 events，返回新 sequence。

    任一写失败整体回滚。LLM/网络调用绝不可在本事务内发生。
    event_store 注入点（G3）：提交后以本地精确 seq 广播（回滚边界外，失败不回滚已提交事务）。
    """
    lock = _write_lock(conn)
    async with lock:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            if state_updates:
                for key in state_updates:
                    if key not in _ALLOWED_COLUMNS:
                        raise ValueError(f"不允许的 state_updates 列: {key}")
                cols = ", ".join(f"{k} = ?" for k in state_updates)
                await conn.execute(
                    f"UPDATE sessions SET {cols} WHERE id = ?",
                    (*state_updates.values(), session_id),
                )
            await conn.execute(
                "UPDATE sessions SET last_event_sequence = last_event_sequence + 1 WHERE id = ?",
                (session_id,),
            )
            row = await (
                await conn.execute(
                    "SELECT last_event_sequence FROM sessions WHERE id = ?", (session_id,)
                )
            ).fetchone()
            seq = row[0]
            await conn.execute(
                "INSERT INTO events (session_id, sequence, event_type, schema_version, payload) "
                "VALUES (?, ?, ?, 1, ?)",
                (session_id, seq, event_type, json.dumps(payload, ensure_ascii=False)),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        if event_store is not None:
            await event_store.publish(conn, session_id, seq)
        return seq


async def create_session(
    conn: aiosqlite.Connection,
    session_id: str,
    topic: str,
    expert_count: int,
    created_at: str,
    event_store=None,
) -> int:
    """原子创建 draft 会话 + 三写（状态/sequence/事件），返回新 sequence（=1）。

    与 commit_event 同一事务模式：INSERT sessions 与 events 任一失败整体回滚。
    创建事件为 session.state_changed，data.state = draft。
    event_store 注入点（G3）：提交后以本地精确 seq 广播 draft 创建事件。
    """
    lock = _write_lock(conn)
    async with lock:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await conn.execute(
                "INSERT INTO sessions (id, topic, expert_count, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'draft', ?, ?)",
                (session_id, topic, expert_count, created_at, created_at),
            )
            await conn.execute(
                "UPDATE sessions SET last_event_sequence = last_event_sequence + 1 WHERE id = ?",
                (session_id,),
            )
            row = await (
                await conn.execute(
                    "SELECT last_event_sequence FROM sessions WHERE id = ?", (session_id,)
                )
            ).fetchone()
            seq = row[0]
            await conn.execute(
                "INSERT INTO events (session_id, sequence, event_type, schema_version, payload) "
                "VALUES (?, ?, 'session.state_changed', 1, ?)",
                (session_id, seq, json.dumps({"state": "draft"}, ensure_ascii=False)),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        if event_store is not None:
            await event_store.publish(conn, session_id, seq)
        return seq


async def execute_command(
    conn: aiosqlite.Connection,
    session_id: str,
    command_type: str,
    command_id: str,
    event_store=None,
) -> CommandOutcome:
    """单一原子命令事务：receipt、状态迁移、事件写入同生共死。

    event_store 注入点（G3）：APPLIED 提交后以本地精确 seq 广播 state_changed——
    命令状态事件必须先于路由启动的引擎 utterance 广播（帧顺序由接线保证）。
    publish 在 commit 之后、异常回滚边界之外执行：广播失败时已提交状态保留、
    异常上抛（HTTP 500）——客户端幂等重试返回 DUPLICATE 202，SSE 端经 replay 自愈。

    事务内顺序（连接级写锁串行化 BEGIN→COMMIT 全区间）：
    NOT_FOUND → 幂等(DUPLICATE) → retry 解析 → 目标解析(UNKNOWN_COMMAND) → 门禁(CONFLICT)
    → INSERT receipt（不 commit）→ CAS 条件更新（rowcount≠1 → ROLLBACK CONFLICT）
    → 读新 seq → INSERT state_changed 事件 → COMMIT(APPLIED)。

    - 门禁与 CAS 均基于事务内读取的 current_status；CAS 以 current_status 为条件
      UPDATE（WHERE id AND status），阻止基于过期状态的第二次迁移。
    - retry 在事务内解析 sessions.retry_operation，无路由外读取窗口；
      幂等（DUPLICATE）先于 retry_operation 检查，重复 retry command_id 仍返回 202。
    - 任何 SQL/写入异常：整体 ROLLBACK 后继续传播（HTTP 层形成 500），
      不得把数据库失败伪装成 202。
    """
    lock = _write_lock(conn)
    async with lock:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            row = await (
                await conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
            ).fetchone()
            if row is None:
                await conn.rollback()
                return CommandOutcome.NOT_FOUND
            existing = await (
                await conn.execute(
                    "SELECT 1 FROM command_receipts WHERE session_id=? AND command_id=?",
                    (session_id, command_id),
                )
            ).fetchone()
            if existing is not None:
                await conn.rollback()
                return CommandOutcome.DUPLICATE
            row = await (
                await conn.execute(
                    "SELECT status, retry_operation FROM sessions WHERE id = ?", (session_id,)
                )
            ).fetchone()
            current_status, retry_operation = row
            actual_type = command_type
            if command_type == "retry":
                if not retry_operation:
                    await conn.rollback()
                    return CommandOutcome.CONFLICT
                actual_type = retry_operation
            target = _COMMANDS.get(actual_type)
            if target is None:
                await conn.rollback()
                return CommandOutcome.UNKNOWN_COMMAND
            if actual_type == "report":
                # 滞留命令（§10.4 阶梯 6）：finalizing 下重试生成报告——允许"自迁移"
                # （target == current）。仅此命令豁免 can_transition；resume 等自环
                # 仍必须 409（test_command_gate_violation_409），不得通用化。
                if SessionState(current_status) is not SessionState.FINALIZING:
                    await conn.rollback()
                    return CommandOutcome.CONFLICT
            elif not can_transition(SessionState(current_status), target):
                await conn.rollback()
                return CommandOutcome.CONFLICT
            # receipt 与业务效果同一事务：此处不 commit，任一步失败随事务回滚
            await conn.execute(
                "INSERT INTO command_receipts (session_id, command_id, command_type) "
                "VALUES (?, ?, ?)",
                (session_id, command_id, command_type),
            )
            # CAS：条件更新阻止基于过期状态的第二次迁移（rowcount 必须恰为 1）
            cur = await conn.execute(
                "UPDATE sessions SET status = ?, last_event_sequence = last_event_sequence + 1, "
                "updated_at = datetime('now') WHERE id = ? AND status = ?",
                (target.value, session_id, current_status),
            )
            if cur.rowcount != 1:
                await conn.rollback()
                return CommandOutcome.CONFLICT
            seq_row = await (
                await conn.execute(
                    "SELECT last_event_sequence FROM sessions WHERE id = ?", (session_id,)
                )
            ).fetchone()
            seq = seq_row[0]
            await conn.execute(
                "INSERT INTO events (session_id, sequence, event_type, schema_version, payload) "
                "VALUES (?, ?, 'session.state_changed', 1, ?)",
                (session_id, seq, json.dumps({"state": target.value}, ensure_ascii=False)),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        if event_store is not None:
            await event_store.publish(conn, session_id, seq)  # 提交后、回滚边界外
        return CommandOutcome.APPLIED


async def commit_panel(
    conn: aiosqlite.Connection,
    session_id: str,
    participants: list[tuple] | None,
    state: str,
    error_code: str | None,
    event_store=None,
) -> int:
    """panel/generate 执行体回写：可选替换 participants + 状态/error_code + sequence + 事件，单事务原子。

    - participants 非 None：DELETE 旧阵容 + INSERT 新阵容（同事务；首次生成 DELETE 影响 0 行，
      re-roll 成功时替换旧阵容）；None：不触碰 participants（失败回退路径，旧阵容原样保留）。
    - error_code None 写 SQL NULL（清空失败标记）；非 None 记录失败原因。
    - 状态为无条件 UPDATE：panel_generating 下无合法并发命令（TRANSITIONS 无出边且
      panel/generate 在 panel_generating 下 CONFLICT），命令门禁已封死并发面。
    LLM/网络调用绝不可在本事务内发生（调用方在事务外完成生成与校验）。
    event_store 注入点（G3）：提交后以本地精确 seq 广播（回滚边界外，失败不回滚已提交事务）。
    """
    lock = _write_lock(conn)
    async with lock:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            if participants is not None:
                await conn.execute(
                    "DELETE FROM participants WHERE session_id = ?", (session_id,)
                )
                for p in participants:
                    role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order = p
                    await conn.execute(
                        "INSERT INTO participants (id, session_id, role, name, profession, title, "
                        "stance, avatar_color, avatar_emoji, sort_order) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            uuid.uuid4().hex,
                            session_id,
                            role,
                            name,
                            profession,
                            title,
                            stance,
                            avatar_color,
                            avatar_emoji,
                            sort_order,
                        ),
                    )
            await conn.execute(
                "UPDATE sessions SET status = ?, error_code = ?, "
                "last_event_sequence = last_event_sequence + 1, updated_at = datetime('now') "
                "WHERE id = ?",
                (state, error_code, session_id),
            )
            row = await (
                await conn.execute(
                    "SELECT last_event_sequence FROM sessions WHERE id = ?", (session_id,)
                )
            ).fetchone()
            seq = row[0]
            await conn.execute(
                "INSERT INTO events (session_id, sequence, event_type, schema_version, payload) "
                "VALUES (?, ?, 'session.state_changed', 1, ?)",
                (session_id, seq, json.dumps({"state": state}, ensure_ascii=False)),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        if event_store is not None:
            await event_store.publish(conn, session_id, seq)
        return seq


async def commit_report(
    conn: aiosqlite.Connection,
    session_id: str,
    report: dict[str, Any],
    raw_json: str,
    degraded: Degradation | None = None,
    event_store=None,
) -> int | None:
    """finalizing 收尾成功回写：INSERT 报告行 + 迁移 completed + 清空错误三元组 + 事件，单事务原子。

    - INSERT OR IGNORE（session_id UNIQUE）是并发裁决点：rowcount=0（报告已存在，
      另一 finalize 任务已成功）→ 提交并返回 0——不重复迁移、不重复广播（幂等重放）。
    - CAS `WHERE status='finalizing'`：状态已离开 finalizing → rowcount=0 → 整体回滚，
      不得留下新 report 行，返回 None（绝不把非 finalizing 会话标成 completed）。
    - 成功路径清空 error_code/retry_operation：重试成功的报告不带残留失败标记。
    - 报告行与 completed 迁移同生共死：绝不出现"报告已持久化但状态未完成"。
    - LLM/网络调用绝不可在本事务内发生。
    """
    lock = _write_lock(conn)
    async with lock:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            d = degraded or Degradation()
            consensus = report.get("key_consensus")
            divergence = report.get("main_divergence")
            unresolved = report.get("unresolved_questions")
            actions = report.get("suggested_actions")
            cur = await conn.execute(
                "INSERT OR IGNORE INTO discussion_reports "
                "(id, session_id, summary, key_consensus, main_divergence, unresolved_questions, "
                " suggested_actions, raw_json, degraded_components, "
                " permanently_failed_insight_count, used_rule_scheduler_count, failed_turn_count, "
                " report_generated_with_degraded_context) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex, session_id,
                    report["summary"],
                    json.dumps(consensus, ensure_ascii=False) if consensus is not None else None,
                    json.dumps(divergence, ensure_ascii=False) if divergence is not None else None,
                    json.dumps(unresolved, ensure_ascii=False) if unresolved is not None else None,
                    json.dumps(actions, ensure_ascii=False) if actions is not None else None,
                    raw_json,
                    json.dumps(d.degraded_components, ensure_ascii=False),
                    d.permanently_failed_insight_count,
                    d.used_rule_scheduler_count,
                    d.failed_turn_count,
                    1 if d.report_generated_with_degraded_context else 0,
                ),
            )
            if cur.rowcount == 0:
                await conn.commit()
                return 0  # 幂等重放：报告已存在——不迁移、不广播
            cur = await conn.execute(
                "UPDATE sessions SET status = 'completed', error_code = NULL, "
                "retry_operation = NULL, last_event_sequence = last_event_sequence + 1, "
                "updated_at = datetime('now') WHERE id = ? AND status = 'finalizing'",
                (session_id,),
            )
            if cur.rowcount != 1:
                await conn.rollback()  # CAS 失败：状态已离开 finalizing → 不留 report 行
                return None
            row = await (
                await conn.execute(
                    "SELECT last_event_sequence FROM sessions WHERE id = ?", (session_id,)
                )
            ).fetchone()
            seq = row[0]
            await conn.execute(
                "INSERT INTO events (session_id, sequence, event_type, schema_version, payload) "
                "VALUES (?, ?, 'session.state_changed', 1, ?)",
                (session_id, seq, json.dumps({"state": "completed"}, ensure_ascii=False)),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        if event_store is not None:
            await event_store.publish(conn, session_id, seq)
        return seq


async def mark_report_failed(
    conn: aiosqlite.Connection,
    session_id: str,
    error_code: str,
    event_store=None,
) -> int | None:
    """finalizing 收尾失败回写：滞留 finalizing + 可恢复错误三元组（error_code/retry_operation）
    + error.recoverable 事件，单事务原子；提交后精确 seq 广播（G3 注入点）。

    - CAS `WHERE status='finalizing'`：并发已 completed → rowcount=0 → 回滚，不污染已完成会话。
    - 状态原地不动（滞留语义）；重试由 retry 命令 + retry_operation='report' 驱动。
    - LLM/网络调用绝不可在本事务内发生。
    """
    lock = _write_lock(conn)
    async with lock:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            cur = await conn.execute(
                "UPDATE sessions SET error_code = ?, retry_operation = 'report', "
                "last_event_sequence = last_event_sequence + 1, updated_at = datetime('now') "
                "WHERE id = ? AND status = 'finalizing'",
                (error_code, session_id),
            )
            if cur.rowcount == 0:
                await conn.rollback()
                return None  # 已离开 finalizing：不写滞留
            row = await (
                await conn.execute(
                    "SELECT last_event_sequence FROM sessions WHERE id = ?", (session_id,)
                )
            ).fetchone()
            seq = row[0]
            await conn.execute(
                "INSERT INTO events (session_id, sequence, event_type, schema_version, payload) "
                "VALUES (?, ?, 'error.recoverable', 1, ?)",
                (
                    session_id, seq,
                    json.dumps(
                        {"error_code": error_code, "retry_operation": "report", "scope": "report"},
                        ensure_ascii=False,
                    ),
                ),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        if event_store is not None:
            await event_store.publish(conn, session_id, seq)
        return seq
