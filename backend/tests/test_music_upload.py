"""v1.6.2: 音乐库本地音频上传（POST /api/music/upload）。"""
import base64


def _b64(n: int) -> str:
    return base64.b64encode(b"\x00" * n).decode()


def test_music_upload_inserts_and_lists(isolated_app):
    client = isolated_app["client"]
    r = client.post("/api/music/upload", json={
        "filename": "song.mp3", "data": _b64(2048), "name": "我的曲子"})
    assert r.status_code == 200, r.text
    tid = r.json()["track_id"]
    tracks = client.get("/api/music/tracks").json()["tracks"]
    row = next((t for t in tracks if t["id"] == tid), None)
    assert row is not None and row["name"] == "我的曲子"
    assert row["mime"] == "audio/mpeg" and row["tags"] == "上传"
    # 合理默认（避免库列表/参数克隆出现空值）
    assert row["bpm"] == 120 and row["time_signature"] == "4"
    assert row["language"] == "zh" and row["key_scale"] == "C major"
    # 文件可取回
    assert client.get(f"/api/music/file/{tid}").status_code == 200


def test_music_upload_rejects_unsupported_ext(isolated_app):
    client = isolated_app["client"]
    assert client.post("/api/music/upload", json={
        "filename": "x.txt", "data": _b64(2048)}).status_code == 400


def test_music_upload_rejects_tiny(isolated_app):
    client = isolated_app["client"]
    assert client.post("/api/music/upload", json={
        "filename": "x.mp3", "data": _b64(10)}).status_code == 400


def test_music_upload_mime_by_ext(isolated_app):
    client = isolated_app["client"]
    tid = client.post("/api/music/upload", json={
        "filename": "a.wav", "data": _b64(2048)}).json()["track_id"]
    row = next(t for t in client.get("/api/music/tracks").json()["tracks"] if t["id"] == tid)
    assert row["mime"] == "audio/wav"
    # 缺省名 = 文件名 stem
    assert row["name"] == "a"


def test_music_upload_dedupes_filename(isolated_app):
    client = isolated_app["client"]
    f1 = client.post("/api/music/upload", json={
        "filename": "dup.mp3", "data": _b64(2048), "name": "同名"}).json()["filename"]
    f2 = client.post("/api/music/upload", json={
        "filename": "dup.mp3", "data": _b64(2048), "name": "同名"}).json()["filename"]
    assert f1 != f2          # 落盘文件名不冲突


def test_music_upload_series_shared(isolated_app):
    """系列项目上传 → _library_key 归并，系列各集都列得到。"""
    client = isolated_app["client"]
    sid = client.post("/api/series", json={"name": "曲库"}).json()["id"]
    a = client.post("/api/projects", json={"name": "A", "series_id": sid}).json()["id"]
    b = client.post("/api/projects", json={"name": "B", "series_id": sid}).json()["id"]
    client.post("/api/music/upload", json={
        "filename": "s.mp3", "data": _b64(2048), "name": "共享曲", "project_id": a})
    names_b = [t["name"] for t in client.get(f"/api/music/tracks?project_id={b}").json()["tracks"]]
    assert "共享曲" in names_b
