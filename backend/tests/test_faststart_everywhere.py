"""v1.4.6: 确保所有产出 mp4 的 ffmpeg 命令都带 -movflags +faststart。
这是 Windows Media Player 兼容的硬性要求 —— 缺一个 mp4 用户就有"播放器打不开"的复现。

覆盖的输出路径：
  1. 每镜子片（slideshow_video.build_scene_clip_cmd）
  2. 合并成片（video_engine.merge_project_video 快/慢路径）
  3. BGM 后期叠加（video_engine.mix_bgm_into_video）
  4. 字幕烧录（subtitle.burn_subtitles_command）
"""
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"


def _read(p): return (BACKEND / p).read_text(encoding="utf-8")


def test_slideshow_per_scene_clip_has_faststart():
    src = _read("services/slideshow_video.py")
    assert "+faststart" in src
    assert "movflags" in src


def test_merge_unified_filter_path_no_more_concat_demuxer():
    """v1.5.1: 合并统一走 filter_complex（逐镜 setpts 重定时），移除了不做重定时的
    concat demuxer 快路径 —— 否则无 BGM 合并画面仍偏快、音画不同步。"""
    src = _read("routers/video_engine.py")
    assert '"-f", "concat"' not in src, "merge 应已移除 concat demuxer 快路径"
    # 逐镜重定时到音频（消除 AI 视频非标准帧率导致的累积错位）
    assert "setpts=PTS*" in src, "merge 必须逐镜 setpts 重定时"


def test_merge_re_encodes_no_codec_copy():
    """合并输出必须真编码（libx264 / aac），不能 -c copy（WMP 拒播 + 无法配合 filter）。"""
    src = _read("routers/video_engine.py")
    idx = src.find('"-filter_complex", filter_complex')
    assert idx >= 0, "merge filter_complex 路径未找到"
    window = src[idx:idx + 1500]
    assert '"-c", "copy"' not in window, "merge must NOT use -c copy (WMP regression)"
    assert "libx264" in window, "merge must re-encode video"
    assert '"aac"' in window, "merge must re-encode audio"


def test_merge_slow_path_has_faststart():
    """xfade / BGM 慢路径（libx264 重编码）必须 +faststart。"""
    src = _read("routers/video_engine.py")
    # 在 libx264 编码块附近找（窗口放宽到 2000 — 加了 bitrate cap / colorspace /
    # aresample 等注释后编码块自然变长了）
    matches = list(re.finditer(r'"libx264"', src))
    assert matches
    for m in matches:
        window = src[m.start():m.start() + 2000]
        assert "+faststart" in window, \
            f"libx264 at offset {m.start()} missing +faststart within 2000 chars"


def test_subtitle_burn_has_faststart():
    """v1.4.6 用户主诉：烧字幕后的 final_video_subbed.mp4 WMP 不能播 —— 缺 faststart。"""
    src = _read("services/subtitle.py")
    assert "+faststart" in src, "subtitle burn must include +faststart"
    # 在 subtitle filter + libx264 的命令附近
    assert "subtitles=" in src


# ── v1.4.6++ WMP 数据速率限制 + A/V drift 修复 ─────────────────────────────


def test_merge_has_bitrate_cap():
    """合并 H.264 Level 4.0 上限 ~25Mbps，必须加 maxrate/bufsize（8M/16M）防 WMP 拒播。"""
    src = _read("routers/video_engine.py")
    idx = src.find('"-filter_complex", filter_complex')
    assert idx >= 0
    window = src[idx:idx + 2000]
    assert '"-maxrate", "8M"' in window
    assert '"-bufsize", "16M"' in window


def test_merge_has_aresample_async_for_av_sync():
    """合并 filter_complex 末节用 aresample=async 填补跨镜次音频 PTS 间隙。"""
    src = _read("routers/video_engine.py")
    assert "aresample=async=1000:first_pts=0[afinal]" in src


def test_subtitle_burn_has_bitrate_cap():
    """烧字幕也加 maxrate/bufsize，跟 merge 一致避免 Level 4.0 超标。"""
    src = _read("services/subtitle.py")
    idx = src.find('subtitles=')
    window = src[idx:idx + 3000]
    assert "'-maxrate', '8M'" in window
    assert "'-bufsize', '16M'" in window
