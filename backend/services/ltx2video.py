"""
LTX-2.3 first-frame-to-last-frame video generation via the flfa2i-lumicreate workflow.

Workflow node IDs that are patched per generation:
  45  (LoadImage FIRST FRAME)  widgets_values[0] = uploaded image filename
  47  (LoadImage LAST FRAME)   widgets_values[0] = uploaded image filename
  232 (LoadAudio)              widgets_values[0] = uploaded audio filename
  166 (INTConstant WIDTH)      widgets_values[0] = int video width
  167 (INTConstant HEIGHT)     widgets_values[0] = int video height
  169 (INTConstant LENGTH s)   widgets_values[0] = int duration in seconds
  164 (PrimitiveFloat FPS)     widgets_values[0] = float fps
  16  (CLIPTextEncode pos)     widgets_values[0] = str positive prompt
"""

import asyncio
import asyncio
import base64
import copy
import json
import math
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

import httpx

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore


# ── File upload helpers ────────────────────────────────────────────────────────

async def _upload_image(comfyui_url: str, png_bytes: bytes, filename: str) -> str:
    """Upload PNG bytes to ComfyUI /upload/image, return the server filename."""
    boundary = f"LumiCreateBoundary{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + png_bytes + f"\r\n--{boundary}--\r\n".encode()

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{comfyui_url}/upload/image",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        r.raise_for_status()
        data = r.json()
        return data.get("name") or filename


def _find_ffmpeg(comfyui_input_dir: str = "", workflow_dir: str = "") -> str:
    """Return the path to an ffmpeg executable, or '' if not found."""
    # 1. System PATH
    found = shutil.which("ffmpeg")
    if found:
        return found
    # 2. Look relative to ComfyUI root (common conda-packed layout: .ext/Library/bin/ffmpeg.exe)
    roots: list[Path] = []
    if comfyui_input_dir:
        roots.append(Path(comfyui_input_dir).parent)  # one level up from input/
    if workflow_dir:
        p = Path(workflow_dir)
        for _ in range(5):
            roots.append(p)
            if p.parent == p:
                break
            p = p.parent
    for root in roots:
        for rel in (".ext/Library/bin/ffmpeg.exe", "ffmpeg.exe", "bin/ffmpeg.exe"):
            candidate = root / rel
            if candidate.is_file():
                return str(candidate)
    return ""


def _resolve_input_dir(comfyui_input_dir: str, workflow_dir: str = "") -> str:
    """Return a valid ComfyUI input/ directory path, or '' if none found."""
    if comfyui_input_dir and Path(comfyui_input_dir).is_dir():
        return comfyui_input_dir
    # Try to auto-detect from workflow_dir:
    # workflow_dir is typically <comfyui_root>/user/default/workflows
    # Walk up until we find a sibling/parent 'input' directory.
    if workflow_dir:
        p = Path(workflow_dir)
        for _ in range(5):
            candidate = p / "input"
            if candidate.is_dir():
                return str(candidate)
            if p.parent == p:
                break
            p = p.parent
    return ""


async def _upload_audio(
    comfyui_url: str,
    wav_bytes: bytes,
    filename: str,
    comfyui_input_dir: str = "",
    workflow_dir: str = "",
) -> str:
    """
    Place WAV bytes where ComfyUI can find them.
    Prefers writing directly to ComfyUI input/ directory (avoids missing /upload/audio endpoint).
    Falls back to /upload/audio API if no local path is available.
    """
    input_dir = _resolve_input_dir(comfyui_input_dir, workflow_dir)
    if input_dir:
        dest = Path(input_dir) / filename
        await asyncio.to_thread(dest.write_bytes, wav_bytes)
        return filename

    # Fallback: try ComfyUI upload API (newer versions only)
    boundary = f"LumiCreateBoundary{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="audio"; filename="{filename}"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + wav_bytes + f"\r\n--{boundary}--\r\n".encode()

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{comfyui_url}/upload/audio",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        r.raise_for_status()
        data = r.json()
        return data.get("name") or filename


# ── Workflow patching ──────────────────────────────────────────────────────────

# Nodes to patch: {node_id(int): widget_index -> new_value}
_PATCH_MAP = {
    45:  {0: "first_frame"},   # placeholder key, filled in patch fn
    47:  {0: "last_frame"},
    232: {0: "audio"},
    166: {0: "width"},
    167: {0: "height"},
    169: {0: "duration_secs"},
    164: {0: "fps"},
    16:  {0: "positive_prompt"},
}


def patch_workflow(
    workflow: dict,
    first_frame_file: str,
    last_frame_file: str,
    audio_file: str,
    width: int,
    height: int,
    fps: float,
    duration_secs: int,
    positive_prompt: str,
) -> dict:
    """Return a deep copy of the workflow with the necessary node values patched."""
    wf = copy.deepcopy(workflow)
    values = {
        45:  {0: first_frame_file},
        47:  {0: last_frame_file},
        232: {0: audio_file},
        166: {0: width},
        167: {0: height},
        169: {0: duration_secs},
        164: {0: float(fps)},
        16:  {0: positive_prompt},
    }
    for node in wf.get("nodes", []):
        nid = node.get("id")
        if nid in values:
            wv = node.get("widgets_values")
            if isinstance(wv, list):
                for idx, val in values[nid].items():
                    if idx < len(wv):
                        wv[idx] = val
                    else:
                        wv.append(val)
            elif isinstance(wv, dict):
                node["widgets_values"] = wv  # leave as-is; not expected for patched nodes

        # Replace buggy VAELoaderKJ with standard VAELoader (same file, avoids AudioVAE.__init__ crash)
        if node.get("type") == "VAELoaderKJ":
            vae_name = (node.get("widgets_values") or [""])[0]
            node["type"] = "VAELoader"
            node["widgets_values"] = [vae_name]
            # Keep only the vae_name input, remove device/weight_dtype widget inputs
            new_inputs = []
            for inp in node.get("inputs", []):
                if inp.get("name") == "vae_name":
                    new_inputs.append(inp)
            node["inputs"] = new_inputs

    return wf


# ── LiteGraph → API conversion (minimal, delegated to comfyui service) ─────────

def _litegraph_to_api(workflow: dict) -> dict:
    """Re-use the converter from comfyui service."""
    from services.comfyui import _litegraph_to_api as _convert
    return _convert(workflow)


# ── Video generation ───────────────────────────────────────────────────────────

async def generate_video(
    comfyui_url: str,
    workflow: dict,
    first_frame_b64: str,
    last_frame_b64: str,
    audio_b64: str,
    width: int,
    height: int,
    fps: float,
    duration_ms: int,
    positive_prompt: str,
    scene_id: str = "",
    comfyui_input_dir: str = "",
    workflow_dir: str = "",
    replace_audio: bool = True,
) -> AsyncGenerator[dict, None]:
    """
    Upload assets, patch workflow, queue to ComfyUI, stream progress events.

    Yields:
      {"event": "uploading"}
      {"event": "queued",    "prompt_id": str}
      {"event": "progress",  "value": int, "max": int}
      {"event": "completed", "video": str (base64 mp4), "filename": str}
      {"event": "error",     "message": str}
    """
    yield {"event": "uploading", "scene_id": scene_id}

    # ── 1. Upload images & audio ─────────────────────────────────────────────
    try:
        first_png  = base64.b64decode(first_frame_b64)
        last_png   = base64.b64decode(last_frame_b64)
        audio_wav  = base64.b64decode(audio_b64)

        ff_name, lf_name, aud_name = await asyncio.gather(
            _upload_image(comfyui_url, first_png, f"lumi_ff_{scene_id}.png"),
            _upload_image(comfyui_url, last_png,  f"lumi_lf_{scene_id}.png"),
            _upload_audio(comfyui_url, audio_wav, f"lumi_aud_{scene_id}.wav",
                          comfyui_input_dir=comfyui_input_dir, workflow_dir=workflow_dir),
        )
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"文件上传失败: {e}"}
        return

    # ── 2. Patch & convert workflow ──────────────────────────────────────────
    duration_secs = max(1, math.ceil(duration_ms / 1000))
    patched_lg = patch_workflow(
        workflow, ff_name, lf_name, aud_name,
        width, height, fps, duration_secs, positive_prompt,
    )
    try:
        api_workflow = _litegraph_to_api(patched_lg)
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"工作流转换失败: {e}"}
        return

    # ── 3. Queue prompt ──────────────────────────────────────────────────────
    client_id = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(
                f"{comfyui_url}/prompt",
                json={"prompt": api_workflow, "client_id": client_id},
            )
            if r.status_code >= 400:
                try:
                    detail = r.json()
                    errmsg = detail.get("error", {}).get("message") or str(detail)
                except Exception:
                    errmsg = r.text[:500]
                yield {"event": "error", "scene_id": scene_id, "message": f"提交任务失败 {r.status_code}: {errmsg}"}
                return
            r.raise_for_status()
            prompt_id = r.json()["prompt_id"]
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"提交任务失败: {e}"}
        return

    yield {"event": "queued", "prompt_id": prompt_id, "scene_id": scene_id}

    # ── 4. WebSocket progress ────────────────────────────────────────────────
    if websockets is None:
        yield {"event": "error", "scene_id": scene_id, "message": "websockets 包未安装"}
        return

    ws_url = comfyui_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws?clientId={client_id}"

    try:
        async with websockets.connect(ws_url, ping_interval=20) as ws:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                mtype = msg.get("type")
                data  = msg.get("data", {})

                if mtype == "progress":
                    yield {
                        "event": "progress",
                        "value": data.get("value", 0),
                        "max":   data.get("max", 1),
                        "scene_id": scene_id,
                    }
                elif mtype == "executing":
                    if data.get("node") is None and data.get("prompt_id") == prompt_id:
                        # Done — fetch video output
                        video_data = await _fetch_video(comfyui_url, prompt_id)
                        if video_data:
                            video_bytes = base64.b64decode(video_data["data"])
                            # Replace AI-generated audio with the user's original audio
                            if replace_audio and audio_b64:
                                ffmpeg = _find_ffmpeg(comfyui_input_dir, workflow_dir)
                                if ffmpeg:
                                    audio_bytes = base64.b64decode(audio_b64)
                                    video_bytes = await _replace_audio_track(
                                        video_bytes, audio_bytes, ffmpeg
                                    )
                            yield {
                                "event":    "completed",
                                "scene_id": scene_id,
                                "video":    base64.b64encode(video_bytes).decode(),
                                "filename": video_data["filename"],
                                "mime":     "video/mp4",
                            }
                        else:
                            yield {"event": "error", "scene_id": scene_id, "message": "未找到输出视频文件"}
                        return
                elif mtype == "execution_error":
                    if data.get("prompt_id") == prompt_id:
                        yield {"event": "error", "scene_id": scene_id,
                               "message": data.get("exception_message", "ComfyUI 执行错误")}
                        return
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"WebSocket 错误: {e}"}


# ── Fetch video output ─────────────────────────────────────────────────────────

async def _replace_audio_track(
    video_bytes: bytes,
    audio_bytes: bytes,
    ffmpeg_path: str,
) -> bytes:
    """
    Use ffmpeg to replace the audio track of an MP4 with the provided WAV,
    trimmed to the video's duration. Returns original bytes on any error.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            vid_in  = tmp / "in.mp4"
            aud_in  = tmp / "in.wav"
            vid_out = tmp / "out.mp4"
            vid_in.write_bytes(video_bytes)
            aud_in.write_bytes(audio_bytes)
            cmd = [
                ffmpeg_path,
                "-y",
                "-i", str(vid_in),
                "-i", str(aud_in),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(vid_out),
            ]
            result = await asyncio.to_thread(
                subprocess.run, cmd,
                capture_output=True, timeout=120,
            )
            if result.returncode == 0 and vid_out.exists():
                return vid_out.read_bytes()
    except Exception:
        pass
    return video_bytes


async def _fetch_video(comfyui_url: str, prompt_id: str) -> Optional[dict]:
    """Download the first video file from the generation history."""
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.get(f"{comfyui_url}/history/{prompt_id}")
            r.raise_for_status()
            history = r.json()
        except Exception:
            return None

        outputs = history.get(prompt_id, {}).get("outputs", {})
        for node_id, node_out in outputs.items():
            # VHS_VideoCombine stores under "gifs" or "videos"
            for key in ("gifs", "videos", "images"):
                for item in node_out.get(key, []):
                    fname = item.get("filename", "")
                    if fname.lower().endswith((".mp4", ".webm", ".mov")):
                        subfolder = item.get("subfolder", "")
                        ftype     = item.get("type", "output")
                        try:
                            dl = await client.get(
                                f"{comfyui_url}/view",
                                params={"filename": fname, "subfolder": subfolder, "type": ftype},
                            )
                            dl.raise_for_status()
                            return {
                                "filename": fname,
                                "data": base64.b64encode(dl.content).decode(),
                            }
                        except Exception:
                            pass
    return None
