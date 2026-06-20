"""Music generation router (ACE-Step v1.5).

Endpoints:
  GET  /api/music/workflows                 — list supported music workflows (bundled)
  POST /api/music/generate-stream           — SSE generate, auto-persist on completed
  GET  /api/music/tracks?project_id=…       — list tracks (filter by project optionally)
  GET  /api/music/track/{id}                — track metadata
  GET  /api/music/file/{id}                 — stream the MP3 file
  DELETE /api/music/track/{id}              — delete (DB + file)
"""
from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from config import load_settings
from services.comfyui import (
    bundled_workflow_dir, get_workflow_json, list_workflows,
)
from services.db import get_global_music_conn, global_music_root


router = APIRouter()


# ── 支持的音乐工作流硬名单（与 image/video 同一思路）─────────────────────────

SUPPORTED_MUSIC_WORKFLOWS: frozenset = frozenset({
    "audio_ace_step_1_5_split_4b",
})


def _safe_filename(name: str) -> str:
    bad = '<>:"|?*\x00/\\'
    out = "".join(c for c in (name or "") if c not in bad).strip()
    return out or "track"


def _library_key(project_id: str) -> str:
    """v1.6.2: 音乐库归属键。系列项目 → 'series:{sid}'（各集共用一份音乐库）；
    独立项目 → 原样 project_id。空 project_id 原样返回（仅入全局库）。"""
    pid = (project_id or "").strip()
    if not pid:
        return ""
    try:
        f = Path(load_settings().projects_dir) / pid / "project.json"
        if f.exists():
            sid = json.loads(f.read_text(encoding="utf-8-sig")).get("series_id") or ""
            if sid:
                return f"series:{sid}"
    except Exception:
        pass
    return pid


# ── Schemas ────────────────────────────────────────────────────────────────────


class MusicGenerateRequest(BaseModel):
    workflow_name:    str = "audio_ace_step_1_5_split_4b"
    duration_seconds: int = 60
    bpm:              int = 120
    time_signature:   str = "4"
    language:         str = "zh"
    key_scale:        str = "C major"
    tags:             str = ""
    lyrics:           str = ""
    name:             str = ""            # 用户给生成结果起的名字
    project_id:       str = ""            # 可选；空 = 仅入全局库
    seed:             Optional[int] = None    # None ⇒ 后端随机；显式数 ⇒ 复现


class TrackUpdate(BaseModel):
    name: Optional[str] = None


# ── Workflow listing ──────────────────────────────────────────────────────────


@router.get("/workflows", response_model=list[str])
async def get_music_workflows():
    """与 image/video 一样：bundled 扫描 + 硬名单双门控。"""
    bundled = bundled_workflow_dir()
    if bundled is None:
        # 仓库结构异常兜底
        cfg = load_settings().image_engine
        names = await list_workflows(cfg)
    else:
        names = [p.stem for p in bundled.glob("*.json")]
    return sorted(n for n in names if n in SUPPORTED_MUSIC_WORKFLOWS)


# ── Library ───────────────────────────────────────────────────────────────────


def _track_dict(row) -> dict:
    return {
        "id":              int(row["id"]),
        "name":            row["name"],
        "file_path":       row["file_path"],
        "mime":            row["mime"],
        "project_id":      row["project_id"],
        "seed":            int(row["seed"]),
        "duration_secs":   int(row["duration_secs"]),
        "bpm":             int(row["bpm"]),
        "time_signature":  row["time_signature"],
        "language":        row["language"],
        "key_scale":       row["key_scale"],
        "tags":            row["tags"],
        "lyrics":          row["lyrics"],
        "bytes":           int(row["bytes"]),
        "created_at":      row["created_at"],
        "url":             f"/api/music/file/{int(row['id'])}",
    }


_MIN_PLAYABLE_BYTES = 1024   # 小于 1KB 的 mp3 八成是损坏 / 提交失败留下的空壳


def _is_playable(file_path: str) -> bool:
    """文件存在 + 大小够 1 帧 mp3。"""
    if not file_path:
        return False
    p = global_music_root() / file_path
    try:
        return p.is_file() and p.stat().st_size >= _MIN_PLAYABLE_BYTES
    except OSError:
        return False


@router.get("/tracks")
async def list_tracks(project_id: str = "", limit: int = 200):
    """列举 tracks。**自动过滤文件丢失 / 体积过小的"幽灵"条目**，不返回给前端。
    实际清理 DB 用 /cleanup 端点。"""
    conn = get_global_music_conn()
    limit = max(1, min(int(limit), 1000))
    if project_id:
        key = _library_key(project_id)
        rows = conn.execute(
            "SELECT * FROM tracks WHERE project_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (key, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tracks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = [_track_dict(r) for r in rows if _is_playable(r["file_path"])]
    return {"tracks": out}


@router.post("/cleanup")
async def cleanup_dead_tracks():
    """物理删除文件丢失 / 体积过小的 track DB 行。返回被删除数 + ID 列表。"""
    conn = get_global_music_conn()
    rows = conn.execute("SELECT id, file_path FROM tracks").fetchall()
    dead_ids: list[int] = []
    for r in rows:
        if not _is_playable(r["file_path"]):
            dead_ids.append(int(r["id"]))
            # 文件可能还在，但小于阈值——尝试清掉物理残骸
            try:
                p = global_music_root() / r["file_path"]
                if p.exists():
                    p.unlink(missing_ok=True)
            except OSError:
                pass
    if dead_ids:
        placeholders = ",".join("?" * len(dead_ids))
        conn.execute(f"DELETE FROM tracks WHERE id IN ({placeholders})", dead_ids)
        conn.commit()
    return {"deleted_count": len(dead_ids), "deleted_ids": dead_ids}


@router.get("/track/{track_id}")
async def get_track(track_id: int):
    conn = get_global_music_conn()
    row = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail="track not found")
    return _track_dict(row)


@router.put("/track/{track_id}")
async def update_track(track_id: int, payload: TrackUpdate):
    conn = get_global_music_conn()
    row = conn.execute("SELECT id FROM tracks WHERE id = ?", (track_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail="track not found")
    if payload.name is not None:
        conn.execute("UPDATE tracks SET name = ? WHERE id = ?",
                     (payload.name.strip()[:200] or "track", track_id))
        conn.commit()
    return await get_track(track_id)


class SetAsBgmRequest(BaseModel):
    project_id: str


@router.post("/track/{track_id}/set-as-bgm")
async def set_track_as_project_bgm(track_id: int, payload: SetAsBgmRequest):
    """把音乐库里这首歌**复制**为项目的 BGM (project>/bgm/bgm.<ext>)。
    下一次 /merge-project-video 会自动用它（与原 /api/video-engine/bgm/{pid} 上传走同一条路）。
    """
    if not payload.project_id.strip():
        raise HTTPException(400, detail="project_id 不能为空")
    conn = get_global_music_conn()
    row = conn.execute(
        "SELECT file_path, name FROM tracks WHERE id = ?", (track_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail=f"音乐 track {track_id} 不存在")
    src = global_music_root() / row["file_path"]
    if not src.is_file():
        raise HTTPException(404, detail=f"音乐文件丢失: {src.name}")

    cfg = load_settings()
    proj_dir = Path(cfg.projects_dir) / payload.project_id
    if not proj_dir.exists():
        raise HTTPException(404, detail="项目不存在")

    bgm_dir = proj_dir / "bgm"
    bgm_dir.mkdir(parents=True, exist_ok=True)
    # 清旧 BGM（任何已支持后缀）
    for old_ext in (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"):
        (bgm_dir / f"bgm{old_ext}").unlink(missing_ok=True)

    # 复制到 bgm.<src 后缀>
    suffix = src.suffix.lower() or ".mp3"
    dest = bgm_dir / f"bgm{suffix}"
    import shutil as _sh
    _sh.copyfile(src, dest)
    return {
        "ok":         True,
        "track_id":   track_id,
        "track_name": row["name"],
        "bgm_path":   str(dest),
        "filename":   dest.name,
    }


@router.delete("/track/{track_id}", status_code=204)
async def delete_track(track_id: int):
    conn = get_global_music_conn()
    row = conn.execute(
        "SELECT file_path FROM tracks WHERE id = ?", (track_id,),
    ).fetchone()
    if row is None:
        return
    try:
        (global_music_root() / row["file_path"]).unlink(missing_ok=True)
    except OSError:
        pass
    conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
    conn.commit()


@router.get("/file/{track_id}")
async def serve_track_file(track_id: int):
    conn = get_global_music_conn()
    row = conn.execute(
        "SELECT file_path, mime FROM tracks WHERE id = ?", (track_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail="track not found")
    full = global_music_root() / row["file_path"]
    if not full.is_file():
        raise HTTPException(404, detail="track file missing on disk")
    return FileResponse(full, media_type=row["mime"] or "audio/mpeg",
                        filename=full.name)


# ── 本地音频上传入库（v1.6.2）──────────────────────────────────────────────────
# 与「生成入库」等价的旁路：音频来源换成用户上传的 base64，落盘到全局音乐库并 INSERT tracks。

ALLOWED_AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}
MIME_BY_EXT = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav",
    ".aac": "audio/aac", ".ogg": "audio/ogg", ".flac": "audio/flac",
}


class MusicUploadRequest(BaseModel):
    filename:   str = ""          # 原始文件名（取后缀 + 缺省显示名）
    data:       str = ""          # base64 音频
    name:       str = ""          # 库内显示名（空则用文件名 stem）
    project_id: str = ""          # 可选；系列项目经 _library_key 归并共享


@router.post("/upload")
async def upload_track(req: MusicUploadRequest):
    """上传本地音频文件进入音乐库。校验后缀/大小 → 落盘 global_music_root → INSERT tracks。"""
    ext = Path(req.filename or "").suffix.lower()
    if ext not in ALLOWED_AUDIO_EXT:
        raise HTTPException(
            400, detail=f"不支持的音频格式：{ext or '(无扩展名)'}；支持 {', '.join(sorted(ALLOWED_AUDIO_EXT))}")
    try:
        audio_bytes = base64.b64decode(req.data or "")
    except Exception as e:
        raise HTTPException(400, detail=f"音频解码失败: {e}")
    if len(audio_bytes) < _MIN_PLAYABLE_BYTES:
        raise HTTPException(400, detail="音频为空或过小(<1KB)")

    music_dir = global_music_root()
    stem = (req.name.strip() or Path(req.filename).stem or "upload")
    base = _safe_filename(stem)
    target = music_dir / _safe_filename(f"{base}{ext}")
    n = 2
    while target.exists():
        target = music_dir / _safe_filename(f"{base}({n}){ext}")
        n += 1
    target.write_bytes(audio_bytes)
    rel = target.name

    display = req.name.strip() or Path(req.filename).stem or "upload"
    conn = get_global_music_conn()
    cur = conn.execute(
        "INSERT INTO tracks("
        "  name, file_path, mime, project_id, seed, duration_secs, "
        "  bpm, time_signature, language, key_scale, tags, lyrics, "
        "  bytes, created_at"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            display, rel, MIME_BY_EXT.get(ext, "audio/mpeg"),
            _library_key(req.project_id),
            # seed/duration 未知留 0；其余沿用与生成 track 一致的合理默认，避免库列表/参数克隆出现空值
            0, 0, 120, "4", "zh", "C major", "上传", "",
            len(audio_bytes), datetime.now(timezone.utc).isoformat(),
        ),
    )
    track_id = cur.lastrowid
    conn.commit()
    return {"ok": True, "track_id": track_id,
            "url": f"/api/music/file/{track_id}", "filename": rel}


# ── Generation SSE ────────────────────────────────────────────────────────────


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/generate-stream")
async def music_generate_stream(req: MusicGenerateRequest):
    """SSE: 提交到 ComfyUI → 进度推送 → completed 时自动入库 + 返回 track_id。"""
    if req.workflow_name not in SUPPORTED_MUSIC_WORKFLOWS:
        raise HTTPException(400, detail=f"不支持的音乐工作流: {req.workflow_name!r}")

    # 找 workflow 文件（优先 bundled）
    icfg = load_settings().image_engine
    workflow = await get_workflow_json(icfg, req.workflow_name)
    if workflow is None:
        raise HTTPException(404, detail=f"工作流 '{req.workflow_name}' 未找到")

    # ComfyUI URL：复用 image_engine.comfyui_url
    comfyui_url = icfg.comfyui_url

    # 给这个 track 预留一个 id（用 created_at + 随机 + name）
    # 实际的 SQLite id 是在 completed 时插入后回填的
    track_label = _safe_filename(req.name) or f"track_{int(datetime.now().timestamp())}"

    async def stream():
        from services.ace_step_audio import generate_music
        used_seed = None
        async for event in generate_music(
            comfyui_url, workflow,
            duration_seconds = req.duration_seconds,
            bpm              = req.bpm,
            time_signature   = req.time_signature,
            language         = req.language,
            key_scale        = req.key_scale,
            tags             = req.tags,
            lyrics           = req.lyrics,
            seed             = req.seed,
            track_id         = track_label,
        ):
            ev = event.get("event")
            if ev == "queued":
                used_seed = event.get("seed")
                yield _sse(event)
            elif ev == "completed":
                # 落盘 + 入库
                try:
                    audio_b64 = event.get("audio") or ""
                    audio_bytes = base64.b64decode(audio_b64) if audio_b64 else b""
                    if not audio_bytes:
                        yield _sse({"event": "error", "message": "生成结果为空"})
                        return
                    music_dir = global_music_root()
                    # 命名：<label>_<seed>.mp3
                    seed_used = used_seed if used_seed is not None else event.get("seed", 0)
                    out_name = _safe_filename(f"{track_label}_{seed_used}.mp3")
                    # 防重名
                    target = music_dir / out_name
                    n = 2
                    while target.exists():
                        target = music_dir / _safe_filename(f"{track_label}_{seed_used}({n}).mp3")
                        n += 1
                    target.write_bytes(audio_bytes)
                    rel = target.name

                    conn = get_global_music_conn()
                    cur = conn.execute(
                        "INSERT INTO tracks("
                        "  name, file_path, mime, project_id, seed, duration_secs, "
                        "  bpm, time_signature, language, key_scale, tags, lyrics, "
                        "  bytes, created_at"
                        ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            req.name.strip() or track_label,
                            rel,
                            event.get("mime") or "audio/mpeg",
                            _library_key(req.project_id),
                            int(seed_used or 0),
                            int(req.duration_seconds),
                            int(req.bpm),
                            req.time_signature,
                            req.language,
                            req.key_scale,
                            req.tags,
                            req.lyrics,
                            len(audio_bytes),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    track_id = cur.lastrowid
                    conn.commit()
                    yield _sse({
                        "event":    "completed",
                        "track_id": track_id,
                        "seed":     int(seed_used or 0),
                        "url":      f"/api/music/file/{track_id}",
                        "filename": event.get("filename"),
                    })
                except Exception as e:
                    yield _sse({"event": "error",
                                 "message": f"音乐入库失败: {e}"})
                return
            else:
                yield _sse(event)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})
