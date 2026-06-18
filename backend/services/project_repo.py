"""ProjectRepo —— 项目数据访问层（DAL）。

定位：
- 当前 router 直接读写 JSON 文件。本层把"该写 SQLite 也写 SQLite"的逻辑
  集中在这里，路由层逐步切换调用 repo。
- 双写策略：
   1) JSON 仍是规范文件（向后兼容、人类可读、Skill CLI 还在用）
   2) 同时写 SQLite（新机制依靠它做状态机 / 查询 / 后续任务系统）
- 双写如果失败，**SQLite 错误不阻塞 JSON 写入**——SQLite 是新机制，老路径必须仍能工作。

接口：
- save_scenes(pid, scenes)            # 全量保存 + 计算 status
- record_asset(pid, scene_id, ...)    # 记录单个 asset（图片/音频/视频/字幕落盘后调）
- get_scenes(pid)                     # 读出（仍然以 JSON 为准，SQLite 作为后备 / 状态查询）
- list_scene_status(pid)              # 仅返回 [{id, status, error_message}]
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import load_settings
from services.db import project_db
from services.project_state import SceneStatus, advance_scene


def _proj_dir(pid: str) -> Path:
    return Path(load_settings().projects_dir) / pid


# ── Scenes ─────────────────────────────────────────────────────────────────────


def save_scenes(project_id: str, scenes: list[dict]) -> None:
    """JSON + SQLite 双写。SQLite 失败不阻塞 JSON。"""
    pdir = _proj_dir(project_id)
    pdir.mkdir(parents=True, exist_ok=True)
    # 1) 写 JSON（原行为）
    (pdir / "scenes.json").write_text(
        json.dumps({"scenes": scenes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 2) 写 SQLite（双写）
    try:
        _sync_scenes_to_db(project_id, scenes)
    except Exception as e:
        # 不能让 SQLite 失败影响主路径
        print(f"[project_repo] sqlite sync failed for {project_id}: {e}", flush=True)


def _sync_scenes_to_db(project_id: str, scenes: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with project_db(project_id) as conn:
        # 当前 scenes id 集合
        ids_now = {s.get("id") for s in scenes if s.get("id")}
        # 删除已不存在的
        existing = {r["id"] for r in conn.execute("SELECT id FROM scenes").fetchall()}
        gone = existing - ids_now
        if gone:
            conn.executemany(
                "DELETE FROM scenes WHERE id = ?",
                [(i,) for i in gone],
            )
            conn.executemany(
                "DELETE FROM scene_assets WHERE scene_id = ?",
                [(i,) for i in gone],
            )

        for s in scenes:
            sid = s.get("id")
            if not sid:
                continue
            row = conn.execute(
                "SELECT status FROM scenes WHERE id = ?", (sid,)
            ).fetchone()
            # 推断 status：description→draft；有 frame prompts → prompted
            has_prompts = bool(
                (s.get("start_frame_prompt") or "").strip()
                and (s.get("end_frame_prompt") or "").strip()
            )
            inferred_status = SceneStatus.PROMPTED if has_prompts else SceneStatus.DRAFT
            # 如果已存在且当前状态 >= prompted（已往前推），保留原状态
            if row is not None:
                cur_status = SceneStatus(row["status"])
                order = list(SceneStatus)
                if order.index(cur_status) >= order.index(inferred_status):
                    inferred_status = cur_status

            payload = (
                sid,
                int(s.get("index", 0) or 0),
                s.get("description", "") or "",
                float(s.get("duration_estimate", 5.0) or 5.0),
                s.get("start_frame_prompt", "") or "",
                s.get("end_frame_prompt", "") or "",
                json.dumps(s.get("dialogues") or [], ensure_ascii=False),
                json.dumps(s.get("_scene_characters") or [], ensure_ascii=False),
                inferred_status.value,
                "",     # error_message 不动
                now,    # 简化：created_at 用 now（若已存在就被 ON CONFLICT 保留也 OK——这里用 upsert）
                now,
            )
            conn.execute(
                """
                INSERT INTO scenes(
                    id, idx, description, duration_estimate,
                    start_frame_prompt, end_frame_prompt,
                    dialogues_json, scene_characters_json,
                    status, error_message, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    idx                   = excluded.idx,
                    description           = excluded.description,
                    duration_estimate     = excluded.duration_estimate,
                    start_frame_prompt    = excluded.start_frame_prompt,
                    end_frame_prompt      = excluded.end_frame_prompt,
                    dialogues_json        = excluded.dialogues_json,
                    scene_characters_json = excluded.scene_characters_json,
                    status                = excluded.status,
                    updated_at            = excluded.updated_at
                """,
                payload,
            )


# ── Assets ─────────────────────────────────────────────────────────────────────


def record_asset(
    project_id: str,
    scene_id: str,
    asset_type: str,             # 'image_start' | 'image_end' | 'audio' | 'video' | 'subtitle'
    *,
    slot_index: int = 0,
    file_path: str = "",         # 相对项目目录的路径
    format: str = "",
    metadata: Optional[dict] = None,
    is_selected: bool = False,
    advance_state: bool = True,  # 是否同时尝试推进 scene 状态
) -> None:
    """登记一个 asset。失败不抛——SQLite 是辅助层。"""
    now = datetime.now(timezone.utc).isoformat()
    try:
        with project_db(project_id) as conn:
            conn.execute(
                """
                INSERT INTO scene_assets(
                    scene_id, asset_type, slot_index, file_path,
                    format, metadata_json, is_selected, created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(scene_id, asset_type, slot_index) DO UPDATE SET
                    file_path     = excluded.file_path,
                    format        = excluded.format,
                    metadata_json = excluded.metadata_json,
                    is_selected   = excluded.is_selected
                """,
                (
                    scene_id, asset_type, int(slot_index),
                    file_path or "", format or "",
                    json.dumps(metadata or {}, ensure_ascii=False),
                    1 if is_selected else 0,
                    now,
                ),
            )
            if advance_state:
                _try_auto_advance(conn, scene_id)
    except Exception as e:
        print(f"[project_repo] record_asset {scene_id}/{asset_type}: {e}", flush=True)


def _try_auto_advance(conn, scene_id: str) -> None:
    """按 invariant 一步步推进 scene 状态到最高合理位置。"""
    from services.project_state import (
        load_scene_snapshot, SceneStatus, advance_scene, InvalidTransition,
    )
    # 升级路径：draft → prompted → image_drafted → audio_ready → video_ready
    chain = [
        SceneStatus.PROMPTED,
        SceneStatus.IMAGE_DRAFTED,
        SceneStatus.AUDIO_READY,
        SceneStatus.VIDEO_READY,
    ]
    for target in chain:
        snap = load_scene_snapshot(conn, scene_id)
        if snap is None:
            return
        # 当前已 >= target 则继续看下一档
        order = list(SceneStatus)
        if order.index(snap.status) >= order.index(target):
            continue
        try:
            advance_scene(conn, scene_id, target, check_invariants=True)
        except InvalidTransition:
            # 该级 invariant 不满足，停止往上推
            return


# ── Queries ────────────────────────────────────────────────────────────────────


def list_video_assets(project_id: str, asset_type: str = "video") -> dict:
    """返回 {scene_id: 视频文件相对路径}（已登记的视频资产）。

    v1.5.1：供 GET /videos 自愈用 —— videos.json 可能缺失/不全，但生成时
    record_asset 已把 video 资产写进 scene_assets；据此把"盘上有、索引缺"的
    分镜视频补回来。失败回 {}（SQLite 是辅助层，不抛）。
    v1.6：asset_type 可传 'video'（旧/普通）或 'video_msr'（多图参考），双模分别查。
    """
    out: dict = {}
    try:
        with project_db(project_id) as conn:
            rows = conn.execute(
                "SELECT scene_id, file_path FROM scene_assets "
                "WHERE asset_type = ? AND file_path != '' "
                "ORDER BY is_selected DESC, slot_index ASC",
                (asset_type,),
            ).fetchall()
            for r in rows:
                sid = r["scene_id"]
                if sid not in out:
                    out[sid] = r["file_path"]
    except Exception as e:
        print(f"[project_repo] list_video_assets: {e}", flush=True)
    return out


def list_scene_status(project_id: str) -> list[dict]:
    try:
        with project_db(project_id) as conn:
            rows = conn.execute(
                "SELECT id, idx, status, error_message FROM scenes ORDER BY idx ASC"
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[project_repo] list_scene_status: {e}", flush=True)
        return []


def project_summary(project_id: str) -> dict:
    """聚合：项目当前阶段 + 每状态计数 + scenes 总数。"""
    try:
        with project_db(project_id) as conn:
            counts = conn.execute(
                "SELECT status, COUNT(*) AS c FROM scenes GROUP BY status"
            ).fetchall()
            by_status = {r["status"]: int(r["c"]) for r in counts}
            from services.project_state import project_status as _ps
            stage = _ps(conn).value
            total = conn.execute("SELECT COUNT(*) AS c FROM scenes").fetchone()["c"]
            assets = conn.execute(
                "SELECT asset_type, COUNT(*) AS c FROM scene_assets GROUP BY asset_type"
            ).fetchall()
            return {
                "project_stage": stage,
                "scene_total":   int(total),
                "by_status":     by_status,
                "by_asset":      {r["asset_type"]: int(r["c"]) for r in assets},
            }
    except Exception as e:
        return {"project_stage": "unknown", "error": str(e)[:200]}
