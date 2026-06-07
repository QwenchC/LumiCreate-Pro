"""轮 6: i2i 提示词端点。"""
import base64
import json
import pytest


# 把 stream_chat 替换成 echo —— 测试不打实际 LLM。
@pytest.fixture()
def stubbed_llm(monkeypatch):
    captured = {}

    async def fake_stream_chat(cfg, system, user):
        captured["system"] = system
        captured["user"] = user
        # 返回有效 JSON 响应
        yield '{"start_frame_prompt": "place character from image 1 into scene from image 2 at dawn",'
        yield ' "end_frame_prompt": "compose character pose updated"}'

    import services.llm
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream_chat)
    import routers.text_engine
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream_chat)
    return captured


def test_endpoint_basic_single(isolated_app, stubbed_llm):
    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-img2img-prompt", json={
        "description": "Alice walks into a moonlit forest.",
        "dialogues":   [{"character": "Alice", "text": "Where am I?"}],
        "characters":  [{"name": "Alice", "appearance": "long red hair, blue dress"}],
        "refs":        [{"kind": "path", "path": "/fake/path.png"}],
        "workflow_kind": "i2i_single",
        "project_id":  "",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["start_frame_prompt"].startswith("place character")
    assert data["end_frame_prompt"]

    # 系统提示词必须强调 EDIT INSTRUCTION + 拒绝 style tags
    sys_msg = stubbed_llm["system"]
    assert "EDIT" in sys_msg
    assert "style" in sys_msg.lower()

    # 用户消息应该包含 ref 块、char 块、workflow_kind
    user_msg = stubbed_llm["user"]
    assert "Reference images" in user_msg
    assert "Image 1" in user_msg
    assert "i2i_single" in user_msg
    assert "Alice" in user_msg


def test_endpoint_double_ref(isolated_app, stubbed_llm):
    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-img2img-prompt", json={
        "description": "A dramatic confrontation.",
        "refs": [
            {"kind": "path", "path": "/r1.png"},
            {"kind": "path", "path": "/r2.png"},
        ],
        "workflow_kind": "i2i_double",
    })
    assert r.status_code == 200, r.text
    user_msg = stubbed_llm["user"]
    assert "Image 1" in user_msg
    assert "Image 2" in user_msg
    assert "i2i_double" in user_msg
    assert "2 reference images" in user_msg


def test_endpoint_invalid_kind_rejected(isolated_app, stubbed_llm):
    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-img2img-prompt", json={
        "description": "x",
        "workflow_kind": "t2i",
    })
    assert r.status_code == 400
    assert "i2i_single" in r.text or "i2i_double" in r.text


def test_endpoint_resolves_portrait_ref_appearance(isolated_app, stubbed_llm):
    """portrait kind 的 ref 应能查到角色的 appearance 注入 prompt。"""
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    client.put(f"/api/projects/{pid}/characters", json={"characters": [
        {"name": "Bob", "role": "", "traits": "",
         "appearance": "stocky build, blue uniform",
         "negative": "", "voice": ""},
    ]})
    # 加张立绘
    body = b"\x89PNG_x"
    client.post(f"/api/projects/{pid}/characters/Bob/portraits",
                json={"data": base64.b64encode(body).decode()})

    r = client.post("/api/text-engine/generate-img2img-prompt", json={
        "description": "Bob enters the room.",
        "refs": [{"kind": "portrait", "project_id": pid,
                  "char_name": "Bob", "filename": "portrait_1.png"}],
        "workflow_kind": "i2i_single",
        "project_id": pid,
    })
    assert r.status_code == 200, r.text
    user_msg = stubbed_llm["user"]
    # appearance 文本应出现在 prompt 中
    assert "stocky build" in user_msg
    # ref_descriptions 应识别为 character
    descs = r.json().get("ref_descriptions") or []
    assert len(descs) == 1
    assert descs[0]["role"] == "character"
    assert descs[0]["label"] == "Bob"


def test_endpoint_resolves_unknown_portrait_gracefully(isolated_app, stubbed_llm):
    """portrait 指向不存在的角色 → 不报错，给个 fallback 描述。"""
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()
    r = client.post("/api/text-engine/generate-img2img-prompt", json={
        "description": "x",
        "refs": [{"kind": "portrait", "project_id": pid,
                  "char_name": "Ghost", "filename": "x.png"}],
        "workflow_kind": "i2i_single",
        "project_id": pid,
    })
    assert r.status_code == 200, r.text
    descs = r.json()["ref_descriptions"]
    assert descs[0]["role"] == "character"
    assert "Ghost" in descs[0]["description"]
