"""v1.4.2: 后期 BGM 混音端点 — 输入校验 + ffmpeg 命令构造。"""
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


# ── 输入校验 ──────────────────────────────────────────────────────────────────


def test_mix_bgm_rejects_invalid_source(isolated_app):
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()
    r = client.post("/api/video-engine/mix-bgm", json={
        "project_id": pid,
        "source":     "garbage",   # 非法
        "track_id":   1,
    })
    assert r.status_code == 400
    assert "source" in r.text


def test_mix_bgm_rejects_missing_source_file(isolated_app):
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()
    # 项目存在但没合并视频
    r = client.post("/api/video-engine/mix-bgm", json={
        "project_id": pid,
        "source":     "final_video",
        "track_id":   1,
    })
    assert r.status_code in (404, 500)
    # 404 因为 final_video.mp4 不存在；500 因为找不到 ffmpeg (测试环境)
    # 两种都算合法路径，关键是不能 200


def test_mix_bgm_rejects_missing_track(isolated_app, tmp_path, monkeypatch):
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()
    # 造一个 final_video.mp4
    pdir = tmp_path / pid
    vdir = pdir / "video"; vdir.mkdir(exist_ok=True, parents=True)
    (vdir / "final_video.mp4").write_bytes(b"fake mp4")

    # 让 _find_ffmpeg 返回 fake 路径，避免因 ffmpeg 缺失先报错
    monkeypatch.setattr("routers.video_engine._find_ffmpeg",
                        lambda *a, **kw: "fake_ffmpeg")
    # 让 ffprobe 不真跑
    monkeypatch.setattr("routers.video_engine._ffprobe_duration_seconds",
                        lambda *a, **kw: 30.0)

    r = client.post("/api/video-engine/mix-bgm", json={
        "project_id": pid,
        "source":     "final_video",
        "track_id":   999999,   # 不存在
    })
    assert r.status_code == 404
    assert "track" in r.text.lower() or "音乐" in r.text


# ── ffmpeg 命令构造 ──────────────────────────────────────────────────────────


def test_mix_bgm_constructs_correct_ffmpeg_command(isolated_app, tmp_path, monkeypatch):
    """关键检查：filter_complex 包含 BGM 链 + 原音链 + amix；
    -c:v copy 保证视频流不重编码；-stream_loop -1 在 loop_bgm 时出现。
    """
    from services.db import get_global_music_conn, global_music_root
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()

    # 准备源视频 & BGM 文件
    pdir = tmp_path / pid
    vdir = pdir / "video"; vdir.mkdir(exist_ok=True, parents=True)
    (vdir / "final_video.mp4").write_bytes(b"fake")
    music_root = global_music_root()
    bgm_file = music_root / "fake_bgm.mp3"
    bgm_file.write_bytes(b"fake audio")

    conn = get_global_music_conn()
    conn.execute(
        "INSERT INTO tracks(name, file_path, mime, project_id, seed, duration_secs,"
        " bpm, time_signature, language, key_scale, tags, lyrics, bytes, created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("BGM1", "fake_bgm.mp3", "audio/mpeg", "", 1, 60,
         120, "4", "zh", "C major", "", "", 10,
         "2026-06-08T00:00:00+00:00"),
    )
    conn.commit()
    track_id = conn.execute("SELECT id FROM tracks WHERE name='BGM1'").fetchone()["id"]

    # Stub ffmpeg / ffprobe
    monkeypatch.setattr("routers.video_engine._find_ffmpeg",
                        lambda *a, **kw: "ffmpeg.exe")
    monkeypatch.setattr("routers.video_engine._ffprobe_duration_seconds",
                        lambda *a, **kw: 45.0)

    # Capture the ffmpeg command
    captured_cmd: list = []
    def _fake_run(cmd, *a, **kw):
        captured_cmd.append(cmd)
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    # run_blocking 被 monkeypatch 不到，因为它已经 await 了——直接 patch 它
    import services.exec_pool
    async def _fake_run_blocking(fn, *a, **kw):
        return fn(*a, **kw)
    monkeypatch.setattr(services.exec_pool, "run_blocking", _fake_run_blocking)

    r = client.post("/api/video-engine/mix-bgm", json={
        "project_id":         pid,
        "source":             "final_video",
        "track_id":           track_id,
        "bgm_volume_db":      -10,
        "original_volume_db": 0,
        "fade_in_ms":         500,
        "fade_out_ms":        1000,
        "loop_bgm":           True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output_filename"] == "final_video_with_bgm.mp4"
    assert body["bgm_track_id"] == track_id

    # ── 检查 ffmpeg 命令构造 ──
    assert captured_cmd, "ffmpeg.run was not called"
    cmd = captured_cmd[0]
    # 视频流必须 copy
    assert "copy" in cmd
    i = cmd.index("-c:v")
    assert cmd[i + 1] == "copy"
    # -stream_loop -1 出现（因为 loop_bgm=True）
    assert "-stream_loop" in cmd
    assert cmd[cmd.index("-stream_loop") + 1] == "-1"
    # filter_complex 内容
    fc_idx = cmd.index("-filter_complex")
    fc = cmd[fc_idx + 1]
    assert "volume=-10" in fc       # BGM 音量
    assert "afade=t=in" in fc        # 淡入
    assert "afade=t=out" in fc       # 淡出
    assert "amix=inputs=2" in fc     # 混合
    # 淡出起始 = duration(45) - fo(1.0) = 44.0
    assert "st=44.000" in fc, f"fade_out start should be 44.000, got: {fc}"


def test_mix_bgm_loop_false_omits_stream_loop(isolated_app, tmp_path, monkeypatch):
    """loop_bgm=False 时不应有 -stream_loop -1。"""
    from services.db import get_global_music_conn, global_music_root
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()

    pdir = tmp_path / pid
    vdir = pdir / "video"; vdir.mkdir(exist_ok=True, parents=True)
    (vdir / "final_video_subbed.mp4").write_bytes(b"x")
    music_root = global_music_root()
    (music_root / "x.mp3").write_bytes(b"x")
    conn = get_global_music_conn()
    conn.execute(
        "INSERT INTO tracks(name, file_path, mime, project_id, seed, duration_secs,"
        " bpm, time_signature, language, key_scale, tags, lyrics, bytes, created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("BGMlo", "x.mp3", "audio/mpeg", "", 2, 60, 120, "4", "zh", "C major", "",
         "", 1, "2026-06-08T00:00:00+00:00"),
    )
    conn.commit()
    tid = conn.execute("SELECT id FROM tracks WHERE name='BGMlo'").fetchone()["id"]

    monkeypatch.setattr("routers.video_engine._find_ffmpeg",
                        lambda *a, **kw: "ffmpeg.exe")
    monkeypatch.setattr("routers.video_engine._ffprobe_duration_seconds",
                        lambda *a, **kw: 30.0)
    captured: list = []
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, *a, **kw: captured.append(cmd) or SimpleNamespace(returncode=0, stderr=b"", stdout=b""))
    import services.exec_pool
    async def _fake_rb(fn, *a, **kw): return fn(*a, **kw)
    monkeypatch.setattr(services.exec_pool, "run_blocking", _fake_rb)

    r = client.post("/api/video-engine/mix-bgm", json={
        "project_id": pid, "source": "final_video_subbed", "track_id": tid,
        "loop_bgm":  False,
    })
    assert r.status_code == 200
    cmd = captured[0]
    # 关键：-stream_loop 不应出现
    assert "-stream_loop" not in cmd
    # source 用了正确的文件
    src_i = cmd.index("-i")
    assert "final_video_subbed.mp4" in cmd[src_i + 1]
