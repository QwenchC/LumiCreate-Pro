import base64
import json
import os
import re
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
    has_final_video: bool = False
    folder_id: str = "default"


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    folder_id: str = "default"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _projects_root() -> Path:
    return Path(load_settings().projects_dir)


def _project_dir(project_id: str) -> Path:
    return _projects_root() / project_id


def _read_meta(project_id: str) -> ProjectMeta:
    meta_file = _project_dir(project_id) / "project.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectMeta(**json.loads(meta_file.read_text(encoding="utf-8-sig")))


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
                    meta = ProjectMeta(**json.loads(meta_file.read_text(encoding="utf-8-sig")))
                    meta.has_final_video = (entry / "video" / "final_video.mp4").exists()
                    projects.append(meta)
                except Exception:
                    pass
    projects.sort(key=lambda p: p.updated_at, reverse=True)
    return projects


@router.post("", response_model=ProjectMeta, status_code=201)
async def create_project(req: CreateProjectRequest):
    now = datetime.now(timezone.utc).isoformat()
    project_id = f"proj_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    meta = ProjectMeta(id=project_id, name=req.name, description=req.description,
                       created_at=now, updated_at=now, folder_id=req.folder_id)
    _write_meta(meta)
    # Create subdirectories
    for sub in ("images", "audio", "video", "cache"):
        (_project_dir(project_id) / sub).mkdir(parents=True, exist_ok=True)
    return meta


@router.get("/{project_id}", response_model=ProjectMeta)
async def get_project(project_id: str):
    meta = _read_meta(project_id)
    meta.has_final_video = (_project_dir(project_id) / "video" / "final_video.mp4").exists()
    return meta


# ── Copy config from another project ──────────────────────────────────────────

class CopyConfigRequest(BaseModel):
    source_project_id: str

@router.post("/{project_id}/copy-config", status_code=204)
async def copy_config_from_project(project_id: str, req: CopyConfigRequest):
    """Copy manuscript_config.json and characters.json from source to target project."""
    _read_meta(project_id)
    src_dir = _project_dir(req.source_project_id)
    dst_dir = _project_dir(project_id)
    for filename in ("manuscript_config.json", "characters.json"):
        src = src_dir / filename
        if src.exists():
            import shutil as _shutil
            _shutil.copy2(src, dst_dir / filename)



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


# ── D1: 通用资产文件下载 ──────────────────────────────────────────────────────
# 一切按 scene_assets 表查路径 → FileResponse，**前端不再走 base64**
# 路径模板：
#   GET /projects/{id}/assets/file/{scene_id}/{asset_type}                # selected 那张
#   GET /projects/{id}/assets/file/{scene_id}/{asset_type}/{slot_index}   # 指定 slot

from fastapi.responses import FileResponse as _FileResponse


def _asset_file_response(project_id: str, scene_id: str,
                         asset_type: str, slot_index: Optional[int] = None):
    """从 scene_assets 表查相对路径 → 拼绝对路径 → FileResponse。"""
    from services.project_migrate import ensure_migrated
    from services.db import get_conn
    _read_meta(project_id)
    ensure_migrated(project_id)
    conn = get_conn(project_id)
    if slot_index is None:
        row = conn.execute(
            "SELECT file_path, format FROM scene_assets "
            "WHERE scene_id = ? AND asset_type = ? "
            "ORDER BY is_selected DESC, slot_index ASC LIMIT 1",
            (scene_id, asset_type),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT file_path, format FROM scene_assets "
            "WHERE scene_id = ? AND asset_type = ? AND slot_index = ?",
            (scene_id, asset_type, int(slot_index)),
        ).fetchone()
    if row is None or not row["file_path"]:
        raise HTTPException(status_code=404, detail="asset not found")
    full = _project_dir(project_id) / row["file_path"]
    if not full.is_file():
        raise HTTPException(status_code=404, detail=f"asset file missing on disk: {row['file_path']}")
    # 简单 MIME 推断
    mime = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
        "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "ogg": "audio/ogg",
        "mp4": "video/mp4", "srt": "application/x-subrip",
    }.get((row["format"] or "").lower(), "application/octet-stream")
    return _FileResponse(full, media_type=mime, filename=full.name)


@router.get("/{project_id}/assets/file/{scene_id}/{asset_type}")
async def get_asset_file(project_id: str, scene_id: str, asset_type: str):
    return _asset_file_response(project_id, scene_id, asset_type)


@router.get("/{project_id}/assets/file/{scene_id}/{asset_type}/{slot_index}")
async def get_asset_file_slot(project_id: str, scene_id: str,
                               asset_type: str, slot_index: int):
    return _asset_file_response(project_id, scene_id, asset_type, slot_index)


@router.get("/{project_id}/assets")
async def list_assets(project_id: str,
                       scene_id: Optional[str] = None,
                       asset_type: Optional[str] = None):
    """列出某项目（或某镜）的所有资产 — 用于前端 URL 寻址，避免 base64。"""
    from services.project_migrate import ensure_migrated
    from services.db import get_conn
    _read_meta(project_id)
    ensure_migrated(project_id)
    conn = get_conn(project_id)
    parts: list[str] = []
    params: list = []
    if scene_id:
        parts.append("scene_id = ?"); params.append(scene_id)
    if asset_type:
        parts.append("asset_type = ?"); params.append(asset_type)
    where = (" WHERE " + " AND ".join(parts)) if parts else ""
    rows = conn.execute(
        f"SELECT scene_id, asset_type, slot_index, file_path, format, is_selected "
        f"FROM scene_assets{where} ORDER BY scene_id, asset_type, slot_index",
        params,
    ).fetchall()
    items = []
    for r in rows:
        items.append({
            "scene_id":   r["scene_id"],
            "asset_type": r["asset_type"],
            "slot_index": r["slot_index"],
            "file_path":  r["file_path"],
            "format":     r["format"],
            "is_selected": bool(r["is_selected"]),
            "url": f"/api/projects/{project_id}/assets/file/{r['scene_id']}/"
                   f"{r['asset_type']}/{r['slot_index']}",
        })
    return {"assets": items, "count": len(items)}


# ── A1/A2: 状态机 + SQLite 入口 ────────────────────────────────────────────────
# 所有 router 现在可以读 SQLite 拿到结构化状态。前端可调 /status 拿"项目当前在
# 哪个阶段 + 每镜状态"，不再依赖手工维护的 last_run_errors.json 推断。

@router.get("/{project_id}/events")
async def get_project_events(
    project_id: str,
    trace_id: Optional[str] = None,
    task_id:  Optional[str] = None,
    scene_id: Optional[str] = None,
    level:    Optional[str] = None,
    limit:    int = 500,
):
    """E1: 查项目的事件流。可按 trace_id / task_id / scene_id / level 过滤。
    用于"任务回放"——选一次任务的 trace_id 就能看到完整时间线。"""
    _read_meta(project_id)
    try:
        from services.project_migrate import ensure_migrated
        from services.db import get_conn
        ensure_migrated(project_id)
        conn = get_conn(project_id)

        where_parts: list[str] = []
        params: list = []
        if trace_id:
            where_parts.append("trace_id = ?"); params.append(trace_id)
        if task_id:
            where_parts.append("task_id = ?");  params.append(task_id)
        if scene_id:
            where_parts.append("scene_id = ?"); params.append(scene_id)
        if level:
            where_parts.append("level = ?");    params.append(level)
        where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        params.append(int(max(1, min(limit, 5000))))
        rows = conn.execute(
            f"SELECT id, trace_id, task_id, scene_id, level, stage, message, "
            f"       payload_json, ts FROM events{where} "
            f"ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except Exception:
                d["payload"] = {}; d.pop("payload_json", None)
            out.append(d)
        return {"events": out, "count": len(out)}
    except Exception as e:
        return {"events": [], "count": 0, "error": str(e)[:200]}


# 列出最近 N 次 task 的 trace_id（前端可用作"任务回放选择器"）
@router.get("/{project_id}/traces")
async def list_recent_traces(project_id: str, limit: int = 50):
    _read_meta(project_id)
    try:
        from services.project_migrate import ensure_migrated
        from services.db import get_conn
        ensure_migrated(project_id)
        conn = get_conn(project_id)
        rows = conn.execute(
            """
            SELECT trace_id,
                   MIN(ts) AS started,
                   MAX(ts) AS ended,
                   COUNT(*) AS event_count,
                   SUM(CASE WHEN level = 'error' THEN 1 ELSE 0 END) AS error_count,
                   GROUP_CONCAT(DISTINCT stage) AS stages
            FROM events
            WHERE trace_id != '-'
            GROUP BY trace_id
            ORDER BY started DESC
            LIMIT ?
            """,
            (int(max(1, min(limit, 500))),),
        ).fetchall()
        return {"traces": [dict(r) for r in rows]}
    except Exception as e:
        return {"traces": [], "error": str(e)[:200]}


@router.get("/{project_id}/status")
async def get_project_status(project_id: str):
    """A1: 返回项目级状态机视图（项目阶段 + scene 计数 + 资产计数）。"""
    _read_meta(project_id)
    try:
        from services.project_migrate import ensure_migrated
        from services.project_repo    import project_summary, list_scene_status
        ensure_migrated(project_id)
        return {
            "summary": project_summary(project_id),
            "scenes":  list_scene_status(project_id),
        }
    except Exception as e:
        return {"summary": {"project_stage": "unknown", "error": str(e)[:200]},
                "scenes":  []}


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str):
    proj_dir = _project_dir(project_id)
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    # 在删除前抢救出该项目的 scene_id 列表，用于清扫 ComfyUI input/ 目录里残留的
    # lumi_ff_/lumi_lf_/lumi_aud_ 临时文件（视频生成时由 ltx2video._upload_image/_upload_audio 写入）
    scene_ids: list[str] = []
    scenes_path = proj_dir / "scenes.json"
    if scenes_path.exists():
        try:
            scenes_data = json.loads(scenes_path.read_text(encoding="utf-8-sig"))
            for s in (scenes_data.get("scenes") or []):
                sid = s.get("id")
                if sid:
                    scene_ids.append(str(sid))
        except Exception:
            pass

    # A2: 关闭并删除 SQLite 连接（避免 Windows 上 db 被进程占用导致 rmtree 失败）
    try:
        from services.db import drop_project_db
        drop_project_db(project_id)
    except Exception as e:
        print(f"[delete_project] drop_project_db: {e}", flush=True)

    shutil.rmtree(proj_dir)

    # 清扫 ComfyUI input/ 里的临时文件（best-effort，失败不影响项目删除）
    try:
        from services.ltx2video import _resolve_input_dir
        settings = load_settings()
        ve = settings.video_engine
        ie = settings.image_engine
        input_dir = _resolve_input_dir(ve.comfyui_input_dir, ve.workflow_dir or ie.workflow_dir)
        if input_dir and scene_ids:
            cleaned = 0
            ipath = Path(input_dir)
            for sid in scene_ids:
                for stem in (f"lumi_ff_{sid}", f"lumi_lf_{sid}", f"lumi_aud_{sid}"):
                    for ext in (".png", ".wav"):
                        f = ipath / f"{stem}{ext}"
                        if f.is_file():
                            try:
                                f.unlink()
                                cleaned += 1
                            except OSError:
                                pass
            if cleaned:
                print(f"[delete_project {project_id}] cleaned {cleaned} ComfyUI input files",
                      flush=True)
    except Exception as e:
        print(f"[delete_project {project_id}] cleanup warning: {e}", flush=True)


# ── Manuscript ─────────────────────────────────────────────────────────────────

class ManuscriptData(BaseModel):
    content: str
    config: dict = {}


@router.get("/{project_id}/manuscript")
async def get_manuscript(project_id: str):
    _read_meta(project_id)  # validates project exists
    path = _project_dir(project_id) / "manuscript.md"
    cfg_path = _project_dir(project_id) / "manuscript_config.json"
    content = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    config = json.loads(cfg_path.read_text(encoding="utf-8-sig")) if cfg_path.exists() else {}
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


class SlotKey(BaseModel):
    scene_id:   str
    frame_type: str
    slot_index: int


class ImageMetadataUpdate(BaseModel):
    counts:    dict
    selected:  dict
    slot_keys: list[SlotKey] = []


@router.get("/{project_id}/images")
async def load_images(project_id: str):
    proj_dir  = _project_dir(project_id)
    meta_path = proj_dir / "images.json"
    if not meta_path.exists():
        return {"slots": [], "counts": {}, "selected": {}}

    metadata = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    img_dir  = proj_dir / "images"
    slots    = []
    for saved in metadata.get("saved_slots", []):
        img_path = img_dir / saved["filename"]
        if img_path.exists():
            slots.append({
                "scene_id":   saved["scene_id"],
                "frame_type": saved["frame_type"],
                "slot_index": saved["slot_index"],
                "url":  f"/api/projects/{project_id}/images/file/{saved['filename']}",
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


@router.get("/{project_id}/images/file/{filename}")
async def serve_image_file(project_id: str, filename: str):
    """Serve a single PNG image file directly (avoids large base64 JSON payloads)."""
    from fastapi.responses import FileResponse
    # Sanitize filename — only allow safe characters to prevent path traversal
    if not filename.replace('_', '').replace('.', '').replace('-', '').isalnum():
        raise HTTPException(status_code=400, detail="Invalid filename")
    img_path = _project_dir(project_id) / "images" / filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(img_path, media_type="image/png")


def _image_asset_type(frame_type: str) -> str:
    """frame_type → scene_assets.asset_type。v1.6 新增 bg（无角色背景图，供 MSR 多图参考）。"""
    if frame_type == "start":
        return "image_start"
    if frame_type == "bg":
        return "image_bg"
    return "image_end"


@router.put("/{project_id}/images/slot")
async def save_image_slot(project_id: str, slot: ImageSlot):
    """Save a single image slot file to disk + A2 双写到 scene_assets。"""
    proj_dir = _project_dir(project_id)
    img_dir  = proj_dir / "images"
    img_dir.mkdir(exist_ok=True)
    filename = f"{slot.scene_id}_{slot.frame_type}_{slot.slot_index}.png"
    (img_dir / filename).write_bytes(base64.b64decode(slot.data))

    # A2: 登记到 SQLite scene_assets（自动尝试推进 status → image_drafted）
    try:
        from services.project_repo import record_asset
        asset_type = _image_asset_type(slot.frame_type)
        record_asset(
            project_id, slot.scene_id, asset_type,
            slot_index=slot.slot_index,
            file_path=f"images/{filename}",
            format="png",
            is_selected=(slot.slot_index == 0),  # 第一张默认选中
        )
    except Exception as e:
        print(f"[image-slot] record_asset failed: {e}", flush=True)
    return {"ok": True}


@router.put("/{project_id}/images/metadata")
async def save_image_metadata(project_id: str, meta_update: ImageMetadataUpdate):
    """Rebuild images.json from the provided slot_keys list + save counts/selected."""
    proj_dir = _project_dir(project_id)
    img_dir  = proj_dir / "images"
    img_dir.mkdir(exist_ok=True)

    saved_slots = []
    for key in meta_update.slot_keys:
        filename = f"{key.scene_id}_{key.frame_type}_{key.slot_index}.png"
        if (img_dir / filename).exists():
            saved_slots.append({
                "scene_id":   key.scene_id,
                "frame_type": key.frame_type,
                "slot_index": key.slot_index,
                "filename":   filename,
            })

    metadata = {
        "saved_slots": saved_slots,
        "counts":      meta_update.counts,
        "selected":    meta_update.selected,
    }
    (proj_dir / "images.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # A2: 把 selected map 同步到 scene_assets.is_selected
    try:
        from services.db import project_db
        with project_db(project_id) as conn:
            for compound_key, sel_idx in (meta_update.selected or {}).items():
                if ":" not in compound_key:
                    continue
                sid, ft = compound_key.split(":", 1)
                asset_type = _image_asset_type(ft)
                # 先把该镜该 frame_type 全部置 0，再把选中那个置 1
                conn.execute(
                    "UPDATE scene_assets SET is_selected = 0 "
                    "WHERE scene_id = ? AND asset_type = ?",
                    (sid, asset_type),
                )
                conn.execute(
                    "UPDATE scene_assets SET is_selected = 1 "
                    "WHERE scene_id = ? AND asset_type = ? AND slot_index = ?",
                    (sid, asset_type, int(sel_idx)),
                )
    except Exception as e:
        print(f"[image-metadata] sync selected to sqlite failed: {e}", flush=True)

    # Update project progress
    proj_meta = _read_meta(project_id)
    progress = proj_meta.progress.model_dump()
    progress["images"] = 100 if saved_slots else 0
    await update_project(project_id, {"progress": progress})

    return {"ok": True, "saved": len(saved_slots)}


@router.get("/{project_id}/scenes")
async def get_scenes(project_id: str):
    _read_meta(project_id)
    path = _project_dir(project_id) / "scenes.json"
    if not path.exists():
        return {"scenes": []}
    return json.loads(path.read_text(encoding="utf-8-sig"))


@router.put("/{project_id}/scenes", response_model=ProjectMeta)
async def save_scenes(project_id: str, data: ScenesData):
    meta = _read_meta(project_id)
    # A2 双写：JSON + SQLite（SQLite 失败不阻塞）
    try:
        from services.project_repo import save_scenes as repo_save
        repo_save(project_id, data.scenes)
    except Exception as e:
        # 保险：repo 写盘失败时仍写 JSON
        proj_dir = _project_dir(project_id)
        (proj_dir / "scenes.json").write_text(
            json.dumps({"scenes": data.scenes}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[save_scenes] repo failed, JSON-only fallback: {e}", flush=True)
    progress = meta.progress.model_dump()
    progress["scenes"] = 100 if data.scenes else 0
    return await update_project(project_id, {"progress": progress})


# ── Audio ──────────────────────────────────────────────────────────────────────
#
# A3: audio.json 现在仅存"元数据"——base64 数据拆到 audio/<key>.{mp3,wav} 单文件，
# 避免大项目 audio.json 几百 MB。
# Entry 形态有两种：
#   1) Reading（直读）：{data?: <b64>, duration_ms, format?, file?}
#   2) Clip（按对白生成）：{voiceRef, emoRef, ..., slots: [{data?, duration, file?}, ...]}
# 兼容策略：
#   - 老项目 entry 里只有 `data` 字段 → GET 时直接透传；PUT 时检测后拆出来落盘
#   - 新项目 entry 里 `file` 是相对路径（"audio/xxx.mp3"），`data` 不再写入 JSON
#   - GET 时检测到 `file` 即从磁盘读出 base64 拼回返回，前端无须改动

def _audio_dir(proj_dir: Path) -> Path:
    p = proj_dir / "audio"
    p.mkdir(exist_ok=True)
    return p


def _hydrate_audio_entry(entry: dict, audio_dir: Path) -> dict:
    """读路径上的 entry 加上 base64 data（如果当前是 file 模式）。原地修改不影响磁盘。"""
    out = dict(entry)
    f = out.get("file")
    if f and not out.get("data"):
        try:
            out["data"] = base64.b64encode((audio_dir / f).read_bytes()).decode()
        except OSError:
            out["data"] = ""
    # 嵌套 slots
    if isinstance(out.get("slots"), list):
        new_slots = []
        for slot in out["slots"]:
            s = dict(slot) if isinstance(slot, dict) else {}
            sf = s.get("file")
            if sf and not s.get("data"):
                try:
                    s["data"] = base64.b64encode((audio_dir / sf).read_bytes()).decode()
                except OSError:
                    s["data"] = ""
            new_slots.append(s)
        out["slots"] = new_slots
    return out


def _persist_audio_entry(key: str, entry: dict, audio_dir: Path) -> dict:
    """把 entry 里的 base64 data 拆到磁盘，返回不含 base64 的精简 entry。"""
    cleaned = {k: v for k, v in entry.items() if k != "data"}
    raw = entry.get("data")
    if raw:
        ext = ".mp3" if (entry.get("format") or "mp3").lower() == "mp3" else ".wav"
        # 文件名安全化
        safe = re.sub(r"[^A-Za-z0-9_\-]+", "_", key)
        filename = f"{safe}{ext}"
        try:
            (audio_dir / filename).write_bytes(base64.b64decode(raw))
            cleaned["file"] = filename
        except Exception as e:
            print(f"[save_audio] persist {key}: {e}", flush=True)
            cleaned["data"] = raw   # 失败时回退到 base64 in JSON

    if isinstance(entry.get("slots"), list):
        new_slots = []
        for i, slot in enumerate(entry["slots"]):
            if not isinstance(slot, dict):
                new_slots.append(slot); continue
            s = {k: v for k, v in slot.items() if k != "data"}
            sraw = slot.get("data")
            if sraw:
                safe = re.sub(r"[^A-Za-z0-9_\-]+", "_", key)
                # clip 槽位用 wav（IndexTTS / GPT-SoVITS / msedge 转过的都是 wav）
                filename = f"{safe}_v{i}.wav"
                try:
                    (audio_dir / filename).write_bytes(base64.b64decode(sraw))
                    s["file"] = filename
                except Exception as e:
                    print(f"[save_audio] persist {key} slot {i}: {e}", flush=True)
                    s["data"] = sraw
            new_slots.append(s)
        cleaned["slots"] = new_slots
    return cleaned


@router.get("/{project_id}/audio")
async def get_audio(project_id: str):
    _read_meta(project_id)
    proj_dir = _project_dir(project_id)
    path = proj_dir / "audio.json"
    if not path.exists():
        return {}
    raw_data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw_data, dict):
        return raw_data
    audio_dir = _audio_dir(proj_dir)
    return {k: _hydrate_audio_entry(v, audio_dir) if isinstance(v, dict) else v
            for k, v in raw_data.items()}


@router.put("/{project_id}/audio")
async def save_audio(project_id: str, data: dict):
    meta = _read_meta(project_id)
    proj_dir = _project_dir(project_id)
    audio_dir = _audio_dir(proj_dir)

    # A3: 拆 base64 到磁盘，JSON 只存元数据
    persisted: dict = {}
    for key, entry in data.items():
        if not isinstance(entry, dict):
            persisted[key] = entry
            continue
        persisted[key] = _persist_audio_entry(key, entry, audio_dir)

    (proj_dir / "audio.json").write_text(
        json.dumps(persisted, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 进度统计：有 file 或 data 或 slots[*].file/data 之一即视为已完成
    def _entry_has_audio(v: dict) -> bool:
        if v.get("file") or v.get("data"):
            return True
        for s in (v.get("slots") or []):
            if isinstance(s, dict) and (s.get("file") or s.get("data")):
                return True
        return False

    done = sum(1 for v in persisted.values() if isinstance(v, dict) and _entry_has_audio(v))
    progress = meta.progress.model_dump()
    progress["audio"] = 100 if done else 0
    return await update_project(project_id, {"progress": progress})


# A3 增量保存：仅追加/更新单个 entry（避免前端一次 PUT 全量 base64 占带宽）
class AudioSlotPayload(BaseModel):
    key:   str
    entry: dict     # entry 内可包含 data（b64）或 slots[*].data


@router.put("/{project_id}/audio/slot")
async def put_audio_slot(project_id: str, payload: AudioSlotPayload):
    _read_meta(project_id)
    proj_dir = _project_dir(project_id)
    audio_dir = _audio_dir(proj_dir)
    path = proj_dir / "audio.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            existing = {}
    persisted = _persist_audio_entry(payload.key, payload.entry, audio_dir)
    existing[payload.key] = persisted
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    # A2: 双写到 scene_assets — 仅当 key 是 __ms_reading__/__stitched__ 这类带 scene_id 的
    scene_id = ""
    if payload.key.startswith("__ms_reading__"):
        scene_id = payload.key[len("__ms_reading__"):]
    elif payload.key.startswith("__stitched__"):
        scene_id = payload.key[len("__stitched__"):]
    if scene_id:
        try:
            from services.project_repo import record_asset
            record_asset(
                project_id, scene_id, "audio",
                slot_index=0,
                file_path=f"audio/{persisted.get('file', '')}",
                format=persisted.get("format") or "mp3",
                metadata={"duration_ms": persisted.get("duration_ms", 0)},
                is_selected=True,
            )
        except Exception as e:
            print(f"[audio-slot] record_asset failed: {e}", flush=True)
    return {"ok": True, "key": payload.key, "file": persisted.get("file")}


# ── Videos ─────────────────────────────────────────────────────────────────────

class VideoSlot(BaseModel):
    scene_id: str
    data: str  # base64 mp4


@router.get("/{project_id}/videos")
async def load_videos(project_id: str):
    proj_dir = _project_dir(project_id)
    vid_dir = proj_dir / "video"
    meta_path = proj_dir / "videos.json"

    # 1) 现有 videos.json 索引（可能缺失/不全）
    metadata: dict = {}
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        except Exception:
            metadata = {}

    # 2) v1.5.1 自愈：mp4 已在 video/ 目录、scene_assets 也有登记，但 videos.json
    #    缺这条（生成时写盘中断 / 没保存）→ 用 scene_assets 补齐，避免"视频在目录里
    #    但视频生成页不显示、无法点合成"。
    discovered = dict(metadata)
    try:
        from services.project_repo import list_video_assets
        for scene_id, rel in list_video_assets(project_id).items():
            if scene_id in discovered:
                continue
            fn = Path(rel).name
            if (vid_dir / fn).exists():
                discovered[scene_id] = fn
    except Exception:
        pass

    # 3) 只保留盘上确实存在的文件；返回【流式 URL】而非 base64。
    #    关键修复：原来把每个分镜视频 base64 塞进一个 JSON 响应，ComfyUI 高清成片
    #    一个项目可达数百 MB → 单个响应 ~500MB+ → 前端请求失败/超时 → 整页无预览、
    #    无法合成。改为返回每镜的流式地址，<video> 按需懒加载，响应只有几 KB。
    result = {}
    healed: dict = {}
    for scene_id, filename in discovered.items():
        vid_path = vid_dir / filename
        if vid_path.exists():
            result[scene_id] = f"/api/projects/{project_id}/video-file/{scene_id}"
            healed[scene_id] = filename

    # 4) 若补出新键，回写 videos.json 让索引自我修正（下次直接命中、合成也能读到）
    if set(healed) - set(metadata):
        try:
            meta_path.write_text(
                json.dumps(healed, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return result


def _resolve_scene_video_filename(project_id: str, scene_id: str) -> Optional[str]:
    """按 videos.json → scene_assets → {scene_id}.mp4 解析某分镜的视频文件名。"""
    proj_dir = _project_dir(project_id)
    vid_dir = proj_dir / "video"
    meta_path = proj_dir / "videos.json"
    if meta_path.exists():
        try:
            md = json.loads(meta_path.read_text(encoding="utf-8-sig"))
            fn = md.get(scene_id)
            if fn and (vid_dir / fn).is_file():
                return fn
        except Exception:
            pass
    try:
        from services.project_repo import list_video_assets
        rel = list_video_assets(project_id).get(scene_id)
        if rel and (vid_dir / Path(rel).name).is_file():
            return Path(rel).name
    except Exception:
        pass
    cand = f"{scene_id}.mp4"
    if (vid_dir / cand).is_file():
        return cand
    return None


@router.get("/{project_id}/video-file/{scene_id}")
async def get_scene_video_file(project_id: str, scene_id: str):
    """流式返回单个分镜视频（支持 Range，<video> 可拖拽）。替代 base64 整包传输。"""
    filename = _resolve_scene_video_filename(project_id, scene_id)
    if not filename:
        raise HTTPException(status_code=404, detail="该分镜暂无视频")
    full = _project_dir(project_id) / "video" / filename
    if not full.is_file():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    return _FileResponse(full, media_type="video/mp4", filename=full.name)


@router.put("/{project_id}/videos")
async def save_videos(project_id: str, data: list[VideoSlot]):
    proj_dir = _project_dir(project_id)
    vid_dir = proj_dir / "video"
    vid_dir.mkdir(exist_ok=True)

    metadata = {}
    for slot in data:
        filename = f"{slot.scene_id}.mp4"
        (vid_dir / filename).write_bytes(base64.b64decode(slot.data))
        metadata[slot.scene_id] = filename

    (proj_dir / "videos.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    meta = _read_meta(project_id)
    progress = meta.progress.model_dump()
    progress["video"] = 100 if data else 0
    return await update_project(project_id, {"progress": progress})


# A3 增量：单镜视频保存，避免一次 PUT 携带 30+ 个 mp4 base64
@router.put("/{project_id}/videos/slot")
async def put_video_slot(project_id: str, slot: VideoSlot):
    _read_meta(project_id)
    proj_dir = _project_dir(project_id)
    vid_dir = proj_dir / "video"
    vid_dir.mkdir(exist_ok=True)

    filename = f"{slot.scene_id}.mp4"
    (vid_dir / filename).write_bytes(base64.b64decode(slot.data))

    # 合并入 videos.json
    meta_path = proj_dir / "videos.json"
    metadata: dict = {}
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        except Exception:
            metadata = {}
    metadata[slot.scene_id] = filename
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    # A2: 双写 scene_assets（自动推进 → video_ready）
    try:
        from services.project_repo import record_asset
        record_asset(
            project_id, slot.scene_id, "video",
            slot_index=0,
            file_path=f"video/{filename}",
            format="mp4",
            is_selected=True,
        )
    except Exception as e:
        print(f"[video-slot] record_asset failed: {e}", flush=True)
    return {"ok": True, "scene_id": slot.scene_id, "file": filename}


# ── Video prompts ───────────────────────────────────────────────────────────────

@router.get("/{project_id}/video-prompts")
async def load_video_prompts(project_id: str):
    path = _project_dir(project_id) / "video_prompts.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


@router.put("/{project_id}/video-prompts")
async def save_video_prompts(project_id: str, data: dict):
    _read_meta(project_id)
    (_project_dir(project_id) / "video_prompts.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True}


# ── Last-run errors (A1: 让前端能看见/重试上次失败的镜次) ────────────────────
# 文件 schema：
#   { "stage": "images"|"audio"|"video"|"prompts",
#     "ts":    "<ISO8601>",
#     "errors": { "<scene_id>": "<error message>", ... } }
# 前端在批量结束 SSE batch_done 后调 GET 查询；点重试时按 errors 的 scene_id
# 重发批量请求。
#
# 后端 service 也可以 import write_last_run_errors() 把 SSE 期间收集的错误
# 持久化下来（同步写入）。


class LastRunErrors(BaseModel):
    stage:  str = ""
    ts:     str = ""
    errors: dict = {}


def _last_run_errors_path(project_id: str) -> Path:
    return _project_dir(project_id) / "last_run_errors.json"


def write_last_run_errors(project_id: str, stage: str, errors: dict) -> None:
    """Service-layer 用：批量任务结束时写入失败 scene 集合。"""
    proj_dir = _project_dir(project_id)
    if not proj_dir.exists():
        return
    data = {
        "stage":  stage,
        "ts":     datetime.now(timezone.utc).isoformat(),
        "errors": {str(k): str(v)[:500] for k, v in (errors or {}).items()},
    }
    _last_run_errors_path(project_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@router.get("/{project_id}/last-run-errors")
async def get_last_run_errors(project_id: str):
    _read_meta(project_id)
    p = _last_run_errors_path(project_id)
    if not p.exists():
        return {"stage": "", "ts": "", "errors": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"stage": "", "ts": "", "errors": {}}


@router.put("/{project_id}/last-run-errors")
async def put_last_run_errors(project_id: str, data: LastRunErrors):
    _read_meta(project_id)
    payload = {
        "stage":  data.stage,
        "ts":     data.ts or datetime.now(timezone.utc).isoformat(),
        "errors": {str(k): str(v)[:500] for k, v in (data.errors or {}).items()},
    }
    _last_run_errors_path(project_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True, "count": len(payload["errors"])}


@router.delete("/{project_id}/last-run-errors", status_code=204)
async def clear_last_run_errors(project_id: str):
    _read_meta(project_id)
    p = _last_run_errors_path(project_id)
    if p.exists():
        p.unlink()


# ── Characters ─────────────────────────────────────────────────────────────────
# Stored separately from manuscript_config so the user can enrich character
# visual descriptions independently of the generation config.

class CharactersData(BaseModel):
    characters: list  # [{name, role, traits, appearance, ...}]


@router.get("/{project_id}/characters")
async def get_characters(project_id: str):
    _read_meta(project_id)
    path = _project_dir(project_id) / "characters.json"
    if not path.exists():
        # Fall back to characters stored in manuscript_config
        cfg_path = _project_dir(project_id) / "manuscript_config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            chars = cfg.get("characters", [])
            # Migrate: add empty appearance field if missing
            for c in chars:
                c.setdefault("appearance", "")
            return {"characters": chars}
        return {"characters": []}
    return json.loads(path.read_text(encoding="utf-8-sig"))


@router.put("/{project_id}/characters")
async def save_characters(project_id: str, data: CharactersData):
    """保存角色列表。

    v1.5.1 修复：立绘元数据（portraits）由专用立绘端点维护；本接口做"载入合并保存"——
    客户端若未带 portraits（角色页保存只发基本字段），按角色名保留磁盘上已有的 portraits，
    避免一次角色保存把立绘元数据整段抹掉（PNG 还在盘上但 characters.json 不再引用 →
    重开项目立绘消失）。同时丢弃前端运行期缓存键 `_portraits`，不落盘。
    """
    _read_meta(project_id)
    existing = _load_characters_list(project_id)
    old_portraits = {
        (c.get("name") or "").strip(): c["portraits"]
        for c in existing
        if isinstance(c.get("portraits"), list)
    }
    merged: list[dict] = []
    for raw in data.characters:
        c = dict(raw)
        c.pop("_portraits", None)          # 运行期缓存键，不持久化
        name = (c.get("name") or "").strip()
        if not isinstance(c.get("portraits"), list):
            # 客户端没带 portraits → 保留磁盘上已有的（立绘不丢）
            if name in old_portraits:
                c["portraits"] = old_portraits[name]
        merged.append(c)
    _save_characters_list(project_id, merged)
    return {"ok": True, "count": len(merged)}


# ── 角色立绘 (轮 4) ────────────────────────────────────────────────────────────
#
# 每个角色可有多张立绘，每张立绘存盘到 <项目>/characters/{safe_name}/portrait_N.png
# 元数据写入 characters.json 该角色对象的 `portraits` 字段：
#   portraits: [
#     {
#       filename: "portrait_1.png",
#       workflow_name: "t2i-lumicreate",
#       prompt: "<英文 prompt>",
#       created_at: "...",
#       is_primary: true   // 主立绘，用于角色一致性参考的默认头像
#     }, ...
#   ]


_PORTRAIT_NAME_RE = re.compile(r"[^A-Za-z0-9_\-一-龥]+")


def _safe_character_dirname(name: str) -> str:
    """角色名转安全目录名（保留中文 + 字母数字）。"""
    n = _PORTRAIT_NAME_RE.sub("_", (name or "").strip())
    return n or "_char"


def _characters_dir(project_id: str, char_name: str) -> Path:
    return _project_dir(project_id) / "characters" / _safe_character_dirname(char_name)


def _load_characters_list(project_id: str) -> list[dict]:
    path = _project_dir(project_id) / "characters.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return list(data.get("characters") or [])
    except Exception:
        return []


def _save_characters_list(project_id: str, chars: list[dict]) -> None:
    (_project_dir(project_id) / "characters.json").write_text(
        json.dumps({"characters": chars}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _find_character(chars: list[dict], name: str) -> Optional[dict]:
    for c in chars:
        if (c.get("name") or "").strip() == (name or "").strip():
            return c
    return None


class PortraitUploadRequest(BaseModel):
    data:          str             # base64 PNG (前端已生成的图)
    workflow_name: str = ""        # 来源工作流（记录用）
    prompt:        str = ""        # 生成时的 prompt（记录用）
    set_primary:   bool = False    # 上传后立刻设为主立绘
    white_bg:      bool = False     # v1.6: 纯白背景立绘（供 MSR 多图参考视频用）


from fastapi.responses import FileResponse  # noqa: E402

@router.post("/{project_id}/characters/{char_name}/portraits")
async def add_character_portrait(project_id: str, char_name: str,
                                  req: PortraitUploadRequest):
    """角色立绘上传：前端拿到图（自己调 image-engine 生成或本地选）后调本接口。
    返回 {filename, file_path, url} 立刻可用。"""
    _read_meta(project_id)
    cdir = _characters_dir(project_id, char_name)
    cdir.mkdir(parents=True, exist_ok=True)

    # 找下个可用编号
    n = 1
    while (cdir / f"portrait_{n}.png").exists():
        n += 1
    filename = f"portrait_{n}.png"
    full = cdir / filename
    try:
        full.write_bytes(base64.b64decode(req.data))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad base64: {e}")

    # 更新 characters.json
    chars = _load_characters_list(project_id)
    char = _find_character(chars, char_name)
    if char is None:
        # 角色不存在则即时新建一个空角色
        char = {"name": char_name, "role": "", "traits": "",
                "appearance": "", "negative": "", "voice": "", "portraits": []}
        chars.append(char)

    char.setdefault("portraits", [])
    now = datetime.now(timezone.utc).isoformat()
    new_entry = {
        "filename":      filename,
        "workflow_name": req.workflow_name or "",
        "prompt":        req.prompt or "",
        "created_at":    now,
        "is_primary":    bool(req.set_primary),
        "white_bg":      bool(req.white_bg),   # v1.6: 纯白背景立绘标记
    }
    # 若设主，把别的清掉
    if req.set_primary:
        for p in char["portraits"]:
            p["is_primary"] = False
    elif not any(p.get("is_primary") for p in char["portraits"]):
        # 没有任何主图时第一张自动设主
        new_entry["is_primary"] = True
    char["portraits"].append(new_entry)
    _save_characters_list(project_id, chars)

    rel = f"characters/{_safe_character_dirname(char_name)}/{filename}"
    return {
        "filename":  filename,
        "file_path": rel,
        "url":       f"/api/projects/{project_id}/characters/{char_name}/portraits/file/{filename}",
        "is_primary": new_entry["is_primary"],
        "created_at": now,
    }


@router.get("/{project_id}/characters/{char_name}/portraits")
async def list_character_portraits(project_id: str, char_name: str):
    _read_meta(project_id)
    chars = _load_characters_list(project_id)
    char = _find_character(chars, char_name)
    if char is None:
        return {"portraits": []}
    cdir = _characters_dir(project_id, char_name)
    out = []
    for p in (char.get("portraits") or []):
        fn = p.get("filename")
        if not fn:
            continue
        out.append({
            **p,
            "url": f"/api/projects/{project_id}/characters/{char_name}/portraits/file/{fn}",
            "exists_on_disk": (cdir / fn).exists(),
        })
    return {"portraits": out}


@router.delete("/{project_id}/characters/{char_name}/portraits/{filename}",
               status_code=204)
async def delete_character_portrait(project_id: str, char_name: str, filename: str):
    _read_meta(project_id)
    # 名字安全：不允许路径穿越
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="bad filename")
    cdir = _characters_dir(project_id, char_name)
    fp = cdir / filename
    fp.unlink(missing_ok=True)

    chars = _load_characters_list(project_id)
    char = _find_character(chars, char_name)
    if char is not None:
        before = char.get("portraits") or []
        after  = [p for p in before if p.get("filename") != filename]
        # 若刚删的是主图且还剩别的，把剩下第一张提升为主图
        if any(p.get("filename") == filename and p.get("is_primary") for p in before):
            if after and not any(p.get("is_primary") for p in after):
                after[0]["is_primary"] = True
        char["portraits"] = after
        _save_characters_list(project_id, chars)


@router.put("/{project_id}/characters/{char_name}/portraits/{filename}/select")
async def set_primary_portrait(project_id: str, char_name: str, filename: str):
    """把指定立绘设为主图（用作"角色头像 / 一致性参考")。"""
    _read_meta(project_id)
    chars = _load_characters_list(project_id)
    char = _find_character(chars, char_name)
    if char is None or not (char.get("portraits") or []):
        raise HTTPException(status_code=404, detail="character or portraits not found")
    found = False
    for p in char["portraits"]:
        if p.get("filename") == filename:
            p["is_primary"] = True
            found = True
        else:
            p["is_primary"] = False
    if not found:
        raise HTTPException(status_code=404, detail="portrait not found")
    _save_characters_list(project_id, chars)
    return {"ok": True}


@router.get("/{project_id}/characters/{char_name}/portraits/file/{filename}")
async def serve_character_portrait(project_id: str, char_name: str, filename: str):
    _read_meta(project_id)
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="bad filename")
    full = _characters_dir(project_id, char_name) / filename
    if not full.is_file():
        raise HTTPException(status_code=404, detail="portrait file missing")
    return FileResponse(full, media_type="image/png", filename=filename)

