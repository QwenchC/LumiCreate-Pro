"""
Subtitle engine router.

Endpoints:
  GET  /status/{project_id}   — check final_video.mp4 and SRT existence
  GET  /script/{project_id}   — auto-extract subtitle script from scenes
  POST /preprocess-text       — convert manuscript text to one-line-per-sentence format
  POST /generate-srt          — SSE: run full subtitle generation pipeline
  POST /embed                 — burn SRT subtitles into final_video.mp4
"""

import asyncio
import json
import threading
from pathlib import Path
from queue import Empty, Queue

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import load_settings
from services.ltx2video import _find_ffmpeg
from services.subtitle import (
    generate_srt as _generate_srt,
    embed_subtitles,
    preprocess_text,
    write_srt,
)

router = APIRouter()

_SSE = lambda obj: f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"  # noqa: E731


def _proj_dir(project_id: str) -> Path:
    return Path(load_settings().projects_dir) / project_id


def _video_dir(project_id: str) -> Path:
    return _proj_dir(project_id) / "video"


def _find_ffprobe(ffmpeg_path: str) -> str:
    """Derive ffprobe path from ffmpeg path."""
    p = Path(ffmpeg_path)
    ffprobe = p.parent / p.name.replace('ffmpeg', 'ffprobe')
    if ffprobe.exists():
        return str(ffprobe)
    # Fallback: assume ffprobe is on PATH
    return 'ffprobe'


# ── Schemas ────────────────────────────────────────────────────────────────────

class SubtitleStatus(BaseModel):
    has_final_video: bool
    has_fixed_cfr: bool
    has_srt: bool
    has_embedded: bool
    srt_path: str = ""
    embedded_path: str = ""


class PreprocessRequest(BaseModel):
    text: str


class GenerateSrtRequest(BaseModel):
    project_id: str
    lines: list[str]           # one subtitle entry per element
    fps: int = 24              # 24 | 25 | 30
    manual_advance: float = 0.0
    model_name: str = "base"


class EmbedRequest(BaseModel):
    project_id: str
    font_name: str = '等线 Bold'
    font_size: int = 18
    # D2: 扩展样式
    primary_colour:  str = "#FFFFFF"   # 文字主色（ASS BGR / RGB 都接受，前端给 #RRGGBB）
    outline_colour:  str = "#000000"   # 描边颜色
    outline_width:   float = 2.0       # 描边粗细（像素）
    shadow_depth:    float = 0.0       # 阴影深度
    margin_v:        int = 30          # 距底/顶的垂直边距（像素）
    position:        str = "bottom"    # "bottom" | "top" | "center"
    bold:            bool = True       # ASS Bold
    italic:          bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status/{project_id}", response_model=SubtitleStatus)
async def subtitle_status(project_id: str):
    vdir = _video_dir(project_id)
    final   = vdir / "final_video.mp4"
    fixed   = vdir / "fixed_cfr.mp4"
    srt     = vdir / "subtitles.srt"
    emb     = vdir / "final_video_subbed.mp4"
    return SubtitleStatus(
        has_final_video=final.exists(),
        has_fixed_cfr=fixed.exists(),
        has_srt=srt.exists(),
        has_embedded=emb.exists(),
        srt_path=str(srt) if srt.exists() else "",
        embedded_path=str(emb) if emb.exists() else "",
    )


@router.get("/script/{project_id}")
async def get_script(project_id: str):
    """Return subtitle script lines extracted from the project's scenes (dialogue / description)."""
    proj_dir = _proj_dir(project_id)
    scenes_path = proj_dir / "scenes.json"
    if not scenes_path.exists():
        return {"lines": []}

    data = json.loads(scenes_path.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    lines: list[str] = []
    for scene in scenes:
        # Prefer dialogue text; fall back to description
        dialogues = scene.get("dialogues") or []
        if dialogues:
            for d in dialogues:
                text = (d.get("text") or "").strip()
                if text:
                    lines.append(text)
        else:
            desc = (scene.get("description") or "").strip()
            if desc:
                lines.append(desc)

    return {"lines": lines, "count": len(lines)}


@router.post("/preprocess-text")
async def preprocess_text_endpoint(req: PreprocessRequest):
    result = preprocess_text(req.text)
    lines = [ln for ln in result.split('\n') if ln.strip()]
    return {"text": result, "lines": lines, "count": len(lines)}


@router.post("/generate-srt")
async def generate_srt_endpoint(req: GenerateSrtRequest):
    """SSE stream: normalize video → extract audio → align → write SRT."""
    cfg  = load_settings()
    vcfg = cfg.video_engine
    icfg = cfg.image_engine
    wdir = vcfg.workflow_dir or icfg.workflow_dir

    ffmpeg = _find_ffmpeg(vcfg.comfyui_input_dir, wdir)
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="未找到 ffmpeg，无法生成字幕")
    ffprobe = _find_ffprobe(ffmpeg)

    vdir = _video_dir(req.project_id)
    final_video = vdir / "final_video.mp4"
    if not final_video.exists():
        raise HTTPException(status_code=400, detail="final_video.mp4 不存在，请先合并视频")

    if not req.lines:
        raise HTTPException(status_code=400, detail="字幕文本为空")

    if req.fps not in (24, 25, 30):
        raise HTTPException(status_code=400, detail="fps 必须为 24、25 或 30")

    srt_path     = str(vdir / "subtitles.srt")
    fixed_cfr    = str(vdir / "fixed_cfr.mp4")

    q: Queue = Queue()

    def _run():
        try:
            for evt in _generate_srt(
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                video_path=str(final_video),
                srt_path=srt_path,
                lines=req.lines,
                fps=req.fps,
                manual_advance=req.manual_advance,
                model_name=req.model_name,
                fixed_cfr_path=fixed_cfr,
            ):
                q.put(evt)
        except Exception as e:
            q.put({'step': 'error', 'message': str(e)})
        finally:
            q.put(None)  # sentinel

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    async def stream():
        loop = asyncio.get_event_loop()
        while True:
            try:
                evt = await loop.run_in_executor(None, lambda: q.get(timeout=300))
            except Empty:
                yield _SSE({'step': 'error', 'message': '超时'})
                break
            if evt is None:
                yield "data: [DONE]\n\n"
                break
            yield _SSE(evt)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/embed")
async def embed_subtitles_endpoint(req: EmbedRequest):
    """Burn subtitles.srt into final_video.mp4 → final_video_subbed.mp4."""
    cfg  = load_settings()
    vcfg = cfg.video_engine
    icfg = cfg.image_engine
    wdir = vcfg.workflow_dir or icfg.workflow_dir

    ffmpeg = _find_ffmpeg(vcfg.comfyui_input_dir, wdir)
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="未找到 ffmpeg")

    vdir = _video_dir(req.project_id)
    srt_path    = vdir / "subtitles.srt"
    fixed_cfr   = vdir / "fixed_cfr.mp4"
    final_video = vdir / "final_video.mp4"
    output_path = vdir / "final_video_subbed.mp4"

    # Prefer fixed_cfr.mp4 (correct timebase) over original final_video.mp4
    source_video = fixed_cfr if fixed_cfr.exists() else final_video

    if not source_video.exists():
        raise HTTPException(status_code=400, detail="final_video.mp4 不存在")
    if not srt_path.exists():
        raise HTTPException(status_code=400, detail="subtitles.srt 不存在，请先生成字幕")

    q: Queue = Queue()

    # D2: 转 ASS force_style：FFmpeg subtitles filter 接受 force_style 串
    def _hex_to_ass_color(hex_str: str) -> str:
        """#RRGGBB → &HBBGGRR&  （ASS 是 BGR + 透明）"""
        h = (hex_str or "#FFFFFF").lstrip("#")
        if len(h) != 6:
            h = "FFFFFF"
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H00{b}{g}{r}".upper() + "&"

    alignment = {"bottom": 2, "center": 5, "top": 8}.get(req.position, 2)
    force_style_parts = [
        f"FontName={req.font_name}",
        f"FontSize={req.font_size}",
        f"PrimaryColour={_hex_to_ass_color(req.primary_colour)}",
        f"OutlineColour={_hex_to_ass_color(req.outline_colour)}",
        f"Outline={req.outline_width}",
        f"Shadow={req.shadow_depth}",
        f"Bold={1 if req.bold else 0}",
        f"Italic={1 if req.italic else 0}",
        f"Alignment={alignment}",
        f"MarginV={req.margin_v}",
        "BorderStyle=1",
    ]
    force_style = ",".join(force_style_parts)

    def _run():
        try:
            for evt in embed_subtitles(
                ffmpeg, str(source_video), str(srt_path), str(output_path),
                font_name=req.font_name,
                font_size=req.font_size,
                ffprobe=_find_ffprobe(ffmpeg),
                force_style=force_style,
            ):
                q.put(evt)
        except Exception as e:
            q.put({'step': 'error', 'message': str(e)})
        finally:
            q.put(None)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    async def stream():
        yield _SSE({'step': 'embedding', 'message': f'正在将字幕烧录到视频（字体：{req.font_name}）…', 'pct': 0})
        loop = asyncio.get_event_loop()
        while True:
            try:
                evt = await loop.run_in_executor(None, lambda: q.get(timeout=600))
            except Empty:
                yield _SSE({'step': 'error', 'message': '嵌入超时'})
                break
            if evt is None:
                yield "data: [DONE]\n\n"
                break
            yield _SSE(evt)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
