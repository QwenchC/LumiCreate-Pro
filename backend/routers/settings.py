from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import AppSettings, TextPlatform, load_settings, save_settings

router = APIRouter()


@router.get("", response_model=AppSettings)
async def get_settings():
    return load_settings()


@router.post("", response_model=AppSettings)
async def update_settings(new_settings: AppSettings):
    save_settings(new_settings)
    return new_settings


# v1.4.11+: 文本引擎平台清单（builtin + 用户自定义）
@router.get("/text-platforms")
async def list_text_platforms():
    """返回 builtin + 用户自定义平台合并清单（用于设置页下拉）。"""
    from services.text_platforms import merge_platforms, BUILTIN_TEXT_PLATFORMS
    s = load_settings()
    merged = merge_platforms(s.text_engine.custom_platforms)
    return {"platforms": [p.model_dump() for p in merged],
            "builtin_ids": [p.id for p in BUILTIN_TEXT_PLATFORMS]}


class TextPlatformAdd(BaseModel):
    id:         str
    label:      str
    base_url:   str
    api_path:   str = "chat/completions"
    model_hint: str = ""
    is_ollama:  bool = False


@router.post("/text-platforms")
async def add_text_platform(payload: TextPlatformAdd):
    """新增自定义平台（builtin id 冲突直接拒绝）。"""
    from services.text_platforms import BUILTIN_TEXT_PLATFORMS
    builtin_ids = {p.id for p in BUILTIN_TEXT_PLATFORMS}
    pid = (payload.id or "").strip()
    if not pid:
        raise HTTPException(400, detail="平台 id 不能为空")
    if pid in builtin_ids:
        raise HTTPException(400, detail=f"平台 id 与内置冲突：{pid}")
    s = load_settings()
    for ex in s.text_engine.custom_platforms:
        if ex.id == pid:
            raise HTTPException(400, detail=f"平台 id 已存在：{pid}")
    s.text_engine.custom_platforms.append(TextPlatform(
        id=pid, label=payload.label or pid,
        base_url=payload.base_url, api_path=payload.api_path,
        model_hint=payload.model_hint,
        is_ollama=payload.is_ollama, is_builtin=False,
    ))
    save_settings(s)
    return {"ok": True, "id": pid}


@router.delete("/text-platforms/{platform_id}", status_code=204)
async def delete_text_platform(platform_id: str):
    """删除自定义平台（builtin 不可删）。"""
    from services.text_platforms import BUILTIN_TEXT_PLATFORMS
    if any(p.id == platform_id for p in BUILTIN_TEXT_PLATFORMS):
        raise HTTPException(400, detail="内置平台不可删除")
    s = load_settings()
    before = len(s.text_engine.custom_platforms)
    s.text_engine.custom_platforms = [
        p for p in s.text_engine.custom_platforms if p.id != platform_id
    ]
    if len(s.text_engine.custom_platforms) == before:
        raise HTTPException(404, detail=f"平台不存在：{platform_id}")
    save_settings(s)
