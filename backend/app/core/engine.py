import asyncio
import itertools
import json
from typing import Any

import aiosqlite

from . import insights, transactions, transcript, turns
from .errors import ErrorClass, SchemaError, classify_error
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
        degraded=None,  # 降级上下文属 CG-D；CG-C 始终 None
        event_store=event_store,
    )


class DiscussionEngine:
    """后端自动编排的讨论引擎：start/pause/resume/end + 六类 LLM 调用。"""

    def __init__(
        self,
        session_id: str,
        llm: Any,
        conn: aiosqlite.Connection,
        max_turns: int = 5,
        event_store=None,
    ):
        self.session_id = session_id
        self.llm = llm
        self.conn = conn
        self.max_turns = max_turns
        self.event_store = event_store
        self._pause = asyncio.Event()
        self._pause.set()
        self._stop = asyncio.Event()
        self._scheduler = RuleScheduler()
        self._seed = 42  # 确定性调度种子（测试不锁具体序列，仅锁轮换与合法性）
        self._experts: dict[str, str] = {}  # participant_id → stance（start 时按 sort_order 读）
        self._history: dict[str, Any] = {"last": None, "gaps": {}, "recent_stances": []}
        self._failure = None  # 最近一次 LLM 失败类别（CG-D 消费）

    async def _host_id(self) -> str:
        row = await (
            await self.conn.execute(
                "SELECT id FROM participants WHERE session_id=? AND role='host'",
                (self.session_id,),
            )
        ).fetchone()
        return row[0]

    async def _emit(self, role: str, speaker_id: str, text: str, ordinal: int) -> None:
        turn_id = await turns.create_turn(self.conn, self.session_id, ordinal, speaker_id if role == "expert" else None)
        await transcript.append_utterance(
            self.conn, self.session_id, turn_id, speaker_id, role, text, ordinal,
            event_store=self.event_store,
        )
        # speech_count 累计（仅 expert）在 append_utterance 的 BEGIN IMMEDIATE 事务内——
        # 与 utterance/事件/seq 原子提交（见 transcript.append_utterance）

    async def start(self) -> None:
        """CG-B 契约：引擎零状态写入（live 由 start 命令事务写入，start() 不再写任何状态）；
        确定性调度决定发言者（LLM intent 仅提供候选意愿，绝不取 items[0]）；
        每轮 intent→utterance→insight；每次 LLM 调用返回后、任何写库/广播前检查 _stop；
        每轮开始 _pause.wait() 检查点；LLM 调用失败或响应结构非法（非 dict/缺字段/类型错）
        → 任务确定性停止、session 保持 live（不重试、不迁移状态——重试矩阵属 CG-D）。"""
        rows = await (
            await self.conn.execute(
                "SELECT id, stance FROM participants "
                "WHERE session_id=? AND role='expert' ORDER BY sort_order",
                (self.session_id,),
            )
        ).fetchall()
        self._experts = {r[0]: r[1] for r in rows}
        host_id = await self._host_id()
        opening = await self._generate("host", "system", "开场白")
        if opening is None or self._stop.is_set():
            return
        opening_text = self._text_of(opening, "text")
        if opening_text is None or self._stop.is_set():
            return
        await self._emit("host", host_id, opening_text, 1)
        ordinal = 2
        turns = itertools.count() if self.max_turns is None else range(self.max_turns)
        for _ in turns:
            if self._stop.is_set():
                break
            try:
                await self._pause.wait()
            except asyncio.CancelledError:
                if self._stop.is_set():
                    return  # end 收尾：暂停检查点被取消（stop 已发）——正常结束
                raise  # 非 end 取消（_stop 未设置）：保留取消语义，不吞异常
            intent = await self._generate("intent", "system", "批量意图")
            if intent is None or self._stop.is_set():
                break
            expert_id = self._pick_expert(intent)
            utterance = await self._generate("utterance", "system", "专家发言")
            if utterance is None or self._stop.is_set():
                break
            utterance_text = self._text_of(utterance, "text")
            if utterance_text is None or self._stop.is_set():
                break
            await self._emit("expert", expert_id, utterance_text, ordinal)
            insight = await self._generate("insight", "system", "洞察归类")
            if insight is None or self._stop.is_set():
                break
            create = insight.get("create")
            if isinstance(create, dict):
                await insights.create_insight(
                    self.conn, self.session_id,
                    create.get("kind", "focus"), create.get("text", ""),
                )
            self._update_history(expert_id)
            ordinal += 1

    async def _generate(self, call_type: str, system: str, user: str) -> dict | None:
        """LLM 调用失败（任何类别）或响应非对象 → 记录失败类别后返回 None，调用方停止循环。
        CG-B 临时契约：失败即停（不重试、不迁移状态）；重试矩阵属 CG-D。
        LLM await 在途被取消（end 收尾）：仅当 stop 信号已发时视为停止请求返回 None
        （调用方按 _stop 检查点正常结束循环）；否则原样重抛——写库途中的取消
        语义不在 LLM 调用点被吞。"""
        try:
            try:
                resp = await self.llm.generate(call_type, system, user)
            except asyncio.CancelledError:
                if self._stop.is_set():
                    return None  # end 收尾：stop 已发、LLM 调用在途被取消——优雅结束循环
                raise  # 非 end 取消（_stop 未设置）：保留取消语义，不吞异常
        except Exception as exc:
            self._failure = classify_error(exc)
            return None
        if not isinstance(resp, dict):
            self._failure = ErrorClass.SCHEMA  # 既有枚举（errors.py:8）；classify_error 对 SchemaError 同值
            return None
        return resp

    def _text_of(self, resp: dict, key: str) -> str | None:
        """不可信响应文本提取：缺键/非字符串 → 置 SCHEMA 失败信号返回 None（调用方停止循环）。"""
        value = resp.get(key)
        if not isinstance(value, str):
            self._failure = ErrorClass.SCHEMA
            return None
        return value

    def _pick_expert(self, intent: dict) -> str:
        """发言者由确定性调度决定：pick_speaker 综合意愿/相关性/公平/多样性选出。
        items 非列表/为空/遍历后无任何合法 participant_id（意愿表为空）→ 统一
        RuleScheduler 降级。候选集恒为合法专家。"""
        items = intent.get("items", [])
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
