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
    FRAME_PROMPT_SYSTEM,
    FRAME_PROMPT_USER_TEMPLATE,
    I2I_PROMPT_SYSTEM,
    I2I_PROMPT_USER_TEMPLATE,
    VIDEO_PROMPT_SYSTEM,
    VIDEO_PROMPT_USER_TEMPLATE,
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
    # AI 有机分镜：reading 模式默认走纯文本切（快速稳定）；
    # 设为 True 时即使 reading 模式也调 LLM 做语义分镜（适合一键全流程"宁多不少"）
    force_llm:     bool = False


class GenerateFramePromptsRequest(BaseModel):
    description: str
    dialogues:   list = []   # [{character, text}]
    characters:  list = []   # project characters for style consistency
    manuscript:  str  = ""   # full manuscript text for narrative context
    scene_index: int  = 0
    total_scenes: int = 0


# 轮 6: i2i 提示词
class GenerateI2IPromptsRequest(BaseModel):
    description:  str
    dialogues:    list = []
    characters:   list = []      # 选中的角色（含 appearance）
    refs:         list = []      # [{kind, ...}] 同 image-engine refs
    workflow_kind: str = "i2i_single"   # i2i_single | i2i_double
    project_id:   str  = ""      # 解析 portrait/element 需要
    manuscript:   str  = ""
    scene_index:  int  = 0
    total_scenes: int  = 0


class GenerateVideoPromptRequest(BaseModel):
    description:        str  = ""
    dialogues:          list = []   # [{character, text, emotion}]
    characters:         list = []   # [{name, role, appearance, traits}]
    start_frame_prompt: str  = ""
    end_frame_prompt:   str  = ""
    manuscript:         str  = ""
    scene_index:        int  = 0
    total_scenes:       int  = 0


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
        "description":        text,
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

    # ── reading mode: pure text split, no LLM (除非 force_llm=True) ───────────
    if req.dialogue_mode == "reading" and not req.force_llm:
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

    # 出场角色启发式：扫描 description + dialogues.text，命中已知名字即填入 _scene_characters
    known_names = [c.get("name", "") for c in chars if c.get("name")]
    def _detect_chars(text: str) -> list[str]:
        if not known_names:
            return []
        hits = []
        for n in known_names:
            if n and n in text:
                hits.append(n)
        return hits

    result = []
    for i, s in enumerate(scenes_raw):
        desc = s.get("description", "")
        dlgs = s.get("dialogues", []) or []
        scan_text = desc + " " + " ".join((d.get("text") or "") + " " + (d.get("character") or "") for d in dlgs)
        result.append({
            "id": f"scene_{i + 1:03d}",
            "index": s.get("index", i + 1),
            "description": desc,
            "duration_estimate": float(s.get("duration_estimate", 8.0)),
            "start_frame_prompt": s.get("start_frame_prompt", ""),
            "end_frame_prompt": s.get("end_frame_prompt", ""),
            "dialogues": dlgs,
            "_scene_characters": _detect_chars(scan_text),
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

@router.post("/generate-frame-prompts")
async def generate_frame_prompts(req: GenerateFramePromptsRequest):
    dialogue_lines = ""
    if req.dialogues:
        line_parts = []
        for d in req.dialogues:
            text = (d.get("text") or "").strip()
            if not text:
                continue
            speaker = (d.get("character") or "").strip()
            # 漫剧/朗读模式：speaker 为空 → 旁白；标注 Narration 让 LLM 知道是叙述而非台词
            if speaker:
                line_parts.append(f"  [{speaker}]: {text}")
            else:
                line_parts.append(f"  [Narration]: {text}")
        if line_parts:
            dialogue_lines = "Dialogues / narration (read in narrative order — earlier lines correspond to the start frame, later lines to the end frame):\n" + "\n".join(line_parts) + "\n"

    # Build per-character appearance block — STRICT: each appearance stays with its owner
    char_parts = []
    if req.characters:
        for c in req.characters:
            name = c.get("name", "").strip()
            if not name:
                continue
            role       = c.get("role",       "").strip()
            appearance = c.get("appearance", "").strip()
            traits     = c.get("traits",     "").strip()
            visual = appearance or traits or ""
            line = f"  - {name}"
            if role:   line += f" ({role})"
            if visual: line += f": {visual}"
            char_parts.append(line)

    char_block = ""
    if char_parts:
        char_block = (
            "Characters in this scene (ONLY these characters exist in this frame — do not add any others):\n"
            + "\n".join(char_parts)
            + "\n\n"
        )

    user_msg = FRAME_PROMPT_USER_TEMPLATE.format(
        char_block=char_block,
        description=req.description,
        dialogue_lines=dialogue_lines,
    )

    cfg = load_settings().text_engine
    full_text = ""
    async for chunk in stream_chat(cfg, FRAME_PROMPT_SYSTEM, user_msg):
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


# ── 轮 6: i2i 提示词（图生图工作流专用）──────────────────────────────────────


def _describe_ref(ref: dict, *, project_id: str = "") -> dict:
    """根据 ref 标识查到一段描述，供 LLM 理解参考图内容。

    返回 {role, label, description}：
      - role:        'character' | 'element' | 'unknown'
      - label:       人类可读标签（角色名/元素名/路径）
      - description: 用于 prompt 的英文描述（appearance / element name / 文件名）
    """
    kind = (ref or {}).get("kind") or ""
    if kind == "portrait":
        char_name = ref.get("char_name") or ""
        pid = ref.get("project_id") or project_id
        appearance = ""
        if pid and char_name:
            try:
                from routers.projects import _project_dir
                cj_path = _project_dir(pid) / "characters.json"
                if cj_path.exists():
                    cj = json.loads(cj_path.read_text(encoding="utf-8-sig"))
                    for c in cj.get("characters") or []:
                        if (c.get("name") or "").strip() == char_name:
                            appearance = (c.get("appearance") or "").strip()
                            break
            except Exception:
                pass
        return {
            "role": "character",
            "label": char_name or "character",
            "description": appearance or f"character portrait of {char_name}",
        }
    if kind == "element":
        scope = ref.get("scope") or "global"
        eid = ref.get("element_id")
        name = ""
        meta_prompt = ""
        try:
            from services.elements_repo import get_element
            elem = get_element(scope, int(eid)) if eid is not None else None
            if elem:
                name = elem.get("name") or ""
                meta = elem.get("source_meta") or {}
                meta_prompt = (meta.get("prompt") if isinstance(meta, dict) else "") or ""
        except Exception:
            pass
        desc = meta_prompt or f"reference element '{name}'" if name else "reference image"
        return {
            "role": "element",
            "label": name or "element",
            "description": desc,
        }
    return {"role": "unknown", "label": "reference", "description": "reference image"}


@router.post("/generate-img2img-prompt")
async def generate_img2img_prompt(req: GenerateI2IPromptsRequest):
    """根据参考图 + 角色 + 分镜信息生成 i2i 编辑指令。"""
    if req.workflow_kind not in ("i2i_single", "i2i_double"):
        raise HTTPException(status_code=400,
                            detail=f"workflow_kind 必须是 i2i_single 或 i2i_double，得到: {req.workflow_kind!r}")
    ref_count = 1 if req.workflow_kind == "i2i_single" else 2

    # 1) refs 描述块
    ref_descs = [_describe_ref(r, project_id=req.project_id) for r in (req.refs or [])]
    ref_lines = []
    for i, d in enumerate(ref_descs[:ref_count]):
        role_label = "character portrait" if d["role"] == "character" else \
                     ("scene/element" if d["role"] == "element" else "reference")
        ref_lines.append(f"  Image {i + 1} ({role_label}, {d['label']}): {d['description']}")
    ref_block = ""
    if ref_lines:
        ref_block = "Reference images (passed to the model alongside this prompt):\n" + \
                    "\n".join(ref_lines) + "\n\n"

    # 2) 角色块（沿用 t2i 的写法）
    char_parts = []
    for c in (req.characters or []):
        name = (c.get("name") or "").strip()
        if not name:
            continue
        role = (c.get("role") or "").strip()
        appearance = (c.get("appearance") or "").strip()
        traits = (c.get("traits") or "").strip()
        visual = appearance or traits or ""
        line = f"  - {name}"
        if role:   line += f" ({role})"
        if visual: line += f": {visual}"
        char_parts.append(line)
    char_block = ""
    if char_parts:
        char_block = (
            "Characters in this scene (only these may appear):\n"
            + "\n".join(char_parts) + "\n\n"
        )

    # 3) 台词块
    dialogue_lines = ""
    if req.dialogues:
        parts = []
        for d in req.dialogues:
            text = (d.get("text") or "").strip()
            if not text: continue
            speaker = (d.get("character") or "").strip()
            parts.append(f"  [{speaker or 'Narration'}]: {text}")
        if parts:
            dialogue_lines = "Dialogues / narration (earlier → start frame, later → end frame):\n" + \
                              "\n".join(parts) + "\n"

    user_msg = I2I_PROMPT_USER_TEMPLATE.format(
        char_block=char_block,
        ref_block=ref_block,
        description=req.description,
        dialogue_lines=dialogue_lines,
        workflow_kind=req.workflow_kind,
        ref_count=ref_count,
        ref_count_plural="" if ref_count == 1 else "s",
    )

    cfg = load_settings().text_engine
    full_text = ""
    async for chunk in stream_chat(cfg, I2I_PROMPT_SYSTEM, user_msg):
        full_text += chunk

    cleaned = re.sub(r"```(?:json)?\n?", "", full_text).strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        obj = {}
        if m:
            try: obj = json.loads(m.group())
            except json.JSONDecodeError: obj = {}

    return {
        "start_frame_prompt": str(obj.get("start_frame_prompt", "")).strip(),
        "end_frame_prompt":   str(obj.get("end_frame_prompt", "")).strip(),
        "ref_descriptions":   ref_descs[:ref_count],   # 调试用，前端可忽略
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
    manuscript:  str  = ""   # full manuscript for pronoun resolution


@router.post("/suggest-scene-characters")
async def suggest_scene_characters(req: SuggestSceneCharactersRequest):
    if not req.all_names:
        return {"characters": []}

    dialogue_lines = "\n".join(
        f"  [{d.get('character','?')}]: {d.get('text','')}"
        for d in (req.dialogues or [])
    ) or "（无台词）"

    # Truncate manuscript to keep context manageable
    ms = (req.manuscript or "").strip()
    if len(ms) > 2000:
        ms = ms[:2000] + "... (截断)"
    if not ms:
        ms = "（未提供文案）"

    user_msg = SUGGEST_CHARS_USER_TEMPLATE.format(
        manuscript=ms,
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


# ── Video prompt generation (streaming SSE) ────────────────────────────────────

@router.post("/generate-video-prompt")
async def generate_video_prompt(req: GenerateVideoPromptRequest):
    # Characters block
    char_lines = []
    if req.characters:
        for c in req.characters:
            name = c.get("name", "").strip()
            if not name:
                continue
            role       = c.get("role",       "").strip()
            appearance = c.get("appearance", "").strip()
            traits     = c.get("traits",     "").strip()
            visual = appearance or traits or ""
            line = f"  - {name}"
            if role:   line += f" ({role})"
            if visual: line += f": {visual}"
            char_lines.append(line)
    characters_block = (
        "Characters in this scene (ONLY these characters — do not add others):\n" + "\n".join(char_lines) + "\n\n"
        if char_lines else ""
    )

    # Dialogues block
    dlg_lines = [
        f"  [{d.get('character','?')} / {d.get('emotion','平静')}]: {d.get('text','')}"
        for d in (req.dialogues or [])
        if d.get("text")
    ]
    dialogues_block = (
        "Dialogues (with emotion):\n" + "\n".join(dlg_lines) + "\n\n"
        if dlg_lines else ""
    )

    # Truncate manuscript if needed
    ms = (req.manuscript or "").strip()
    if len(ms) > 3000:
        ms = ms[:3000] + "... (truncated)"
    if not ms:
        ms = "（未提供文案）"

    user_msg = VIDEO_PROMPT_USER_TEMPLATE.format(
        manuscript=ms,
        scene_index=req.scene_index or 1,
        total_scenes=req.total_scenes or 1,
        description=req.description or "（无描述）",
        characters_block=characters_block,
        dialogues_block=dialogues_block,
        start_frame_prompt=req.start_frame_prompt or "（未提供）",
        end_frame_prompt=req.end_frame_prompt or "（未提供）",
    )

    cfg = load_settings().text_engine

    async def sse_stream():
        try:
            async for chunk in stream_chat(cfg, VIDEO_PROMPT_SYSTEM, user_msg):
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
