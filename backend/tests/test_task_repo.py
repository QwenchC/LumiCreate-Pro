"""TaskRepo：tasks 表 CRUD + 状态推进 + interrupted 清理。"""
import importlib

import pytest


@pytest.fixture()
def isolated_project(tmp_path, monkeypatch):
    import config
    orig = config.load_settings

    class _S:
        projects_dir = str(tmp_path)
    fake = _S()
    monkeypatch.setattr(config, "load_settings", lambda: fake)

    from services import db, project_repo, structured_log, task_repo
    importlib.reload(db)
    importlib.reload(project_repo)
    importlib.reload(structured_log)
    importlib.reload(task_repo)

    pid = "test_tasks"
    (tmp_path / pid).mkdir()
    yield {"pid": pid, "db": db, "task_repo": task_repo}

    db.close_all()
    monkeypatch.setattr(config, "load_settings", orig)


def test_create_lists_pending(isolated_project):
    pid = isolated_project["pid"]
    tr  = isolated_project["task_repo"]
    tid = tr.create_task(pid, "orchestrator", {"stages": ["scenes"]}, items_total=10)
    assert len(tid) == 16

    rows = tr.list_tasks(pid)
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["items_total"] == 10


def test_lifecycle_running_success(isolated_project):
    pid = isolated_project["pid"]
    tr  = isolated_project["task_repo"]
    tid = tr.create_task(pid, "orchestrator", {})
    tr.mark_running(pid, tid)
    t = tr.get_task(pid, tid)
    assert t["status"] == "running"
    assert t["started_at"] is not None

    tr.update_progress(pid, tid, items_done=5, items_failed=1)
    t = tr.get_task(pid, tid)
    assert t["items_done"] == 5
    assert t["items_failed"] == 1

    tr.mark_success(pid, tid, {"final": "ok"})
    t = tr.get_task(pid, tid)
    assert t["status"] == "success"
    assert t["ended_at"] is not None
    assert t["result"] == {"final": "ok"}


def test_lifecycle_failed(isolated_project):
    pid = isolated_project["pid"]
    tr  = isolated_project["task_repo"]
    tid = tr.create_task(pid, "orchestrator", {})
    tr.mark_running(pid, tid)
    tr.mark_failed(pid, tid, "boom")
    t = tr.get_task(pid, tid)
    assert t["status"] == "failed"
    assert "boom" in t["error_message"]


def test_cancel_only_pending_or_running(isolated_project):
    pid = isolated_project["pid"]
    tr  = isolated_project["task_repo"]
    tid = tr.create_task(pid, "orchestrator", {})
    tr.mark_success(pid, tid)
    # Already success → cancel must not change it
    tr.mark_cancelled(pid, tid)
    assert tr.get_task(pid, tid)["status"] == "success"


def test_list_filter(isolated_project):
    pid = isolated_project["pid"]
    tr  = isolated_project["task_repo"]
    tid1 = tr.create_task(pid, "orchestrator", {})
    tid2 = tr.create_task(pid, "images", {})
    tr.mark_running(pid, tid1); tr.mark_success(pid, tid1)
    assert len(tr.list_tasks(pid, status="success")) == 1
    assert len(tr.list_tasks(pid, status="pending")) == 1
    assert len(tr.list_tasks(pid, type_="images")) == 1


def test_mark_interrupted_on_startup(isolated_project):
    pid = isolated_project["pid"]
    tr  = isolated_project["task_repo"]
    # 模拟"上次崩溃"：留一个 running + 一个 pending
    tid1 = tr.create_task(pid, "orchestrator", {})
    tid2 = tr.create_task(pid, "orchestrator", {})
    tr.mark_running(pid, tid1)

    n = tr.mark_interrupted_on_startup(pid)
    assert n == 2
    assert tr.get_task(pid, tid1)["status"] == "interrupted"
    assert tr.get_task(pid, tid2)["status"] == "interrupted"
    # 第二次调用不应再处理（已经被标记完）
    assert tr.mark_interrupted_on_startup(pid) == 0
