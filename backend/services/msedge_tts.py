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
    loop = asyncio.get_event_loop()
    wav = await loop.run_in_executor(None, _mp3_to_wav, mp3)
    mime = "audio/wav" if wav is not mp3 else "audio/mpeg"
    yield {
        "event": "completed",
        "id":    gen_id,
        "data":  base64.b64encode(wav).decode(),
        "mime":  mime,
    }


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
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)
