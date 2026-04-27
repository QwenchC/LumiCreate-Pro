import base64
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import load_settings

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ProjectProgress(BaseModel):
    manuscript: int = 0
    scenes: int = 0
    images: int = 0
    audio: int = 0
    video: int = 0


class ProjectMeta(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: str
    updated_at: str
    progress: ProjectProgress = ProjectProgress()


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _projects_root() -> Path:
    return Path(load_settings().projects_dir)


def _project_dir(project_id: str) -> Path:
    return _projects_root() / project_id


def _read_meta(project_id: str) -> ProjectMeta:
    meta_file = _project_dir(project_id) / "project.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectMeta(**json.loads(meta_file.read_text(encoding="utf-8")))


def _write_meta(meta: ProjectMeta) -> None:
    proj_dir = _project_dir(meta.id)
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "project.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ProjectMeta])
async def list_projects():
    root = _projects_root()
    if not root.exists():
        return []
    projects = []
    for entry in root.iterdir():
        if entry.is_dir():
            meta_file = entry / "project.json"
            if meta_file.exists():
                try:
                    projects.append(ProjectMeta(**json.loads(meta_file.read_text(encoding="utf-8"))))
                except Exception:
                    pass
    projects.sort(key=lambda p: p.updated_at, reverse=True)
    return projects


@router.post("", response_model=ProjectMeta, status_code=201)
async def create_project(req: CreateProjectRequest):
    now = datetime.now(timezone.utc).isoformat()
    project_id = f"proj_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    meta = ProjectMeta(id=project_id, name=req.name, description=req.description,
                       created_at=now, updated_at=now)
    _write_meta(meta)
    # Create subdirectories
    for sub in ("images", "audio", "video", "cache"):
        (_project_dir(project_id) / sub).mkdir(parents=True, exist_ok=True)
    return meta


@router.get("/{project_id}", response_model=ProjectMeta)
async def get_project(project_id: str):
    return _read_meta(project_id)


@router.put("/{project_id}", response_model=ProjectMeta)
async def update_project(project_id: str, updates: dict):
    meta = _read_meta(project_id)
    data = meta.model_dump()
    data.update(updates)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = ProjectMeta(**data)
    _write_meta(updated)
    return updated


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str):
    proj_dir = _project_dir(project_id)
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    shutil.rmtree(proj_dir)


# ── Manuscript ─────────────────────────────────────────────────────────────────

class ManuscriptData(BaseModel):
    content: str
    config: dict = {}


@router.get("/{project_id}/manuscript")
async def get_manuscript(project_id: str):
    _read_meta(project_id)  # validates project exists
    path = _project_dir(project_id) / "manuscript.md"
    cfg_path = _project_dir(project_id) / "manuscript_config.json"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    config = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    return {"content": content, "config": config}


@router.put("/{project_id}/manuscript", response_model=ProjectMeta)
async def save_manuscript(project_id: str, data: ManuscriptData):
    meta = _read_meta(project_id)
    proj_dir = _project_dir(project_id)
    (proj_dir / "manuscript.md").write_text(data.content, encoding="utf-8")
    if data.config:
        (proj_dir / "manuscript_config.json").write_text(
            json.dumps(data.config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    # Update progress
    progress = meta.progress.model_dump()
    progress["manuscript"] = 100 if data.content.strip() else 0
    return await update_project(project_id, {"progress": progress})


# ── Scenes ─────────────────────────────────────────────────────────────────────

class ScenesData(BaseModel):
    scenes: list


# ── Images ─────────────────────────────────────────────────────────────────────

class ImageSlot(BaseModel):
    scene_id:   str
    frame_type: str   # "start" | "end"
    slot_index: int
    data:       str   # base64 PNG, no data-url prefix


class ImagesState(BaseModel):
    slots:    list[ImageSlot]
    counts:   dict   # "{scene_id}:{frame_type}" -> int
    selected: dict   # "{scene_id}:start" | "{scene_id}:end" -> int


@router.get("/{project_id}/images")
async def load_images(project_id: str):
    proj_dir  = _project_dir(project_id)
    meta_path = proj_dir / "images.json"
    if not meta_path.exists():
        return {"slots": [], "counts": {}, "selected": {}}

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    img_dir  = proj_dir / "images"
    slots    = []
    for saved in metadata.get("saved_slots", []):
        img_path = img_dir / saved["filename"]
        if img_path.exists():
            data = base64.b64encode(img_path.read_bytes()).decode("ascii")
            slots.append({
                "scene_id":   saved["scene_id"],
                "frame_type": saved["frame_type"],
                "slot_index": saved["slot_index"],
                "data":       data,
            })

    return {
        "slots":    slots,
        "counts":   metadata.get("counts",   {}),
        "selected": metadata.get("selected", {}),
    }


@router.put("/{project_id}/images")
async def save_images(project_id: str, state: ImagesState):
    proj_dir = _project_dir(project_id)
    img_dir  = proj_dir / "images"
    img_dir.mkdir(exist_ok=True)

    saved_slots = []
    for slot in state.slots:
        filename = f"{slot.scene_id}_{slot.frame_type}_{slot.slot_index}.png"
        img_path = img_dir / filename
        img_path.write_bytes(base64.b64decode(slot.data))
        saved_slots.append({
            "scene_id":   slot.scene_id,
            "frame_type": slot.frame_type,
            "slot_index": slot.slot_index,
            "filename":   filename,
        })

    metadata = {
        "saved_slots": saved_slots,
        "counts":      state.counts,
        "selected":    state.selected,
    }
    (proj_dir / "images.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Update project progress
    meta = _read_meta(project_id)
    progress = meta.progress.model_dump()
    progress["images"] = 100 if saved_slots else 0
    await update_project(project_id, {"progress": progress})

    return {"ok": True, "saved": len(saved_slots)}


@router.get("/{project_id}/scenes")
async def get_scenes(project_id: str):
    _read_meta(project_id)
    path = _project_dir(project_id) / "scenes.json"
    if not path.exists():
        return {"scenes": []}
    return json.loads(path.read_text(encoding="utf-8"))


@router.put("/{project_id}/scenes", response_model=ProjectMeta)
async def save_scenes(project_id: str, data: ScenesData):
    meta = _read_meta(project_id)
    proj_dir = _project_dir(project_id)
    (proj_dir / "scenes.json").write_text(
        json.dumps({"scenes": data.scenes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    progress = meta.progress.model_dump()
    progress["scenes"] = 100 if data.scenes else 0
    return await update_project(project_id, {"progress": progress})


# ── Audio ──────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/audio")
async def get_audio(project_id: str):
    _read_meta(project_id)
    path = _project_dir(project_id) / "audio.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@router.put("/{project_id}/audio")
async def save_audio(project_id: str, data: dict):
    meta = _read_meta(project_id)
    proj_dir = _project_dir(project_id)
    (proj_dir / "audio.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Count clips that have at least one completed slot
    done = sum(
        1 for v in data.values()
        if any(s.get("data") for s in (v.get("slots") or []))
    )
    progress = meta.progress.model_dump()
    progress["audio"] = 100 if done else 0
    return await update_project(project_id, {"progress": progress})
