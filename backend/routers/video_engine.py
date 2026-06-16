"""
Video engine router — LTX-2.3 first-frame-to-last-frame via ComfyUI.

Endpoints:
  GET  /test                  — connectivity check
  GET  /workflows             — list ComfyUI video workflows
  POST /generate-stream       — SSE: generate video per scene (sequential)
  POST /merge-project-video   — concat all scene videos into one final MP4
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import load_settings
from services.comfyui import list_workflows, get_workflow_json
from services.ltx2video import _find_ffmpeg

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ConnectionTestResult(BaseModel):
    success: bool
    message: str


class VolcSceneRef(BaseModel):
    """v1.4.10+: 火山引擎 Seedance 多模态参考图条目。
    kind 决定 backend 怎么解析；driver 最终拿到 base64 / URL 喂给 Ark API。
    """
    kind: str   # 'portrait' | 'element' | 'scene_start' | 'scene_end' | 'b64'
    # portrait
    project_id: Optional[str] = None
    char_name:  Optional[str] = None
    filename:   Optional[str] = None
    # element
    scope:      Optional[str] = None
    element_id: Optional[int] = None
    # b64（前端直接喂 base64，scene_start/scene_end 也用这个通道）
    image_b64:  Optional[str] = None


class VolcSceneOptions(BaseModel):
    """每个分镜独立的火山引擎策略（None = 用全局设置默认值）。"""
    # 模式：t2v 纯文生 / i2v_first 单首帧驱动 / i2v_flf 首末帧驱动 / multi_ref 多参考
    mode:          Optional[str] = None
    duration_secs: Optional[int] = None
    references:    list[VolcSceneRef] = []


class SceneVideoRequest(BaseModel):
    scene_id:        str
    scene_index:     int
    start_image_b64: str = ""
    end_image_b64:   str = ""    # i2v 工作流不需要
    audio_b64:       str = ""    # 空 = 无音频模式（flfa2i + i2v 都接受）
    duration_ms:     int = 4000
    positive_prompt: str = ""
    # v1.4.10+: 火山引擎模式下的每分镜配置（其它引擎忽略此字段）
    volcengine_options: Optional[VolcSceneOptions] = None


# D2: 视频工作流前置检查
@router.get("/precheck")
async def precheck_video_workflow_endpoint(workflow_name: str):
    from services.comfyui_precheck import precheck_video_workflow
    cfg = load_settings().video_engine
    result = await precheck_video_workflow(cfg.comfyui_url, workflow_name)
    return {"ok": result.ok, "issues": result.issues, "info": result.info}


# v1.4.1: 视频工作流分类（前端用来决定显示几个图片槽 + 是否需要音频）
@router.get("/workflow-info")
async def video_workflow_info(workflow_name: str):
    from services.workflow_meta import classify_video_workflow, get_video_workflow_features
    from services.comfyui import get_workflow_json
    from pathlib import Path as _P

    cfg  = load_settings()
    vcfg = cfg.video_engine
    icfg = cfg.image_engine
    wdir = vcfg.workflow_dir or icfg.workflow_dir

    class _Cfg:
        def __init__(self, url, wd):
            self.comfyui_url  = url
            self.workflow_dir = wd

    wf = await get_workflow_json(_Cfg(vcfg.comfyui_url, wdir), workflow_name)
    if wf is None:
        return {**get_video_workflow_features("unknown"), "found": False}
    wf_path = _P(wdir) / f"{workflow_name}.json" if wdir else None
    kind = classify_video_workflow(workflow_name, workflow=wf,
                                     workflow_path=str(wf_path) if wf_path else None)
    return {**get_video_workflow_features(kind), "found": True}


class VideoGenerateRequest(BaseModel):
    workflow_name: str
    resolution:    str = "720x1280"
    fps:           float = 25.0
    scenes:        list[SceneVideoRequest]
    # A1: 让后端在批量结束时把失败镜次写入 last_run_errors.json
    project_id:    str = ""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _volc_refs_to_b64_list(
        refs: list, scene_start_b64: str = "", scene_end_b64: str = "",
) -> list[str]:
    """v1.4.10+: 把火山引擎每分镜的 references 解析为 base64 列表。

    复用 image_engine._resolve_ref_paths 处理 portrait / element 来源，
    scene_start / scene_end 直接用前端已经传过来的 b64。
    """
    import base64 as _b64
    out: list[str] = []
    if not refs:
        return out
    # 抽出需要走 path 解析的 refs（portrait / element）
    path_refs: list[dict] = []
    placeholders: list[Optional[str]] = []   # 占位列表保留顺序
    for r in refs:
        rd = r.model_dump() if hasattr(r, "model_dump") else dict(r or {})
        kind = (rd.get("kind") or "").strip()
        if kind == "scene_start":
            placeholders.append(scene_start_b64 or None)
        elif kind == "scene_end":
            placeholders.append(scene_end_b64 or None)
        elif kind == "b64":
            placeholders.append((rd.get("image_b64") or "").strip() or None)
        elif kind in ("portrait", "element", "path"):
            placeholders.append(None)
            path_refs.append(rd)
        else:
            placeholders.append(None)   # 未知类型静默跳过
    # 批量解析 path
    from routers.image_engine import _resolve_ref_paths
    paths_iter = iter(_resolve_ref_paths(path_refs))
    # 串回 placeholders
    for i, ph in enumerate(placeholders):
        if ph is not None:
            out.append(ph); continue
        if i < len(refs):
            rd = refs[i].model_dump() if hasattr(refs[i], "model_dump") \
                else dict(refs[i] or {})
            kind = (rd.get("kind") or "").strip()
            if kind in ("portrait", "element", "path"):
                p = next(paths_iter, None)
                if p:
                    try:
                        out.append(_b64.b64encode(open(p, "rb").read()).decode("ascii"))
                    except Exception:
                        pass
    return [b for b in out if b]


def _parse_resolution(res: str) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in res.lower().split("x"))
    except Exception:
        w, h = 720, 1280
    w = max(64, min(w, 1280))
    h = max(64, min(h, 1280))
    w = (w // 32) * 32
    h = (h // 32) * 32
    return w, h


# ── Connectivity ───────────────────────────────────────────────────────────────

@router.get("/test", response_model=ConnectionTestResult)
async def test_connection():
    cfg = load_settings().video_engine
    # v1.4.10: 按 engine_type 分派 —— 火山引擎模式探活云端 Ark
    if getattr(cfg, "engine_type", "comfyui") == "volcengine_seedance":
        from services.volcengine_seedance import test_seedance_connection
        ok, msg = await test_seedance_connection(
            cfg.volcengine_base_url, cfg.volcengine_api_key,
        )
        return ConnectionTestResult(success=ok,
                                    message=f"火山引擎 Seedance：{msg}")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{cfg.comfyui_url}/system_stats")
            r.raise_for_status()
        return ConnectionTestResult(success=True, message="ComfyUI (Video) 连接成功")
    except Exception as e:
        return ConnectionTestResult(success=False, message=str(e))


@router.get("/volcengine-test", response_model=ConnectionTestResult)
async def test_volcengine_connection():
    """v1.4.10: 独立的火山引擎连通性测试 —— 不依赖 engine_type 切换，让用户在
    切换之前就能确认 API key + 端点正确。"""
    cfg = load_settings().video_engine
    from services.volcengine_seedance import test_seedance_connection
    ok, msg = await test_seedance_connection(
        cfg.volcengine_base_url, cfg.volcengine_api_key,
    )
    return ConnectionTestResult(success=ok, message=msg)


@router.get("/workflows", response_model=list[str])
async def get_video_workflows():
    """v1.4.1+: 只列举项目自带 workflows/ 目录里能被识别为视频工作流的文件
    (video_flfa2i / video_i2v)。用户的 ComfyUI 目录里其它工作流不显示。
    v1.4.10: 火山引擎模式直接返回一个合成名 'volcengine_seedance'，让前端
    工作流选择控件有得选 —— router 收到这个名字时走云端 dispatch，不真去
    ComfyUI 拉 workflow JSON。"""
    cfg  = load_settings()
    vcfg = cfg.video_engine
    if getattr(vcfg, "engine_type", "comfyui") == "volcengine_seedance":
        return ["volcengine_seedance"]

    from services.workflow_meta import is_supported_video_workflow
    from services.comfyui import bundled_workflow_dir, get_workflow_json

    class _Cfg:
        def __init__(self, url, wd):
            self.comfyui_url  = url
            self.workflow_dir = wd

    bundled = bundled_workflow_dir()
    if bundled is None:
        # 仓库结构异常时兜底用 cfg.workflow_dir
        wdir = vcfg.workflow_dir or cfg.image_engine.workflow_dir
        if not wdir or not Path(wdir).is_dir():
            return []
        names = [f.stem for f in Path(wdir).glob("*.json")]
        base = wdir
    else:
        names = [f.stem for f in bundled.glob("*.json")]
        base = str(bundled)

    supported: list[str] = []
    for name in names:
        try:
            wf = await get_workflow_json(_Cfg(vcfg.comfyui_url, base), name)
            wf_path = Path(base) / f"{name}.json"
            if is_supported_video_workflow(name, workflow=wf,
                                           workflow_path=str(wf_path) if wf_path.exists() else None):
                supported.append(name)
        except Exception:
            pass
    return sorted(set(supported))


# ── Video generation SSE ───────────────────────────────────────────────────────

@router.post("/generate-stream")
async def generate_video_stream(req: VideoGenerateRequest):
    cfg  = load_settings()
    vcfg = cfg.video_engine
    icfg = cfg.image_engine
    wdir = vcfg.workflow_dir or icfg.workflow_dir

    # v1.4.10: 火山引擎模式跳过 ComfyUI workflow 加载（远端不需要 workflow JSON）
    # —— wf_kind / wf_features / workflow_meta 都用占位的 dispatch-safe 值
    is_volc = getattr(vcfg, "engine_type", "comfyui") == "volcengine_seedance"

    workflow = None
    wf_path = None
    workflow_meta = None
    if not is_volc:
        class _Cfg:
            def __init__(self, url, wd):
                self.comfyui_url  = url
                self.workflow_dir = wd

        workflow = await get_workflow_json(_Cfg(vcfg.comfyui_url, wdir), req.workflow_name)
        if workflow is None:
            raise HTTPException(status_code=404, detail=f"工作流 '{req.workflow_name}' 未找到")

        # v1.4.1+: 解析 wf_path（优先 bundled）让 meta.json 也按相同优先级查
        from services.comfyui import bundled_workflow_dir
        from pathlib import Path as _P
        bundled = bundled_workflow_dir()
        if bundled is not None and (bundled / f"{req.workflow_name}.json").exists():
            wf_path = bundled / f"{req.workflow_name}.json"
        elif wdir and (_P(wdir) / f"{req.workflow_name}.json").exists():
            wf_path = _P(wdir) / f"{req.workflow_name}.json"

        # C1: 读取同名 .meta.json（如果存在），让节点 ID 可配置
        if wf_path is not None:
            from services.workflow_meta import load_meta
            workflow_meta = load_meta(wf_path, type_="video")

    width, height = _parse_resolution(req.resolution)
    total = len(req.scenes)

    # v1.4.1: 工作流类型决定走哪个 driver + 校验哪些字段
    if is_volc:
        # 火山引擎当作 flf2v：需要首帧；末帧可选；音频独立后期合成（与 LTX 不同）
        wf_kind = "video_volcengine_seedance"
        wf_features = {
            "requires_start_image": True,
            "requires_end_image":   False,
            "supports_audio":       False,
            "supports_duration":    True,
        }
    else:
        from services.workflow_meta import classify_video_workflow, get_video_workflow_features
        wf_kind = classify_video_workflow(req.workflow_name, workflow=workflow,
                                            workflow_path=str(wf_path) if wf_path else None)
        wf_features = get_video_workflow_features(wf_kind)

    # Error substring that indicates VRAM weight offload to CPU — safe to free+retry
    _VRAM_OFFLOAD_SIG = "should be the same"

    async def _free_vram() -> None:
        """Ask ComfyUI to unload models and free VRAM, then wait for it to settle."""
        import asyncio
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    f"{vcfg.comfyui_url}/free",
                    json={"unload_models": True, "free_memory": True},
                )
            await asyncio.sleep(3)
        except Exception:
            pass

    # A1: 收集失败镜次，批量结束时持久化
    scene_errors: dict[str, str] = {}

    def _record_err(sid: str, msg: str) -> None:
        scene_errors[str(sid)] = str(msg)[:500]

    # E2
    from datetime import datetime as _dt, timezone as _tz
    started_at = _dt.now(_tz.utc).isoformat()
    started_ms = int(__import__("time").time() * 1000)

    async def stream():
        from services.ltx2video import generate_video, generate_video_i2v

        for idx, scene in enumerate(req.scenes):
            # 必需字段校验（按 workflow kind 决定）
            if not scene.start_image_b64:
                _record_err(scene.scene_id, "缺少首帧图片")
                yield _sse({"event": "scene_error", "scene_id": scene.scene_id,
                            "scene_index": scene.scene_index,
                            "message": "缺少首帧图片"})
                continue
            if wf_features.get("requires_end_image") and not scene.end_image_b64:
                _record_err(scene.scene_id, "缺少末帧图片")
                yield _sse({"event": "scene_error", "scene_id": scene.scene_id,
                            "scene_index": scene.scene_index,
                            "message": "缺少末帧图片"})
                continue
            # 音频：flfa2i 可选（空字符串 = 无音频模式），i2v 不接受音频
            # 不再做"缺音频就 fail"的硬校验

            yield _sse({
                "event":       "scene_start",
                "scene_id":    scene.scene_id,
                "scene_index": scene.scene_index,
                "current":     idx + 1,
                "total":       total,
                "workflow_kind": wf_kind,
            })

            def _make_iter():
                # v1.4.10: 引擎 dispatch —— engine_type='volcengine_seedance' 走云端
                # Ark API；其它（默认 'comfyui'）走原 ComfyUI / LTX 通路，行为不变。
                if getattr(vcfg, "engine_type", "comfyui") == "volcengine_seedance":
                    from services.volcengine_seedance import generate_video_seedance
                    # v1.4.10+: 解析每分镜独立策略（mode / duration / refs）
                    vo = scene.volcengine_options
                    per_mode  = (vo.mode          if vo else None) or "i2v_first"
                    per_dur   = (vo.duration_secs if vo else None) or vcfg.volcengine_duration_secs
                    per_refs  = (vo.references    if vo else None) or []
                    # 把 portrait/element 解析成 b64；scene_start/scene_end 走前端传来的 b64
                    refs_b64 = _volc_refs_to_b64_list(
                        per_refs,
                        scene_start_b64=scene.start_image_b64,
                        scene_end_b64=scene.end_image_b64,
                    )
                    # 模式映射：
                    #   t2v        → use_image=False（无图）
                    #   i2v_first  → first 仅传首帧
                    #   i2v_flf    → first + last
                    #   multi_ref  → multi_refs_b64 列表（Seedance 2.0）
                    use_img         = per_mode != "t2v"
                    first_b64       = ""
                    last_b64        = ""
                    multi_refs_send = None
                    if per_mode == "multi_ref":
                        multi_refs_send = refs_b64
                    elif per_mode == "i2v_flf":
                        first_b64 = scene.start_image_b64
                        last_b64  = scene.end_image_b64
                    elif per_mode == "i2v_first":
                        first_b64 = scene.start_image_b64
                    return generate_video_seedance(
                        base_url        = vcfg.volcengine_base_url,
                        api_key         = vcfg.volcengine_api_key,
                        model_id        = vcfg.volcengine_model_id,
                        first_frame_b64 = first_b64,
                        last_frame_b64  = last_b64,
                        multi_refs_b64  = multi_refs_send,
                        positive_prompt = scene.positive_prompt,
                        duration_secs   = per_dur,
                        resolution      = vcfg.volcengine_resolution,
                        ratio           = getattr(vcfg, "volcengine_ratio", "adaptive"),
                        use_image       = use_img,
                        generate_audio  = getattr(vcfg, "volcengine_generate_audio", False),
                        watermark       = getattr(vcfg, "volcengine_watermark", False),
                        camera_fixed    = getattr(vcfg, "volcengine_camera_fixed", False),
                        seed            = getattr(vcfg, "volcengine_seed", -1),
                        poll_interval   = vcfg.volcengine_poll_interval,
                        poll_timeout    = vcfg.volcengine_poll_timeout,
                        scene_id        = scene.scene_id,
                    )
                if wf_kind == "video_i2v":
                    return generate_video_i2v(
                        comfyui_url       = vcfg.comfyui_url,
                        workflow          = workflow,
                        first_frame_b64   = scene.start_image_b64,
                        width             = width,
                        height            = height,
                        fps               = req.fps,
                        duration_ms       = scene.duration_ms,
                        positive_prompt   = scene.positive_prompt,
                        scene_id          = scene.scene_id,
                        comfyui_input_dir = vcfg.comfyui_input_dir,
                        workflow_dir      = wdir or "",
                    )
                return generate_video(
                    comfyui_url       = vcfg.comfyui_url,
                    workflow          = workflow,
                    first_frame_b64   = scene.start_image_b64,
                    last_frame_b64    = scene.end_image_b64,
                    audio_b64         = scene.audio_b64,
                    width             = width,
                    height            = height,
                    fps               = req.fps,
                    duration_ms       = scene.duration_ms,
                    positive_prompt   = scene.positive_prompt,
                    scene_id          = scene.scene_id,
                    comfyui_input_dir = vcfg.comfyui_input_dir,
                    workflow_dir      = wdir or "",
                    workflow_meta     = workflow_meta,
                )

            for attempt in range(2):   # at most one retry
                vram_error = False
                async for event in _make_iter():
                    ev  = event.get("event")
                    msg = event.get("message", "")
                    if ev == "error":
                        if _VRAM_OFFLOAD_SIG in msg and attempt == 0:
                            # VRAM offload detected on first attempt — free and retry
                            vram_error = True
                            break
                        _record_err(scene.scene_id, msg or "unknown error")
                        yield _sse({**event, "event": "scene_error",
                                    "scene_index": scene.scene_index})
                        break
                    elif ev == "completed":
                        # D1: project_id 提供时由后端直接落盘 + 事件加 file_path
                        ev_out = {**event, "event": "scene_done",
                                  "scene_index": scene.scene_index}
                        if req.project_id and event.get("video"):
                            try:
                                import base64 as _b64
                                from pathlib import Path as _P
                                from config import load_settings as _ls
                                vid_dir = _P(_ls().projects_dir) / req.project_id / "video"
                                vid_dir.mkdir(parents=True, exist_ok=True)
                                filename = f"{scene.scene_id}.mp4"
                                (vid_dir / filename).write_bytes(
                                    _b64.b64decode(event["video"])
                                )
                                rel = f"video/{filename}"
                                ev_out["file_path"] = rel
                                ev_out["url"] = (
                                    f"/api/projects/{req.project_id}/assets/file/"
                                    f"{scene.scene_id}/video"
                                )
                                # 同步 SQLite scene_assets（自动推进 → video_ready）
                                from services.project_repo import record_asset
                                record_asset(
                                    req.project_id, scene.scene_id, "video",
                                    slot_index=0, file_path=rel, format="mp4",
                                    is_selected=True,
                                )
                                # videos.json 也维护一份（前端老路径仍能用）
                                meta_path = _P(_ls().projects_dir) / req.project_id / "videos.json"
                                metadata: dict = {}
                                if meta_path.exists():
                                    try:
                                        metadata = json.loads(
                                            meta_path.read_text(encoding="utf-8-sig")
                                        )
                                    except Exception:
                                        metadata = {}
                                metadata[scene.scene_id] = filename
                                meta_path.write_text(
                                    json.dumps(metadata, ensure_ascii=False, indent=2),
                                    encoding="utf-8",
                                )
                            except Exception as e:
                                print(f"[video-batch] auto-persist failed: {e}", flush=True)
                        yield _sse(ev_out)
                        break
                    else:
                        yield _sse(event)

                if vram_error:
                    yield _sse({"event":    "scene_retrying",
                                "scene_id": scene.scene_id,
                                "message":  "检测到 VRAM 权重迁移，释放显存后重试…"})
                    await _free_vram()
                    # attempt=1 will re-run generate_video
                else:
                    break   # success or non-retryable error — next scene

        # A1: 落盘失败镜次
        if req.project_id:
            try:
                from routers.projects import write_last_run_errors
                write_last_run_errors(req.project_id, "video", scene_errors)
            except Exception as e:
                print(f"[video-batch] write_last_run_errors failed: {e}", flush=True)
        # E2
        try:
            from services.task_history import append as _th_append
            ended_at = _dt.now(_tz.utc).isoformat()
            ended_ms = int(__import__("time").time() * 1000)
            _th_append(
                "video",
                req.project_id or "(no-project)",
                started_at=started_at, ended_at=ended_at,
                duration_ms=ended_ms - started_ms,
                items=total, errors=len(scene_errors),
                note=f"workflow={req.workflow_name}, {req.resolution}@{req.fps}fps",
            )
        except Exception as e:
            print(f"[video-batch] task_history append failed: {e}", flush=True)
        yield _sse({"event": "batch_done", "total": total, "errors": scene_errors})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Merge project video ────────────────────────────────────────────────────────

class MergeVideoRequest(BaseModel):
    project_id: str
    scene_order: list[str]   # scene_id list in display order
    # D3: 镜间过渡
    transition: str = "cut"                  # "cut" | "fade" | "dissolve" | "wipeleft" | "wiperight" | "slideleft" | "slideright"
    transition_duration_ms: int = 300        # 过渡时长（"cut" 时忽略）
    # D1: BGM
    bgm_volume_db: float = -20.0             # BGM 相对原音的音量（负值越大越轻），关闭 BGM 用 -100
    bgm_fade_in_ms: int = 1000
    bgm_fade_out_ms: int = 1500


class MergeVideoResult(BaseModel):
    output_path: str
    output_dir: str


# D1: BGM 上传 / 查询 / 删除（一个项目最多一首 BGM，文件名固定 bgm.<ext>）
ALLOWED_BGM_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}


def _proj_bgm_path(project_id: str) -> tuple[Optional[Path], Optional[Path]]:
    """返回 (bgm_dir, existing_bgm_file)。existing 为 None 时表示无 BGM。"""
    from config import load_settings as _ls
    proj_dir = Path(_ls().projects_dir) / project_id
    bgm_dir = proj_dir / "bgm"
    if not bgm_dir.exists():
        return bgm_dir, None
    for ext in ALLOWED_BGM_EXT:
        f = bgm_dir / f"bgm{ext}"
        if f.exists():
            return bgm_dir, f
    return bgm_dir, None


@router.get("/bgm/{project_id}")
async def get_project_bgm(project_id: str):
    """返回 BGM 元信息：是否存在、文件名。"""
    bgm_dir, existing = _proj_bgm_path(project_id)
    if not existing:
        return {"exists": False, "filename": "", "size": 0}
    return {"exists": True, "filename": existing.name, "size": existing.stat().st_size}


@router.delete("/bgm/{project_id}", status_code=204)
async def delete_project_bgm(project_id: str):
    bgm_dir, existing = _proj_bgm_path(project_id)
    if existing:
        existing.unlink(missing_ok=True)


class UploadBgmRequest(BaseModel):
    filename: str    # 原始文件名（仅用于取后缀）
    data:     str    # base64 音频


@router.put("/bgm/{project_id}")
async def upload_project_bgm(project_id: str, req: UploadBgmRequest):
    """上传 BGM。前端读取本地文件 → base64 → 此接口。"""
    import base64 as _b64
    ext = Path(req.filename).suffix.lower()
    if ext not in ALLOWED_BGM_EXT:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {ext}")
    bgm_dir, existing = _proj_bgm_path(project_id)
    if not bgm_dir:
        raise HTTPException(status_code=404, detail="项目不存在")
    bgm_dir.mkdir(parents=True, exist_ok=True)
    # 先清空旧文件
    for old_ext in ALLOWED_BGM_EXT:
        (bgm_dir / f"bgm{old_ext}").unlink(missing_ok=True)
    dest = bgm_dir / f"bgm{ext}"
    try:
        dest.write_bytes(_b64.b64decode(req.data))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"BGM 写入失败: {e}")
    return {"ok": True, "filename": dest.name, "size": dest.stat().st_size}


@router.post("/merge-project-video", response_model=MergeVideoResult)
async def merge_project_video(req: MergeVideoRequest):
    """Concatenate all scene MP4 files in order into one final video using ffmpeg concat demuxer."""
    cfg  = load_settings()
    vcfg = cfg.video_engine
    icfg = cfg.image_engine
    wdir = vcfg.workflow_dir or icfg.workflow_dir

    ffmpeg = _find_ffmpeg(vcfg.comfyui_input_dir, wdir)
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="未找到 ffmpeg 可执行文件，无法合并视频")

    from config import load_settings as _ls
    projects_dir = Path(_ls().projects_dir)
    proj_dir = projects_dir / req.project_id
    vid_dir  = proj_dir / "video"
    meta_path = proj_dir / "videos.json"

    if not meta_path.exists():
        raise HTTPException(status_code=400, detail="该项目尚无已保存的分镜视频")

    saved: dict = json.loads(meta_path.read_text(encoding="utf-8"))

    # Build ordered list of video files
    ordered_files: list[Path] = []
    for scene_id in req.scene_order:
        filename = saved.get(scene_id)
        if not filename:
            raise HTTPException(status_code=400, detail=f"分镜 {scene_id} 尚无视频，请先生成所有分镜")
        p = vid_dir / filename
        if not p.exists():
            raise HTTPException(status_code=400, detail=f"分镜视频文件不存在: {filename}")
        ordered_files.append(p)

    if not ordered_files:
        raise HTTPException(status_code=400, detail="没有可合并的视频")

    # 找 BGM（若有且 bgm_volume_db > -100 则纳入）
    _, bgm_file = _proj_bgm_path(req.project_id)
    use_bgm = bgm_file is not None and req.bgm_volume_db > -100

    transition = (req.transition or "cut").lower()
    use_xfade = transition != "cut" and len(ordered_files) >= 2

    video_dir = proj_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    out_path = video_dir / "final_video.mp4"

    # v1.5.1: 统一走 filter_complex 路径（逐镜 setpts 重定时 → 消除 AI 视频非标准帧率
    # 导致的"画面比音频快 1%"逐镜累积错位）。之前"无 BGM 无过渡"走 concat demuxer 快路径
    # 不做重定时，画面仍偏快 → 音画不同步。两条路径合并后所有合并都正确对齐。
    # 需要重新编码（codec copy 不能配合 filter_complex）
    inputs: list[str] = []
    for p in ordered_files:
        inputs += ["-i", str(p)]
    if use_bgm:
        # -stream_loop -1 必须出现在它对应的 -i 之前
        inputs += ["-stream_loop", "-1", "-i", str(bgm_file)]

    # 用 ffprobe 测每镜【容器】时长（= max(画面,音频)，漫剧里通常 = 音频）+【视频流】时长
    from services.exec_pool import run_blocking
    n = len(ordered_files)

    async def _probe(p, *sel):
        try:
            r = await run_blocking(
                subprocess.run,
                [ffmpeg.replace("ffmpeg", "ffprobe"), "-v", "error", *sel,
                 "-show_entries", "format=duration" if not sel else "stream=duration",
                 "-of", "default=nw=1:nk=1", str(p)],
                capture_output=True, text=True, timeout=10,
            )
            return float(r.stdout.strip() or "0")
        except Exception:
            return 0.0

    # 同时取容器、视频流、音频流时长：画面要补齐到的目标 = max(音频流, 容器)
    # （有的 mp4 容器时长报的是画面长度，必须显式拿音频流，否则补不够 → 残留累积错位）
    durations: list[float] = []   # 每镜的对齐目标长度（≈ 音频长度）
    v_secs: list[float] = []      # 每镜画面流时长
    for p in ordered_files:
        cont = await _probe(p) or 0.0
        vd   = await _probe(p, "-select_streams", "v:0")
        ad   = await _probe(p, "-select_streams", "a:0")
        target = max(ad, cont) or vd or 4.0
        durations.append(target)
        v_secs.append(vd)

    # v1.5.1 关键修复（逐镜实测根因）：AI 生成的分镜视频帧是按"非标准帧率"(常 ~23.7fps)
    # 生成的，却被标成 24fps 播放 → 每镜画面比其音频【快约 1%】(短几十~一百毫秒)。单镜
    # <20s 时察觉不到，但 80+ 镜拼接后累积成数秒"画面跑在音频前、末尾音频没播完"。
    # 正确做法：逐镜把【画面重定时】到其音频时长（setpts，按画面本应的速度播放）——
    # 画面与音频【全程】对齐(非仅末尾)、无定格、无累积漂移。
    ratios = [
        min(2.0, max(0.5, durations[i] / v_secs[i])) if v_secs[i] > 0.01 else 1.0
        for i in range(n)
    ]

    fc_parts: list[str] = []
    for i in range(n):
        if abs(ratios[i] - 1.0) > 0.001:
            fc_parts.append(f"[{i}:v]setpts=PTS*{ratios[i]:.6f},settb=AVTB[vp{i}]")
        else:
            fc_parts.append(f"[{i}:v]settb=AVTB[vp{i}]")

    last_v_label = "[vp0]"
    last_a_label = "[0:a]"
    td = max(0.05, req.transition_duration_ms / 1000.0)
    if use_xfade:
        cur_offset = 0.0
        for i in range(n - 1):
            cur_offset += durations[i] - td   # 画面已补到容器时长 → offset 用 durations 正确
            v_out = f"[v{i+1}]"
            a_out = f"[a{i+1}]"
            fc_parts.append(
                f"{last_v_label}[vp{i+1}]xfade=transition={transition}:duration={td}:offset={cur_offset:.3f}{v_out}"
            )
            # 音频也跟着 crossfade，保持衔接平顺
            fc_parts.append(
                f"{last_a_label}[{i+1}:a]acrossfade=d={td}{a_out}"
            )
            last_v_label = v_out
            last_a_label = a_out
    else:
        # 无过渡但仍走 filter_complex（因为有 BGM）；用 concat filter（画面已逐镜补齐）
        v_chain = "".join(f"[vp{i}]" for i in range(n))
        a_chain = "".join(f"[{i}:a]" for i in range(n))
        fc_parts.append(f"{v_chain}concat=n={n}:v=1:a=0[vcat]")
        fc_parts.append(f"{a_chain}concat=n={n}:v=0:a=1[acat]")
        last_v_label = "[vcat]"
        last_a_label = "[acat]"

    # 对齐后的总时长（画面≈音频）：作为 BGM 裁剪长度 + 输出 -t 安全封顶
    video_out_total = (sum(durations) - td * max(0, n - 1)) if use_xfade else sum(durations)

    final_audio_label = last_a_label
    if use_bgm:
        bgm_input_idx = len(ordered_files)   # BGM 是最后一个 -i
        gain = req.bgm_volume_db
        fi  = max(0, req.bgm_fade_in_ms)  / 1000.0
        fo  = max(0, req.bgm_fade_out_ms) / 1000.0
        # 画面已逐镜补齐到音频长度 → 用对齐后的总时长，BGM 与画面同时结束、淡出落在真正片尾
        total_dur = video_out_total
        # BGM 调音量 + fade in/out 裁剪到视频总时长
        fc_parts.append(
            f"[{bgm_input_idx}:a]volume={gain}dB,"
            f"afade=t=in:st=0:d={fi},"
            f"afade=t=out:st={max(0.0, total_dur - fo):.3f}:d={fo},"
            f"atrim=0:{total_dur:.3f}[bgm]"
        )
        # 与对白混合（duration=first → 跟主音轨长度对齐）
        fc_parts.append(f"{last_a_label}[bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]")
        final_audio_label = "[aout]"

    # v1.4.6++ A/V sync 兜底：在 filter_complex 末尾给 final_audio_label 追加
    # aresample=async —— filter_complex 映射后的标签上不能用 `-af` 输出选项，
    # 必须把 aresample 作为 filter 节点。补齐 acrossfade / amix 输出可能留下的
    # PTS 间隙（每镜次 50-100ms × N 镜次 = 用户主诉的 60s drift 来源）。
    fc_parts.append(f"{final_audio_label}aresample=async=1000:first_pts=0[afinal]")
    final_audio_label = "[afinal]"

    # v1.5.1: 片尾让【画面比音频多撑 END_HOLD 秒】（克隆末帧）→ 最后一句台词务必说完、
    # 画面再结束，彻底消除"视频播完音频还没播完/末尾对白被切"。用户实测：画面晚于音频
    # 结束时台词完整收尾；画面早于音频则末尾对白被截。这里给 0.5s 舒适余量。
    END_HOLD = 1.5
    fc_parts.append(f"{last_v_label}tpad=stop_mode=clone:stop_duration={END_HOLD + 0.5:.3f}[vfinal]")
    last_v_label = "[vfinal]"

    filter_complex = ";".join(fc_parts)

    # v1.4.6++ 慢路径也用 Windows-safe 编码档 + bitrate 上限，
    # 跟快路径保持一致的产出格式（避免"快路径能播慢路径不能播"的诡异情形）
    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", last_v_label,
        "-map", final_audio_label,
        "-c:v", "libx264",
        "-profile:v", "main", "-level", "4.0",
        "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-maxrate", "8M", "-bufsize", "16M",
        "-vsync", "cfr",
        "-video_track_timescale", "90000",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        # 画面已逐镜补齐到音频；再按对齐后的总时长安全封顶（同时给无限循环的 BGM 收尾）
        # 输出按【音频总长 + END_HOLD】封顶：音频在 video_out_total 结束，画面多撑 0.5s
        *(["-t", f"{video_out_total + END_HOLD:.3f}"] if video_out_total > 0.5 else []),
        "-movflags", "+faststart",
        str(out_path),
    ]
    # B2: 慢路径合并 / BGM 混音也走线程池（重编码 900s 上限）
    result = await run_blocking(subprocess.run, cmd, capture_output=True, timeout=900)
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace")[-800:]
        raise HTTPException(status_code=500, detail=f"ffmpeg 合并失败: {err}")

    # E2
    try:
        from services.task_history import append as _th_append
        _th_append(
            "merge",
            req.project_id,
            items=len(ordered_files), errors=0, status="ok",
            note=f"transition={req.transition}, bgm={'yes' if (use_bgm) else 'no'}",
        )
    except Exception as e:
        print(f"[merge] task_history append failed: {e}", flush=True)

    return MergeVideoResult(
        output_path=str(out_path),
        output_dir=str(proj_dir),
    )

# ── v1.4.2: 给已合并 / 已烧字幕的视频追加 BGM ───────────────────────────────
#
# 与 /merge-project-video 不同：这里不重新拼接、不重编码视频流（-c:v copy），
# 只在音轨上做"原音 + BGM"混合。源文件保留，输出新文件，避免一次失败把原片
# 也搞坏。
#
# 输入：project_id + source(=final_video|final_video_subbed) + 音乐库 track_id
#       + 混音参数（BGM 音量 dB / 原音量 dB / 淡入淡出时长 / 是否循环 BGM）
# 输出：<project>/video/<source>_with_bgm.mp4 + URL


def _ffprobe_duration_seconds(ffmpeg_path: str, file_path: Path) -> float:
    """从 ffmpeg 旁的 ffprobe 拿视频时长（秒），失败回 0。"""
    import shutil as _sh, subprocess as _sp, os as _os
    # ffprobe 跟 ffmpeg 一般同目录
    ffprobe = _sh.which("ffprobe") or str(Path(ffmpeg_path).parent / "ffprobe.exe")
    if not Path(ffprobe).is_file():
        ffprobe = "ffprobe"
    try:
        out = _sp.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
            capture_output=True, timeout=30,
        )
        if out.returncode == 0:
            return float((out.stdout or b"").decode().strip() or "0")
    except Exception:
        pass
    return 0.0


def _ffprobe_video_stream_seconds(ffmpeg_path: str, file_path: Path) -> float:
    """探测【视频流】时长（秒）。漫剧分镜里音频(TTS)常比画面长 ~30-130ms，
    合并若不封顶会让画面比声音早结束 → 末尾定格。用视频流时长给输出封顶。
    视频流没报 duration 时回退到容器时长。失败回 0。"""
    import shutil as _sh, subprocess as _sp
    ffprobe = _sh.which("ffprobe") or str(Path(ffmpeg_path).parent / "ffprobe.exe")
    if not Path(ffprobe).is_file():
        ffprobe = "ffprobe"
    try:
        out = _sp.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
            capture_output=True, timeout=30,
        )
        if out.returncode == 0:
            v = float((out.stdout or b"").decode().strip() or "0")
            if v > 0:
                return v
    except Exception:
        pass
    return _ffprobe_duration_seconds(ffmpeg_path, file_path)


class MixBgmRequest(BaseModel):
    project_id:         str
    source:             str = "final_video"   # 'final_video' | 'final_video_subbed'
    track_id:           int                    # 来自 /api/music/tracks
    bgm_volume_db:      float = -12.0
    original_volume_db: float = 0.0
    fade_in_ms:         int   = 800
    fade_out_ms:        int   = 1500
    loop_bgm:           bool  = True


class MixBgmResult(BaseModel):
    output_path:     str    # 绝对路径（Electron openPath 可直接用）
    output_filename: str    # 仅文件名（前端拼 video/<file> 用）
    duration_secs:   float
    bgm_track_id:    int


@router.post("/mix-bgm", response_model=MixBgmResult)
async def mix_bgm_into_video(req: MixBgmRequest):
    """在已完成的视频上叠加音乐库里的一首 BGM。视频流 -c:v copy 不重编码。"""
    cfg  = load_settings()
    vcfg = cfg.video_engine
    icfg = cfg.image_engine
    wdir = vcfg.workflow_dir or icfg.workflow_dir
    ffmpeg = _find_ffmpeg(vcfg.comfyui_input_dir, wdir)
    if not ffmpeg:
        raise HTTPException(500, detail="未找到 ffmpeg")

    # 源视频
    if req.source not in ("final_video", "final_video_subbed"):
        raise HTTPException(400, detail=f"非法 source: {req.source!r}")
    proj_dir = Path(cfg.projects_dir) / req.project_id
    vid_dir  = proj_dir / "video"
    source_path = vid_dir / f"{req.source}.mp4"
    if not source_path.is_file():
        raise HTTPException(404, detail=f"源视频不存在: {source_path.name}")

    # 音乐 track
    from services.db import get_global_music_conn, global_music_root
    conn = get_global_music_conn()
    row = conn.execute(
        "SELECT file_path, mime, name FROM tracks WHERE id = ?", (req.track_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail=f"音乐 track {req.track_id} 不存在")
    bgm_path = global_music_root() / row["file_path"]
    if not bgm_path.is_file():
        raise HTTPException(404, detail=f"音乐文件丢失: {bgm_path.name}")

    # 视频时长（用于淡出对齐）
    duration = _ffprobe_duration_seconds(ffmpeg, source_path)
    if duration <= 0:
        # 兜底：靠 ffmpeg -shortest 自动截断，淡出按 fade_out_ms 在视频结尾
        duration = 0.0

    # ── filter_complex 构造 ──
    fi = max(0, int(req.fade_in_ms))  / 1000.0
    fo = max(0, int(req.fade_out_ms)) / 1000.0
    # 淡出起始：max(0, duration - fo)
    fade_out_start = max(0.0, duration - fo) if duration > 0 else 0.0

    # BGM 链：volume → 可选 fade in → 可选 fade out
    bgm_filters = [f"volume={req.bgm_volume_db}dB"]
    if fi > 0:
        bgm_filters.append(f"afade=t=in:st=0:d={fi:.3f}")
    if fo > 0 and duration > 0:
        bgm_filters.append(f"afade=t=out:st={fade_out_start:.3f}:d={fo:.3f}")
    bgm_chain = ",".join(bgm_filters)

    # 原音轨：仅音量
    orig_chain = f"volume={req.original_volume_db}dB"

    filter_complex = (
        f"[1:a]{bgm_chain}[bgm];"
        f"[0:a]{orig_chain}[orig];"
        f"[orig][bgm]amix=inputs=2:duration=first:dropout_transition=0[mixed]"
    )

    # 输出
    out_path = vid_dir / f"{req.source}_with_bgm.mp4"

    # 构 ffmpeg 命令
    bgm_input_flags = []
    if req.loop_bgm:
        bgm_input_flags += ["-stream_loop", "-1"]
    cmd = [
        ffmpeg, "-y",
        "-i", str(source_path),
        *bgm_input_flags, "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[mixed]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        # v1.4.6: 把 moov atom 放文件开头，让 Windows Media Player / 系统播放器可播
        "-movflags", "+faststart",
        str(out_path),
    ]

    import subprocess as _sp
    from services.exec_pool import run_blocking
    result = await run_blocking(_sp.run, cmd, capture_output=True, timeout=600)
    if result.returncode != 0:
        err = (result.stderr or b"").decode(errors="replace")[-800:]
        raise HTTPException(500, detail=f"ffmpeg BGM 混音失败: {err}")

    # 任务历史
    try:
        from services.task_history import append as _th_append
        _th_append(
            "bgm-mix", req.project_id,
            items=1, errors=0, status="ok",
            note=(f"source={req.source}, track={req.track_id} ({row['name']}), "
                  f"bgm_db={req.bgm_volume_db}, fade={req.fade_in_ms}/{req.fade_out_ms}ms"),
        )
    except Exception as e:
        print(f"[bgm-mix] task_history append failed: {e}", flush=True)

    return MixBgmResult(
        output_path=str(out_path),
        output_filename=out_path.name,
        duration_secs=float(duration or 0.0),
        bgm_track_id=req.track_id,
    )


# ── v1.4.6: 图片放映视频（不走 LTX，给低 GPU 用户用）───────────────────────


class RenderSlideshowRequest(BaseModel):
    project_id:          str
    scene_order:         list[str]                  # scene_id 顺序
    width:               int = 1920
    height:              int = 1080
    fps:                 int = 25
    # 单镜内 2 张图之间的转场
    intra_transition:    str = "fade"
    intra_transition_ms: int = 800
    # 无音频镜次的默认时长
    default_no_audio_ms: int = 4000
    # v1.4.6: Ken Burns 画面动态
    # 可选：none / zoom_in / zoom_out / pan_left / pan_right / pan_up / pan_down
    motion_effect:       str = "none"
    # v1.4.6+: 并行渲染镜次数。0 = 按 CPU 自动选；1 = 顺序（兼容旧行为）；≥2 = 显式
    parallel:            int = 0


@router.post("/render-slideshow")
async def render_slideshow(req: RenderSlideshowRequest):
    """逐个分镜生成 mp4 子片（图片 + 音频，按音频时长，可加镜内转场）。
    每个 <project>/video/<scene_id>.mp4 与 LTX 输出同 schema —— 后续可直接
    复用 /merge-project-video 合并（含镜间转场 + BGM）。"""
    cfg  = load_settings()
    vcfg = cfg.video_engine
    icfg = cfg.image_engine
    wdir = vcfg.workflow_dir or icfg.workflow_dir
    ffmpeg = _find_ffmpeg(vcfg.comfyui_input_dir, wdir)
    if not ffmpeg:
        raise HTTPException(500, detail="未找到 ffmpeg")

    from pathlib import Path as _P
    proj_dir = _P(cfg.projects_dir) / req.project_id
    if not proj_dir.exists():
        raise HTTPException(404, detail="项目不存在")
    if not req.scene_order:
        raise HTTPException(400, detail="scene_order 不能为空")

    from services.slideshow_video import render_slideshow_project
    from services.exec_pool import run_blocking
    result = await run_blocking(
        render_slideshow_project,
        req.project_id,
        proj_dir=proj_dir,
        scene_order=req.scene_order,
        ffmpeg_path=ffmpeg,
        width=req.width, height=req.height, fps=req.fps,
        intra_transition=req.intra_transition,
        intra_transition_ms=req.intra_transition_ms,
        default_no_audio_ms=req.default_no_audio_ms,
        motion_effect=req.motion_effect,
        parallel=req.parallel,
    )

    # task_history
    try:
        from services.task_history import append as _th_append
        _th_append(
            "slideshow", req.project_id,
            items=len(req.scene_order),
            errors=len(result.get("errors") or []),
            status="ok" if result.get("ok") else "partial",
            note=f"transition={req.intra_transition}, dur={req.intra_transition_ms}ms",
        )
    except Exception as e:
        print(f"[slideshow] task_history append failed: {e}", flush=True)

    return result
