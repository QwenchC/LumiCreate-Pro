"""Unified LLM streaming service for all engine types."""
import json
from typing import AsyncGenerator

import httpx

from config import TextEngineConfig


async def stream_chat(
    cfg: TextEngineConfig,
    system_prompt: str,
    user_message: str,
) -> AsyncGenerator[str, None]:
    """
    Yield text chunks from the configured LLM engine.
    Handles: Ollama, LM Studio (OpenAI-compat), DeepSeek / other OpenAI-compat.
    """
    if cfg.engine_type == "ollama":
        async for chunk in _stream_ollama(cfg, system_prompt, user_message):
            yield chunk
    else:
        # LM Studio and all OpenAI-compatible endpoints use the same format
        async for chunk in _stream_openai_compat(cfg, system_prompt, user_message):
            yield chunk


# ── Ollama ─────────────────────────────────────────────────────────────────────

async def _stream_ollama(cfg: TextEngineConfig, system: str, user: str) -> AsyncGenerator[str, None]:
    payload = {
        "model": cfg.model or "llama3",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "options": {"temperature": cfg.temperature, "top_p": cfg.top_p},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", f"{cfg.base_url}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    text = data.get("message", {}).get("content", "")
                    if text:
                        yield text
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue


# ── OpenAI-compatible (LM Studio / DeepSeek / etc.) ───────────────────────────

async def _stream_openai_compat(cfg: TextEngineConfig, system: str, user: str) -> AsyncGenerator[str, None]:
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    payload = {
        "model": cfg.model or "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "temperature": cfg.temperature,
        "top_p": cfg.top_p,
    }

    # DeepSeek uses its own base URL; LM Studio uses the configured one
    base = cfg.base_url.rstrip("/")
    url = f"{base}/v1/chat/completions"

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:].strip()
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                    delta = data["choices"][0]["delta"]
                    text = delta.get("content", "")
                    if text:
                        yield text
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
