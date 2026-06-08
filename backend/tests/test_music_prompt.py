"""v1.4.2: AI 助写音乐标签 + 歌词端点。"""
import pytest


@pytest.fixture()
def stubbed_llm(monkeypatch):
    """把 stream_chat 替换成可控的 fake，记录系统/用户消息。"""
    captured = {}

    async def fake_stream_chat(cfg, system, user):
        captured["system"] = system
        captured["user"] = user
        yield '{"tags": "一首武侠燃曲，低沉笛声开场，副歌爆发",'
        yield ' "lyrics": "[Intro — low dizi]\\n[Verse 1]\\n剑出鞘\\n[Chorus]\\n刀光剑影\\n[Outro — fade]"}'

    import services.llm
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream_chat)
    import routers.text_engine
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream_chat)
    return captured


def test_endpoint_basic(isolated_app, stubbed_llm):
    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-music-prompt", json={
        "user_request":     "一首武侠燃曲，开场低沉笛声，副歌爆发",
        "language":         "zh",
        "duration_seconds": 60,
        "bpm":              140,
        "time_signature":   "4",
        "key_scale":        "A minor",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert "tags" in data and "lyrics" in data
    assert "武侠燃曲" in data["tags"]
    assert "[Verse 1]" in data["lyrics"]
    assert "[Chorus]" in data["lyrics"]
    # 系统消息必须强调 JSON only + structure rules
    sys_msg = stubbed_llm["system"]
    assert "JSON" in sys_msg
    assert "STRUCTURE" in sys_msg
    # 用户消息含核心字段（结构化参数依然要传，让 LLM 内部参考节奏 / 段落结构）
    user_msg = stubbed_llm["user"]
    assert "Chinese" in user_msg or "中文" in user_msg
    assert "60s" in user_msg or "60 second" in user_msg
    assert "140 BPM" in user_msg
    assert "A minor" in user_msg
    # 但 user message 必须明确禁止把这些数字 / 调名抄进 tags
    assert "DO NOT mention" in user_msg or "DO NOT write" in user_msg or "never write" in user_msg.lower()


def test_endpoint_requires_user_request(isolated_app, stubbed_llm):
    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-music-prompt", json={
        "user_request": "   ",
        "language": "zh",
    })
    assert r.status_code == 400


def test_endpoint_instrumental_mode_appends_directive(isolated_app, stubbed_llm):
    """include_lyrics=False 时系统提示加 INSTRUMENTAL 指令，让 LLM 留空 lyrics。"""
    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-music-prompt", json={
        "user_request":   "纯器乐 BGM",
        "include_lyrics": False,
    })
    assert r.status_code == 200
    sys_msg = stubbed_llm["system"]
    assert "INSTRUMENTAL" in sys_msg
    assert "lyrics" in sys_msg.lower()


def test_endpoint_pulls_project_manuscript_context(isolated_app, stubbed_llm, tmp_path):
    """传 project_id 时，manuscript.txt 片段会附在用户消息里。"""
    client = isolated_app["client"]
    pid = isolated_app["make_project"]()
    (tmp_path / pid / "manuscript.txt").write_text(
        "讲一个隐世剑客重出江湖的故事，他每天在小镇开餐馆，背后藏着惊人的过去……",
        encoding="utf-8",
    )

    r = client.post("/api/text-engine/generate-music-prompt", json={
        "user_request": "片头曲",
        "project_id":   pid,
    })
    assert r.status_code == 200
    user_msg = stubbed_llm["user"]
    assert "隐世剑客" in user_msg or "Project manuscript context" in user_msg


def test_endpoint_handles_llm_with_code_fence(isolated_app, monkeypatch):
    """LLM 偶尔会用 ```json fence 包裹，端点必须能剥掉。"""
    async def fake(cfg, system, user):
        yield "```json\n"
        yield '{"tags": "rock", "lyrics": "verse"}\n```'

    import services.llm, routers.text_engine
    monkeypatch.setattr(services.llm, "stream_chat", fake)
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake)

    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-music-prompt", json={
        "user_request": "rock song",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["tags"] == "rock"
    assert data["lyrics"] == "verse"


def test_endpoint_recovers_from_garbage_around_json(isolated_app, monkeypatch):
    """LLM 在 JSON 前后多说几句话，端点应该提取 {…} 段。"""
    async def fake(cfg, system, user):
        yield 'Sure, here\'s your song:\n\n{"tags": "punk", "lyrics": ""}\n\nHope you like it!'

    import services.llm, routers.text_engine
    monkeypatch.setattr(services.llm, "stream_chat", fake)
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake)

    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-music-prompt", json={
        "user_request": "punk",
    })
    assert r.status_code == 200
    assert r.json()["tags"] == "punk"


def test_system_prompt_forbids_structured_params_in_tags():
    """User feedback: tags 里不能写 120 BPM / 4/4 拍 / C 大调 这些参数化字段，
    因为它们都有独立表单项，重复会被双倍套用导致音乐质量下降。"""
    from services.prompts import MUSIC_PROMPT_SYSTEM
    sys = MUSIC_PROMPT_SYSTEM
    # 必须明确出现禁止清单关键词
    assert "DO-NOT-INCLUDE" in sys or "CRITICAL" in sys
    # 必须涵盖 BPM / 拍号 / 调式 / 时长 四类
    assert "BPM" in sys
    assert "time signature" in sys or "拍号" in sys
    assert "key" in sys.lower()
    assert "duration" in sys.lower()
    # 必须给出反例（让 LLM 知道哪些字面量该避免）
    assert "120 BPM" in sys or "C 大调" in sys or "A minor" in sys
