"""Elements API（轮 2）。

提供两个 scope（全局 + 项目级）共用同一套端点设计，差别在 URL 前缀：

- 全局：       /api/elements/...
- 项目级：    /api/projects/{project_id}/elements/...

文件下载用通用 file endpoint：
    /api/elements/file/{element_id}
    /api/projects/{project_id}/elements/file/{element_id}
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services import elements_repo as repo
from services.db import global_elements_root


router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None  # 改父级（移动）


class ElementUpload(BaseModel):
    folder_id: Optional[int] = None
    name: str = ""
    filename: str = ""
    mime: str = "image/png"
    data: str                                  # base64
    source: str = "upload"                     # upload | t2i | imported
    source_meta: Optional[dict] = None
    width: Optional[int] = None
    height: Optional[int] = None


class ElementUpdate(BaseModel):
    name: Optional[str] = None
    folder_id: Optional[int] = None            # 移动到该文件夹；None 表示根


class ElementCopy(BaseModel):
    """v1.5.0: 跨库复制。target_scope 形如 'global' 或 'project:{pid}'。"""
    target_scope: str
    target_folder_id: Optional[int] = None


# ── Folders ───────────────────────────────────────────────────────────────────


def _make_folder_routes(scope_fn):
    """工厂：根据 scope_fn 注册 folder + element 路由。
    scope_fn(request_path_params) -> scope string"""
    pass   # 实际上每个 scope 我们直接显式写两套——比 factory 容易看


def _scope_global(_=None) -> str:
    return "global"


# ── Global scope endpoints ────────────────────────────────────────────────────


@router.get("/folders")
async def list_folders_global():
    return {"folders": repo.list_folders(_scope_global())}


@router.post("/folders")
async def create_folder_global(req: FolderCreate):
    try:
        return repo.create_folder(_scope_global(), req.name, req.parent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/folders/{folder_id}")
async def update_folder_global(folder_id: int, req: FolderUpdate):
    try:
        out = None
        if req.name is not None:
            out = repo.rename_folder(_scope_global(), folder_id, req.name)
        if req.parent_id is not None or "parent_id" in req.model_fields_set:
            out = repo.move_folder(_scope_global(), folder_id, req.parent_id)
        return out or {"ok": True}
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder_global(folder_id: int, cascade: bool = True):
    try:
        repo.delete_folder(_scope_global(), folder_id, cascade=cascade)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/")
async def list_elements_global(folder_id: Optional[int] = None,
                                recursive: bool = False, limit: int = 500):
    return {"elements": repo.list_elements(
        _scope_global(), folder_id=folder_id, recursive=recursive, limit=limit
    )}


@router.post("/")
async def upload_element_global(req: ElementUpload):
    try:
        data = base64.b64decode(req.data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad base64: {e}")
    try:
        return repo.create_element(
            _scope_global(),
            folder_id=req.folder_id,
            name=req.name,
            file_bytes=data,
            filename=req.filename or req.name or "element.png",
            mime=req.mime, source=req.source,
            source_meta=req.source_meta,
            width=req.width, height=req.height,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"folder not found: {e}")


@router.get("/{element_id}")
async def get_element_global(element_id: int):
    elem = repo.get_element(_scope_global(), element_id)
    if elem is None:
        raise HTTPException(status_code=404, detail="element not found")
    return elem


@router.put("/{element_id}")
async def update_element_global(element_id: int, req: ElementUpdate):
    try:
        # folder_id 可以显式设 None（移到根），也可以省略不动；用 model_fields_set 判断
        if "folder_id" in req.model_fields_set:
            return repo.update_element(
                _scope_global(), element_id,
                name=req.name, folder_id=req.folder_id,
            )
        return repo.update_element(_scope_global(), element_id, name=req.name)
    except KeyError:
        raise HTTPException(status_code=404, detail="element or folder not found")


@router.delete("/{element_id}", status_code=204)
async def delete_element_global(element_id: int):
    repo.delete_element(_scope_global(), element_id)


@router.post("/{element_id}/copy")
async def copy_element_global(element_id: int, req: ElementCopy):
    """把全局库元素复制到 target_scope（全局 / 任意项目）。"""
    try:
        return repo.copy_element(
            _scope_global(), element_id, req.target_scope,
            dst_folder_id=req.target_folder_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="element not found")
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/file/{element_id}")
async def serve_element_file_global(element_id: int):
    elem = repo.get_element(_scope_global(), element_id)
    if elem is None:
        raise HTTPException(status_code=404, detail="element not found")
    full = global_elements_root() / elem["file_path"]
    if not full.is_file():
        raise HTTPException(status_code=404, detail="file missing on disk")
    mime = elem.get("mime") or mimetypes.guess_type(full.name)[0] or "application/octet-stream"
    return FileResponse(full, media_type=mime, filename=Path(elem["name"]).name or full.name)


@router.post("/ensure-local")
async def ensure_local_folder_global():
    """创建 / 取回'local'根文件夹（本地上传默认入口）。"""
    fid = repo.ensure_local_folder(_scope_global())
    return {"folder_id": fid}
