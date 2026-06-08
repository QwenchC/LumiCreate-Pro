"""Pytest scaffolding + 共享 fixture（E2 集成测试用）。"""
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# 给 SETTINGS_PATH 一个测试专用临时根，避免污染用户的真实 settings.json
os.environ.setdefault("APPDATA", str(_BACKEND_DIR / ".test-tmp"))


# ── 共享 fixture ───────────────────────────────────────────────────────────────


@pytest.fixture()
def isolated_app(tmp_path, monkeypatch):
    """端到端测试通用 fixture：
       - 临时 projects_dir
       - 全局 load_settings 被 monkeypatch
       - 给 services.db / project_repo / structured_log 重新 import
       - 返回 {client, settings, tmp_path, make_project}
    """
    import config

    class _Cfg:
        projects_dir = str(tmp_path)
        # 给路由层零依赖即可启动的最小 stubs
        text_engine  = type("T", (), {"engine_type": "ollama", "concurrency": 4})()
        image_engine = type("I", (), {
            "engine_type":    "comfyui",
            "comfyui_url":    "http://localhost:18888",
            "workflow_dir":   str(tmp_path / "workflows"),
            "default_workflow": "",
            "image_width": 1024, "image_height": 1024,
            "default_gen_count": 1,
            "style_preset": "", "custom_style_text": "",
            # v1.4.5: Pollinations
            "pollinations_base_url": "https://gen.pollinations.ai",
            "pollinations_api_key":  "",
            "pollinations_model":    "flux",
        })()
        audio_engine = type("A", (), {
            "engine_type": "msedge",
            "api_url": "http://localhost:7860",
            "voice_ref_dir": "", "default_voice_ref": "",
            "emotion_ref_dir": "", "default_emo_weight": 0.8,
            "msedge_voice": "zh-CN-XiaoxiaoNeural",
            "msedge_rate":  "+0%",
            "default_gen_count": 1,
            "msedge_available_voices": [],
        })()
        video_engine = type("V", (), {
            "comfyui_url": "http://localhost:18888",
            "workflow_dir": "", "comfyui_input_dir": "",
            "default_workflow": "flfa2i-lumicreate",
            "resolution": "720x1280", "fps": 24,
        })()

    fake = _Cfg()
    load_settings_stub = lambda: fake
    monkeypatch.setattr(config, "load_settings", load_settings_stub)
    # 已经 `from config import load_settings` 的模块都要单独 patch
    for modname in (
        "services.db", "services.project_repo", "services.project_migrate",
        "services.task_runner", "services.task_repo",
        "services.engine_adapter", "services.comfyui_precheck",
        "routers.projects", "routers.image_engine", "routers.video_engine",
        "routers.audio_engine", "routers.subtitle_engine",
        "routers.orchestrator", "routers.task_history", "routers.templates",
        "routers.tasks", "routers.text_engine", "routers.music",
    ):
        import sys as _sys
        mod = _sys.modules.get(modname)
        if mod is not None and hasattr(mod, "load_settings"):
            monkeypatch.setattr(mod, "load_settings", load_settings_stub)

    # 不 reload 模块（routers 已持引用），改用清理全局状态的方式
    from services import db
    db.close_all()
    db._CONNS.clear()                # 强制丢弃前面测试的连接

    # v1.4.2: 全局音乐 / 元素 SQLite + 媒体目录跨测试残留会让"列表 / 清理"
    # 类测试结果不可预测；每次起 fixture 时整体清空。
    try:
        import shutil as _sh
        gm = db._global_music_path()
        if gm.exists():
            gm.unlink(missing_ok=True)
        ge = db._global_elements_path()
        if ge.exists():
            ge.unlink(missing_ok=True)
        music_root = db.SETTINGS_PATH.parent / "music"
        if music_root.exists():
            _sh.rmtree(music_root, ignore_errors=True)
        elements_root = db.SETTINGS_PATH.parent / "elements"
        if elements_root.exists():
            _sh.rmtree(elements_root, ignore_errors=True)
    except Exception:
        pass

    # 清理 task_runner 跨测试的全局字典
    try:
        from services import task_runner
        task_runner._CANCEL_EVENTS.clear()
        task_runner._RUNNING.clear()
    except Exception:
        pass

    from app import create_app
    from fastapi.testclient import TestClient
    client = TestClient(create_app())

    def make_project(pid: str = "test_proj", *, name: str = "Test") -> str:
        """落盘项目结构（project.json + 子目录），返回 pid。"""
        pdir = tmp_path / pid
        pdir.mkdir(exist_ok=True)
        for sub in ("images", "audio", "video", "cache"):
            (pdir / sub).mkdir(exist_ok=True)
        (pdir / "project.json").write_text(json.dumps({
            "id": pid, "name": name, "description": "", "folder_id": "default",
            "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
            "progress": {"manuscript": 0, "scenes": 0, "images": 0, "audio": 0, "video": 0},
        }), encoding="utf-8")
        return pid

    yield {
        "client":        client,
        "tmp_path":      tmp_path,
        "make_project":  make_project,
        "settings":      fake,
    }

    db.close_all()
