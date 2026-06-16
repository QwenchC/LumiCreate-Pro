"""v1.5.1 回归：字幕流水线按【视频流】时长封顶，避免成片"画面放完音频还在响"。

真因：normalize_video 产出的 fixed_cfr 保留了比画面长的音频(漫剧 TTS 常比画面长
几十毫秒~数秒)，烧字幕后 final_video_subbed 画面早结束、音频拖尾。修复：normalize
与 burn 都用视频流时长 -t 封顶。
"""
import re
from types import SimpleNamespace

import services.subtitle as sub


def test_normalize_video_caps_to_video_stream(monkeypatch):
    monkeypatch.setattr(sub, "probe_video_stream_duration", lambda *a, **k: 100.0)
    captured = {}

    def fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(sub.subprocess, "run", fake_run)
    sub.normalize_video("ffmpeg", "in.mp4", "out.mp4", fps=24)

    cmd = captured["cmd"]
    assert "-t" in cmd, f"normalize 必须按视频流时长封顶: {cmd}"
    assert cmd[cmd.index("-t") + 1] == "100.000"
    # 仍保留帧率标准化 + 音频重采样
    assert any("fps" in str(x) for x in cmd)
    assert "aresample=async=1" in cmd


def test_normalize_video_skips_cap_when_probe_fails(monkeypatch):
    """探测失败(0)时不封顶 → 安全回退，绝不把视频截没。"""
    monkeypatch.setattr(sub, "probe_video_stream_duration", lambda *a, **k: 0.0)
    captured = {}
    monkeypatch.setattr(sub.subprocess, "run",
                        lambda cmd, *a, **k: captured.update(cmd=cmd) or SimpleNamespace(returncode=0, stderr=b""))
    sub.normalize_video("ffmpeg", "in.mp4", "out.mp4")
    assert "-t" not in captured["cmd"]


def test_burn_subtitles_command_has_video_cap():
    """源码层保证 burn 的 ffmpeg 命令带视频流时长封顶。"""
    src = (sub.__file__)
    text = open(src, encoding="utf-8").read()
    # burn cmd 里存在按 _burn_vdur 的 -t 封顶
    assert re.search(r"_burn_vdur\s*>\s*0\.5", text), "burn 缺少视频流封顶守卫"
    assert re.search(r"'-t',\s*f'\{_burn_vdur", text), "burn cmd 缺少 -t 封顶"
