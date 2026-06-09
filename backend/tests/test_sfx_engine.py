"""v1.4.8 SFX 引擎接口测试：上传 / 列表 / 时间轴读写 / 删除。"""
import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app import create_app
    return TestClient(create_app())


def _make_b64(payload: bytes = b"\x00" * 1024) -> str:
    return base64.b64encode(payload).decode("ascii")


def test_upload_and_list_sfx_round_trip(client, monkeypatch, tmp_path):
    """上传 → /list 能查到 → /file/{id} 能拉到字节 → DELETE 清理。"""
    # 让全局 SFX 根目录指向 tmp，避免污染真实 APPDATA
    import services.db as _db
    monkeypatch.setattr(_db, "global_sfx_root", lambda: tmp_path / "sfx_root")
    # 关掉缓存的 conn 让 schema 走 tmp 的新文件
    _db._CONNS.pop("__global_sfx__", None)
    monkeypatch.setattr(_db, "_global_sfx_path",
                        lambda: tmp_path / "sfx.sqlite")

    r = client.post("/api/sfx/upload", json={
        "filename": "door.mp3",
        "name":     "Door Close",
        "category": "ambient",
        "tags":     "door,interior",
        "data":     _make_b64(b"\xff\xfb\x90\x00" + b"\x00" * 1024),
    })
    assert r.status_code == 200, r.text
    body = r.json()
    sfx_id = body["id"]
    assert body["name"] == "Door Close"
    assert body["category"] == "ambient"
    assert body["bytes"] > 0
    assert body["url"].endswith(f"/api/sfx/file/{sfx_id}")

    # list
    r = client.get("/api/sfx/list")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(it["id"] == sfx_id for it in items)

    # file
    r = client.get(f"/api/sfx/file/{sfx_id}")
    assert r.status_code == 200
    assert len(r.content) >= 1024

    # categories
    r = client.get("/api/sfx/categories")
    assert "ambient" in r.json()["categories"]

    # delete
    r = client.delete(f"/api/sfx/clip/{sfx_id}")
    assert r.status_code == 204
    r = client.get("/api/sfx/list")
    assert all(it["id"] != sfx_id for it in r.json()["items"])


def test_upload_rejects_bad_extension(client, monkeypatch, tmp_path):
    import services.db as _db
    monkeypatch.setattr(_db, "global_sfx_root", lambda: tmp_path / "sfx_root")
    _db._CONNS.pop("__global_sfx__", None)
    monkeypatch.setattr(_db, "_global_sfx_path",
                        lambda: tmp_path / "sfx.sqlite")
    r = client.post("/api/sfx/upload", json={
        "filename": "evil.exe", "data": _make_b64(),
    })
    assert r.status_code == 400
    assert "不支持的格式" in r.json()["detail"]


def test_timeline_get_put_round_trip(isolated_app):
    """项目 SFX 时间轴 PUT → GET 应保留所有镜次条目。"""
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()
    # 起始为空
    r = client.get(f"/api/sfx/timeline/{pid}")
    assert r.status_code == 200
    assert r.json()["timeline"] == {}
    # PUT 写入
    payload = {
        "timeline": {
            "scene_001": [
                {"sfx_id": 1, "offset_ms": 1200, "volume_db": -6},
                {"sfx_id": 2, "offset_ms": 3500, "volume_db": -8},
            ],
            "scene_002": [
                {"sfx_id": 5, "offset_ms": 0, "volume_db": 0},
            ],
        }
    }
    r = client.put(f"/api/sfx/timeline/{pid}", json=payload)
    assert r.status_code == 200, r.text
    assert set(r.json()["scenes"]) == {"scene_001", "scene_002"}
    # GET 读回
    r = client.get(f"/api/sfx/timeline/{pid}")
    tl = r.json()["timeline"]
    assert tl["scene_001"][0]["offset_ms"] == 1200
    assert tl["scene_001"][1]["sfx_id"] == 2
    assert tl["scene_002"][0]["volume_db"] == 0.0


def test_timeline_validates_volume_bounds(isolated_app):
    """volume_db 超界 (>20 / < -40) 应被 Pydantic 校验拒绝。"""
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()
    r = client.put(f"/api/sfx/timeline/{pid}", json={
        "timeline": {"s1": [{"sfx_id": 1, "offset_ms": 0, "volume_db": 100}]}
    })
    assert r.status_code in (400, 422)


def test_timeline_404_when_project_missing(client):
    r = client.put("/api/sfx/timeline/nonexistent_project_xyz", json={
        "timeline": {"s1": [{"sfx_id": 1, "offset_ms": 0, "volume_db": -6}]}
    })
    assert r.status_code == 404
