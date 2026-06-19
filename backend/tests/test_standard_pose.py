"""v1.6.1: 标准造型（Z-Image ControlNet）工作流 patch 测试。

经 _litegraph_to_api 取解析后 inputs 断言：姿势图 → LoadImage、正/负提示词、空白背景约束。
"""
import glob
import json
from pathlib import Path

import pytest

from services.standard_pose import (
    is_standard_pose_workflow,
    patch_standard_pose_workflow,
    build_standard_pose_prompt,
)

REPO = Path(__file__).resolve().parents[2]


def _load() -> dict:
    files = glob.glob(str(REPO / "workflows" / "Z-Image*.json"))
    if not files:
        pytest.skip("Z-Image workflow not present")
    return json.loads(Path(files[0]).read_text(encoding="utf-8"))


def _api(wf):
    from services.comfyui import _litegraph_to_api
    return _litegraph_to_api(wf)


def test_detects_workflow():
    assert is_standard_pose_workflow(_load()) is True
    assert is_standard_pose_workflow({"nodes": [{"type": "KSampler"}]}) is False


def test_pose_image_orientation_maps_to_files():
    """竖幅→character_default_pose_2.png（适配竖屏视频）；横幅→character_default_pose.png。"""
    from services.standard_pose import bundled_pose_image_path
    land = bundled_pose_image_path("landscape")
    port = bundled_pose_image_path("portrait")
    if land is None or port is None:
        pytest.skip("pose images not bundled in test env")
    assert land.name == "character_default_pose.png"
    assert port.name == "character_default_pose_2.png"
    # 默认（不传/未知）走横幅
    assert bundled_pose_image_path().name == "character_default_pose.png"


def test_blank_bg_prompt_always_present():
    p = build_standard_pose_prompt("银发少女，红色长裙", style="anime")
    assert "white background" in p and "empty background" in p
    assert "银发少女，红色长裙" in p and "anime" in p
    assert "full body" in p


def test_patch_sets_pose_and_prompts_via_api():
    wf = patch_standard_pose_workflow(
        _load(), pose_filename="lumi_pose_x.png",
        positive_prompt="white background, silver hair girl, full body",
        negative_prompt="scenery, blurry")
    api = _api(wf)
    # LoadImage 的 image 解析为姿势图文件名
    ld = next(n for n in api.values() if n["class_type"] == "LoadImage")
    assert ld["inputs"].get("image") == "lumi_pose_x.png"
    # KSampler.positive / .negative 指向被改写的 CLIPTextEncode
    ks = next(n for n in api.values() if n["class_type"] == "KSampler")
    pos_ref = ks["inputs"]["positive"]            # ["<id>", slot]
    neg_ref = ks["inputs"]["negative"]
    pos = api[pos_ref[0]]; neg = api[neg_ref[0]]
    assert pos["class_type"] == "CLIPTextEncode"
    assert "silver hair girl" in pos["inputs"]["text"]
    assert "scenery" in neg["inputs"]["text"]


def test_patch_does_not_touch_size():
    """ImageScaleByAspectRatio 'original' 自适应尺寸 —— 不应被改动。"""
    before = _load()
    sc_before = next(n for n in before["nodes"]
                     if "ImageScaleByAspectRatio" in str(n.get("type", "")))
    wf = patch_standard_pose_workflow(before, pose_filename="p.png",
                                      positive_prompt="x")
    sc_after = next(n for n in wf["nodes"]
                    if "ImageScaleByAspectRatio" in str(n.get("type", "")))
    assert sc_after["widgets_values"] == sc_before["widgets_values"]   # 尺寸节点未动


def test_patch_no_mutate_input():
    wf = _load()
    before = json.dumps(wf, ensure_ascii=False)
    patch_standard_pose_workflow(wf, pose_filename="p.png", positive_prompt="x")
    assert json.dumps(wf, ensure_ascii=False) == before


def test_patch_randomizes_seed_each_call():
    """KSampler 种子每次随机化 —— 否则每次生成同一张、无法重抽。"""
    base = _load()
    a = patch_standard_pose_workflow(base, pose_filename="p.png", positive_prompt="x")
    b = patch_standard_pose_workflow(base, pose_filename="p.png", positive_prompt="x")

    def _seed(wf):
        ks = next(n for n in wf["nodes"] if n.get("type") == "KSampler")
        return ks["widgets_values"][0]

    orig = _seed(base)
    assert _seed(a) != orig and _seed(b) != orig   # 已随机化（不再是工作流自带固定种子）
    assert _seed(a) != _seed(b)                      # 两次不同
    # 经 _litegraph_to_api 后种子确实进了 KSampler.inputs.seed
    ks = next(n for n in _api(a).values() if n["class_type"] == "KSampler")
    assert ks["inputs"]["seed"] == _seed(a)
