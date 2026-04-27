"""
IndexTTS-2.0 TTS service (Gradio API).

Endpoints used:
  POST /gradio_api/upload              — upload reference audio files
  POST /gradio_api/call/gen_single     — submit generation task
  GET  /gradio_api/call/gen_single/{id}— SSE poll for result

Two generation modes:
  "same"     — 与音色参考音频相同（emo_control_method="与音色参考音频相同"）
  "emotion"  — 使用情感参考音频（emo_control_method="使用情感参考音频"）
"""

import asyncio
import base64
import json
import os
import uuid
from typing import AsyncGenerator, Optional

import httpx

from config import AudioEngineConfig


# ── File upload ───────────────────────────────────────────────────────────────

async def _upload_file(client: httpx.AsyncClient, base_url: str, path: str) -> dict:
    """Upload a local audio file to Gradio, return a FileData dict."""
    filename = os.path.basename(path)
    mime = "audio/mpeg" if path.lower().endswith(".mp3") else "audio/wav"
    boundary = "LumiCreateBoundary"

    with open(path, "rb") as f:
        file_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

    r = await client.post(
        f"{base_url}/gradio_api/upload",
        content=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        timeout=30,
    )
    r.raise_for_status()
    server_path = r.json()[0]
    return {"path": server_path, "orig_name": filename, "meta": {"_type": "gradio.FileData"}}


# ── Default generation parameters ─────────────────────────────────────────────

_DEFAULT_GEN = [
    True,   # do_sample
    0.8,    # top_p
    30,     # top_k
    0.8,    # temperature
    0.0,    # length_penalty
    3,      # num_beams
    10.0,   # repetition_penalty
    1500,   # max_mel_tokens
]


# ── Core generation ───────────────────────────────────────────────────────────

async def synthesise(
    cfg: AudioEngineConfig,
    text: str,
    voice_ref_path: str,            # 音色参考音频（必填）
    emo_ref_path: Optional[str] = None,   # 情感参考音频（可选）
    emo_weight: float = 0.8,
) -> AsyncGenerator[dict, None]:
    """
    Yield SSE-style events:
      {"event": "started",   "id": str}
      {"event": "completed", "data": str (base64 wav)}
      {"event": "error",     "message": str}
    """
    gen_id = str(uuid.uuid4())
    yield {"event": "started", "id": gen_id}

    base_url = cfg.api_url.rstrip("/")
    use_emo  = bool(emo_ref_path and emo_ref_path.strip())

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # 1. Upload voice reference
            voice_fd = await _upload_file(client, base_url, voice_ref_path)

            # 2. Upload emotion reference if needed
            emo_fd = None
            if use_emo:
                emo_fd = await _upload_file(client, base_url, emo_ref_path)

            # 3. Build gen_single params
            emo_method = "使用情感参考音频" if use_emo else "与音色参考音频相同"
            params = [
                emo_method,   # emo_control_method
                voice_fd,     # prompt（音色参考）
                text,         # text
                emo_fd,       # emo_ref_path（None if not used）
                emo_weight,   # emo_weight
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # vec1..vec8
                "",           # emo_text
                False,        # emo_random
                120,          # max_text_tokens_per_sentence
                *_DEFAULT_GEN,
            ]

            # 4. Submit task
            r = await client.post(
                f"{base_url}/gradio_api/call/gen_single",
                json={"data": params},
                timeout=30,
            )
            r.raise_for_status()
            event_id = r.json()["event_id"]

            # 5. Poll SSE result
            async with client.stream(
                "GET",
                f"{base_url}/gradio_api/call/gen_single/{event_id}",
                timeout=120,
            ) as resp:
                resp.raise_for_status()
                async for raw_line in resp.aiter_lines():
                    if not raw_line.startswith("data:"):
                        continue
                    data = json.loads(raw_line[5:].strip())
                    if isinstance(data, list) and len(data) > 0:
                        item = data[0]
                        file_info = item.get("value") if isinstance(item, dict) and "value" in item else item
                        audio_url = file_info.get("url") or f"{base_url}/gradio_api/file={file_info['path']}"

                        # Download the wav file
                        dl = await client.get(audio_url, timeout=60)
                        dl.raise_for_status()
                        b64 = base64.b64encode(dl.content).decode()
                        yield {"event": "completed", "id": gen_id, "data": b64, "mime": "audio/wav"}
                        return

    except httpx.HTTPStatusError as e:
        yield {"event": "error", "id": gen_id, "message": f"IndexTTS HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        yield {"event": "error", "id": gen_id, "message": str(e)}
