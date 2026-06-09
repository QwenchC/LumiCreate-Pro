"""v1.4.11+ 火山引擎 Seedream 图片引擎测试。

完全 additive：comfyui / pollinations 路径 0 修改，新增 volcengine_seedream
作为第 3 个 engine_type 分支。
"""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock


def test_image_config_defaults_preserve_comfyui():
    """老配置升上来：engine_type 默认 'comfyui'，seedream_* 默认空 → 0 改变。"""
    from config import ImageEngineConfig
    cfg = ImageEngineConfig()
    assert cfg.engine_type == "comfyui"
    assert cfg.seedream_api_key == ""
    assert cfg.seedream_model == ""
    assert cfg.seedream_base_url.startswith("https://ark.")


def test_workflows_returns_synthetic_name_in_seedream_mode(isolated_app):
    """engine_type='volcengine_seedream' 时 /workflows 返回合成名，
    不真去 ComfyUI 拉清单。"""
    client = isolated_app["client"]
    fake = isolated_app["settings"]
    fake.image_engine.engine_type = "volcengine_seedream"
    r = client.get("/api/image-engine/workflows")
    assert r.status_code == 200
    assert r.json() == ["volcengine_seedream"]


def test_workflow_info_returns_t2i_in_seedream_mode(isolated_app):
    """Seedream 没有 ComfyUI 工作流概念 → workflow-info 返合成 t2i shape，
    ref_count=0（前端隐藏参考图槽位）。"""
    client = isolated_app["client"]
    fake = isolated_app["settings"]
    fake.image_engine.engine_type = "volcengine_seedream"
    r = client.get("/api/image-engine/workflow-info?workflow_name=anything")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "t2i"
    assert body["ref_count"] == 0
    assert body["engine_type"] == "volcengine_seedream"


def test_test_endpoint_dispatches_to_seedream(isolated_app):
    client = isolated_app["client"]
    fake = isolated_app["settings"]
    fake.image_engine.engine_type = "volcengine_seedream"
    fake.image_engine.seedream_api_key = "k"

    async def _fake_test(*a, **kw):
        return True, "鉴权通过"

    with patch("services.volcengine_seedream.test_seedream_connection",
               new=AsyncMock(side_effect=_fake_test)):
        r = client.get("/api/image-engine/test")
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert "Seedream" in r.json()["message"]


def test_independent_seedream_test_endpoint(isolated_app):
    """/image-engine/seedream/test 不依赖 engine_type 切换，
    允许用户切换之前先测。"""
    client = isolated_app["client"]
    fake = isolated_app["settings"]
    fake.image_engine.engine_type = "comfyui"   # 仍在 ComfyUI 模式
    fake.image_engine.seedream_api_key = ""
    r = client.get("/api/image-engine/seedream/test")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False   # 没填 key
    assert "API" in body["message"] or "api" in body["message"].lower()


def test_seedream_driver_yields_completed_with_images_schema():
    """driver 必须吐出与 ComfyUI/Pollinations 一致的 schema:
    {event:'completed', images:[{filename, data, type}]}
    保证下游 image_engine.py 的批量处理逻辑不需要改。"""
    from services import volcengine_seedream as vs

    class _FakeResp:
        status_code = 200
        def json(self):
            return {"data": [{"url": "https://x/img.png"}]}

    class _FakeImgResp:
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        def raise_for_status(self): pass

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw): return _FakeResp()
        async def get(self, *a, **kw):  return _FakeImgResp()

    # 只 mock httpx；不要 mock asyncio.sleep（会污染 wait_for 内部）。
    # _tick 任务每 2s 推一次进度，请求几乎瞬时完成，主循环 0.5s timeout 后
    # 退出 → 测试约 0.5s 跑完。
    with patch.object(vs.httpx, "AsyncClient", _FakeClient):
        events = []
        async def _go():
            async for ev in vs.generate_image_seedream(
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key="k", model="doubao-seedream-5-0-260128",
                prompt="a cat",
            ):
                events.append(ev)
        asyncio.run(_go())

    assert events[0]["event"] == "queued"
    final = events[-1]
    assert final["event"] == "completed"
    assert "images" in final
    assert isinstance(final["images"], list)
    assert "data" in final["images"][0]
    assert final["images"][0]["type"] == "image/png"


def test_driver_yields_error_when_no_api_key():
    from services import volcengine_seedream as vs
    events = []
    async def _go():
        async for ev in vs.generate_image_seedream(
            base_url="https://x", api_key="", model="m", prompt="x",
        ):
            events.append(ev)
    asyncio.run(_go())
    assert events[0]["event"] == "error"
    assert "API Key" in events[0]["message"]


def test_driver_yields_error_when_no_model():
    from services import volcengine_seedream as vs
    events = []
    async def _go():
        async for ev in vs.generate_image_seedream(
            base_url="https://x", api_key="k", model="", prompt="x",
        ):
            events.append(ev)
    asyncio.run(_go())
    assert events[0]["event"] == "error"
    assert "模型" in events[0]["message"]
