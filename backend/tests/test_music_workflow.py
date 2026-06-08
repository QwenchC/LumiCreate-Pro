"""v1.4.2: ACE-Step 音乐生成工作流补丁 + seed 注入 + 库 CRUD。"""
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / "workflows"


def _load_wf() -> dict:
    p = WORKFLOWS / "audio_ace_step_1_5_split_4b.json"
    if not p.exists():
        pytest.skip("ACE-Step workflow not present")
    return json.loads(p.read_text(encoding="utf-8-sig"))


# ── 补丁 ──────────────────────────────────────────────────────────────────────


def test_patch_writes_all_widgets():
    from services.ace_step_audio import patch_workflow
    wf = _load_wf()
    out = patch_workflow(
        wf, duration_seconds=90, bpm=140, time_signature="3",
        language="zh", key_scale="A minor",
        tags="一首电子摇滚", lyrics="[Verse]\n测试歌词", seed=123456789,
    )
    nodes_by_id = {n["id"]: n for n in out["nodes"]}

    # PrimitiveNode "Song Duration" (99) widget[0] = 90
    assert nodes_by_id[99]["widgets_values"][0] == 90
    # PrimitiveNode "seed" (102) widget[0] = 123456789
    assert nodes_by_id[102]["widgets_values"][0] == 123456789
    # KSampler (3) widget[0] (seed) = 123456789
    assert nodes_by_id[3]["widgets_values"][0] == 123456789
    # EmptyLatentAudio (98) widget[0] = 90
    assert nodes_by_id[98]["widgets_values"][0] == 90
    # TextEncodeAceStepAudio1.5 (94) — tags / lyrics / seed / bpm / duration / timesig / language / keyscale
    te = nodes_by_id[94]["widgets_values"]
    assert te[0] == "一首电子摇滚"     # tags
    assert te[1] == "[Verse]\n测试歌词"  # lyrics
    assert te[2] == 123456789            # seed
    assert te[4] == 140                  # bpm
    assert te[5] == 90.0                 # duration
    assert te[6] == "3"                  # timesignature
    assert te[7] == "zh"                 # language
    assert te[8] == "A minor"            # keyscale
    # SaveAudioMP3 (107) prefix 注入
    assert "lumi_music" in str(nodes_by_id[107]["widgets_values"][0])


def test_patch_does_not_mutate_input():
    """deep-copy 必须，不能改原 workflow。"""
    from services.ace_step_audio import patch_workflow
    wf = _load_wf()
    orig = json.dumps(wf, sort_keys=True)
    _ = patch_workflow(wf, duration_seconds=60, bpm=120, time_signature="4",
                       language="en", key_scale="C major",
                       tags="x", lyrics="y", seed=1)
    after = json.dumps(wf, sort_keys=True)
    assert orig == after


def test_litegraph_to_api_compatible():
    """补丁后必须能正确转为 API 格式，关键节点的连线、widget 不能丢。"""
    from services.ace_step_audio import patch_workflow
    from services.comfyui import _litegraph_to_api
    wf = _load_wf()
    patched = patch_workflow(
        wf, duration_seconds=90, bpm=140, time_signature="4",
        language="zh", key_scale="A minor",
        tags="测试", lyrics="测试", seed=42,
    )
    api = _litegraph_to_api(patched)

    # v1.4.2+: KSampler 的 seed 必须是 PrimitiveNode 内联的字面量（不是 link）。
    # 否则 ComfyUI 会拒 "Node 'Song Duration' not found"。
    assert "3" in api
    ks = api["3"]["inputs"]
    assert ks.get("seed") == 42, f"seed must be inlined literal, got {ks.get('seed')!r}"
    # TextEncode 必须有 tags/lyrics/bpm/keyscale 这些 widget 字段
    te = api["94"]["inputs"]
    assert te.get("bpm") == 140
    assert te.get("timesignature") == "4"
    assert te.get("language") == "zh"
    assert te.get("keyscale") == "A minor"
    assert te.get("tags") == "测试"
    assert te.get("lyrics") == "测试"
    # duration / seed 来自 PrimitiveNode (id=99 / id=102)，必须被内联成数值
    assert te.get("duration") == 90.0 or te.get("duration") == 90
    assert te.get("seed") == 42
    # API 输出不能包含任何 PrimitiveNode（ComfyUI 后端没有这个 class_type）
    primitive_left = [nid for nid, n in api.items() if n["class_type"] == "PrimitiveNode"]
    assert not primitive_left, f"PrimitiveNode leaked into API: {primitive_left}"


# ── seed 随机性 ──────────────────────────────────────────────────────────────


def test_generate_music_always_injects_random_seed_when_none(monkeypatch):
    """seed=None 必须每次注入新随机数；否则用户重新生成永远拿同一首。"""
    from services import ace_step_audio
    wf = _load_wf()

    seeds_seen: list[int] = []

    # 替换 patch_workflow 以拦截 seed
    orig_patch = ace_step_audio.patch_workflow
    def _spy(workflow, *, seed, **kw):
        seeds_seen.append(seed)
        return orig_patch(workflow, seed=seed, **kw)
    monkeypatch.setattr(ace_step_audio, "patch_workflow", _spy)

    # 把 _litegraph_to_api 也短路：返回空 dict 让 httpx 提交时 ComfyUI 返 400
    # 我们只关心 seed 是否被注入（在 patch_workflow 拦截到）
    monkeypatch.setattr("services.comfyui._litegraph_to_api", lambda x: {})

    # mock httpx so we don't actually call ComfyUI
    import httpx
    class _DummyResp:
        status_code = 400
        text = "test"
        def raise_for_status(self): pass
        def json(self): return {"error": {"message": "test"}}
    class _DummyClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, *a, **kw): return _DummyResp()
    monkeypatch.setattr(httpx, "AsyncClient", _DummyClient)

    import asyncio
    async def _runonce():
        async for ev in ace_step_audio.generate_music(
            "http://x", wf, duration_seconds=60, seed=None,
        ):
            if ev.get("event") == "error": return

    asyncio.run(_runonce())
    asyncio.run(_runonce())
    asyncio.run(_runonce())
    assert len(seeds_seen) == 3, seeds_seen
    # 全部不同（理论上有极小概率撞，但 2**63 范围内基本不可能）
    assert len(set(seeds_seen)) == 3, f"seed reused: {seeds_seen}"
    # 全部都是合法的非零正整数
    for s in seeds_seen:
        assert isinstance(s, int) and s > 0


def test_generate_music_respects_explicit_seed(monkeypatch):
    """显式传 seed=N 必须用 N，不能被覆盖。"""
    from services import ace_step_audio
    wf = _load_wf()
    seeds_seen: list[int] = []
    orig_patch = ace_step_audio.patch_workflow
    def _spy(workflow, *, seed, **kw):
        seeds_seen.append(seed)
        return orig_patch(workflow, seed=seed, **kw)
    monkeypatch.setattr(ace_step_audio, "patch_workflow", _spy)
    monkeypatch.setattr("services.comfyui._litegraph_to_api", lambda x: {})
    import httpx
    class _Resp:
        status_code = 400; text = ""
        def raise_for_status(self): pass
        def json(self): return {"error": {"message": "test"}}
    class _C:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, *a, **kw): return _Resp()
    monkeypatch.setattr(httpx, "AsyncClient", _C)

    import asyncio
    async def _run():
        async for ev in ace_step_audio.generate_music(
            "http://x", wf, duration_seconds=60, seed=987654321,
        ):
            if ev.get("event") == "error": return
    asyncio.run(_run())
    asyncio.run(_run())
    assert seeds_seen == [987654321, 987654321]


# ── 工作流列表 / 硬名单 ─────────────────────────────────────────────────────


def test_music_workflow_in_whitelist():
    from routers.music import SUPPORTED_MUSIC_WORKFLOWS
    assert "audio_ace_step_1_5_split_4b" in SUPPORTED_MUSIC_WORKFLOWS


def test_music_workflows_endpoint_only_bundled(isolated_app):
    client = isolated_app["client"]
    r = client.get("/api/music/workflows")
    assert r.status_code == 200, r.text
    names = r.json()
    # 必须包含 ACE-Step，不能漏其它非音乐工作流
    assert names == ["audio_ace_step_1_5_split_4b"], names


# ── 库 CRUD（不打 ComfyUI）─────────────────────────────────────────────────


def test_track_db_schema(isolated_app):
    """global music DB 自动创建 + 基本插入 / 查询通顺。"""
    from services.db import get_global_music_conn, global_music_root
    conn = get_global_music_conn()
    # v1.4.2+: list 端点会过滤丢失文件，所以测试落一个 2KB 文件配合
    (global_music_root() / "intro_42.mp3").write_bytes(b"\x00" * 2048)
    conn.execute(
        "INSERT INTO tracks(name, file_path, mime, project_id, seed, duration_secs,"
        " bpm, time_signature, language, key_scale, tags, lyrics, bytes, created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("intro", "intro_42.mp3", "audio/mpeg", "", 42, 60,
         140, "4", "zh", "C major", "tag", "lyric", 2048,
         "2026-06-08T00:00:00+00:00"),
    )
    conn.commit()

    # GET /tracks 应能查到
    client = isolated_app["client"]
    r = client.get("/api/music/tracks")
    assert r.status_code == 200, r.text
    tracks = r.json()["tracks"]
    assert len(tracks) >= 1
    t = next((x for x in tracks if x["name"] == "intro"), None)
    assert t is not None
    assert t["seed"] == 42
    assert t["bpm"] == 140
    assert t["url"].endswith(f"/api/music/file/{t['id']}")


# ── set-as-project-bgm ────────────────────────────────────────────────────────


def test_set_as_bgm_copies_track_to_project_dir(isolated_app, tmp_path):
    from services.db import get_global_music_conn, global_music_root
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()

    # 准备 track + 文件
    music_root = global_music_root()
    src = music_root / "src.mp3"
    src.write_bytes(b"RAW MUSIC BYTES")
    conn = get_global_music_conn()
    conn.execute(
        "INSERT INTO tracks(name, file_path, mime, project_id, seed, duration_secs,"
        " bpm, time_signature, language, key_scale, tags, lyrics, bytes, created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("MyBGM", "src.mp3", "audio/mpeg", "", 7, 60,
         120, "4", "zh", "C major", "", "", 14,
         "2026-06-08T00:00:00+00:00"),
    )
    conn.commit()
    tid = conn.execute("SELECT id FROM tracks WHERE name='MyBGM'").fetchone()["id"]

    r = client.post(f"/api/music/track/{tid}/set-as-bgm",
                    json={"project_id": pid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["track_id"] == tid
    assert body["filename"] == "bgm.mp3"
    # 物理文件落在项目 bgm/ 目录
    bgm_file = tmp_path / pid / "bgm" / "bgm.mp3"
    assert bgm_file.is_file()
    assert bgm_file.read_bytes() == b"RAW MUSIC BYTES"


def test_set_as_bgm_overwrites_old_bgm(isolated_app, tmp_path):
    """已经存在的 bgm.<ext> 要被新 track 覆盖，不能两首并存。"""
    from services.db import get_global_music_conn, global_music_root
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()
    bgm_dir = tmp_path / pid / "bgm"
    bgm_dir.mkdir(parents=True, exist_ok=True)
    # 老的 BGM 是 .wav
    (bgm_dir / "bgm.wav").write_bytes(b"old")

    music_root = global_music_root()
    (music_root / "new.mp3").write_bytes(b"new")
    conn = get_global_music_conn()
    conn.execute(
        "INSERT INTO tracks(name, file_path, mime, project_id, seed, duration_secs,"
        " bpm, time_signature, language, key_scale, tags, lyrics, bytes, created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("NewBGM", "new.mp3", "audio/mpeg", "", 8, 60,
         120, "4", "zh", "C major", "", "", 3,
         "2026-06-08T00:00:00+00:00"),
    )
    conn.commit()
    tid = conn.execute("SELECT id FROM tracks WHERE name='NewBGM'").fetchone()["id"]

    r = client.post(f"/api/music/track/{tid}/set-as-bgm",
                    json={"project_id": pid})
    assert r.status_code == 200
    # 新 BGM 是 .mp3
    assert (bgm_dir / "bgm.mp3").is_file()
    assert (bgm_dir / "bgm.mp3").read_bytes() == b"new"
    # 老的 .wav 应当被清掉
    assert not (bgm_dir / "bgm.wav").exists()


def test_set_as_bgm_rejects_missing_project(isolated_app):
    from services.db import get_global_music_conn, global_music_root
    client = isolated_app["client"]
    (global_music_root() / "x.mp3").write_bytes(b"x")
    conn = get_global_music_conn()
    conn.execute(
        "INSERT INTO tracks(name, file_path, mime, project_id, seed, duration_secs,"
        " bpm, time_signature, language, key_scale, tags, lyrics, bytes, created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("t", "x.mp3", "audio/mpeg", "", 1, 1, 120, "4", "zh", "C major", "", "", 1,
         "2026-06-08T00:00:00+00:00"),
    )
    conn.commit()
    tid = conn.execute("SELECT id FROM tracks WHERE name='t'").fetchone()["id"]
    r = client.post(f"/api/music/track/{tid}/set-as-bgm",
                    json={"project_id": "ghost_project"})
    assert r.status_code == 404


def test_set_as_bgm_rejects_missing_track(isolated_app):
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()
    r = client.post("/api/music/track/999999/set-as-bgm",
                    json={"project_id": pid})
    assert r.status_code == 404


def test_primitive_node_inlines_constant_into_consumers():
    """Real-world bug: ComfyUI 400 'Node "Song Duration" not found' —— ACE-Step
    workflow uses legacy PrimitiveNode (title='Song Duration') as constant source.
    PrimitiveNode is NOT a valid ComfyUI backend class_type; its widget value
    must be inlined into downstream consumers. Submitting it as a node makes
    ComfyUI think it's a missing custom node."""
    from services.comfyui import _litegraph_to_api
    wf = {
        "nodes": [
            {"id": 99, "type": "PrimitiveNode", "title": "Song Duration",
             "widgets_values": [120, "fixed"],
             "outputs": [{"type": "INT", "links": [10]}]},
            {"id": 50, "type": "EmptyAceStepLatentAudio",
             "inputs": [{"name": "seconds", "type": "FLOAT", "link": 10, "widget": {"name":"seconds"}},
                         {"name": "batch_size", "type": "INT", "widget": {"name":"batch_size"}}],
             "widgets_values": [None, 1]},
        ],
        "links": [
            [10, 99, 0, 50, 0, "INT"],
        ],
    }
    api = _litegraph_to_api(wf)
    # PrimitiveNode 绝不能在 API 里
    assert "99" not in api
    assert not any(n.get("class_type") == "PrimitiveNode" for n in api.values())
    # EmptyAceStepLatentAudio 的 seconds 应被内联为 120
    assert "50" in api
    assert api["50"]["inputs"].get("seconds") == 120


# ── 死 track 过滤 / 清理 ──────────────────────────────────────────────────────


def test_list_tracks_filters_dead_entries(isolated_app):
    """/tracks 应当自动过滤文件丢失 / 体积过小的"幽灵"条目。"""
    from services.db import get_global_music_conn, global_music_root
    client = isolated_app["client"]
    music_root = global_music_root()

    conn = get_global_music_conn()

    # 一个正常 track（文件 2KB）
    good = music_root / "good.mp3"; good.write_bytes(b"x" * 2048)
    # 一个文件丢失的 track
    # 一个文件存在但 < 1KB 的"幽灵"
    tiny = music_root / "tiny.mp3"; tiny.write_bytes(b"y" * 100)

    for name, path in (("good", "good.mp3"), ("missing", "no_file.mp3"), ("tiny", "tiny.mp3")):
        conn.execute(
            "INSERT INTO tracks(name, file_path, mime, project_id, seed, duration_secs,"
            " bpm, time_signature, language, key_scale, tags, lyrics, bytes, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, path, "audio/mpeg", "", 1, 60, 120, "4", "zh", "C major", "", "",
             1, "2026-06-08T00:00:00+00:00"),
        )
    conn.commit()

    r = client.get("/api/music/tracks")
    assert r.status_code == 200, r.text
    names = [t["name"] for t in r.json()["tracks"]]
    assert "good" in names
    assert "missing" not in names
    assert "tiny" not in names


def test_cleanup_dead_tracks_removes_from_db(isolated_app):
    from services.db import get_global_music_conn, global_music_root
    client = isolated_app["client"]
    music_root = global_music_root()

    conn = get_global_music_conn()
    # 1 good + 2 dead
    good = music_root / "ok.mp3"; good.write_bytes(b"x" * 2048)
    tiny = music_root / "smol.mp3"; tiny.write_bytes(b"y" * 50)
    for name, path in (("ok", "ok.mp3"), ("missing", "gone.mp3"), ("smol", "smol.mp3")):
        conn.execute(
            "INSERT INTO tracks(name, file_path, mime, project_id, seed, duration_secs,"
            " bpm, time_signature, language, key_scale, tags, lyrics, bytes, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, path, "audio/mpeg", "", 1, 60, 120, "4", "zh", "C major", "", "",
             1, "2026-06-08T00:00:00+00:00"),
        )
    conn.commit()

    r = client.post("/api/music/cleanup")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted_count"] == 2
    # DB 里只剩 1 个 (ok)
    rows = conn.execute("SELECT name FROM tracks").fetchall()
    assert [row["name"] for row in rows] == ["ok"]
    # 物理上 smol.mp3 也被清掉了
    assert not tiny.exists()
    # 正常的没动
    assert good.exists()
