"""轮 1: ComfyUI subgraph 展平器 + 工作流分类。

直接用项目实际备份的工作流文件做集成测试——比纯 mock 更能反映真实场景。
"""
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / "workflows"


def _load_wf(name: str) -> dict:
    p = WORKFLOWS / name
    if not p.exists():
        pytest.skip(f"workflow {name} not present")
    return json.loads(p.read_text(encoding="utf-8-sig"))


# ── 分类 ──────────────────────────────────────────────────────────────────────

def test_classify_t2i_lumicreate():
    from services.workflow_meta import classify_workflow
    wf = _load_wf("t2i-lumicreate.json")
    assert classify_workflow("t2i-lumicreate", workflow=wf) == "t2i"


def test_classify_flux2_t2i():
    from services.workflow_meta import classify_workflow
    wf = _load_wf("image_flux2_text_to_image_9b.json")
    assert classify_workflow("image_flux2_text_to_image_9b",
                              workflow=wf) == "t2i"


def test_classify_flux2_i2i_edit():
    from services.workflow_meta import classify_workflow
    wf = _load_wf("image_flux2_klein_image_edit_9b_base.json")
    # 名字含 image_edit → 默认 i2i_single；但里头有 2 个 LoadImage → 节点扫描升级为 double
    kind = classify_workflow("image_flux2_klein_image_edit_9b_base",
                              workflow=wf)
    assert kind in ("i2i_single", "i2i_double")


def test_classify_video_flfa2i():
    from services.workflow_meta import classify_workflow
    wf = _load_wf("flfa2i-lumicreate.json")
    assert classify_workflow("flfa2i-lumicreate", workflow=wf) == "video"


def test_classify_pure_name_pattern():
    from services.workflow_meta import classify_workflow
    assert classify_workflow("custom_text_to_image_test") == "t2i"
    assert classify_workflow("my_i2i_workflow")            == "i2i_single"
    assert classify_workflow("video_v2v_clip")             == "video"


def test_classify_double_keyword():
    from services.workflow_meta import classify_workflow
    assert classify_workflow("flux_i2i_double_ref") == "i2i_double"


# ── 展平 ──────────────────────────────────────────────────────────────────────

def test_flatten_passthrough_when_no_subgraphs():
    """无 subgraph 时返回原对象（性能 + 兼容性）。"""
    from services.comfyui import _flatten_subgraphs
    wf = _load_wf("t2i-lumicreate.json")
    out = _flatten_subgraphs(wf)
    # 节点数完全不变
    assert len(out["nodes"]) == len(wf["nodes"])


def test_flatten_flux2_t2i_eliminates_uuid_nodes():
    """Flux.2 t2i 工作流展平后，原 UUID-type 节点必须消失。"""
    from services.comfyui import _flatten_subgraphs
    wf = _load_wf("image_flux2_text_to_image_9b.json")
    # 原工作流里有 UUID 类型的 subgraph 实例
    uuid_types_before = {
        n.get("type") for n in wf["nodes"]
        if isinstance(n.get("type"), str)
        and "-" in n["type"] and len(n["type"]) == 36
    }
    assert uuid_types_before, "test workflow should contain UUID subgraph instances"

    out = _flatten_subgraphs(wf)
    uuid_types_after = {
        n.get("type") for n in out["nodes"]
        if isinstance(n.get("type"), str)
        and "-" in n["type"] and len(n["type"]) == 36
    }
    assert not uuid_types_after, \
        f"flattening should remove all subgraph instances but {uuid_types_after} remain"


def test_flatten_flux2_t2i_brings_internal_nodes_to_top():
    """子图内部 Flux2Scheduler / SamplerCustomAdvanced 等节点应当展平到顶层。"""
    from services.comfyui import _flatten_subgraphs
    wf = _load_wf("image_flux2_text_to_image_9b.json")
    out = _flatten_subgraphs(wf)
    types = {n.get("type") for n in out["nodes"]}
    assert "SamplerCustomAdvanced" in types
    assert "VAEDecode" in types
    assert "Flux2Scheduler" in types


def test_flatten_preserves_top_level_save_image():
    """顶层 SaveImage 不能因为展平丢失。"""
    from services.comfyui import _flatten_subgraphs
    wf = _load_wf("image_flux2_text_to_image_9b.json")
    save_image_before = sum(1 for n in wf["nodes"] if n.get("type") == "SaveImage")
    out = _flatten_subgraphs(wf)
    save_image_after = sum(1 for n in out["nodes"] if n.get("type") == "SaveImage")
    assert save_image_after >= save_image_before


def test_flatten_image_edit_double_keeps_loadimages():
    """图生图双图工作流的两张 LoadImage 必须保留。"""
    from services.comfyui import _flatten_subgraphs
    wf = _load_wf("image_flux2_klein_image_edit_9b_base.json")
    loads_before = sum(1 for n in wf["nodes"] if n.get("type") == "LoadImage")
    out = _flatten_subgraphs(wf)
    loads_after = sum(1 for n in out["nodes"] if n.get("type") == "LoadImage")
    assert loads_after == loads_before, \
        f"LoadImage count should not change ({loads_before} → {loads_after})"


# ── workflow_meta.get_ref_image_nodes ─────────────────────────────────────────

def test_ref_nodes_from_workflow_scan():
    """没有 meta 时按 LoadImage 节点 id 升序作为参考图。"""
    from services.workflow_meta import get_ref_image_nodes
    wf = _load_wf("image_flux2_klein_image_edit_9b_base.json")
    refs = get_ref_image_nodes({}, workflow=wf)
    # 这个工作流有 2 个 LoadImage
    assert len(refs) == 2
    # 都是 {node_id, input_widget}
    for r in refs:
        assert "node_id" in r and isinstance(r["node_id"], int)
        assert "input_widget" in r


def test_ref_nodes_from_meta_overrides_scan():
    from services.workflow_meta import get_ref_image_nodes
    meta = {"ref_images": [
        {"node_id": 999, "input_widget": 1},
        {"node_id": 1000, "input_widget": 2},
    ]}
    refs = get_ref_image_nodes(meta, workflow=None)
    assert refs == [
        {"node_id": 999, "input_widget": 1},
        {"node_id": 1000, "input_widget": 2},
    ]


# ── 回归：subgraph 内部 link 重映射 ────────────────────────────────────────────

def test_flux2_edit_inner_node_inputs_remapped():
    """Real-world bug: cloned VAEDecode (inside subgraph 75) lost both samples
    and vae after flattening because inputs[*].link still pointed to old inner
    link ids 147/148 that no longer exist in the new flat link list.
    
    Verifies inputs[*].link entries reference link ids that actually exist."""
    from services.comfyui import _flatten_subgraphs
    wf = _load_wf("image_flux2_klein_image_edit_9b_base.json")
    flat = _flatten_subgraphs(wf)
    link_ids = {l[0] for l in (flat.get("links") or []) if isinstance(l, list)}
    for n in flat.get("nodes") or []:
        for inp in (n.get("inputs") or []):
            lk = inp.get("link")
            if lk is None: continue
            assert lk in link_ids, \
                f"node {n.get('id')} input {inp.get('name')!r} → link {lk} dangling " \
                f"(only {len(link_ids)} valid link ids in flat workflow)"


def test_flux2_edit_api_format_has_vae_decode_inputs():
    """Same bug from the API-format side: VAEDecode in API must have both
    'samples' and 'vae' inputs after litegraph→api conversion."""
    from services.comfyui import _litegraph_to_api
    wf = _load_wf("image_flux2_klein_image_edit_9b_base.json")
    api = _litegraph_to_api(wf)
    vae_decodes = [(nid, n) for nid, n in api.items()
                    if n.get("class_type") == "VAEDecode"]
    assert vae_decodes, "expected at least one VAEDecode in flux2 image-edit workflow"
    for nid, n in vae_decodes:
        ins = n.get("inputs") or {}
        assert "samples" in ins, f"VAEDecode {nid} missing 'samples' input → ComfyUI 400"
        assert "vae"     in ins, f"VAEDecode {nid} missing 'vae' input → ComfyUI 400"


def test_flux2_edit_partial_bypass_falls_back_to_widget():
    """Real-world bug: GetImageSize (sg75_100) is in mode==4 (bypass) but has
    1 input / 3 outputs. ComfyUI's bypass passes slot N input → slot N output;
    output slots 1 and 2 have no input partner, so consumers must fall back
    to their widget value. Previous behavior left dangling [sg75_100, 1]
    references → ComfyUI 400 'exception_during_inner_validation'."""
    from services.comfyui import _litegraph_to_api
    wf = _load_wf("image_flux2_klein_image_edit_9b_base.json")
    api = _litegraph_to_api(wf)

    # 1. bypassed GetImageSize must not be in the API
    assert "sg75_100" not in api, "bypassed node should be excluded from API"

    # 2. no remaining input may reference sg75_100 (or any other dead node)
    alive = set(api.keys())
    for nid, n in api.items():
        for inp_name, val in (n.get("inputs") or {}).items():
            if isinstance(val, list) and len(val) >= 1:
                assert val[0] in alive, \
                    f"node {nid} input {inp_name!r} references dead node {val[0]!r}"

    # 3. EmptyFlux2LatentImage / Flux2Scheduler should have height set to
    # something resolvable (either a live link or a widget value), not a dangling list
    for nid in ("sg75_66", "sg75_62"):
        if nid in api:
            for k, v in (api[nid].get("inputs") or {}).items():
                if isinstance(v, list):
                    assert v[0] in alive, f"{nid}.{k} dangling: {v}"


def test_flux2_edit_bypass_does_not_pass_type_mismatch():
    """Real-world bug: GetImageSize bypass would have passed IMAGE-typed image
    input through slot 0 to the INT-typed width output, producing
    ComfyUI 400 'return_type_mismatch: received_type(IMAGE) mismatch input_type(INT)'.
    The bypass must be type-aware: when input/output types don't match, drop
    the link entirely so the consumer falls back to its widget value."""
    from services.comfyui import _litegraph_to_api
    wf = _load_wf("image_flux2_klein_image_edit_9b_base.json")
    api = _litegraph_to_api(wf)

    # Flux2Scheduler width must be an int widget, not a link
    n62 = api.get("sg75_62") or {}
    w = (n62.get("inputs") or {}).get("width")
    assert isinstance(w, int), f"width should be widget int, got {w!r}"

    # EmptyFlux2LatentImage width must be widget int, not a link
    n66 = api.get("sg75_66") or {}
    w = (n66.get("inputs") or {}).get("width")
    assert isinstance(w, int), f"width should be widget int, got {w!r}"


def test_flux2_width_height_patching_t2i():
    """User-configured image size must flow into EmptyFlux2LatentImage AND
    Flux2Scheduler — both have width/height widgets and both must match the
    same resolution or scheduling will be miscalibrated."""
    from services.comfyui import _patch_workflow
    wf = _load_wf("image_flux2_text_to_image_9b.json")
    api = _patch_workflow(wf, "test", "", None, 1080, 1920)
    found_latent = found_scheduler = False
    for nid, n in api.items():
        if n["class_type"] == "EmptyFlux2LatentImage":
            assert n["inputs"]["width"]  == 1080, f"{nid} width not patched: {n['inputs']}"
            assert n["inputs"]["height"] == 1920, f"{nid} height not patched: {n['inputs']}"
            found_latent = True
        if n["class_type"] == "Flux2Scheduler":
            assert n["inputs"]["width"]  == 1080
            assert n["inputs"]["height"] == 1920
            found_scheduler = True
    assert found_latent, "EmptyFlux2LatentImage not present — workflow shape changed"
    assert found_scheduler, "Flux2Scheduler not present — workflow shape changed"


def test_flux2_width_height_patching_i2i():
    """Same for the image-edit workflow."""
    from services.comfyui import _patch_workflow
    wf = _load_wf("image_flux2_klein_image_edit_9b_base.json")
    api = _patch_workflow(wf, "test", "", None, 1080, 1920)
    n66 = api.get("sg75_66") or {}
    n62 = api.get("sg75_62") or {}
    assert n66.get("inputs", {}).get("width")  == 1080
    assert n66.get("inputs", {}).get("height") == 1920
    assert n62.get("inputs", {}).get("width")  == 1080
    assert n62.get("inputs", {}).get("height") == 1920


def test_classify_strict_rejects_noise_workflows():
    """v1.4.1+: 真实生产 bug —— 用户的 ComfyUI 目录里 27 个工作流全显示在下拉里，
    因为 classify_workflow 默认返回 't2i'。新的严格分类应让所有无明显证据的
    工作流返回 'unknown'，被支持过滤掉。"""
    from services.workflow_meta import classify_workflow, is_supported_image_workflow
    # 用户截图里的实际工作流名字（部分）
    noise = [
        "3d_hunyuan3d-v2.1",         # 3D 模型，不是图生
        "Bernini_testing_video_edit_01",   # video_edit → 视频
        "EasyFlow v1.5",             # 无任何关键词
        "LTX-2.3首尾帧+语音数字人",  # 视频
        "WanMove工作流",             # Wan 视频
        "Z-Image-万能局部重绘",     # 不在白名单
        "Z_Image 合集",              # 不在白名单
        "_temp_relay",               # 私有临时文件
        "canny_workflow",            # ControlNet 辅助
        "depth_workflow",            # ControlNet 辅助
        "fishaudio+ltx2.3",          # 视频（含 ltx）
        "hed_workflow",              # ControlNet 辅助
        "infinitetalk单人 I2V",      # 视频
        "video_wan2_2_14B_i2v",      # 视频
        "video_wan2_2_5B_ti2v",      # 视频
        "utility_sdpose_ood_image_to_pose",   # pose 估计
    ]
    for name in noise:
        kind = classify_workflow(name, workflow=None)
        # 这些都不能进图片下拉
        assert not is_supported_image_workflow(name, workflow=None), \
            f"{name!r} → kind={kind!r}, leaked into image dropdown"


def test_classify_strict_keeps_real_image_workflows():
    """正面：bundled 里那 3 个图片工作流仍然识别。"""
    import json
    from pathlib import Path
    from services.workflow_meta import classify_workflow, is_supported_image_workflow
    REPO = Path(__file__).resolve().parents[2]
    wd = REPO / "workflows"
    for name in ("t2i-lumicreate", "image_flux2_text_to_image_9b",
                 "image_flux2_klein_image_edit_9b_base"):
        wf = json.loads((wd / f"{name}.json").read_text(encoding="utf-8-sig"))
        assert is_supported_image_workflow(name, workflow=wf), \
            f"{name} should still pass image classifier"
