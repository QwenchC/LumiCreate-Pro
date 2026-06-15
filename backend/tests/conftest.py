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

# 给 SETTINGS_PATH 一个测试专用临时根，避免污染/删除用户的真实数据。
# ⚠ 必须【无条件】覆盖：Windows 上 APPDATA 一定已存在，原先的 os.environ.setdefault
#   会变成 no-op → config.SETTINGS_PATH 指向真实 %APPDATA%/LumiCreate-Pro，
#   于是 isolated_app fixture 的"全局库清理"会删掉用户真实的 music.sqlite /
#   elements.sqlite / sfx / prompts 及其媒体目录（音乐库、元素库每次跑测试就消失）。
#   这里在任何 config 被 import 之前就锁死到测试目录，并把 HOME/USERPROFILE 一并兜底
#   （以防 config.py 的 Path.home() 回退分支）。
_TEST_DATA_ROOT = str(_BACKEND_DIR / ".test-tmp")
os.environ["APPDATA"] = _TEST_DATA_ROOT
os.environ["USERPROFILE"] = _TEST_DATA_ROOT
os.environ["HOME"] = _TEST_DATA_ROOT


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
        text_engine  = type("T", (), {
            "engine_type": "ollama", "concurrency": 4,
            "custom_platforms": [],   # v1.4.11+ 文本平台自定义列表
        })()
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
            # v1.4.11+: Seedream
            "seedream_base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "seedream_api_key":  "",
            "seedream_model":    "",
            "seedream_size":     "1024x1024",
            "seedream_response_format": "url",
            "seedream_seed":     -1,
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
            # v1.4.10 火山引擎字段（默认值，方便测试覆盖 dispatch 分支）
            "engine_type": "comfyui",
            "volcengine_base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "volcengine_api_key": "",
            "volcengine_model_id": "",
            "volcengine_poll_timeout": 600,
            "volcengine_poll_interval": 5,
            "volcengine_duration_secs": 5,
            "volcengine_resolution": "720p",
            "volcengine_ratio": "adaptive",
            "volcengine_use_image": True,
            "volcengine_generate_audio": False,
            "volcengine_watermark": False,
            "volcengine_camera_fixed": False,
            "volcengine_seed": -1,
        })()

    fake = _Cfg()
    # 防止 class 级 list 被跨测试共用
    fake.text_engine.custom_platforms = []
    load_settings_stub = lambda: fake
    # v1.4.11+ save_settings 在测试里改成 no-op，避免写到真实 ~/.lumicreate/settings.json
    save_settings_stub = lambda _s: None
    monkeypatch.setattr(config, "load_settings", load_settings_stub)
    monkeypatch.setattr(config, "save_settings", save_settings_stub)
    # 已经 `from config import load_settings` 的模块都要单独 patch
    for modname in (
        "services.db", "services.project_repo", "services.project_migrate",
        "services.task_runner", "services.task_repo",
        "services.engine_adapter", "services.comfyui_precheck",
        "routers.projects", "routers.image_engine", "routers.video_engine",
        "routers.audio_engine", "routers.subtitle_engine",
        "routers.orchestrator", "routers.task_history", "routers.templates",
        "routers.tasks", "routers.text_engine", "routers.music",
        "routers.sfx_engine",   # v1.4.8
        "routers.prompts_engine",   # v1.4.9
        "routers.settings",         # v1.4.11+ 文本平台 CRUD
    ):
        import sys as _sys
        mod = _sys.modules.get(modname)
        if mod is not None and hasattr(mod, "load_settings"):
            monkeypatch.setattr(mod, "load_settings", load_settings_stub)
        if mod is not None and hasattr(mod, "save_settings"):
            monkeypatch.setattr(mod, "save_settings", save_settings_stub)

    # 不 reload 模块（routers 已持引用），改用清理全局状态的方式
    from services import db
    # 把全局库根钉到本测试专属的 tmp 目录（per-test 隔离）。这一步至关重要：
    # 其它 fixture（如 test_elements_repo 的 isolated_global）会 importlib.reload(db)
    # 把 db.SETTINGS_PATH 改成它自己的 tmp，污染全局模块状态；这里无条件覆盖回本测试的
    # tmp，确保下面的"全局库清理"永远落在 tmp、绝不碰用户真实 %APPDATA%。
    _test_settings = tmp_path / "appdata" / "LumiCreate-Pro" / "settings.json"
    monkeypatch.setattr(db, "SETTINGS_PATH", _test_settings)
    monkeypatch.setattr(config, "SETTINGS_PATH", _test_settings, raising=False)
    db.close_all()
    db._CONNS.clear()                # 强制丢弃前面测试的连接

    # ⚠ 致命安全闸：下面会 unlink/rmtree 全局库。绝不允许落在用户真实 APPDATA 上。
    #   放在 try 之外，确保即便误指向真实路径也会【响亮地】报错而不是被静默吞掉。
    assert str(tmp_path) in str(db.SETTINGS_PATH), (
        f"refusing to wipe global stores at a non-test path: {db.SETTINGS_PATH}"
    )

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
        # v1.4.8 SFX 全局库残留
        gs = db._global_sfx_path()
        if gs.exists():
            gs.unlink(missing_ok=True)
        sfx_root = db.SETTINGS_PATH.parent / "sfx"
        if sfx_root.exists():
            _sh.rmtree(sfx_root, ignore_errors=True)
        # v1.4.9 提示词插件全局库残留
        gp = db._global_prompts_path()
        if gp.exists():
            gp.unlink(missing_ok=True)
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
