"""v1.6.3: 角色多外观（appearances[] + 立绘按外观分组 + derive-appearance + i2i 按外观）。"""
import base64
import pytest


def _b64(b: bytes = b"\x89PNG_x") -> str:
    return base64.b64encode(b).decode()


# 复用 i2i 测试的 LLM echo stub
@pytest.fixture()
def stubbed_llm(monkeypatch):
    captured = {}

    async def fake_stream_chat(cfg, system, user):
        captured["system"] = system
        captured["user"] = user
        yield '{"start_frame_prompt": "x", "end_frame_prompt": "y"}'

    import services.llm
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream_chat)
    import routers.text_engine
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream_chat)
    return captured


def test_legacy_single_appearance_migrates_to_default(isolated_app):
    """旧项目单 appearance → GET 返回 appearances[] 含一个默认「常态」，appearance 同步默认。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    client.put(f"/api/projects/{pid}/characters", json={"characters": [
        {"name": "Old", "role": "", "traits": "", "appearance": "tall, brown hair",
         "negative": "", "voice": ""}]})
    got = client.get(f"/api/projects/{pid}/characters").json()["characters"][0]
    apps = got["appearances"]
    assert isinstance(apps, list) and len(apps) == 1
    assert apps[0]["is_default"] is True
    assert apps[0]["text"] == "tall, brown hair"
    assert got["appearance"] == "tall, brown hair"     # 同步默认外观


def test_appearances_round_trip_and_default_sync(isolated_app):
    """PUT 多外观 → GET 保留；appearance 恒等于默认外观文本。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    client.put(f"/api/projects/{pid}/characters", json={"characters": [{
        "name": "Cara",
        "appearances": [
            {"id": "default", "name": "常态", "text": "silver hair, school uniform", "is_default": True},
            {"id": "ap_bed", "name": "卧床", "text": "silver hair, lying in bed, pajamas", "is_default": False},
        ],
    }]})
    got = client.get(f"/api/projects/{pid}/characters").json()["characters"][0]
    assert [a["id"] for a in got["appearances"]] == ["default", "ap_bed"]
    assert got["appearance"] == "silver hair, school uniform"   # = 默认


def test_only_one_default_enforced(isolated_app):
    """多个 is_default → 规整为只保留第一个。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    client.put(f"/api/projects/{pid}/characters", json={"characters": [{
        "name": "Dup",
        "appearances": [
            {"id": "a1", "name": "A", "text": "tA", "is_default": True},
            {"id": "a2", "name": "B", "text": "tB", "is_default": True},
        ],
    }]})
    apps = client.get(f"/api/projects/{pid}/characters").json()["characters"][0]["appearances"]
    assert [a["is_default"] for a in apps] == [True, False]


def test_portrait_appearance_id_and_per_appearance_primary(isolated_app):
    """立绘带 appearance_id；is_primary 在每个外观内各自独立。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    client.put(f"/api/projects/{pid}/characters", json={"characters": [{
        "name": "Cara",
        "appearances": [
            {"id": "default", "name": "常态", "text": "silver hair", "is_default": True},
            {"id": "ap_bed", "name": "卧床", "text": "lying in bed", "is_default": False},
        ],
    }]})
    # 默认外观传一张 → 自动主图
    client.post(f"/api/projects/{pid}/characters/Cara/portraits",
                json={"data": _b64(), "appearance_id": "default"})
    # 卧床外观传一张 → 在该外观内也自动主图（与默认互不影响）
    up2 = client.post(f"/api/projects/{pid}/characters/Cara/portraits",
                      json={"data": _b64(), "appearance_id": "ap_bed"})
    assert up2.json()["appearance_id"] == "ap_bed"

    plist = client.get(f"/api/projects/{pid}/characters/Cara/portraits").json()["portraits"]
    by_app = {}
    for p in plist:
        by_app.setdefault(p["appearance_id"], []).append(p)
    assert set(by_app) == {"default", "ap_bed"}
    # 两个外观各有一张主图
    assert sum(1 for p in by_app["default"] if p["is_primary"]) == 1
    assert sum(1 for p in by_app["ap_bed"] if p["is_primary"]) == 1


def test_set_primary_scoped_to_appearance(isolated_app):
    """设主只在该立绘所属外观内生效，不动其它外观的主图。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    client.put(f"/api/projects/{pid}/characters", json={"characters": [{
        "name": "Cara",
        "appearances": [{"id": "default", "name": "常态", "text": "x", "is_default": True},
                        {"id": "ap_bed", "name": "卧床", "text": "y", "is_default": False}],
    }]})
    client.post(f"/api/projects/{pid}/characters/Cara/portraits", json={"data": _b64(), "appearance_id": "default"})
    client.post(f"/api/projects/{pid}/characters/Cara/portraits", json={"data": _b64(), "appearance_id": "ap_bed"})    # portrait_2 primary of ap_bed
    client.post(f"/api/projects/{pid}/characters/Cara/portraits", json={"data": _b64(), "appearance_id": "ap_bed"})    # portrait_3 (not primary)
    # 把 ap_bed 的 portrait_3 设主
    client.put(f"/api/projects/{pid}/characters/Cara/portraits/portrait_3.png/select")
    plist = {p["filename"]: p for p in client.get(f"/api/projects/{pid}/characters/Cara/portraits").json()["portraits"]}
    assert plist["portrait_1.png"]["is_primary"] is True     # 默认外观主图不受影响
    assert plist["portrait_2.png"]["is_primary"] is False    # 同外观旧主图被取消
    assert plist["portrait_3.png"]["is_primary"] is True


def test_i2i_describe_ref_uses_selected_appearance(isolated_app, stubbed_llm):
    """portrait ref 落在变体外观 → i2i 提示词注入该变体文本（而非默认）。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    client.put(f"/api/projects/{pid}/characters", json={"characters": [{
        "name": "Cara",
        "appearances": [
            {"id": "default", "name": "常态", "text": "silver hair, school uniform", "is_default": True},
            {"id": "ap_bed", "name": "卧床", "text": "silver hair, lying in bed, pajamas", "is_default": False},
        ],
    }]})
    client.post(f"/api/projects/{pid}/characters/Cara/portraits",
                json={"data": _b64(), "appearance_id": "ap_bed"})   # portrait_1 → ap_bed
    # ref 不带 appearance_id：靠 filename 反查所属外观
    r = client.post("/api/text-engine/generate-img2img-prompt", json={
        "description": "Cara rests.",
        "refs": [{"kind": "portrait", "project_id": pid, "char_name": "Cara", "filename": "portrait_1.png"}],
        "workflow_kind": "i2i_single", "project_id": pid,
    })
    assert r.status_code == 200, r.text
    user_msg = stubbed_llm["user"]
    assert "lying in bed" in user_msg          # 变体文本
    assert "school uniform" not in user_msg    # 不是默认文本


def test_derive_appearance_feeds_base_and_variation(isolated_app, stubbed_llm):
    """derive-appearance 把常态 + 变体说明都送进 LLM。"""
    client = isolated_app["client"]
    r = client.post("/api/text-engine/derive-appearance", json={
        "name": "Cara", "base_appearance": "silver hair, red eyes, school uniform",
        "variation": "lying in bed, eyes closed, pajamas",
    })
    assert r.status_code == 200, r.text
    user_msg = stubbed_llm["user"]
    assert "silver hair, red eyes" in user_msg
    assert "lying in bed" in user_msg


def test_derive_appearance_requires_variation(isolated_app):
    client = isolated_app["client"]
    assert client.post("/api/text-engine/derive-appearance",
                       json={"base_appearance": "x", "variation": ""}).status_code == 400


def test_normalize_tolerates_malformed_appearances(isolated_app):
    """脏 appearances（混入 str/None 等非 dict）不应让保存/读取 500（对抗评审回归）。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    r = client.put(f"/api/projects/{pid}/characters", json={"characters": [
        {"name": "X", "appearances": ["junk", None, {"id": "a", "text": "t"}]}]})
    assert r.status_code == 200, r.text
    got = client.get(f"/api/projects/{pid}/characters").json()["characters"][0]
    assert isinstance(got["appearances"], list)
    assert all(isinstance(a, dict) for a in got["appearances"])
    assert sum(1 for a in got["appearances"] if a.get("is_default")) == 1
