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


class SceneVideoRequest(BaseModel):
    scene_id:        str
    scene_index:     int
    start_image_b64: str = ""
    end_image_b64:   str = ""
    audio_b64:       str = ""
    duration_ms:     int = 4000
    positive_prompt: str = ""


class VideoGenerateRequest(BaseModel):
    workflow_name: str
    resolution:    str = "720x1280"
    fps:           float = 25.0
    scenes:        list[SceneVideoRequest]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


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
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{cfg.comfyui_url}/system_stats")
            r.raise_for_status()
        return ConnectionTestResult(success=True, message="ComfyUI (Video) 连接成功")
    except Exception as e:
        return ConnectionTestResult(success=False, message=str(e))


@router.get("/workflows", response_model=list[str])
async def get_video_workflows():
    cfg  = load_settings()
    vcfg = cfg.video_engine
    icfg = cfg.image_engine

    class _Cfg:
        def __init__(self, url, wd):
            self.comfyui_url  = url
            self.workflow_dir = wd

    for wdir in filter(None, [vcfg.workflow_dir, icfg.workflow_dir]):
        p = Path(wdir)
        if p.is_dir():
            names = sorted(f.stem for f in p.glob("*.json"))
            if names:
                return names

    try:
        return await list_workflows(_Cfg(vcfg.comfyui_url, ""))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Video generation SSE ───────────────────────────────────────────────────────

@router.post("/generate-stream")
async def generate_video_stream(req: VideoGenerateRequest):
    cfg  = load_settings()
    vcfg = cfg.video_engine
    icfg = cfg.image_engine
    wdir = vcfg.workflow_dir or icfg.workflow_dir

    class _Cfg:
        def __init__(self, url, wd):
            self.comfyui_url  = url
            self.workflow_dir = wd

    workflow = await get_workflow_json(_Cfg(vcfg.comfyui_url, wdir), req.workflow_name)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"工作流 '{req.workflow_name}' 未找到")

    width, height = _parse_resolution(req.resolution)
    total = len(req.scenes)

    async def stream():
        from services.ltx2video import generate_video

        for idx, scene in enumerate(req.scenes):
            if not scene.start_image_b64:
                yield _sse({"event": "scene_error", "scene_id": scene.scene_id,
                            "scene_index": scene.scene_index,
                            "message": "缺少首帧图片"})
                continue
            if not scene.end_image_b64:
                yield _sse({"event": "scene_error", "scene_id": scene.scene_id,
                            "scene_index": scene.scene_index,
                            "message": "缺少末帧图片"})
                continue
            if not scene.audio_b64:
                yield _sse({"event": "scene_error", "scene_id": scene.scene_id,
                            "scene_index": scene.scene_index,
                            "message": "缺少场景合并音频"})
                continue

            yield _sse({
                "event":       "scene_start",
                "scene_id":    scene.scene_id,
                "scene_index": scene.scene_index,
                "current":     idx + 1,
                "total":       total,
            })

            async for event in generate_video(
                comfyui_url        = vcfg.comfyui_url,
                workflow           = workflow,
                first_frame_b64    = scene.start_image_b64,
                last_frame_b64     = scene.end_image_b64,
                audio_b64          = scene.audio_b64,
                width              = width,
                height             = height,
                fps                = req.fps,
                duration_ms        = scene.duration_ms,
                positive_prompt    = scene.positive_prompt,
                scene_id           = scene.scene_id,
                comfyui_input_dir  = vcfg.comfyui_input_dir,
                workflow_dir       = wdir or "",
            ):
                ev = event.get("event")
                if ev == "completed":
                    yield _sse({**event, "event": "scene_done", "scene_index": scene.scene_index})
                elif ev == "error":
                    yield _sse({**event, "event": "scene_error", "scene_index": scene.scene_index})
                else:
                    yield _sse(event)

        yield _sse({"event": "batch_done", "total": total})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Merge project video ────────────────────────────────────────────────────────

class MergeVideoRequest(BaseModel):
    project_id: str
    scene_order: list[str]   # scene_id list in display order


class MergeVideoResult(BaseModel):
    output_path: str
    output_dir: str


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

    # Build ffmpeg concat list
    video_dir = proj_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    out_path = video_dir / "final_video.mp4"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in ordered_files:
            f.write(f"file '{str(p).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
        concat_list = f.name

    try:
        cmd = [
            ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            err = result.stderr.decode(errors="replace")[-500:]
            raise HTTPException(status_code=500, detail=f"ffmpeg 合并失败: {err}")
    finally:
        Path(concat_list).unlink(missing_ok=True)

    return MergeVideoResult(
        output_path=str(out_path),
        output_dir=str(proj_dir),
    )