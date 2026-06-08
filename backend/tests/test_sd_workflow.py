"""v1.4.4: sd_default_workflow 参数化 + 模型信息端点。"""
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]


def _load_wf() -> dict:
    p = REPO / "workflows" / "sd_default_workflow.json"
    if not p.exists():
        pytest.skip("sd_default_workflow not present")
    return json.loads(p.read_text(encoding="utf-8-sig"))


# ── 分类 / 白名单 ────────────────────────────────────────────────────────────


def test_sd_workflow_classified_as_t2i():
    from services.workflow_meta import classify_workflow, is_supported_image_workflow
    wf = _load_wf()
    assert classify_workflow("sd_default_workflow", workflow=wf) == "t2i"
    assert is_supported_image_workflow("sd_default_workflow", workflow=wf)


def test_sd_workflow_in_image_dropdown_via_bundled(isolated_app):
    client = isolated_app["client"]
    r = client.get("/api/image-engine/workflows")
    assert r.status_code == 200, r.text
    assert "sd_default_workflow" in r.json()


# ── patch_sd_workflow ───────────────────────────────────────────────────────


def test_patch_writes_checkpoint_and_sampler():
    from services.sd_workflow import patch_sd_workflow
    wf = _load_wf()
    out = patch_sd_workflow(
        wf, checkpoint="my_ckpt.safetensors",
        loras=[], steps=25, cfg=4.5,
        sampler_name="dpmpp_2m", scheduler="karras",
    )
    by_id = {n["id"]: n for n in out["nodes"]}
    assert by_id[17]["widgets_values"][0] == "my_ckpt.safetensors"
    ks = by_id[20]["widgets_values"]
    assert ks[2] == 25
    assert ks[3] == 4.5
    assert ks[4] == "dpmpp_2m"
    assert ks[5] == "karras"


def test_patch_with_two_loras_bypasses_unused_slots():
    """工作流有 7 个 LoRA 槽位，用户只用 2 个 → 剩下 5 个必须 mode=4 (bypass)
    才能在链路里穿透，不然 ComfyUI 会试图加载不存在的 LoRA 文件。"""
    from services.sd_workflow import patch_sd_workflow, SD_NODES
    wf = _load_wf()
    out = patch_sd_workflow(
        wf, loras=[
            {"name": "a.safetensors", "strength": 0.7},
            {"name": "b.safetensors", "strength": 0.5},
        ],
    )
    by_id = {n["id"]: n for n in out["nodes"]}
    # 前 2 个槽位被启用
    chain = SD_NODES["lora_chain"]
    assert by_id[chain[0]]["widgets_values"][:2] == ["a.safetensors", 0.7]
    assert by_id[chain[0]].get("mode", 0) == 0
    assert by_id[chain[1]]["widgets_values"][:2] == ["b.safetensors", 0.5]
    assert by_id[chain[1]].get("mode", 0) == 0
    # 剩余 5 个全部 bypass
    for nid in chain[2:]:
        assert by_id[nid].get("mode") == 4, \
            f"node {nid} should be bypassed, got mode={by_id[nid].get('mode')}"


def test_patch_with_zero_loras_bypasses_all():
    from services.sd_workflow import patch_sd_workflow, SD_NODES
    wf = _load_wf()
    out = patch_sd_workflow(wf, loras=[])
    by_id = {n["id"]: n for n in out["nodes"]}
    for nid in SD_NODES["lora_chain"]:
        assert by_id[nid].get("mode") == 4


def test_patch_treats_none_name_or_zero_weight_as_disabled():
    """name='None' 或 'none' 或 strength=0 → 视为禁用，节点 bypass。"""
    from services.sd_workflow import patch_sd_workflow, SD_NODES
    wf = _load_wf()
    out = patch_sd_workflow(wf, loras=[
        {"name": "real.safetensors", "strength": 0.6},
        {"name": "none",   "strength": 0.5},   # name 是 none → disabled
        {"name": "x.safetensors", "strength": 0},      # weight 0 → disabled
    ])
    by_id = {n["id"]: n for n in out["nodes"]}
    chain = SD_NODES["lora_chain"]
    assert by_id[chain[0]].get("mode", 0) == 0   # real enabled
    assert by_id[chain[1]].get("mode") == 4      # none → bypass
    assert by_id[chain[2]].get("mode") == 4      # weight 0 → bypass


def test_patch_does_not_mutate_input():
    from services.sd_workflow import patch_sd_workflow
    wf = _load_wf()
    orig = json.dumps(wf, sort_keys=True)
    _ = patch_sd_workflow(wf, checkpoint="x", loras=[{"name":"y","strength":0.5}],
                          steps=20, cfg=7, sampler_name="euler", scheduler="normal")
    after = json.dumps(wf, sort_keys=True)
    assert orig == after


# ── litegraph→API + bypass 穿透 ──────────────────────────────────────────────


def test_unused_lora_bypassed_in_api_with_correct_model_chain():
    """关键：bypass 的 LoRA 链必须正确穿透 model 引用，让 KSampler 看到的
    model 输入是最后一个 enabled LoRA（或 ckpt）的 model 输出。"""
    from services.sd_workflow import patch_sd_workflow, SD_NODES
    from services.comfyui import _litegraph_to_api
    wf = _load_wf()
    # 只用前 3 个 LoRA
    out = patch_sd_workflow(wf, loras=[
        {"name": "a.safetensors", "strength": 0.5},
        {"name": "b.safetensors", "strength": 0.5},
        {"name": "c.safetensors", "strength": 0.5},
    ])
    api = _litegraph_to_api(out)
    # KSampler 的 model 输入应当指向链上"最后一个 enabled LoRA"
    # 在 sd_default_workflow 里 chain = [10, 11, 13, 12, 14, 15, 16]
    # 前 3 个槽位 (10, 11, 13) enabled → KSampler.model 应当 = ["13", 0]
    ks = api["20"]["inputs"]
    expected_last_enabled = SD_NODES["lora_chain"][2]   # 13
    assert ks.get("model") == [str(expected_last_enabled), 0], \
        f"KSampler.model should bypass unused LoRAs to node {expected_last_enabled}, got {ks.get('model')}"
    # 4 个 bypassed 的 LoRA 不在 API
    for nid in SD_NODES["lora_chain"][3:]:
        assert str(nid) not in api, \
            f"bypassed LoRA node {nid} should not appear in API"


# ── /model-info ──────────────────────────────────────────────────────────────


def test_model_info_endpoint_handles_comfyui_down(isolated_app, monkeypatch):
    """ComfyUI 离线时 endpoint 不能 500，返回空列表 + error 字段。"""
    client = isolated_app["client"]
    r = client.get("/api/image-engine/model-info")
    assert r.status_code == 200, r.text
    d = r.json()
    # ComfyUI 没起 → checkpoints/loras 列表空
    assert isinstance(d.get("checkpoints"), list)
    assert isinstance(d.get("loras"), list)
    assert isinstance(d.get("samplers"), list)
    assert isinstance(d.get("schedulers"), list)


def test_model_info_endpoint_parses_object_info(isolated_app, monkeypatch):
    """正常工作时按 ComfyUI /object_info 的格式抽取 4 个枚举列表。"""
    import httpx

    fake_object_info = {
        "CheckpointLoaderSimple": {
            "input": {"required": {"ckpt_name": [["a.safetensors", "b.safetensors"], {}]}},
        },
        "LoraLoaderModelOnly": {
            "input": {"required": {"lora_name": [["lora_a.safetensors", "lora_b.safetensors"], {}]}},
        },
        "KSampler": {
            "input": {"required": {
                "sampler_name": [["euler", "euler_ancestral", "dpmpp_2m"], {}],
                "scheduler":    [["normal", "karras", "simple"], {}],
            }},
        },
    }

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return fake_object_info
    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, *a, **kw): return _Resp()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    client = isolated_app["client"]
    r = client.get("/api/image-engine/model-info")
    assert r.status_code == 200
    d = r.json()
    assert d["checkpoints"] == ["a.safetensors", "b.safetensors"]
    assert d["loras"]       == ["lora_a.safetensors", "lora_b.safetensors"]
    assert "euler" in d["samplers"]
    assert "karras" in d["schedulers"]
