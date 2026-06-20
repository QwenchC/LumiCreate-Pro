"""v1.6: 无角色背景图提示词 + MSR 多图参考视频提示词 端点测试（D-1/D-2）。

- /generate-bg-prompt(-batch)：纯环境提示词（无角色）。
- /generate-msr-video-prompt(-batch)：参考图N + 动作叙述格式。
另含 _msr_ref_block / _msr_dialogues_block 确定性单测。
"""
import json


def _mock_llm(monkeypatch, response_text: str):
    import routers.text_engine as te

    async def _fake_stream(cfg, system, user):
        yield response_text

    monkeypatch.setattr(te, "stream_chat", _fake_stream)


def _drain_sse(text: str):
    out = []
    for ln in text.splitlines():
        if ln.startswith("data: "):
            raw = ln[len("data: "):].strip()
            if raw and raw != "[DONE]":
                try:
                    out.append(json.loads(raw))
                except Exception:
                    pass
    return out


# ── 无角色背景图提示词 ────────────────────────────────────────────────────────

def test_bg_prompt_single(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "misty jiangnan town, wet stone path, white walls black tiles, no people")
    r = client.post("/api/text-engine/generate-bg-prompt", json={
        "description": "WV 在石板路上走来，RN 站着微笑", "scene_index": 3, "total_scenes": 10,
    })
    assert r.status_code == 200, r.text
    assert "no people" in r.json()["prompt"]


def test_bg_prompt_strips_codefence(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "```\nempty rainy alley, lanterns, no person\n```")
    r = client.post("/api/text-engine/generate-bg-prompt", json={"description": "x"})
    assert r.json()["prompt"] == "empty rainy alley, lanterns, no person"


def test_bg_prompts_batch(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "empty environment plate, no people")
    r = client.post("/api/text-engine/generate-bg-prompts-batch", json={
        "scenes": [{"scene_id": "s1", "description": "a"}, {"scene_id": "s2", "description": "b"}],
        "total_scenes": 2,
    })
    assert r.status_code == 200, r.text
    evs = _drain_sse(r.text)
    results = {e["scene_id"]: e.get("bg_prompt") for e in evs if e.get("event") == "result"}
    assert results.get("s1") == "empty environment plate, no people"
    assert results.get("s2") == "empty environment plate, no people"
    assert any(e.get("event") == "done" for e in evs)


# ── MSR 多图参考视频提示词 ────────────────────────────────────────────────────

def test_msr_ref_block_order_and_scene_tail():
    from routers.text_engine import _msr_ref_block
    block = _msr_ref_block([
        {"name": "RN", "appearance": "深棕色长发"},
        {"name": "WV", "appearance": "乌黑长发"},
    ])
    lines = block.splitlines()
    assert lines[0].startswith("参考图1：标签=RN")
    assert "深棕色长发" in lines[0]
    assert lines[1].startswith("参考图2：标签=WV")
    # 末行是场景参考图
    assert lines[2].startswith("参考图3（场景）")


def test_msr_ref_block_empty_chars_still_has_scene():
    from routers.text_engine import _msr_ref_block
    block = _msr_ref_block([])
    assert block.startswith("参考图1（场景）")


def test_msr_ref_block_skips_nondict_without_misnumbering():
    """混入非 dict 条目时编号仍连续：参考图1 给唯一合法角色，场景行为参考图2。"""
    from routers.text_engine import _msr_ref_block
    block = _msr_ref_block(["junk", {"name": "X", "appearance": "x"}, None])
    lines = block.splitlines()
    assert lines[0].startswith("参考图1：标签=X")
    assert lines[1].startswith("参考图2（场景）")
    assert len(lines) == 2          # 只有 1 个合法角色 + 1 个场景行


def test_msr_dialogues_block_narration_fallback():
    from routers.text_engine import _msr_dialogues_block
    b = _msr_dialogues_block([
        {"character": "RN", "text": "这么巧"},
        {"character": "", "text": "她转身离去"},
        {"text": "  "},   # 空 → 跳过
    ])
    assert "[RN]：这么巧" in b
    assert "[旁白]：她转身离去" in b


def test_msr_video_prompt_single(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "参考图1：RN，男人，深棕色长发\n参考图2（场景）：江南小镇\n\nRN 微微一笑。")
    r = client.post("/api/text-engine/generate-msr-video-prompt", json={
        "characters": [{"name": "RN", "appearance": "深棕色长发"}],
        "background": "江南小镇", "description": "RN 站着", "dialogues": [],
        "scene_index": 1, "total_scenes": 5,
    })
    assert r.status_code == 200, r.text
    assert "参考图1" in r.json()["prompt"]


def test_msr_video_prompts_batch(isolated_app, monkeypatch):
    client = isolated_app["client"]
    _mock_llm(monkeypatch, "参考图1：RN，男人\n参考图2（场景）：街道\n\n动作叙述。")
    r = client.post("/api/text-engine/generate-msr-video-prompts-batch", json={
        "scenes": [
            {"scene_id": "s1", "characters": [{"name": "RN", "appearance": "x"}],
             "background": "街道", "description": "d", "dialogues": []},
        ],
        "total_scenes": 1,
    })
    assert r.status_code == 200, r.text
    evs = _drain_sse(r.text)
    res = [e for e in evs if e.get("event") == "result"]
    assert res and res[0]["scene_id"] == "s1" and "参考图1" in res[0]["prompt"]


# ── v1.6.2: MSR 提示词按对白模式差异化 ────────────────────────────────────────

def test_msr_prompt_injects_per_mode_guidance(isolated_app, monkeypatch):
    """每种对白模式 → MSR 用户提示词注入对应的「动作叙述」指导块。"""
    import routers.text_engine as te
    captured = {}

    async def _fake_stream(cfg, system, user):
        captured["user"] = user
        yield "参考图1：RN，男人，x\n参考图2（场景）：街道\n\n动作叙述。"

    monkeypatch.setattr(te, "stream_chat", _fake_stream)
    client = isolated_app["client"]
    cases = [("narration", "纯旁白"), ("dialogue", "纯对话"),
             ("reading", "纯朗读"), ("mixed", "混合")]
    for mode, marker in cases:
        r = client.post("/api/text-engine/generate-msr-video-prompt", json={
            "characters": [{"name": "RN", "appearance": "x"}], "background": "街道",
            "description": "d", "dialogues": [], "dialogue_mode": mode,
        })
        assert r.status_code == 200, r.text
        assert marker in captured["user"], (mode, captured["user"][-300:])
    # 未知/缺省 → 回退混合
    r = client.post("/api/text-engine/generate-msr-video-prompt", json={
        "characters": [{"name": "RN", "appearance": "x"}], "description": "d"})
    assert r.status_code == 200
    assert "混合" in captured["user"]


def test_msr_batch_threads_dialogue_mode(isolated_app, monkeypatch):
    import routers.text_engine as te
    seen = []

    async def _fake_stream(cfg, system, user):
        seen.append(user)
        yield "参考图1（场景）：街\n\n动作。"

    monkeypatch.setattr(te, "stream_chat", _fake_stream)
    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-msr-video-prompts-batch", json={
        "scenes": [{"scene_id": "s1", "characters": [], "background": "街",
                    "description": "d", "dialogues": []}],
        "dialogue_mode": "reading", "total_scenes": 1,
    })
    assert r.status_code == 200, r.text
    assert any("纯朗读" in u for u in seen)
