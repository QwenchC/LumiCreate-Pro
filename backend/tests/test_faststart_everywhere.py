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


def test_merge_fast_path_has_faststart():
    """v1.4.6+: 快路径已从 `-c copy` 改为干净再编码（WMP 兼容修复），但仍必须
    带 +faststart。这里改成在"快路径"特征 concat demuxer 后面找 +faststart。"""
    src = _read("routers/video_engine.py")
    matches = list(re.finditer(r'"-f",\s*"concat"', src))
    assert matches, "merge concat path not found"
    for m in matches:
        window = src[m.start():m.start() + 1200]
        assert "+faststart" in window, \
            f"concat at offset {m.start()} missing +faststart"


def test_merge_fast_path_no_longer_uses_codec_copy():
    """v1.4.6+ WMP 兼容修复硬约束：concat demuxer 后面**不能**出现 `-c copy`
    （-c copy 拼接对 LTX+slideshow 混合镜次会产出 WMP 拒播的 mp4）。
    必须真编码（libx264 / aac）让所有跨镜次时基差异被消化。"""
    src = _read("routers/video_engine.py")
    # 找到 fast-path concat 块，断言其窗口内必须有 libx264 + aac，不能有 -c copy
    matches = list(re.finditer(r'"-f",\s*"concat",\s*"-safe"', src))
    assert matches, "merge fast path concat not found"
    for m in matches:
        window = src[m.start():m.start() + 1500]
        assert '"-c", "copy"' not in window, \
            "fast path must NOT use -c copy (WMP regression)"
        assert "libx264" in window, "fast path must re-encode video"
        assert '"aac"' in window, "fast path must re-encode audio"


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


def test_merge_fast_path_has_bitrate_cap():
    """v1.4.6++ 用户主诉：合并视频"数据速率和总比特率过高"WMP 拒播。
    H.264 Level 4.0 上限 ~25Mbps，必须在快路径 concat re-encode 块加 maxrate
    / bufsize 上限（8M/16M 留足边距）。"""
    src = _read("routers/video_engine.py")
    matches = list(re.finditer(r'"-f",\s*"concat",\s*"-safe"', src))
    assert matches
    window = src[matches[0].start():matches[0].start() + 2500]
    assert '"-maxrate", "8M"' in window
    assert '"-bufsize", "16M"' in window


def test_merge_paths_have_aresample_async_for_av_sync():
    """v1.4.6++ 用户主诉：10min 视频音频比视频早 1min 结束（10% drift）。
    根因：concat + re-encode 时跨镜次边界音频 PTS 有 50-100ms 间隙，
    累积放大。修复：aresample=async=1000:first_pts=0 填补间隙。"""
    src = _read("routers/video_engine.py")
    # 快路径：在 -af 里
    fast_matches = list(re.finditer(r'"-f",\s*"concat",\s*"-safe"', src))
    assert fast_matches
    fast_window = src[fast_matches[0].start():fast_matches[0].start() + 2500]
    assert "aresample=async=1000:first_pts=0" in fast_window
    # 慢路径：在 filter_complex 节点里（不能用 -af on mapped label）
    slow_matches = list(re.finditer(r'"-filter_complex",\s*filter_complex', src))
    assert slow_matches
    # 慢路径 aresample 应作为 filter chain 末节，找文件中是否存在
    assert "aresample=async=1000:first_pts=0[afinal]" in src


def test_subtitle_burn_has_bitrate_cap():
    """烧字幕也加 maxrate/bufsize，跟 merge 一致避免 Level 4.0 超标。"""
    src = _read("services/subtitle.py")
    idx = src.find('subtitles=')
    window = src[idx:idx + 3000]
    assert "'-maxrate', '8M'" in window
    assert "'-bufsize', '16M'" in window
