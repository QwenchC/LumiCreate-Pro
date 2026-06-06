"""Task history (E2).

记录每次完成的批量任务，让用户能查"本周跑了多少次出图"、"哪个项目跑得最多"等。

存储：APPDATA/LumiCreate-Pro/task_history.json（单文件，append 模式）
schema：
  {
    "id": "<uuid>",
    "type": "images" | "audio" | "video" | "subtitle" | "merge" | "prompts",
    "project_id": str,
    "project_name": str,
    "started_at": ISO,
    "ended_at":   ISO,
    "duration_ms": int,
    "status":     "ok" | "partial" | "error",
    "items":      int,        // 任务规模（镜次数 / token 数）
    "errors":     int,        // 失败子项
    "note":       str         // 自由文本
  }
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import SETTINGS_PATH

_LOCK = threading.Lock()
_MAX = 2000   # 截断阈值


def _history_path() -> Path:
    return SETTINGS_PATH.parent / "task_history.json"


def _load() -> list[dict]:
    p = _history_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return []


def _save(records: list[dict]) -> None:
    p = _history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if len(records) > _MAX:
        records = records[-_MAX:]
    p.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def append(
    type_: str,
    project_id: str,
    *,
    project_name: str = "",
    started_at: Optional[str] = None,
    ended_at:   Optional[str] = None,
    duration_ms: Optional[int] = None,
    items: int = 0,
    errors: int = 0,
    status: Optional[str] = None,
    note: str = "",
) -> dict:
    """同步追加一条记录（带文件锁防并发覆盖）。"""
    now = datetime.now(timezone.utc).isoformat()
    if status is None:
        status = "error" if (errors and errors >= items > 0) else "partial" if errors else "ok"
    rec = {
        "id":          uuid.uuid4().hex[:12],
        "type":        type_,
        "project_id":  project_id,
        "project_name": project_name,
        "started_at":  started_at or now,
        "ended_at":    ended_at   or now,
        "duration_ms": int(duration_ms or 0),
        "items":       int(items),
        "errors":      int(errors),
        "status":      status,
        "note":        str(note)[:500],
    }
    with _LOCK:
        recs = _load()
        recs.append(rec)
        _save(recs)
    return rec


def list_records(limit: int = 100, project_id: Optional[str] = None, type_: Optional[str] = None) -> list[dict]:
    with _LOCK:
        recs = _load()
    if project_id:
        recs = [r for r in recs if r.get("project_id") == project_id]
    if type_:
        recs = [r for r in recs if r.get("type") == type_]
    return list(reversed(recs))[:limit]


def stats() -> dict:
    """简单统计：本月各类型计数 + 项目使用排行。"""
    with _LOCK:
        recs = _load()
    from datetime import datetime as _dt
    now = _dt.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    by_type: dict[str, int] = {}
    by_project: dict[str, int] = {}
    total = 0
    total_errors = 0
    total_ms = 0
    for r in recs:
        if (r.get("ended_at") or "") < month_start:
            continue
        total += 1
        total_errors += int(r.get("errors") or 0)
        total_ms     += int(r.get("duration_ms") or 0)
        by_type[r.get("type", "?")]       = by_type.get(r.get("type", "?"), 0) + 1
        by_project[r.get("project_name", r.get("project_id", "?"))] = \
            by_project.get(r.get("project_name", r.get("project_id", "?")), 0) + 1
    return {
        "month_start": month_start,
        "total_tasks": total,
        "total_errors": total_errors,
        "total_duration_ms": total_ms,
        "by_type": by_type,
        "by_project": dict(sorted(by_project.items(), key=lambda kv: kv[1], reverse=True)[:10]),
    }


def clear() -> None:
    with _LOCK:
        _save([])
