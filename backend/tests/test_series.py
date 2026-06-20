"""v1.6.2: 系列连载（series）—— CRUD + 章节 + 章节导入 + 角色共享池。"""
import json


def test_series_crud_and_chapters(isolated_app):
    client = isolated_app["client"]
    # 建系列
    r = client.post("/api/series", json={"name": "我的连载", "emoji": "📖"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["emoji"] == "📖"
    assert any(s["id"] == sid for s in client.get("/api/series").json())

    # 加 2 章
    c1 = client.post(f"/api/series/{sid}/chapters",
                     json={"title": "第一章", "content": "第一章正文。"}).json()["id"]
    c2 = client.post(f"/api/series/{sid}/chapters",
                     json={"title": "第二章", "content": "第二章正文。"}).json()["id"]
    chs = client.get(f"/api/series/{sid}/chapters").json()["chapters"]
    assert [c["title"] for c in chs] == ["第一章", "第二章"]
    assert all(c["used_by"] == [] for c in chs)        # 尚无项目用过

    # 改章节 + 删章节
    client.put(f"/api/series/{sid}/chapters/{c1}", json={"title": "第一章改", "content": "改后正文。"})
    chs = client.get(f"/api/series/{sid}/chapters").json()["chapters"]
    assert chs[0]["title"] == "第一章改"
    client.delete(f"/api/series/{sid}/chapters/{c2}")
    assert len(client.get(f"/api/series/{sid}/chapters").json()["chapters"]) == 1


def test_create_project_in_series_imports_chapters_and_marks_usage(isolated_app):
    client = isolated_app["client"]
    pdir_root = isolated_app["tmp_path"]
    sid = client.post("/api/series", json={"name": "连载A"}).json()["id"]
    c1 = client.post(f"/api/series/{sid}/chapters",
                     json={"title": "序章", "content": "序章内容AAA。"}).json()["id"]
    c2 = client.post(f"/api/series/{sid}/chapters",
                     json={"title": "第一回", "content": "第一回内容BBB。"}).json()["id"]

    # 在系列里建项目，勾选两章
    r = client.post("/api/projects", json={
        "name": "第1集", "series_id": sid, "chapter_ids": [c1, c2],
        "folder_id": "default",
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["series_id"] == sid

    # 章节文案被导入 manuscript.md（按勾选顺序拼接）
    ms = client.get(f"/api/projects/{pid}/manuscript").json()
    assert "序章内容AAA" in ms["content"] and "第一回内容BBB" in ms["content"]
    assert ms["content"].index("序章内容AAA") < ms["content"].index("第一回内容BBB")

    # 章节 used_by 现在标注被「第1集」用过
    chs = client.get(f"/api/series/{sid}/chapters").json()["chapters"]
    used = {c["id"]: [u["project_name"] for u in c["used_by"]] for c in chs}
    assert used[c1] == ["第1集"] and used[c2] == ["第1集"]


def test_series_shares_characters_across_projects(isolated_app):
    """同系列两个项目【共用角色池】：A 存的角色，B 立即读到。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "连载B"}).json()["id"]
    a = client.post("/api/projects", json={"name": "A集", "series_id": sid}).json()["id"]
    b = client.post("/api/projects", json={"name": "B集", "series_id": sid}).json()["id"]

    # 在 A 存角色
    client.put(f"/api/projects/{a}/characters", json={"characters": [
        {"name": "主角", "role": "protagonist", "appearance": "银发"}]})
    # B 立即读到同一份（共享池）
    chars_b = client.get(f"/api/projects/{b}/characters").json()["characters"]
    assert [c["name"] for c in chars_b] == ["主角"]
    assert chars_b[0]["appearance"] == "银发"


def test_series_delete_blocked_when_projects_exist(isolated_app):
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "连载C"}).json()["id"]
    client.post("/api/projects", json={"name": "X集", "series_id": sid})
    r = client.delete(f"/api/series/{sid}")
    assert r.status_code == 409          # 有项目 → 拒绝删除


def test_standalone_project_uses_own_characters(isolated_app):
    """非系列项目仍用自己的角色目录（共享池改动不影响独立项目）。"""
    client = isolated_app["client"]
    p = client.post("/api/projects", json={"name": "独立"}).json()["id"]
    client.put(f"/api/projects/{p}/characters", json={"characters": [{"name": "独角"}]})
    assert [c["name"] for c in client.get(f"/api/projects/{p}/characters").json()["characters"]] == ["独角"]
