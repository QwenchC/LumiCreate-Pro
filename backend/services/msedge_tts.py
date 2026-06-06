"""Microsoft Edge TTS service via the edge-tts package (no API key required)."""
import asyncio
import base64
import shutil
import uuid

import edge_tts


def _mp3_to_wav(mp3: bytes) -> bytes:
    """Convert mp3 bytes to 24kHz mono PCM WAV via ffmpeg, so audio_engine.stitch-scene
    (which uses the stdlib wave module) can read it. Falls back to returning mp3 unchanged
    if ffmpeg is not available — caller should treat the result as "best effort"."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return mp3
    try:
        proc = __import__("subprocess").run(
            [ffmpeg, "-loglevel", "error", "-i", "pipe:0",
             "-ar", "24000", "-ac", "1", "-f", "wav", "pipe:1"],
            input=mp3, capture_output=True, timeout=60, check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except Exception:
        pass
    return mp3


async def synthesise(text: str, voice: str, rate: str = "+0%"):
    """
    Streaming generator with the same event schema as services.indextts.synthesise():
        {"event": "started",   "id": gen_id}
        {"event": "completed", "id": gen_id, "data": <b64 wav>, "mime": "audio/wav"}
        {"event": "error",     "id": gen_id, "message": str}

    Used by audio_engine.generate-stream / generate-batch-stream when
    settings.audio_engine.engine_type == "msedge". Output is WAV (transcoded from mp3
    via ffmpeg) so the existing stitch-scene endpoint and downstream LTX video pipeline
    work unchanged across all dialogue_modes.
    """
    gen_id = uuid.uuid4().hex[:8]
    yield {"event": "started", "id": gen_id}
    text = (text or "").strip()
    if not text:
        yield {"event": "error", "id": gen_id, "message": "empty text"}
        return
    try:
        mp3 = await synthesise_mp3(text, voice, rate)
    except Exception as e:
        yield {"event": "error", "id": gen_id, "message": f"edge-tts: {e}"}
        return
    # B2: 走共享 exec_pool（避免阻塞 event loop + 不挤占默认 executor 槽位）
    from services.exec_pool import run_blocking
    wav = await run_blocking(_mp3_to_wav, mp3)
    mime = "audio/wav" if wav is not mp3 else "audio/mpeg"
    yield {
        "event": "completed",
        "id":    gen_id,
        "data":  base64.b64encode(wav).decode(),
        "mime":  mime,
    }


async def _synthesise_mp3_once(text: str, voice: str, rate: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


async def synthesise_mp3(text: str, voice: str, rate: str = "+0%") -> bytes:
    """
    Generate speech using a Microsoft Edge neural voice.

    Args:
        text:  The text to speak.
        voice: Microsoft voice name, e.g. "zh-CN-XiaoxiaoNeural".
        rate:  Speed adjustment, e.g. "+0%", "-25%", "+50%".

    Returns:
        Raw MP3 bytes.
    """
    # 完全幂等 → 直接 retry 包一层
    from services.retry import async_retry
    return await async_retry(
        lambda: _synthesise_mp3_once(text, voice, rate),
        attempts=3, base_delay=0.5, label=f"msedge:{voice}",
    )
