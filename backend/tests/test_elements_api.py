"""轮 2: Elements API 端到端（FastAPI TestClient）。"""
import base64
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_with_temp_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import config
    importlib.reload(config)
    from services import db, elements_repo
    importlib.reload(db)
    importlib.reload(elements_repo)

    # 同时 patch settings 让 projects_dir 也在 tmp 下（避免污染真实项目）
    class _Cfg:
        projects_dir = str(tmp_path / "projects")
    fake = _Cfg()
    monkeypatch.setattr(config, "load_settings", lambda: fake)
    Path(fake.projects_dir).mkdir(parents=True, exist_ok=True)

    # patch 所有从 config import load_settings 的模块（与 conftest 思路一致）
    import sys
    for modname in (
        "services.db", "services.project_repo", "services.project_migrate",
        "services.elements_repo",
        "routers.projects", "routers.elements", "routers.project_elements",
    ):
        mod = sys.modules.get(modname)
        if mod is not None and hasattr(mod, "load_settings"):
            monkeypatch.setattr(mod, "load_settings", lambda: fake)

    db.close_all()
    db._CONNS.clear()

    from app import create_app
    yield TestClient(create_app())
    db.close_all()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


# ── Global scope ──────────────────────────────────────────────────────────────


def test_create_and_list_folder(app_with_temp_appdata):
    c = app_with_temp_appdata
    r = c.post("/api/elements/folders", json={"name": "characters"})
    assert r.status_code == 200
    f = r.json()
    assert f["name"] == "characters"

    r2 = c.get("/api/elements/folders")
    assert len(r2.json()["folders"]) == 1


def test_invalid_folder_name_returns_400(app_with_temp_appdata):
    c = app_with_temp_appdata
    r = c.post("/api/elements/folders", json={"name": "a/b"})
    assert r.status_code == 400


def test_upload_element_and_get_file(app_with_temp_appdata):
    c = app_with_temp_appdata
    PNG = b"\x89PNG\r\n\x1a\nFAKE"
    r = c.post("/api/elements/", json={
        "folder_id": None, "name": "test", "filename": "test.png",
        "mime": "image/png", "data": _b64(PNG),
    })
    assert r.status_code == 200, r.text
    elem = r.json()
    assert elem["bytes"] == len(PNG)

    # GET 文件回原始字节
    r2 = c.get(f"/api/elements/file/{elem['id']}")
    assert r2.status_code == 200
    assert r2.content == PNG
    assert r2.headers["content-type"].startswith("image/png")


def test_list_elements_filter_by_folder(app_with_temp_appdata):
    c = app_with_temp_appdata
    f = c.post("/api/elements/folders", json={"name": "anime"}).json()
    c.post("/api/elements/", json={
        "folder_id": f["id"], "name": "a", "filename": "a.png",
        "data": _b64(b"x"),
    })
    c.post("/api/elements/", json={
        "folder_id": None, "name": "root_one", "filename": "root_one.png",
        "data": _b64(b"y"),
    })

    in_folder = c.get(f"/api/elements/?folder_id={f['id']}").json()
    assert len(in_folder["elements"]) == 1
    assert in_folder["elements"][0]["name"] == "a"

    in_root = c.get("/api/elements/").json()
    assert len(in_root["elements"]) == 1
    assert in_root["elements"][0]["name"] == "root_one"


def test_move_element_between_folders(app_with_temp_appdata):
    c = app_with_temp_appdata
    a = c.post("/api/elements/folders", json={"name": "A"}).json()
    b = c.post("/api/elements/folders", json={"name": "B"}).json()
    e = c.post("/api/elements/", json={
        "folder_id": a["id"], "name": "movable", "filename": "movable.png",
        "data": _b64(b"png"),
    }).json()

    r = c.put(f"/api/elements/{e['id']}", json={"folder_id": b["id"]})
    assert r.status_code == 200
    assert r.json()["folder_id"] == b["id"]

    # 列 A 应当空，列 B 应当有
    assert len(c.get(f"/api/elements/?folder_id={a['id']}").json()["elements"]) == 0
    assert len(c.get(f"/api/elements/?folder_id={b['id']}").json()["elements"]) == 1


def test_delete_folder_cascade_via_api(app_with_temp_appdata):
    c = app_with_temp_appdata
    f = c.post("/api/elements/folders", json={"name": "todrop"}).json()
    c.post("/api/elements/", json={
        "folder_id": f["id"], "name": "x", "filename": "x.png",
        "data": _b64(b"x"),
    })
    r = c.delete(f"/api/elements/folders/{f['id']}")
    assert r.status_code == 204
    assert c.get("/api/elements/folders").json()["folders"] == []


def test_ensure_local_idempotent(app_with_temp_appdata):
    c = app_with_temp_appdata
    fid1 = c.post("/api/elements/ensure-local").json()["folder_id"]
    fid2 = c.post("/api/elements/ensure-local").json()["folder_id"]
    assert fid1 == fid2


# ── Project scope ─────────────────────────────────────────────────────────────


def test_project_elements_isolated_from_global(app_with_temp_appdata, tmp_path):
    """全局元素和项目元素相互独立。"""
    c = app_with_temp_appdata
    # 建一个项目（需要 project.json）
    import json
    pid = "p1"
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "id": pid, "name": "P1", "description": "", "folder_id": "default",
        "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
        "progress": {"manuscript": 0, "scenes": 0, "images": 0, "audio": 0, "video": 0},
    }), encoding="utf-8")

    # 全局放 1 个 element
    c.post("/api/elements/", json={"folder_id": None, "name": "globalonly",
                                    "filename": "g.png", "data": _b64(b"g")})
    # 项目放 1 个
    c.post(f"/api/projects/{pid}/elements/", json={
        "folder_id": None, "name": "projonly",
        "filename": "p.png", "data": _b64(b"p"),
    })

    g_items = c.get("/api/elements/").json()["elements"]
    p_items = c.get(f"/api/projects/{pid}/elements/").json()["elements"]
    assert len(g_items) == 1 and g_items[0]["name"] == "globalonly"
    assert len(p_items) == 1 and p_items[0]["name"] == "projonly"


def test_project_elements_404_when_project_missing(app_with_temp_appdata):
    c = app_with_temp_appdata
    r = c.get("/api/projects/no_such/elements/folders")
    assert r.status_code == 404
