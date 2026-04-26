"""
Audio engine router (GPT-SoVITS).

Endpoints:
  GET  /test                  — connectivity check
  GET  /voice-models          — list available speaker names
  POST /generate-stream       — SSE: single dialogue line
  POST /generate-batch-stream — SSE: all dialogue lines, each N times in parallel
"""

import asyncio
import json
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import load_settings
from services.gptsovits import synthesise, list_voice_models

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ConnectionTestResult(BaseModel):
    success: bool
    message: str


class SingleGenerateRequest(BaseModel):
    text: str
    lang: str = "zh"
    speaker: Optional[str] = None
    ref_audio_path: Optional[str] = None
    prompt_text: Optional[str] = None
    prompt_lang: str = "zh"
    speed: float = 1.0
    # Metadata echoed back in events
    scene_id: str = ""
    dialogue_id: str = ""
    slot_index: int = 0


class BatchDialogue(BaseModel):
    scene_id: str
    dialogue_id: str
    text: str
    lang: str = "zh"
    speaker: Optional[str] = None
    ref_audio_path: Optional[str] = None
    prompt_text: Optional[str] = None


class BatchGenerateRequest(BaseModel):
    gen_count: int = 3
    speed: float = 1.0
    dialogues: list[BatchDialogue]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ── Connectivity ───────────────────────────────────────────────────────────────

@router.get("/test", response_model=ConnectionTestResult)
async def test_connection():
    cfg = load_settings().audio_engine
    if cfg.engine_type == "manual":
        return ConnectionTestResult(success=True, message="手动导入模式，无需连接")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{cfg.api_url}/")
            r.raise_for_status()
        return ConnectionTestResult(success=True, message="GPT-SoVITS 连接成功")
    except Exception as e:
        return ConnectionTestResult(success=False, message=str(e))


@router.get("/voice-models", response_model=list[str])
async def get_voice_models():
    cfg = load_settings().audio_engine
    if cfg.engine_type == "manual":
        return []
    try:
        return await list_voice_models(cfg)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Single line SSE ────────────────────────────────────────────────────────────

@router.post("/generate-stream")
async def generate_single_stream(req: SingleGenerateRequest):
    cfg = load_settings().audio_engine
    meta = {"scene_id": req.scene_id, "dialogue_id": req.dialogue_id, "slot_index": req.slot_index}

    async def stream():
        async for event in synthesise(
            cfg, req.text, req.lang, req.speaker,
            req.ref_audio_path, req.prompt_text, req.prompt_lang,
            speed=req.speed
        ):
            yield _sse({**event, **meta})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Batch parallel SSE ────────────────────────────────────────────────────────

@router.post("/generate-batch-stream")
async def generate_batch_stream(req: BatchGenerateRequest):
    """
    Launch len(dialogues) * gen_count concurrent TTS tasks.
    Events: started | completed | error | batch_done
    Each carries scene_id, dialogue_id, slot_index.
    completed carries: data (base64 wav), mime.
    """
    cfg = load_settings().audio_engine
    gen_count   = max(1, min(req.gen_count, 10))
    total_tasks = len(req.dialogues) * gen_count

    queue: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()
    done_count = 0

    async def run_one(dlg: BatchDialogue, slot: int):
        nonlocal done_count
        meta = {"scene_id": dlg.scene_id, "dialogue_id": dlg.dialogue_id, "slot_index": slot}
        async for event in synthesise(
            cfg, dlg.text, dlg.lang, dlg.speaker,
            dlg.ref_audio_path, dlg.prompt_text, speed=req.speed
        ):
            await queue.put({**event, **meta})
        done_count += 1
        if done_count >= total_tasks:
            finished.set()

    async def producer():
        tasks = [run_one(d, s) for d in req.dialogues for s in range(gen_count)]
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
