"""
Image generation router.

Key endpoints:
  GET  /test                  — connectivity check
  GET  /workflows             — list available ComfyUI workflows
  GET  /workflow/{name}       — download one workflow JSON
  POST /generate-stream       — SSE: single image
  POST /generate-batch-stream — SSE: all scene frames, each N copies in parallel
"""

import asyncio
import json
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import load_settings
from services.comfyui import generate_image, list_workflows, get_workflow_json

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ConnectionTestResult(BaseModel):
    success: bool
    message: str


class SingleGenerateRequest(BaseModel):
    workflow_name: str
    positive_prompt: str
    negative_prompt: str = ""
    seed: Optional[int] = None
    width: int = 0
    height: int = 0
    scene_id: str = ""
    frame_type: str = ""
    slot_index: int = 0


class BatchGenerateRequest(BaseModel):
    workflow_name: str
    gen_count: int = 3
    negative_prompt: str = ""
    width: int = 0
    height: int = 0
    frames: list[dict]   # [{scene_id, frame_type, prompt}]


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _load_workflow(cfg, workflow_name: str) -> dict:
    wf = await get_workflow_json(cfg, workflow_name)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"工作流 '{workflow_name}' 未找到")
    return wf


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ── Connectivity ───────────────────────────────────────────────────────────────

@router.get("/test", response_model=ConnectionTestResult)
async def test_connection():
    cfg = load_settings().image_engine
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{cfg.comfyui_url}/system_stats")
            r.raise_for_status()
        return ConnectionTestResult(success=True, message="ComfyUI 连接成功")
    except Exception as e:
        return ConnectionTestResult(success=False, message=str(e))


@router.get("/workflows", response_model=list[str])
async def get_workflows():
    cfg = load_settings().image_engine
    try:
        return await list_workflows(cfg)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/workflow/{workflow_name}")
async def get_workflow(workflow_name: str):
    cfg = load_settings().image_engine
    wf = await get_workflow_json(cfg, workflow_name)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return wf


# ── Single image SSE ──────────────────────────────────────────────────────────

@router.post("/generate-stream")
async def generate_single_stream(req: SingleGenerateRequest):
    cfg = load_settings().image_engine
    workflow = await _load_workflow(cfg, req.workflow_name)
    meta = {"scene_id": req.scene_id, "frame_type": req.frame_type, "slot_index": req.slot_index}
    w = req.width  or cfg.image_width
    h = req.height or cfg.image_height

    async def stream():
        async for event in generate_image(cfg, workflow, req.positive_prompt, req.negative_prompt, req.seed, w, h):
            yield _sse({**event, **meta})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Batch parallel SSE ────────────────────────────────────────────────────────

@router.post("/generate-batch-stream")
async def generate_batch_stream(req: BatchGenerateRequest):
    """
    Launch len(frames) * gen_count concurrent generation tasks.
    Multiplex all events into one SSE stream.

    Event types: queued | progress | completed | error | batch_done
    Each carries: scene_id, frame_type, slot_index
    completed carries: images = [{filename, data(base64), type}]
    """
    cfg = load_settings().image_engine
    workflow = await _load_workflow(cfg, req.workflow_name)
    gen_count = max(1, min(req.gen_count, 10))
    total_tasks = len(req.frames) * gen_count
    w = req.width  or cfg.image_width
    h = req.height or cfg.image_height

    queue: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()
    done_count = 0

    async def run_one(frame: dict, slot: int):
        nonlocal done_count
        meta = {"scene_id": frame["scene_id"], "frame_type": frame["frame_type"], "slot_index": slot}
        async for event in generate_image(cfg, workflow, frame.get("prompt", ""), req.negative_prompt, width=w, height=h):
            await queue.put({**event, **meta})
        done_count += 1
        if done_count >= total_tasks:
            finished.set()

    async def producer():
        tasks = [run_one(f, s) for f in req.frames for s in range(gen_count)]
        await asyncio.gather(*tasks, return_exceptions=True)
        finished.set()

    async def stream():
        asyncio.create_task(producer())
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.1)
                yield _sse(item)
            except asyncio.TimeoutError:
                if finished.is_set() and queue.empty():
                    break
        yield _sse({"event": "batch_done", "total": total_tasks})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

