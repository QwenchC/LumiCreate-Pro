"""
Audio engine router — supports IndexTTS-2.0 and GPT-SoVITS.

Endpoints:
  GET  /test                  — connectivity check
  GET  /voice-refs            — list available voice reference files
  GET  /emotion-refs          — list available emotion reference files
  POST /generate-stream       — SSE: single dialogue
  POST /generate-batch-stream — SSE: batch dialogues
  POST /stitch-scene          — merge clips for one scene into a single WAV
"""

import asyncio
import base64
import io
import json
import os
import struct
import wave
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import load_settings

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ConnectionTestResult(BaseModel):
    success: bool
    message: str


class SingleGenerateRequest(BaseModel):
    text: str
    voice_ref:   Optional[str] = None
    emo_ref:     Optional[str] = None
    emo_weight:  float = 0.8
    lang:        str = "zh"
    speaker:     Optional[str] = None
    speed:       float = 1.0
    scene_id:    str = ""
    dialogue_id: str = ""
    slot_index:  int = 0


class BatchDialogue(BaseModel):
    scene_id:    str
    dialogue_id: str
    text:        str
    voice_ref:   Optional[str] = None
    emo_ref:     Optional[str] = None
    emo_weight:  float = 0.8
    lang:        str = "zh"
    speaker:     Optional[str] = None


class BatchGenerateRequest(BaseModel):
    gen_count: int = 3
    speed:     float = 1.0
    dialogues: list[BatchDialogue]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _resolve_ref(path: Optional[str], ref_dir: str) -> Optional[str]:
    if not path:
        return None
    if os.path.isabs(path):
        return path if os.path.exists(path) else None
    if ref_dir:
        candidate = os.path.join(ref_dir, path)
        return candidate if os.path.exists(candidate) else None
    return None


def _list_audio_files(folder: str) -> list[str]:
    if not folder or not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder) if f.lower().endswith((".wav", ".mp3")))


# ── Connectivity ───────────────────────────────────────────────────────────────

@router.get("/test", response_model=ConnectionTestResult)
async def test_connection():
    cfg = load_settings().audio_engine
    if cfg.engine_type == "manual":
        return ConnectionTestResult(success=True, message="手动导入模式，无需连接")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.get(f"{cfg.api_url}/")
        name = "IndexTTS-2.0" if cfg.engine_type == "indextts" else "GPT-SoVITS"
        return ConnectionTestResult(success=True, message=f"{name} 连接成功")
    except Exception as e:
        return ConnectionTestResult(success=False, message=str(e))


@router.get("/voice-refs", response_model=list[str])
async def get_voice_refs():
    return _list_audio_files(load_settings().audio_engine.voice_ref_dir)


@router.get("/emotion-refs", response_model=list[str])
async def get_emotion_refs():
    return _list_audio_files(load_settings().audio_engine.emotion_ref_dir)


# ── Single SSE ─────────────────────────────────────────────────────────────────

@router.post("/generate-stream")
async def generate_single_stream(req: SingleGenerateRequest):
    cfg  = load_settings().audio_engine
    meta = {"scene_id": req.scene_id, "dialogue_id": req.dialogue_id, "slot_index": req.slot_index}

    async def stream():
        if cfg.engine_type == "indextts":
            from services.indextts import synthesise
            voice_path = (
                _resolve_ref(req.voice_ref, cfg.voice_ref_dir)
                or _resolve_ref(cfg.default_voice_ref, cfg.voice_ref_dir)
            )
            if not voice_path:
                yield _sse({**meta, "event": "error",
                            "message": "未配置音色参考音频，请在设置中指定 voice_ref_dir"})
                yield "data: [DONE]\n\n"
                return
            emo_path = _resolve_ref(req.emo_ref, cfg.emotion_ref_dir)
            async for event in synthesise(cfg, req.text, voice_path, emo_path, req.emo_weight):
                yield _sse({**event, **meta})

        elif cfg.engine_type == "gptsovits":
            from services.gptsovits import synthesise
            async for event in synthesise(
                cfg, req.text, req.lang, req.speaker,
                req.voice_ref, None, req.lang, speed=req.speed
            ):
                yield _sse({**event, **meta})

        else:
            yield _sse({**meta, "event": "error", "message": "manual 模式不支持自动生成"})

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Batch SSE ──────────────────────────────────────────────────────────────────

@router.post("/generate-batch-stream")
async def generate_batch_stream(req: BatchGenerateRequest):
    cfg         = load_settings().audio_engine
    gen_count   = max(1, min(req.gen_count, 10))
    total_tasks = len(req.dialogues) * gen_count
    queue:   asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()
    done_count = 0

    async def run_one(dlg: BatchDialogue, slot: int):
        nonlocal done_count
        meta = {"scene_id": dlg.scene_id, "dialogue_id": dlg.dialogue_id, "slot_index": slot}

        if cfg.engine_type == "indextts":
            from services.indextts import synthesise
            voice_path = (
                _resolve_ref(dlg.voice_ref, cfg.voice_ref_dir)
                or _resolve_ref(cfg.default_voice_ref, cfg.voice_ref_dir)
            )
            if not voice_path:
                await queue.put({**meta, "event": "error", "message": "未配置音色参考音频"})
            else:
                emo_path = _resolve_ref(dlg.emo_ref, cfg.emotion_ref_dir)
                async for event in synthesise(cfg, dlg.text, voice_path, emo_path, dlg.emo_weight):
                    await queue.put({**event, **meta})

        elif cfg.engine_type == "gptsovits":
            from services.gptsovits import synthesise
            async for event in synthesise(
                cfg, dlg.text, dlg.lang, dlg.speaker, dlg.voice_ref, None, speed=req.speed
            ):
                await queue.put({**event, **meta})

        else:
            await queue.put({**meta, "event": "error", "message": "manual 模式不支持批量生成"})

        done_count += 1
        if done_count >= total_tasks:
            finished.set()

    async def producer():
        await asyncio.gather(
            *[run_one(d, s) for d in req.dialogues for s in range(gen_count)],
            return_exceptions=True
        )
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


# ── Stitch ─────────────────────────────────────────────────────────────────────

class StitchClip(BaseModel):
    data: str           # base64 WAV
    pre_silence_ms:  int = 0
    post_silence_ms: int = 0


class StitchRequest(BaseModel):
    clips: list[StitchClip]


def _make_silence(n_channels: int, sampwidth: int, framerate: int, duration_ms: int) -> bytes:
    if duration_ms <= 0:
        return b""
    n_frames = int(framerate * duration_ms / 1000)
    return b"\x00" * (n_frames * n_channels * sampwidth)


def _stitch_wavs(clips: list[StitchClip]) -> bytes:
    segments: list[bytes] = []
    params = None

    for clip in clips:
        raw = base64.b64decode(clip.data)
        with wave.open(io.BytesIO(raw)) as wf:
            p = wf.getparams()
            pcm = wf.readframes(wf.getnframes())
        if params is None:
            params = p
        nc, sw, fr = params.nchannels, params.sampwidth, params.framerate
        segments.append(_make_silence(nc, sw, fr, clip.pre_silence_ms) + pcm + _make_silence(nc, sw, fr, clip.post_silence_ms))

    if not segments or params is None:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(24000)
            out.writeframes(_make_silence(1, 2, 24000, 100))
        return buf.getvalue()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(b"".join(segments))
    return buf.getvalue()


@router.post("/stitch-scene")
async def stitch_scene(req: StitchRequest):
    """Merge clips for one scene into a single WAV (with pre/post silence)."""
    if not req.clips:
        return {"data": "", "duration_ms": 0}
    loop = asyncio.get_event_loop()
    wav_bytes = await loop.run_in_executor(None, _stitch_wavs, req.clips)
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        duration_ms = int(wf.getnframes() / wf.getframerate() * 1000)
    return {"data": base64.b64encode(wav_bytes).decode(), "duration_ms": duration_ms}
