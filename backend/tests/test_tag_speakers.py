"""v1.5.1: /tag-dialogue-speakers 端点测试。

只指派说话人、不改台词；服务端对 LLM 输出做名单校验（未知名归旁白 ""）。
"""
import json


def _mock_llm(monkeypatch, response_text: str):
    import routers.text_engine as te

    async def _fake_stream(cfg, system, user):
        yield response_text

    monkeypatch.setattr(te, "stream_chat", _fake_stream)


def test_assigns_speakers_in_order(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, json.dumps(["张三", "李四", "旁白"]))
    r = client.post("/api/text-engine/tag-dialogue-speakers", json={
        "lines": ["你来了。", "嗯，路上堵车。", "他擦了擦汗。"],
        "characters": ["张三", "李四"],
        "context": "张三在门口迎接李四。",
    })
    assert r.status_code == 200, r.text
    # "旁白" 不在名单 → 归 ""
    assert r.json()["speakers"] == ["张三", "李四", ""]


def test_unknown_name_coerced_to_empty(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, json.dumps(["王五", "张三"]))  # 王五 不在名单
    r = client.post("/api/text-engine/tag-dialogue-speakers", json={
        "lines": ["A", "B"], "characters": ["张三", "李四"],
    })
    assert r.json()["speakers"] == ["", "张三"]


def test_length_mismatch_padded(isolated_app, monkeypatch):
    """LLM 少返回 → 缺失项补 ""，长度始终等于 lines。"""
    client = isolated_app["client"]
    _mock_llm(monkeypatch, json.dumps(["张三"]))
    r = client.post("/api/text-engine/tag-dialogue-speakers", json={
        "lines": ["A", "B", "C"], "characters": ["张三"],
    })
    assert r.json()["speakers"] == ["张三", "", ""]


def test_no_roster_all_narration(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "should not be called")
    r = client.post("/api/text-engine/tag-dialogue-speakers", json={
        "lines": ["A", "B"], "characters": [],
    })
    assert r.json()["speakers"] == ["", ""]


def test_garbage_llm_falls_back_to_narration(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "抱歉我无法完成")
    r = client.post("/api/text-engine/tag-dialogue-speakers", json={
        "lines": ["A", "B"], "characters": ["张三"],
    })
    assert r.json()["speakers"] == ["", ""]


def test_empty_lines(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "[]")
    r = client.post("/api/text-engine/tag-dialogue-speakers", json={
        "lines": ["   ", ""], "characters": ["张三"],
    })
    assert r.json()["speakers"] == []


# ── v1.6: 纯白背景立绘提示词优化 ──────────────────────────────────────────────


def test_white_bg_portrait_uses_llm(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "tall girl, silver hair, isolated on pure white background, full body")
    r = client.post("/api/text-engine/optimize-white-bg-portrait", json={
        "appearance": "银发少女", "base_prompt": "anime",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "pure white background" in body["prompt"]
    assert body["negative"]              # 强力背景负面词


def test_white_bg_portrait_fallback_when_llm_empty(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "")           # LLM 空 → 确定性兜底
    r = client.post("/api/text-engine/optimize-white-bg-portrait", json={
        "appearance": "red hair boy",
    })
    body = r.json()
    assert "pure white background" in body["prompt"]
    assert "red hair boy" in body["prompt"]
