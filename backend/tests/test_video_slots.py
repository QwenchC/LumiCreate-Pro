"""v1.6.2: 多引擎视频槽 —— 槽模型 + 合并按 scene_sources 选槽 + /videos-all。

每个生成方式（ltx/msr/slideshow/seedance）给每镜各存独立一份、互不覆盖；
合并时按每镜所选来源挑对应那份，跨引擎混合。
"""
import json
import subprocess
from types import SimpleNamespace


# ── 槽模型（纯函数）────────────────────────────────────────────────────────────

def test_slot_helpers():
    from services.video_slots import (slot_filename, slot_index_name, slot_asset,
                                      kind_query, norm_kind, SLOT_KINDS)
    assert set(SLOT_KINDS) == {"ltx", "msr", "slideshow", "seedance"}
    assert slot_filename("s1", "ltx") == "s1.mp4"
    assert slot_filename("s1", "msr") == "s1.msr.mp4"
    assert slot_filename("s1", "slideshow") == "s1.slideshow.mp4"
    assert slot_filename("s1", "seedance") == "s1.seedance.mp4"
    assert slot_index_name("seedance") == "videos_seedance.json"
    assert slot_asset("slideshow") == "video_slideshow"
    # ltx 默认槽不带 ?kind=（向后兼容旧 URL）；其它带
    assert kind_query("ltx") == "" and kind_query("old") == ""
    assert kind_query("msr") == "?kind=msr"
    # 归一：未知/old/'' → ltx
    assert norm_kind("old") == "ltx" and norm_kind("") == "ltx" and norm_kind("???") == "ltx"


# ── /videos-all ────────────────────────────────────────────────────────────────

def test_videos_all_lists_each_slot(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid
    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    # scene_001 有 ltx + slideshow；scene_002 只有 seedance
    (vdir / "scene_001.mp4").write_bytes(b"a")
    (vdir / "scene_001.slideshow.mp4").write_bytes(b"b")
    (vdir / "scene_002.seedance.mp4").write_bytes(b"c")
    (pdir / "videos.json").write_text(json.dumps({"scene_001": "scene_001.mp4"}), encoding="utf-8")
    (pdir / "videos_slideshow.json").write_text(json.dumps({"scene_001": "scene_001.slideshow.mp4"}), encoding="utf-8")
    (pdir / "videos_seedance.json").write_text(json.dumps({"scene_002": "scene_002.seedance.mp4"}), encoding="utf-8")

    body = client.get(f"/api/projects/{pid}/videos-all").json()
    assert set(body.get("scene_001", {})) == {"ltx", "slideshow"}
    assert set(body.get("scene_002", {})) == {"seedance"}
    assert body["scene_001"]["ltx"].endswith("/video-file/scene_001")
    assert "kind=slideshow" in body["scene_001"]["slideshow"]
    assert "kind=seedance" in body["scene_002"]["seedance"]


# ── 合并按 scene_sources 选槽（跨引擎混合）──────────────────────────────────────

def _mock_merge_ffmpeg(monkeypatch):
    import routers.video_engine as ve
    monkeypatch.setattr(ve, "_find_ffmpeg", lambda *a, **k: "ffmpeg.exe")
    captured = []

    def _fake_run(cmd, *a, **k):
        s = " ".join(str(x) for x in cmd)
        if "-show_entries" in s:                       # ffprobe
            return SimpleNamespace(returncode=0, stdout=b"4.0\n", stderr=b"")
        captured.append(cmd)                            # ffmpeg merge
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    import services.exec_pool
    async def _fake_run_blocking(fn, *a, **k): return fn(*a, **k)
    monkeypatch.setattr(services.exec_pool, "run_blocking", _fake_run_blocking)
    return captured


def test_merge_picks_per_scene_source(isolated_app, monkeypatch):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid
    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    # 同一镜 scene_001 同时有 ltx 与 slideshow 两个版本（互不覆盖）
    for fn in ("scene_001.mp4", "scene_001.slideshow.mp4",
               "scene_002.mp4", "scene_002.seedance.mp4", "scene_003.msr.mp4"):
        (vdir / fn).write_bytes(b"fake")
    (pdir / "videos.json").write_text(json.dumps(
        {"scene_001": "scene_001.mp4", "scene_002": "scene_002.mp4"}), encoding="utf-8")
    (pdir / "videos_slideshow.json").write_text(json.dumps(
        {"scene_001": "scene_001.slideshow.mp4"}), encoding="utf-8")
    (pdir / "videos_seedance.json").write_text(json.dumps(
        {"scene_002": "scene_002.seedance.mp4"}), encoding="utf-8")
    (pdir / "videos_msr.json").write_text(json.dumps(
        {"scene_003": "scene_003.msr.mp4"}), encoding="utf-8")

    captured = _mock_merge_ffmpeg(monkeypatch)
    r = client.post("/api/video-engine/merge-project-video", json={
        "project_id": pid,
        "scene_order": ["scene_001", "scene_002", "scene_003"],
        "transition": "cut",
        "bgm_volume_db": -100,    # 关 BGM
        "scene_sources": {        # 跨引擎混合：放映 + Seedance + MSR
            "scene_001": "slideshow",
            "scene_002": "seedance",
            "scene_003": "msr",
        },
    })
    assert r.status_code == 200, r.text
    cmd = captured[-1]
    inputs = [str(cmd[i + 1]) for i, a in enumerate(cmd) if a == "-i"]
    joined = " ".join(inputs)
    assert "scene_001.slideshow.mp4" in joined   # 选了放映，而非 ltx
    assert "scene_002.seedance.mp4" in joined     # 选了 Seedance
    assert "scene_003.msr.mp4" in joined          # 选了 MSR
    assert "scene_001.mp4 " not in joined + " "   # 没用 ltx 版本
    # 跨引擎尺寸不一 → filter_complex 必须把每路画面统一缩放+letterbox、音频统一重采样，
    # 否则 concat 报错（回归保护：审查发现的关键 bug）
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.count("force_original_aspect_ratio=decrease") >= 3   # 每镜各一份缩放
    assert "pad=" in fc and "setsar=1" in fc
    assert "aresample=48000" in fc                                  # 音频归一


def test_merge_audioless_input_gets_silence(isolated_app, monkeypatch):
    """无音轨的镜（如 Seedance 关音频 / i2v）合并时补静音 anullsrc，避免 [i:a] 映射失败。"""
    import routers.video_engine as ve
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid
    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "scene_001.seedance.mp4").write_bytes(b"fake")
    (pdir / "videos_seedance.json").write_text(json.dumps(
        {"scene_001": "scene_001.seedance.mp4"}), encoding="utf-8")

    monkeypatch.setattr(ve, "_find_ffmpeg", lambda *a, **k: "ffmpeg.exe")
    monkeypatch.setattr(ve, "_ffprobe_dimensions", lambda *a, **k: (1280, 720))
    captured = []

    def _fake_run(cmd, *a, **k):
        s = " ".join(str(x) for x in cmd)
        if "-show_entries" in s:
            if "a:0" in s:   # 音频流探测 → 无音轨
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            return SimpleNamespace(returncode=0, stdout=b"4.0\n", stderr=b"")
        captured.append(cmd)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    import services.exec_pool
    async def _rb(fn, *a, **k): return fn(*a, **k)
    monkeypatch.setattr(services.exec_pool, "run_blocking", _rb)

    r = client.post("/api/video-engine/merge-project-video", json={
        "project_id": pid, "scene_order": ["scene_001"], "transition": "cut",
        "bgm_volume_db": -100, "scene_sources": {"scene_001": "seedance"},
    })
    assert r.status_code == 200, r.text
    fc = captured[-1][captured[-1].index("-filter_complex") + 1]
    assert "anullsrc" in fc      # 补了静音轨


def test_merge_falls_back_to_msr_scene_ids(isolated_app, monkeypatch):
    """未传 scene_sources 时，仍兼容旧的 msr_scene_ids。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid
    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "scene_001.mp4").write_bytes(b"x")
    (vdir / "scene_001.msr.mp4").write_bytes(b"y")
    (pdir / "videos.json").write_text(json.dumps({"scene_001": "scene_001.mp4"}), encoding="utf-8")
    (pdir / "videos_msr.json").write_text(json.dumps({"scene_001": "scene_001.msr.mp4"}), encoding="utf-8")

    captured = _mock_merge_ffmpeg(monkeypatch)
    r = client.post("/api/video-engine/merge-project-video", json={
        "project_id": pid, "scene_order": ["scene_001"],
        "transition": "cut", "bgm_volume_db": -100,
        "msr_scene_ids": ["scene_001"],
    })
    assert r.status_code == 200, r.text
    joined = " ".join(str(x) for x in captured[-1])
    assert "scene_001.msr.mp4" in joined
