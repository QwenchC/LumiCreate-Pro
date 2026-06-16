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
    assert "scene_001" in body and body["scene_001"], "应从 scene_assets 自愈补回"
    # 索引被回写，下次直接命中、合成也能读到
    assert (pdir / "videos.json").exists()
    idx = json.loads((pdir / "videos.json").read_text(encoding="utf-8-sig"))
    assert idx.get("scene_001") == "scene_001.mp4"


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


def test_merge_with_bgm_caps_output_to_video_length(isolated_app, monkeypatch):
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
        if "-show_entries" in s:            # ffprobe（容器/视频流时长）
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
    # 走了慢路径（filter_complex + amix），且输出被 -t 封顶
    assert "-filter_complex" in cmd
    assert "-t" in cmd, f"合并(含 BGM)输出必须按视频流时长封顶: {cmd}"
    # 2 段各 5s = 10s（cut 无 xfade 重叠）
    t_val = float(cmd[cmd.index("-t") + 1])
    assert abs(t_val - 10.0) < 0.01, t_val
