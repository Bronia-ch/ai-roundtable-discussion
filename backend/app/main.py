import os
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI

from . import db
from .api import routes
from .config import Settings
from .core.engine_registry import EngineRegistry
from .core.event_store import EventStore
from .llm.openai_compat import OpenAICompatProvider

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    db_dir = os.path.dirname(settings.sqlite_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = await aiosqlite.connect(settings.sqlite_path)
    await db.init_db(conn)
    app.state.conn = conn
    app.state.event_store = EventStore(conn)  # 进程共享：SSE 订阅按 session_id 分桶
    app.state.llm = OpenAICompatProvider(settings)  # LLM 注入点：测试以替身覆盖（见 test_panel._mount）
    app.state.engine_registry = EngineRegistry()  # 引擎/task 登记：start 接线 + 停机确定性收尾
    try:
        yield
    finally:
        await app.state.engine_registry.shutdown()  # 先停后台引擎任务（cancel+await+清理）
        await conn.close()


app = FastAPI(title="AI Roundtable", lifespan=lifespan)
app.include_router(routes.router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
