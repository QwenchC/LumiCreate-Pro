"""v1.6.2: 智能分镜（导演式、分段多次续接）端点测试。

验证：文案分段、逐段续接（带前情衔接）、分镜全局连续编号、角色检测、SSE 事件。
"""
import json


def _drain(text: str):
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


def test_split_segments():
    from routers.text_engine import _split_manuscript_segments
    assert _split_manuscript_segments("") == []
    assert _split_manuscript_segments("短句。") == ["短句。"]
    long = "一段话。" * 200          # 800 字单段 → 按句末二次切
    segs = _split_manuscript_segments(long, target=300)
    assert len(segs) >= 2
    assert "".join(segs).replace("\n", "") == long   # 不丢内容


def test_smart_scenes_streams_continues_and_renumbers(isolated_app, monkeypatch):
    import routers.text_engine as te
    calls = []

    async def _fake(cfg, system, user):
        calls.append(user)
        n = len(calls)
        yield json.dumps([
            {"description": f"镜A·段{n}：张三推门而入", "duration_estimate": 5, "dialogues": []},
            {"description": f"镜B·段{n}", "duration_estimate": 4,
             "dialogues": [{"character": "张三", "text": "你好", "emotion": "平静"}]},
        ], ensure_ascii=False)

    monkeypatch.setattr(te, "stream_chat", _fake)
    client = isolated_app["client"]
    # 两段各 ~500 字（合计 >700 默认目标）→ 真的分成 2 段、2 次 LLM 调用
    ms = ("第一段剧情文字。" * 60) + "\n\n" + ("第二段剧情文字。" * 60)
    r = client.post("/api/text-engine/generate-scenes-smart", json={
        "manuscript": ms, "dialogue_mode": "mixed", "characters": [{"name": "张三"}],
    })
    assert r.status_code == 200, r.text
    evs = _drain(r.text)
    all_scenes = [s for e in evs if e.get("event") == "scenes" for s in e["scenes"]]
    # 2 段 × 2 镜 = 4，全局连续编号
    assert [s["index"] for s in all_scenes] == [1, 2, 3, 4]
    assert [s["id"] for s in all_scenes] == \
        ["scene_001", "scene_002", "scene_003", "scene_004"]
    # 第二段调用带【前情衔接】上下文
    assert any("前情衔接" in u for u in calls)
    # 角色检测命中
    assert "张三" in all_scenes[0]["_scene_characters"]
    # done 事件总数正确
    assert any(e.get("event") == "done" and e.get("total") == 4 for e in evs)


def test_smart_scenes_segment_error_continues(isolated_app, monkeypatch):
    """某段 LLM 抛错 → 该段报 segment_error 但整体不中断、其余段照常。"""
    import routers.text_engine as te
    calls = []

    async def _fake(cfg, system, user):
        calls.append(user)
        if len(calls) == 1:
            raise RuntimeError("LLM 超时")
            yield  # pragma: no cover
        yield json.dumps([{"description": "镜", "duration_estimate": 5, "dialogues": []}],
                         ensure_ascii=False)

    monkeypatch.setattr(te, "stream_chat", _fake)
    client = isolated_app["client"]
    ms = ("段一剧情文字。" * 60) + "\n\n" + ("段二剧情文字。" * 60)   # → 2 段
    r = client.post("/api/text-engine/generate-scenes-smart", json={
        "manuscript": ms, "dialogue_mode": "mixed",
    })
    assert r.status_code == 200, r.text
    evs = _drain(r.text)
    assert any(e.get("event") == "segment_error" for e in evs)
    assert any(e.get("event") == "done" and e.get("total") == 1 for e in evs)
