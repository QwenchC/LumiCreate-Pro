"""E2: 项目生命周期端到端 — 经过 FastAPI 路由 + ProjectRepo + SQLite。"""


def test_get_project_status_empty(isolated_app):
    """全新项目（无分镜）→ project_stage='empty'。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    r = client.get(f"/api/projects/{pid}/status")
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["project_stage"] == "empty"
    assert data["scenes"] == []


def test_put_scenes_creates_sqlite_state(isolated_app):
    """PUT /scenes 走 ProjectRepo 双写 → 状态查询能立刻看到。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    scenes = [
        {"id": "s1", "index": 1, "description": "镜 1",
         "start_frame_prompt": "a", "end_frame_prompt": "b"},
        {"id": "s2", "index": 2, "description": "镜 2"},
    ]
    r = client.put(f"/api/projects/{pid}/scenes", json={"scenes": scenes})
    assert r.status_code == 200

    # JSON 文件落盘
    pdir = isolated_app["tmp_path"] / pid
    import json
    saved = json.loads((pdir / "scenes.json").read_text(encoding="utf-8-sig"))
    assert len(saved["scenes"]) == 2

    # SQLite 同时落
    r = client.get(f"/api/projects/{pid}/status")
    body = r.json()
    by_id = {s["id"]: s for s in body["scenes"]}
    # s1 有 prompts → prompted；s2 没有 → draft
    assert by_id["s1"]["status"] == "prompted"
    assert by_id["s2"]["status"] == "draft"
    # 项目阶段 = 最低 = drafted
    assert body["summary"]["project_stage"] == "drafted"


def test_assets_list_filter(isolated_app):
    """直接调 record_asset 后 /assets endpoint 能查到。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    client.put(f"/api/projects/{pid}/scenes", json={"scenes": [
        {"id": "s1", "index": 1, "description": "x"}
    ]})

    pdir = isolated_app["tmp_path"] / pid
    (pdir / "images" / "x.png").write_bytes(b"\x89PNG fake")

    from services.project_repo import record_asset
    record_asset(pid, "s1", "image_start",
                 slot_index=0, file_path="images/x.png", format="png",
                 is_selected=True)

    r = client.get(f"/api/projects/{pid}/assets")
    items = r.json()["assets"]
    assert len(items) == 1
    assert items[0]["scene_id"] == "s1"
    assert "/assets/file/s1/image_start/0" in items[0]["url"]


def test_delete_project_drops_sqlite_and_dir(isolated_app):
    """删项目后磁盘和 SQLite 文件都清理掉。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    # 写一次 scenes 让 SQLite 出现
    client.put(f"/api/projects/{pid}/scenes", json={"scenes": [
        {"id": "s1", "index": 1, "description": "x"}
    ]})
    pdir = isolated_app["tmp_path"] / pid
    assert (pdir / "project.sqlite").exists()

    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
    assert not pdir.exists()


def test_last_run_errors_lifecycle(isolated_app):
    """PUT errors → GET 查 → DELETE 清。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    # 默认空
    assert client.get(f"/api/projects/{pid}/last-run-errors").json() == {
        "stage": "", "ts": "", "errors": {},
    }

    payload = {"stage": "images", "ts": "2024-01-01T00:00:00Z",
               "errors": {"s1:start": "fail"}}
    r = client.put(f"/api/projects/{pid}/last-run-errors", json=payload)
    assert r.status_code == 200
    assert r.json()["count"] == 1

    body = client.get(f"/api/projects/{pid}/last-run-errors").json()
    assert body["stage"] == "images"
    assert body["errors"]["s1:start"] == "fail"

    assert client.delete(f"/api/projects/{pid}/last-run-errors").status_code == 204
    assert client.get(f"/api/projects/{pid}/last-run-errors").json()["errors"] == {}
