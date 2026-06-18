"""v1.6: /video-engine/redub-stream 视频后期 RVC 变声端点回归（Phase C）。

锁定附加式契约：成片换回该分镜视频、原片备份可回退、无声退出补 redub_error、
/rvc-models 列举 .pth。
"""
import base64

import pytest


def _drain_sse(text: str) -> list[str]:
    return [ln[len("data: "):] for ln in text.splitlines() if ln.startswith("data: ")]


def _seed_scene_video(isolated_app, pid, scene_id="scene_001", data=b"ORIGINAL_MP4"):
    pdir = isolated_app["tmp_path"] / pid
    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{scene_id}.mp4").write_bytes(data)
    return pdir


def test_redub_replaces_video_and_backs_up_original(isolated_app, monkeypatch):
    import services.redub_video as redub_mod
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = _seed_scene_video(isolated_app, pid)

    async def _fake_redub(comfyui_url, workflow, *, video_bytes, default_model,
                          voice_mapping, rvc_root, rvc_python, device,
                          whisper_model, language, comfyui_input_dir,
                          workflow_dir, scene_id):
        # 收到的就是原片字节
        assert video_bytes == b"ORIGINAL_MP4"
        assert default_model == "alice.pth"
        yield {"event": "queued", "prompt_id": "p1", "scene_id": scene_id}
        yield {"event": "completed", "scene_id": scene_id,
               "video": base64.b64encode(b"REDUBBED_MP4").decode(),
               "filename": "redub_001.mp4", "mime": "video/mp4"}

    monkeypatch.setattr(redub_mod, "generate_redub_video", _fake_redub)

    r = client.post("/api/video-engine/redub-stream", json={
        "project_id": pid, "scene_id": "scene_001", "default_model": "alice.pth",
    })
    assert r.status_code == 200, r.text
    joined = "\n".join(_drain_sse(r.text))
    assert "redub_done" in joined

    vdir = pdir / "video"
    # 成片换回该分镜视频
    assert (vdir / "scene_001.mp4").read_bytes() == b"REDUBBED_MP4"
    # 原片备份可回退
    assert (vdir / "scene_001.orig.mp4").read_bytes() == b"ORIGINAL_MP4"


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
