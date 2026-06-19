"""v1.6: 去水印/去字幕 V2V 工作流 patch 测试。

在真实工作流上验证：输入视频名、最长边像素（MAX PIXEL SIZE）、save_output=True。
经 _litegraph_to_api 取解析后 inputs 断言，避免 widget 下标同义反复。
"""
import glob
import json
from pathlib import Path

import pytest

from services.watermark_video import (
    is_watermark_workflow,
    patch_watermark_workflow,
)

REPO = Path(__file__).resolve().parents[2]


def _load_wm() -> dict:
    files = glob.glob(str(REPO / "workflows" / "*去水印*.json"))
    if not files:
        pytest.skip("watermark workflow not present")
    return json.loads(Path(files[0]).read_text(encoding="utf-8"))


def _api(wf):
    from services.comfyui import _litegraph_to_api
    return _litegraph_to_api(wf)


def test_detects_watermark_workflow():
    assert is_watermark_workflow(_load_wm()) is True
    assert is_watermark_workflow({"nodes": [{"type": "KSampler"}]}) is False


def test_patch_sets_input_video_and_longest_edge():
    wf = patch_watermark_workflow(_load_wm(), input_video_filename="clip.mp4",
                                  longest_edge=720)
    # VHS_LoadVideoFFmpeg 的 video（dict widgets）
    ld = next(n for n in wf["nodes"] if n.get("type") == "VHS_LoadVideoFFmpeg")
    assert ld["widgets_values"]["video"] == "clip.mp4"
    # MAX PIXEL SIZE 的 INTConstant 被设成 720
    pix = next(n for n in wf["nodes"] if n.get("type") == "INTConstant"
               and "PIXEL" in str(n.get("title", "")).upper())
    assert pix["widgets_values"][0] == 720


def test_patch_enables_save_output():
    wf = patch_watermark_workflow(_load_wm(), input_video_filename="c.mp4",
                                  longest_edge=960)
    vc = next(n for n in wf["nodes"] if n.get("type") == "VHS_VideoCombine")
    assert vc["widgets_values"]["save_output"] is True


def test_patch_longest_edge_via_api_resolves():
    """经 _litegraph_to_api 后，VHS_LoadVideoFFmpeg.video 解析为我们设的文件名。"""
    wf = patch_watermark_workflow(_load_wm(), input_video_filename="zzz.mp4",
                                  longest_edge=1080)
    api = _api(wf)
    ld = next(n for n in api.values() if n["class_type"] == "VHS_LoadVideoFFmpeg")
    assert ld["inputs"].get("video") == "zzz.mp4"


def test_patch_does_not_mutate_input():
    wf = _load_wm()
    before = json.dumps(wf, ensure_ascii=False)
    patch_watermark_workflow(wf, input_video_filename="c.mp4", longest_edge=720)
    assert json.dumps(wf, ensure_ascii=False) == before
