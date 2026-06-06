"""Scene / Project 状态机（A1 地基）。

设计要点：
- Scene 是基本单位。Project 状态从 scenes 状态聚合派生。
- 状态推进必须显式调 `advance_scene(...)`；它会校验 invariant + 写 SQLite。
- 状态机 = 防止"frame_prompt 为空但图片已生成"这类自相矛盾状态的核心。

状态：
  draft           分镜刚切出来，没有提示词
  prompted        start/end_frame_prompt 都已生成
  image_drafted   每镜至少有 1 张 start + 1 张 end 图片
  audio_ready     音频已生成（reading 模式：__ms_reading__；其它：所有 dialogue clip 完成）
  video_ready     该镜的 mp4 已生成（依赖 image_drafted + audio_ready）
  finalized       项目级合并 + 字幕完成后，最终态
  error           任意阶段出错，error_message 给出原因

转移规则（任何不在 ALLOWED 表里的转移 → 抛 InvalidTransition）：
  draft         → prompted | error
  prompted      → image_drafted | error
  image_drafted → audio_ready | error
  audio_ready   → video_ready | error
  video_ready   → finalized | error
  finalized     → finalized (no-op)
  error         → 任意（允许从 error 回退/重试到任何状态）
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional


class SceneStatus(str, Enum):
    DRAFT          = "draft"
    PROMPTED       = "prompted"
    IMAGE_DRAFTED  = "image_drafted"
    AUDIO_READY    = "audio_ready"
    VIDEO_READY    = "video_ready"
    FINALIZED      = "finalized"
    ERROR          = "error"


_ALLOWED: dict[SceneStatus, set[SceneStatus]] = {
    SceneStatus.DRAFT:         {SceneStatus.PROMPTED, SceneStatus.ERROR},
    SceneStatus.PROMPTED:      {SceneStatus.IMAGE_DRAFTED, SceneStatus.ERROR, SceneStatus.DRAFT},
    SceneStatus.IMAGE_DRAFTED: {SceneStatus.AUDIO_READY,   SceneStatus.ERROR, SceneStatus.PROMPTED},
    SceneStatus.AUDIO_READY:   {SceneStatus.VIDEO_READY,   SceneStatus.ERROR, SceneStatus.IMAGE_DRAFTED},
    SceneStatus.VIDEO_READY:   {SceneStatus.FINALIZED,     SceneStatus.ERROR, SceneStatus.AUDIO_READY},
    SceneStatus.FINALIZED:     {SceneStatus.FINALIZED,     SceneStatus.ERROR},
    # error 视为"待用户介入"，允许从 error 重置到任意状态
    SceneStatus.ERROR:         {s for s in SceneStatus},
}


class InvalidTransition(RuntimeError):
    pass


def can_transition(src: SceneStatus, dst: SceneStatus) -> bool:
    return dst in _ALLOWED.get(src, set())


class ProjectStage(str, Enum):
    """项目级聚合阶段，从 scenes 状态派生。"""
    EMPTY         = "empty"            # 无分镜
    DRAFTED       = "drafted"          # 有分镜但还没出提示词
    PROMPTED      = "prompted"         # 全部分镜 prompted+
    IMAGES_DONE   = "images_done"      # 全部分镜 image_drafted+
    AUDIO_DONE    = "audio_done"       # 全部分镜 audio_ready+
    VIDEOS_DONE   = "videos_done"      # 全部分镜 video_ready+
    FINALIZED     = "finalized"        # 全部 finalized
    PARTIAL_ERROR = "partial_error"    # 部分 error


def aggregate_project_stage(scene_statuses: Iterable[SceneStatus]) -> ProjectStage:
    statuses = list(scene_statuses)
    if not statuses:
        return ProjectStage.EMPTY
    has_error = any(s == SceneStatus.ERROR for s in statuses)
    if has_error:
        return ProjectStage.PARTIAL_ERROR

    # 最低状态决定项目阶段
    order = [
        SceneStatus.DRAFT, SceneStatus.PROMPTED, SceneStatus.IMAGE_DRAFTED,
        SceneStatus.AUDIO_READY, SceneStatus.VIDEO_READY, SceneStatus.FINALIZED,
    ]
    min_status = min(statuses, key=lambda s: order.index(s) if s in order else 0)
    return {
        SceneStatus.DRAFT:         ProjectStage.DRAFTED,
        SceneStatus.PROMPTED:      ProjectStage.PROMPTED,
        SceneStatus.IMAGE_DRAFTED: ProjectStage.IMAGES_DONE,
        SceneStatus.AUDIO_READY:   ProjectStage.AUDIO_DONE,
        SceneStatus.VIDEO_READY:   ProjectStage.VIDEOS_DONE,
        SceneStatus.FINALIZED:     ProjectStage.FINALIZED,
    }[min_status]


# ── Invariants ────────────────────────────────────────────────────────────────
#
# 进入某个状态前必须满足的硬约束。校验失败 → 抛 InvalidTransition。

@dataclass
class SceneSnapshot:
    """从 SQLite 读出的某镜快照（DB row + 关联 assets 汇总）。"""
    id: str
    status: SceneStatus
    has_start_frame_prompt: bool
    has_end_frame_prompt: bool
    image_start_count: int
    image_end_count: int
    has_audio: bool
    has_video: bool


def check_can_enter(target: SceneStatus, snap: SceneSnapshot) -> None:
    """target 状态对应的 invariant 校验。不满足抛异常。"""
    if target == SceneStatus.PROMPTED:
        if not (snap.has_start_frame_prompt and snap.has_end_frame_prompt):
            raise InvalidTransition(
                f"scene {snap.id} 不能进 prompted：start/end frame_prompt 缺一"
            )
    elif target == SceneStatus.IMAGE_DRAFTED:
        if snap.image_start_count < 1 or snap.image_end_count < 1:
            raise InvalidTransition(
                f"scene {snap.id} 不能进 image_drafted："
                f"start_count={snap.image_start_count} end_count={snap.image_end_count}"
            )
    elif target == SceneStatus.AUDIO_READY:
        if not snap.has_audio:
            raise InvalidTransition(f"scene {snap.id} 不能进 audio_ready：缺音频")
    elif target == SceneStatus.VIDEO_READY:
        if not snap.has_video:
            raise InvalidTransition(f"scene {snap.id} 不能进 video_ready：缺视频")
    # FINALIZED / DRAFT / ERROR 不需要 entry invariant


# ── DB ops（薄包装）────────────────────────────────────────────────────────────

def load_scene_snapshot(conn, scene_id: str) -> Optional[SceneSnapshot]:
    row = conn.execute(
        "SELECT id, status, start_frame_prompt, end_frame_prompt "
        "FROM scenes WHERE id = ?", (scene_id,)
    ).fetchone()
    if row is None:
        return None
    counts = conn.execute(
        "SELECT asset_type, COUNT(*) AS c FROM scene_assets "
        "WHERE scene_id = ? GROUP BY asset_type",
        (scene_id,),
    ).fetchall()
    by_type = {r["asset_type"]: int(r["c"]) for r in counts}
    return SceneSnapshot(
        id=row["id"],
        status=SceneStatus(row["status"]),
        has_start_frame_prompt=bool((row["start_frame_prompt"] or "").strip()),
        has_end_frame_prompt=bool((row["end_frame_prompt"] or "").strip()),
        image_start_count=by_type.get("image_start", 0),
        image_end_count=by_type.get("image_end", 0),
        has_audio=by_type.get("audio", 0) > 0,
        has_video=by_type.get("video", 0) > 0,
    )


def advance_scene(
    conn,
    scene_id: str,
    target: SceneStatus,
    *,
    error_message: str = "",
    check_invariants: bool = True,
) -> SceneStatus:
    """显式状态推进。校验 + 写库 + 返回新状态。"""
    snap = load_scene_snapshot(conn, scene_id)
    if snap is None:
        raise InvalidTransition(f"scene {scene_id} 不存在")
    if not can_transition(snap.status, target):
        raise InvalidTransition(
            f"scene {scene_id}: {snap.status.value} -> {target.value} 不允许"
        )
    if check_invariants and target != SceneStatus.ERROR:
        check_can_enter(target, snap)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE scenes SET status = ?, error_message = ?, updated_at = ? WHERE id = ?",
        (target.value, error_message or "", now, scene_id),
    )
    return target


def project_status(conn) -> ProjectStage:
    rows = conn.execute("SELECT status FROM scenes").fetchall()
    return aggregate_project_stage(SceneStatus(r["status"]) for r in rows)
