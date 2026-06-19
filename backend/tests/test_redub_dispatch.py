"""v1.6: /video-engine/redub-stream 视频后期 RVC 变声端点回归（Phase C）。

锁定附加式契约：成片换回该分镜视频、原片备份可回退、无声退出补 redub_error、
/rvc-models 列举 .pth。
"""
import base64

import pytest


def _drain_sse(text: str) -> list[str]:
    return [ln[len("data: "):] for ln in text.splitlines() if ln.startswith("data: ")]


def _seed_scene_video(isolated_app, pid, scene_id="scene_001", data=b"ORIGINAL_MP4",
                      msr=False):
    pdir = isolated_app["tmp_path"] / pid
    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    name = f"{scene_id}.msr.mp4" if msr else f"{scene_id}.mp4"
    (vdir / name).write_bytes(data)
    return pdir


def test_redub_preview_returns_base64_without_replacing(isolated_app, monkeypatch):
    """v1.6 预览模式：redub-stream 回 redub_preview(base64)，绝不改动分镜视频。"""
    import services.redub_video as redub_mod
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = _seed_scene_video(isolated_app, pid)
    captured = {}

    async def _fake_redub(comfyui_url, workflow, *, video_bytes, default_model,
                          transpose=None, index_rate=None, protect=None,
                          rms_mix_rate=None, mixback_gain=None, scene_id="", **k):
        captured.update(video_bytes=video_bytes, default_model=default_model,
                        mixback_gain=mixback_gain, index_rate=index_rate)
        yield {"event": "queued", "prompt_id": "p1", "scene_id": scene_id}
        yield {"event": "completed", "scene_id": scene_id,
               "video": base64.b64encode(b"REDUBBED").decode(),
               "filename": "redub_001.mp4", "mime": "video/mp4"}

    monkeypatch.setattr(redub_mod, "generate_redub_video", _fake_redub)
    r = client.post("/api/video-engine/redub-stream", json={
        "project_id": pid, "scene_id": "scene_001", "default_model": "alice.pth",
        "mixback_gain": 0.8, "index_rate": 0.5,
    })
    assert r.status_code == 200, r.text
    joined = "\n".join(_drain_sse(r.text))
    assert "redub_preview" in joined
    assert base64.b64encode(b"REDUBBED").decode() in joined   # base64 透传给前端预览
    # 配置项透传
    assert captured["mixback_gain"] == 0.8 and captured["index_rate"] == 0.5
    # 分镜视频【未被改动】（预览不落盘）
    assert (pdir / "video" / "scene_001.mp4").read_bytes() == b"ORIGINAL_MP4"
    assert not (pdir / "video" / "scene_001.orig.mp4").exists()


def test_redub_apply_writes_and_backs_up(isolated_app):
    """确认变声：/redub-apply 把预览成片写回分镜视频 + 备份原片。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = _seed_scene_video(isolated_app, pid)
    r = client.post("/api/video-engine/redub-apply", json={
        "project_id": pid, "scene_id": "scene_001", "use_msr": False,
        "video": base64.b64encode(b"FINAL").decode(),
    })
    assert r.status_code == 200, r.text
    vdir = pdir / "video"
    assert (vdir / "scene_001.mp4").read_bytes() == b"FINAL"
    assert (vdir / "scene_001.orig.mp4").read_bytes() == b"ORIGINAL_MP4"


def test_redub_apply_msr_targets_msr_file(isolated_app):
    """use_msr=True → 写 .msr.mp4 + 备份 .msr.orig.mp4，不碰旧 .mp4。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = _seed_scene_video(isolated_app, pid, data=b"OLD")            # 旧 .mp4
    _seed_scene_video(isolated_app, pid, data=b"MSR_ORIG", msr=True)    # .msr.mp4
    r = client.post("/api/video-engine/redub-apply", json={
        "project_id": pid, "scene_id": "scene_001", "use_msr": True,
        "video": base64.b64encode(b"MSR_FINAL").decode(),
    })
    assert r.status_code == 200, r.text
    vdir = pdir / "video"
    assert (vdir / "scene_001.msr.mp4").read_bytes() == b"MSR_FINAL"
    assert (vdir / "scene_001.msr.orig.mp4").read_bytes() == b"MSR_ORIG"
    assert (vdir / "scene_001.mp4").read_bytes() == b"OLD"             # 旧片不动


def test_redub_preview_msr_uses_msr_source(isolated_app, monkeypatch):
    """use_msr=True 时预览读取的是 .msr.mp4 源。"""
    import services.redub_video as redub_mod
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _seed_scene_video(isolated_app, pid, data=b"OLD")
    _seed_scene_video(isolated_app, pid, data=b"MSR_SRC", msr=True)
    seen = {}

    async def _fake(comfyui_url, workflow, *, video_bytes, scene_id="", **k):
        seen["bytes"] = video_bytes
        yield {"event": "completed", "scene_id": scene_id,
               "video": base64.b64encode(b"x").decode(), "filename": "o.mp4", "mime": "video/mp4"}

    monkeypatch.setattr(redub_mod, "generate_redub_video", _fake)
    r = client.post("/api/video-engine/redub-stream", json={
        "project_id": pid, "scene_id": "scene_001", "default_model": "a.pth", "use_msr": True,
    })
    assert r.status_code == 200, r.text
    assert seen["bytes"] == b"MSR_SRC"


def test_redub_missing_model_errors(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _seed_scene_video(isolated_app, pid)
    # 无 default_model 且设置无默认 → 400
    r = client.post("/api/video-engine/redub-stream", json={
        "project_id": pid, "scene_id": "scene_001",
    })
    assert r.status_code == 400
    assert "RVC" in r.json()["detail"]


def test_redub_missing_video_errors(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    r = client.post("/api/video-engine/redub-stream", json={
        "project_id": pid, "scene_id": "nope", "default_model": "a.pth",
    })
    assert r.status_code == 404


def test_redub_silent_exit_emits_error(isolated_app, monkeypatch):
    import services.redub_video as redub_mod
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _seed_scene_video(isolated_app, pid)

    async def _silent(*a, **k):
        yield {"event": "queued", "prompt_id": "p1", "scene_id": "scene_001"}
        # 无 completed / error

    monkeypatch.setattr(redub_mod, "generate_redub_video", _silent)
    r = client.post("/api/video-engine/redub-stream", json={
        "project_id": pid, "scene_id": "scene_001", "default_model": "a.pth",
    })
    assert r.status_code == 200, r.text
    assert "redub_error" in "\n".join(_drain_sse(r.text))


def test_rvc_models_lists_pth(isolated_app, tmp_path):
    client = isolated_app["client"]
    # 造一个假 RVC 根目录 + 权重
    root = tmp_path / "rvc"
    weights = root / "assets" / "weights"; weights.mkdir(parents=True)
    (weights / "alice.pth").write_bytes(b"x")
    (weights / "bob.pth").write_bytes(b"x")
    (weights / "notmodel.txt").write_bytes(b"x")

    r = client.get(f"/api/video-engine/rvc-models", params={"rvc_root": str(root)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exists"] is True
    assert set(body["models"]) == {"alice.pth", "bob.pth"}
