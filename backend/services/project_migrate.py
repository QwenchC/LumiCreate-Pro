"""一次性把项目目录里现有 JSON 文件导入到 project.sqlite。

调用时机：
- 项目第一次被路由触达时（GET /projects/{id}/* 等任何端点）调一次 `ensure_migrated(pid)`
- 幂等：若已迁移到 SCHEMA_VERSION 直接返回

迁移内容（v1 范围）：
- scenes.json → scenes 表
- images.json + 项目目录下 images/*.png → scene_assets(image_start/image_end)
- audio.json → scene_assets(audio)
- videos.json → scene_assets(video)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import load_settings
from services.db import project_db


_MIGRATED_FLAG = "_lumi_migrated_v1"


def _proj_dir(pid: str) -> Path:
    return Path(load_settings().projects_dir) / pid


def _is_migrated(conn) -> bool:
    row = conn.execute(
        "SELECT value FROM (SELECT 'x' AS k, NULL AS value) WHERE 0"
    ).fetchone()
    # 用 schema_version 表的 applied_at 标记: 若 v1 已 applied 且 scenes 表有任何 row，认为迁移过
    r = conn.execute(
        "SELECT COUNT(*) AS c FROM scenes"
    ).fetchone()
    return int(r["c"] or 0) > 0


def ensure_migrated(project_id: str) -> bool:
    """幂等迁移；返回 True 表示真的执行了迁移。"""
    pdir = _proj_dir(project_id)
    if not pdir.exists():
        return False

    with project_db(project_id) as conn:
        if _is_migrated(conn):
            return False

        # ── scenes.json → scenes ─────────────────────────────────────────
        scenes_data = _read_json(pdir / "scenes.json", default={})
        scenes = (scenes_data or {}).get("scenes") or []
        if not isinstance(scenes, list):
            scenes = []

        from services.project_repo import _sync_scenes_to_db
        if scenes:
            _sync_scenes_to_db(project_id, scenes)

        # ── images.json → scene_assets(image_start/image_end) ───────────
        img_meta = _read_json(pdir / "images.json", default={})
        saved_slots = (img_meta or {}).get("saved_slots") or []
        selected_map = (img_meta or {}).get("selected") or {}
        now = datetime.now(timezone.utc).isoformat()
        for slot in saved_slots:
            sid = slot.get("scene_id")
            ft  = slot.get("frame_type")
            si  = int(slot.get("slot_index", 0))
            fn  = slot.get("filename")
            if not (sid and ft and fn):
                continue
            asset_type = "image_start" if ft == "start" else "image_end"
            rel = f"images/{fn}"
            is_sel = 1 if selected_map.get(f"{sid}:{ft}") == si else 0
            conn.execute(
                """
                INSERT OR REPLACE INTO scene_assets(
                    scene_id, asset_type, slot_index, file_path,
                    format, metadata_json, is_selected, created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (sid, asset_type, si, rel, "png", "{}", is_sel, now),
            )

        # ── audio.json → scene_assets(audio) ─────────────────────────────
        audio = _read_json(pdir / "audio.json", default={})
        for key, entry in (audio or {}).items():
            if not isinstance(entry, dict):
                continue
            if key.startswith("__ms_reading__"):
                sid = key[len("__ms_reading__"):]
                file = entry.get("file") or ""
                fmt  = entry.get("format") or ("mp3" if file.endswith(".mp3") else "wav" if file else "")
                rel  = f"audio/{file}" if file else ""
                conn.execute(
                    """
                    INSERT OR IGNORE INTO scene_assets(
                        scene_id, asset_type, slot_index, file_path,
                        format, metadata_json, is_selected, created_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        sid, "audio", 0, rel, fmt,
                        json.dumps({"duration_ms": entry.get("duration_ms", 0)}),
                        1, now,
                    ),
                )
            elif key.startswith("__stitched__"):
                sid = key[len("__stitched__"):]
                file = entry.get("file") or ""
                rel  = f"audio/{file}" if file else ""
                fmt  = entry.get("format") or "wav"
                conn.execute(
                    """
                    INSERT OR IGNORE INTO scene_assets(
                        scene_id, asset_type, slot_index, file_path,
                        format, metadata_json, is_selected, created_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        sid, "audio", 0, rel, fmt,
                        json.dumps({"duration_ms": entry.get("duration_ms", 0), "stitched": True}),
                        1, now,
                    ),
                )

        # ── videos.json → scene_assets(video) ────────────────────────────
        videos = _read_json(pdir / "videos.json", default={})
        for sid, fn in (videos or {}).items():
            if not (sid and isinstance(fn, str)):
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO scene_assets(
                    scene_id, asset_type, slot_index, file_path,
                    format, metadata_json, is_selected, created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (sid, "video", 0, f"video/{fn}", "mp4", "{}", 1, now),
            )

        # ── 状态推断：根据 assets 把 scenes status 推到最高合理状态 ─────
        from services.project_repo import _try_auto_advance
        for s in scenes:
            sid = s.get("id")
            if sid:
                _try_auto_advance(conn, sid)

    return True


def _read_json(path: Path, *, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default
