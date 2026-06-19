"""v1.6: /video-engine/dewatermark-stream 去水印端点回归。

成片换回该分镜视频、原片备份 .predewm.mp4、最长边按输入视频探测、无声退出补 dewm_error。
"""
import base64


def _drain(text: str):
    return [ln[len("data: "):] for ln in text.splitlines() if ln.startswith("data: ")]


def _seed(isolated_app, pid, sid="scene_001", data=b"ORIG_WM"):
    pdir = isolated_app["tmp_path"] / pid
    vdir = pdir / "video"; vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{sid}.mp4").write_bytes(data)
    return pdir


def test_dewatermark_replaces_and_backs_up(isolated_app, monkeypatch):
    import services.watermark_video as wm
    import routers.video_engine as ve
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = _seed(isolated_app, pid)

    monkeypatch.setattr(ve, "_find_ffmpeg", lambda *a, **k: "ffmpeg.exe")
    monkeypatch.setattr(ve, "_ffprobe_dimensions", lambda *a, **k: (1080, 1920))

    captured = {}

    async def _fake(comfyui_url, workflow, *, video_bytes, longest_edge, max_seconds,
                    comfyui_input_dir, workflow_dir, scene_id):
        captured["longest_edge"] = longest_edge
        captured["video_bytes"] = video_bytes
        yield {"event": "queued", "prompt_id": "p", "scene_id": scene_id}
        yield {"event": "completed", "scene_id": scene_id,
               "video": base64.b64encode(b"CLEAN_WM").decode(),
               "filename": "out.mp4", "mime": "video/mp4"}

    monkeypatch.setattr(wm, "generate_watermark_removal", _fake)

    r = client.post("/api/video-engine/dewatermark-stream", json={
        "project_id": pid, "scene_id": "scene_001",
    })
    assert r.status_code == 200, r.text
    joined = "\n".join(_drain(r.text))
    assert "dewm_done" in joined
    # 最长边 = 输入视频最长边 1920
    assert captured["longest_edge"] == 1920
    assert captured["video_bytes"] == b"ORIG_WM"
    vdir = pdir / "video"
    assert (vdir / "scene_001.mp4").read_bytes() == b"CLEAN_WM"
    assert (vdir / "scene_001.predewm.mp4").read_bytes() == b"ORIG_WM"


def test_dewatermark_respects_max_longest_edge_cap(isolated_app, monkeypatch):
    import services.watermark_video as wm
    import routers.video_engine as ve
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _seed(isolated_app, pid)
    monkeypatch.setattr(ve, "_find_ffmpeg", lambda *a, **k: "ffmpeg.exe")
    monkeypatch.setattr(ve, "_ffprobe_dimensions", lambda *a, **k: (1080, 1920))
    cap = {}

    async def _fake(comfyui_url, workflow, *, video_bytes, longest_edge, **k):
        cap["le"] = longest_edge
        yield {"event": "completed", "scene_id": k.get("scene_id"),
               "video": base64.b64encode(b"x").decode(), "filename": "o.mp4", "mime": "video/mp4"}

    monkeypatch.setattr(wm, "generate_watermark_removal", _fake)
    r = client.post("/api/video-engine/dewatermark-stream", json={
        "project_id": pid, "scene_id": "scene_001", "max_longest_edge": 960,
    })
    assert r.status_code == 200, r.text
    assert cap["le"] == 960     # min(1920, 960)


def test_dewatermark_missing_video_404(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    r = client.post("/api/video-engine/dewatermark-stream", json={
        "project_id": pid, "scene_id": "nope",
    })
    assert r.status_code == 404


def test_dewatermark_silent_exit_errors(isolated_app, monkeypatch):
    import services.watermark_video as wm
    import routers.video_engine as ve
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _seed(isolated_app, pid)
    monkeypatch.setattr(ve, "_find_ffmpeg", lambda *a, **k: "ffmpeg.exe")
    monkeypatch.setattr(ve, "_ffprobe_dimensions", lambda *a, **k: (640, 480))

    async def _silent(*a, **k):
        yield {"event": "queued", "prompt_id": "p", "scene_id": "scene_001"}

    monkeypatch.setattr(wm, "generate_watermark_removal", _silent)
    r = client.post("/api/video-engine/dewatermark-stream", json={
        "project_id": pid, "scene_id": "scene_001",
    })
    assert r.status_code == 200, r.text
    assert "dewm_error" in "\n".join(_drain(r.text))
