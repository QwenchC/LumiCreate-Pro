"""
Video engine router (ComfyUI video).

Endpoints:
  GET  /test                  — connectivity check
  GET  /workflows             — list ComfyUI video workflows
  POST /generate-stream       — SSE: generate video for all scenes sequentially
  GET  /outputs/{project_id}  — list previously generated video files
"""

import asyncio
import json
from pathlib import Path

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


class SceneVideoRequest(BaseModel):
    scene_id: str
    scene_index: int
    start_image: str    # base64 or empty (user selects from ImagesTab)
    end_image: str      # base64 or empty
    duration: float = 4.0
    positive_prompt: str = ""
    negative_prompt: str = ""


class VideoGenerateRequest(BaseModel):
    workflow_name: str
    resolution: str = "1920x1080"
    fps: int = 30
    scenes: list[SceneVideoRequest]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ── Connectivity ───────────────────────────────────────────────────────────────

@router.get("/test", response_model=ConnectionTestResult)
async def test_connection():
    cfg = load_settings().video_engine
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{cfg.comfyui_url}/system_stats")
            r.raise_for_status()
        return ConnectionTestResult(success=True, message="ComfyUI (Video) 连接成功")
    except Exception as e:
        return ConnectionTestResult(success=False, message=str(e))


@router.get("/workflows", response_model=list[str])
async def get_workflows():
    cfg = load_settings().video_engine
    try:
        return await list_workflows(cfg)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Video generation SSE ───────────────────────────────────────────────────────

@router.post("/generate-stream")
async def generate_video_stream(req: VideoGenerateRequest):
    """
    Generate video clips for each scene sequentially using ComfyUI.

    SSE events:
      scene_start    — starting a new scene  {scene_id, scene_index, total}
      progress       — ComfyUI progress       {value, max, scene_id}
      scene_done     — scene clip ready       {scene_id, images}
      scene_error    — scene failed           {scene_id, message}
      batch_done     — all scenes finished    {total}
    """
    cfg = load_settings().video_engine
    workflow = await get_workflow_json(cfg, req.workflow_name)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"工作流 '{req.workflow_name}' 未找到")

    total = len(req.scenes)

    async def stream():
        for idx, scene in enumerate(req.scenes):
            yield _sse({
                "event": "scene_start",
                "scene_id": scene.scene_id,
                "scene_index": scene.scene_index,
                "current": idx + 1,
                "total": total,
            })
            try:
                async for event in generate_image(
                    cfg, workflow,
                    scene.positive_prompt,
                    scene.negative_prompt,
                ):
                    if event["event"] == "completed":
                        yield _sse({**event, "event": "scene_done", "scene_id": scene.scene_id, "scene_index": scene.scene_index})
                    elif event["event"] == "progress":
                        yield _sse({**event, "scene_id": scene.scene_id})
                    elif event["event"] == "error":
                        yield _sse({**event, "event": "scene_error", "scene_id": scene.scene_id})
            except Exception as e:
                yield _sse({"event": "scene_error", "scene_id": scene.scene_id, "message": str(e)})

        yield _sse({"event": "batch_done", "total": total})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

