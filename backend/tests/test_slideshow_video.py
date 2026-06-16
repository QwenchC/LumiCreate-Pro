"""v1.4.6: 图片放映视频 — 单镜 ffmpeg 命令构造 + 端到端落盘协议。

不真跑 ffmpeg（无 GPU/无 ffmpeg 的 CI 也能跑），只验证：
  - 命令字符串里参数顺序正确
  - 1 张图 / 2 张图分支
  - 转场预设映射到合法 xfade transition 名
  - render_slideshow_project 跑完会写 videos.json
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


# ── build_scene_clip_cmd ────────────────────────────────────────────────────


def test_single_image_clip_loops_image_and_muxes_audio(tmp_path):
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "ff.png"; img.write_bytes(b"x")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"y")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg.exe",
        start_image=img, end_image=None, audio=aud,
        duration_ms=5000, output_path=out,
        width=1920, height=1080, fps=25,
    )
    # 关键 flag 都在
    assert "-loop" in cmd and "1" in cmd
    # v1.4.6++: 用 `-t duration_s` 取代 `-shortest`，让音视频末尾对齐到精确时间戳
    # 避免 AAC 编码器 priming 每镜次"丢"~50-100ms × N 镜次累积到大幅 drift
    assert "-shortest" not in cmd
    assert "libx264" in cmd
    assert "yuv420p" in cmd
    assert str(img) in cmd and str(aud) in cmd
    assert str(out) == cmd[-1]
    # 持续时间 = 5s
    assert "5.000" in cmd
    # 没有 filter_complex (单图静态不需要 xfade/zoompan)
    assert "-filter_complex" not in cmd
    # v1.4.6+: Windows Media Player 兼容套装
    assert "-movflags" in cmd and "+faststart" in cmd     # moov atom 提前
    assert "-preset" in cmd and "fast" in cmd              # 保守 preset
    assert "-profile:v" in cmd and "main" in cmd            # main profile (DXVA 友好)
    assert "-level" in cmd and "4.0" in cmd                 # level cap
    assert "yuv420p" in cmd                                  # 8-bit 4:2:0
    assert "bt709" in cmd                                    # 明确色域
    # 不再用 -tune stillimage（产出非常规 ME 参数，部分播放器拒绝）
    assert "stillimage" not in cmd
    # v1.4.6++: bitrate 上限（用户主诉数据速率过高→ WMP 拒播）
    assert "-maxrate" in cmd and "8M" in cmd
    assert "-bufsize" in cmd and "16M" in cmd
    # v1.4.6++: 音频 48k + aresample async（修复 60s drift）
    assert "-ar" in cmd and "48000" in cmd
    assert "-af" in cmd
    af_idx = cmd.index("-af")
    assert "aresample=async=1000" in cmd[af_idx + 1]


def test_two_image_clip_uses_xfade_with_correct_offset(tmp_path):
    """2 张图 + 5s 音频 + 800ms 转场：
    each = (5 + 0.8) / 2 = 2.9s；offset = 2.9 - 0.8 = 2.1s。"""
    from services.slideshow_video import build_scene_clip_cmd
    a = tmp_path / "a.png"; a.write_bytes(b"x")
    b = tmp_path / "b.png"; b.write_bytes(b"y")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"z")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg.exe",
        start_image=a, end_image=b, audio=aud,
        duration_ms=5000, output_path=out,
        width=1920, height=1080, fps=25,
        intra_transition="fade", intra_transition_ms=800,
    )
    assert "-filter_complex" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade" in fc
    assert "duration=0.800" in fc
    assert "offset=2.100" in fc
    # 双图都要 loop -t 2.9
    assert cmd.count("-loop") == 2
    assert cmd.count("2.900") == 2


def test_two_image_clip_maps_known_transition_names(tmp_path):
    from services.slideshow_video import build_scene_clip_cmd, TRANSITIONS
    a = tmp_path / "a.png"; a.write_bytes(b"x")
    b = tmp_path / "b.png"; b.write_bytes(b"y")
    out = tmp_path / "scene.mp4"
    for name in ("slideleft", "dissolve", "zoomin", "wipeleft"):
        cmd = build_scene_clip_cmd(
            "ffmpeg.exe", start_image=a, end_image=b, audio=None,
            duration_ms=3000, output_path=out,
            width=1280, height=720, fps=24,
            intra_transition=name, intra_transition_ms=500,
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert f"transition={TRANSITIONS[name]}" in fc


def test_unknown_transition_falls_back_to_fade(tmp_path):
    """非法转场名不能崩，回落到 fade（默认）。"""
    from services.slideshow_video import build_scene_clip_cmd
    a = tmp_path / "a.png"; a.write_bytes(b"x")
    b = tmp_path / "b.png"; b.write_bytes(b"y")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg.exe", start_image=a, end_image=b, audio=None,
        duration_ms=3000, output_path=out,
        width=1280, height=720, fps=24,
        intra_transition="not_a_real_one", intra_transition_ms=500,
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "transition=fade" in fc


def test_no_audio_branch_injects_silent_anullsrc(tmp_path):
    """v1.4.6+: 无真实音频时**注入静音 anullsrc**（不再 -an），让所有镜次
    mp4 流布局一致（视频+音频），concat -c copy 才不会产出损坏 mp4 ——
    用户主诉之一"编码设置不受支持"的诱因。"""
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "ff.png"; img.write_bytes(b"x")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg.exe", start_image=img, end_image=None, audio=None,
        duration_ms=4000, output_path=out,
        width=1920, height=1080, fps=25,
    )
    assert "-an" not in cmd                # 不再用 -an
    assert "anullsrc" in " ".join(cmd)     # 改为 lavfi 静音源
    assert "-c:a" in cmd and "aac" in cmd  # 编码为 AAC，保证统一
    # 2 个 -i 输入（图片 + 静音）
    assert cmd.count("-i") == 2


# ── render_slideshow_project 端到端 ─────────────────────────────────────────


def test_render_slideshow_writes_videos_json_and_skips_missing(
        isolated_app, tmp_path, monkeypatch):
    """整片渲染（mock ffmpeg）→ 必须更新 videos.json，并把缺图镜次列入 skipped。"""
    from services.db import get_conn
    pid = isolated_app["make_project"]()
    proj_dir = tmp_path / pid
    imgs = proj_dir / "images"; imgs.mkdir(exist_ok=True)
    auds = proj_dir / "audio";  auds.mkdir(exist_ok=True)

    # scene_a: 完整（首帧 + 音频）
    (imgs / "scene_a_start_0.png").write_bytes(b"png_a")
    (auds / "stitched_a.mp3").write_bytes(b"mp3_a")
    # scene_b: 缺首帧 → 跳过
    # scene_c: 完整（双帧）
    (imgs / "scene_c_start_0.png").write_bytes(b"png_c1")
    (imgs / "scene_c_end_0.png").write_bytes(b"png_c2")
    (auds / "stitched_c.mp3").write_bytes(b"mp3_c")

    # 在 scene_assets 里注册
    conn = get_conn(pid)
    for sid, asset_type, fp in [
        ("scene_a", "image_start", "images/scene_a_start_0.png"),
        ("scene_a", "audio",       "audio/stitched_a.mp3"),
        ("scene_c", "image_start", "images/scene_c_start_0.png"),
        ("scene_c", "image_end",   "images/scene_c_end_0.png"),
        ("scene_c", "audio",       "audio/stitched_c.mp3"),
    ]:
        meta = '{"duration_ms": 3000}' if asset_type == "audio" else "{}"
        conn.execute(
            "INSERT OR REPLACE INTO scene_assets("
            "  scene_id, asset_type, slot_index, file_path, format, "
            "  metadata_json, is_selected, created_at) "
            "VALUES(?,?,?,?,?,?,?, datetime('now'))",
            (sid, asset_type, 0, fp, "png" if "image" in asset_type else "mp3",
             meta, 1),
        )
    conn.commit()

    # mock subprocess.run（不真跑 ffmpeg）
    calls = []
    def _fake_run(cmd, *a, **kw):
        calls.append(cmd)
        # 写出空 .mp4 让 record_asset 满意
        out = Path(cmd[-1])
        out.write_bytes(b"\x00\x00\x00\x18ftypmp42mp42")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", _fake_run)

    from services.slideshow_video import render_slideshow_project
    result = render_slideshow_project(
        pid,
        proj_dir=proj_dir,
        scene_order=["scene_a", "scene_b", "scene_c"],
        ffmpeg_path="ffmpeg.exe",
        width=1920, height=1080, fps=25,
        intra_transition="fade", intra_transition_ms=800,
    )

    assert result["ok"] is True
    assert "scene_a" in result["rendered"]
    assert "scene_c" in result["rendered"]
    assert any(s["scene_id"] == "scene_b" for s in result["skipped"])
    # videos.json 落盘
    meta_path = proj_dir / "videos.json"
    assert meta_path.exists()
    data = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    assert data.get("scene_a") == "scene_a.mp4"
    assert data.get("scene_c") == "scene_c.mp4"
    # scene_c 的命令应当含 xfade（双帧分支）
    cmd_c = next(c for c in calls if "scene_c.mp4" in c[-1])
    assert "-filter_complex" in cmd_c
    assert "xfade=transition=fade" in cmd_c[cmd_c.index("-filter_complex") + 1]


# ── v1.4.6: Ken Burns 画面动态 + Windows 兼容 ──────────────────────────────


def test_all_clips_include_movflags_faststart(tmp_path):
    """v1.4.6 用户主诉：合并视频 WMP 不能播，浏览器能播 —— moov atom 在末尾。
    所有 ffmpeg 输出必须带 `-movflags +faststart`。"""
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    img2 = tmp_path / "b.png"; img2.write_bytes(b"y")
    out = tmp_path / "scene.mp4"

    # 单图静态
    c1 = build_scene_clip_cmd("ffmpeg", start_image=img, end_image=None,
                               audio=None, duration_ms=3000, output_path=out,
                               width=1280, height=720, fps=25)
    assert "+faststart" in c1
    # 单图 + 动态
    c2 = build_scene_clip_cmd("ffmpeg", start_image=img, end_image=None,
                               audio=None, duration_ms=3000, output_path=out,
                               width=1280, height=720, fps=25,
                               motion_effect="zoom_in")
    assert "+faststart" in c2
    # 双图
    c3 = build_scene_clip_cmd("ffmpeg", start_image=img, end_image=img2,
                               audio=None, duration_ms=4000, output_path=out,
                               width=1280, height=720, fps=25)
    assert "+faststart" in c3


def test_single_image_with_zoom_in_uses_zoompan_filter(tmp_path):
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "ff.png"; img.write_bytes(b"x")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg", start_image=img, end_image=None, audio=None,
        duration_ms=5000, output_path=out, width=1280, height=720, fps=25,
        motion_effect="zoom_in",
    )
    # 动态模式必须用 filter_complex（zoompan 自带 fps）
    assert "-filter_complex" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "zoompan=" in fc
    # zoom_in 表达式特征：z 从 1.0 增长
    assert "1.0+0.0008*on" in fc
    # 静态 -vf 通道不应出现
    assert "-vf" not in cmd


def test_all_motion_effects_produce_unique_zoompan_expressions(tmp_path):
    from services.slideshow_video import build_scene_clip_cmd, MOTION_EFFECTS
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    out = tmp_path / "scene.mp4"
    expressions = {}
    for m in MOTION_EFFECTS:
        if m == "none": continue
        cmd = build_scene_clip_cmd(
            "ffmpeg", start_image=img, end_image=None, audio=None,
            duration_ms=3000, output_path=out, width=1280, height=720, fps=25,
            motion_effect=m,
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "zoompan=" in fc
        expressions[m] = fc
    # 6 种动态应当各不相同
    assert len(set(expressions.values())) == 6


def test_unknown_motion_falls_back_to_static(tmp_path):
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg", start_image=img, end_image=None, audio=None,
        duration_ms=3000, output_path=out, width=1280, height=720, fps=25,
        motion_effect="not_real",
    )
    # 退回静态：用 -vf，无 zoompan
    assert "-vf" in cmd
    assert "-filter_complex" not in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "zoompan" not in vf


def test_two_image_with_motion_applies_to_both_images(tmp_path):
    """双图 + 动态：filter_complex 必须有两段 zoompan（每张图独立做 Ken Burns）
    然后才走 xfade。"""
    from services.slideshow_video import build_scene_clip_cmd
    a = tmp_path / "a.png"; a.write_bytes(b"x")
    b = tmp_path / "b.png"; b.write_bytes(b"y")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg", start_image=a, end_image=b, audio=None,
        duration_ms=5000, output_path=out, width=1280, height=720, fps=25,
        intra_transition="fade", intra_transition_ms=800,
        motion_effect="pan_right",
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.count("zoompan=") == 2   # [0:v] 和 [1:v] 各一个
    assert "[v0][v1]xfade" in fc


def test_motion_uses_4x_lanczos_prescale_for_anti_jitter(tmp_path):
    """v1.4.6+ 抖动修复：动态模式必须用 4× 预缩放 + lanczos。
    之前 1.2× 预缩放导致 zoompan 每帧映射落在亚像素位置 → 帧间整数取整 → 震动。
    """
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg", start_image=img, end_image=None, audio=None,
        duration_ms=5000, output_path=out,
        width=1920, height=1080, fps=25,
        motion_effect="zoom_in",
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    # 4× 预缩放（1920×4=7680, 1080×4=4320）
    assert "scale=7680:4320" in fc, f"missing 4x pre-scale, got: {fc[:200]}"
    # 高质量 lanczos
    assert "flags=lanczos" in fc, "lanczos flag is required for anti-jitter"


def test_parallel_renders_multiple_scenes_concurrently(
        isolated_app, tmp_path, monkeypatch):
    """v1.4.6+ CPU 利用率优化：并行 N 个 ffmpeg 镜次。
    用线程池验证：3 镜 + parallel=3 时，所有 3 个 ffmpeg 同时在跑。
    """
    import threading, time as _t
    from services.db import get_conn
    pid = isolated_app["make_project"]()
    proj_dir = tmp_path / pid
    imgs = proj_dir / "images"; imgs.mkdir(exist_ok=True)

    # 注册 3 个完整分镜
    conn = get_conn(pid)
    for i, sid in enumerate(["sA", "sB", "sC"]):
        (imgs / f"{sid}_start_0.png").write_bytes(b"png")
        conn.execute(
            "INSERT OR REPLACE INTO scene_assets(scene_id, asset_type, slot_index,"
            " file_path, format, metadata_json, is_selected, created_at) "
            "VALUES(?,?,?,?,?,?,?, datetime('now'))",
            (sid, "image_start", 0, f"images/{sid}_start_0.png", "png", "{}", 1),
        )
    conn.commit()

    # 用一个共享计数器证明并发：fake_run 进来 +1，离开 -1，记录峰值
    in_flight = [0]
    peak      = [0]
    lock = threading.Lock()
    def _fake_run(cmd, *a, **kw):
        with lock:
            in_flight[0] += 1
            peak[0] = max(peak[0], in_flight[0])
        _t.sleep(0.1)
        with lock:
            in_flight[0] -= 1
        Path(cmd[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42mp42")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", _fake_run)

    from services.slideshow_video import render_slideshow_project
    result = render_slideshow_project(
        pid, proj_dir=proj_dir,
        scene_order=["sA", "sB", "sC"],
        ffmpeg_path="ffmpeg.exe",
        width=1280, height=720, fps=25,
        parallel=3,    # 显式 3 并行
    )
    assert result["ok"] is True
    assert len(result["rendered"]) == 3
    assert result["parallel_workers"] == 3
    # 关键：峰值 == 3，证明确实在并行（不是排队跑）
    assert peak[0] == 3, f"in-flight peak {peak[0]} != 3 (expected concurrent)"


def test_parallel_workers_auto_detects_from_cpu_count(monkeypatch):
    """parallel=0 时按 _suggest_parallel_workers 算 = cpu_count // 4，cap [1,4]。"""
    import os
    from services.slideshow_video import _suggest_parallel_workers
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    assert _suggest_parallel_workers() == 4
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert _suggest_parallel_workers() == 2
    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    assert _suggest_parallel_workers() == 1
    monkeypatch.setattr(os, "cpu_count", lambda: 32)
    assert _suggest_parallel_workers() == 4   # cap


# ── v1.4.6+ Windows 兼容 + 音画同步 ─────────────────────────────────────────


def test_encode_settings_are_windows_player_safe(tmp_path):
    """v1.4.6+ 用户主诉：WMP 显示"编码设置不受支持"。
    所有编码都必须是 main profile + level 4.0 + bt709 + yuv420p + 无 stillimage tune。"""
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    out = tmp_path / "scene.mp4"
    for mot in ("none", "zoom_in", "pan_left"):
        cmd = build_scene_clip_cmd(
            "ffmpeg", start_image=img, end_image=None, audio=None,
            duration_ms=3000, output_path=out,
            width=1920, height=1080, fps=25, motion_effect=mot,
        )
        # main profile + level 4.0
        i = cmd.index("-profile:v"); assert cmd[i+1] == "main"
        i = cmd.index("-level");     assert cmd[i+1] == "4.0"
        # bt709 三件套
        assert "bt709" in cmd
        # 不能有 stillimage tune
        assert "stillimage" not in cmd


def test_render_uses_ffprobe_for_authoritative_audio_duration(
        isolated_app, tmp_path, monkeypatch):
    """v1.4.6+ 音画同步修复：实际音频时长以 ffprobe 为准，**忽略**
    scene_assets.metadata.duration_ms（TTS 请求时的"目标"时长，与真实产出
    经常差几十-几百 ms，累积起来音频比视频早结束，字幕走不完）。"""
    from services.db import get_conn
    pid = isolated_app["make_project"]()
    proj_dir = tmp_path / pid
    imgs = proj_dir / "images"; imgs.mkdir(exist_ok=True)
    auds = proj_dir / "audio";  auds.mkdir(exist_ok=True)
    (imgs / "s1_start_0.png").write_bytes(b"x")
    (auds / "s1.mp3").write_bytes(b"x")

    conn = get_conn(pid)
    # metadata 撒谎说 5000ms，但 ffprobe 会"真"说 4750ms
    for (at, fp, meta) in [
        ("image_start", "images/s1_start_0.png", "{}"),
        ("audio",       "audio/s1.mp3",          '{"duration_ms": 5000}'),
    ]:
        conn.execute(
            "INSERT OR REPLACE INTO scene_assets(scene_id, asset_type, slot_index,"
            " file_path, format, metadata_json, is_selected, created_at) "
            "VALUES(?,?,?,?,?,?,?, datetime('now'))",
            ("s1", at, 0, fp, "png" if "image" in at else "mp3", meta, 1),
        )
    conn.commit()

    # mock ffprobe → 4750ms（短于 metadata 的 5000）
    import services.slideshow_video as _sv
    monkeypatch.setattr(_sv, "_ffprobe_audio_duration_ms",
                        lambda *a, **kw: 4750)

    # mock ffmpeg
    captured = []
    def _fake_run(cmd, *a, **kw):
        captured.append(cmd)
        Path(cmd[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42mp42")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", _fake_run)

    _sv.render_slideshow_project(
        pid, proj_dir=proj_dir, scene_order=["s1"],
        ffmpeg_path="ffmpeg.exe", width=1280, height=720, fps=25,
    )
    cmd = captured[0]
    # 关键断言：用了 ffprobe 的 4.750s，没用 metadata 的 5.000s
    assert "4.750" in cmd, f"should use ffprobe 4750ms, got cmd: {cmd}"
    assert "5.000" not in cmd, "must not use stale metadata duration_ms"


def test_explicit_duration_t_replaces_shortest_for_av_sync(tmp_path):
    """v1.4.6++ A/V drift 修复：用户报 10min 视频音频比视频早 1min 结束。
    根因：`-shortest` + AAC priming 让每镜次音频 50-100ms 短于视频，N 镜次累积。
    修复：用显式 `-t duration_s` 让音视频末尾对齐到精确时间戳，并配合
    aresample=async 填补 priming 静音。"""
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"y")
    out = tmp_path / "scene.mp4"
    cmd1 = build_scene_clip_cmd(
        "ffmpeg", start_image=img, end_image=None, audio=aud,
        duration_ms=5000, output_path=out, width=1280, height=720, fps=25,
    )
    assert "-shortest" not in cmd1, "must drop -shortest (causes per-clip drift)"
    # 应有 2 个 `-t 5.000`：一个 image input，一个 output（音频截断到精确点）
    assert cmd1.count("5.000") >= 2
    # 双图分支
    img2 = tmp_path / "b.png"; img2.write_bytes(b"z")
    cmd2 = build_scene_clip_cmd(
        "ffmpeg", start_image=img, end_image=img2, audio=aud,
        duration_ms=5000, output_path=out, width=1280, height=720, fps=25,
    )
    assert "-shortest" not in cmd2
    # 双图分支末尾的 `-t 5.000` 输出截断也必须有
    assert "5.000" in cmd2


# ── v1.4.6++ concat 兼容 + 烧字幕同步 ─────────────────────────────────────────


def test_scene_clip_pins_uniform_timescale_for_concat_copy(tmp_path):
    """v1.4.6++ WMP 兼容关键：所有镜次 mp4 必须用相同的 video_track_timescale。
    单图分支走 -vf、动态分支走 zoompan(filter_complex) —— 默认 timebase 不同，
    concat -c copy 出来的 mp4 WMP 拒播。统一 90kHz 后所有镜次 mvhd 一致。"""
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    out = tmp_path / "scene.mp4"
    for mot in ("none", "zoom_in"):
        cmd = build_scene_clip_cmd(
            "ffmpeg", start_image=img, end_image=None, audio=None,
            duration_ms=3000, output_path=out,
            width=1920, height=1080, fps=25, motion_effect=mot,
        )
        assert "-video_track_timescale" in cmd
        i = cmd.index("-video_track_timescale")
        assert cmd[i+1] == "90000"
        # CFR 强制 + GOP 节奏（concat 边界对齐）
        assert "-vsync" in cmd and "cfr" in cmd
        assert "-g" in cmd


def test_subtitle_burn_reencodes_audio_to_fix_av_drift():
    """v1.4.6++ 用户主诉：烧字幕后音频提前放完字幕还在跑。
    根因：`-c:a copy` + 视频 re-encode → 视频 PTS 重新生成、音频保留旧 PTS，
    在 slideshow 标准 fps 上 drift 累积明显。
    修复：音频也走 AAC 48k 重编码，与视频共享 demux→encode 通路。"""
    src = (Path(__file__).resolve().parents[1] / "services" / "subtitle.py")\
        .read_text(encoding="utf-8")
    # 找到 burn cmd 块（subtitles= + libx264 之后的窗口）
    idx = src.find('subtitles=')
    assert idx > 0
    window = src[idx:idx + 2500]
    # 不能再有 -c:a copy
    assert "'-c:a', 'copy'" not in window, \
        "subtitle burn must NOT use -c:a copy (causes A/V drift on slideshow)"
    # 必须有 AAC 再编码
    assert "'-c:a', 'aac'" in window
    assert "'-ar', '48000'" in window
    # 必须有 fflags +genpts 消除上游 PTS 漂移
    assert "+genpts" in src
    # 必须显式 CFR + 统一 timescale
    assert "'-vsync', 'cfr'" in window
    assert "'-video_track_timescale', '90000'" in window
    # Windows-safe 编码档
    assert "'main'" in window and "'4.0'" in window


# ── v1.4.6++ A/V drift + bitrate ceiling regression ──────────────────────────


def test_per_scene_clip_pins_48k_audio_and_aresample_async(tmp_path):
    """A/V drift 修复硬约束（用户主诉：10min 视频音频早 1min 结束）：
    - 音频统一 48kHz（与 merge / burn 一致 → 全链路无重采样）
    - `aresample=async=1000:first_pts=0` 在每镜起点用静音填 PTS 间隙
    - 用显式 -t 取代 -shortest（避免 -shortest 在 AAC priming 上累积截断）
    """
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"y")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg", start_image=img, end_image=None, audio=aud,
        duration_ms=5000, output_path=out, width=1280, height=720, fps=25,
    )
    # 48kHz 全链路对齐
    i = cmd.index("-ar"); assert cmd[i+1] == "48000"
    # aresample 滤镜
    assert "-af" in cmd
    af_chain = cmd[cmd.index("-af") + 1]
    assert "aresample=async=1000:first_pts=0" == af_chain or \
           af_chain.endswith("aresample=async=1000:first_pts=0")
    # 显式 -t 控制末尾，不再依赖 -shortest
    # （单图分支：第一个 -t 是 input image 时长，必须存在第二个 -t 给 output）
    t_indices = [i for i, x in enumerate(cmd) if x == "-t"]
    assert len(t_indices) >= 1


def test_per_scene_clip_enforces_wmp_bitrate_ceiling(tmp_path):
    """用户主诉：合并视频"数据速率/总比特率过高" → WMP 拒播。
    每镜次必须 maxrate 8M + bufsize 16M（Level 4.0 安全边界）。"""
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg", start_image=img, end_image=None, audio=None,
        duration_ms=3000, output_path=out, width=1920, height=1080, fps=25,
    )
    assert "-maxrate" in cmd
    i = cmd.index("-maxrate"); assert cmd[i+1] == "8M"
    assert "-bufsize" in cmd
    i = cmd.index("-bufsize"); assert cmd[i+1] == "16M"


def test_merge_re_encode_paths_have_aresample_async():
    """v1.5.1: merge 统一 filter_complex 路径，末节用 aresample=async 修跨镜次 A/V drift。"""
    src = (Path(__file__).resolve().parents[1] / "routers" / "video_engine.py")\
        .read_text(encoding="utf-8")
    assert "aresample=async=1000:first_pts=0[afinal]" in src


def test_merge_paths_enforce_wmp_bitrate_ceiling():
    src = (Path(__file__).resolve().parents[1] / "routers" / "video_engine.py")\
        .read_text(encoding="utf-8")
    idx = src.find('"-filter_complex", filter_complex')
    assert idx >= 0
    win = src[idx:idx + 2000]
    assert '"-maxrate", "8M"' in win
    assert '"-bufsize", "16M"' in win


# ── v1.4.8 SFX overlays ─────────────────────────────────────────────────────


def test_sfx_overlay_adds_inputs_and_amix_filter_complex(tmp_path):
    """带 SFX 时单图分支必须：
    - 把 SFX 作为额外 -i 输入追加
    - 用 filter_complex 串接 video + adelay/volume + amix
    - 不再单独走 -af（音频流被 fc 替换）"""
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"y")
    sfx1 = tmp_path / "s1.mp3"; sfx1.write_bytes(b"a")
    sfx2 = tmp_path / "s2.mp3"; sfx2.write_bytes(b"b")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg", start_image=img, end_image=None, audio=aud,
        duration_ms=5000, output_path=out, width=1280, height=720, fps=25,
        sfx_overlays=[
            {"path": sfx1, "offset_ms": 1200, "volume_db": -8},
            {"path": sfx2, "offset_ms": 3500, "volume_db": -10},
        ],
    )
    # 两个 SFX 作为新增 -i
    assert str(sfx1) in cmd
    assert str(sfx2) in cmd
    # filter_complex 节点齐全
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "adelay=1200|1200" in fc
    assert "adelay=3500|3500" in fc
    assert "volume=-8.0dB" in fc
    assert "volume=-10.0dB" in fc
    # amix 节点存在，输入数 = 1 主音轨 + 2 SFX
    assert "amix=inputs=3" in fc
    # 输出标签 [aout] 被 map
    assert cmd.count("-map") >= 2
    map_targets = [cmd[i+1] for i, x in enumerate(cmd) if x == "-map"]
    assert "[aout]" in map_targets


def test_sfx_overlay_two_image_branch(tmp_path):
    """2 图 xfade 分支也能叠 SFX，主音轨索引是 [2:a]，SFX 从 [3:a] 起。"""
    from services.slideshow_video import build_scene_clip_cmd
    a = tmp_path / "a.png"; a.write_bytes(b"x")
    b = tmp_path / "b.png"; b.write_bytes(b"y")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"z")
    sfx = tmp_path / "s.mp3"; sfx.write_bytes(b"k")
    out = tmp_path / "scene.mp4"
    cmd = build_scene_clip_cmd(
        "ffmpeg", start_image=a, end_image=b, audio=aud,
        duration_ms=5000, output_path=out, width=1280, height=720, fps=25,
        sfx_overlays=[{"path": sfx, "offset_ms": 500, "volume_db": -5}],
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    # xfade + SFX 必须并存
    assert "xfade=" in fc
    assert "[2:a]aresample" in fc       # 主音轨索引 2
    assert "[3:a]adelay=500|500" in fc   # SFX 索引 3
    assert "amix=inputs=2" in fc


def test_no_sfx_overlay_uses_legacy_fast_path(tmp_path):
    """sfx_overlays=None / [] 时必须保持原快路径（-af aresample；不进 fc）。"""
    from services.slideshow_video import build_scene_clip_cmd
    img = tmp_path / "a.png"; img.write_bytes(b"x")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"y")
    out = tmp_path / "scene.mp4"
    for sfx in (None, []):
        cmd = build_scene_clip_cmd(
            "ffmpeg", start_image=img, end_image=None, audio=aud,
            duration_ms=3000, output_path=out, width=1280, height=720, fps=25,
            sfx_overlays=sfx,
        )
        # 没有 SFX -i 输入
        assert "amix" not in " ".join(cmd)
        # -af aresample 仍在
        assert "-af" in cmd
        af = cmd[cmd.index("-af") + 1]
        assert "aresample=async=1000:first_pts=0" in af


def test_render_loads_sfx_timeline_and_passes_overlays(
        isolated_app, tmp_path, monkeypatch):
    """render_slideshow_project 必须读 sfx_timeline.json + 把 overlays 传给
    每个 build_scene_clip_cmd。缺失的 sfx_id 静默跳过，不让整片崩。"""
    from services.db import get_conn, get_global_sfx_conn, global_sfx_root
    from datetime import datetime, timezone
    pid = isolated_app["make_project"]()
    proj_dir = tmp_path / pid
    imgs = proj_dir / "images"; imgs.mkdir(exist_ok=True)
    auds = proj_dir / "audio";  auds.mkdir(exist_ok=True)
    (imgs / "s1_start_0.png").write_bytes(b"x")
    (auds / "s1.mp3").write_bytes(b"y")

    conn = get_conn(pid)
    for at, fp in [("image_start", "images/s1_start_0.png"),
                   ("audio",       "audio/s1.mp3")]:
        conn.execute(
            "INSERT OR REPLACE INTO scene_assets(scene_id, asset_type, slot_index,"
            " file_path, format, metadata_json, is_selected, created_at) "
            "VALUES(?,?,?,?,?,?,?, datetime('now'))",
            ("s1", at, 0, fp, "png" if "image" in at else "mp3", "{}", 1),
        )
    conn.commit()

    # 全局 SFX 库塞一个 clip
    sfx_root = global_sfx_root()
    sfx_file = sfx_root / "test_clip.mp3"
    sfx_file.write_bytes(b"\x00" * 512)
    sconn = get_global_sfx_conn()
    sconn.execute(
        "INSERT INTO sfx_clips(name, category, file_path, mime, duration_ms,"
        " tags, bytes, created_at) VALUES(?,?,?,?,?,?,?,?)",
        ("test", "uncategorized", "test_clip.mp3", "audio/mpeg", 500,
         "", 512, datetime.now(timezone.utc).isoformat()),
    )
    sconn.commit()
    sfx_id = sconn.execute("SELECT id FROM sfx_clips WHERE name='test'").fetchone()["id"]

    # 写时间轴：s1 用真 sfx_id + 一个不存在的 999（应被静默跳过）
    (proj_dir / "sfx_timeline.json").write_text(
        json.dumps({
            "s1": [
                {"sfx_id": sfx_id, "offset_ms": 1000, "volume_db": -6},
                {"sfx_id": 999,    "offset_ms": 2000, "volume_db": -8},
            ],
        }), encoding="utf-8",
    )

    captured = []
    def _fake_run(cmd, *a, **kw):
        captured.append(cmd)
        Path(cmd[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42mp42")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", _fake_run)
    import services.slideshow_video as _sv
    monkeypatch.setattr(_sv, "_ffprobe_audio_duration_ms",
                        lambda *a, **kw: 3000)

    _sv.render_slideshow_project(
        pid, proj_dir=proj_dir, scene_order=["s1"],
        ffmpeg_path="ffmpeg.exe", width=1280, height=720, fps=25,
    )
    # 真 sfx 文件出现在 cmd；999 没有
    cmd = captured[0]
    assert str(sfx_file) in cmd
    # adelay 1000 来自有效 overlay；2000 应被丢弃
    fc_idx = cmd.index("-filter_complex")
    fc = cmd[fc_idx + 1]
    assert "adelay=1000|1000" in fc
    assert "adelay=2000|2000" not in fc

    # 清理全局 SFX 库（避免污染其它测试 run）
    sconn.execute("DELETE FROM sfx_clips WHERE id=?", (sfx_id,))
    sconn.commit()
    sfx_file.unlink(missing_ok=True)
