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
    # A1: 让后端在批量结束时把失败镜次写入 last_run_errors.json，前端可一键重试
    project_id: str = ""


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


# ── C1: 工作流节点映射（image / video 都用这套）────────────────────────────────


def _resolve_workflow_path(workflow_name: str) -> "Path":
    """返回 workflow 的 .json 路径。优先 image_engine.workflow_dir，回退 video_engine.workflow_dir。"""
    from pathlib import Path as _P
    s = load_settings()
    candidates = [s.image_engine.workflow_dir, s.video_engine.workflow_dir]
    for d in candidates:
        if not d:
            continue
        p = _P(d) / f"{workflow_name}.json"
        if p.exists():
            return p
    # 找不到也返回一个可写的默认路径（meta 仍可保存在 image_engine.workflow_dir 下）
    base = s.image_engine.workflow_dir or s.video_engine.workflow_dir or str(_P.home() / "LumiCreate-Workflows")
    return _P(base) / f"{workflow_name}.json"


@router.get("/workflow-meta/{workflow_name}")
async def get_workflow_meta(workflow_name: str, type: str = "video"):
    from services.workflow_meta import load_meta
    wf_path = _resolve_workflow_path(workflow_name)
    return load_meta(wf_path, type_=type)


class WorkflowMetaPayload(BaseModel):
    node_map: dict
    notes:    str = ""
    type:     str = "video"
    version:  int = 1


@router.put("/workflow-meta/{workflow_name}")
async def put_workflow_meta(workflow_name: str, payload: WorkflowMetaPayload):
    from services.workflow_meta import save_meta
    wf_path = _resolve_workflow_path(workflow_name)
    save_meta(wf_path, payload.model_dump())
    return {"ok": True, "path": str(wf_path.with_name(wf_path.stem + ".meta.json"))}


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

    # A1: 收集失败镜次的最后错误，批量结束时持久化
    scene_errors: dict[str, str] = {}

    async def run_one(frame: dict, slot: int):
        nonlocal done_count
        meta = {"scene_id": frame["scene_id"], "frame_type": frame["frame_type"], "slot_index": slot}
        async for event in generate_image(cfg, workflow, frame.get("prompt", ""), req.negative_prompt, width=w, height=h):
            await queue.put({**event, **meta})
            if event.get("event") == "error":
                scene_errors[f"{frame['scene_id']}:{frame['frame_type']}"] = \
                    str(event.get("message", "unknown error"))[:500]
        done_count += 1
        if done_count >= total_tasks:
            finished.set()

    async def producer():
        tasks = [run_one(f, s) for f in req.frames for s in range(gen_count)]
        await asyncio.gather(*tasks, return_exceptions=True)
        finished.set()

    # E2: 任务历史
    from datetime import datetime as _dt, timezone as _tz
    started_at = _dt.now(_tz.utc).isoformat()
    started_ms = int(__import__("time").time() * 1000)

    async def stream():
        asyncio.create_task(producer())
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.1)
                yield _sse(item)
            except asyncio.TimeoutError:
                if finished.is_set() and queue.empty():
                    break
        # A1: 落盘失败镜次（仅当客户端给了 project_id）
        if req.project_id:
            try:
                from routers.projects import write_last_run_errors
                write_last_run_errors(req.project_id, "images", scene_errors)
            except Exception as e:
                print(f"[image-batch] write_last_run_errors failed: {e}", flush=True)
        # E2: 记录历史
        try:
            from services.task_history import append as _th_append
            ended_at = _dt.now(_tz.utc).isoformat()
            ended_ms = int(__import__("time").time() * 1000)
            _th_append(
                "images",
                req.project_id or "(no-project)",
                started_at=started_at, ended_at=ended_at,
                duration_ms=ended_ms - started_ms,
                items=total_tasks, errors=len(scene_errors),
                note=f"workflow={req.workflow_name}, frames={len(req.frames)}, gen_count={gen_count}",
            )
        except Exception as e:
            print(f"[image-batch] task_history append failed: {e}", flush=True)
        yield _sse({"event": "batch_done", "total": total_tasks,
                    "errors": scene_errors})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

