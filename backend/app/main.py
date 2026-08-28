from fastapi import FastAPI

app = FastAPI(title="AI Roundtable")


@app.get("/healthz")
async def healthz():
    return {"ok": True}
