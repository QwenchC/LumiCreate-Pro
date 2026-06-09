"""v1.4.8 音效（SFX）通路。

漫剧叙事强烈依赖点状音效（脚步、关门、抽刀）。本模块在 music 模块之外
单独维护一个 SFX 库 + 项目级 SFX 时间轴：

  - 全局 SFX 库：用户上传的 ≤ 几秒短音效；元数据 SQLite + 文件 APPDATA/sfx/
  - 项目时间轴：<project>/sfx_timeline.json — 每镜次 N 个 [offset_ms, sfx_id, volume_db]
  - 渲染集成：slideshow_video.build_scene_clip_cmd 接 sfx_overlays 列表 → ffmpeg
    多输入 + adelay+volume+amix 直接烧进镜次 mp4

设计取舍：
  - 不预置 SFX 种子（用户上传），避开版权风险
  - MVP 仅 slideshow 通路；LTX 用户暂不接（要重新跑视频生成）
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import load_settings
from services.db import get_global_sfx_conn, global_sfx_root


router = APIRouter()


ALLOWED_SFX_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}
_MIN_PLAYABLE_BYTES = 256   # 256B 以下八成是损坏


def _safe_filename(name: str) -> str:
    bad = '<>:"|?*\x00/\\'
    out = "".join(c for c in (name or "") if c not in bad).strip()
    return out or "sfx"


def _row_dict(row) -> dict:
    return {
        "id":           int(row["id"]),
        "name":         row["name"],
        "category":     row["category"],
        "file_path":    row["file_path"],
        "mime":         row["mime"],
        "duration_ms":  int(row["duration_ms"]),
        "tags":         row["tags"],
        "bytes":        int(row["bytes"]),
        "created_at":   row["created_at"],
        "url":          f"/api/sfx/file/{int(row['id'])}",
    }


def _is_playable(file_path: str) -> bool:
    if not file_path: return False
    p = global_sfx_root() / file_path
    try:
        return p.is_file() and p.stat().st_size >= _MIN_PLAYABLE_BYTES
    except OSError:
        return False


def _ffprobe_duration_ms(audio_path: Path) -> int:
    """无 ffprobe 也不致命，返回 0 让前端"未知时长"显示。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, timeout=15,
        )
        if out.returncode == 0:
            return int(float((out.stdout or b"").decode().strip() or "0") * 1000)
    except Exception:
        pass
    return 0


# ── Schemas ────────────────────────────────────────────────────────────────────


class SfxUploadRequest(BaseModel):
    filename: str = Field(..., description="原始文件名（取后缀用）")
    name:     str = Field("", description="显示名；空则用文件名前缀")
    category: str = Field("uncategorized")
    tags:     str = Field("")
    data:     str = Field(..., description="base64 音频内容")


class SfxUpdate(BaseModel):
    name:     Optional[str] = None
    category: Optional[str] = None
    tags:     Optional[str] = None


# ── 库 CRUD ────────────────────────────────────────────────────────────────────


@router.get("/categories")
async def list_categories():
    """所有已存在分类的去重列表（按字母排序）。"""
    conn = get_global_sfx_conn()
    rows = conn.execute(
        "SELECT DISTINCT category FROM sfx_clips ORDER BY category"
    ).fetchall()
    return {"categories": [r["category"] for r in rows if r["category"]]}


@router.get("/list")
async def list_sfx(category: str = "", limit: int = 500):
    conn = get_global_sfx_conn()
    limit = max(1, min(int(limit), 2000))
    if category:
        rows = conn.execute(
            "SELECT * FROM sfx_clips WHERE category = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (category, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sfx_clips ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"items": [_row_dict(r) for r in rows if _is_playable(r["file_path"])]}


@router.post("/upload")
async def upload_sfx(req: SfxUploadRequest):
    ext = Path(req.filename or "").suffix.lower()
    if ext not in ALLOWED_SFX_EXT:
        raise HTTPException(400, detail=f"不支持的格式: {ext}")
    try:
        blob = base64.b64decode(req.data)
    except Exception as e:
        raise HTTPException(400, detail=f"base64 解码失败: {e}")
    if len(blob) < _MIN_PLAYABLE_BYTES:
        raise HTTPException(400, detail=f"文件太小（{len(blob)} bytes），疑似损坏")

    name = (req.name or Path(req.filename).stem)[:200].strip() or "sfx"
    category = _safe_filename(req.category or "uncategorized")[:80] or "uncategorized"

    root = global_sfx_root()
    # 按 category 分目录，文件名加时间戳避免冲突
    cat_dir = root / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    fname = f"{_safe_filename(name)[:60]}_{stamp}{ext}"
    abs_path = cat_dir / fname
    abs_path.write_bytes(blob)
    rel_path = f"{category}/{fname}"

    mime = {
        ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
        ".wav": "audio/wav",  ".ogg": "audio/ogg", ".flac": "audio/flac",
    }.get(ext, "application/octet-stream")
    duration_ms = _ffprobe_duration_ms(abs_path)

    now = datetime.now(timezone.utc).isoformat()
    conn = get_global_sfx_conn()
    cur = conn.execute(
        "INSERT INTO sfx_clips(name, category, file_path, mime, duration_ms, "
        "tags, bytes, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (name, category, rel_path, mime, duration_ms,
         (req.tags or "")[:500], len(blob), now),
    )
    conn.commit()
    new_id = cur.lastrowid
    row = conn.execute("SELECT * FROM sfx_clips WHERE id=?", (new_id,)).fetchone()
    return _row_dict(row)


@router.get("/file/{sfx_id}")
async def get_sfx_file(sfx_id: int):
    conn = get_global_sfx_conn()
    row = conn.execute("SELECT file_path, mime FROM sfx_clips WHERE id=?",
                       (sfx_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail="SFX not found")
    abs_path = global_sfx_root() / row["file_path"]
    if not abs_path.is_file():
        raise HTTPException(404, detail="SFX file missing")
    return FileResponse(abs_path, media_type=row["mime"], filename=abs_path.name)


@router.put("/clip/{sfx_id}")
async def update_sfx(sfx_id: int, payload: SfxUpdate):
    conn = get_global_sfx_conn()
    row = conn.execute("SELECT id FROM sfx_clips WHERE id=?", (sfx_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail="SFX not found")
    fields, values = [], []
    if payload.name is not None:
        fields.append("name = ?"); values.append(payload.name.strip()[:200] or "sfx")
    if payload.category is not None:
        fields.append("category = ?")
        values.append(_safe_filename(payload.category)[:80] or "uncategorized")
    if payload.tags is not None:
        fields.append("tags = ?"); values.append(payload.tags[:500])
    if fields:
        values.append(sfx_id)
        conn.execute(f"UPDATE sfx_clips SET {', '.join(fields)} WHERE id=?", values)
        conn.commit()
    row = conn.execute("SELECT * FROM sfx_clips WHERE id=?", (sfx_id,)).fetchone()
    return _row_dict(row)


@router.delete("/clip/{sfx_id}", status_code=204)
async def delete_sfx(sfx_id: int):
    conn = get_global_sfx_conn()
    row = conn.execute("SELECT file_path FROM sfx_clips WHERE id=?",
                       (sfx_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail="SFX not found")
    abs_path = global_sfx_root() / row["file_path"]
    abs_path.unlink(missing_ok=True)
    conn.execute("DELETE FROM sfx_clips WHERE id=?", (sfx_id,))
    conn.commit()


# ── 项目时间轴 ────────────────────────────────────────────────────────────────


class SfxOverlay(BaseModel):
    sfx_id:     int
    offset_ms:  int = Field(0, ge=0)        # 从镜次起点起算
    volume_db:  float = Field(0.0, ge=-40, le=20)


class SfxTimelineUpdate(BaseModel):
    timeline: dict[str, list[SfxOverlay]]   # {scene_id: [overlay, ...]}


def _timeline_path(project_id: str) -> Path:
    cfg = load_settings()
    return Path(cfg.projects_dir) / project_id / "sfx_timeline.json"


@router.get("/timeline/{project_id}")
async def get_timeline(project_id: str):
    p = _timeline_path(project_id)
    if not p.exists():
        return {"timeline": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        # 防御：确保是 dict[str, list]
        if not isinstance(data, dict):
            return {"timeline": {}}
        return {"timeline": data}
    except Exception:
        return {"timeline": {}}


@router.put("/timeline/{project_id}")
async def put_timeline(project_id: str, req: SfxTimelineUpdate):
    cfg = load_settings()
    proj_dir = Path(cfg.projects_dir) / project_id
    if not proj_dir.is_dir():
        raise HTTPException(404, detail="项目不存在")
    p = _timeline_path(project_id)
    # 序列化为纯 dict（pydantic v2 → model_dump）
    serial = {
        sid: [ov.model_dump() for ov in items]
        for sid, items in (req.timeline or {}).items()
    }
    p.write_text(json.dumps(serial, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return {"ok": True, "scenes": list(serial.keys())}
