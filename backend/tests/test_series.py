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


def test_series_shares_portraits_across_projects(isolated_app):
    """同系列共用【立绘】：A 给角色加立绘，B 立即在同一角色下看到该立绘并可取回文件。"""
    import base64
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "连载立绘"}).json()["id"]
    a = client.post("/api/projects", json={"name": "A集", "series_id": sid}).json()["id"]
    b = client.post("/api/projects", json={"name": "B集", "series_id": sid}).json()["id"]

    # A 建角色 + 传一张立绘（1x1 PNG）
    client.put(f"/api/projects/{a}/characters", json={"characters": [{"name": "小明"}]})
    png = base64.b64encode(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
        "00000049454e44ae426082")).decode()
    up = client.post(f"/api/projects/{a}/characters/小明/portraits",
                     json={"data": png, "set_primary": True})
    assert up.status_code == 200, up.text
    fn = up.json()["filename"]

    # B 在同一角色下看到该立绘（共享池）
    plist = client.get(f"/api/projects/{b}/characters/小明/portraits").json()["portraits"]
    assert [p["filename"] for p in plist] == [fn]
    # B 也能取回立绘文件本体
    assert client.get(
        f"/api/projects/{b}/characters/小明/portraits/file/{fn}").status_code == 200


def test_series_portrait_i2i_ref_resolves_to_shared_dir(isolated_app):
    """回归：系列各集做 i2i 立绘参考时，引用解析须指向系列共享目录（不再 404）。
    （image_engine._resolve_ref_paths 早期硬编码项目目录，系列项目会 404。）"""
    import base64
    from pathlib import Path
    from routers.image_engine import _resolve_ref_paths
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "连载参考"}).json()["id"]
    a = client.post("/api/projects", json={"name": "A集", "series_id": sid}).json()["id"]
    b = client.post("/api/projects", json={"name": "B集", "series_id": sid}).json()["id"]
    client.put(f"/api/projects/{a}/characters", json={"characters": [{"name": "小红"}]})
    png = base64.b64encode(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
        "00000049454e44ae426082")).decode()
    fn = client.post(f"/api/projects/{a}/characters/小红/portraits",
                     json={"data": png, "set_primary": True}).json()["filename"]
    # B 集用同角色立绘做参考：解析成功且指向系列共享目录
    paths = _resolve_ref_paths([{"kind": "portrait", "project_id": b,
                                  "char_name": "小红", "filename": fn}])
    assert len(paths) == 1
    assert "_series" in paths[0].replace("\\", "/")
    assert Path(paths[0]).is_file()


def test_series_shares_elements_across_projects(isolated_app):
    """同系列共用【项目级元素库】：A 上传元素，B 立即在自己的元素库里看到。"""
    import base64
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "连载元素"}).json()["id"]
    a = client.post("/api/projects", json={"name": "A集", "series_id": sid}).json()["id"]
    b = client.post("/api/projects", json={"name": "B集", "series_id": sid}).json()["id"]

    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
    up = client.post(f"/api/projects/{a}/elements/", json={
        "name": "道具A", "filename": "propA.png", "mime": "image/png", "data": png})
    assert up.status_code == 200, up.text

    # B 在自己的元素库里看到同一元素（共享系列库）
    items = client.get(f"/api/projects/{b}/elements/?recursive=true").json()["elements"]
    assert any(e["name"] == "道具A" for e in items)
    # 文件本体也可由 B 取回
    eid = next(e["id"] for e in items if e["name"] == "道具A")
    assert client.get(f"/api/projects/{b}/elements/file/{eid}").status_code == 200


def test_standalone_project_elements_not_shared(isolated_app):
    """独立项目元素库不受系列共享影响（仍各自独立）。"""
    import base64
    client = isolated_app["client"]
    p1 = client.post("/api/projects", json={"name": "独A"}).json()["id"]
    p2 = client.post("/api/projects", json={"name": "独B"}).json()["id"]
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
    client.post(f"/api/projects/{p1}/elements/", json={
        "name": "私有道具", "filename": "x.png", "mime": "image/png", "data": png})
    items2 = client.get(f"/api/projects/{p2}/elements/?recursive=true").json()["elements"]
    assert not any(e["name"] == "私有道具" for e in items2)


def test_series_shares_music_library_across_projects(isolated_app):
    """同系列共用【音乐库】：以系列键入库的曲目，A/B 两集都列得到；独立项目列不到。"""
    from services.db import get_global_music_conn, global_music_root
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "连载音乐"}).json()["id"]
    a = client.post("/api/projects", json={"name": "A集", "series_id": sid}).json()["id"]
    b = client.post("/api/projects", json={"name": "B集", "series_id": sid}).json()["id"]
    solo = client.post("/api/projects", json={"name": "独立"}).json()["id"]

    # 直接以系列键写入一首曲目（生成走 ComfyUI，单测里直接入库验证列举过滤）
    (global_music_root() / "song.mp3").write_bytes(b"\x00" * 2048)
    conn = get_global_music_conn()
    conn.execute(
        "INSERT INTO tracks(name, file_path, project_id, bytes, created_at) "
        "VALUES(?,?,?,?,?)",
        ("片头曲", "song.mp3", f"series:{sid}", 2048, "2024-01-01T00:00:00Z"))
    conn.commit()

    names_a = [t["name"] for t in client.get(f"/api/music/tracks?project_id={a}").json()["tracks"]]
    names_b = [t["name"] for t in client.get(f"/api/music/tracks?project_id={b}").json()["tracks"]]
    names_solo = [t["name"] for t in client.get(f"/api/music/tracks?project_id={solo}").json()["tracks"]]
    assert "片头曲" in names_a and "片头曲" in names_b
    assert "片头曲" not in names_solo


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


# ── v1.6.2 fix: 集数（episode_no）+ 删集策略（shift/blank）─────────────────────────

def _mk_eps(client, sid, names):
    """在系列里按序建若干集，返回 project_id 列表。"""
    return [client.post("/api/projects",
                        json={"name": n, "series_id": sid}).json()["id"] for n in names]


def test_series_episode_numbering_and_order(isolated_app):
    """新建集自动 1,2,3…；series/projects 返回按集数升序的完整 episodes（无空白）。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "集数"}).json()["id"]
    ids = _mk_eps(client, sid, ["甲", "乙", "丙"])
    eps = client.get(f"/api/series/{sid}/projects").json()
    assert eps["max_no"] == 3
    assert [e["no"] for e in eps["episodes"]] == [1, 2, 3]
    assert [e["project_id"] for e in eps["episodes"]] == ids
    assert all(not e["blank"] for e in eps["episodes"])
    # 项目 meta 也持久化了 episode_no
    assert client.get(f"/api/projects/{ids[0]}").json()["episode_no"] == 1
    assert client.get(f"/api/projects/{ids[2]}").json()["episode_no"] == 3


def test_delete_episode_shift_renumbers(isolated_app):
    """删中间集 + shift：后续集 -1，编号保持连续。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "shift"}).json()["id"]
    ids = _mk_eps(client, sid, ["甲", "乙", "丙"])
    r = client.post(f"/api/series/{sid}/delete-episode",
                    json={"project_id": ids[1], "strategy": "shift"})
    assert r.status_code == 200, r.text
    eps = r.json()
    assert eps["max_no"] == 2
    assert [e["no"] for e in eps["episodes"]] == [1, 2]
    assert [e["project_id"] for e in eps["episodes"]] == [ids[0], ids[2]]
    assert all(not e["blank"] for e in eps["episodes"])
    # 原第3集（丙）现在是第2集
    assert client.get(f"/api/projects/{ids[2]}").json()["episode_no"] == 2


def test_delete_episode_blank_keeps_gap_and_new_appends(isolated_app):
    """删中间集 + blank：保留空白集占位，后续不变；之后新建集追加到 max+1（不填空白）。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "blank"}).json()["id"]
    ids = _mk_eps(client, sid, ["甲", "乙", "丙"])
    r = client.post(f"/api/series/{sid}/delete-episode",
                    json={"project_id": ids[1], "strategy": "blank"})
    eps = r.json()
    assert eps["max_no"] == 3
    assert [(e["no"], e["blank"]) for e in eps["episodes"]] == [(1, False), (2, True), (3, False)]
    # 第3集（丙）仍是 3
    assert client.get(f"/api/projects/{ids[2]}").json()["episode_no"] == 3
    # 新建集 → 第4集（追加，不回填空白 2）
    new = client.post("/api/projects", json={"name": "丁", "series_id": sid}).json()["id"]
    assert client.get(f"/api/projects/{new}").json()["episode_no"] == 4
    eps2 = client.get(f"/api/series/{sid}/projects").json()
    assert [(e["no"], e["blank"]) for e in eps2["episodes"]] == \
        [(1, False), (2, True), (3, False), (4, False)]


def test_delete_last_episode_no_gap(isolated_app):
    """删最后一集：直接缩短，不产生空白集。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "last"}).json()["id"]
    ids = _mk_eps(client, sid, ["甲", "乙", "丙"])
    r = client.post(f"/api/series/{sid}/delete-episode",
                    json={"project_id": ids[2], "strategy": "blank"})
    eps = r.json()
    assert eps["max_no"] == 2
    assert [e["no"] for e in eps["episodes"]] == [1, 2]
    assert all(not e["blank"] for e in eps["episodes"])


def test_delete_blank_slot_removes_gap(isolated_app):
    """删空白集占位：消除空缺，后续集 -1。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "rmblank"}).json()["id"]
    ids = _mk_eps(client, sid, ["甲", "乙", "丙"])
    client.post(f"/api/series/{sid}/delete-episode",
                json={"project_id": ids[1], "strategy": "blank"})   # 空白集在 2
    r = client.post(f"/api/series/{sid}/delete-blank", json={"episode_no": 2})
    assert r.status_code == 200, r.text
    eps = r.json()
    assert eps["max_no"] == 2
    assert [e["project_id"] for e in eps["episodes"]] == [ids[0], ids[2]]
    assert client.get(f"/api/projects/{ids[2]}").json()["episode_no"] == 2
    # 占用集不是空白集 → 拒绝
    assert client.post(f"/api/series/{sid}/delete-blank",
                       json={"episode_no": 1}).status_code == 400


def test_shift_delete_densifies_and_removes_preexisting_blank(isolated_app):
    """shift = 保持连续编号：删中间集时把全系列重排为 1..N，连此前遗留的空白集一并消除。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "致密"}).json()["id"]
    ids = _mk_eps(client, sid, ["甲", "乙", "丙", "丁"])     # 1,2,3,4
    # 先 blank 删乙 → 空白集在 2： 甲(1),[2空],丙(3),丁(4)
    client.post(f"/api/series/{sid}/delete-episode",
                json={"project_id": ids[1], "strategy": "blank"})
    # 再 shift 删丙 → 期望整体重排连续：甲(1),丁(2)，无任何空白
    r = client.post(f"/api/series/{sid}/delete-episode",
                    json={"project_id": ids[2], "strategy": "shift"})
    eps = r.json()
    assert eps["max_no"] == 2
    assert all(not e["blank"] for e in eps["episodes"])
    assert [e["project_id"] for e in eps["episodes"]] == [ids[0], ids[3]]
    assert client.get(f"/api/projects/{ids[3]}").json()["episode_no"] == 2


def test_delete_blank_rejects_nonpositive_episode_no(isolated_app):
    """delete-blank 的 episode_no 必须 >=1：传 0/负数被拒，且不腐蚀任何集号（CRITICAL 回归）。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "防腐蚀"}).json()["id"]
    ids = _mk_eps(client, sid, ["甲", "乙", "丙"])
    assert client.post(f"/api/series/{sid}/delete-blank",
                       json={"episode_no": 0}).status_code == 422
    assert client.post(f"/api/series/{sid}/delete-blank",
                       json={"episode_no": -1}).status_code == 422
    # 集号完好无损
    assert client.get(f"/api/projects/{ids[0]}").json()["episode_no"] == 1
    assert client.get(f"/api/projects/{ids[1]}").json()["episode_no"] == 2
    assert client.get(f"/api/projects/{ids[2]}").json()["episode_no"] == 3


def test_chapter_usage_includes_episode_no(isolated_app):
    """章节 used_by 带 episode_no + project_name，供「第n集：项目名」显示。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "章节集"}).json()["id"]
    c1 = client.post(f"/api/series/{sid}/chapters",
                     json={"title": "序", "content": "内容X"}).json()["id"]
    _mk_eps(client, sid, ["甲"])                       # 第1集（不引用章节）
    p2 = client.post("/api/projects", json={
        "name": "乙", "series_id": sid, "chapter_ids": [c1]}).json()["id"]   # 第2集引用 c1
    chs = client.get(f"/api/series/{sid}/chapters").json()["chapters"]
    used = next(c for c in chs if c["id"] == c1)["used_by"]
    assert len(used) == 1
    assert used[0]["episode_no"] == 2 and used[0]["project_name"] == "乙"
    assert used[0]["project_id"] == p2
