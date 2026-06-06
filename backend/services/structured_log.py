"""结构化日志（E1 地基）。

设计：
- 用 contextvars 在异步链路自动传播 trace_id / task_id / stage
- emit() 写两路：
   1) 老 log_bus（前端浮窗依然看得到）
   2) project.sqlite 的 events 表（持久化、可关联回放）
- 不入侵已有代码：现有 print(...) 不动；新代码用 log_event() 即可

用法：
    from services.structured_log import set_context, log_event, traced

    @traced("scenes")        # 装饰器：自动给整个 stage 起一个 trace_id
    async def my_stage(project_id, ...):
        log_event("info", "开始", scene_id="scene_001")

或在 SSE 流式生成里手动管理 trace_id：
    with use_trace(task_id, stage="images") as trace_id:
        ...
"""
from __future__ import annotations

import json
import sys
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Iterator, Optional

# 异步任务里跨 await 传播
_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_task_id_var:  ContextVar[Optional[str]] = ContextVar("task_id",  default=None)
_stage_var:    ContextVar[Optional[str]] = ContextVar("stage",    default=None)
_project_id_var: ContextVar[Optional[str]] = ContextVar("project_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def get_trace_id() -> Optional[str]:
    return _trace_id_var.get()


def get_task_id() -> Optional[str]:
    return _task_id_var.get()


def get_stage() -> Optional[str]:
    return _stage_var.get()


def get_project_id() -> Optional[str]:
    return _project_id_var.get()


def set_context(
    *,
    trace_id: Optional[str] = None,
    task_id:  Optional[str] = None,
    stage:    Optional[str] = None,
    project_id: Optional[str] = None,
) -> None:
    if trace_id is not None: _trace_id_var.set(trace_id)
    if task_id  is not None: _task_id_var.set(task_id)
    if stage    is not None: _stage_var.set(stage)
    if project_id is not None: _project_id_var.set(project_id)


@contextmanager
def use_trace(
    *,
    trace_id: Optional[str] = None,
    task_id:  Optional[str] = None,
    stage:    Optional[str] = None,
    project_id: Optional[str] = None,
) -> Iterator[str]:
    tid = trace_id or new_trace_id()
    tokens = []
    tokens.append(_trace_id_var.set(tid))
    if task_id  is not None: tokens.append(_task_id_var.set(task_id))
    if stage    is not None: tokens.append(_stage_var.set(stage))
    if project_id is not None: tokens.append(_project_id_var.set(project_id))
    try:
        yield tid
    finally:
        for t in reversed(tokens):
            try:
                _trace_id_var.reset(t)   # noqa: PERF203 — best effort
            except (ValueError, LookupError):
                pass


def traced(stage: str) -> Callable:
    """函数级装饰器：自动开一个 trace_id 并设 stage。"""
    def deco(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            with use_trace(stage=stage):
                return await fn(*args, **kwargs)
        return wrapper
    return deco


def log_event(
    level: str,
    message: str,
    *,
    scene_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    """写入结构化事件。
    - 同时打印到 stderr（兼容已有日志面板）
    - 若当前 contextvars 里有 project_id，则写入项目 SQLite 的 events 表
    """
    trace_id = _trace_id_var.get() or "-"
    task_id  = _task_id_var.get() or ""
    stage    = _stage_var.get() or ""
    project_id = _project_id_var.get() or ""

    # 1) 老 log_bus：前端浮窗
    prefix = f"[{trace_id[:6]}"
    if stage: prefix += f"/{stage}"
    if scene_id: prefix += f"/{scene_id}"
    prefix += "]"
    out = sys.stderr if level == "error" else sys.stdout
    print(f"{prefix} {message}", file=out, flush=True)

    # 2) SQLite events 表（若有 project_id）
    if not project_id:
        return
    try:
        from services.db import get_conn
        conn = get_conn(project_id)
        conn.execute(
            "INSERT INTO events(trace_id, task_id, scene_id, level, stage, message, payload_json, ts) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                trace_id, task_id or None, scene_id or None,
                level, stage, message[:2000],
                json.dumps(payload or {}, ensure_ascii=False, default=str)[:4000],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    except Exception:
        # 日志失败永远不能反过来打挂业务
        pass


def info(msg: str, **kw)  -> None: log_event("info",  msg, **kw)
def warn(msg: str, **kw)  -> None: log_event("warn",  msg, **kw)
def error(msg: str, **kw) -> None: log_event("error", msg, **kw)
