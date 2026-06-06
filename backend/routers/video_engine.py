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


# D2: 视频工作流前置检查
@router.get("/precheck")
async def precheck_video_workflow_endpoint(workflow_name: str):
    from services.comfyui_precheck import precheck_video_workflow
    cfg = load_settings().video_engine
    result = await precheck_video_workflow(cfg.comfyui_url, workflow_name)
    return {"ok": result.ok, "issues": result.issues, "info": result.info}


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

    # C1: 读取同名 .meta.json（如果存在），让节点 ID 可配置
    workflow_meta = None
    if wdir:
        from services.workflow_meta import load_meta
        from pathlib import Path as _P
        wf_path = _P(wdir) / f"{req.workflow_name}.json"
        if wf_path.exists():
            workflow_meta = load_meta(wf_path, type_="video")

    width, height = _parse_resolution(req.resolution)
    total = len(req.scenes)

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
        from services.ltx2video import generate_video

        for idx, scene in enumerate(req.scenes):
            if not scene.start_image_b64:
                _record_err(scene.scene_id, "缺少首帧图片")
                yield _sse({"event": "scene_error", "scene_id": scene.scene_id,
                            "scene_index": scene.scene_index,
                            "message": "缺少首帧图片"})
                continue
            if not scene.end_image_b64:
                _record_err(scene.scene_id, "缺少末帧图片")
                yield _sse({"event": "scene_error", "scene_id": scene.scene_id,
                            "scene_index": scene.scene_index,
                            "message": "缺少末帧图片"})
                continue
            if not scene.audio_b64:
                _record_err(scene.scene_id, "缺少场景合并音频")
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

            gen_kwargs = dict(
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
                async for event in generate_video(**gen_kwargs):
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

    # ─── 快路径：无过渡 & 无 BGM → concat demuxer + copy（最快） ───
    if not use_xfade and not use_bgm:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            for p in ordered_files:
                f.write(f"file '{str(p).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
            concat_list = f.name
        try:
            cmd = [
                ffmpeg, "-y",
                "-f", "concat", "-safe", "0", "-i", concat_list,
                "-c", "copy",
                str(out_path),
            ]
            # B2: 走线程池，避免阻塞 event loop（最长 300s）
            from services.exec_pool import run_blocking
            result = await run_blocking(subprocess.run, cmd, capture_output=True, timeout=300)
            if result.returncode != 0:
                err = result.stderr.decode(errors="replace")[-500:]
                raise HTTPException(status_code=500, detail=f"ffmpeg 合并失败: {err}")
        finally:
            Path(concat_list).unlink(missing_ok=True)
        return MergeVideoResult(output_path=str(out_path), output_dir=str(proj_dir))

    # ─── 慢路径：xfade 镜间过渡 / BGM 混音 ───
    # 需要重新编码（codec copy 不能配合 filter_complex）
    inputs: list[str] = []
    for p in ordered_files:
        inputs += ["-i", str(p)]
    if use_bgm:
        # -stream_loop -1 必须出现在它对应的 -i 之前
        inputs += ["-stream_loop", "-1", "-i", str(bgm_file)]

    # 用 ffprobe 测每镜时长，xfade 偏移需要累计时长
    from services.exec_pool import run_blocking
    durations: list[float] = []
    for p in ordered_files:
        try:
            r = await run_blocking(
                subprocess.run,
                [ffmpeg.replace("ffmpeg", "ffprobe"), "-v", "error",
                 "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(p)],
                capture_output=True, text=True, timeout=10,
            )
            durations.append(float(r.stdout.strip() or "0") or 4.0)
        except Exception:
            durations.append(4.0)

    fc_parts: list[str] = []
    last_v_label = "[0:v]"
    last_a_label = "[0:a]"
    td = max(0.05, req.transition_duration_ms / 1000.0)
    if use_xfade:
        cur_offset = 0.0
        for i in range(len(ordered_files) - 1):
            cur_offset += durations[i] - td
            v_out = f"[v{i+1}]"
            a_out = f"[a{i+1}]"
            fc_parts.append(
                f"{last_v_label}[{i+1}:v]xfade=transition={transition}:duration={td}:offset={cur_offset:.3f}{v_out}"
            )
            # 音频也跟着 crossfade，保持衔接平顺
            fc_parts.append(
                f"{last_a_label}[{i+1}:a]acrossfade=d={td}{a_out}"
            )
            last_v_label = v_out
            last_a_label = a_out
    else:
        # 无过渡但仍走 filter_complex（因为有 BGM）；用 concat filter
        n = len(ordered_files)
        v_chain = "".join(f"[{i}:v]" for i in range(n))
        a_chain = "".join(f"[{i}:a]" for i in range(n))
        fc_parts.append(f"{v_chain}concat=n={n}:v=1:a=0[vcat]")
        fc_parts.append(f"{a_chain}concat=n={n}:v=0:a=1[acat]")
        last_v_label = "[vcat]"
        last_a_label = "[acat]"

    final_audio_label = last_a_label
    if use_bgm:
        bgm_input_idx = len(ordered_files)   # BGM 是最后一个 -i
        gain = req.bgm_volume_db
        fi  = max(0, req.bgm_fade_in_ms)  / 1000.0
        fo  = max(0, req.bgm_fade_out_ms) / 1000.0
        total_dur = sum(durations) - td * max(0, len(ordered_files) - 1) if use_xfade else sum(durations)
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

    filter_complex = ";".join(fc_parts)

    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", last_v_label,
        "-map", final_audio_label,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
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