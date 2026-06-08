"""v1.4.5: Pollinations 图片生成引擎 + 路由分派。"""
import asyncio
import base64
from types import SimpleNamespace


# ── URL 构造 ────────────────────────────────────────────────────────────────


def test_build_url_encodes_prompt_and_options():
    from services.pollinations_image import _build_url
    url = _build_url(
        "https://gen.pollinations.ai/",
        "a cat in space, masterpiece",
        model="flux", width=1024, height=1024, seed=42,
        api_key="sk_test123",
    )
    assert url.startswith("https://gen.pollinations.ai/image/")
    # prompt 编码（空格 / 逗号变 %）
    assert "a%20cat%20in%20space" in url
    assert "model=flux" in url
    assert "width=1024" in url
    assert "height=1024" in url
    assert "seed=42" in url
    assert "key=sk_test123" in url
    # v1.4.5+: 新版 API 校验严格，不再传 nologo / private（之前会触发 400 validation failed）
    assert "nologo" not in url
    assert "private" not in url


def test_build_url_without_seed_or_key():
    from services.pollinations_image import _build_url
    url = _build_url(
        "https://gen.pollinations.ai", "hi", model="kontext",
        width=512, height=512, seed=None, api_key="",
    )
    assert "seed=" not in url
    assert "key=" not in url


# ── generate_image_pollinations ──────────────────────────────────────────────


def test_generate_image_yields_completed_with_base64(monkeypatch):
    """完整流程 mock：queued → progress(可能) → completed{images:[{data:b64}]}。"""
    import httpx
    fake_png = b"\x89PNG\r\n\x1a\nfake_png_bytes"

    class _Resp:
        status_code = 200
        headers = {"content-type": "image/png"}
        content = fake_png
        text = ""
        def raise_for_status(self): pass
        def json(self): return {}
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url, headers=None): return _Resp()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    from services.pollinations_image import generate_image_pollinations

    async def _run():
        events = []
        async for ev in generate_image_pollinations(
            base_url="https://gen.pollinations.ai",
            api_key="sk_x", model="flux",
            prompt="cat", width=512, height=512, seed=7,
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    kinds = [e["event"] for e in events]
    assert kinds[0] == "queued"
    assert "completed" in kinds
    completed = next(e for e in events if e["event"] == "completed")
    assert completed["images"][0]["data"]
    # base64 解开应等于原图字节
    decoded = base64.b64decode(completed["images"][0]["data"])
    assert decoded == fake_png
    assert completed["images"][0]["type"] == "image/png"


def test_generate_image_returns_error_on_4xx(monkeypatch):
    import httpx

    class _Resp:
        status_code = 401
        headers = {"content-type": "application/json"}
        content = b'{"error":{"message":"Invalid API key"}}'
        text = '{"error":{"message":"Invalid API key"}}'
        def raise_for_status(self): pass
        def json(self): return {"error": {"message": "Invalid API key"}}
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url, headers=None): return _Resp()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    from services.pollinations_image import generate_image_pollinations

    async def _run():
        events = []
        async for ev in generate_image_pollinations(
            base_url="https://gen.pollinations.ai", api_key="sk_bad",
            model="flux", prompt="x", width=512, height=512,
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    last = events[-1]
    assert last["event"] == "error"
    assert "401" in last["message"]
    assert "Invalid API key" in last["message"]


def test_generate_image_returns_error_on_non_image_response(monkeypatch):
    """200 OK 但 content-type 不是 image/* 时不能假装成功。"""
    import httpx

    class _Resp:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"<html>maintenance</html>"
        text = "..."
        def raise_for_status(self): pass
        def json(self): return {}
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url, headers=None): return _Resp()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    from services.pollinations_image import generate_image_pollinations

    async def _run():
        events = []
        async for ev in generate_image_pollinations(
            base_url="https://gen.pollinations.ai", api_key="sk_x",
            model="flux", prompt="x", width=512, height=512,
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    last = events[-1]
    assert last["event"] == "error"
    assert "非图片" in last["message"] or "text/html" in last["message"]


# ── 模型列表 ────────────────────────────────────────────────────────────────


def test_fetch_models_parses_list_response(monkeypatch):
    import httpx
    fake = ["flux", "kontext", "gptimage"]
    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return fake
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url): return _Resp()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    from services.pollinations_image import fetch_pollinations_image_models
    models = asyncio.run(fetch_pollinations_image_models("https://gen.pollinations.ai"))
    assert set(models) == {"flux", "kontext", "gptimage"}


def test_fetch_models_falls_back_when_offline(monkeypatch):
    """请求失败时不抛，返回内置兜底列表（保证 UI 永远有可选项）。"""
    import httpx
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url): raise httpx.ConnectError("nope")
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    from services.pollinations_image import (
        fetch_pollinations_image_models, DEFAULT_POLLINATIONS_IMAGE_MODELS,
    )
    models = asyncio.run(fetch_pollinations_image_models("https://x"))
    assert models == DEFAULT_POLLINATIONS_IMAGE_MODELS


# ── 路由分派：engine_type 切换 ─────────────────────────────────────────────────


def test_workflow_info_for_pollinations_returns_t2i(isolated_app):
    """engine_type=pollinations 时 workflow-info 跳过 ComfyUI 工作流文件读取，
    直接返回 t2i shape + engine_type='pollinations'。"""
    cfg = isolated_app["settings"]
    cfg.image_engine.engine_type = "pollinations"
    cfg.image_engine.pollinations_base_url = "https://gen.pollinations.ai"
    cfg.image_engine.pollinations_api_key  = "sk_test"

    client = isolated_app["client"]
    r = client.get("/api/image-engine/workflow-info?workflow_name=flux")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["engine_type"] == "pollinations"
    assert d["kind"] == "t2i"
    assert d["ref_count"] == 0


def test_workflows_endpoint_returns_pollinations_models_when_pollinations(
        isolated_app, monkeypatch):
    """engine_type=pollinations 时 /workflows 直接返回 Pollinations 模型列表
    （而不是 bundled 工作流名）。"""
    cfg = isolated_app["settings"]
    cfg.image_engine.engine_type = "pollinations"

    async def fake_fetch(base_url):
        return ["flux", "kontext", "gptimage"]

    import services.pollinations_image
    monkeypatch.setattr(services.pollinations_image,
                        "fetch_pollinations_image_models", fake_fetch)

    client = isolated_app["client"]
    r = client.get("/api/image-engine/workflows")
    assert r.status_code == 200, r.text
    assert r.json() == ["flux", "kontext", "gptimage"]


def test_pollinations_test_endpoint_returns_message(isolated_app, monkeypatch):
    async def fake_test(base, key):
        return {"success": True, "message": "Pollinations 连接成功（key 类型: secret）"}

    import services.pollinations_image
    monkeypatch.setattr(services.pollinations_image,
                        "test_pollinations_connection", fake_test)

    client = isolated_app["client"]
    r = client.get("/api/image-engine/pollinations/test")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["success"] is True
    assert "secret" in d["message"]


def test_400_error_extracts_details_for_validation_failure(monkeypatch):
    """Real-world bug: 'Pollinations 400: Query parameter validation failed' 没有任何
    线索说哪个参数错了。改进后必须把 error.details / issues 也带出来。"""
    import httpx, asyncio
    class _Resp:
        status_code = 400
        headers = {"content-type": "application/json"}
        content = b''
        text = ''
        def raise_for_status(self): pass
        def json(self):
            return {"error": {
                "code": "BAD_REQUEST",
                "message": "Query parameter validation failed",
                "details": "Unknown query parameter: 'nologo'",
            }}
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url, headers=None): return _Resp()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    from services.pollinations_image import generate_image_pollinations
    async def _run():
        events = []
        async for ev in generate_image_pollinations(
            base_url="https://gen.pollinations.ai", api_key="sk_x",
            model="flux", prompt="x", width=512, height=512,
        ):
            events.append(ev)
        return events
    events = asyncio.run(_run())
    last = events[-1]
    assert last["event"] == "error"
    # 必须把 details 也暴露给用户/前端
    assert "validation failed" in last["message"].lower()
    assert "nologo" in last["message"]
