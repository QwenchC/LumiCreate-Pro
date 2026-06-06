"""Task 数据访问层（B1）。

`tasks` 表已在 db.py 的 INITIAL_DDL 里创建：
  id / type / status / request_json / result_json / error_message /
  items_total / items_done / items_failed / started_at / ended_at / created_at

状态：
  pending   提交了但还没开始
  running   执行中
  success   全部完成
  failed    抛异常或被中断且无法恢复
  cancelled 用户主动取消
  interrupted  服务进程重启时还在 running 的任务 → 启动后清理为此态
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from services.db import project_db


def new_task_id() -> str:
    return uuid.uuid4().hex[:16]


def create_task(
    project_id: str,
    task_type: str,
    request: dict,
    *,
    items_total: int = 0,
) -> str:
    """插入一条 pending 任务，返回 task_id。"""
    tid = new_task_id()
    now = datetime.now(timezone.utc).isoformat()
    with project_db(project_id) as conn:
        conn.execute(
            """
            INSERT INTO tasks(
                id, type, status, request_json, result_json, error_message,
                items_total, items_done, items_failed,
                started_at, ended_at, created_at
            ) VALUES(?, ?, 'pending', ?, '{}', '', ?, 0, 0, NULL, NULL, ?)
            """,
            (tid, task_type, json.dumps(request, ensure_ascii=False, default=str),
             int(items_total), now),
        )
    return tid


def mark_running(project_id: str, task_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with project_db(project_id) as conn:
        conn.execute(
            "UPDATE tasks SET status = 'running', started_at = ? WHERE id = ?",
            (now, task_id),
        )


def mark_success(project_id: str, task_id: str, result: Optional[dict] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with project_db(project_id) as conn:
        conn.execute(
            "UPDATE tasks SET status = 'success', ended_at = ?, result_json = ? WHERE id = ?",
            (now, json.dumps(result or {}, ensure_ascii=False, default=str), task_id),
        )


def mark_failed(project_id: str, task_id: str, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with project_db(project_id) as conn:
        conn.execute(
            "UPDATE tasks SET status = 'failed', ended_at = ?, error_message = ? WHERE id = ?",
            (now, str(error)[:2000], task_id),
        )


def mark_cancelled(project_id: str, task_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with project_db(project_id) as conn:
        conn.execute(
            "UPDATE tasks SET status = 'cancelled', ended_at = ? "
            "WHERE id = ? AND status IN ('pending','running')",
            (now, task_id),
        )


def update_progress(
    project_id: str, task_id: str,
    *, items_done: Optional[int] = None,
    items_failed: Optional[int] = None,
    items_total: Optional[int] = None,
) -> None:
    parts = []
    params = []
    if items_done is not None:
        parts.append("items_done = ?"); params.append(int(items_done))
    if items_failed is not None:
        parts.append("items_failed = ?"); params.append(int(items_failed))
    if items_total is not None:
        parts.append("items_total = ?"); params.append(int(items_total))
    if not parts:
        return
    params.append(task_id)
    with project_db(project_id) as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(parts)} WHERE id = ?", params)


def get_task(project_id: str, task_id: str) -> Optional[dict]:
    with project_db(project_id) as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        try: d["request"] = json.loads(d.pop("request_json") or "{}")
        except Exception: d["request"] = {}
        try: d["result"]  = json.loads(d.pop("result_json")  or "{}")
        except Exception: d["result"] = {}
        return d


def list_tasks(
    project_id: str,
    *, status: Optional[str] = None,
    type_:  Optional[str] = None,
    limit:  int = 100,
) -> list[dict]:
    parts = []
    params: list = []
    if status:
        parts.append("status = ?"); params.append(status)
    if type_:
        parts.append("type = ?");   params.append(type_)
    where = (" WHERE " + " AND ".join(parts)) if parts else ""
    params.append(int(max(1, min(limit, 1000))))
    with project_db(project_id) as conn:
        rows = conn.execute(
            f"SELECT id, type, status, items_total, items_done, items_failed, "
            f"       error_message, started_at, ended_at, created_at "
            f"FROM tasks{where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def mark_interrupted_on_startup(project_id: str) -> int:
    """启动钩子：把上次崩溃留下的 running/pending 任务标为 interrupted。返回个数。"""
    now = datetime.now(timezone.utc).isoformat()
    with project_db(project_id) as conn:
        rows = conn.execute(
            "SELECT id FROM tasks WHERE status IN ('pending','running')"
        ).fetchall()
        if not rows:
            return 0
        conn.execute(
            "UPDATE tasks SET status = 'interrupted', ended_at = ?, "
            "  error_message = '服务重启，原任务未完成' "
            "WHERE status IN ('pending','running')",
            (now,),
        )
        return len(rows)
