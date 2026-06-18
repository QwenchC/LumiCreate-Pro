"""v1.6: /video-engine/generate-stream 的 MSR 多图参考【按分镜调度】回归。

锁定【附加式】契约：
  - 分镜带 msr_options.enabled → 走 generate_msr_video（而非 generate_video），
    参考图 / 尺寸 / 时长按软件设置透传；完成事件复用现有落盘通路。
  - 普通分镜（无 msr_options）→ 仍走原 generate_video，零影响。
  - MSR 分镜缺参考图 → scene_error（不需要首/末帧）。
"""
import base64

import pytest


def _drain_sse(text: str) -> list[str]:
    return [ln[len("data: "):] for ln in text.splitlines() if ln.startswith("data: ")]


def test_generate_stream_dispatches_msr_scene(isolated_app, monkeypatch):
    import services.msr_video as msr_mod
    import services.ltx2video as ltx

    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid

    captured: dict = {}

    async def _fake_msr(comfyui_url, workflow, *, char_b64_list, bg_b64, width,
                        height, fps, duration_ms, positive_prompt, scene_id):
        captured.update(dict(char_b64_list=char_b64_list, bg_b64=bg_b64,
                             width=width, height=height, fps=fps,
                             duration_ms=duration_ms, prompt=positive_prompt,
                             has_workflow=workflow is not None))
        yield {"event": "queued", "prompt_id": "p1", "scene_id": scene_id}
        yield {"event": "completed", "scene_id": scene_id,
               "video": base64.b64encode(b"\x00\x00\x00\x18ftypmp42msr").decode(),
               "filename": "msr_out.mp4", "mime": "video/mp4"}

    monkeypatch.setattr(msr_mod, "generate_msr_video", _fake_msr)

    # 普通 generate_video 绝不该为 MSR 分镜被调用
    async def _boom(*a, **k):
        raise AssertionError("normal generate_video called for an MSR scene")
        yield  # pragma: no cover

    monkeypatch.setattr(ltx, "generate_video", _boom)

    r = client.post("/api/video-engine/generate-stream", json={
        "workflow_name": "flfa2i-lumicreate",   # 主工作流仍要可加载（前端总有选中）
        "resolution": "720x1280",
        "fps": 24,
        "project_id": pid,
        "scenes": [{
            "scene_id": "scene_001",
            "scene_index": 0,
            "duration_ms": 5000,
            "positive_prompt": "two people talking in a cafe",
            "msr_options": {"enabled": True,
                            "char_ref_b64": ["AAAA", "CCCC"],
                            "bg_ref_b64": "BBBB"},
        }],
    })
    assert r.status_code == 200, r.text
    events = _drain_sse(r.text)

    # dispatch 命中 MSR + 透传正确
    assert captured.get("char_b64_list") == ["AAAA", "CCCC"]
    assert captured.get("bg_b64") == "BBBB"
    # 尺寸经 _parse_resolution 对齐到 32 的倍数（720→704），与普通通路一致
    assert captured.get("width") == 704 and captured.get("height") == 1280
    assert captured.get("duration_ms") == 5000
    assert captured.get("has_workflow") is True

    # scene_start 标注 video_msr；完成走 scene_done
    joined = "\n".join(events)
    assert "video_msr" in joined
    assert "scene_done" in joined

    # v1.6 双模：MSR 视频写到独立的 <scene>.msr.mp4（与旧/普通 <scene>.mp4 并存）
    assert (pdir / "video" / "scene_001.msr.mp4").exists()
    assert not (pdir / "video" / "scene_001.mp4").exists()
    # MSR 索引 videos_msr.json 落盘
    import json as _json
    msr_idx = _json.loads((pdir / "videos_msr.json").read_text(encoding="utf-8-sig"))
    assert msr_idx.get("scene_001") == "scene_001.msr.mp4"


def test_msr_scene_without_refs_errors(isolated_app, monkeypatch):
    import services.msr_video as msr_mod
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    async def _should_not_run(*a, **k):
        raise AssertionError("generate_msr_video called despite no refs")
        yield  # pragma: no cover

    monkeypatch.setattr(msr_mod, "generate_msr_video", _should_not_run)

    r = client.post("/api/video-engine/generate-stream", json={
        "workflow_name": "flfa2i-lumicreate",
        "resolution": "720x1280", "fps": 24, "project_id": pid,
        "scenes": [{
            "scene_id": "scene_001", "scene_index": 0, "duration_ms": 4000,
            "msr_options": {"enabled": True, "char_ref_b64": [], "bg_ref_b64": ""},
        }],
    })
    assert r.status_code == 200, r.text
    joined = "\n".join(_drain_sse(r.text))
    assert "scene_error" in joined
    assert "参考图" in joined


def test_driver_silent_exit_emits_scene_error(isolated_app, monkeypatch):
    """兜底：驱动无声退出（只发 queued/progress、无 completed/error）时，
    端点必须补一条 scene_error，分镜不能静默消失。覆盖 MSR + i2v + flfa2i 共用通路。"""
    import services.msr_video as msr_mod
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]

    async def _silent(*a, **k):
        # 模拟 WebSocket 干净关闭却没给终止事件
        yield {"event": "queued", "prompt_id": "p1", "scene_id": k.get("scene_id", "scene_001")}
        yield {"event": "progress", "value": 5, "max": 10, "scene_id": k.get("scene_id", "scene_001")}
        # 无 completed / 无 error → 生成器自然结束

    monkeypatch.setattr(msr_mod, "generate_msr_video", _silent)

    r = client.post("/api/video-engine/generate-stream", json={
        "workflow_name": "flfa2i-lumicreate",
        "resolution": "720x1280", "fps": 24, "project_id": pid,
        "scenes": [{
            "scene_id": "scene_001", "scene_index": 0, "duration_ms": 4000,
            "msr_options": {"enabled": True, "char_ref_b64": ["AAAA"], "bg_ref_b64": "BBBB"},
        }],
    })
    assert r.status_code == 200, r.text
    joined = "\n".join(_drain_sse(r.text))
    assert "scene_error" in joined, "无声退出未补 scene_error"
    assert "scene_001" in joined


def test_normal_scene_still_uses_generate_video(isolated_app, monkeypatch):
    """回归：不带 msr_options 的分镜仍走原 generate_video（MSR 改动是纯附加）。"""
    import services.ltx2video as ltx
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    pdir = isolated_app["tmp_path"] / pid

    used = {"normal": False}

    async def _fake_normal(*a, **k):
        used["normal"] = True
        yield {"event": "completed", "scene_id": k.get("scene_id", "scene_001"),
               "video": base64.b64encode(b"\x00\x00\x00\x18ftypmp42").decode(),
               "filename": "n.mp4", "mime": "video/mp4"}

    monkeypatch.setattr(ltx, "generate_video", _fake_normal)

    r = client.post("/api/video-engine/generate-stream", json={
        "workflow_name": "flfa2i-lumicreate",
        "resolution": "720x1280", "fps": 24, "project_id": pid,
        "scenes": [{
            "scene_id": "scene_001", "scene_index": 0, "duration_ms": 4000,
            "start_image_b64": "ZmFrZQ==", "end_image_b64": "ZmFrZQ==",
            "positive_prompt": "a scene",
        }],
    })
    assert r.status_code == 200, r.text
    assert used["normal"], "普通分镜未走 generate_video"
    assert (pdir / "video" / "scene_001.mp4").exists()
