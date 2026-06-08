"""ACE-Step v1.5 music/song generation via ComfyUI.

Workflow node IDs that are patched per generation:
  99  (PrimitiveNode "Song Duration")    widgets_values[0] = int duration secs
  102 (PrimitiveNode "seed")              widgets_values[0] = int seed
  94  (TextEncodeAceStepAudio1.5)         widgets_values[0..8] = tags/lyrics/seed/bpm/duration/timesig/lang/keyscale
  3   (KSampler)                          widgets_values[0] = int seed (sync with above)
  98  (EmptyAceStep1.5LatentAudio)        widgets_values[0] = duration secs
  107 (SaveAudioMP3)                      widgets_values[0] = filename prefix

Critical: ComfyUI's "randomize" widget mode is **client-side** — when submitting
via /prompt API it always uses the literal seed. So we ALWAYS inject a fresh
random seed if the caller didn't pass one explicitly, else regeneration produces
the exact same audio.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import json
import random
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

import httpx

try:
    import websockets
except ImportError:
    websockets = None   # type: ignore


# 节点 ID → 字段映射（不在 workflow_meta 里因为这类工作流目前只有这一个）
NODE_DURATION_PRIMITIVE     = 99
NODE_SEED_PRIMITIVE         = 102
NODE_TEXT_ENCODE            = 94
NODE_KSAMPLER               = 3
NODE_EMPTY_LATENT_AUDIO     = 98
NODE_SAVE_AUDIO             = 107

# TextEncodeAceStepAudio1.5 的 widgets_values 索引
_TE_TAGS         = 0
_TE_LYRICS       = 1
_TE_SEED         = 2
_TE_BPM          = 4
_TE_DURATION     = 5
_TE_TIMESIG      = 6
_TE_LANGUAGE     = 7
_TE_KEYSCALE     = 8


def patch_workflow(
    workflow: dict, *,
    duration_seconds: int,
    bpm: int,
    time_signature: str,
    language: str,
    key_scale: str,
    tags: str,
    lyrics: str,
    seed: int,
    filename_prefix: str = "lumi_music",
) -> dict:
    wf = copy.deepcopy(workflow)

    by_id_widget: dict[int, dict[int, object]] = {
        NODE_DURATION_PRIMITIVE: {0: int(duration_seconds)},
        NODE_SEED_PRIMITIVE:     {0: int(seed)},
        NODE_KSAMPLER:           {0: int(seed)},
        NODE_EMPTY_LATENT_AUDIO: {0: int(duration_seconds)},
        NODE_TEXT_ENCODE: {
            _TE_TAGS:     str(tags or ""),
            _TE_LYRICS:   str(lyrics or ""),
            _TE_SEED:     int(seed),
            _TE_BPM:      int(bpm),
            _TE_DURATION: float(duration_seconds),
            _TE_TIMESIG:  str(time_signature or "4"),
            _TE_LANGUAGE: str(language or "zh"),
            _TE_KEYSCALE: str(key_scale or "C major"),
        },
        NODE_SAVE_AUDIO: {0: f"audio/{filename_prefix}"},
    }

    for node in wf.get("nodes") or []:
        nid = node.get("id")
        if nid not in by_id_widget:
            continue
        wv = node.get("widgets_values")
        if isinstance(wv, list):
            for idx, val in by_id_widget[nid].items():
                while len(wv) <= idx:
                    wv.append("")
                wv[idx] = val
    return wf


async def generate_music(
    comfyui_url: str,
    workflow: dict,
    *,
    duration_seconds: int,
    bpm: int = 120,
    time_signature: str = "4",
    language: str = "zh",
    key_scale: str = "C major",
    tags: str = "",
    lyrics: str = "",
    seed: Optional[int] = None,
    track_id: str = "",
) -> AsyncGenerator[dict, None]:
    """Submit ACE-Step audio job, stream progress, return MP3 bytes (base64).

    seed=None ⇒ inject a fresh random seed; pass an int to reproduce a track.

    Yields:
      {"event": "queued",    "prompt_id": str, "seed": int}
      {"event": "progress",  "value": int, "max": int}
      {"event": "completed", "audio": str (b64 mp3), "filename": str}
      {"event": "error",     "message": str}
    """
    # 必须先确定 seed —— 即使用户没显式传入，ComfyUI 的 randomize 是客户端逻辑，
    # 经 /prompt API 走会用 literal seed，不刷新就会重复出同一首
    if seed is None:
        seed = random.randint(0, 2**63 - 1)

    patched_lg = patch_workflow(
        workflow,
        duration_seconds=duration_seconds,
        bpm=bpm,
        time_signature=time_signature,
        language=language,
        key_scale=key_scale,
        tags=tags,
        lyrics=lyrics,
        seed=seed,
        filename_prefix=f"lumi_music_{track_id or seed}",
    )

    # 转 API 格式
    try:
        from services.comfyui import _litegraph_to_api
        api_workflow = _litegraph_to_api(patched_lg)
    except Exception as e:
        yield {"event": "error", "message": f"工作流转换失败: {e}"}
        return

    client_id = str(uuid.uuid4())

    # 提交任务
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(
                f"{comfyui_url}/prompt",
                json={"prompt": api_workflow, "client_id": client_id},
            )
            if r.status_code >= 400:
                detail = ""
                try:
                    j = r.json()
                    err = j.get("error") or {}
                    parts = [f"ComfyUI {r.status_code}: {err.get('message') or err.get('type')}"]
                    for nid, ne in (j.get("node_errors") or {}).items():
                        cls = (ne or {}).get("class_type", "?")
                        for e in (ne or {}).get("errors") or []:
                            parts.append(f"  • 节点 {nid} ({cls}) {e.get('type','?')}: {e.get('message','')}")
                    detail = "\n".join(parts)
                except Exception:
                    detail = f"ComfyUI {r.status_code}: {r.text[:500]}"
                yield {"event": "error", "message": f"提交任务失败:\n{detail}"}
                return
            prompt_id = r.json()["prompt_id"]
    except Exception as e:
        yield {"event": "error", "message": f"提交任务失败: {e}"}
        return

    yield {"event": "queued", "prompt_id": prompt_id, "seed": seed}

    if websockets is None:
        yield {"event": "error", "message": "websockets 包未安装"}
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
                    yield {"event": "progress",
                           "value": data.get("value", 0),
                           "max":   data.get("max", 1)}
                elif mtype == "executing":
                    if data.get("node") is None and data.get("prompt_id") == prompt_id:
                        audio = await _fetch_audio(comfyui_url, prompt_id)
                        if audio:
                            yield {
                                "event":    "completed",
                                "audio":    audio["data"],   # b64 mp3
                                "filename": audio["filename"],
                                "mime":     audio["mime"],
                                "seed":     seed,
                            }
                        else:
                            yield {"event": "error", "message": "未找到生成的音频文件"}
                        return
                elif mtype == "execution_error":
                    if data.get("prompt_id") == prompt_id:
                        yield {"event": "error",
                               "message": data.get("exception_message", "ComfyUI 执行错误")}
                        return
    except Exception as e:
        yield {"event": "error", "message": f"WebSocket 错误: {e}"}


async def _fetch_audio(comfyui_url: str, prompt_id: str) -> Optional[dict]:
    """Download the result MP3 from ComfyUI history."""
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.get(f"{comfyui_url}/history/{prompt_id}")
            r.raise_for_status()
            history = r.json()
        except Exception:
            return None
        outputs = history.get(prompt_id, {}).get("outputs", {})
        # SaveAudioMP3 节点输出在 outputs[node_id]['audio'] 列表里
        for nid, out in outputs.items():
            for audio_info in (out.get("audio") or []):
                filename  = audio_info.get("filename", "lumi_music.mp3")
                subfolder = audio_info.get("subfolder", "")
                ftype     = audio_info.get("type", "output")
                try:
                    ar = await client.get(
                        f"{comfyui_url}/view",
                        params={"filename": filename, "subfolder": subfolder, "type": ftype},
                    )
                    ar.raise_for_status()
                    return {
                        "data":     base64.b64encode(ar.content).decode(),
                        "filename": filename,
                        "mime":     "audio/mpeg",
                    }
                except Exception:
                    continue
    return None
