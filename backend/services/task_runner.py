"""Async task runner（B1）。

把 orchestrator 从"HTTP 长连接 yield SSE"改成"后台 asyncio task 写 events 表"。

设计：
- `submit(...)` 立即返回 task_id + 启动 asyncio.create_task；HTTP 立即响应
- runner 内部所有阶段事件用 `log_event()` 写进 SQLite events 表
- 同时维护一个进程内的 cancel event，前端调 cancel 时设置该 event，runner 看到就退出
- 浏览器/客户端可关掉 → 任务继续在后台跑；下次 `GET /tasks/{id}/events` 仍能从 SQLite 回放

实现说明：
- 复用 orchestrator 现有 stage 函数（_stage_scenes / _stage_prompts / ...）
- 由于这些函数是 async generator，runner 自己消费它们 + 写 events
- 当前只针对 type='orchestrator'；后续 image batch / audio batch 也可走此通道
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Optional

import httpx

from services import task_repo
from services.structured_log import use_trace, log_event, new_trace_id

# 进程内 cancel 信号；task_id -> asyncio.Event
_CANCEL_EVENTS: dict[str, asyncio.Event] = {}
# 后台 task 句柄；task_id -> asyncio.Task
_RUNNING: dict[str, asyncio.Task] = {}


def is_running(task_id: str) -> bool:
    t = _RUNNING.get(task_id)
    return t is not None and not t.done()


def request_cancel(task_id: str) -> bool:
    """信号外部取消请求；runner 内部 check 该 event。"""
    e = _CANCEL_EVENTS.get(task_id)
    if e is None:
        return False
    e.set()
    return True


async def submit_orchestrator_task(project_id: str, request: dict) -> str:
    """提交 orchestrator 任务，立即返回 task_id。"""
    from services.project_migrate import ensure_migrated
    ensure_migrated(project_id)

    task_id = task_repo.create_task(project_id, "orchestrator", request)

    cancel_event = asyncio.Event()
    _CANCEL_EVENTS[task_id] = cancel_event

    loop = asyncio.get_running_loop()
    runner = loop.create_task(_run_orchestrator(task_id, project_id, request, cancel_event))
    _RUNNING[task_id] = runner
    return task_id


async def _run_orchestrator(
    task_id: str, project_id: str, request: dict, cancel_event: asyncio.Event,
) -> None:
    """实际执行 orchestrator 流水线。事件全部 → events 表。"""
    pipeline_trace = new_trace_id()

    try:
        task_repo.mark_running(project_id, task_id)
        with use_trace(stage="pipeline", project_id=project_id,
                       trace_id=pipeline_trace, task_id=task_id):
            log_event("info", "task started", payload={"request": request})

            from routers.orchestrator import (
                OrchestratorRequest, _stage_scenes, _stage_prompts, _stage_images,
                _stage_audio_reading, _stage_video, _stage_subtitle, _stage_merge,
            )
            req = OrchestratorRequest(**request)

            async with httpx.AsyncClient(timeout=None) as client:
                # 读 manuscript
                from routers.orchestrator import _http_get
                try:
                    ms = await _http_get(client, f"/api/projects/{project_id}/manuscript")
                except Exception as e:
                    log_event("error", f"读取文案失败: {e}")
                    task_repo.mark_failed(project_id, task_id, f"读取文案失败: {e}")
                    return

                scenes: list[dict] = []
                # ── scenes ──
                if "scenes" in req.stages:
                    if _check_cancel(cancel_event, project_id, task_id): return
                    with use_trace(stage="scenes", project_id=project_id,
                                   trace_id=f"{pipeline_trace}-scenes", task_id=task_id):
                        try:
                            scenes = await _stage_scenes(client, req, ms) or []
                            log_event("info", "scenes done", payload={"count": len(scenes)})
                        except Exception as e:
                            log_event("error", f"scenes error: {e}")
                else:
                    scenes = (await _http_get(client, f"/api/projects/{project_id}/scenes")).get("scenes") or []

                from services.project_repo import list_scene_status

                def _status_map() -> dict[str, str]:
                    return {r["id"]: r["status"] for r in list_scene_status(project_id)}

                # 总 items_total：每个启用阶段的镜次累加
                total = 0
                for s in (("prompts", "images", "audio", "video")):
                    if s in req.stages:
                        total += len(scenes)
                task_repo.update_progress(project_id, task_id, items_total=total)
                items_done = 0
                items_failed = 0
                status_map = _status_map()

                async def run_async_stage(stage_name: str, runner, *args, filter_pending):
                    nonlocal items_done, items_failed, status_map
                    if _check_cancel(cancel_event, project_id, task_id):
                        return
                    pending = [s for s in scenes if filter_pending(status_map.get(s.get("id"), "draft"))]
                    if not pending:
                        log_event("info", f"{stage_name} skip — nothing pending")
                        items_done += len(scenes)  # 视为已完成
                        task_repo.update_progress(project_id, task_id, items_done=items_done)
                        return
                    with use_trace(stage=stage_name, project_id=project_id,
                                   trace_id=f"{pipeline_trace}-{stage_name}", task_id=task_id):
                        log_event("info", f"{stage_name} start", payload={"count": len(pending)})
                        try:
                            if asyncio.iscoroutinefunction(runner):
                                await runner(*args, pending)
                            else:
                                # async generator
                                async for ev in runner(*args, pending):
                                    if _check_cancel(cancel_event, project_id, task_id):
                                        return
                                    # 透传上游事件作为 events 行
                                    et = ev.get("event") or "evt"
                                    if et == "error" or et == "scene_error":
                                        items_failed += 1
                                        log_event("error",
                                                  f"{stage_name} {ev.get('scene_id') or ''}: "
                                                  f"{ev.get('message') or ''}")
                                    elif et == "completed" or et == "scene_done":
                                        log_event("info", f"{stage_name} ok {ev.get('scene_id') or ''}")
                            items_done += len(pending)
                            task_repo.update_progress(project_id, task_id,
                                                       items_done=items_done,
                                                       items_failed=items_failed)
                            log_event("info", f"{stage_name} done")
                        except Exception as e:
                            log_event("error", f"{stage_name} error: {e}")
                            items_failed += len(pending)
                            task_repo.update_progress(project_id, task_id,
                                                       items_failed=items_failed)
                    status_map = _status_map()

                # ── prompts ──
                if "prompts" in req.stages and scenes:
                    async def _wrap_prompts(client, req, ms, pending):
                        await _stage_prompts(client, req, pending, ms)
                    await run_async_stage(
                        "prompts", _wrap_prompts, client, req, ms,
                        filter_pending=lambda st: st == "draft",
                    )
                # ── images ──
                if "images" in req.stages and scenes:
                    await run_async_stage(
                        "images", _stage_images, client, req,
                        filter_pending=lambda st: st in ("draft", "prompted"),
                    )
                # ── audio ──
                if "audio" in req.stages and scenes:
                    async def _wrap_audio(client, req, ms, pending):
                        async for ev in _stage_audio_reading(client, req, pending, ms):
                            yield ev
                    await run_async_stage(
                        "audio", _wrap_audio, client, req, ms,
                        filter_pending=lambda st: st not in (
                            "audio_ready", "video_ready", "finalized"),
                    )
                # ── video ──
                if "video" in req.stages and scenes:
                    await run_async_stage(
                        "video", _stage_video, client, req,
                        filter_pending=lambda st: st not in ("video_ready", "finalized"),
                    )
                # ── merge / subtitle 不分镜，直接跑 ──
                if "merge" in req.stages and scenes:
                    with use_trace(stage="merge", project_id=project_id,
                                   trace_id=f"{pipeline_trace}-merge", task_id=task_id):
                        try:
                            async for ev in _stage_merge(client, req, scenes):
                                if _check_cancel(cancel_event, project_id, task_id):
                                    return
                            log_event("info", "merge done")
                        except Exception as e:
                            log_event("error", f"merge error: {e}")

                if "subtitle" in req.stages:
                    w, h = 720, 1280
                    try:
                        from config import load_settings
                        settings = load_settings()
                        parts = (settings.video_engine.resolution or "720x1280").split("x")
                        w, h = int(parts[0]), int(parts[1])
                    except Exception:
                        pass
                    with use_trace(stage="subtitle", project_id=project_id,
                                   trace_id=f"{pipeline_trace}-subtitle", task_id=task_id):
                        try:
                            async for ev in _stage_subtitle(client, req, ms, w, h):
                                if _check_cancel(cancel_event, project_id, task_id):
                                    return
                            log_event("info", "subtitle done")
                        except Exception as e:
                            log_event("error", f"subtitle error: {e}")

            log_event("info", "task success")
            task_repo.mark_success(project_id, task_id,
                                   {"trace_id": pipeline_trace,
                                    "items_done": items_done,
                                    "items_failed": items_failed})
    except asyncio.CancelledError:
        # asyncio 层取消
        task_repo.mark_cancelled(project_id, task_id)
        raise
    except Exception as e:
        log_event("error", f"task crashed: {e}")
        task_repo.mark_failed(project_id, task_id, str(e))
    finally:
        _CANCEL_EVENTS.pop(task_id, None)
        _RUNNING.pop(task_id, None)


def _check_cancel(cancel_event: asyncio.Event, project_id: str, task_id: str) -> bool:
    if cancel_event.is_set():
        task_repo.mark_cancelled(project_id, task_id)
        log_event("warn", "task cancelled by user")
        return True
    return False


# ── 启动钩子 ──────────────────────────────────────────────────────────────────


def cleanup_interrupted_tasks() -> int:
    """扫描所有项目，把上次崩溃留下的 running/pending 任务标 interrupted。
    返回处理掉的总数。"""
    from pathlib import Path
    from config import load_settings
    root = Path(load_settings().projects_dir)
    if not root.exists():
        return 0
    total = 0
    for proj_dir in root.iterdir():
        if not proj_dir.is_dir():
            continue
        if not (proj_dir / "project.sqlite").exists():
            continue
        try:
            total += task_repo.mark_interrupted_on_startup(proj_dir.name)
        except Exception as e:
            print(f"[startup] cleanup_interrupted {proj_dir.name}: {e}", flush=True)
    return total
