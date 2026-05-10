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
    DIALOGUE_MODE_DESC,
    MANUSCRIPT_SYSTEM,
    MANUSCRIPT_USER_TEMPLATE,
    SCENES_SYSTEM,
    SCENES_USER_TEMPLATE,
    CHARACTER_APPEARANCE_SYSTEM,
    CHARACTER_APPEARANCE_USER_TEMPLATE,
    SUGGEST_CHARS_SYSTEM,
    SUGGEST_CHARS_USER_TEMPLATE,
    CHARACTER_PROFILE_SYSTEM,
    CHARACTER_PROFILE_USER_TEMPLATE,
)

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    models: list[str] = []


class ManuscriptConfig(BaseModel):
    length:        str  = "medium"
    audience:      str  = ""
    style:         str  = ""
    tone:          str  = ""
    theme:         str  = ""
    worldview:     str  = ""
    characters:    list = []   # list of {name, role, traits}
    dialogue_mode: str  = "mixed"  # "narration" | "dialogue" | "mixed"


class GenerateManuscriptRequest(BaseModel):
    config: ManuscriptConfig
    existing_content: str = ""


class GenerateScenesRequest(BaseModel):
    manuscript:    str
    dialogue_mode: str  = "mixed"   # narration | dialogue | mixed | reading
    characters:    list = []         # [{name, role, traits}]


class GenerateFramePromptsRequest(BaseModel):
    description: str
    dialogues:   list = []   # [{character, text}]
    characters:  list = []   # project characters for style consistency


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
            base = cfg.base_url.rstrip("/")
            models_url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(models_url, headers=headers)
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
    import sys
    print(f"[generate-manuscript] engine={cfg.engine_type} base_url={cfg.base_url} model={cfg.model}", flush=True, file=sys.stderr)
    length_desc = LENGTH_DESC.get(req.config.length, LENGTH_DESC["medium"])
    dialogue_mode_desc = DIALOGUE_MODE_DESC.get(req.config.dialogue_mode, DIALOGUE_MODE_DESC["mixed"])

    # Build characters section
    chars = req.config.characters or []
    if chars:
        lines = []
        for c in chars:
            name   = c.get("name", "").strip()
            role   = c.get("role", "").strip()
            traits = c.get("traits", "").strip()
            if name:
                line = f"  - {name}"
                if role:   line += f"（{role}）"
                if traits: line += f"：{traits}"
                lines.append(line)
        characters_section = "【主要角色】\n" + "\n".join(lines) if lines else ""
    else:
        characters_section = ""

    existing_hint = (
        f"\n【已有文案参考（请在此基础上扩展完善）】\n{req.existing_content}\n"
        if req.existing_content.strip() else ""
    )
    user_msg = MANUSCRIPT_USER_TEMPLATE.format(
        length_desc=length_desc,
        audience=req.config.audience or "普通观众",
        style=req.config.style or "通用",
        tone=req.config.tone or "（未指定）",
        theme=req.config.theme or "（未指定，请自由发挥）",
        worldview=req.config.worldview or "（未指定）",
        characters_section=characters_section,
        dialogue_mode_desc=dialogue_mode_desc,
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

_READING_CPS      = 4.0   # chars per second (Chinese TTS)
_READING_MAX_SECS = 28.0  # keep under 30 s with a safety margin

def _make_reading_scene(index: int, text: str) -> dict:
    duration = min(round(len(text) / _READING_CPS + 0.5, 1), _READING_MAX_SECS)
    return {
        "id":                 f"scene_{index:03d}",
        "index":              index,
        "description":        text[:30] + ("…" if len(text) > 30 else ""),
        "duration_estimate":  duration,
        "start_frame_prompt": "",
        "end_frame_prompt":   "",
        "dialogues": [{
            "character":    "旁白",
            "text":         text,
            "emotion":      "平静",
            "pause_before": 0.0,
            "pause_after":  0.3,
        }],
        "audio_timeline": [{"type": "dialogue", "dialogue_index": 0}],
    }

def _split_reading_scenes(manuscript: str) -> list:
    max_chars = int(_READING_CPS * _READING_MAX_SECS)
    # split on sentence-ending punctuation but keep the delimiter
    sentences = re.split(r"(?<=[\u3002\uff01\uff1f\u2026\n])", manuscript.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    scenes, group, group_len = [], [], 0
    for sent in sentences:
        slen = len(sent)
        if group and group_len + slen > max_chars:
            scenes.append(_make_reading_scene(len(scenes) + 1, "".join(group)))
            group, group_len = [sent], slen
        else:
            group.append(sent)
            group_len += slen
    if group:
        scenes.append(_make_reading_scene(len(scenes) + 1, "".join(group)))
    return scenes


@router.post("/generate-scenes")
async def generate_scenes(req: GenerateScenesRequest):
    if not req.manuscript.strip():
        raise HTTPException(status_code=400, detail="文案内容不能为空")

    # ── reading mode: pure text split, no LLM ─────────────────────────────────
    if req.dialogue_mode == "reading":
        scenes = _split_reading_scenes(req.manuscript)
        return {"scenes": scenes, "total": len(scenes)}

    # ── LLM-based modes ───────────────────────────────────────────────────────
    cfg = load_settings().text_engine

    # Build characters hint
    chars = req.characters or []
    if chars:
        lines = []
        for c in chars:
            name   = c.get("name",   "").strip()
            role   = c.get("role",   "").strip()
            traits = c.get("traits", "").strip()
            if name:
                line = f"  - {name}"
                if role:   line += f"（{role}）"
                if traits: line += f"：{traits}"
                lines.append(line)
        characters_hint = "\n【主要角色参考】\n" + "\n".join(lines) + "\n" if lines else ""
    else:
        characters_hint = ""

    mode_desc = DIALOGUE_MODE_DESC.get(req.dialogue_mode, DIALOGUE_MODE_DESC["mixed"])
    dialogue_mode_hint = f"\n【对白模式】{mode_desc}\n"

    user_msg = SCENES_USER_TEMPLATE.format(
        manuscript=req.manuscript,
        characters_hint=characters_hint,
        dialogue_mode_hint=dialogue_mode_hint,
    )
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


# ── Frame prompt generation ────────────────────────────────────────────────────

_FRAME_PROMPT_SYSTEM = (
    "You are an expert AI image prompt engineer for video generation. "
    "Given a scene description and optional dialogue, write two concise English prompts: "
    "one for the START frame and one for the END frame of a short video clip. "
    "Each prompt should be vivid, specific, and suitable for a text-to-image model "
    "(Stable Diffusion / ComfyUI). "
    "CRITICAL: Do NOT include any art style, painting style, or rendering style tags "
    "(e.g. do NOT write 'anime style', 'watercolor', '3D render', 'photorealistic', "
    "'oil painting', 'sketch', 'cartoon', 'manga', 'illustration', etc.). "
    "Art style will be applied separately by the user. "
    "Focus only on scene content, character appearance, composition, lighting, and mood. "
    "Output ONLY a JSON object with keys "
    "\"start_frame_prompt\" and \"end_frame_prompt\". No extra text."
)

@router.post("/generate-frame-prompts")
async def generate_frame_prompts(req: GenerateFramePromptsRequest):
    dialogue_lines = "\n".join(
        f"  [{d.get('character','?')}]: {d.get('text','')}"
        for d in (req.dialogues or [])
    )

    # Build per-character appearance tags for consistency
    char_appearances = []
    char_styles = ""
    if req.characters:
        parts = []
        for c in req.characters:
            name = c.get("name", "").strip()
            if not name:
                continue
            role = c.get("role", "").strip()
            appearance = c.get("appearance", "").strip()
            traits = c.get("traits", "").strip()
            # Collect for the prompt header
            desc_parts = [name]
            if role:        desc_parts.append(f"({role})")
            if appearance:  char_appearances.append(f"{name}: {appearance}")
            elif traits:    char_appearances.append(f"{name}: {traits}")
            parts.append(" ".join(desc_parts))
        if parts:
            char_styles = "Characters in this series: " + ", ".join(parts) + ". "

    appearance_block = ""
    if char_appearances:
        appearance_block = (
            "Character visual descriptions (MUST be included in every frame prompt for consistency):\n"
            + "\n".join(f"  - {a}" for a in char_appearances)
            + "\n"
        )

    user_msg = (
        f"{char_styles}"
        f"{appearance_block}"
        f"Scene description (Chinese): {req.description}\n"
        + (f"Dialogues:\n{dialogue_lines}\n" if dialogue_lines.strip() else "")
        + "\nIMPORTANT: Each prompt MUST include the character appearance tags above verbatim so the characters look consistent across all frames.\n"
        + "Return JSON only."
    )

    cfg = load_settings().text_engine
    full_text = ""
    async for chunk in stream_chat(cfg, _FRAME_PROMPT_SYSTEM, user_msg):
        full_text += chunk

    # parse JSON from response
    cleaned = re.sub(r"```(?:json)?\n?", "", full_text).strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                obj = json.loads(m.group())
            except json.JSONDecodeError:
                obj = {}
        else:
            obj = {}

    return {
        "start_frame_prompt": obj.get("start_frame_prompt", ""),
        "end_frame_prompt":   obj.get("end_frame_prompt",   ""),
    }


# ── Character appearance prompt generation (streaming) ─────────────────────────

class GenerateCharacterAppearanceRequest(BaseModel):
    name:     str = ""
    role:     str = ""
    traits:   str = ""
    existing: str = ""   # existing appearance text the user may have written


class GenerateCharacterProfileRequest(BaseModel):
    name: str = ""
    manuscript: str = ""
    existing_role: str = ""
    existing_traits: str = ""


@router.post("/generate-character-appearance")
async def generate_character_appearance(req: GenerateCharacterAppearanceRequest):
    if not req.name.strip() and not req.traits.strip():
        raise HTTPException(status_code=400, detail="至少提供角色姓名或性格特征")

    existing_hint = ""
    if req.existing.strip():
        existing_hint = f"\n【现有描述（可参考并改进）】{req.existing.strip()}\n"

    user_msg = CHARACTER_APPEARANCE_USER_TEMPLATE.format(
        name=req.name or "（未命名）",
        role=req.role or "（未指定）",
        traits=req.traits or "（未指定）",
        existing_hint=existing_hint,
    )

    cfg = load_settings().text_engine

    async def sse_stream():
        try:
            async for chunk in stream_chat(cfg, CHARACTER_APPEARANCE_SYSTEM, user_msg):
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/generate-character-profile")
async def generate_character_profile(req: GenerateCharacterProfileRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="角色名不能为空")
    if not req.manuscript.strip():
        raise HTTPException(status_code=400, detail="文案内容不能为空")

    user_msg = CHARACTER_PROFILE_USER_TEMPLATE.format(
        name=req.name.strip(),
        manuscript=req.manuscript.strip(),
        existing_role=req.existing_role.strip() or "（无）",
        existing_traits=req.existing_traits.strip() or "（无）",
    )

    cfg = load_settings().text_engine
    full_text = ""
    async for chunk in stream_chat(cfg, CHARACTER_PROFILE_SYSTEM, user_msg):
        full_text += chunk

    cleaned = re.sub(r"```(?:json)?\n?", "", full_text).strip()
    obj = {}
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                obj = json.loads(m.group())
            except json.JSONDecodeError:
                obj = {}

    return {
        "role": str(obj.get("role", "")).strip(),
        "traits": str(obj.get("traits", "")).strip(),
    }



# ── Suggest characters for a scene ────────────────────────────────────────────

class SuggestSceneCharactersRequest(BaseModel):
    description: str = ""
    dialogues:   list = []
    all_names:   list = []


@router.post("/suggest-scene-characters")
async def suggest_scene_characters(req: SuggestSceneCharactersRequest):
    if not req.all_names:
        return {"characters": []}

    dialogue_lines = "\n".join(
        f"  [{d.get('character','?')}]: {d.get('text','')}"
        for d in (req.dialogues or [])
    ) or "（无台词）"

    user_msg = SUGGEST_CHARS_USER_TEMPLATE.format(
        description=req.description or "（无描述）",
        dialogues=dialogue_lines,
        all_names="、".join(req.all_names),
    )

    cfg = load_settings().text_engine
    full_text = ""
    async for chunk in stream_chat(cfg, SUGGEST_CHARS_SYSTEM, user_msg):
        full_text += chunk

    cleaned = re.sub(r"```(?:json)?\n?", "", full_text).strip()
    valid = set(req.all_names)
    try:
        names = json.loads(cleaned)
        if isinstance(names, list):
            return {"characters": [n for n in names if n in valid]}
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[\s\S]*?\]", cleaned)
    if m:
        try:
            names = json.loads(m.group())
            if isinstance(names, list):
                return {"characters": [n for n in names if n in valid]}
        except json.JSONDecodeError:
            pass
    return {"characters": []}
