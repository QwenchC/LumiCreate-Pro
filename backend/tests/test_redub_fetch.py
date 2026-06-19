"""v1.6: 视频后期成片【从磁盘取回】+ UI 节点 bypass 回归。

根因：RedubFinalize 是 OUTPUT_NODE 但只返回路径字符串、不进 ComfyUI /history → /view
取不到成片，导致『ComfyUI 实际成功、App 报失败』。改为从 output 磁盘按唯一前缀取最新 mp4。
"""
import base64
import glob
import json
from pathlib import Path

import pytest

from services.redub_video import (
    _find_redub_output_on_disk,
    patch_redub_workflow,
)

REPO = Path(__file__).resolve().parents[2]


def _load_redub() -> dict:
    files = glob.glob(str(REPO / "workflows" / "*识别分段*.json"))
    if not files:
        pytest.skip("redub workflow not present")
    return json.loads(Path(files[0]).read_text(encoding="utf-8"))


def test_find_output_on_disk_picks_newest_matching(tmp_path):
    # 造 ComfyUI 目录结构：<root>/input 与 <root>/output/redub
    inp = tmp_path / "input"; inp.mkdir()
    outdir = tmp_path / "output" / "redub"; outdir.mkdir(parents=True)
    prefix = "redub/lumi_redub_sceneX"
    # 旧文件（早于 since_ts）+ 新文件（晚于）
    old = outdir / "lumi_redub_sceneX_00001.mp4"; old.write_bytes(b"OLD")
    import os, time
    t0 = time.time()
    new = outdir / "lumi_redub_sceneX_00002.mp4"; new.write_bytes(b"NEWREDUB")
    os.utime(old, (t0 - 100, t0 - 100))   # 把旧文件压到 since_ts 之前
    os.utime(new, (t0 + 1, t0 + 1))

    got = _find_redub_output_on_disk(str(inp), prefix, since_ts=t0)
    assert got is not None
    assert got["filename"] == "lumi_redub_sceneX_00002.mp4"
    assert base64.b64decode(got["data"]) == b"NEWREDUB"


def test_find_output_on_disk_none_when_absent(tmp_path):
    inp = tmp_path / "input"; inp.mkdir()
    (tmp_path / "output" / "redub").mkdir(parents=True)
    import time
    assert _find_redub_output_on_disk(str(inp), "redub/nope", time.time()) is None


def test_patch_bypasses_ui_nodes():
    """ShowText / PreviewAudio 被 bypass(mode=4)，消除 extra_pnginfo 噪声错 + 省算力。"""
    wf = patch_redub_workflow(_load_redub(), input_video_filename="v.mp4",
                              video_full_path="/x/v.mp4", default_model="m.pth")
    for n in wf["nodes"]:
        t = str(n.get("type", ""))
        if "ShowText" in t or t == "PreviewAudio":
            assert n.get("mode") == 4, f"{t} 未被 bypass"
