"""Project-scoped elements API (轮 2)。
端点形态与全局元素库相同，只是 scope 是 project:{pid}。
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import load_settings
from services import elements_repo as repo


router = APIRouter()


class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None


class ElementUpload(BaseModel):
    folder_id: Optional[int] = None
    name: str = ""
    filename: str = ""
    mime: str = "image/png"
    data: str
    source: str = "upload"
    source_meta: Optional[dict] = None
    width: Optional[int] = None
    height: Optional[int] = None


class ElementUpdate(BaseModel):
    name: Optional[str] = None
    folder_id: Optional[int] = None


def _scope_for(pid: str) -> str:
    return f"project:{pid}"


def _verify_project(pid: str) -> None:
    pdir = Path(load_settings().projects_dir) / pid
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="project not found")
    from services.project_migrate import ensure_migrated
    ensure_migrated(pid)


@router.get("/folders")
async def list_folders(project_id: str):
    _verify_project(project_id)
    return {"folders": repo.list_folders(_scope_for(project_id))}


@router.post("/folders")
async def create_folder(project_id: str, req: FolderCreate):
    _verify_project(project_id)
    try:
        return repo.create_folder(_scope_for(project_id), req.name, req.parent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/folders/{folder_id}")
async def update_folder(project_id: str, folder_id: int, req: FolderUpdate):
    _verify_project(project_id)
    scope = _scope_for(project_id)
    try:
        out = None
        if req.name is not None:
            out = repo.rename_folder(scope, folder_id, req.name)
        if "parent_id" in req.model_fields_set:
            out = repo.move_folder(scope, folder_id, req.parent_id)
        return out or {"ok": True}
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(project_id: str, folder_id: int, cascade: bool = True):
    _verify_project(project_id)
    try:
        repo.delete_folder(_scope_for(project_id), folder_id, cascade=cascade)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/")
async def list_elements(project_id: str, folder_id: Optional[int] = None,
                         recursive: bool = False, limit: int = 500):
    _verify_project(project_id)
    return {"elements": repo.list_elements(
        _scope_for(project_id), folder_id=folder_id, recursive=recursive, limit=limit,
    )}


@router.post("/")
async def upload_element(project_id: str, req: ElementUpload):
    _verify_project(project_id)
    try:
        data = base64.b64decode(req.data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad base64: {e}")
    try:
        return repo.create_element(
            _scope_for(project_id),
            folder_id=req.folder_id, name=req.name,
            file_bytes=data, filename=req.filename or req.name or "element.png",
            mime=req.mime, source=req.source,
            source_meta=req.source_meta,
            width=req.width, height=req.height,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"folder not found: {e}")


@router.get("/{element_id}")
async def get_element(project_id: str, element_id: int):
    _verify_project(project_id)
    elem = repo.get_element(_scope_for(project_id), element_id)
    if elem is None:
        raise HTTPException(status_code=404, detail="element not found")
    return elem


@router.put("/{element_id}")
async def update_element(project_id: str, element_id: int, req: ElementUpdate):
    _verify_project(project_id)
    scope = _scope_for(project_id)
    try:
        if "folder_id" in req.model_fields_set:
            return repo.update_element(scope, element_id,
                                        name=req.name, folder_id=req.folder_id)
        return repo.update_element(scope, element_id, name=req.name)
    except KeyError:
        raise HTTPException(status_code=404, detail="element or folder not found")


@router.delete("/{element_id}", status_code=204)
async def delete_element(project_id: str, element_id: int):
    _verify_project(project_id)
    repo.delete_element(_scope_for(project_id), element_id)


@router.get("/file/{element_id}")
async def serve_element_file(project_id: str, element_id: int):
    _verify_project(project_id)
    elem = repo.get_element(_scope_for(project_id), element_id)
    if elem is None:
        raise HTTPException(status_code=404, detail="element not found")
    proot = Path(load_settings().projects_dir) / project_id / "elements"
    full = proot / elem["file_path"]
    if not full.is_file():
        raise HTTPException(status_code=404, detail="file missing on disk")
    mime = elem.get("mime") or mimetypes.guess_type(full.name)[0] or "application/octet-stream"
    return FileResponse(full, media_type=mime, filename=Path(elem["name"]).name or full.name)


@router.post("/ensure-local")
async def ensure_local_folder(project_id: str):
    _verify_project(project_id)
    fid = repo.ensure_local_folder(_scope_for(project_id))
    return {"folder_id": fid}
