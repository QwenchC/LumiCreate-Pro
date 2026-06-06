"""Tasks API（B1）。

POST   /tasks                       提交任务，立即返回 task_id
GET    /tasks?project_id=&status=   列出任务
GET    /tasks/{task_id}             查任务状态
POST   /tasks/{task_id}/cancel      取消（运行中的会被打断）
GET    /tasks/{task_id}/events      SSE 实时事件 + 历史回放
       (header: Last-Event-ID 用于断网重连续传)
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import task_repo, task_runner
from services.db import get_conn, project_db
from services.project_migrate import ensure_migrated

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class SubmitTaskRequest(BaseModel):
    project_id: str
    type:       str            # 当前只支持 'orchestrator'
    request:    dict


class CancelResponse(BaseModel):
    ok: bool
    message: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("")
async def submit_task(req: SubmitTaskRequest):
    if req.type != "orchestrator":
        raise HTTPException(status_code=400, detail=f"暂不支持的 task type: {req.type}")
    ensure_migrated(req.project_id)
    task_id = await task_runner.submit_orchestrator_task(req.project_id, req.request)
    return {"task_id": task_id, "project_id": req.project_id, "type": req.type, "status": "pending"}


@router.get("")
async def list_tasks(
    project_id: str,
    status: Optional[str] = None,
    type:   Optional[str] = None,
    limit:  int = 100,
):
    ensure_migrated(project_id)
    return {"tasks": task_repo.list_tasks(project_id, status=status, type_=type, limit=limit)}


@router.get("/{task_id}")
async def get_task(task_id: str, project_id: str):
    ensure_migrated(project_id)
    t = task_repo.get_task(project_id, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    t["is_running"] = task_runner.is_running(task_id)
    return t


@router.post("/{task_id}/cancel", response_model=CancelResponse)
async def cancel_task(task_id: str, project_id: str):
    ensure_migrated(project_id)
    t = task_repo.get_task(project_id, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    if t["status"] not in ("pending", "running"):
        return CancelResponse(ok=False, message=f"task already {t['status']}")
    requested = task_runner.request_cancel(task_id)
    if not requested:
        # 进程内信号已没了（可能是个老任务）
        task_repo.mark_cancelled(project_id, task_id)
    return CancelResponse(ok=True, message="cancellation requested")


# ── SSE events stream（支持断网重连） ─────────────────────────────────────────


@router.get("/{task_id}/events")
async def stream_task_events(
    task_id: str,
    project_id: str,
    request: Request,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
):
    """SSE：先回放历史事件（id > last_event_id），再实时推送新事件。

    - 断网重连：前端 EventSource 自动带上 Last-Event-ID header → 服务端从那以后回放
    - 历史持久化在 SQLite events 表，任务结束后仍可看完整时间线
    """
    ensure_migrated(project_id)
    # 校验任务存在
    if task_repo.get_task(project_id, task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")

    try:
        start_id = int(last_event_id) if last_event_id else 0
    except ValueError:
        start_id = 0

    async def gen():
        nonlocal start_id
        # 1) 回放历史事件
        while True:
            rows = await asyncio.to_thread(_fetch_events, project_id, task_id, start_id, 200)
            if not rows:
                break
            for r in rows:
                start_id = r["id"]
                yield _sse_event(r)
            if len(rows) < 200:
                break

        # 2) 长轮询：每 1.5s 查一次新事件
        while True:
            if await request.is_disconnected():
                return
            t = task_repo.get_task(project_id, task_id)
            running = t and t.get("status") in ("pending", "running")

            rows = await asyncio.to_thread(_fetch_events, project_id, task_id, start_id, 200)
            for r in rows:
                start_id = r["id"]
                yield _sse_event(r)

            if not running and not rows:
                # 任务已结束 + 历史推完 → 发一个 final 事件并退出
                t2 = task_repo.get_task(project_id, task_id) or {}
                yield _sse_marker("task_end", {
                    "status":       t2.get("status"),
                    "error":        t2.get("error_message", ""),
                    "items_done":   t2.get("items_done", 0),
                    "items_failed": t2.get("items_failed", 0),
                })
                yield "data: [DONE]\n\n"
                return

            await asyncio.sleep(1.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── helpers ───────────────────────────────────────────────────────────────────


def _fetch_events(project_id: str, task_id: str, after_id: int, limit: int) -> list[dict]:
    conn = get_conn(project_id)
    rows = conn.execute(
        "SELECT id, trace_id, task_id, scene_id, level, stage, message, payload_json, ts "
        "FROM events WHERE task_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
        (task_id, int(after_id), int(limit)),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d.pop("payload_json") or "{}")
        except Exception:
            d.pop("payload_json", None)
            d["payload"] = {}
        out.append(d)
    return out


def _sse_event(row: dict) -> str:
    return f"id: {row['id']}\ndata: {json.dumps(row, ensure_ascii=False, default=str)}\n\n"


def _sse_marker(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
