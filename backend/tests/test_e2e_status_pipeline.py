"""E2: 经过路由层验证状态机推进 + 资产 URL 寻址。

不调真实 ComfyUI/ffmpeg；通过 service 层手动写资产模拟生成结果，
然后从 endpoint 角度看状态机推进与 file URL 是否对得上。
"""
from pathlib import Path


def _seed_two_scenes(client, pid):
    client.put(f"/api/projects/{pid}/scenes", json={"scenes": [
        {"id": "s1", "index": 1, "description": "first",
         "start_frame_prompt": "a", "end_frame_prompt": "b"},
        {"id": "s2", "index": 2, "description": "second",
         "start_frame_prompt": "c", "end_frame_prompt": "d"},
    ]})


def test_full_status_progression(isolated_app):
    """draft → prompted → image_drafted → audio_ready → video_ready."""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir   = isolated_app["tmp_path"] / pid

    _seed_two_scenes(client, pid)
    body = client.get(f"/api/projects/{pid}/status").json()
    assert {s["id"]: s["status"] for s in body["scenes"]} == {
        "s1": "prompted", "s2": "prompted",
    }

    # 1) 写图片资产 → image_drafted
    from services.project_repo import record_asset
    for sid in ("s1", "s2"):
        (pdir / "images" / f"{sid}_start.png").write_bytes(b"X")
        (pdir / "images" / f"{sid}_end.png").write_bytes(b"X")
        record_asset(pid, sid, "image_start",
                     file_path=f"images/{sid}_start.png", format="png", is_selected=True)
        record_asset(pid, sid, "image_end",
                     file_path=f"images/{sid}_end.png", format="png", is_selected=True)

    body = client.get(f"/api/projects/{pid}/status").json()
    assert {s["id"]: s["status"] for s in body["scenes"]} == {
        "s1": "image_drafted", "s2": "image_drafted",
    }
    assert body["summary"]["project_stage"] == "images_done"

    # 2) 写音频 → audio_ready
    for sid in ("s1", "s2"):
        (pdir / "audio" / f"{sid}.mp3").write_bytes(b"A")
        record_asset(pid, sid, "audio",
                     file_path=f"audio/{sid}.mp3", format="mp3", is_selected=True)

    body = client.get(f"/api/projects/{pid}/status").json()
    assert {s["id"]: s["status"] for s in body["scenes"]} == {
        "s1": "audio_ready", "s2": "audio_ready",
    }
    assert body["summary"]["project_stage"] == "audio_done"

    # 3) 写视频 → video_ready
    for sid in ("s1", "s2"):
        (pdir / "video" / f"{sid}.mp4").write_bytes(b"V")
        record_asset(pid, sid, "video",
                     file_path=f"video/{sid}.mp4", format="mp4", is_selected=True)

    body = client.get(f"/api/projects/{pid}/status").json()
    assert body["summary"]["project_stage"] == "videos_done"


def test_asset_url_round_trip(isolated_app):
    """记录资产后，通过 /assets URL 能拿回原始字节。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir   = isolated_app["tmp_path"] / pid

    client.put(f"/api/projects/{pid}/scenes", json={"scenes": [
        {"id": "s1", "index": 1, "description": "x"}
    ]})

    data = b"\x89PNG\r\n\x1a\n_REAL_BYTES_"
    (pdir / "images" / "s1_start.png").write_bytes(data)

    from services.project_repo import record_asset
    record_asset(pid, "s1", "image_start",
                 file_path="images/s1_start.png", format="png", is_selected=True)

    # 通过 /assets 列表拿 url 再 fetch
    items = client.get(f"/api/projects/{pid}/assets").json()["assets"]
    assert len(items) == 1
    url = items[0]["url"]
    r = client.get(url)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == data


def test_save_scenes_preserves_advanced_status_via_route(isolated_app):
    """再次 PUT /scenes 不应把已推进的状态打回。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir   = isolated_app["tmp_path"] / pid

    _seed_two_scenes(client, pid)
    from services.project_repo import record_asset
    (pdir / "images" / "x.png").write_bytes(b"X")
    record_asset(pid, "s1", "image_start", file_path="images/x.png",
                 format="png", is_selected=True)
    record_asset(pid, "s1", "image_end",   file_path="images/x.png",
                 format="png", is_selected=True)

    assert client.get(f"/api/projects/{pid}/status").json()["scenes"][0]["status"] == "image_drafted"

    # 用户编辑分镜描述 → 重新 PUT
    client.put(f"/api/projects/{pid}/scenes", json={"scenes": [
        {"id": "s1", "index": 1, "description": "edited",
         "start_frame_prompt": "a", "end_frame_prompt": "b"},
        {"id": "s2", "index": 2, "description": "second",
         "start_frame_prompt": "c", "end_frame_prompt": "d"},
    ]})
    after = client.get(f"/api/projects/{pid}/status").json()
    by_id = {s["id"]: s["status"] for s in after["scenes"]}
    assert by_id["s1"] == "image_drafted", "已推进的状态不应被打回"
