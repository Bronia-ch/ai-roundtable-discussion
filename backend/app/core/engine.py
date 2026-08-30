import asyncio
import logging
import itertools
import json
from typing import Any

import aiosqlite

from . import insights, transactions, transcript, turns
from .errors import AuthError, Degradation, RateLimitError, SchemaError, UpstreamError, classify_error
from app.llm.reliability import call_with_retry
from .scheduler import RuleScheduler, pick_speaker


REPORT_SYSTEM = (
    "你是圆桌讨论的会议记录。严格输出 JSON："
    '{"summary": <string>, "key_consensus": [<string>], '
    '"main_divergence": [<string>], "unresolved_questions": [<string>], '
    '"suggested_actions": [<string>]}。summary 为必填的中文讨论总结。'
)
REPORT_GENERATION_FAILED = "report_generation_failed"

_REPORT_LIST_FIELDS = ("key_consensus", "main_divergence", "unresolved_questions", "suggested_actions")


# CG-D 降级记账：组件 → sessions 计数列（_degrade 经 commit_event 原子更新）
_DEGRADE_COLUMNS = {
    "rule_scheduler": "used_rule_scheduler_count",
    "utterance": "failed_turn_count",
    "insight": "permanently_failed_insight_count",
}


async def _read_degradation(
    conn: aiosqlite.Connection,
    session_id: str,
) -> Degradation | None:
    """从 sessions 降级记账列构造 Degradation；全零（无组件、无计数）→ None（无降级上下文）。"""
    row = await (
        await conn.execute(
            "SELECT degraded_components, used_rule_scheduler_count, "
            "permanently_failed_insight_count, failed_turn_count "
            "FROM sessions WHERE id = ?",
            (session_id,),
        )
    ).fetchone()
    if row is None:
        return None
    comps_raw, used, pf, ft = row
    comps = json.loads(comps_raw) if comps_raw else []
    if not comps and used == 0 and pf == 0 and ft == 0:
        return None
    return Degradation(
        degraded_components=comps,
        permanently_failed_insight_count=pf,
        used_rule_scheduler_count=used,
        failed_turn_count=ft,
        report_generated_with_degraded_context=True,
    )


def _validate_report(resp: Any) -> dict[str, Any]:
    """LLM 输出不可信：summary 必填（非空字符串）；结构化字段仅接受 str/list，其余忽略。
    校验失败抛 SchemaError（classify_error → SCHEMA → call_with_retry 立即抛出，不重试）。"""
    if not isinstance(resp, dict):
        raise SchemaError("报告响应不是对象")
    summary = resp.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise SchemaError("报告缺少 summary")
    cleaned: dict[str, Any] = {"summary": summary}
    for field in _REPORT_LIST_FIELDS:
        value = resp.get(field)
        if isinstance(value, (str, list)):
            cleaned[field] = value
    return cleaned


async def finalize_report(
    conn: aiosqlite.Connection,
    llm: Any,
    session_id: str,
    event_store=None,
) -> None:
    """finalizing 收尾执行体：LLM 生成报告 → 原子落库 + 迁移 completed
    （transactions.commit_report）；失败滞留 finalizing + 可恢复三元组
    （transactions.mark_report_failed），retry 命令驱动重试。
    LLM/网络调用绝不在 DB 事务内；CancelledError 穿透 except Exception——任务取消零写入。"""
    row = await (
        await conn.execute("SELECT topic FROM sessions WHERE id=?", (session_id,))
    ).fetchone()
    if row is None:
        return  # 会话不存在：静默返回（路由层已保证存在；防御会话被并发清理）
    topic = row[0]
    try:
        resp = await call_with_retry(
            lambda: llm.generate("report", REPORT_SYSTEM, f"讨论主题：{topic}"),
            classify=classify_error,
            max_retries=3,
        )
        validated = _validate_report(resp)
    except Exception:
        await transactions.mark_report_failed(
            conn, session_id, REPORT_GENERATION_FAILED, event_store=event_store,
        )
        return
    # 成功：报告行 + completed 迁移 + 清空错误三元组（单事务原子，见 transactions.commit_report）
    await transactions.commit_report(
        conn, session_id, validated,
        json.dumps(validated, ensure_ascii=False),
        degraded=await _read_degradation(conn, session_id),  # CG-D：会话降级记账 → 报告上下文
        event_store=event_store,
    )


logger = logging.getLogger(__name__)


class DiscussionEngine:
    """后端自动编排的讨论引擎：start/pause/resume/end + 六类 LLM 调用。"""

    def __init__(
        self,
        session_id: str,
        llm: Any,
        conn: aiosqlite.Connection,
        max_turns: int = 5,
        retries: int = 3,  # CG-D：LLM 调用重试次数（RECOVERABLE 指数退避；AUTH/SCHEMA/FATAL 不重试）
        event_store=None,
    ):
        self.session_id = session_id
        self.llm = llm
        self.conn = conn
        self.max_turns = max_turns
        self.retries = retries
        self.event_store = event_store
        self._pause = asyncio.Event()
        self._pause.set()
        self._stop = asyncio.Event()
        self._scheduler = RuleScheduler()
        self._seed = 42  # 确定性调度种子（测试不锁具体序列，仅锁轮换与合法性）
        self._experts: dict[str, str] = {}  # participant_id → stance（start 时按 sort_order 读）
        self._history: dict[str, Any] = {"last": None, "gaps": {}, "recent_stances": []}

    async def _host_id(self) -> str:
        row = await (
            await self.conn.execute(
                "SELECT id FROM participants WHERE session_id=? AND role='host'",
                (self.session_id,),
            )
        ).fetchone()
        return row[0]

    async def _emit(
        self,
        role: str,
        speaker_id: str,
        text: str,
        ordinal: int,
        turn_id: str | None = None,
    ) -> str:
        """写库落 utterance：turn 已由调用方创建（专家路径：失败矩阵需对已建 turn 标 failed）
        则复用传入 turn_id，缺省（host 开场）才创建——同一 ordinal 绝不二次建 turn
        （turns UNIQUE(session_id, sequence)）。返回 utterance uid（CG-D insight 降级记账）。"""
        if turn_id is None:
            turn_id = await turns.create_turn(
                self.conn, self.session_id, ordinal, speaker_id if role == "expert" else None
            )
        return await transcript.append_utterance(
            self.conn, self.session_id, turn_id, speaker_id, role, text, ordinal,
            event_store=self.event_store,
        )
        # speech_count 累计（仅 expert）在 append_utterance 的 BEGIN IMMEDIATE 事务内——
        # 与 utterance/事件/seq 原子提交（见 transcript.append_utterance）

    async def _utterance_count(self) -> int:
        row = await (
            await self.conn.execute(
                "SELECT COUNT(*) FROM utterances WHERE session_id=?", (self.session_id,)
            )
        ).fetchone()
        return row[0]

    async def _cap(self) -> int:
        row = await (
            await self.conn.execute(
                "SELECT utterance_cap FROM sessions WHERE id=?", (self.session_id,)
            )
        ).fetchone()
        return row[0]

    async def _fail_to_paused(self, code: str) -> None:
        """失败/上限暂停迁移：paused + 可恢复错误三元组（last_stable_state='live'），
        状态事件精确 seq 广播（commit_event 三写）。"""
        await transactions.commit_event(
            self.conn, self.session_id, "session.state_changed",
            {"state": "paused"},
            state_updates={"status": "paused", "error_code": code, "last_stable_state": "live"},
            event_store=self.event_store,
        )

    async def _degrade(self, component: str) -> None:
        """降级记账：对应计数 +1、degraded_components 追加（去重），session.degraded
        事件精确 seq 广播——计数/组件/事件/seq 同事务原子。"""
        column = _DEGRADE_COLUMNS[component]
        row = await (
            await self.conn.execute(
                f"SELECT {column}, degraded_components FROM sessions WHERE id = ?",
                (self.session_id,),
            )
        ).fetchone()
        count, comps_raw = row
        comps = json.loads(comps_raw) if comps_raw else []
        if component not in comps:
            comps.append(component)
        await transactions.commit_event(
            self.conn, self.session_id, "session.degraded",
            {"component": component, "count": count + 1},
            state_updates={
                column: count + 1,
                "degraded_components": json.dumps(comps, ensure_ascii=False),
            },
            event_store=self.event_store,
        )

    async def start(self) -> None:
        """CG-D 契约（§10.1 失败矩阵 / §10.3 发言上限 / §10.4 降级阶梯）：
        引擎零状态写入（live 由 start 命令事务写入，start() 不再写任何状态）；
        启动即停防线（count>=cap → 零新增发言立即 paused）；恢复模式（count>0）不开场、
        ordinal 从 count+1 继续（不撞 UNIQUE(session_id, ordinal)）；确定性调度决定发言者
        （LLM intent 仅提供候选意愿，绝不取 items[0]）；每轮 intent→utterance→insight；
        每次 LLM 调用返回后、任何写库/广播前检查 _stop（end 收尾：LLM 在途取消 → _generate
        返回 None，调用方按 _stop 检查点退出，绝不消费 None）；每轮开始 _pause.wait() 检查点。
        失败矩阵（§10.1）：host/utterance 的 AUTH/SCHEMA/重试耗尽（含文本缺失/非字符串
        → SchemaError）→ _fail_to_paused（可恢复三元组 last_stable_state='live'）；FATAL →
        任务确定性停止、状态保持不动（CG-B 契约，test_engine_llm_failure_stops_task_keeps_live
        锁定）；intent 任何失败 → RuleScheduler 降级（_degrade）本轮照常继续；insight 失败/
        结构非法 → utterance 标 permanently_failed + insight 降级继续；host 开场与每轮落库
        后 count>=cap → 上限暂停（cap<100：utterance_cap_reached；cap>=100：absolute_cap_reached）。"""
        rows = await (
            await self.conn.execute(
                "SELECT id, stance FROM participants "
                "WHERE session_id=? AND role='expert' ORDER BY sort_order",
                (self.session_id,),
            )
        ).fetchall()
        self._experts = {r[0]: r[1] for r in rows}
        host_id = await self._host_id()
        count = await self._utterance_count()
        cap = await self._cap()
        if count >= cap:
            # 启动即停防线（§10.3/E3）：count>=cap → 零新增发言立即 paused（绝对上限防线）
            await self._fail_to_paused(
                "absolute_cap_reached" if cap >= 100 else "utterance_cap_reached"
            )
            return
        if count == 0:
            # 首轮：host 开场（恢复模式 count>0 跳过开场，ordinal 从 count+1 继续）。
            # 生成与文本提取同入失败矩阵：AUTH/SCHEMA/重试耗尽（含缺失/非字符串文本
            # → SchemaError）→ host_opening_failed 暂停；FATAL → 任务停止、状态保持不动。
            # None（end 收尾：LLM 在途取消）→ 按 _stop 检查点优雅退出。
            try:
                opening = await self._generate("host", "system", "开场白")
                if opening is None or self._stop.is_set():
                    return  # end 收尾优雅退出（None 仅当 _stop 已发时产生）
                opening_text = self._text_of(opening, "text")
            except (AuthError, SchemaError, TimeoutError, ConnectionError,
                    RateLimitError, UpstreamError):
                logger.exception("host opening generation failed for session %s", self.session_id)
                await self._fail_to_paused("host_opening_failed")
                return
            except Exception:
                logger.exception("discussion engine fatal error for session %s", self.session_id)
                return  # FATAL：任务停止、状态保持不动（CG-B 契约）
            await self._emit("host", host_id, opening_text, 1)  # turn_id 缺省 → _emit 内创建
            count += 1
            if count >= cap:
                # 开场落库即达上限（cap=1）：零专家发言，按软/绝对上限规则暂停
                await self._fail_to_paused(
                    "absolute_cap_reached" if cap >= 100 else "utterance_cap_reached"
                )
                return
        ordinal = count + 1
        turn_rounds = itertools.count() if self.max_turns is None else range(self.max_turns)
        for _ in turn_rounds:
            if self._stop.is_set():
                break
            try:
                await self._pause.wait()
            except asyncio.CancelledError:
                if self._stop.is_set():
                    return  # end 收尾：暂停检查点被取消（stop 已发）——正常结束
                raise  # 非 end 取消（_stop 未设置）：保留取消语义，不吞异常
            try:
                intent = await self._generate("intent", "system", "批量意图")
            except Exception:
                await self._degrade("rule_scheduler")  # RuleScheduler 降级，本轮照常继续
                intent = None
            if self._stop.is_set():
                break  # 消费 intent 前检查点（end 取消的 None 必伴随 _stop，先于此退出）
            expert_id = self._pick_expert(intent)
            row = await (
                await self.conn.execute(
                    "SELECT id FROM turns WHERE session_id=? AND sequence=? AND status='failed'",
                    (self.session_id, ordinal),
                )
            ).fetchone()
            if row is not None:
                turn_id = row[0]  # R1 恢复：失败轮占位 turn 复用，不撞 UNIQUE(session_id, sequence)
            else:
                turn_id = await turns.create_turn(self.conn, self.session_id, ordinal, expert_id)
            try:
                utterance = await self._generate("utterance", "system", "专家发言")
                if self._stop.is_set():
                    break  # 消费 utterance 前检查点（_text_of 绝不吃 None）
                utterance_text = self._text_of(utterance, "text")
            except (AuthError, SchemaError, TimeoutError, ConnectionError,
                    RateLimitError, UpstreamError):
                await turns.mark_turn_failed(self.conn, turn_id)
                await self._degrade("utterance")
                await self._fail_to_paused("utterance_generation_failed")
                return
            except Exception:
                return  # FATAL：任务停止、状态保持不动（CG-B 契约）
            uid = await self._emit("expert", expert_id, utterance_text, ordinal, turn_id=turn_id)
            count += 1
            ordinal += 1
            self._update_history(expert_id)
            if count >= cap:
                # 每轮落库后检查上限：cap<100 软上限码、cap>=100 绝对上限码
                await self._fail_to_paused(
                    "absolute_cap_reached" if cap >= 100 else "utterance_cap_reached"
                )
                return
            try:
                insight = await self._generate("insight", "system", "洞察归类")
                if self._stop.is_set():
                    break  # 消费 insight 前检查点（insight.get 绝不吃 None）
                create = insight.get("create")
                if not isinstance(create, dict):
                    raise SchemaError("insight 缺 create 结构")  # 结构非法 → 同一降级路径
                await insights.create_insight(
                    self.conn, self.session_id,
                    create.get("kind", "focus"), create.get("text", ""),
                )
            except Exception:
                await insights.mark_insight_state(self.conn, uid, "permanently_failed")
                await self._degrade("insight")  # insight 降级，讨论继续

    async def _generate(self, call_type: str, system: str, user: str) -> dict | None:
        """LLM 调用经 call_with_retry：仅 RECOVERABLE 指数退避重试（AUTH/SCHEMA/FATAL
        立即上抛；重试耗尽上抛原异常）——任何失败上抛，由调用方失败矩阵处理；
        响应非对象 → SchemaError（SCHEMA 类，不重试）。
        LLM await 在途被取消（end 收尾）：仅当 stop 信号已发时返回 None（调用方按 _stop
        检查点退出，绝不消费 None）；否则原样重抛——非 end 取消语义不在调用点被吞。
        CancelledError 不被 call_with_retry 捕获（except Exception 不捕获 BaseException）。"""
        try:
            resp = await call_with_retry(
                lambda: self.llm.generate(call_type, system, user),
                classify=classify_error,
                max_retries=self.retries,
            )
        except asyncio.CancelledError:
            if self._stop.is_set():
                return None  # end 收尾：stop 已发、LLM 调用在途被取消——优雅结束循环
            raise  # 非 end 取消（_stop 未设置）：保留取消语义，不吞异常
        if not isinstance(resp, dict):
            raise SchemaError(f"{call_type} 响应不是对象")
        return resp

    def _text_of(self, resp: dict, key: str) -> str:
        """不可信响应文本提取：缺键/非字符串 → SchemaError（SCHEMA → 调用方失败矩阵
        host/utterance → paused）。"""
        value = resp.get(key)
        if not isinstance(value, str):
            raise SchemaError(f"{key} 缺失或非字符串")
        return value

    def _pick_expert(self, intent: dict) -> str:
        """发言者由确定性调度决定：pick_speaker 综合意愿/相关性/公平/多样性选出。
        items 非列表/为空/遍历后无任何合法 participant_id（意愿表为空）→ 统一
        RuleScheduler 降级。候选集恒为合法专家。"""
        items = (intent or {}).get("items", [])  # intent 失败降级后为 None → 空意愿 → RuleScheduler 兜底
        candidates = list(self._experts)
        willingness: dict[str, float] = {}
        intents: dict[str, str] = {}
        if isinstance(items, list):
            for p in items:
                if not isinstance(p, dict):
                    continue
                pid = p.get("participant_id")
                if not isinstance(pid, str) or pid not in self._experts:
                    continue
                w = p.get("willingness", 0.0)
                t = p.get("intent_type", "answer")
                willingness[pid] = w if isinstance(w, (int, float)) else 0.0
                intents[pid] = t if isinstance(t, str) else "answer"
        if not willingness:
            return self._scheduler.pick(candidates, self._history, seed=self._seed)
        return pick_speaker(
            candidates, willingness, intents, self._experts, self._history, seed=self._seed
        )

    def _update_history(self, expert_id: str) -> None:
        """调度历史：last 防连续、gaps 公平（被选者清零其余 +1）、recent_stances 多样性（近 5 轮）。"""
        gaps = {c: self._history["gaps"].get(c, 0) + 1 for c in self._experts}
        gaps[expert_id] = 0
        self._history = {
            "last": expert_id,
            "gaps": gaps,
            "recent_stances": (self._history["recent_stances"] + [self._experts[expert_id]])[-5:],
        }

    async def stop(self) -> None:
        """确定性停止循环：设信号；循环在下一 LLM 调用返回后的检查点（写库/广播前）退出。"""
        self._stop.set()

    async def pause(self) -> None:
        self._pause.clear()

    async def resume(self) -> None:
        self._pause.set()

    async def end(self) -> None:
        """CG-C 收尾接线：先发停止信号（utterance 检查点退出循环），再生成讨论报告。
        状态 finalizing 已由 discussion/end 命令事务写入；本方法负责报告落库：
        成功 → completed（commit_report）；失败 → 滞留 finalizing + 可恢复三元组
        （mark_report_failed），retry 命令驱动重试。CancelledError 穿透 except Exception：
        任务取消（registry 停机）不写任何数据、不 bump seq。"""
        await self.stop()
        await finalize_report(self.conn, self.llm, self.session_id, event_store=self.event_store)
