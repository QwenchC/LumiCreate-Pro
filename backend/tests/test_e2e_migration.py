"""E2: 老项目（纯 JSON，没 SQLite）首次访问 status endpoint 自动迁移。"""
import json


def test_legacy_project_migrates_on_first_status_call(isolated_app):
    """模拟一个 v1.3.5 时代的项目：scenes.json + images.json + audio.json + videos.json，
    没有 project.sqlite。访问 /status 后应当：
      - 创建 sqlite
      - scenes 表填好
      - assets 表按 metadata 填好
      - 状态自动推到最合理的高位
    """
    pid = isolated_app["make_project"]("legacy")
    pdir = isolated_app["tmp_path"] / pid
    client = isolated_app["client"]

    # scenes.json
    (pdir / "scenes.json").write_text(json.dumps({"scenes": [
        {"id": "s1", "index": 1, "description": "first",
         "start_frame_prompt": "a", "end_frame_prompt": "b",
         "dialogues": [], "_scene_characters": []},
        {"id": "s2", "index": 2, "description": "second",
         "start_frame_prompt": "c", "end_frame_prompt": "d",
         "dialogues": [], "_scene_characters": []},
    ]}), encoding="utf-8")

    # images.json — 两镜每镜 1 张 start + 1 张 end，文件已落盘
    saved_slots = []
    for sid in ("s1", "s2"):
        for ft in ("start", "end"):
            fn = f"{sid}_{ft}_0.png"
            (pdir / "images" / fn).write_bytes(b"\x89PNG fake")
            saved_slots.append({
                "scene_id": sid, "frame_type": ft, "slot_index": 0,
                "filename": fn,
            })
    (pdir / "images.json").write_text(json.dumps({
        "saved_slots": saved_slots,
        "counts":      {f"{s['scene_id']}:{s['frame_type']}": 1 for s in saved_slots},
        "selected":    {f"{s['scene_id']}:{s['frame_type']}": 0 for s in saved_slots},
    }), encoding="utf-8")

    # audio.json — 仅 s1 有
    (pdir / "audio" / "__ms_reading__s1.mp3").write_bytes(b"AUDIO")
    (pdir / "audio.json").write_text(json.dumps({
        "__ms_reading__s1": {
            "file": "__ms_reading__s1.mp3",
            "duration_ms": 4200, "format": "mp3",
        }
    }), encoding="utf-8")

    # 项目还没 sqlite
    assert not (pdir / "project.sqlite").exists()

    # 第一次访问 /status 应触发迁移
    r = client.get(f"/api/projects/{pid}/status")
    assert r.status_code == 200
    assert (pdir / "project.sqlite").exists()

    body = r.json()
    by_id = {s["id"]: s["status"] for s in body["scenes"]}

    # s1：有图片 + 音频 → audio_ready
    # s2：仅有图片 → image_drafted
    assert by_id["s1"] == "audio_ready"
    assert by_id["s2"] == "image_drafted"
    # 项目最低 = image_drafted
    assert body["summary"]["project_stage"] == "images_done"


def test_migration_is_idempotent(isolated_app):
    """重复调 ensure_migrated 不会重复 INSERT 或破坏 SQLite。"""
    pid = isolated_app["make_project"]("rerun")
    pdir = isolated_app["tmp_path"] / pid
    client = isolated_app["client"]

    (pdir / "scenes.json").write_text(json.dumps({"scenes": [
        {"id": "x", "index": 1, "description": "x"}
    ]}), encoding="utf-8")

    # 调 4 次（首次迁移，后续应直接返回）
    for _ in range(4):
        r = client.get(f"/api/projects/{pid}/status")
        assert r.status_code == 200

    # scenes 表里仍然只有 1 条
    from services.db import get_conn
    conn = get_conn(pid)
    n = conn.execute("SELECT COUNT(*) AS c FROM scenes").fetchone()["c"]
    assert n == 1
