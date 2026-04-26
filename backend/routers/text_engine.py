"""Text (LLM) engine router — connection test, streaming generation, scene generation."""
import json
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import load_settings
from services.llm import stream_chat
from services.prompts import (
    LENGTH_DESC,
    MANUSCRIPT_SYSTEM,
    MANUSCRIPT_USER_TEMPLATE,
    SCENES_SYSTEM,
    SCENES_USER_TEMPLATE,
)

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    models: list[str] = []


class ManuscriptConfig(BaseModel):
    length: str = "medium"
    audience: str = ""
    style: str = ""
    theme: str = ""


class GenerateManuscriptRequest(BaseModel):
    config: ManuscriptConfig
    existing_content: str = ""


class GenerateScenesRequest(BaseModel):
    manuscript: str


# ── Connection test ────────────────────────────────────────────────────────────

@router.get("/test", response_model=ConnectionTestResult)
async def test_connection():
    cfg = load_settings().text_engine
    try:
        if cfg.engine_type == "ollama":
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{cfg.base_url}/api/tags")
                r.raise_for_status()
                models = [m["name"] for m in r.json().get("models", [])]
                return ConnectionTestResult(success=True, message="Ollama 连接成功", models=models)
        elif cfg.engine_type == "lmstudio":
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{cfg.base_url}/v1/models")
                r.raise_for_status()
                models = [m["id"] for m in r.json().get("data", [])]
                return ConnectionTestResult(success=True, message="LM Studio 连接成功", models=models)
        else:
            headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{cfg.base_url}/v1/models", headers=headers)
                r.raise_for_status()
                models = [m["id"] for m in r.json().get("data", [])]
                return ConnectionTestResult(success=True, message="API 连接成功", models=models)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"引擎返回错误: {e.response.status_code}")
    except Exception as e:
        return ConnectionTestResult(success=False, message=str(e))


# ── Manuscript generation (streaming SSE) ─────────────────────────────────────

@router.post("/generate-manuscript")
async def generate_manuscript(req: GenerateManuscriptRequest):
    cfg = load_settings().text_engine
    length_desc = LENGTH_DESC.get(req.config.length, LENGTH_DESC["medium"])
    existing_hint = (
        f"\n【已有文案参考（请在此基础上扩展完善）】\n{req.existing_content}\n"
        if req.existing_content.strip() else ""
    )
    user_msg = MANUSCRIPT_USER_TEMPLATE.format(
        length_desc=length_desc,
        audience=req.config.audience or "普通观众",
        style=req.config.style or "通用",
        theme=req.config.theme or "（未指定，请自由发挥）",
        existing_hint=existing_hint,
    )

    async def sse_stream():
        try:
            async for chunk in stream_chat(cfg, MANUSCRIPT_SYSTEM, user_msg):
                payload = json.dumps({"text": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Scene generation (structured JSON) ────────────────────────────────────────

@router.post("/generate-scenes")
async def generate_scenes(req: GenerateScenesRequest):
    if not req.manuscript.strip():
        raise HTTPException(status_code=400, detail="文案内容不能为空")
    cfg = load_settings().text_engine
    user_msg = SCENES_USER_TEMPLATE.format(manuscript=req.manuscript)
    full_text = ""
    async for chunk in stream_chat(cfg, SCENES_SYSTEM, user_msg):
        full_text += chunk

    scenes_raw = _extract_json_array(full_text)
    if scenes_raw is None:
        raise HTTPException(status_code=502, detail=f"LLM 未返回有效 JSON:\n{full_text[:400]}")

    result = []
    for i, s in enumerate(scenes_raw):
        result.append({
            "id": f"scene_{i + 1:03d}",
            "index": s.get("index", i + 1),
            "description": s.get("description", ""),
            "duration_estimate": float(s.get("duration_estimate", 8.0)),
            "start_frame_prompt": s.get("start_frame_prompt", ""),
            "end_frame_prompt": s.get("end_frame_prompt", ""),
            "dialogues": s.get("dialogues", []),
        })
    return {"scenes": result, "total": len(result)}


def _extract_json_array(text: str) -> Optional[list]:
    text = re.sub(r"```(?:json)?\n?", "", text).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    return None

