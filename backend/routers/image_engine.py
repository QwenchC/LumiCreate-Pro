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


class RefImageSpec(BaseModel):
    """参考图来源标识。后端按 kind 解析为绝对路径。

    支持三种来源：
      - kind="portrait":  project_id + char_name + filename → 项目角色立绘
      - kind="element":   scope ("global" 或 "project:{pid}") + element_id → 元素库
      - kind="path":      path（仅供测试 / 内部使用，绝对路径直传）
    """
    kind: str
    project_id: Optional[str] = None
    char_name: Optional[str] = None
    filename: Optional[str] = None
    scope: Optional[str] = None
    element_id: Optional[int] = None
    path: Optional[str] = None


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
    refs: list[RefImageSpec] = []   # 轮 5: i2i 参考图（可为空 = t2i）


# D2: 工作流前置检查
@router.get("/precheck")
async def precheck_workflow(workflow_name: str):
    """生成前校验工作流：ComfyUI 是否在线 + 节点 class_type 是否齐 + 资源引用统计。"""
    from services.comfyui_precheck import precheck_image_workflow
    cfg = load_settings().image_engine
    result = await precheck_image_workflow(cfg.comfyui_url, workflow_name)
    return {"ok": result.ok, "issues": result.issues, "info": result.info}


# 轮 1: 工作流分类 + 参考图节点位置 —— 前端用来决定 ImagesTab 是否切图生图布局
@router.get("/workflow-info")
async def workflow_info(workflow_name: str):
    """返回工作流的分类（t2i / i2i_single / i2i_double / video）+ 参考图节点信息。
    前端可据此决定：
    - 图片生成页是否显示"参考图选择器"
    - 显示几个参考图槽位
    """
    from services.comfyui import get_workflow_json
    from services.workflow_meta import classify_workflow, load_meta, get_ref_image_nodes
    from pathlib import Path
    cfg = load_settings().image_engine
    workflow = await get_workflow_json(cfg, workflow_name)
    if workflow is None:
        return {"kind": "unknown", "ref_count": 0, "ref_nodes": [], "found": False}

    wf_dir = Path(cfg.workflow_dir or "")
    wf_path = wf_dir / f"{workflow_name}.json" if wf_dir.exists() else None

    kind = classify_workflow(workflow_name, workflow=workflow, workflow_path=str(wf_path) if wf_path else None)
    meta = load_meta(str(wf_path), type_="image") if wf_path else {}
    ref_nodes = get_ref_image_nodes(meta, workflow=workflow)
    ref_count = {"t2i": 0, "i2i_single": 1, "i2i_double": 2}.get(kind, 0)
    # 工作流实际 LoadImage 节点数可能多于声明（如 single 工作流里有 2 个 LoadImage 一个不用）
    # 优先用 kind 推断的 ref_count，但提供 actual 给前端做诊断
    return {
        "kind": kind,
        "ref_count": ref_count,
        "ref_nodes": ref_nodes[:max(ref_count, 1)] if ref_count else [],
        "actual_loadimage_count": sum(1 for n in (workflow.get("nodes") or [])
                                       if n.get("type") == "LoadImage"),
        "found": True,
    }


class BatchGenerateRequest(BaseModel):
    workflow_name: str
    gen_count: int = 3
    negative_prompt: str = ""
    width: int = 0
    height: int = 0
    # 轮 5: 每个 frame 可附带 refs: [{kind, ...}]，没有则等同 t2i
    frames: list[dict]   # [{scene_id, frame_type, prompt, refs?: [RefImageSpec]}]
    # A1: 让后端在批量结束时把失败镜次写入 last_run_errors.json，前端可一键重试
    project_id: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _load_workflow(cfg, workflow_name: str) -> dict:
    wf = await get_workflow_json(cfg, workflow_name)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"工作流 '{workflow_name}' 未找到")
    return wf


def _resolve_ref_paths(refs: list) -> list[str]:
    """把 RefImageSpec / dict 列表解析为本地绝对路径列表。
    用于 i2i 工作流向 ComfyUI 注入参考图。
    """
    from pathlib import Path as _P
    s = load_settings()
    out: list[str] = []
    for r in refs or []:
        # 兼容 Pydantic 模型和 dict
        r = r.model_dump() if hasattr(r, "model_dump") else dict(r or {})
        kind = (r.get("kind") or "").strip()
        if kind == "portrait":
            pid = r.get("project_id") or ""
            cn = r.get("char_name") or ""
            fn = r.get("filename") or ""
            if not (pid and cn and fn):
                raise HTTPException(400, detail=f"portrait ref 缺字段: {r}")
            from routers.projects import _safe_character_dirname
            safe_cn = _safe_character_dirname(cn)
            p = _P(s.projects_dir) / pid / "characters" / safe_cn / fn
            if not p.is_file():
                raise HTTPException(404, detail=f"角色立绘文件不存在: {p}")
            out.append(str(p))
        elif kind == "element":
            scope = r.get("scope") or "global"
            eid = r.get("element_id")
            if eid is None:
                raise HTTPException(400, detail=f"element ref 缺 element_id: {r}")
            from services.elements_repo import get_element_path
            try:
                p = get_element_path(scope, int(eid))
            except Exception as e:
                raise HTTPException(404, detail=f"element {eid}@{scope} 不可用: {e}")
            if not p:
                raise HTTPException(404, detail=f"element {eid}@{scope} 文件不存在")
            out.append(str(p))
        elif kind == "path":
            p = r.get("path") or ""
            if not p or not _P(p).is_file():
                raise HTTPException(404, detail=f"path ref 文件不存在: {p}")
            out.append(str(p))
        else:
            raise HTTPException(400, detail=f"不支持的 ref kind: {kind!r}")
    return out


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

    ref_paths = _resolve_ref_paths(req.refs) if req.refs else []

    async def stream():
        async for event in generate_image(
            cfg, workflow, req.positive_prompt, req.negative_prompt, req.seed, w, h,
            ref_image_paths=ref_paths or None,
            workflow_name=req.workflow_name,
        ):
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
        # 轮 5: 每个 frame 自带 refs
        try:
            frame_ref_paths = _resolve_ref_paths(frame.get("refs") or [])
        except HTTPException as e:
            await queue.put({"event": "error", "message": f"参考图解析失败: {e.detail}", **meta})
            done_count += 1
            if done_count >= total_tasks:
                finished.set()
            return
        async for event in generate_image(
            cfg, workflow, frame.get("prompt", ""), req.negative_prompt,
            width=w, height=h,
            ref_image_paths=frame_ref_paths or None,
            workflow_name=req.workflow_name,
        ):
            ev_out = {**event, **meta}
            # D1: project_id 提供时由后端直接落盘 → 事件加 file_path（前端可不再 base64 PUT）
            if event.get("event") == "completed" and req.project_id:
                imgs = event.get("images") or []
                if imgs and (imgs[0] or {}).get("data"):
                    try:
                        import base64 as _b64
                        from pathlib import Path as _P
                        from config import load_settings as _ls
                        pid = req.project_id
                        sid = frame["scene_id"]; ft = frame["frame_type"]
                        img_dir = _P(_ls().projects_dir) / pid / "images"
                        img_dir.mkdir(parents=True, exist_ok=True)
                        filename = f"{sid}_{ft}_{slot}.png"
                        (img_dir / filename).write_bytes(_b64.b64decode(imgs[0]["data"]))
                        rel = f"images/{filename}"
                        ev_out["file_path"] = rel
                        ev_out["url"] = f"/api/projects/{pid}/assets/file/{sid}/" \
                                        f"{'image_start' if ft == 'start' else 'image_end'}/{slot}"
                        # 同步 SQLite scene_assets（自动推进状态）
                        from services.project_repo import record_asset
                        record_asset(
                            pid, sid,
                            "image_start" if ft == "start" else "image_end",
                            slot_index=slot, file_path=rel, format="png",
                            is_selected=(slot == 0),
                        )
                    except Exception as e:
                        print(f"[image-batch] auto-persist failed: {e}", flush=True)
            await queue.put(ev_out)
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

