"""DAL：save_scenes 双写 + record_asset + 自动状态推进。"""
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_project(tmp_path, monkeypatch):
    """每个测试在 tmp_path 下建一个空项目（包括重置 settings.projects_dir）。"""
    # Monkey-patch load_settings to point at tmp dir
    import config
    orig = config.load_settings

    class _S:
        projects_dir = str(tmp_path)

        @property
        def audio_engine(self):
            class _A: ...
            return _A()
    # 用闭包确保每次调用都返回同一个简单对象
    fake = _S()
    monkeypatch.setattr(config, "load_settings", lambda: fake)

    # 重新 import db / project_repo 以确保它们用 patched config
    from services import db, project_repo
    importlib.reload(db); importlib.reload(project_repo)

    pid = "test_proj"
    (tmp_path / pid).mkdir()

    yield {"pid": pid, "dir": tmp_path / pid, "db": db, "repo": project_repo}

    db.close_all()
    monkeypatch.setattr(config, "load_settings", orig)


def test_save_scenes_creates_sqlite(isolated_project):
    pid = isolated_project["pid"]
    repo = isolated_project["repo"]
    scenes = [
        {"id": "scene_001", "index": 1, "description": "镜头一", "duration_estimate": 5},
        {"id": "scene_002", "index": 2, "description": "镜头二",
         "start_frame_prompt": "a cat", "end_frame_prompt": "a dog"},
    ]
    repo.save_scenes(pid, scenes)

    rows = repo.list_scene_status(pid)
    assert len(rows) == 2
    by_id = {r["id"]: r for r in rows}
    # scene_001 没 prompts → 推断 draft
    assert by_id["scene_001"]["status"] == "draft"
    # scene_002 两个 prompts 都有 → 推断 prompted
    assert by_id["scene_002"]["status"] == "prompted"


def test_save_scenes_removes_gone_ids(isolated_project):
    pid  = isolated_project["pid"]
    repo = isolated_project["repo"]
    repo.save_scenes(pid, [
        {"id": "scene_001", "index": 1, "description": "1"},
        {"id": "scene_002", "index": 2, "description": "2"},
    ])
    repo.save_scenes(pid, [
        {"id": "scene_002", "index": 1, "description": "2 only"},
    ])
    rows = repo.list_scene_status(pid)
    assert [r["id"] for r in rows] == ["scene_002"]


def test_record_asset_auto_advances_status(isolated_project):
    pid  = isolated_project["pid"]
    repo = isolated_project["repo"]
    repo.save_scenes(pid, [{
        "id": "scene_001", "index": 1, "description": "x",
        "start_frame_prompt": "a", "end_frame_prompt": "b",
    }])
    # 起步：prompted（因为有两个 frame prompts）
    rows = repo.list_scene_status(pid)
    assert rows[0]["status"] == "prompted"

    # 加 1 张 start 图，仍是 prompted（需要 end 也至少 1 张）
    repo.record_asset(pid, "scene_001", "image_start",
                      slot_index=0, file_path="images/x.png", format="png")
    assert repo.list_scene_status(pid)[0]["status"] == "prompted"

    # 加 1 张 end 图 → 自动推进到 image_drafted
    repo.record_asset(pid, "scene_001", "image_end",
                      slot_index=0, file_path="images/y.png", format="png")
    assert repo.list_scene_status(pid)[0]["status"] == "image_drafted"

    # 加音频 → audio_ready
    repo.record_asset(pid, "scene_001", "audio",
                      slot_index=0, file_path="audio/__ms_reading__scene_001.mp3",
                      format="mp3")
    assert repo.list_scene_status(pid)[0]["status"] == "audio_ready"

    # 加视频 → video_ready
    repo.record_asset(pid, "scene_001", "video",
                      slot_index=0, file_path="video/scene_001.mp4", format="mp4")
    assert repo.list_scene_status(pid)[0]["status"] == "video_ready"


def test_save_scenes_preserves_advanced_status(isolated_project):
    """若 scene 已往前推进，重新 save_scenes 不应把它打回 draft/prompted。"""
    pid  = isolated_project["pid"]
    repo = isolated_project["repo"]
    repo.save_scenes(pid, [{
        "id": "scene_001", "index": 1, "description": "x",
        "start_frame_prompt": "a", "end_frame_prompt": "b",
    }])
    # 推进到 image_drafted
    repo.record_asset(pid, "scene_001", "image_start", file_path="x.png")
    repo.record_asset(pid, "scene_001", "image_end",   file_path="y.png")
    assert repo.list_scene_status(pid)[0]["status"] == "image_drafted"

    # 再写一次 scenes（例如用户编辑了 description）
    repo.save_scenes(pid, [{
        "id": "scene_001", "index": 1, "description": "edited",
        "start_frame_prompt": "a", "end_frame_prompt": "b",
    }])
    # 不应该被打回 prompted
    assert repo.list_scene_status(pid)[0]["status"] == "image_drafted"


def test_project_summary(isolated_project):
    pid  = isolated_project["pid"]
    repo = isolated_project["repo"]
    repo.save_scenes(pid, [
        {"id": "s1", "index": 1, "description": "x"},
        {"id": "s2", "index": 2, "description": "y",
         "start_frame_prompt": "a", "end_frame_prompt": "b"},
    ])
    summary = repo.project_summary(pid)
    assert summary["scene_total"] == 2
    assert summary["by_status"].get("draft", 0)    == 1
    assert summary["by_status"].get("prompted", 0) == 1
    # 项目阶段取最低 → drafted
    assert summary["project_stage"] == "drafted"
