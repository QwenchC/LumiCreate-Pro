"""项目模板：把现有项目的"配置"打包成可复用模板。

模板包含：
- manuscript_config.json：对白模式、角色名单初稿（不含 manuscript 正文）
- characters.json（可选）：完整角色卡（含 appearance / voice / negative）
- engine_snapshot.json：image_workflow / video_workflow / resolution / fps / msedge_voice / msedge_rate / 字幕字号字体

模板**不**含 manuscript 正文 / scenes / images / audio / video。
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import load_settings

router = APIRouter()


# ── Paths ─────────────────────────────────────────────────────────────────────

def _templates_root() -> Path:
    """模板存放目录。默认在 projects_dir 同级 `LumiCreate-Templates`。"""
    s = load_settings()
    base = Path(s.projects_dir).expanduser()
    root = base.parent / f"{base.name}-Templates" if base.name else Path.home() / "LumiCreate-Templates"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _template_dir(template_id: str) -> Path:
    return _templates_root() / template_id


def _project_dir(project_id: str) -> Path:
    return Path(load_settings().projects_dir) / project_id


# ── Schemas ───────────────────────────────────────────────────────────────────


class TemplateMeta(BaseModel):
    id:          str
    name:        str
    description: str = ""
    created_at:  str = ""
    source_project_id: str = ""
    has_characters: bool = False
    has_engine_snapshot: bool = False


class CreateTemplateRequest(BaseModel):
    project_id:         str
    name:               str
    description:        str  = ""
    include_characters: bool = True


class ApplyTemplateRequest(BaseModel):
    project_id: str


class NewProjectFromTemplateRequest(BaseModel):
    template_id: str
    name:        str
    folder_id:   str = "default"


# ── List / read / delete ──────────────────────────────────────────────────────


def _read_template_meta(template_id: str) -> TemplateMeta:
    p = _template_dir(template_id) / "template.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    # Backfill flags
    dir_ = _template_dir(template_id)
    data["has_characters"]      = (dir_ / "characters.json").exists()
    data["has_engine_snapshot"] = (dir_ / "engine_snapshot.json").exists()
    return TemplateMeta(**data)


@router.get("", response_model=list[TemplateMeta])
async def list_templates():
    root = _templates_root()
    items: list[TemplateMeta] = []
    for sub in root.iterdir():
        if not sub.is_dir():
            continue
        meta_path = sub / "template.json"
        if not meta_path.exists():
            continue
        try:
            items.append(_read_template_meta(sub.name))
        except Exception:
            continue
    items.sort(key=lambda t: t.created_at, reverse=True)
    return items


@router.get("/{template_id}", response_model=TemplateMeta)
async def get_template(template_id: str):
    return _read_template_meta(template_id)


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: str):
    d = _template_dir(template_id)
    if not d.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    shutil.rmtree(d)


# ── Create from project ───────────────────────────────────────────────────────


@router.post("/from-project", response_model=TemplateMeta, status_code=201)
async def create_from_project(req: CreateTemplateRequest):
    src = _project_dir(req.project_id)
    if not src.exists():
        raise HTTPException(status_code=404, detail="Source project not found")

    template_id = f"tpl_{datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}"
    dst = _template_dir(template_id)
    dst.mkdir(parents=True, exist_ok=True)

    # 1) manuscript_config.json（必含——文案模式+角色名单基线）
    msc = src / "manuscript_config.json"
    if msc.exists():
        shutil.copy2(msc, dst / "manuscript_config.json")
    else:
        (dst / "manuscript_config.json").write_text("{}", encoding="utf-8")

    # 2) characters.json（按开关包含——含 appearance/voice/negative）
    if req.include_characters:
        cj = src / "characters.json"
        if cj.exists():
            shutil.copy2(cj, dst / "characters.json")

    # 3) engine_snapshot.json：当前 settings 的关键子集
    s = load_settings()
    snapshot = {
        "image_workflow":    s.image_engine.default_workflow,
        "image_width":       s.image_engine.image_width,
        "image_height":      s.image_engine.image_height,
        "style_preset":      s.image_engine.style_preset,
        "custom_style_text": s.image_engine.custom_style_text,
        "video_workflow":    s.video_engine.default_workflow,
        "video_resolution":  s.video_engine.resolution,
        "video_fps":         s.video_engine.fps,
        "audio_engine_type": s.audio_engine.engine_type,
        "msedge_voice":      s.audio_engine.msedge_voice,
        "msedge_rate":       s.audio_engine.msedge_rate,
    }
    (dst / "engine_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    meta = TemplateMeta(
        id=template_id,
        name=req.name,
        description=req.description,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_project_id=req.project_id,
        has_characters=(dst / "characters.json").exists(),
        has_engine_snapshot=True,
    )
    (dst / "template.json").write_text(
        meta.model_dump_json(indent=2), encoding="utf-8"
    )
    return meta


# ── Apply to existing project ─────────────────────────────────────────────────


@router.post("/{template_id}/apply", status_code=204)
async def apply_template(template_id: str, req: ApplyTemplateRequest):
    tdir = _template_dir(template_id)
    if not tdir.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    pdir = _project_dir(req.project_id)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="Target project not found")
    # 复制 manuscript_config.json 与 characters.json（如有）
    for filename in ("manuscript_config.json", "characters.json"):
        src = tdir / filename
        if src.exists():
            shutil.copy2(src, pdir / filename)


# ── Spawn a new project from a template ───────────────────────────────────────
# 这是"用户在主屏点'从模板新建'"的入口。仅创建项目 + 拷模板文件，不动 settings。
# （settings 是全局；如需采用模板的引擎设置，让用户在设置页手动调，避免破坏全局偏好）


@router.post("/{template_id}/spawn-project")
async def spawn_project_from_template(template_id: str, req: NewProjectFromTemplateRequest):
    tdir = _template_dir(template_id)
    if not tdir.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    # 调用内层 create_project 流程
    from routers.projects import (
        create_project, ProjectMeta,
        CreateProjectRequest,
    )
    new_meta = await create_project(
        CreateProjectRequest(name=req.name, description="", folder_id=req.folder_id)
    )
    # 然后拷模板配置
    pdir = _project_dir(new_meta.id)
    for filename in ("manuscript_config.json", "characters.json"):
        src = tdir / filename
        if src.exists():
            shutil.copy2(src, pdir / filename)
    return new_meta
