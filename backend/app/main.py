import os
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI

from . import db
from .api import routes
from .config import Settings
from .core.event_store import EventStore

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
    try:
        yield
    finally:
        await conn.close()


app = FastAPI(title="AI Roundtable", lifespan=lifespan)
app.include_router(routes.router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
