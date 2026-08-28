from fastapi import APIRouter, HTTPException

router = APIRouter()


def _not_implemented() -> None:
    raise HTTPException(status_code=501, detail="not implemented")


@router.post("/sessions/{id}/panel/generate")
async def panel_generate(id: str):
    _not_implemented()


@router.post("/sessions/{id}/panel/confirm")
async def panel_confirm(id: str):
    _not_implemented()


@router.post("/sessions/{id}/discussion/start")
async def discussion_start(id: str):
    _not_implemented()


@router.post("/sessions/{id}/discussion/pause")
async def discussion_pause(id: str):
    _not_implemented()


@router.post("/sessions/{id}/discussion/resume")
async def discussion_resume(id: str):
    _not_implemented()


@router.post("/sessions/{id}/discussion/end")
async def discussion_end(id: str):
    _not_implemented()


@router.post("/sessions/{id}/retry")
async def retry(id: str):
    _not_implemented()


@router.get("/sessions/{id}/events")
async def events(id: str):
    _not_implemented()
