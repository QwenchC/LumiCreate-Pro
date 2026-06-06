"""D1 assets endpoint：基于 scene_assets 的统一资产寻址。"""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_with_project(tmp_path, monkeypatch):
    """单项目 + 已有 sqlite + 文件资产，对外暴露 TestClient。"""
    import config

    class _Cfg:
        projects_dir = str(tmp_path)
        text_engine  = type("T", (), {"engine_type": "ollama"})()
        image_engine = type("I", (), {})()
        audio_engine = type("A", (), {})()
        video_engine = type("V", (), {})()

    fake = _Cfg()
    monkeypatch.setattr(config, "load_settings", lambda: fake)

    from services import db, project_repo, structured_log
    importlib.reload(db)
    importlib.reload(project_repo)
    importlib.reload(structured_log)

    # 建项目目录 + 一个最小的 meta.json，让 _read_meta 不报错
    import json
    pid = "test_proj"
    pdir = tmp_path / pid
    pdir.mkdir()
    (pdir / "images").mkdir()
    (pdir / "project.json").write_text(json.dumps({
        "id": pid, "name": "Test", "description": "", "folder_id": "default",
        "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
        "progress": {"manuscript": 0, "scenes": 0, "images": 0, "audio": 0, "video": 0},
    }), encoding="utf-8")
    # 写一张假 PNG
    (pdir / "images" / "scene_001_start_0.png").write_bytes(b"\x89PNG\r\n\x1a\n_fake_")

    # 写入 scene + asset 到 sqlite
    project_repo.save_scenes(pid, [{
        "id": "scene_001", "index": 1, "description": "x",
        "start_frame_prompt": "a", "end_frame_prompt": "b",
    }])
    project_repo.record_asset(
        pid, "scene_001", "image_start",
        slot_index=0, file_path="images/scene_001_start_0.png",
        format="png", is_selected=True,
    )

    from app import create_app
    app = create_app()
    yield {"client": TestClient(app), "pid": pid}

    db.close_all()


def test_get_asset_file_by_slot(app_with_project):
    pid    = app_with_project["pid"]
    client = app_with_project["client"]
    r = client.get(f"/api/projects/{pid}/assets/file/scene_001/image_start/0")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content.startswith(b"\x89PNG")


def test_get_asset_file_default_selected(app_with_project):
    """不带 slot 时取 is_selected 那张。"""
    pid    = app_with_project["pid"]
    client = app_with_project["client"]
    r = client.get(f"/api/projects/{pid}/assets/file/scene_001/image_start")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")


def test_get_asset_file_404_missing(app_with_project):
    pid    = app_with_project["pid"]
    client = app_with_project["client"]
    r = client.get(f"/api/projects/{pid}/assets/file/no_such_scene/image_start")
    assert r.status_code == 404


def test_list_assets_returns_url(app_with_project):
    pid    = app_with_project["pid"]
    client = app_with_project["client"]
    r = client.get(f"/api/projects/{pid}/assets")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    a = data["assets"][0]
    assert a["scene_id"] == "scene_001"
    assert a["asset_type"] == "image_start"
    assert a["is_selected"] is True
    assert a["url"].endswith("/assets/file/scene_001/image_start/0")


def test_list_assets_filter_by_scene(app_with_project):
    pid    = app_with_project["pid"]
    client = app_with_project["client"]
    r = client.get(f"/api/projects/{pid}/assets",
                   params={"scene_id": "scene_001", "asset_type": "image_start"})
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_list_assets_filter_returns_empty(app_with_project):
    pid    = app_with_project["pid"]
    client = app_with_project["client"]
    r = client.get(f"/api/projects/{pid}/assets",
                   params={"scene_id": "nonexistent"})
    assert r.status_code == 200
    assert r.json()["count"] == 0
