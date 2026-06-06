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


@router.put("/{project_id}/images/slot")
async def save_image_slot(project_id: str, slot: ImageSlot):
    """Save a single image slot file to disk (does not touch images.json)."""
    proj_dir = _project_dir(project_id)
    img_dir  = proj_dir / "images"
    img_dir.mkdir(exist_ok=True)
    filename = f"{slot.scene_id}_{slot.frame_type}_{slot.slot_index}.png"
    (img_dir / filename).write_bytes(base64.b64decode(slot.data))
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
    proj_dir = _project_dir(project_id)
    (proj_dir / "scenes.json").write_text(
        json.dumps({"scenes": data.scenes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
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
    existing[payload.key] = _persist_audio_entry(payload.key, payload.entry, audio_dir)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "key": payload.key, "file": existing[payload.key].get("file")}


# ── Videos ─────────────────────────────────────────────────────────────────────

class VideoSlot(BaseModel):
    scene_id: str
    data: str  # base64 mp4


@router.get("/{project_id}/videos")
async def load_videos(project_id: str):
    proj_dir = _project_dir(project_id)
    vid_dir = proj_dir / "video"
    meta_path = proj_dir / "videos.json"
    if not meta_path.exists():
        return {}
    metadata = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    result = {}
    for scene_id, filename in metadata.items():
        vid_path = vid_dir / filename
        if vid_path.exists():
            result[scene_id] = base64.b64encode(vid_path.read_bytes()).decode("ascii")
    return result


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
    _read_meta(project_id)
    (_project_dir(project_id) / "characters.json").write_text(
        json.dumps({"characters": data.characters}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True, "count": len(data.characters)}

