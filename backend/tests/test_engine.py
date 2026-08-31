"""CG-B RED：讨论引擎后台任务契约（G3/G5/G6 + 确定性收尾）。

契约（规格 §5.1 迁移表 + §9.3 调用清单 #2-6 + §10.1 失败矩阵）：
- G5 零状态写入：live 由 discussion/start 命令事务写入（state_changed 恰 1 条）；
  引擎循环只写 utterance/insight，不写 sessions 状态、不产生重复 state_changed。
- G6 调度器决定发言者：pick_speaker 确定性选出（合法专家、轮换），LLM intent 仅提供
  候选意愿（items[0] 不得直接决定）。
- G3 精确 seq 广播：命令 state_changed 与引擎 utterance 均在各自事务提交后以本地精确
  seq 广播（事务层 event_store 注入点），绝不通过"读取最新事件"推断；无订阅者时事件
  仍落库供重放（envelope 与 replay 同构）。
- 失败矩阵（§10.1）：LLM FATAL → 引擎任务确定性停止，session 保持 live（CG-B 临时
  契约，CG-D 才引入状态迁移）；意图缺失 → RuleScheduler 降级。
- pause/resume/stop：确定性收尾（测试局部门控 provider 同步屏障，无 sleep/时序碰巧）。

当前实现：start() 自行写 live（违反 G5）、items[0] 定 speaker（违反 G6）、无广播
（违反 G3）、无 pause/resume/stop 方法 → 全部失败（有效 RED）。
"""

import asyncio
import inspect
import json

import pytest

from app.core import transactions
from app.core import transcript
from app.core.engine import DiscussionEngine
from app.core.event_store import EventStore
from app.core.transactions import CommandOutcome
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

# 意图缺失：items 为空 → 必须降级到 RuleScheduler（现行实现 items[0] → IndexError）
NO_INTENT_SCRIPT = {
    "host": {"text": "欢迎来到圆桌讨论"},
    "intent": {"items": []},
    "utterance": {"text": "我认为这个观点值得探讨"},
    "insight": {"create": {"kind": "focus", "text": "AI 红利分配"}},
    "report": {"summary": "讨论完成"},
}

# LLM 失败：缺 "host" 键 → KeyError → classify_error 判 FATAL（不再重试）
FAIL_SCRIPT = {}


class GateLLMProvider:
    """测试门控 provider：每次 generate 先 set entered 信号、再等待 gate（asyncio.Event）。

    entered：engine 已实际进入本次调用（尚未被放行）——测试 await wait_entered() 确认
    到达后才 set+clear 放行；信号一对一（wait_entered 后 clear），create_task 后也
    不会错过；calls 记录已进入的调用序号（call_type 序列），供断言诊断。
    gate：set()+clear() 精确放行当前等待者，清除只影响之后的 wait（不会误伤已醒者）。
    全流程无 sleep、无时序碰巧。
    """

    def __init__(self, inner: ScriptedLLMProvider, gate: asyncio.Event):
        self.inner = inner
        self.gate = gate
        self.entered = asyncio.Event()
        self.calls: list[str] = []

    async def generate(self, call_type: str, system: str, user: str):
        self.calls.append(call_type)
        self.entered.set()
        await self.gate.wait()
        return await self.inner.generate(call_type, system, user)

    async def wait_entered(self, timeout: float = 2.0) -> None:
        """等待 engine 进入下一次 generate 调用（进入即 set；本次尚未被放行）。"""
        await asyncio.wait_for(self.entered.wait(), timeout=timeout)
        self.entered.clear()


async def _count(conn) -> int:
    """s1 的 utterance 行数（async：供确定性 DB 计数断言）。"""
    row = await (
        await conn.execute("SELECT COUNT(*) FROM utterances WHERE session_id='s1'")
    ).fetchone()
    return row[0]


# ---------------------------------------------------------------- G5：命令写 live，引擎零状态写入

@pytest.mark.asyncio
async def test_engine_loop_after_command_writes_no_state(conn):
    """G5 契约：live 由命令事务写入（state_changed 恰 1 条）；引擎零状态写入；
    max_turns=2 精确产出：host 开场 1 条 + 专家 2 条 = 3 条 utterance；
    speech_count 仅专家累计（每轮 +1，host 不参与调度公平）。"""
    await _setup(conn)
    outcome = await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    assert outcome is CommandOutcome.APPLIED
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCRIPT), conn, max_turns=2)
    await engine.start()
    changed = (
        await (
            await conn.execute(
                "SELECT COUNT(*) FROM events WHERE session_id='s1' AND event_type='session.state_changed'"
            )
        ).fetchone()
    )[0]
    assert changed == 1, f"live 只由命令事务写入（state_changed 必须恰 1 条，当前：{changed}）"
    count = (await (await conn.execute("SELECT COUNT(*) FROM utterances WHERE session_id='s1'")).fetchone())[0]
    assert count == 3, f"max_turns=2 精确产出：1 host 开场 + 2 expert = 3 条 utterance（当前：{count}）"
    experts = (
        await (
            await conn.execute(
                "SELECT COUNT(*) FROM utterances WHERE session_id='s1' AND role='expert'"
            )
        ).fetchone()
    )[0]
    assert experts == 2, f"专家发言必须恰 2 条（max_turns=2）（当前：{experts}）"
    total_speech = (
        await (
            await conn.execute(
                "SELECT SUM(speech_count) FROM participants WHERE session_id='s1' AND role='expert'"
            )
        ).fetchone()
    )[0]
    assert total_speech == 2, f"speech_count 仅专家累计、每轮 +1（当前：{total_speech}）"
    host_speech = (
        await (await conn.execute("SELECT speech_count FROM participants WHERE id='h1'")).fetchone()
    )[0]
    assert host_speech == 0, f"契约：speech_count 仅用于调度公平，不累计 host（当前：{host_speech}）"


@pytest.mark.asyncio
async def test_engine_persists_and_emits_participant_runtime_states(conn):
    """主持人和专家在生成/发言阶段必须产生可重放的席位状态事件，
    引擎结束后回到各自的休息状态。"""
    await _setup(conn)
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCRIPT), conn, max_turns=1)
    await engine.start()

    rows = await (
        await conn.execute(
            "SELECT payload FROM events WHERE session_id='s1' "
            "AND event_type='participant.state_changed' ORDER BY sequence"
        )
    ).fetchall()
    changes = [json.loads(row[0]) for row in rows]
    assert {c["state"] for c in changes} >= {"preparing", "speaking", "idle", "waiting"}
    assert any(c == {"participant_id": "h1", "state": "speaking"} for c in changes)
    assert any(c["participant_id"] in {"e1", "e2"} and c["state"] == "speaking" for c in changes)

    final = dict(
        await (
            await conn.execute(
                "SELECT id, runtime_state FROM participants WHERE session_id='s1'"
            )
        ).fetchall()
    )
    assert final["h1"] == "idle"
    assert final["e1"] == "waiting"
    assert final["e2"] == "waiting"


# ---------------------------------------------------------------- G6：发言者由确定性调度决定

@pytest.mark.asyncio
async def test_engine_speaker_determined_by_scheduler_not_llm(conn):
    """发言者由确定性调度决定：合法专家、且不恒为 LLM 意图首项（items[0]）。
    稳定契约（不锁具体序列/seed/历史构造）：两轮发言必须轮换到不同专家——
    LLM intent 只声明 e1 意愿，若引擎以 items[0] 定 speaker 则恒 e1，轮换断言失败。"""
    await _setup(conn)
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCRIPT), conn, max_turns=2)
    await engine.start()
    rows = await (
        await conn.execute(
            "SELECT speaker_id FROM utterances WHERE session_id='s1' AND role='expert' ORDER BY ordinal"
        )
    ).fetchall()
    assert len(rows) == 2
    speakers = {r[0] for r in rows}
    assert speakers <= {"e1", "e2"}, f"发言者必须是合法专家（当前：{speakers}）"
    assert len(speakers) == 2, f"确定性调度必须轮换发言者（当前恒为：{speakers}）——LLM items[0] 不得决定 speaker"


# ---------------------------------------------------------------- 意图缺失降级

@pytest.mark.asyncio
async def test_engine_intent_degradation_to_scheduler(conn):
    """意图缺失（items 为空）→ RuleScheduler 降级：按确定性规则仍选出合法专家，
    讨论不中断（utterance 正常落库）。"""
    await _setup(conn)
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    engine = DiscussionEngine("s1", ScriptedLLMProvider(NO_INTENT_SCRIPT), conn, max_turns=2)
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    assert task.exception() is None, "意图缺失不得使任务异常结束（必须降级到调度器）"
    rows = await (
        await conn.execute(
            "SELECT speaker_id FROM utterances WHERE session_id='s1' AND role='expert' ORDER BY ordinal"
        )
    ).fetchall()
    assert len(rows) == 2
    assert all(r[0] in ("e1", "e2") for r in rows), f"降级发言者必须合法（当前：{[r[0] for r in rows]}）"


# ---------------------------------------------------------------- LLM 失败：任务停止、保持 live

@pytest.mark.asyncio
async def test_engine_llm_failure_stops_task_keeps_live(conn):
    """§10.1 失败矩阵（CG-B 临时契约）：LLM FATAL → 引擎任务确定性停止；
    session 保持 live（引擎不写状态；状态迁移属 CG-D 范围）。"""
    await _setup(conn)
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    engine = DiscussionEngine("s1", ScriptedLLMProvider(FAIL_SCRIPT), conn, max_turns=3)
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)   # 任务必须自行终止（FATAL 不重试、不挂起）
    assert task.exception() is None, "LLM FATAL 不得使任务异常结束（引擎捕获后停止循环）"
    status = (await (await conn.execute("SELECT status FROM sessions WHERE id='s1'")).fetchone())[0]
    assert status == "live", f"LLM 失败后 session 保持 live（当前：{status}）——CG-B 临时契约"
    changed = (
        await (
            await conn.execute(
                "SELECT COUNT(*) FROM events WHERE session_id='s1' AND event_type='session.state_changed'"
            )
        ).fetchone()
    )[0]
    assert changed == 1, "失败不得产生状态事件（引擎零状态写入）"


# ---------------------------------------------------------------- pause/resume/stop 确定性收尾

@pytest.mark.asyncio
async def test_engine_pause_resume_stop_deterministic(conn):
    """pause/resume/stop 由门控 provider 提供确定性同步屏障：每次放行前以 entered 信号
    确认 engine 已实际进入对应 gate.wait()——无 sleep、无时序碰巧。

    冻结契约：
    - pause：在 host 调用仍在途（wait_entered 确认、尚未放行）时设置，先于下一轮
      _pause.wait() 检查点——放行 host 后 engine 必须阻塞在 round1 检查点：不得进入
      round1 intent（wait_entered 有限超时证明）、utterance 计数保持 1；resume 后才
      进入 round1 intent，放行完成 round1 并收到专家帧。
    - stop：round3 intent 已在途（wait_entered 证明）时设置，立即阻止其写入。
      GREEN 契约：每次 LLM 调用返回后、任何写库/广播前检查 _stop——放行 in-flight
      intent 后 engine 在写 utterance 前退出：零写入、任务完成、计数冻结。
      max_turns=3 保证 round3 本应产生第 4 条写入，stop 不生效则计数断言失败。"""
    assert hasattr(DiscussionEngine, "pause"), "契约：DiscussionEngine.pause() 阻塞下一轮"
    assert hasattr(DiscussionEngine, "resume"), "契约：DiscussionEngine.resume() 解除暂停"
    assert hasattr(DiscussionEngine, "stop"), "契约：DiscussionEngine.stop() 确定性停止循环"
    await _setup(conn)
    await transactions.execute_command(conn, "s1", "discussion/start", "c1")
    gate = asyncio.Event()
    provider = GateLLMProvider(ScriptedLLMProvider(SCRIPT), gate)
    store = EventStore(conn)
    q = store.subscribe("s1")
    engine = DiscussionEngine("s1", provider, conn, max_turns=3, event_store=store)
    task = asyncio.create_task(engine.start())

    def release(n: int = 1) -> None:
        """放行 n 次 LLM 调用（set+clear：当前等待者通过、后续调用重新阻塞）。
        放行量多于消费量无害（无人等待的 set+clear 是 no-op）。"""
        for _ in range(n):
            gate.set()
            gate.clear()

    async def finish_round(first_call_in_flight: bool) -> None:
        """放行一整轮（共 3 次调用：intent/utterance/insight）。
        first_call_in_flight=True：本轮首个调用已在途（entered 已由调用点确认、卡在
        gate）——先放行当前调用，再等待/放行余下 2 次；否则等待/放行 3 次。
        每次放行前 wait_entered 确认 engine 已进入对应 gate（信号配对，无错过）；
        放行总数恒为 3，绝不等待或放行到下一轮。"""
        if first_call_in_flight:
            release()
        n = 2 if first_call_in_flight else 3
        for _ in range(n):
            await provider.wait_entered()
            release()

    async def next_utterance_frame() -> dict:
        """席位状态事件与发言共用 SSE 队列，跳过状态帧取下一条发言。"""
        while True:
            frame = await asyncio.wait_for(q.get(), timeout=2.0)
            if frame["event"] == "utterance.completed":
                return frame

    # —— pause：在 host 调用在途（wait_entered 确认、尚未放行）时设置——
    #    先于下一轮 _pause.wait() 检查点，pause 必然生效于 round1 开始之前
    await provider.wait_entered()        # host generate 已进入、卡在 gate
    await engine.pause()
    release()                            # 放行 host
    host_frame = await next_utterance_frame()
    assert host_frame["event"] == "utterance.completed"
    assert await _count(conn) == 1, "pause 后仅 host 落库"

    # —— pause 生效：engine 阻塞在 round1 检查点，不得进入 round1 intent ——
    with pytest.raises(asyncio.TimeoutError):
        await provider.wait_entered(timeout=0.5)   # 缺席断言：intent 调用永不发起
    assert await _count(conn) == 1, "pause 期间计数不得增长"

    # —— resume：解除检查点后 engine 进入 round1 intent ——
    await engine.resume()
    await provider.wait_entered()        # 确认 round1 intent 已进入（卡 gate）
    await finish_round(first_call_in_flight=True)      # 放行在途 intent + utterance + insight
    e1 = await next_utterance_frame()
    assert e1["event"] == "utterance.completed"
    n1 = await _count(conn)
    assert n1 == 2, f"resume 后计数必须增长（host + round1 expert，当前：{n1}）"

    # —— round2 正常推进 ——
    await provider.wait_entered()        # 确认 round2 intent 已进入
    await finish_round(first_call_in_flight=True)
    e2 = await next_utterance_frame()
    assert e2["event"] == "utterance.completed"
    n2 = await _count(conn)
    assert n2 == 3, f"round2 后计数必须继续增长（当前：{n2}）"

    # —— stop：round3 intent 已在途（wait_entered 证明）；放行后零写入 ——
    await provider.wait_entered()        # 确认 round3 intent 已进入（尚未写入任何内容）
    n_stopped = await _count(conn)
    assert n_stopped == 3, "stop 前恰 3 条 utterance（host + 2 expert）"
    await engine.stop()
    release(3)                           # 放行 in-flight intent；GREEN 契约：engine 在
                                         # 写 utterance 前检查 _stop 退出（多余放行
                                         # 无人消费，no-op）
    await asyncio.wait_for(task, timeout=2.0)
    assert task.done(), "stop 后任务必须确定性完成"
    assert await _count(conn) == n_stopped, "stop 后计数冻结：round3 不得写入"


# ---------------------------------------------------------------- G3：精确 seq 广播（事务层注入点）

@pytest.mark.asyncio
async def test_engine_broadcasts_exact_seq_after_commit(conn):
    """G3 契约：广播发生在各自事务提交后，以本地精确 seq（绝不读最新事件）：
    - 命令事务 state_changed（seq 1）必须先于引擎任何 utterance 广播；
    - 引擎 utterance 事件 seq 与 append_utterance 落库行精确一致（帧序连续 [1,2,3]）；
    - 无订阅者时事件仍落库（重放与广播同构——EventStore 行级构造）。
    事务层注入点由签名守卫锁定（execute_command/append_utterance 的 event_store kwarg）。"""
    assert "event_store" in inspect.signature(transactions.execute_command).parameters, (
        "契约：execute_command 须带 event_store 注入点（事务提交后精确 seq 广播）"
    )
    assert "event_store" in inspect.signature(transcript.append_utterance).parameters, (
        "契约：append_utterance 须带 event_store 注入点（返回精确 seq 供广播）"
    )
    await _setup(conn)
    store = EventStore(conn)
    q = store.subscribe("s1")
    await transactions.execute_command(conn, "s1", "discussion/start", "c1", event_store=store)
    engine = DiscussionEngine("s1", ScriptedLLMProvider(SCRIPT), conn, max_turns=1, event_store=store)
    task = asyncio.create_task(engine.start())
    await asyncio.wait_for(task, timeout=2.0)
    frames = []
    while not q.empty():
        frames.append(q.get_nowait())
    core_frames = [
        f for f in frames if f["event"] in {"session.state_changed", "utterance.completed"}
    ]
    assert [f["event"] for f in core_frames] == [
        "session.state_changed",
        "utterance.completed",
        "utterance.completed",
    ], "命令 state_changed 必须先于引擎 utterance 广播"
    assert [f["sequence"] for f in frames] == sorted({f["sequence"] for f in frames})
    persisted = await (
        await conn.execute(
            "SELECT sequence, event_type FROM events WHERE session_id='s1' ORDER BY sequence"
        )
    ).fetchall()
    assert [(f["sequence"], f["event"]) for f in frames] == [tuple(row) for row in persisted]
    assert core_frames[1]["data"]["role"] == "host"
    assert core_frames[2]["data"]["role"] == "expert"
