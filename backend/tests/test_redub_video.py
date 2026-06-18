"""v1.6: 视频后期【识别分段→逐条变声→换音轨】工作流 patch 测试（Phase C）。

在真实工作流 JSON 上验证确定性变换：LoadAudio 文件名、RedubAnalyze 的 whisper/语言、
RedubReVoice 的 voice_mapping/default_model/rvc 路径、RedubFinalize 的 video_path + finalize。
"""
import glob
import json
from pathlib import Path

import pytest

from services.redub_video import (
    is_redub_workflow,
    patch_redub_workflow,
    _REVOICE_W,
)

REPO = Path(__file__).resolve().parents[2]


def _load_redub() -> dict:
    files = glob.glob(str(REPO / "workflows" / "*识别分段*.json"))
    if not files:
        pytest.skip("redub workflow not present in repo workflows/")
    return json.loads(Path(files[0]).read_text(encoding="utf-8"))


def _first(wf, type_name):
    return next(n for n in wf["nodes"] if n.get("type") == type_name)


def _resolved_inputs(wf, class_type):
    """把 patch 后的 litegraph 真正过一遍 _litegraph_to_api，返回某类型节点【解析后】的
    inputs。直接断 widgets_values[idx] 是同义反复（写/读同一下标）；必须经 API 转换才能
    抓到 “widget 槽被连线占用导致整体右移” 这类 off-by-one。"""
    from services.comfyui import _litegraph_to_api
    api = _litegraph_to_api(wf)
    for n in api.values():
        if n["class_type"] == class_type:
            return n["inputs"]
    raise AssertionError(f"{class_type} not found in api")


def test_detects_redub_workflow():
    assert is_redub_workflow(_load_redub()) is True
    assert is_redub_workflow({"nodes": [{"type": "KSampler"}]}) is False


def test_patch_sets_loadaudio_and_finalize():
    wf = patch_redub_workflow(
        _load_redub(),
        input_video_filename="lumi_redub_s1.mp4",
        video_full_path="E:/comfy/input/lumi_redub_s1.mp4",
        default_model="keruanV1.pth",
    )
    assert _resolved_inputs(wf, "LoadAudio")["audio"] == "lumi_redub_s1.mp4"
    fin = _resolved_inputs(wf, "RedubFinalize")
    assert fin["video_path"] == "E:/comfy/input/lumi_redub_s1.mp4"
    assert fin["finalize"] is True                # finalize 必须 True 才写出


def test_patch_sets_revoice_model_and_mapping():
    """经 _litegraph_to_api 解析后，逐字段都要落到正确的 RedubReVoice 输入上
    （回归 voice_mapping off-by-one：project_dir 占了 widget 槽 [0]，整体右移一位）。"""
    wf = patch_redub_workflow(
        _load_redub(),
        input_video_filename="v.mp4", video_full_path="/x/v.mp4",
        default_model="alice.pth",
        voice_mapping="role1: alice.pth\nrole2: bob.pth",
        rvc_root="E:/RVC", rvc_python="E:/RVC/python.exe", device="cuda:1",
    )
    ins = _resolved_inputs(wf, "RedubReVoice")
    assert ins["voice_mapping"] == "role1: alice.pth\nrole2: bob.pth"
    assert ins["default_model"] == "alice.pth"
    assert ins["rvc_root"]   == "E:/RVC"
    assert ins["rvc_python"] == "E:/RVC/python.exe"
    assert ins["device"]     == "cuda:1"


def test_patch_empty_mapping_uses_single_default_for_consistency():
    """音色一致性：voice_mapping 留空 → 解析后必须是空串（而非残留帮助文本），
    所有分段才会都走 default_model。"""
    wf = patch_redub_workflow(
        _load_redub(),
        input_video_filename="v.mp4", video_full_path="/x/v.mp4",
        default_model="onevoice.pth",
    )
    ins = _resolved_inputs(wf, "RedubReVoice")
    assert ins["voice_mapping"] == ""          # 关键：不是工作流自带的帮助说明文本
    assert ins["default_model"] == "onevoice.pth"


def test_patch_sets_whisper_and_language():
    wf = patch_redub_workflow(
        _load_redub(),
        input_video_filename="v.mp4", video_full_path="/x/v.mp4",
        default_model="m.pth", whisper_model="large-v3", language="en",
    )
    an = _resolved_inputs(wf, "RedubAnalyze")
    assert an["whisper_model"] == "large-v3"
    assert an["language"] == "en"


def test_patch_preserves_defaults_when_not_overridden():
    """不传 rvc_root/whisper 等 → 保留工作流自带默认（不抹掉用户已配好的路径）。"""
    orig = _load_redub()
    rv_before = _first(orig, "RedubReVoice")["widgets_values"][_REVOICE_W["rvc_root"]]
    an_before = _first(orig, "RedubAnalyze")["widgets_values"][0]
    wf = patch_redub_workflow(
        orig, input_video_filename="v.mp4", video_full_path="/x/v.mp4",
        default_model="m.pth",
    )
    rv = _first(wf, "RedubReVoice")
    an = _first(wf, "RedubAnalyze")
    assert rv["widgets_values"][_REVOICE_W["rvc_root"]] == rv_before   # 未覆盖 → 保留
    assert an["widgets_values"][0] == an_before


def test_patch_does_not_mutate_input():
    wf = _load_redub()
    before = json.dumps(wf, ensure_ascii=False)
    patch_redub_workflow(wf, input_video_filename="v.mp4",
                         video_full_path="/x/v.mp4", default_model="m.pth")
    assert json.dumps(wf, ensure_ascii=False) == before   # 深拷贝，原图不动
