"""v1.5.1 视频 bug 回归：

bug1 GET /videos 自愈 —— ComfyUI 生成的视频在 video/ 目录、scene_assets 已登记，
     但 videos.json 缺失/不全时仍要列出（否则重开项目分镜框不显示视频、无法合成）。
bug2 合并(含 BGM)输出按【视频流】时长封顶 —— 漫剧音频常比画面长几十~百毫秒，
     不封顶会让画面比声音早结束、末尾定格。
"""
import base64
import json
import subprocess
from types import SimpleNamespace


# ── bug1: GET /videos 自愈 ────────────────────────────────────────────────────


def test_load_videos_heals_from_scene_assets(isolated_app):
    from services import project_repo
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid

    # mp4 在盘
    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "scene_001.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42_fake")
    # scene_assets 有登记，但 videos.json 不存在（模拟没保存 / 写盘中断）
    project_repo.record_asset(pid, "scene_001", "video",
                              slot_index=0, file_path="video/scene_001.mp4",
                              format="mp4", is_selected=True)
    assert not (pdir / "videos.json").exists()

    r = client.get(f"/api/projects/{pid}/videos")
    assert r.status_code == 200, r.text
    body = r.json()
    # 返回流式 URL（不再 base64 整包），且自愈补回了 scene_001
    assert body.get("scene_001") == f"/api/projects/{pid}/video-file/scene_001"
    # 索引被回写，下次直接命中、合成也能读到
    assert (pdir / "videos.json").exists()
    idx = json.loads((pdir / "videos.json").read_text(encoding="utf-8-sig"))
    assert idx.get("scene_001") == "scene_001.mp4"

    # 流式端点能取到该分镜视频
    rf = client.get(f"/api/projects/{pid}/video-file/scene_001")
    assert rf.status_code == 200, rf.text
    assert rf.headers["content-type"].startswith("video/mp4")


def test_load_videos_skips_dangling_keeps_existing(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid
    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "scene_001.mp4").write_bytes(b"x")
    (pdir / "videos.json").write_text(json.dumps({
        "scene_001": "scene_001.mp4",   # 存在
        "scene_002": "scene_002.mp4",   # 不存在
    }), encoding="utf-8")
    body = client.get(f"/api/projects/{pid}/videos").json()
    assert "scene_001" in body
    assert "scene_002" not in body


# ── bug2: 合并输出按视频流时长封顶 ────────────────────────────────────────────


def test_merge_with_bgm_pads_clips_and_caps_to_aligned_total(isolated_app, monkeypatch):
    """含 BGM 慢路径：逐镜把画面补到音频长度(tpad)消除累积音画错位，输出按对齐总时长封顶。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid

    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    for sid in ("scene_001", "scene_002"):
        (vdir / f"{sid}.mp4").write_bytes(b"fake")
    (pdir / "videos.json").write_text(json.dumps({
        "scene_001": "scene_001.mp4", "scene_002": "scene_002.mp4",
    }), encoding="utf-8")
    # 项目 BGM → 触发慢路径
    bgm_dir = pdir / "bgm"; bgm_dir.mkdir(exist_ok=True)
    (bgm_dir / "bgm.mp3").write_bytes(b"fake audio")

    monkeypatch.setattr("routers.video_engine._find_ffmpeg", lambda *a, **k: "ffmpeg.exe")

    captured = []
    def _fake_run(cmd, *a, **k):
        s = " ".join(str(x) for x in cmd)
        if "-show_entries" in s:            # ffprobe
            # 视频流 4.5s，容器(音频)5.0s → 每镜 pad=0.5s 触发 tpad
            if "-select_streams" in s:
                return SimpleNamespace(returncode=0, stdout=b"4.5\n", stderr=b"")
            return SimpleNamespace(returncode=0, stdout=b"5.0\n", stderr=b"")
        captured.append(cmd)                 # ffmpeg 合并
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    import services.exec_pool
    async def _fake_run_blocking(fn, *a, **k): return fn(*a, **k)
    monkeypatch.setattr(services.exec_pool, "run_blocking", _fake_run_blocking)

    r = client.post("/api/video-engine/merge-project-video", json={
        "project_id": pid,
        "scene_order": ["scene_001", "scene_002"],
        "transition": "cut",
        "bgm_volume_db": -20,
    })
    assert r.status_code == 200, r.text
    assert captured, "ffmpeg 合并未被调用"
    cmd = captured[-1]
    fc = cmd[cmd.index("-filter_complex") + 1]
    # 逐镜把画面重定时到音频长度（消除非标准帧率导致的累积音画错位）
    assert "setpts=PTS*" in fc, f"缺少逐镜画面重定时: {fc}"
    assert "concat=n=2" in fc
    # 视频流 4.5s、音频 5.0s → 重定时比例 5/4.5≈1.111
    import re as _re
    m = _re.search(r"setpts=PTS\*([0-9.]+)", fc)
    assert m and abs(float(m.group(1)) - (5.0 / 4.5)) < 0.001, fc
    # 片尾画面多撑 0.5s 让末句说完
    assert "tpad=stop_mode=clone" in fc, "缺少片尾画面补帧"
    # 输出 = 音频总长(2×5=10s) + 末尾 0.5s 余量
    assert "-t" in cmd
    assert abs(float(cmd[cmd.index("-t") + 1]) - 10.5) < 0.01
