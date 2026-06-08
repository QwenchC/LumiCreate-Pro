"""v1.4.2: 批量 SSE 文本端点 —— 绕开 Chromium 单 origin 6 连接上限。

关键校验：
  - 同一个连接里返回 N 个结果
  - 每个结果带正确 scene_id
  - 后端真按 settings 的 concurrency 并发跑（用 in-flight 计数器证明）
  - per-scene characters 子集生效（覆盖共享 characters）
"""
import asyncio
import json
import pytest


def _consume_sse(resp):
    """从 TestClient 的 SSE 响应里抽出所有 data 事件。"""
    events = []
    for line in resp.text.splitlines():
        if not line.startswith("data: "): continue
        raw = line[6:].strip()
        if raw == "[DONE]": break
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return events


# ── frame-prompts 批量 ───────────────────────────────────────────────────────


def test_frame_prompts_batch_returns_all_scenes(isolated_app, monkeypatch):
    """N 个 scene → 同一个 connection → N 个 result 事件 + 1 个 done。"""
    async def fake_stream(cfg, system, user):
        # 根据 user_msg 里的 description 字符串构造可识别的结果
        # 让前端断言 scene_id 对应关系
        yield '{"start_frame_prompt": "S_' + ("A" if "alice" in user else "B" if "bob" in user else "C") + '",'
        yield ' "end_frame_prompt": "E"}'

    import services.llm, routers.text_engine
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream)
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream)

    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-frame-prompts-batch", json={
        "frames": [
            {"scene_id": "s1", "description": "alice walks in", "dialogues": []},
            {"scene_id": "s2", "description": "bob answers",    "dialogues": []},
            {"scene_id": "s3", "description": "carol leaves",   "dialogues": []},
        ],
        "characters": [], "manuscript": "", "total_scenes": 3,
    })
    assert r.status_code == 200, r.text
    events = _consume_sse(r)
    results = [e for e in events if e.get("event") == "result"]
    done    = [e for e in events if e.get("event") == "done"]
    assert len(results) == 3
    assert {e["scene_id"] for e in results} == {"s1", "s2", "s3"}
    # 内容跟 description 一致：scene 1 含 alice → S_A
    by_id = {e["scene_id"]: e for e in results}
    assert by_id["s1"]["start_frame_prompt"] == "S_A"
    assert by_id["s2"]["start_frame_prompt"] == "S_B"
    assert done and done[0]["total"] == 3


def test_frame_prompts_batch_honors_settings_concurrency(isolated_app, monkeypatch):
    """concurrency=settings 控制：用 in-flight 计数器证明真并发跑。
    没设 concurrency=10，理论上同时跑的 task 数应该到 10（如果有 10+ 个 scene）。"""
    in_flight = 0
    peak = [0]   # 用 list 模拟可变状态
    lock = asyncio.Lock()

    async def fake_stream(cfg, system, user):
        nonlocal in_flight
        async with lock:
            in_flight += 1
            peak[0] = max(peak[0], in_flight)
        # 模拟真实 LLM 耗时
        await asyncio.sleep(0.02)
        async with lock:
            in_flight -= 1
        yield '{"start_frame_prompt": "x", "end_frame_prompt": "y"}'

    import services.llm, routers.text_engine
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream)
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream)

    # 配置后端 settings.text_engine.concurrency=10
    cfg = isolated_app["settings"]
    cfg.text_engine.concurrency = 10

    client = isolated_app["client"]
    # 30 个 scene + concurrency=10
    frames = [{"scene_id": f"s{i}", "description": f"d{i}", "dialogues": []}
              for i in range(30)]
    r = client.post("/api/text-engine/generate-frame-prompts-batch", json={
        "frames": frames, "characters": [], "manuscript": "", "total_scenes": 30,
    })
    assert r.status_code == 200, r.text
    events = _consume_sse(r)
    assert len([e for e in events if e.get("event") == "result"]) == 30
    # 关键断言：peak in-flight 应当 = 10（被 settings 的并发数 cap 住）
    # 这是核心证明：前端 fetch 不再是瓶颈，后端真按设定值并发跑
    assert peak[0] == 10, f"in-flight peak {peak[0]} != settings.concurrency=10"


def test_frame_prompts_batch_per_scene_characters_override(isolated_app, monkeypatch):
    """per-scene characters 优先于共享 characters。"""
    captured_user_msgs = []
    async def fake_stream(cfg, system, user):
        captured_user_msgs.append(user)
        yield '{"start_frame_prompt": "x", "end_frame_prompt": "y"}'
    import services.llm, routers.text_engine
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream)
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream)

    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-frame-prompts-batch", json={
        "frames": [
            # scene 1 用 per-scene 子集（只有 Alice）
            {"scene_id": "s1", "description": "d1", "dialogues": [],
             "characters": [{"name": "Alice", "appearance": "red dress"}]},
            # scene 2 用共享 characters（Alice + Bob 全集）
            {"scene_id": "s2", "description": "d2", "dialogues": []},
        ],
        "characters": [
            {"name": "Alice", "appearance": "red dress"},
            {"name": "Bob",   "appearance": "blue suit"},
        ],
    })
    assert r.status_code == 200, r.text
    assert len(captured_user_msgs) == 2
    # scene 1 的 user_msg 只能含 Alice，不能含 Bob
    s1_msg = next(m for m in captured_user_msgs if "d1" in m)
    s2_msg = next(m for m in captured_user_msgs if "d2" in m)
    assert "Alice" in s1_msg and "Bob" not in s1_msg, \
        f"per-scene subset failed: s1 should not have Bob, got {s1_msg!r}"
    # scene 2 落到共享 → 应该 Alice + Bob 都有
    assert "Alice" in s2_msg and "Bob" in s2_msg


def test_frame_prompts_batch_item_error_isolates(isolated_app, monkeypatch):
    """一条任务抛错不能影响其它任务，且 SSE 必须有 item_error 事件。"""
    async def fake_stream(cfg, system, user):
        if "boom" in user:
            raise RuntimeError("LLM exploded")
        yield '{"start_frame_prompt": "x", "end_frame_prompt": "y"}'
    import services.llm, routers.text_engine
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream)
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream)

    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-frame-prompts-batch", json={
        "frames": [
            {"scene_id": "ok1",  "description": "fine",  "dialogues": []},
            {"scene_id": "bad",  "description": "boom",  "dialogues": []},
            {"scene_id": "ok2",  "description": "fine2", "dialogues": []},
        ],
    })
    assert r.status_code == 200
    events = _consume_sse(r)
    ok_events  = [e for e in events if e.get("event") == "result"]
    err_events = [e for e in events if e.get("event") == "item_error"]
    assert {e["scene_id"] for e in ok_events}  == {"ok1", "ok2"}
    assert err_events and err_events[0]["scene_id"] == "bad"
    assert "exploded" in err_events[0]["message"]


# ── suggest-scene-characters 批量 ─────────────────────────────────────────────


def test_suggest_chars_batch_returns_per_scene(isolated_app, monkeypatch):
    async def fake_stream(cfg, system, user):
        # 用 description 里的独特 marker 匹配，避开 all_names 引入的字符串干扰
        if "MARKER_RUN" in user:
            yield '["Alice"]'
        elif "MARKER_JUMP" in user:
            yield '["Bob"]'
        else:
            yield '[]'
    import services.llm, routers.text_engine
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream)
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream)

    client = isolated_app["client"]
    r = client.post("/api/text-engine/suggest-scene-characters-batch", json={
        "scenes": [
            {"scene_id": "s1", "description": "MARKER_RUN scene", "dialogues": []},
            {"scene_id": "s2", "description": "MARKER_JUMP scene", "dialogues": []},
        ],
        "all_names": ["Alice", "Bob"],
        "manuscript": "...",
    })
    assert r.status_code == 200, r.text
    events = _consume_sse(r)
    results = [e for e in events if e.get("event") == "result"]
    by_id = {e["scene_id"]: e for e in results}
    assert by_id["s1"]["characters"] == ["Alice"]
    assert by_id["s2"]["characters"] == ["Bob"]


def test_suggest_chars_batch_no_names_returns_empty(isolated_app, monkeypatch):
    """all_names 为空 → 直接给所有 scene 返空，不调 LLM。"""
    call_count = [0]
    async def fake_stream(cfg, system, user):
        call_count[0] += 1
        yield '[]'
    import services.llm, routers.text_engine
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream)
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream)

    client = isolated_app["client"]
    r = client.post("/api/text-engine/suggest-scene-characters-batch", json={
        "scenes":    [{"scene_id": "s1", "description": "d", "dialogues": []}],
        "all_names": [],
    })
    assert r.status_code == 200
    events = _consume_sse(r)
    results = [e for e in events if e.get("event") == "result"]
    assert results and results[0]["characters"] == []
    assert call_count[0] == 0   # LLM 未被调用


# ── video-prompts 批量 ───────────────────────────────────────────────────────


def test_video_prompts_batch_returns_text_per_scene(isolated_app, monkeypatch):
    async def fake_stream(cfg, system, user):
        # 把 description 直接回写到 prompt
        if "fight" in user:
            yield "fight scene description"
        else:
            yield "calm scene description"
    import services.llm, routers.text_engine
    monkeypatch.setattr(services.llm, "stream_chat", fake_stream)
    monkeypatch.setattr(routers.text_engine, "stream_chat", fake_stream)

    client = isolated_app["client"]
    r = client.post("/api/text-engine/generate-video-prompts-batch", json={
        "scenes": [
            {"scene_id": "s1", "description": "fight",
             "dialogues": [], "start_frame_prompt": "a", "end_frame_prompt": "b", "scene_index": 1},
            {"scene_id": "s2", "description": "calm dialogue",
             "dialogues": [], "start_frame_prompt": "c", "end_frame_prompt": "d", "scene_index": 2},
        ],
        "characters": [], "manuscript": "", "total_scenes": 2,
    })
    assert r.status_code == 200, r.text
    events = _consume_sse(r)
    results = [e for e in events if e.get("event") == "result"]
    by_id = {e["scene_id"]: e for e in results}
    assert by_id["s1"]["text"] == "fight scene description"
    assert by_id["s2"]["text"] == "calm scene description"


def test_concurrency_resolver_clamps_to_100():
    """settings.text_engine.concurrency 上限 100 —— 防止意外打挂 LLM 服务。"""
    from routers.text_engine import _resolve_concurrency
    # 显式参数 > 0 时只走显式
    assert _resolve_concurrency(50) == 50
    assert _resolve_concurrency(500) == 100   # 上限 100
    assert _resolve_concurrency(0) >= 1        # 0 → settings 兜底
