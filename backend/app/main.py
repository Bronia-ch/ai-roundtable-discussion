from fastapi import FastAPI

from .api import routes

app = FastAPI(title="AI Roundtable")
app.include_router(routes.router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
