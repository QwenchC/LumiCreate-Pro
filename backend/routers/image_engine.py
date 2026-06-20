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


class LoraSpec(BaseModel):
    name:     str = ""
    strength: float = 1.0


class SdParams(BaseModel):
    """v1.4.4: sd_default_workflow 暴露的全套可调参数。
    前端检测到 sd_default_workflow 时显示对应面板，把这些参数发过来。
    其它 t2i / i2i 工作流不发该字段。
    """
    checkpoint:   str = ""
    loras:        list[LoraSpec] = []
    steps:        int   = 0   # 0 = 用工作流默认
    cfg:          float = 0.0
    sampler_name: str = ""
    scheduler:    str = ""


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
    sd_params: Optional[SdParams] = None   # v1.4.4: SD 工作流高级参数


# v1.4.5: Pollinations 模型列表
@router.get("/pollinations/models")
async def pollinations_models():
    """从 Pollinations 拉活的图片模型列表（失败时回退内置兜底列表）。"""
    from services.pollinations_image import fetch_pollinations_image_models
    cfg = load_settings().image_engine
    base_url = getattr(cfg, "pollinations_base_url", "") or "https://gen.pollinations.ai"
    return {"models": await fetch_pollinations_image_models(base_url)}


@router.get("/pollinations/test", response_model=ConnectionTestResult)
async def pollinations_test():
    """连通性 + API key 校验。"""
    from services.pollinations_image import test_pollinations_connection
    cfg = load_settings().image_engine
    result = await test_pollinations_connection(
        getattr(cfg, "pollinations_base_url", "") or "https://gen.pollinations.ai",
        getattr(cfg, "pollinations_api_key", "") or "",
    )
    return ConnectionTestResult(success=bool(result.get("success")),
                                 message=str(result.get("message") or ""))


# v1.4.4: 给 SD 工作流面板提供可选模型列表
@router.get("/model-info")
async def get_model_info():
    """从 ComfyUI /object_info 拉 checkpoints / loras / samplers / schedulers 枚举。"""
    from services.sd_workflow import fetch_sd_model_info
    cfg = load_settings().image_engine
    return await fetch_sd_model_info(cfg.comfyui_url)


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
    from services.comfyui import get_workflow_json, bundled_workflow_dir, _flatten_subgraphs
    from services.workflow_meta import (
        classify_workflow, load_meta, get_ref_image_nodes,
        get_image_workflow_ref_count,
    )
    from pathlib import Path
    cfg = load_settings().image_engine

    # v1.4.5: Pollinations 模式没有工作流概念，直接返回 t2i shape
    if getattr(cfg, "engine_type", "comfyui") == "pollinations":
        return {
            "kind": "t2i", "ref_count": 0, "ref_nodes": [],
            "actual_loadimage_count": 0, "found": True,
            "engine_type": "pollinations",
        }
    # v1.4.11+: 火山引擎 Seedream 同样无 ComfyUI 工作流概念
    if getattr(cfg, "engine_type", "comfyui") == "volcengine_seedream":
        return {
            "kind": "t2i", "ref_count": 0, "ref_nodes": [],
            "actual_loadimage_count": 0, "found": True,
            "engine_type": "volcengine_seedream",
        }

    workflow = await get_workflow_json(cfg, workflow_name)
    if workflow is None:
        return {"kind": "unknown", "ref_count": 0, "ref_nodes": [], "found": False,
                "engine_type": "comfyui"}

    # v1.4.1+: bundled 优先（与 list 端点一致）
    bundled = bundled_workflow_dir()
    wf_path = None
    if bundled is not None and (bundled / f"{workflow_name}.json").exists():
        wf_path = bundled / f"{workflow_name}.json"
    else:
        wf_dir = Path(cfg.workflow_dir or "")
        if wf_dir.exists():
            wf_path = wf_dir / f"{workflow_name}.json"

    kind = classify_workflow(workflow_name, workflow=workflow,
                              workflow_path=str(wf_path) if wf_path else None)
    meta = load_meta(str(wf_path), type_="image") if wf_path else {}

    # ref_count 按 kind 决定（i2i_multi 时按真实 LoadImage 节点数，上限 8）
    ref_count = get_image_workflow_ref_count(kind, workflow=workflow)

    # ref_nodes: 优先 meta 显式，否则在展平后的 workflow 上扫
    try:
        flat = _flatten_subgraphs(workflow)
    except Exception:
        flat = workflow
    ref_nodes = get_ref_image_nodes(meta, workflow=flat)

    # 实际 LoadImage 节点数（含 subgraph 内部，供前端诊断）
    actual = sum(1 for n in (flat.get("nodes") or [])
                  if n.get("type") == "LoadImage")

    return {
        "kind": kind,
        "ref_count": ref_count,
        "ref_nodes": ref_nodes[:ref_count] if ref_count else [],
        "actual_loadimage_count": actual,
        "found": True,
        "engine_type": "comfyui",
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
    # v1.4.4: SD 工作流的高级参数（所有 frame 共用，因为 ckpt / LoRA / sampler 是整批一致的）
    sd_params: Optional[SdParams] = None


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
            # v1.6.2: 系列项目立绘存于系列共享目录 → 经 _character_base 重定向，
            # 否则系列各集做 i2i 立绘参考会 404（共享角色一致性的核心路径）。
            from routers.projects import _safe_character_dirname, _character_base
            safe_cn = _safe_character_dirname(cn)
            p = _character_base(pid) / "characters" / safe_cn / fn
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
    # v1.4.11+: 按 engine_type 分派
    if getattr(cfg, "engine_type", "comfyui") == "volcengine_seedream":
        from services.volcengine_seedream import test_seedream_connection
        ok, msg = await test_seedream_connection(
            getattr(cfg, "seedream_base_url", "") or
                "https://ark.cn-beijing.volces.com/api/v3",
            getattr(cfg, "seedream_api_key", "") or "",
        )
        return ConnectionTestResult(success=ok,
                                    message=f"火山引擎 Seedream：{msg}")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{cfg.comfyui_url}/system_stats")
            r.raise_for_status()
        return ConnectionTestResult(success=True, message="ComfyUI 连接成功")
    except Exception as e:
        return ConnectionTestResult(success=False, message=str(e))


# v1.4.11+: 火山引擎 Seedream 独立连通性测试（不依赖 engine_type 切换）
@router.get("/seedream/test", response_model=ConnectionTestResult)
async def seedream_test():
    from services.volcengine_seedream import test_seedream_connection
    cfg = load_settings().image_engine
    ok, msg = await test_seedream_connection(
        getattr(cfg, "seedream_base_url", "") or
            "https://ark.cn-beijing.volces.com/api/v3",
        getattr(cfg, "seedream_api_key", "") or "",
    )
    return ConnectionTestResult(success=ok, message=msg)


@router.get("/workflows", response_model=list[str])
async def get_workflows():
    """v1.4.1: 只返回当前后端能驱动的图片工作流（t2i / i2i_single / i2i_double）。
    视频工作流虽然在同一目录，但不会出现在图片下拉里。
    v1.4.5: engine_type='pollinations' 时返回 Pollinations 模型名列表（下拉用同一字段）。"""
    from services.workflow_meta import is_supported_image_workflow
    from services.comfyui import get_workflow_json
    from pathlib import Path as _P
    cfg = load_settings().image_engine

    # v1.4.5: Pollinations 模式直接返回模型列表
    if getattr(cfg, "engine_type", "comfyui") == "pollinations":
        from services.pollinations_image import fetch_pollinations_image_models
        return await fetch_pollinations_image_models(
            getattr(cfg, "pollinations_base_url", "") or "https://gen.pollinations.ai"
        )
    # v1.4.11+: Seedream 没有"列模型"API，返合成名一项让前端下拉有得选
    if getattr(cfg, "engine_type", "comfyui") == "volcengine_seedream":
        return ["volcengine_seedream"]

    try:
        names = await list_workflows(cfg)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    out: list[str] = []
    wf_dir = _P(cfg.workflow_dir or "")
    for name in names:
        try:
            wf = await get_workflow_json(cfg, name)
            wf_path = (wf_dir / f"{name}.json") if wf_dir.is_dir() else None
            if is_supported_image_workflow(name, workflow=wf,
                                            workflow_path=str(wf_path) if wf_path else None):
                out.append(name)
        except Exception:
            pass
    return out


# v1.4.1: 旧端点：把所有 json 文件（包括视频工作流）作为下拉项时用
@router.get("/workflows-all", response_model=list[str])
async def get_workflows_all():
    """不做过滤，返回工作流目录下的全部 *.json（调试 / 高级用户用）。"""
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
    meta = {"scene_id": req.scene_id, "frame_type": req.frame_type, "slot_index": req.slot_index}
    w = req.width  or cfg.image_width
    h = req.height or cfg.image_height

    # v1.4.5: Pollinations 路径 —— 不走 ComfyUI 工作流
    if getattr(cfg, "engine_type", "comfyui") == "pollinations":
        from services.pollinations_image import generate_image_pollinations
        # workflow_name 在 Pollinations 模式下当作模型名（保持前端字段语义一致）
        model = req.workflow_name or cfg.pollinations_model or "flux"

        async def stream_pollinations():
            async for event in generate_image_pollinations(
                base_url = cfg.pollinations_base_url,
                api_key  = cfg.pollinations_api_key,
                model    = model,
                prompt   = req.positive_prompt,
                width    = w, height = h,
                seed     = req.seed,
            ):
                yield _sse({**event, **meta})
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_pollinations(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    # v1.4.11+: 火山引擎 Seedream 路径（云端付费）—— 同样不走 ComfyUI
    if getattr(cfg, "engine_type", "comfyui") == "volcengine_seedream":
        from services.volcengine_seedream import generate_image_seedream
        # 模型 ID 用 settings 主表单的 seedream_model；workflow_name 可作覆盖
        model = (req.workflow_name if req.workflow_name and
                 req.workflow_name != "volcengine_seedream" else "") or \
                getattr(cfg, "seedream_model", "") or ""

        async def stream_seedream():
            async for event in generate_image_seedream(
                base_url = getattr(cfg, "seedream_base_url", ""),
                api_key  = getattr(cfg, "seedream_api_key", ""),
                model    = model,
                prompt   = req.positive_prompt,
                width    = w, height = h,
                seed     = req.seed if req.seed and req.seed >= 0 else None,
                response_format = getattr(cfg, "seedream_response_format", "url"),
            ):
                yield _sse({**event, **meta})
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_seedream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    # ComfyUI 路径（默认）
    workflow = await _load_workflow(cfg, req.workflow_name)

    # v1.4.4: SD 工作流先打补丁（其它工作流跳过）
    if req.sd_params and req.workflow_name == "sd_default_workflow":
        from services.sd_workflow import patch_sd_workflow
        workflow = patch_sd_workflow(
            workflow,
            checkpoint=req.sd_params.checkpoint,
            loras=[l.model_dump() for l in req.sd_params.loras],
            steps=req.sd_params.steps,
            cfg=req.sd_params.cfg,
            sampler_name=req.sd_params.sampler_name,
            scheduler=req.sd_params.scheduler,
        )

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

    # v1.4.5: Pollinations 路径 —— 跳过 ComfyUI 工作流加载，按 prompt 直跑
    is_pollinations = getattr(cfg, "engine_type", "comfyui") == "pollinations"
    is_seedream    = getattr(cfg, "engine_type", "comfyui") == "volcengine_seedream"
    workflow = None
    if not is_pollinations and not is_seedream:
        workflow = await _load_workflow(cfg, req.workflow_name)

    # v1.4.4: SD 工作流先打补丁（一次，整批共用；云端模式跳过）
    if not is_pollinations and not is_seedream and req.sd_params and req.workflow_name == "sd_default_workflow":
        from services.sd_workflow import patch_sd_workflow
        workflow = patch_sd_workflow(
            workflow,
            checkpoint=req.sd_params.checkpoint,
            loras=[l.model_dump() for l in req.sd_params.loras],
            steps=req.sd_params.steps,
            cfg=req.sd_params.cfg,
            sampler_name=req.sd_params.sampler_name,
            scheduler=req.sd_params.scheduler,
        )

    gen_count = max(1, min(req.gen_count, 10))
    total_tasks = len(req.frames) * gen_count
    w = req.width  or cfg.image_width
    h = req.height or cfg.image_height

    queue: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()
    done_count = 0

    # A1: 收集失败镜次的最后错误，批量结束时持久化
    scene_errors: dict[str, str] = {}

    # v1.4.5: Pollinations 模式按模型名选择（workflow_name 字段当模型名用）
    poll_model = req.workflow_name or getattr(cfg, "pollinations_model", "flux") or "flux"

    async def run_one(frame: dict, slot: int):
        nonlocal done_count
        meta = {"scene_id": frame["scene_id"], "frame_type": frame["frame_type"], "slot_index": slot}

        # v1.4.11+: Seedream 路径（云端，无 ComfyUI 工作流）
        if is_seedream:
            from services.volcengine_seedream import generate_image_seedream
            seedream_model = (req.workflow_name if req.workflow_name and
                              req.workflow_name != "volcengine_seedream" else "") or \
                             getattr(cfg, "seedream_model", "") or ""
            gen = generate_image_seedream(
                base_url = getattr(cfg, "seedream_base_url", ""),
                api_key  = getattr(cfg, "seedream_api_key", ""),
                model    = seedream_model,
                prompt   = frame.get("prompt", ""),
                width    = w, height = h,
                seed     = None,
                response_format = getattr(cfg, "seedream_response_format", "url"),
            )
            async for event in gen:
                ev_out = {**event, **meta}
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
                            from services.project_repo import record_asset
                            record_asset(
                                pid, sid,
                                "image_start" if ft == "start" else "image_end",
                                slot_index=slot, file_path=rel, format="png",
                                is_selected=(slot == 0),
                            )
                        except Exception as e:
                            print(f"[image-batch-seedream] auto-persist failed: {e}", flush=True)
                await queue.put(ev_out)
                if event.get("event") == "error":
                    scene_errors[f"{frame['scene_id']}:{frame['frame_type']}"] = \
                        str(event.get("message", "unknown error"))[:500]
            done_count += 1
            if done_count >= total_tasks:
                finished.set()
            return

        # Pollinations 路径：无参考图、无工作流，直接调 prompt
        if is_pollinations:
            from services.pollinations_image import generate_image_pollinations
            gen = generate_image_pollinations(
                base_url = cfg.pollinations_base_url,
                api_key  = cfg.pollinations_api_key,
                model    = poll_model,
                prompt   = frame.get("prompt", ""),
                width    = w, height = h,
                seed     = None,    # 每张都新随机
            )
            async for event in gen:
                ev_out = {**event, **meta}
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
                            from services.project_repo import record_asset
                            record_asset(
                                pid, sid,
                                "image_start" if ft == "start" else "image_end",
                                slot_index=slot, file_path=rel, format="png",
                                is_selected=(slot == 0),
                            )
                        except Exception as e:
                            print(f"[image-batch-poll] auto-persist failed: {e}", flush=True)
                await queue.put(ev_out)
                if event.get("event") == "error":
                    scene_errors[f"{frame['scene_id']}:{frame['frame_type']}"] = \
                        str(event.get("message", "unknown error"))[:500]
            done_count += 1
            if done_count >= total_tasks:
                finished.set()
            return

        # ComfyUI 路径（默认）
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



# ── v1.6.1: 角色「标准造型」立绘（Z-Image ControlNet + 固定姿势图）─────────────
#
# 用固定姿势图做 ControlNet 约束 + 角色外貌提示词，生成【空白背景】特定角色姿势图，
# 供 MSR 多图参考视频做角色参考。尺寸按姿势图比例自适应（不约束竖幅）。
# 事件 schema 与 /generate-stream 一致（queued/progress/completed.images/error），
# 前端复用现有立绘上传通路（白底标记 white_bg=True）。


class StandardPoseRequest(BaseModel):
    appearance:  str = ""     # 角色外貌（来自角色卡）
    style:       str = ""     # 画风前缀（可选）
    orientation: str = "landscape"   # 'landscape'(横幅) | 'portrait'(竖幅)；决定姿势图 → 出图朝向


@router.post("/generate-standard-pose")
async def generate_standard_pose_stream(req: StandardPoseRequest):
    cfg = load_settings().image_engine
    from services.standard_pose import (
        load_bundled_zimage_workflow, bundled_pose_image_path, generate_standard_pose)

    if load_bundled_zimage_workflow() is None:
        raise HTTPException(404, detail="未找到 Z-Image ControlNet 标准造型工作流")
    pose_path = bundled_pose_image_path(req.orientation)
    if pose_path is None:
        raise HTTPException(404, detail="未找到固定姿势图（assets/pic/character_default_pose*.png）")
    try:
        pose_bytes = pose_path.read_bytes()
    except Exception as e:
        raise HTTPException(500, detail=f"读取姿势图失败: {e}")

    async def stream():
        async for event in generate_standard_pose(
            cfg, pose_image_bytes=pose_bytes,
            appearance=req.appearance, style=req.style,
        ):
            yield _sse(event)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
