"""v1.4.12 Ideogram 4 文生图工作流支持。

完全 additive：现有 t2i / i2i / SD / flux2 路径 0 修改。新增 image_ideogram4_t2i
作为白名单工作流 + _patch_workflow 专用注入分支（命中 Ideogram4PromptBuilderKJ
节点时把 caption JSON 写进 import_json 上游 + import_mode=always，并跳过通用
CLIPTextEncode literal 覆盖以保护子图里的 wire）。
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WF = REPO / "workflows" / "image_ideogram4_t2i.json"


def _load():
    return json.loads(WF.read_text(encoding="utf-8"))


def test_bundled_ideogram_workflow_exists_and_is_clean():
    """打包的工作流必须存在，且只有 1 个图片输出节点（剥掉了 KJ 预览 /
    debug showAnything / 孤儿 LoadImage，避免 _fetch_images 抓错图）。"""
    assert WF.is_file(), f"missing bundled workflow: {WF}"
    from services.comfyui import _litegraph_to_api
    api = _litegraph_to_api(_load())
    img_outs = [nid for nid, n in api.items()
                if n.get("class_type") in ("PreviewImage", "SaveImage")]
    assert len(img_outs) == 1, f"expected exactly 1 image output, got {img_outs}"


def test_ideogram_classifies_as_t2i():
    from services.workflow_meta import classify_workflow
    assert classify_workflow("image_ideogram4_t2i", workflow=_load()) == "t2i"


def test_ideogram_in_whitelist_and_supported():
    from services.workflow_meta import (
        SUPPORTED_IMAGE_WORKFLOWS, is_supported_image_workflow,
    )
    assert "image_ideogram4_t2i" in SUPPORTED_IMAGE_WORKFLOWS
    assert is_supported_image_workflow("image_ideogram4_t2i", workflow=_load())


def test_patcher_injects_caption_into_stringconstant_and_flips_import_mode():
    """核心：caption JSON 写进 StringConstantMultiline.string，KJ.import_mode→always，
    且子图里 CLIPTextEncode.text 的 wire 保持不变（不被通用 patcher 用 literal 覆盖）。"""
    from services.comfyui import _patch_workflow
    caption = ('{"high_level_description":"a cat",'
               '"compositional_deconstruction":{"background":"bg","elements":[]}}')
    patched = _patch_workflow(_load(), caption, "", seed=123)

    string_nodes = [n for n in patched.values()
                    if n.get("class_type") == "StringConstantMultiline"]
    assert string_nodes, "StringConstantMultiline missing after patch"
    assert string_nodes[0]["inputs"]["string"] == caption

    kj = [n for n in patched.values()
          if str(n.get("class_type", "")).startswith("Ideogram4PromptBuilder")]
    assert kj and kj[0]["inputs"]["import_mode"] == "always"
    # import_json 仍是 wire（指向 StringConstantMultiline），未被改成 literal
    assert isinstance(kj[0]["inputs"].get("import_json"), list)

    # 子图 CLIPTextEncode.text 仍是 wire ['169', 0]，没被 literal 覆盖
    clips = [n for n in patched.values()
             if n.get("class_type") == "CLIPTextEncode"]
    assert clips, "expected at least one CLIPTextEncode in subgraph"
    assert all(isinstance(c["inputs"].get("text"), list) for c in clips), \
        "CLIPTextEncode.text wire was clobbered by generic patcher"


def test_patcher_injects_seed_into_randomnoise():
    from services.comfyui import _patch_workflow
    patched = _patch_workflow(_load(), "{}", "", seed=777)
    rn = [n for n in patched.values() if n.get("class_type") == "RandomNoise"]
    assert rn and rn[0]["inputs"]["noise_seed"] == 777


def test_patcher_fills_kj_hidden_required_widgets():
    """KJ 节点的 3 个 UI 托管隐藏 widget（elements_data / style_palette_data /
    bg_brightness）不在 litegraph inputs 数组里 → 转换时丢失 → ComfyUI 校验报
    required_input_missing。patcher 必须补全（import_mode=always 下被 import_json
    覆盖，填安全默认即可）。"""
    from services.comfyui import _patch_workflow
    patched = _patch_workflow(_load(), "{}", "", seed=1)
    kj = next(n for n in patched.values()
              if str(n.get("class_type", "")).startswith("Ideogram4PromptBuilder"))
    ins = kj["inputs"]
    assert "elements_data" in ins
    assert "style_palette_data" in ins
    assert "bg_brightness" in ins
    # 类型合理：data 是字符串，brightness 是数值
    assert isinstance(ins["elements_data"], str)
    assert isinstance(ins["style_palette_data"], str)
    assert isinstance(ins["bg_brightness"], int)


def test_patcher_does_not_clobber_existing_kj_widgets():
    """已有值不动 setdefault：若转换后某隐藏 widget 已存在，patcher 不覆盖。"""
    from services.comfyui import _patch_workflow
    mini = {
        "1": {"class_type": "Ideogram4PromptBuilderKJ",
              "inputs": {"import_json": "", "import_mode": "when empty",
                         "elements_data": '[{"keep":1}]', "bg_brightness": 42}},
    }
    patched = _patch_workflow(mini, "CAP", "", seed=1)
    assert patched["1"]["inputs"]["elements_data"] == '[{"keep":1}]'  # 不动
    assert patched["1"]["inputs"]["bg_brightness"] == 42               # 不动
    assert patched["1"]["inputs"]["style_palette_data"] == "[]"        # 缺的补


def test_patcher_handles_unwired_import_json_fallback():
    """若 import_json 未接线（无上游），caption 直接写到 KJ.import_json 字面量。"""
    from services.comfyui import _patch_workflow
    # 构造一个最小 API 格式：KJ 节点 import_json 是字面量
    mini = {
        "1": {"class_type": "Ideogram4PromptBuilderKJ",
              "inputs": {"import_json": "", "import_mode": "when empty"}},
    }
    patched = _patch_workflow(mini, "CAPTION_X", "", seed=1)
    assert patched["1"]["inputs"]["import_json"] == "CAPTION_X"
    assert patched["1"]["inputs"]["import_mode"] == "always"


def test_non_ideogram_workflow_still_uses_cliptextencode_path():
    """回归保护：不含 KJ 节点的工作流仍走原 CLIPTextEncode literal 注入。"""
    from services.comfyui import _patch_workflow
    wf = {
        "10": {"class_type": "CLIPTextEncode",
               "inputs": {"text": "old", "clip": ["1", 0]},
               "_meta": {"title": "正面提示词"}},
        "11": {"class_type": "CLIPTextEncode",
               "inputs": {"text": "oldneg", "clip": ["1", 0]},
               "_meta": {"title": "负面提示词"}},
    }
    patched = _patch_workflow(wf, "NEWPOS", "NEWNEG", seed=5)
    assert patched["10"]["inputs"]["text"] == "NEWPOS"
    assert patched["11"]["inputs"]["text"] == "NEWNEG"


# ── v1.4.13: 分步 AI 生成 caption 端点 ───────────────────────────────────────


def _mock_llm(monkeypatch, response_text: str):
    """把 stream_chat 替换成固定输出。"""
    import routers.text_engine as te

    async def _fake_stream(cfg, system, user):
        yield response_text

    monkeypatch.setattr(te, "stream_chat", _fake_stream)


def test_caption_overview_step(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, json.dumps({
        "high_level_description": "A cat on a roof at dusk.",
        "background": "Tiled rooftops under an orange sky.",
        "style_description": {
            "aesthetics": "serene", "lighting": "golden hour",
            "photo": "85mm, f/2", "medium": "photograph",
            "color_palette": ["#FF6B35", "#2B2D42"],
        },
        "hallucinated_key": "should be dropped",
    }))
    r = client.post("/api/text-engine/generate-ideogram-caption", json={
        "description": "黄昏屋顶上的猫", "step": "overview", "style_type": "photo",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["step"] == "overview"
    data = body["data"]
    assert data["high_level_description"].startswith("A cat")
    assert "style_description" in data
    assert "hallucinated_key" not in data       # 幻觉字段被剥掉


def test_caption_elements_step_clamps_bboxes(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, json.dumps({"elements": [
        {"type": "obj", "bbox": [100, 200, 900, 800], "desc": "a cat"},
        {"type": "text", "bbox": [-50, 0, 200, 1500], "text": "MEOW", "desc": "title"},
        {"type": "obj", "bbox": [500, 500, 100, 600], "desc": "invalid bbox dropped"},
        {"type": "obj", "desc": "no bbox is fine"},
        "not-a-dict-skipped",
    ]}))
    r = client.post("/api/text-engine/generate-ideogram-caption", json={
        "description": "x", "step": "elements",
        "width": 1080, "height": 1920,
        "overview": {"background": "bg"},
    })
    assert r.status_code == 200, r.text
    els = r.json()["data"]["elements"]
    assert len(els) == 4                          # 字符串项被跳过
    assert els[0]["bbox"] == [100, 200, 900, 800]
    assert els[1]["bbox"] == [0, 0, 200, 1000]    # 越界夹紧
    assert els[1]["text"] == "MEOW"
    assert "bbox" not in els[2]                   # 非法 bbox 整个剥掉但元素保留
    assert "bbox" not in els[3]


def test_caption_rejects_empty_description(isolated_app):
    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-ideogram-caption", json={
        "description": "   ", "step": "overview",
    })
    assert r.status_code == 400


def test_caption_rejects_bad_step(isolated_app):
    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-ideogram-caption", json={
        "description": "x", "step": "everything",
    })
    assert r.status_code == 400


def test_caption_502_when_llm_returns_garbage(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "I cannot do that, sorry!")
    r = client.post("/api/text-engine/generate-ideogram-caption", json={
        "description": "x", "step": "overview",
    })
    assert r.status_code == 502
