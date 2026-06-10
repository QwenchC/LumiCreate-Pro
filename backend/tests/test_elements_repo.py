"""轮 2: ElementsRepo + 全局/项目级 elements API。"""
import base64
import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_global(tmp_path, monkeypatch):
    """全局元素库隔离：APPDATA 重定向到 tmp。"""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    # reload config + db 以确保 SETTINGS_PATH 用 patched APPDATA
    import config
    importlib.reload(config)
    from services import db
    importlib.reload(db)
    from services import elements_repo
    importlib.reload(elements_repo)
    yield {"tmp": tmp_path, "repo": elements_repo, "db": db}
    db.close_all()


def test_create_folder_root(isolated_global):
    repo = isolated_global["repo"]
    f = repo.create_folder("global", "characters")
    assert f["id"] is not None
    assert f["name"] == "characters"
    assert f["parent_id"] is None
    assert f["path"] == "characters"


def test_create_nested_folder(isolated_global):
    repo = isolated_global["repo"]
    f1 = repo.create_folder("global", "anime")
    f2 = repo.create_folder("global", "girls", parent_id=f1["id"])
    f3 = repo.create_folder("global", "blue_hair", parent_id=f2["id"])
    assert f3["path"] == "anime/girls/blue_hair"


def test_list_folders(isolated_global):
    repo = isolated_global["repo"]
    repo.create_folder("global", "a")
    f_a = repo.list_folders("global")[0]
    repo.create_folder("global", "b", parent_id=f_a["id"])
    folders = repo.list_folders("global")
    assert len(folders) == 2
    paths = {f["path"] for f in folders}
    assert paths == {"a", "a/b"}


def test_rename_folder_updates_descendants_path(isolated_global):
    repo = isolated_global["repo"]
    a = repo.create_folder("global", "alpha")
    b = repo.create_folder("global", "beta", parent_id=a["id"])
    c = repo.create_folder("global", "gamma", parent_id=b["id"])

    repo.rename_folder("global", a["id"], "ALPHA2")

    paths = {f["id"]: f["path"] for f in repo.list_folders("global")}
    assert paths[a["id"]] == "ALPHA2"
    assert paths[b["id"]] == "ALPHA2/beta"
    assert paths[c["id"]] == "ALPHA2/beta/gamma"


def test_move_folder_under_self_rejected(isolated_global):
    repo = isolated_global["repo"]
    a = repo.create_folder("global", "a")
    b = repo.create_folder("global", "b", parent_id=a["id"])
    with pytest.raises(ValueError, match="under itself"):
        repo.move_folder("global", a["id"], b["id"])


def test_move_folder_to_new_parent(isolated_global):
    repo = isolated_global["repo"]
    a = repo.create_folder("global", "a")
    b = repo.create_folder("global", "b")
    c = repo.create_folder("global", "c", parent_id=a["id"])

    repo.move_folder("global", c["id"], b["id"])
    paths = {f["id"]: f["path"] for f in repo.list_folders("global")}
    assert paths[c["id"]] == "b/c"


def test_upload_and_list_element_in_root(isolated_global):
    repo = isolated_global["repo"]
    elem = repo.create_element(
        "global",
        folder_id=None,
        name="kitty",
        file_bytes=b"\x89PNG_FAKE",
        filename="kitty.png",
        mime="image/png",
    )
    assert elem["id"]
    assert elem["folder_id"] is None
    assert elem["bytes"] == 9

    items = repo.list_elements("global", folder_id=None)
    assert len(items) == 1
    assert items[0]["name"] == "kitty"


def test_upload_into_folder_creates_subdir(isolated_global):
    repo = isolated_global["repo"]
    root = isolated_global["tmp"] / "LumiCreate-Pro" / "elements"
    f = repo.create_folder("global", "characters")
    elem = repo.create_element(
        "global", folder_id=f["id"], name="hero",
        file_bytes=b"png-bytes", filename="hero.png",
    )
    # 物理文件落到 elements/characters/hero.png
    assert (root / "characters" / "hero.png").exists()
    assert elem["file_path"] == "characters/hero.png"


def test_unique_filename_avoids_overwrite(isolated_global):
    repo = isolated_global["repo"]
    e1 = repo.create_element("global", folder_id=None, name="a",
                              file_bytes=b"x", filename="a.png")
    e2 = repo.create_element("global", folder_id=None, name="a",
                              file_bytes=b"y", filename="a.png")
    assert e1["file_path"] != e2["file_path"]
    assert "(2)" in e2["file_path"]


def test_list_elements_recursive(isolated_global):
    repo = isolated_global["repo"]
    root_f = repo.create_folder("global", "stuff")
    sub_f = repo.create_folder("global", "sub", parent_id=root_f["id"])
    repo.create_element("global", folder_id=root_f["id"], name="x",
                        file_bytes=b"x", filename="x.png")
    repo.create_element("global", folder_id=sub_f["id"], name="y",
                        file_bytes=b"y", filename="y.png")
    flat = repo.list_elements("global", folder_id=root_f["id"], recursive=False)
    assert len(flat) == 1
    deep = repo.list_elements("global", folder_id=root_f["id"], recursive=True)
    assert len(deep) == 2


def test_delete_element_removes_file(isolated_global):
    repo = isolated_global["repo"]
    root = isolated_global["tmp"] / "LumiCreate-Pro" / "elements"
    e = repo.create_element("global", folder_id=None, name="t",
                            file_bytes=b"t", filename="t.png")
    assert (root / "t.png").exists()
    repo.delete_element("global", e["id"])
    assert not (root / "t.png").exists()
    assert repo.get_element("global", e["id"]) is None


def test_delete_folder_cascade(isolated_global):
    repo = isolated_global["repo"]
    root = isolated_global["tmp"] / "LumiCreate-Pro" / "elements"
    a = repo.create_folder("global", "a")
    b = repo.create_folder("global", "b", parent_id=a["id"])
    repo.create_element("global", folder_id=a["id"], name="x",
                        file_bytes=b"x", filename="x.png")
    repo.create_element("global", folder_id=b["id"], name="y",
                        file_bytes=b"y", filename="y.png")

    repo.delete_folder("global", a["id"], cascade=True)
    assert repo.list_folders("global") == []
    assert not (root / "a").exists()


def test_delete_folder_non_cascade_when_empty(isolated_global):
    repo = isolated_global["repo"]
    a = repo.create_folder("global", "empty")
    repo.delete_folder("global", a["id"], cascade=False)
    assert repo.list_folders("global") == []


def test_delete_folder_non_cascade_when_not_empty_errors(isolated_global):
    repo = isolated_global["repo"]
    a = repo.create_folder("global", "a")
    repo.create_element("global", folder_id=a["id"], name="x",
                        file_bytes=b"x", filename="x.png")
    with pytest.raises(RuntimeError, match="not empty"):
        repo.delete_folder("global", a["id"], cascade=False)


def test_move_element_to_folder(isolated_global):
    repo = isolated_global["repo"]
    root = isolated_global["tmp"] / "LumiCreate-Pro" / "elements"
    a = repo.create_folder("global", "a")
    e = repo.create_element("global", folder_id=None, name="moveme",
                            file_bytes=b"x", filename="moveme.png")
    assert (root / "moveme.png").exists()
    repo.update_element("global", e["id"], folder_id=a["id"])
    assert (root / "a" / "moveme.png").exists()
    assert not (root / "moveme.png").exists()


def test_ensure_local_folder_idempotent(isolated_global):
    repo = isolated_global["repo"]
    f1 = repo.ensure_local_folder("global")
    f2 = repo.ensure_local_folder("global")
    assert f1 == f2


def test_invalid_folder_name(isolated_global):
    repo = isolated_global["repo"]
    with pytest.raises(ValueError):
        repo.create_folder("global", "bad/name")
    with pytest.raises(ValueError):
        repo.create_folder("global", "bad\\name")


# ── v1.5.0: 跨库复制（全局 ↔ 项目共通）────────────────────────────────────────


def test_copy_element_into_other_folder(isolated_global):
    """copy_element：读源字节 + 在目标文件夹另落一份新元素（新 id，原件保留）。"""
    repo = isolated_global["repo"]
    root = isolated_global["tmp"] / "LumiCreate-Pro" / "elements"
    dst = repo.create_folder("global", "dst")
    src = repo.create_element("global", folder_id=None, name="logo",
                              file_bytes=b"PNGDATA", filename="logo.png",
                              width=64, height=64)
    copied = repo.copy_element("global", src["id"], "global",
                               dst_folder_id=dst["id"])
    # 新元素：不同 id、落在目标文件夹、字节一致、宽高沿用
    assert copied["id"] != src["id"]
    assert copied["folder_id"] == dst["id"]
    assert copied["width"] == 64 and copied["height"] == 64
    assert (root / copied["file_path"]).read_bytes() == b"PNGDATA"
    # 原件仍在
    assert repo.get_element("global", src["id"]) is not None
    # source_meta 记录来源
    assert copied["source_meta"].get("copied_from", {}).get("element_id") == src["id"]


def test_copy_element_missing_raises(isolated_global):
    repo = isolated_global["repo"]
    with pytest.raises(KeyError):
        repo.copy_element("global", 99999, "global")
