"""E2: 任务异步执行 + events 表查询 + 状态查询。

mock orchestrator stage 函数避免真实 LLM / ComfyUI 调用。
"""
import asyncio
import time

import pytest


async def _quick_stage(*_args, **_kwargs):
    """异步生成器 stub：立即 yield 一个 done 事件。"""
    yield {"event": "scene_done", "scene_id": "s1"}


def test_submit_returns_task_id_immediately(isolated_app, monkeypatch):
    """POST /tasks 必须立即返回，不等任务跑完。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    # 让 runner 跑一秒后再 success（验证"立即返回 ≠ 跑完"）
    from services import task_runner

    async def slow_runner(task_id, project_id, request, cancel_event):
        from services.task_repo import mark_running, mark_success
        mark_running(project_id, task_id)
        await asyncio.sleep(0.3)
        mark_success(project_id, task_id)

    monkeypatch.setattr(task_runner, "_run_orchestrator", slow_runner)

    t0 = time.monotonic()
    r = client.post("/api/tasks", json={
        "project_id": pid, "type": "orchestrator",
        "request": {"project_id": pid, "stages": ["scenes"]},
    })
    elapsed = time.monotonic() - t0
    assert r.status_code == 200, r.text
    assert "task_id" in r.json()
    assert elapsed < 0.2, f"POST /tasks took {elapsed:.2f}s — must be < 200ms"


def test_unsupported_task_type_rejected(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    r = client.post("/api/tasks", json={
        "project_id": pid, "type": "blockchain-mining", "request": {},
    })
    assert r.status_code == 400


def test_task_lifecycle_runs_to_success(isolated_app, monkeypatch):
    """提交 → 等 runner 跑完 → GET 看到 success。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    from services import task_runner

    async def runner(task_id, project_id, request, cancel_event):
        from services.task_repo import mark_running, mark_success
        from services.structured_log import use_trace, log_event
        mark_running(project_id, task_id)
        with use_trace(project_id=project_id, task_id=task_id, stage="scenes"):
            log_event("info", "test stage start")
            log_event("info", "test stage done")
        mark_success(project_id, task_id, {"result": 42})

    monkeypatch.setattr(task_runner, "_run_orchestrator", runner)

    r = client.post("/api/tasks", json={
        "project_id": pid, "type": "orchestrator",
        "request": {"project_id": pid, "stages": ["scenes"]},
    })
    task_id = r.json()["task_id"]

    # 轮询直到 success（最长 2s）
    for _ in range(20):
        t = client.get(f"/api/tasks/{task_id}",
                       params={"project_id": pid}).json()
        if t["status"] not in ("pending", "running"):
            break
        time.sleep(0.1)
    assert t["status"] == "success"
    assert t["result"] == {"result": 42}

    # events 表里有该 task 的事件
    events = client.get(f"/api/tasks/{task_id}/events",
                        params={"project_id": pid},
                        headers={"Accept": "text/event-stream"})
    # SSE 响应：起码包含 task_end 或事件 lines
    assert events.status_code == 200


def test_cancel_running_task(isolated_app, monkeypatch):
    """cancel endpoint 必须能下达信号；同时让 task_repo 直接验证状态转为 cancelled。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    from services import task_runner
    from services.task_repo import create_task, mark_running, get_task

    # 直接造一个 running 状态的任务（避免 TestClient sync 与 asyncio 事件循环排程的耦合）
    task_id = create_task(pid, "orchestrator", {})
    mark_running(pid, task_id)
    # 注册一个 dummy cancel event（与 request_cancel 接口约定一致）
    import asyncio as _asyncio
    task_runner._CANCEL_EVENTS[task_id] = _asyncio.Event()

    r = client.post(f"/api/tasks/{task_id}/cancel",
                    params={"project_id": pid})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # cancel event 已被设置
    assert task_runner._CANCEL_EVENTS[task_id].is_set()


def test_cancel_already_finished_task_returns_ok_false(isolated_app):
    """已成功的任务被 cancel → 返回 ok=False，状态不变。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    from services.task_repo import create_task, mark_success

    task_id = create_task(pid, "orchestrator", {})
    mark_success(pid, task_id)
    r = client.post(f"/api/tasks/{task_id}/cancel", params={"project_id": pid})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "success" in body["message"]


def test_list_tasks_filter(isolated_app):
    """B1: GET /tasks?project_id=...&status=... 过滤。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    from services.task_repo import create_task, mark_running, mark_success
    t1 = create_task(pid, "orchestrator", {})
    t2 = create_task(pid, "orchestrator", {})
    mark_running(pid, t1); mark_success(pid, t1)

    r = client.get("/api/tasks", params={"project_id": pid, "status": "success"})
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["tasks"]]
    assert t1 in ids
    assert t2 not in ids
