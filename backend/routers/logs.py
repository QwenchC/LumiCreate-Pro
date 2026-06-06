"""Log streaming endpoints (E1)."""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from services.log_bus import get_recent, subscribe, unsubscribe

router = APIRouter()


@router.get("/recent")
async def recent(limit: int = 200, after_id: int = 0):
    return {"lines": get_recent(limit=limit, after_id=after_id)}


@router.get("/stream")
async def stream():
    """SSE: 实时推送新日志行。"""
    q = subscribe()
    # 先推一批最近日志，让前端立即有内容
    backlog = get_recent(limit=100)

    async def gen():
        try:
            for evt in backlog:
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # heartbeat 防止 proxy 关连接
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/clear", status_code=204)
async def clear():
    from services.log_bus import _BUFFER, _BUF_LOCK
    with _BUF_LOCK:
        _BUFFER.clear()
