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
    # Microsoft Edge TTS overrides (used when engine_type == "msedge"):
    # 前端按角色填好后传过来；为空则用 settings.audio_engine.msedge_voice/rate
    msedge_voice: Optional[str] = None
    msedge_rate:  Optional[str] = None


class BatchDialogue(BaseModel):
    scene_id:    str
    dialogue_id: str
    text:        str
    voice_ref:   Optional[str] = None
    emo_ref:     Optional[str] = None
    emo_weight:  float = 0.8
    lang:        str = "zh"
    speaker:     Optional[str] = None
    # Microsoft Edge TTS per-dialogue override（按角色音色 / 双音色朗读时使用）
    msedge_voice: Optional[str] = None
    msedge_rate:  Optional[str] = None


class BatchGenerateRequest(BaseModel):
    gen_count: int = 3
    speed:     float = 1.0
    dialogues: list[BatchDialogue]
    # A1: 让后端持久化失败镜次（last_run_errors.json），前端可一键重试
    project_id: str = ""


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
    """C2: 走统一 adapter，路由 engine_type 的分支逻辑收敛进 adapter factory。"""
    from services.engine_adapter import make_audio_adapter
    adapter = make_audio_adapter()
    result = await adapter.test()
    return ConnectionTestResult(success=result.success, message=result.message)


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

        elif cfg.engine_type == "msedge":
            from services.msedge_tts import synthesise as msedge_synthesise
            voice = req.msedge_voice or cfg.msedge_voice
            rate  = req.msedge_rate  or cfg.msedge_rate
            async for event in msedge_synthesise(req.text, voice, rate):
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
    # A1: 失败镜次（按 dialogue_id 聚合）
    scene_errors: dict[str, str] = {}

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

        elif cfg.engine_type == "msedge":
            from services.msedge_tts import synthesise as msedge_synthesise
            voice = dlg.msedge_voice or cfg.msedge_voice
            rate  = dlg.msedge_rate  or cfg.msedge_rate
            async for event in msedge_synthesise(dlg.text, voice, rate):
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

    # E2
    from datetime import datetime as _dt, timezone as _tz
    started_at = _dt.now(_tz.utc).isoformat()
    started_ms = int(__import__("time").time() * 1000)

    async def stream():
        asyncio.create_task(producer())
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.1)
                # A1: 顺手收集错误（按 scene_id:dialogue_id 聚合）
                if item.get("event") == "error":
                    key = f"{item.get('scene_id','?')}:{item.get('dialogue_id','?')}"
                    scene_errors[key] = str(item.get("message","unknown error"))[:500]
                yield _sse(item)
            except asyncio.TimeoutError:
                if finished.is_set() and queue.empty():
                    break
        # A1: 落盘失败镜次
        if req.project_id:
            try:
                from routers.projects import write_last_run_errors
                write_last_run_errors(req.project_id, "audio", scene_errors)
            except Exception as e:
                print(f"[audio-batch] write_last_run_errors failed: {e}", flush=True)
        # E2
        try:
            from services.task_history import append as _th_append
            ended_at = _dt.now(_tz.utc).isoformat()
            ended_ms = int(__import__("time").time() * 1000)
            _th_append(
                "audio",
                req.project_id or "(no-project)",
                started_at=started_at, ended_at=ended_at,
                duration_ms=ended_ms - started_ms,
                items=total_tasks, errors=len(scene_errors),
                note=f"engine={cfg.engine_type}, dialogues={len(req.dialogues)}, gen={gen_count}",
            )
        except Exception as e:
            print(f"[audio-batch] task_history append failed: {e}", flush=True)
        yield _sse({"event": "batch_done", "total": total_tasks, "errors": scene_errors})
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
    from services.exec_pool import run_blocking
    wav_bytes = await run_blocking(_stitch_wavs, req.clips)
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        duration_ms = int(wf.getnframes() / wf.getframerate() * 1000)
    return {"data": base64.b64encode(wav_bytes).decode(), "duration_ms": duration_ms}


# ── Microsoft Edge TTS ─────────────────────────────────────────────────────────

class MsTtsRequest(BaseModel):
    text:  str
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate:  str = "+0%"   # e.g. "-25%", "+0%", "+50%"
    # 可选：MP3（直读模式，前端 <audio> 直接播）或 WAV（双音色朗读需要拼接，必须 WAV）
    format: str = "mp3"  # "mp3" | "wav"


@router.post("/ms-tts")
async def ms_tts(req: MsTtsRequest):
    """Generate a single TTS clip with Microsoft Edge neural voices.
    Returns base64 MP3 by default; pass format="wav" for stitch-scene compatible WAV."""
    try:
        from services.msedge_tts import synthesise_mp3, _mp3_to_wav
        mp3_bytes = await synthesise_mp3(req.text.strip(), req.voice, req.rate)
        if (req.format or "mp3").lower() == "wav":
            from services.exec_pool import run_blocking
            wav_bytes = await run_blocking(_mp3_to_wav, mp3_bytes)
            # 若 ffmpeg 不存在 _mp3_to_wav 会原样返回 mp3 —— 这种情况下
            # 报错给前端，避免后续 stitch 失败。
            if wav_bytes is mp3_bytes:
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail="ffmpeg not found, cannot transcode to wav")
            # 用 wave 算实际时长
            with wave.open(io.BytesIO(wav_bytes)) as wf:
                duration_ms = int(wf.getnframes() / wf.getframerate() * 1000)
            return {"data": base64.b64encode(wav_bytes).decode(),
                    "duration_ms": duration_ms, "format": "wav"}
        b64 = base64.b64encode(mp3_bytes).decode()
        # Rough estimate: Chinese neural TTS ~3.5 chars/sec
        duration_ms = max(1000, int(len(req.text) / 3.5 * 1000))
        return {"data": b64, "duration_ms": duration_ms, "format": "mp3"}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# 内置可选音色清单（与前端 SettingsView / CharactersTab / AudioTab 一致）
MSEDGE_BUILTIN_VOICES = [
    "zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural",
    "zh-CN-XiaohanNeural",  "zh-CN-XiaomengNeural", "zh-CN-XiaomoNeural",
    "zh-CN-XiaoqiuNeural",  "zh-CN-XiaoruiNeural",  "zh-CN-XiaoxuanNeural",
    "zh-CN-YunxiNeural",    "zh-CN-YunjianNeural",  "zh-CN-YunyangNeural",
    "zh-CN-YunfengNeural",  "zh-CN-YunhaoNeural",   "zh-CN-YunxiaNeural",
]


class TestAllRequest(BaseModel):
    voices: Optional[list[str]] = None     # 不传 = 跑全部内置
    text:   str = "测试"
    save:   bool = True                    # 跑完写入 settings.audio_engine.msedge_available_voices


@router.post("/ms-tts/test-all")
async def ms_tts_test_all(req: TestAllRequest):
    """逐一测试 Microsoft Edge neural voices；返回 {voice: ok/err}，
    并将通过的 voice 列表写入 settings.audio_engine.msedge_available_voices。"""
    from services.msedge_tts import synthesise_mp3
    voices = req.voices or MSEDGE_BUILTIN_VOICES
    sem = asyncio.Semaphore(4)   # 并发 4，避免 edge-tts 公网被限速

    async def probe(v: str):
        async with sem:
            try:
                # 短文本 + 默认 rate，最小代价探活
                mp3 = await synthesise_mp3(req.text or "测试", v, "+0%")
                return v, {"ok": len(mp3) > 0, "size": len(mp3), "error": ""}
            except Exception as e:
                return v, {"ok": False, "size": 0, "error": str(e)[:200]}

    results = dict(await asyncio.gather(*(probe(v) for v in voices)))
    available = [v for v, r in results.items() if r["ok"]]

    if req.save:
        from config import load_settings, SETTINGS_PATH
        import json
        s = load_settings()
        # 仅更新通过名单；若用户曾跑过部分音色，本次未测试的保留
        prev = set(s.audio_engine.msedge_available_voices or [])
        tested = set(voices)
        new_available = (prev - tested) | set(available)
        s.audio_engine.msedge_available_voices = sorted(new_available)
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(s.model_dump_json(indent=2), encoding="utf-8")

    return {
        "tested":    len(voices),
        "passed":    len(available),
        "results":   results,        # {voice: {ok, size, error}}
        "available": available,
    }
