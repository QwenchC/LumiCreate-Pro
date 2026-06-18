"""v1.6: MSR 多图参考视频工作流 patch 测试（Phase B）。

在真实 MSR 工作流 JSON 上验证确定性变换：尺寸/帧率/帧数、参考图槽位映射 + 多余 bypass、
正向提示词。
"""
import glob
import json
from pathlib import Path

import pytest

from services.msr_video import is_msr_workflow, patch_msr_workflow

REPO = Path(__file__).resolve().parents[2]


def _load_msr() -> dict:
    files = glob.glob(str(REPO / "workflows" / "MSR_*.json"))
    if not files:
        pytest.skip("MSR workflow not present in repo workflows/")
    return json.loads(Path(files[0]).read_text(encoding="utf-8"))


def _nodes(wf):
    return {n["id"]: n for n in wf["nodes"]}


def _link_src(wf, link_id):
    for l in wf.get("links", []):
        if l and l[0] == link_id:
            return l[1]
    return None


def _const_value_feeding(wf, target_type, input_name):
    """返回接到 target_type.input_name 的 INTConstant 的值。"""
    nodes = _nodes(wf)
    for n in wf["nodes"]:
        if n.get("type") != target_type:
            continue
        for inp in n.get("inputs") or []:
            if inp.get("name") == input_name:
                src = _link_src(wf, inp.get("link"))
                sn = nodes.get(src)
                if sn and sn.get("type") == "INTConstant":
                    return sn["widgets_values"][0]
    return None


def test_detects_msr_workflow():
    assert is_msr_workflow(_load_msr()) is True
    assert is_msr_workflow({"nodes": [{"type": "KSampler"}]}) is False


def test_patch_sets_size_and_frames():
    wf = patch_msr_workflow(
        _load_msr(), width=540, height=960, fps=24, duration_secs=5,
        prompt="two people talking in a park",
        char_files=["charA.png"], bg_file="bgX.png",
    )
    # EmptyLTXVLatentVideo 的 width/height/length 应来自被改写的 INTConstant
    assert _const_value_feeding(wf, "EmptyLTXVLatentVideo", "width") == 540
    assert _const_value_feeding(wf, "EmptyLTXVLatentVideo", "height") == 960
    assert _const_value_feeding(wf, "EmptyLTXVLatentVideo", "length") == 24 * 5  # 120


def test_patch_sets_fps():
    wf = patch_msr_workflow(_load_msr(), width=720, height=1280, fps=30,
                            duration_secs=4, char_files=["a.png"])
    for t, idx in (("CreateVideo", 0), ("LTXVConditioning", 0), ("LTXVEmptyLatentAudio", 1)):
        for n in wf["nodes"]:
            if n.get("type") == t:
                assert float(n["widgets_values"][idx]) == 30.0


def test_patch_maps_refs_and_bypasses_unused():
    """2 个角色参考 + 1 个背景 → 槽1/2 + background 启用、第3 槽 bypass。"""
    wf = patch_msr_workflow(_load_msr(), width=720, height=1280, fps=24,
                            duration_secs=5, char_files=["c1.png", "c2.png"],
                            bg_file="bg.png")
    nodes = _nodes(wf)
    licon = next(n for n in wf["nodes"] if n.get("type") == "LiconMSR")

    def loadimage_for(input_name):
        for inp in licon.get("inputs") or []:
            if inp.get("name") == input_name:
                src = _link_src(wf, inp.get("link"))
                return nodes.get(src)
        return None

    s1, s2, s3 = loadimage_for("1"), loadimage_for("2"), loadimage_for("3")
    bg = loadimage_for("background")
    assert s1["mode"] == 0 and s1["widgets_values"][0] == "c1.png"
    assert s2["mode"] == 0 and s2["widgets_values"][0] == "c2.png"
    assert s3["mode"] == 4                       # 未用 → bypass
    assert bg["mode"] == 0 and bg["widgets_values"][0] == "bg.png"


def test_patch_sets_positive_prompt():
    wf = patch_msr_workflow(_load_msr(), width=720, height=1280, fps=24,
                            duration_secs=5, prompt="A cat walks across",
                            char_files=["a.png"])
    nodes = _nodes(wf)
    cond = next(n for n in wf["nodes"] if n.get("type") == "LTXVConditioning")
    pos_link = next(i.get("link") for i in cond["inputs"] if i.get("name") == "positive")
    clip = nodes[_link_src(wf, pos_link)]
    assert clip["type"] == "CLIPTextEncode"
    assert clip["widgets_values"][0] == "A cat walks across"


def test_patch_does_not_mutate_input():
    wf = _load_msr()
    before = json.dumps(wf, ensure_ascii=False)
    patch_msr_workflow(wf, width=540, height=960, fps=24, duration_secs=5,
                       char_files=["a.png"])
    assert json.dumps(wf, ensure_ascii=False) == before   # 深拷贝，原图不动
