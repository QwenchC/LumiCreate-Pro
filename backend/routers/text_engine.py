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
    SMART_SCENES_SYSTEM,
    SMART_SCENES_USER_TEMPLATE,
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
    MUSIC_PROMPT_SYSTEM,
    MUSIC_PROMPT_USER_TEMPLATE,
    VIDEO_PROMPT_SYSTEM,
    VIDEO_PROMPT_USER_TEMPLATE,
    IDEOGRAM_OVERVIEW_SYSTEM,
    IDEOGRAM_OVERVIEW_USER_TEMPLATE,
    IDEOGRAM_ELEMENTS_SYSTEM,
    IDEOGRAM_ELEMENTS_USER_TEMPLATE,
    TAG_SPEAKERS_SYSTEM,
    TAG_SPEAKERS_USER_TEMPLATE,
    WHITE_BG_PORTRAIT_SYSTEM,
    WHITE_BG_PORTRAIT_USER_TEMPLATE,
    BG_SCENE_PROMPT_SYSTEM,
    BG_SCENE_PROMPT_USER_TEMPLATE,
    MSR_VIDEO_PROMPT_SYSTEM,
    MSR_VIDEO_PROMPT_USER_TEMPLATE,
    MSR_VIDEO_MODE_GUIDANCE,
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


# ── v1.6.2: 智能分镜（导演式，分段多次续接）─────────────────────────────────────

class SmartScenesRequest(BaseModel):
    manuscript:    str
    dialogue_mode: str = "mixed"
    characters:    list = []


def _split_manuscript_segments(text: str, target: int = 700) -> list:
    """把文案按段落/句末切成 ~target 字的片段，让每段 LLM 调用都能丰富分镜、
    不被单次输出上限逼着压缩描述。返回片段列表（至少 1 段）。"""
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    segs: list = []
    cur = ""

    def _flush():
        nonlocal cur
        if cur.strip():
            segs.append(cur.strip())
        cur = ""

    for p in paras:
        if len(p) > target * 1.6:          # 段落本身过长 → 按句末标点二次切
            for s in re.split(r"(?<=[。！？!?…\n])", p):
                if cur and len(cur) + len(s) > target:
                    _flush()
                cur += s
            _flush()
        else:
            if cur and len(cur) + len(p) > target:
                _flush()
            cur += ("\n" + p if cur else p)
    _flush()
    return segs or [text]


@router.post("/generate-scenes-smart")
async def generate_scenes_smart(req: SmartScenesRequest):
    """导演式智能分镜：把文案分段、逐段续接生成电影感分镜，SSE 流式回传。
    每段一次 LLM 调用（互带前情衔接），避免单次输出上限逼简化每镜描述。"""
    cfg = load_settings().text_engine
    chars = req.characters or []

    lines = []
    for c in chars:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        role = (c.get("role") or "").strip()
        lines.append(f"- {name}" + (f"（{role}）" if role else ""))
    characters_hint = ("\n【主要角色参考】\n" + "\n".join(lines) + "\n") if lines else ""
    mode_desc = DIALOGUE_MODE_DESC.get(req.dialogue_mode, DIALOGUE_MODE_DESC["mixed"])
    dialogue_mode_hint = f"\n【对白模式】{mode_desc}\n"
    known_names = [c.get("name", "") for c in chars
                   if isinstance(c, dict) and c.get("name")]

    def _detect(text: str) -> list:
        return [n for n in known_names if n and n in text] if known_names else []

    segments = _split_manuscript_segments(req.manuscript)

    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def stream():
        all_count = 0
        last_desc = ""
        for si, seg in enumerate(segments):
            continuity = (
                f"\n【前情衔接】前面已生成 {all_count} 个分镜，最后一镜画面是：{last_desc[:80]}。"
                f"本段剧情紧接其后，请自然承接、不要重复已分内容。\n"
            ) if all_count else ""
            user_msg = SMART_SCENES_USER_TEMPLATE.format(
                characters_hint=characters_hint, dialogue_mode_hint=dialogue_mode_hint,
                continuity_hint=continuity, segment=seg, next_index=all_count + 1)
            full = ""
            try:
                async for chunk in stream_chat(cfg, SMART_SCENES_SYSTEM, user_msg):
                    full += chunk
            except Exception as e:
                yield _sse({"event": "segment_error", "segment": si + 1,
                            "message": str(e)[:300]})
                continue
            raw = _extract_json_array(full) or []
            batch = []
            for s in raw:
                if not isinstance(s, dict):
                    continue
                all_count += 1
                desc = (s.get("description") or "").strip()
                dlgs = s.get("dialogues") if isinstance(s.get("dialogues"), list) else []
                scan = desc + " " + " ".join(
                    ((d.get("text") or "") + " " + (d.get("character") or ""))
                    for d in dlgs if isinstance(d, dict))
                if desc:
                    last_desc = desc
                batch.append({
                    "id": f"scene_{all_count:03d}", "index": all_count,
                    "description": desc,
                    "duration_estimate": float(s.get("duration_estimate", 6.0) or 6.0),
                    "start_frame_prompt": s.get("start_frame_prompt", "") or "",
                    "end_frame_prompt": s.get("end_frame_prompt", "") or "",
                    "dialogues": dlgs,
                    "_scene_characters": _detect(scan),
                })
            yield _sse({"event": "scenes", "scenes": batch, "segment": si + 1,
                        "total_segments": len(segments), "total_scenes": all_count})
        yield _sse({"event": "done", "total": all_count})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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


# ── v1.4.13: Ideogram 4 结构化 caption 生成（分步：overview → elements）──────


class IdeogramCaptionRequest(BaseModel):
    description: str                       # 画面描述（中/英文均可）
    step: str = "overview"                 # 'overview' | 'elements'
    style_type: str = "photo"              # 'photo' | 'art_style'
    width: int = 1024                      # 画布尺寸（elements 步摆 bbox 用）
    height: int = 1024
    overview: Optional[dict] = None        # elements 步传入第一步结果作上下文
    characters: list[dict] = []            # 可选角色卡 [{name, role, appearance, traits}]


def _llm_json(text: str) -> dict:
    """从 LLM 响应中稳健抽取 JSON 对象（剥 markdown 围栏 + 首尾大括号兜底）。"""
    cleaned = re.sub(r"```(?:json)?\n?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {}


def _ideogram_chars_block(characters: list[dict]) -> str:
    parts = []
    for c in characters or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        visual = (c.get("appearance") or c.get("traits") or "").strip()
        line = f"  - {name}"
        if c.get("role"): line += f" ({c['role']})"
        if visual:        line += f": {visual}"
        parts.append(line)
    if not parts:
        return ""
    return (
        "Characters present in this scene (for character CONSISTENCY — these are the ONLY people in the image, "
        "do NOT invent or add others):\n"
        + "\n".join(parts) + "\n"
        "For every character that appears, create an \"obj\" element whose desc embeds that character's FULL "
        "appearance verbatim (hair, face, clothing, accessories, body) so the rendered person matches across "
        "shots. Bind each appearance to its own character — never blend, swap, or transfer features between them.\n\n"
    )


def _clamp_bbox(bbox) -> Optional[list[int]]:
    """校验 + 收敛 bbox 到 0-1000 网格；非法返 None。"""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        vals = [max(0, min(1000, int(round(float(v))))) for v in bbox]
    except (TypeError, ValueError):
        return None
    ymin, xmin, ymax, xmax = vals
    if ymax <= ymin or xmax <= xmin:
        return None
    return vals


@router.post("/generate-ideogram-caption")
async def generate_ideogram_caption(req: IdeogramCaptionRequest):
    """分步生成 Ideogram 4 结构化 caption（JSON 大 → 两次小响应拼起来）。

    step='overview' → {high_level_description, background, style_description}
    step='elements' → {elements: [...]}（bbox 服务端校验 + 0-1000 夹紧）
    """
    if not (req.description or "").strip():
        raise HTTPException(400, detail="description 不能为空")
    step = (req.step or "overview").lower()
    if step not in ("overview", "elements"):
        raise HTTPException(400, detail=f"非法 step: {req.step!r}（应为 overview / elements）")

    chars_block = _ideogram_chars_block(req.characters)
    cfg = load_settings().text_engine

    if step == "overview":
        style_type = req.style_type if req.style_type in ("photo", "art_style") else "photo"
        user_msg = IDEOGRAM_OVERVIEW_USER_TEMPLATE.format(
            style_type=style_type,
            characters_block=chars_block,
            description=req.description,
        )
        full = ""
        async for chunk in stream_chat(cfg, IDEOGRAM_OVERVIEW_SYSTEM, user_msg):
            full += chunk
        obj = _llm_json(full)
        if not obj:
            raise HTTPException(502, detail="LLM 未返回有效 JSON（overview 步）")
        # 只透传认识的 3 个 key，去掉幻觉字段
        out = {k: obj[k] for k in
               ("high_level_description", "background", "style_description")
               if k in obj}
        return {"step": "overview", "data": out}

    # step == 'elements'
    user_msg = IDEOGRAM_ELEMENTS_USER_TEMPLATE.format(
        width=req.width, height=req.height,
        characters_block=chars_block,
        description=req.description,
        overview_json=json.dumps(req.overview or {}, ensure_ascii=False),
    )
    full = ""
    async for chunk in stream_chat(cfg, IDEOGRAM_ELEMENTS_SYSTEM, user_msg):
        full += chunk
    obj = _llm_json(full)
    raw_elements = obj.get("elements") if isinstance(obj, dict) else None
    if not isinstance(raw_elements, list):
        raise HTTPException(502, detail="LLM 未返回有效 elements 数组")
    elements: list[dict] = []
    for el in raw_elements[:9]:           # Ideogram 多模态上限附近，留余量
        if not isinstance(el, dict):
            continue
        etype = "text" if el.get("type") == "text" else "obj"
        out_el: dict = {"type": etype}
        bbox = _clamp_bbox(el.get("bbox"))
        if bbox:
            out_el["bbox"] = bbox
        if etype == "text":
            out_el["text"] = str(el.get("text") or "")
        out_el["desc"] = str(el.get("desc") or "")
        if isinstance(el.get("color_palette"), list):
            out_el["color_palette"] = [str(c) for c in el["color_palette"][:5]]
        elements.append(out_el)
    return {"step": "elements", "data": {"elements": elements}}


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


# ── v1.5.1: 给已有台词逐条指派说话人（音色 100% 可控）──────────────────────────

class TagSpeakersRequest(BaseModel):
    lines:      list[str] = []   # 台词文本（保持顺序与原文不变）
    characters: list[str] = []   # 角色名单（roster）
    context:    str = ""         # 分镜描述 / 完整文案，用于消解人称代词


@router.post("/tag-dialogue-speakers")
async def tag_dialogue_speakers(req: TagSpeakersRequest):
    """对一组**已有台词**逐条指派说话人（不改写台词，只返回 speakers 数组）。

    返回 {"speakers": [...]}，长度与传入 lines（非空者）等长；每个元素是角色名单里的
    名字，或空串 ""（旁白/未识别）。服务端对 LLM 输出做名单校验，未知名一律归 ""，
    确保前端拿到的说话人 100% 落在合法集合内。
    """
    lines = [str(l) for l in (req.lines or []) if str(l or "").strip()]
    roster = [c for c in (req.characters or []) if c]
    if not lines:
        return {"speakers": []}
    if not roster:
        # 无角色名单 → 全部旁白（无可指派对象）
        return {"speakers": ["" for _ in lines]}

    numbered = "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(lines))
    ctx = (req.context or "").strip()
    if len(ctx) > 2000:
        ctx = ctx[:2000] + "...（截断）"
    user_msg = TAG_SPEAKERS_USER_TEMPLATE.format(
        roster="、".join(roster),
        context=ctx or "（无额外上下文）",
        lines=numbered,
    )

    cfg = load_settings().text_engine
    full = ""
    async for chunk in stream_chat(cfg, TAG_SPEAKERS_SYSTEM, user_msg):
        full += chunk

    cleaned = re.sub(r"```(?:json)?\n?", "", full).strip()
    arr = None
    try:
        arr = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", cleaned)
        if m:
            try:
                arr = json.loads(m.group())
            except json.JSONDecodeError:
                arr = None
    if not isinstance(arr, list):
        # 解析失败：整体回退为旁白，前端用下拉手动纠正（绝不乱猜）
        return {"speakers": ["" for _ in lines]}

    valid = set(roster)
    speakers: list[str] = []
    for i in range(len(lines)):
        name = str(arr[i]).strip() if i < len(arr) else ""
        speakers.append(name if name in valid else "")
    return {"speakers": speakers}


# ── v1.6: 纯白背景立绘提示词优化（供 MSR 多图参考视频）────────────────────────

class WhiteBgPortraitRequest(BaseModel):
    appearance:  str = ""        # 角色外观描述
    base_prompt: str = ""        # 现有草稿提示词（可选）


@router.post("/optimize-white-bg-portrait")
async def optimize_white_bg_portrait(req: WhiteBgPortraitRequest):
    """用文本引擎把角色外观改写成"纯白背景、单人、全身"的图像提示词。
    返回 {prompt, negative}。LLM 失败时回退到确定性拼接，保证可用。"""
    appearance = (req.appearance or "").strip()
    base = (req.base_prompt or "").strip()
    # 纯白背景的强负面词（直接给图片引擎用，进一步压制背景）
    negative = ("background scenery, environment, room, furniture, props, gradient "
                "background, colored background, shadow on background, multiple people, "
                "text, watermark, lowres, blurry")

    user_msg = WHITE_BG_PORTRAIT_USER_TEMPLATE.format(
        appearance=appearance or "（未提供）",
        base_prompt=base or "（无）",
    )
    cfg = load_settings().text_engine
    full = ""
    try:
        async for chunk in stream_chat(cfg, WHITE_BG_PORTRAIT_SYSTEM, user_msg):
            full += chunk
    except Exception:
        full = ""
    prompt = re.sub(r"^```\w*\n?|\n?```$", "", full).strip().strip('"').strip()
    if not prompt:
        # 兜底：确定性拼接，仍能产出纯白背景立绘
        wb = ("full body, single character, front view, neutral standing pose, "
              "isolated on pure white background, plain white studio backdrop, "
              "seamless white, no scenery, no props, even flat lighting, "
              "no cast shadow on background, masterpiece, best quality")
        prompt = f"{appearance}, {wb}" if appearance else wb
    return {"prompt": prompt, "negative": negative}


# ── v1.6: 无角色背景图提示词（单 + 批量）─────────────────────────────────────────

def _bg_context_block(manuscript: str, scene_index: int, total_scenes: int) -> str:
    parts = []
    if scene_index or total_scenes:
        parts.append(f"This is scene {scene_index} of {total_scenes}.")
    ms = (manuscript or "").strip()
    if ms:
        if len(ms) > 1500:
            ms = ms[:1500] + "..."
        parts.append("Story context (for understanding only):\n" + ms)
    return ("\n".join(parts) + "\n") if parts else ""


async def _gen_bg_prompt(description: str, manuscript: str = "",
                         scene_index: int = 0, total_scenes: int = 0) -> str:
    user_msg = BG_SCENE_PROMPT_USER_TEMPLATE.format(
        description=(description or "").strip() or "（无描述）",
        context=_bg_context_block(manuscript, scene_index, total_scenes),
    )
    cfg = load_settings().text_engine
    full = ""
    async for chunk in stream_chat(cfg, BG_SCENE_PROMPT_SYSTEM, user_msg):
        full += chunk
    return re.sub(r"^```\w*\n?|\n?```$", "", full).strip().strip('"').strip()


class BgPromptRequest(BaseModel):
    description:  str = ""
    manuscript:   str = ""
    scene_index:  int = 0
    total_scenes: int = 0


@router.post("/generate-bg-prompt")
async def generate_bg_prompt(req: BgPromptRequest):
    """生成【无角色】背景图提示词（专用指令彻底排除人物）。返回 {prompt}。"""
    prompt = await _gen_bg_prompt(req.description, req.manuscript,
                                  req.scene_index, req.total_scenes)
    return {"prompt": prompt}


class BgPromptsBatchRequest(BaseModel):
    scenes:       list[dict] = []    # [{scene_id, description}]
    manuscript:   str = ""
    total_scenes: int = 0
    concurrency:  int = 0


@router.post("/generate-bg-prompts-batch")
async def generate_bg_prompts_batch(req: BgPromptsBatchRequest):
    """为全部分镜批量生成无角色背景提示词。SSE: {event:result, scene_id, bg_prompt}。"""
    sem = _asyncio.Semaphore(_resolve_concurrency(req.concurrency))

    async def gen_one(s: dict) -> dict:
        async with sem:
            p = await _gen_bg_prompt(s.get("description", ""), req.manuscript,
                                     int(s.get("scene_index", 0) or 0), req.total_scenes)
            return {"scene_id": s.get("scene_id", ""), "bg_prompt": p}

    return await _run_batched_sse(req.scenes, gen_one)


# ── v1.6: MSR 多图参考视频提示词（“参考图N + 动作叙述”格式，单 + 批量）───────────

def _msr_ref_block(characters: list) -> str:
    """逐行列出参考图（角色顺序即 LiconMSR 槽位顺序），最后追加场景参考图占位。
    编号一律按【已追加行数】推导（而非 enumerate 下标），跳过非法条目后仍连续 1..N。"""
    lines = []
    for c in characters or []:
        if not isinstance(c, dict):
            continue
        n = len(lines) + 1
        name = (c.get("name") or "").strip() or f"角色{n}"
        appearance = (c.get("appearance") or c.get("traits") or "").strip() or "（未提供外观）"
        lines.append(f"参考图{n}：标签={name}，外观={appearance}")
    lines.append(f"参考图{len(lines) + 1}（场景）：见下方“背景/场景描述”")
    return "\n".join(lines)


def _msr_dialogues_block(dialogues: list) -> str:
    parts = []
    for d in dialogues or []:
        if not isinstance(d, dict):
            continue
        text = (d.get("text") or "").strip()
        if not text:
            continue
        spk = (d.get("character") or "").strip()
        parts.append(f"  [{spk or '旁白'}]：{text}")
    if not parts:
        return ""
    return ("台词（按叙事顺序，需逐字融入动作叙述并保留引号）：\n"
            + "\n".join(parts) + "\n")


async def _gen_msr_prompt(characters: list, background: str, description: str,
                          dialogues: list, scene_index: int = 0,
                          total_scenes: int = 0, dialogue_mode: str = "mixed") -> str:
    # v1.6.2: 按对白模式注入差异化「动作叙述」指导（纯旁白/纯对话/混合/纯朗读）
    mode_guidance = MSR_VIDEO_MODE_GUIDANCE.get(
        (dialogue_mode or "mixed"), MSR_VIDEO_MODE_GUIDANCE["mixed"])
    user_msg = MSR_VIDEO_PROMPT_USER_TEMPLATE.format(
        ref_block=_msr_ref_block(characters),
        background=(background or "").strip() or "（沿用画面描述中的环境，纯场景无人物）",
        scene_index=scene_index or 0, total_scenes=total_scenes or 0,
        description=(description or "").strip() or "（无描述）",
        dialogues_block=_msr_dialogues_block(dialogues),
        mode_guidance=mode_guidance,
    )
    cfg = load_settings().text_engine
    full = ""
    async for chunk in stream_chat(cfg, MSR_VIDEO_PROMPT_SYSTEM, user_msg):
        full += chunk
    return re.sub(r"^```\w*\n?|\n?```$", "", full).strip()


class MsrVideoPromptRequest(BaseModel):
    characters:   list = []      # 参考图顺序，每个 {name, appearance/traits}
    background:   str = ""       # 背景/场景描述（背景图的内容）
    description:  str = ""
    dialogues:    list = []
    scene_index:  int = 0
    total_scenes: int = 0
    dialogue_mode: str = "mixed"  # narration|dialogue|mixed|reading → 差异化动作叙述指导


@router.post("/generate-msr-video-prompt")
async def generate_msr_video_prompt(req: MsrVideoPromptRequest):
    """生成 MSR 多图参考视频提示词（参考图N + 动作叙述格式）。返回 {prompt}。"""
    p = await _gen_msr_prompt(req.characters, req.background, req.description,
                              req.dialogues, req.scene_index, req.total_scenes,
                              req.dialogue_mode)
    return {"prompt": p}


class MsrVideoPromptsBatchRequest(BaseModel):
    scenes:       list[dict] = []    # [{scene_id, characters, background, description, dialogues, scene_index}]
    total_scenes: int = 0
    concurrency:  int = 0
    dialogue_mode: str = "mixed"     # 项目级对白模式（每镜可被 scene 内 dialogue_mode 覆盖）


@router.post("/generate-msr-video-prompts-batch")
async def generate_msr_video_prompts_batch(req: MsrVideoPromptsBatchRequest):
    """为全部 MSR 分镜批量生成提示词。SSE: {event:result, scene_id, prompt}。"""
    sem = _asyncio.Semaphore(_resolve_concurrency(req.concurrency))

    async def gen_one(s: dict) -> dict:
        async with sem:
            p = await _gen_msr_prompt(
                s.get("characters") or [], s.get("background", ""),
                s.get("description", ""), s.get("dialogues") or [],
                s.get("scene_index", 0), req.total_scenes,
                s.get("dialogue_mode") or req.dialogue_mode,
            )
            return {"scene_id": s.get("scene_id", ""), "prompt": p}

    return await _run_batched_sse(req.scenes, gen_one)


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


# ── v1.4.2: 音乐标签 + 歌词 AI 助写（ACE-Step）────────────────────────────────


_LANGUAGE_LABEL = {
    "zh": "Chinese (中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
}


class GenerateMusicPromptRequest(BaseModel):
    user_request:     str                     # 用户的高层简介（必填）
    language:         str = "zh"
    duration_seconds: int = 60
    bpm:              int = 120
    time_signature:   str = "4"
    key_scale:        str = "C major"
    project_id:       str = ""                # 可选：拿项目文案做背景上下文
    include_lyrics:   bool = True             # False = 仅给 tags（纯器乐）


@router.post("/generate-music-prompt")
async def generate_music_prompt(req: GenerateMusicPromptRequest):
    if not req.user_request.strip():
        raise HTTPException(400, detail="user_request 不能为空")

    # 项目上下文：把文案前 800 字符塞进去，让歌词贴合剧情
    project_context = ""
    if req.project_id.strip():
        try:
            from pathlib import Path as _P
            ppath = _P(load_settings().projects_dir) / req.project_id / "manuscript.txt"
            if ppath.exists():
                snippet = ppath.read_text(encoding="utf-8-sig").strip()[:800]
                if snippet:
                    project_context = f"\nProject manuscript context (excerpt):\n{snippet}\n"
        except Exception:
            pass

    user_msg = MUSIC_PROMPT_USER_TEMPLATE.format(
        user_request    = req.user_request.strip(),
        language_display = _LANGUAGE_LABEL.get(req.language, req.language),
        duration_seconds = max(10, int(req.duration_seconds)),
        bpm             = int(req.bpm),
        time_signature  = req.time_signature,
        key_scale       = req.key_scale or "Not specified",
        project_context = project_context,
    )

    # 纯器乐时让模型只给 tags
    sys_msg = MUSIC_PROMPT_SYSTEM
    if not req.include_lyrics:
        sys_msg = sys_msg + (
            "\n\n** This song is INSTRUMENTAL — return an empty string for "
            "\"lyrics\" and put all detail into \"tags\". **"
        )

    cfg = load_settings().text_engine
    full_text = ""
    async for chunk in stream_chat(cfg, sys_msg, user_msg):
        full_text += chunk

    cleaned = re.sub(r"```(?:json)?\n?", "", full_text).strip()
    obj: dict = {}
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
        "tags":   str(obj.get("tags", "")).strip(),
        "lyrics": str(obj.get("lyrics", "")).strip(),
    }


# ── v1.4.2: 批量 SSE 端点 ────────────────────────────────────────────────────
#
# 真实瓶颈：Chromium 对单 origin 的 HTTP/1.1 连接上限 = 6。前端就算 fire 50
# 个 fetch，浏览器只放出 6 个连接，其它在浏览器内部排队，跟我们的 worker
# pool 完全无关。Settings 里改 concurrency=50 在前端 fetch 模式下永远只能跑 ~5 个。
#
# 解决：单 connection / 多结果。前端开一个 SSE，发一个含 N 条任务的请求，
# 后端用 asyncio.Semaphore(N_settings) 真正并发跑，每完成一条就 SSE push 出来。
# 浏览器只占 1 个 origin slot，N 由后端 settings 完全控制。

import asyncio as _asyncio


def _build_char_block(characters: list) -> str:
    """构建角色描述块（与 generate_frame_prompts / generate_video_prompt 同款）。"""
    char_lines = []
    for c in characters or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        role       = (c.get("role")       or "").strip()
        appearance = (c.get("appearance") or "").strip()
        traits     = (c.get("traits")     or "").strip()
        visual = appearance or traits or ""
        line = f"  - {name}"
        if role:   line += f" ({role})"
        if visual: line += f": {visual}"
        char_lines.append(line)
    return "\n".join(char_lines)


def _parse_json_object(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\n?", "", (text or "")).strip()
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                obj = json.loads(m.group())
                return obj if isinstance(obj, dict) else {}
            except json.JSONDecodeError:
                pass
    return {}


def _parse_json_list(text: str) -> list:
    cleaned = re.sub(r"```(?:json)?\n?", "", (text or "")).strip()
    try:
        arr = json.loads(cleaned)
        return arr if isinstance(arr, list) else []
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", cleaned)
        if m:
            try:
                arr = json.loads(m.group())
                return arr if isinstance(arr, list) else []
            except json.JSONDecodeError:
                pass
    return []


def _resolve_concurrency(req_value: int) -> int:
    """req.concurrency=0 → 跟随 settings.text_engine.concurrency；上限 100。"""
    if req_value and req_value > 0:
        return max(1, min(int(req_value), 100))
    try:
        cfg = load_settings().text_engine
        n = int(getattr(cfg, "concurrency", 4) or 4)
        return max(1, min(n, 100))
    except Exception:
        return 4


async def _run_batched_sse(items, gen_one):
    """通用批量 SSE 跑路。gen_one(item) -> dict，必须含 scene_id 让前端定位结果。"""
    queue: _asyncio.Queue = _asyncio.Queue()
    total = len(items)

    async def worker(item):
        try:
            result = await gen_one(item)
            await queue.put({"event": "result", **result})
        except Exception as e:
            sid = item.get("scene_id") if isinstance(item, dict) else ""
            await queue.put({"event": "item_error",
                             "scene_id": sid, "message": str(e)[:500]})

    async def producer():
        await _asyncio.gather(*(worker(it) for it in items),
                               return_exceptions=True)
        await queue.put(None)   # sentinel

    async def stream():
        _asyncio.create_task(producer())
        while True:
            ev = await queue.get()
            if ev is None: break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'event': 'done', 'total': total}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Batch: frame prompts (图片提示词)─────────────────────────────────────────


class BatchFramePromptsRequest(BaseModel):
    frames:       list[dict]
    characters:   list = []
    manuscript:   str  = ""
    total_scenes: int  = 0
    concurrency:  int  = 0


@router.post("/generate-frame-prompts-batch")
async def generate_frame_prompts_batch(req: BatchFramePromptsRequest):
    concurrency = _resolve_concurrency(req.concurrency)
    sem = _asyncio.Semaphore(concurrency)
    cfg = load_settings().text_engine

    def _build_char_block_text(chars: list) -> str:
        inner = _build_char_block(chars)
        if not inner: return ""
        return ("Characters in this scene (ONLY these characters exist in this frame — "
                "do not add any others):\n" + inner + "\n\n")

    shared_char_block = _build_char_block_text(req.characters)

    async def gen_one(frame: dict) -> dict:
        async with sem:
            # 优先用 frame 自带 characters（per-scene 子集），否则用共享集合
            char_block = (_build_char_block_text(frame["characters"])
                          if isinstance(frame.get("characters"), list)
                          else shared_char_block)
            dialogue_lines = ""
            if frame.get("dialogues"):
                parts = []
                for d in frame["dialogues"]:
                    text = (d.get("text") or "").strip()
                    if not text: continue
                    speaker = (d.get("character") or "").strip()
                    parts.append(f"  [{speaker or 'Narration'}]: {text}")
                if parts:
                    dialogue_lines = (
                        "Dialogues / narration (read in narrative order — earlier "
                        "lines correspond to the start frame, later lines to the "
                        "end frame):\n" + "\n".join(parts) + "\n"
                    )
            user_msg = FRAME_PROMPT_USER_TEMPLATE.format(
                char_block=char_block,
                description=frame.get("description", ""),
                dialogue_lines=dialogue_lines,
            )
            full_text = ""
            async for chunk in stream_chat(cfg, FRAME_PROMPT_SYSTEM, user_msg):
                full_text += chunk
            obj = _parse_json_object(full_text)
            return {
                "scene_id":           frame.get("scene_id", ""),
                "start_frame_prompt": str(obj.get("start_frame_prompt", "")).strip(),
                "end_frame_prompt":   str(obj.get("end_frame_prompt",   "")).strip(),
            }

    return await _run_batched_sse(req.frames, gen_one)


# ── Batch: suggest scene characters (AI 自动选角色)────────────────────────────


class BatchSuggestSceneCharsRequest(BaseModel):
    scenes:      list[dict]
    all_names:   list = []
    manuscript:  str  = ""
    concurrency: int  = 0


@router.post("/suggest-scene-characters-batch")
async def suggest_scene_characters_batch(req: BatchSuggestSceneCharsRequest):
    concurrency = _resolve_concurrency(req.concurrency)
    sem = _asyncio.Semaphore(concurrency)

    if not req.all_names:
        async def gen_one_empty(s: dict) -> dict:
            return {"scene_id": s.get("scene_id", ""), "characters": []}
        return await _run_batched_sse(req.scenes, gen_one_empty)

    cfg = load_settings().text_engine
    ms_truncated = (req.manuscript or "").strip()
    if len(ms_truncated) > 2000:
        ms_truncated = ms_truncated[:2000] + "... (截断)"
    if not ms_truncated:
        ms_truncated = "（未提供文案）"
    all_names_str = "、".join(req.all_names)
    valid_names = set(req.all_names)

    async def gen_one(scene: dict) -> dict:
        async with sem:
            dialogue_lines = "\n".join(
                f"  [{d.get('character','?')}]: {d.get('text','')}"
                for d in (scene.get("dialogues") or [])
            ) or "（无台词）"
            user_msg = SUGGEST_CHARS_USER_TEMPLATE.format(
                manuscript=ms_truncated,
                description=scene.get("description", "") or "（无描述）",
                dialogues=dialogue_lines,
                all_names=all_names_str,
            )
            full_text = ""
            async for chunk in stream_chat(cfg, SUGGEST_CHARS_SYSTEM, user_msg):
                full_text += chunk
            arr = _parse_json_list(full_text)
            return {
                "scene_id":   scene.get("scene_id", ""),
                "characters": [n for n in arr if n in valid_names],
            }

    return await _run_batched_sse(req.scenes, gen_one)


# ── Batch: video prompts (视频提示词)────────────────────────────────────────


class BatchVideoPromptsRequest(BaseModel):
    scenes:       list[dict]
    characters:   list = []
    manuscript:   str  = ""
    total_scenes: int  = 0
    concurrency:  int  = 0


@router.post("/generate-video-prompts-batch")
async def generate_video_prompts_batch(req: BatchVideoPromptsRequest):
    concurrency = _resolve_concurrency(req.concurrency)
    sem = _asyncio.Semaphore(concurrency)
    cfg = load_settings().text_engine

    def _build_char_block_text(chars: list) -> str:
        inner = _build_char_block(chars)
        if not inner: return ""
        return ("Characters in this scene (ONLY these characters — do not add others):\n"
                + inner + "\n\n")

    shared_chars_block = _build_char_block_text(req.characters)

    ms = (req.manuscript or "").strip()
    if len(ms) > 3000:
        ms = ms[:3000] + "... (truncated)"
    if not ms:
        ms = "（未提供文案）"

    async def gen_one(scene: dict) -> dict:
        async with sem:
            characters_block = (_build_char_block_text(scene["characters"])
                                if isinstance(scene.get("characters"), list)
                                else shared_chars_block)
            dlg_lines = [
                f"  [{d.get('character','?')} / {d.get('emotion','平静')}]: {d.get('text','')}"
                for d in (scene.get("dialogues") or [])
                if d.get("text")
            ]
            dialogues_block = (
                "Dialogues (with emotion):\n" + "\n".join(dlg_lines) + "\n\n"
                if dlg_lines else ""
            )
            user_msg = VIDEO_PROMPT_USER_TEMPLATE.format(
                manuscript=ms,
                scene_index=scene.get("scene_index", 1) or 1,
                total_scenes=req.total_scenes or 1,
                description=scene.get("description", "") or "（无描述）",
                characters_block=characters_block,
                dialogues_block=dialogues_block,
                start_frame_prompt=scene.get("start_frame_prompt", "") or "（未提供）",
                end_frame_prompt=scene.get("end_frame_prompt", "") or "（未提供）",
            )
            full_text = ""
            async for chunk in stream_chat(cfg, VIDEO_PROMPT_SYSTEM, user_msg):
                full_text += chunk
            return {
                "scene_id": scene.get("scene_id", ""),
                "text":     full_text.strip(),
            }

    return await _run_batched_sse(req.scenes, gen_one)
