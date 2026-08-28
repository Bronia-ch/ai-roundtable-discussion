import asyncio
import json
import uuid
from typing import Any

import aiosqlite

from . import insights, transcript, turns
from .transactions import commit_event


class DiscussionEngine:
    """后端自动编排的讨论引擎：start/pause/resume/end + 六类 LLM 调用。"""

    def __init__(
        self,
        session_id: str,
        llm: Any,
        conn: aiosqlite.Connection,
        max_turns: int = 5,
    ):
        self.session_id = session_id
        self.llm = llm
        self.conn = conn
        self.max_turns = max_turns
        self._pause = asyncio.Event()
        self._pause.set()
        self._stop = asyncio.Event()

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
        await transcript.append_utterance(self.conn, self.session_id, turn_id, speaker_id, role, text, ordinal)

    async def start(self) -> None:
        await commit_event(self.conn, self.session_id, "session.state_changed", {"state": "live"}, {"status": "live"})
        host_id = await self._host_id()
        opening = await self.llm.generate("host", "system", "开场白")
        await self._emit("host", host_id, opening["text"], 1)
        ordinal = 2
        for _ in range(self.max_turns):
            if self._stop.is_set():
                break
            await self._pause.wait()
            intent = await self.llm.generate("intent", "system", "批量意图")
            items = intent.get("items", [])
            if not items:
                break
            expert_id = items[0]["participant_id"]
            utterance = await self.llm.generate("utterance", "system", "专家发言")
            await self._emit("expert", expert_id, utterance["text"], ordinal)
            insight = await self.llm.generate("insight", "system", "洞察归类")
            if insight.get("create"):
                await insights.create_insight(
                    self.conn, self.session_id, insight["create"].get("kind", "focus"), insight["create"].get("text", "")
                )
            ordinal += 1

    async def pause(self) -> None:
        self._pause.clear()

    async def resume(self) -> None:
        self._pause.set()

    async def end(self) -> None:
        self._stop.set()
        report = await self.llm.generate("report", "system", "最终报告")
        await self.conn.execute(
            "INSERT INTO discussion_reports (id, session_id, summary, raw_json) VALUES (?, ?, ?, ?)",
            (
                uuid.uuid4().hex,
                self.session_id,
                report.get("summary", ""),
                json.dumps(report, ensure_ascii=False),
            ),
        )
        await self.conn.commit()
        await commit_event(self.conn, self.session_id, "session.state_changed", {"state": "completed"}, {"status": "completed"})
