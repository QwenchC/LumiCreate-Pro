"""轮 4: 角色立绘 CRUD 端到端测试。"""
import base64
import json
from pathlib import Path


def _make_chars(client, pid, names):
    chars = [{"name": n, "role": "", "traits": "", "appearance": "",
              "negative": "", "voice": ""} for n in names]
    r = client.put(f"/api/projects/{pid}/characters", json={"characters": chars})
    assert r.status_code == 200, r.text


def _png_b64(prefix=b"PNG") -> str:
    return base64.b64encode(b"\x89" + prefix + b"_fake").decode()


def test_add_portrait_creates_file_and_updates_json(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid

    _make_chars(client, pid, ["Alice"])
    r = client.post(
        f"/api/projects/{pid}/characters/Alice/portraits",
        json={"data": _png_b64(), "workflow_name": "t2i-lumicreate",
              "prompt": "a girl"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "portrait_1.png"
    assert body["is_primary"] is True   # 第一张自动主图

    # 文件落盘
    pf = pdir / "characters" / "Alice" / "portrait_1.png"
    assert pf.exists()

    # characters.json 更新
    cj = json.loads((pdir / "characters.json").read_text(encoding="utf-8-sig"))
    char = cj["characters"][0]
    assert len(char["portraits"]) == 1
    assert char["portraits"][0]["filename"] == "portrait_1.png"
    assert char["portraits"][0]["is_primary"] is True


def test_add_multiple_portraits_increments_number(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _make_chars(client, pid, ["Bob"])
    for i in range(3):
        r = client.post(
            f"/api/projects/{pid}/characters/Bob/portraits",
            json={"data": _png_b64()},
        )
        assert r.status_code == 200
        assert r.json()["filename"] == f"portrait_{i+1}.png"


def test_only_first_is_primary_by_default(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _make_chars(client, pid, ["Cat"])

    p1 = client.post(f"/api/projects/{pid}/characters/Cat/portraits",
                     json={"data": _png_b64()}).json()
    p2 = client.post(f"/api/projects/{pid}/characters/Cat/portraits",
                     json={"data": _png_b64()}).json()
    assert p1["is_primary"] is True
    assert p2["is_primary"] is False


def test_set_primary_flips_old_primary(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _make_chars(client, pid, ["Dog"])

    client.post(f"/api/projects/{pid}/characters/Dog/portraits",
                json={"data": _png_b64()})
    client.post(f"/api/projects/{pid}/characters/Dog/portraits",
                json={"data": _png_b64()})

    r = client.put(
        f"/api/projects/{pid}/characters/Dog/portraits/portrait_2.png/select"
    )
    assert r.status_code == 200

    lst = client.get(f"/api/projects/{pid}/characters/Dog/portraits").json()["portraits"]
    by_fn = {p["filename"]: p for p in lst}
    assert by_fn["portrait_2.png"]["is_primary"] is True
    assert by_fn["portrait_1.png"]["is_primary"] is False


def test_serve_portrait_file_returns_png(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _make_chars(client, pid, ["Eve"])
    body = b"\x89PNG\r\n\x1a\n_REAL_"
    client.post(
        f"/api/projects/{pid}/characters/Eve/portraits",
        json={"data": base64.b64encode(body).decode()},
    )
    r = client.get(
        f"/api/projects/{pid}/characters/Eve/portraits/file/portrait_1.png"
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == body


def test_delete_portrait_removes_file_and_promotes_next_primary(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid
    _make_chars(client, pid, ["Fox"])

    client.post(f"/api/projects/{pid}/characters/Fox/portraits",
                json={"data": _png_b64()})
    client.post(f"/api/projects/{pid}/characters/Fox/portraits",
                json={"data": _png_b64()})

    # 删主图（p1）
    r = client.delete(
        f"/api/projects/{pid}/characters/Fox/portraits/portrait_1.png"
    )
    assert r.status_code == 204
    # 物理文件消失
    assert not (pdir / "characters" / "Fox" / "portrait_1.png").exists()
    # 剩下的 p2 自动晋升为主图
    lst = client.get(f"/api/projects/{pid}/characters/Fox/portraits").json()["portraits"]
    assert len(lst) == 1
    assert lst[0]["filename"] == "portrait_2.png"
    assert lst[0]["is_primary"] is True


def test_path_traversal_rejected(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _make_chars(client, pid, ["X"])
    # 各种危险文件名
    r = client.delete(f"/api/projects/{pid}/characters/X/portraits/..%2Fproject.json")
    # FastAPI 的路径参数会 URL-decode；但即使解码后我们的检查也会拒绝
    assert r.status_code in (400, 404, 422)

    r = client.get(f"/api/projects/{pid}/characters/X/portraits/file/..%2Fsecret")
    assert r.status_code in (400, 404, 422)


def test_chinese_character_name_supported(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid
    _make_chars(client, pid, ["林夏"])
    import urllib.parse
    enc = urllib.parse.quote("林夏")
    r = client.post(
        f"/api/projects/{pid}/characters/{enc}/portraits",
        json={"data": _png_b64()},
    )
    assert r.status_code == 200
    # 物理目录用安全化后的中文名
    assert (pdir / "characters" / "林夏" / "portrait_1.png").exists()


def test_list_returns_url_for_each_portrait(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    _make_chars(client, pid, ["Y"])
    client.post(f"/api/projects/{pid}/characters/Y/portraits",
                json={"data": _png_b64()})
    lst = client.get(f"/api/projects/{pid}/characters/Y/portraits").json()["portraits"]
    assert lst[0]["url"].endswith("/Y/portraits/file/portrait_1.png")
    assert lst[0]["exists_on_disk"] is True


def test_add_portrait_for_nonexistent_char_creates_stub(isolated_app):
    """允许给不存在的角色加立绘 → 自动创建角色 stub。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    r = client.post(
        f"/api/projects/{pid}/characters/Ghost/portraits",
        json={"data": _png_b64()},
    )
    assert r.status_code == 200
    # characters.json 出现 Ghost
    chars = client.get(f"/api/projects/{pid}/characters").json()["characters"]
    assert any(c["name"] == "Ghost" for c in chars)
