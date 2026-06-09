"""v1.4.10 火山引擎 Seedance dispatch + driver 回归测试。

**非侵入性约束**：
  - 老配置（没有 engine_type / volcengine_* 字段）必须按 ComfyUI 行为
  - 切到 volcengine_seedance 后，/workflows 返回合成名、/test 走 Ark 探活
  - 创建任务的 content payload 必须含 prompt + image，不会把 LTX 字段错传
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


# ── 配置兼容性（最重要！老 settings.json 不能炸）────────────────────────────


def test_old_settings_loads_default_engine_type_comfyui():
    """老用户 settings.json 没有 engine_type 字段，Pydantic 必须给默认值
    'comfyui' —— 行为与升级前完全一致。"""
    from config import VideoEngineConfig
    cfg = VideoEngineConfig()  # 全默认
    assert cfg.engine_type == "comfyui"
    # 火山引擎字段空字符串/默认值，但存在（settings 文件能序列化回去）
    assert cfg.volcengine_api_key == ""
    assert cfg.volcengine_model_id == ""
    assert cfg.volcengine_base_url.startswith("https://ark.")


def test_legacy_settings_json_without_engine_fields_round_trips(tmp_path, monkeypatch):
    """模拟 v1.4.9 留下的 settings.json：没有任何 volcengine_* 字段。
    load_settings 必须正常解析；新字段用默认值补齐。"""
    from config import AppSettings
    legacy = {
        "projects_dir": str(tmp_path),
        "video_engine": {
            "comfyui_url": "http://localhost:9999",
            "workflow_dir": "C:/x",
            "default_workflow": "flfa2i-lumicreate",
            "resolution": "720x1280",
            "fps": 25,
        },
    }
    s = AppSettings(**legacy)
    assert s.video_engine.comfyui_url == "http://localhost:9999"
    assert s.video_engine.engine_type == "comfyui"
    assert s.video_engine.volcengine_base_url   # 默认填充


# ── /workflows dispatch ──────────────────────────────────────────────────────


def test_workflows_returns_synthetic_name_in_volcengine_mode(
        isolated_app, monkeypatch):
    """engine_type='volcengine_seedance' 时 /workflows 直接返合成名，
    不真去 ComfyUI 拉清单 —— 否则前端会在云端模式下也尝试加载 LTX 工作流崩掉。"""
    client = isolated_app["client"]
    fake = isolated_app["settings"]
    fake.video_engine.engine_type = "volcengine_seedance"
    r = client.get("/api/video-engine/workflows")
    assert r.status_code == 200
    assert r.json() == ["volcengine_seedance"]


def test_workflows_normal_path_unchanged_in_comfyui_mode(isolated_app):
    """ComfyUI 模式下 /workflows 走原来的 bundled 扫描 + 硬名单 ——
    本测试只确认不抛 500，具体名单走 v1.4.5 的固有覆盖。"""
    client = isolated_app["client"]
    fake = isolated_app["settings"]
    fake.video_engine.engine_type = "comfyui"
    r = client.get("/api/video-engine/workflows")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── /test dispatch + /volcengine-test 独立端点 ────────────────────────────────


def test_test_endpoint_dispatches_to_seedance_when_volc_mode(
        isolated_app, monkeypatch):
    """engine_type='volcengine_seedance' 时 /test 不去 ping ComfyUI，
    走 Seedance 探活函数（mock 掉以免真发请求）。"""
    client = isolated_app["client"]
    fake = isolated_app["settings"]
    fake.video_engine.engine_type = "volcengine_seedance"
    fake.video_engine.volcengine_api_key = "test_key"

    async def _fake_seedance(*a, **kw):
        return True, "鉴权通过"

    with patch("services.volcengine_seedance.test_seedance_connection",
               new=AsyncMock(side_effect=_fake_seedance)):
        r = client.get("/api/video-engine/test")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "火山引擎" in body["message"]


def test_volcengine_test_endpoint_works_independently(isolated_app):
    """/volcengine-test 不依赖 engine_type 切换，用户配置中即可测试。
    没填 key 时返 success=False + 提示语，不应该 500。"""
    client = isolated_app["client"]
    fake = isolated_app["settings"]
    fake.video_engine.engine_type = "comfyui"
    fake.video_engine.volcengine_api_key = ""
    r = client.get("/api/video-engine/volcengine-test")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "API" in body["message"] or "api" in body["message"].lower()


# ── driver SSE schema 与 LTX 一致 ────────────────────────────────────────────


def _collect(agen):
    """同步收集 async generator 的全部 yields（测试辅助）。"""
    out = []
    async def _go():
        async for ev in agen:
            out.append(ev)
    asyncio.run(_go())
    return out


def test_driver_yields_error_when_no_api_key():
    """没 API key 第一时间 yield 'error'，不会偷偷打远端。"""
    from services.volcengine_seedance import generate_video_seedance
    events = _collect(generate_video_seedance(
        base_url="https://x", api_key="", model_id="m",
        first_frame_b64="abc",
        scene_id="s1",
    ))
    assert events[0]["event"] == "error"
    assert "API Key" in events[0]["message"]


def test_driver_yields_error_when_no_model_id():
    from services.volcengine_seedance import generate_video_seedance
    events = _collect(generate_video_seedance(
        base_url="https://x", api_key="k", model_id="",
        first_frame_b64="abc",
        scene_id="s2",
    ))
    assert events[0]["event"] == "error"
    assert "模型" in events[0]["message"]


def test_driver_happy_path_with_mocked_http():
    """打通完整 SSE 事件序列（mock 掉所有 HTTP 调用）：
    queued → progress(任务已创建) → progress(状态更新) → completed。"""
    from services import volcengine_seedance as vs

    create_calls = []
    poll_calls = [0]

    async def _fake_create(base_url, api_key, *, model_id, content, **kw):
        create_calls.append({"model": model_id, "content": content, "kwargs": kw})
        return "task_abc123", ""

    async def _fake_poll(base_url, api_key, task_id):
        poll_calls[0] += 1
        if poll_calls[0] < 2:
            return "running", None, ""
        return "succeeded", "https://example.com/v.mp4", ""

    async def _fake_download(url):
        return b"\x00\x00\x00\x18ftypmp42mp42"

    with patch.object(vs, "_post_create_task",
                      new=AsyncMock(side_effect=_fake_create)), \
         patch.object(vs, "_get_task_status",
                      new=AsyncMock(side_effect=_fake_poll)), \
         patch.object(vs, "_download_video",
                      new=AsyncMock(side_effect=_fake_download)), \
         patch.object(vs.asyncio, "sleep", new=AsyncMock(return_value=None)):
        events = _collect(vs.generate_video_seedance(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="k", model_id="ep-test",
            first_frame_b64="img_b64",
            positive_prompt="test prompt",
            duration_secs=5, resolution="720p",
            poll_interval=1, poll_timeout=60,
            scene_id="s_happy",
        ))
    # 事件序列
    kinds = [e["event"] for e in events]
    assert kinds[0] == "queued"
    assert "progress" in kinds
    assert kinds[-1] == "completed"
    # 最后一个 completed 必须带 base64 视频
    final = events[-1]
    assert final["video"]
    # 验证创建 task 时 content 含 prompt 文本 + image_url
    assert len(create_calls) == 1
    content = create_calls[0]["content"]
    assert any(p["type"] == "text" for p in content)
    assert any(p["type"] == "image_url" for p in content)
    # 验证生成参数走 request body（新方式）而不是塞 prompt
    kwargs = create_calls[0]["kwargs"]
    assert kwargs["resolution"] == "720p"
    assert kwargs["duration"] == 5
    # prompt 末尾不能再有 --hint
    text = next(p for p in content if p["type"] == "text")["text"]
    assert "--resolution" not in text
    assert "--duration" not in text


def test_content_builder_does_not_inject_hints_in_prompt():
    """v1.4.10 文档对齐：生成参数走 request body 强校验，prompt 保持干净。"""
    from services.volcengine_seedance import _build_content_payload
    parts = _build_content_payload(
        "a cat walks",
        first_frame_b64="ab",
        use_image=True,
    )
    text = parts[0]["text"]
    assert text == "a cat walks"
    # image_url 必须出现且是 data: URL 形态
    assert parts[1]["image_url"]["url"].startswith("data:image/")


def test_content_builder_sets_role_on_first_last_frame():
    """文档约定：图生视频-首尾帧场景必须给 role；首帧 role='first_frame'，
    尾帧 role='last_frame'。"""
    from services.volcengine_seedance import _build_content_payload
    parts = _build_content_payload(
        "scene",
        first_frame_b64="first_b64",
        last_frame_b64="last_b64",
        use_image=True,
    )
    img_parts = [p for p in parts if p["type"] == "image_url"]
    assert len(img_parts) == 2
    assert img_parts[0].get("role") == "first_frame"
    assert img_parts[1].get("role") == "last_frame"
    # 单图（首帧）也显式打 role=first_frame —— 文档说"或不填"，我们显式更稳
    parts2 = _build_content_payload("s", first_frame_b64="f", use_image=True)
    img2 = [p for p in parts2 if p["type"] == "image_url"]
    assert len(img2) == 1
    assert img2[0].get("role") == "first_frame"


def test_post_body_includes_new_way_parameters():
    """request body 必须包含 resolution / ratio / duration / generate_audio
    等顶层字段（新方式，强校验）。"""
    from services import volcengine_seedance as vs

    captured = {}

    class _FakeResp:
        status_code = 200
        def json(self): return {"id": "task_x"}

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, *, headers, json):
            captured["url"]     = url
            captured["headers"] = headers
            captured["body"]    = json
            return _FakeResp()

    with patch.object(vs.httpx, "AsyncClient", return_value=_FakeClient()):
        async def _go():
            return await vs._post_create_task(
                "https://ark.cn-beijing.volces.com/api/v3",
                "sk_test",
                model_id="doubao-seedance-2-0-260128",
                content=[{"type": "text", "text": "hello"}],
                resolution="1080p", duration=10,
                ratio="9:16", seed=42,
                camera_fixed=False, watermark=False,
                generate_audio=False,
            )
        asyncio.run(_go())

    body = captured["body"]
    assert body["model"] == "doubao-seedance-2-0-260128"
    assert body["resolution"] == "1080p"
    assert body["duration"]   == 10
    assert body["ratio"]      == "9:16"
    assert body["seed"]       == 42
    assert body["generate_audio"] is False
    assert "watermark" not in body or body["watermark"] is False
    # auth 头
    assert captured["headers"]["Authorization"] == "Bearer sk_test"
    # 端点 URL
    assert captured["url"].endswith("/contents/generations/tasks")


def test_status_mapping_recognizes_synonyms():
    """不同后端可能用 success / completed / processing 等同义词，
    必须收敛到我们的标准 5 状态之一。"""
    from services.volcengine_seedance import _get_task_status

    async def _go(raw_status):
        with patch("httpx.AsyncClient") as MockClient:
            mock_resp = SimpleNamespace(
                status_code=200,
                json=lambda: {"status": raw_status, "content": {"video_url": "x"}},
            )
            instance = AsyncMock()
            instance.__aenter__.return_value = instance
            instance.__aexit__.return_value = None
            instance.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = instance
            status, url, err = await _get_task_status("u", "k", "t")
            return status

    for raw, expected in [
        ("PENDING", "queued"), ("Processing", "running"),
        ("success", "succeeded"), ("Completed", "succeeded"),
        ("FAILED", "failed"), ("canceled", "cancelled"),
    ]:
        assert asyncio.run(_go(raw)) == expected, f"failed mapping {raw!r}"
