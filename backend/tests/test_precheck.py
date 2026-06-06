"""D2 ComfyUI precheck：节点缺失检测 / 不可达 / 工作流不存在。"""
import pytest

from services.comfyui_precheck import PrecheckResult, precheck_image_workflow


# 构造一个最小 litegraph 风格 workflow
_DEMO_WORKFLOW = {
    "nodes": [
        {"id": 1, "type": "LoadImage", "widgets_values": ["a.png"]},
        {"id": 2, "type": "VAEEncode", "widgets_values": []},
        {"id": 3, "type": "SuperFancyCustomNode_2024",
         "widgets_values": ["my_lora.safetensors", "model.ckpt"]},
    ]
}


class _FakeCfg:
    workflow_dir = "/tmp/wf"


@pytest.mark.asyncio
async def test_workflow_missing_reports_workflow_missing(monkeypatch):
    """工作流读不到时返回明确错误。"""
    import services.comfyui_precheck as pc

    async def fake_get(cfg, name):
        return None
    monkeypatch.setattr(pc, "get_workflow_json", fake_get, raising=False)
    # 模块顶部 import — 用 patch services.comfyui 入口
    import services.comfyui as cu
    monkeypatch.setattr(cu, "get_workflow_json", fake_get)

    r = await precheck_image_workflow("http://localhost:8188", "nonexistent",
                                       image_cfg=_FakeCfg)
    assert r.ok is False
    assert any(i["type"] == "workflow_missing" for i in r.issues)


@pytest.mark.asyncio
async def test_comfyui_unreachable(monkeypatch):
    """ComfyUI 不在线时立刻给出明确错误。"""
    import services.comfyui as cu

    async def fake_wf(cfg, name):
        return _DEMO_WORKFLOW
    monkeypatch.setattr(cu, "get_workflow_json", fake_wf)

    # 把 httpx.AsyncClient.get 替换成永远失败
    import services.comfyui_precheck as pc

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kw):
            raise ConnectionError("ECONNREFUSED")
    monkeypatch.setattr(pc.httpx, "AsyncClient", lambda *a, **kw: _FakeClient())

    r = await precheck_image_workflow("http://localhost:8188", "demo", image_cfg=_FakeCfg)
    assert r.ok is False
    assert any(i["type"] == "comfyui_unreachable" for i in r.issues)


@pytest.mark.asyncio
async def test_missing_nodes_reported(monkeypatch):
    """object_info 缺某个 class_type 时点名报出。"""
    import services.comfyui as cu

    async def fake_wf(cfg, name):
        return _DEMO_WORKFLOW
    monkeypatch.setattr(cu, "get_workflow_json", fake_wf)

    import services.comfyui_precheck as pc

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kw):
            class _R:
                status_code = 200
                def raise_for_status(self): pass
                def json(_self):
                    # 只有 LoadImage / VAEEncode 在；缺 SuperFancyCustomNode_2024
                    return {"LoadImage": {}, "VAEEncode": {}}
            return _R()
    monkeypatch.setattr(pc.httpx, "AsyncClient", lambda *a, **kw: _FakeClient())

    r = await precheck_image_workflow("http://localhost:8188", "demo", image_cfg=_FakeCfg)
    assert r.ok is False
    miss = [i for i in r.issues if i["type"] == "missing_nodes"]
    assert miss
    assert "SuperFancyCustomNode_2024" in miss[0]["message"]
    # 模型引用统计也应有 2 个
    assert r.info.get("model_refs") == 2


@pytest.mark.asyncio
async def test_all_clear(monkeypatch):
    """全部 class_type 都在 → ok。"""
    import services.comfyui as cu

    async def fake_wf(cfg, name):
        return _DEMO_WORKFLOW
    monkeypatch.setattr(cu, "get_workflow_json", fake_wf)

    import services.comfyui_precheck as pc

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kw):
            class _R:
                status_code = 200
                def raise_for_status(self): pass
                def json(_self):
                    return {"LoadImage": {}, "VAEEncode": {},
                            "SuperFancyCustomNode_2024": {}}
            return _R()
    monkeypatch.setattr(pc.httpx, "AsyncClient", lambda *a, **kw: _FakeClient())

    r = await precheck_image_workflow("http://localhost:8188", "demo", image_cfg=_FakeCfg)
    assert r.ok is True
    assert r.issues == []
