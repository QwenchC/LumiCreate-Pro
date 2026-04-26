"""
GPT-SoVITS TTS service.

Handles:
- Querying available voice models from GPT-SoVITS API
- Synthesising audio and returning base64-encoded WAV
- SSE event stream for single and batch generation
"""

import asyncio
import base64
import uuid
from typing import AsyncGenerator, Optional

import httpx

from config import AudioEngineConfig


# ── Voice model / reference audio queries ─────────────────────────────────────

async def list_voice_models(cfg: AudioEngineConfig) -> list[str]:
    """Return available speaker/model names from the GPT-SoVITS server."""
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            # The Septy/GPT-SoVITS-v2 API exposes /speakers
            r = await client.get(f"{cfg.api_url}/speakers")
            if r.status_code == 200:
                data = r.json()
                # May be a list of strings or dicts
                if isinstance(data, list):
                    return [
                        item if isinstance(item, str) else item.get("name", str(item))
                        for item in data
                    ]
        except Exception:
            pass
    return []


# ── Single TTS generation ─────────────────────────────────────────────────────

async def synthesise(
    cfg: AudioEngineConfig,
    text: str,
    lang: str = "zh",
    speaker: Optional[str] = None,
    ref_audio_path: Optional[str] = None,
    prompt_text: Optional[str] = None,
    prompt_lang: str = "zh",
    top_k: int = 5,
    top_p: float = 1.0,
    temperature: float = 1.0,
    speed: float = 1.0,
) -> AsyncGenerator[dict, None]:
    """
    Call GPT-SoVITS /tts and yield SSE-style events:
      {"event": "started",   "id": str}
      {"event": "completed", "data": str (base64 wav)}
      {"event": "error",     "message": str}
    """
    gen_id = str(uuid.uuid4())
    yield {"event": "started", "id": gen_id}

    params: dict = {
        "text":      text,
        "text_lang": lang,
        "top_k":     top_k,
        "top_p":     top_p,
        "temperature": temperature,
        "speed_factor": speed,
        "streaming_mode": False,
    }
    if speaker:         params["character"] = speaker
    if ref_audio_path:  params["ref_audio_path"] = ref_audio_path
    if prompt_text:     params["prompt_text"] = prompt_text
    if prompt_lang:     params["prompt_lang"] = prompt_lang

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{cfg.api_url}/tts", json=params)
            r.raise_for_status()
            b64 = base64.b64encode(r.content).decode()
            yield {"event": "completed", "id": gen_id, "data": b64, "mime": "audio/wav"}
    except httpx.HTTPStatusError as e:
        yield {"event": "error", "id": gen_id, "message": f"TTS HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        yield {"event": "error", "id": gen_id, "message": str(e)}
