"""services.workflow_meta — 默认 + 自定义 + 缺字段兜底。"""
import json
import pytest

from services.workflow_meta import (
    DEFAULT_VIDEO_NODE_MAP,
    get_node_id, get_widget,
    load_meta, save_meta,
)


def test_load_meta_missing_returns_defaults(tmp_path):
    wf = tmp_path / "imaginary.json"
    meta = load_meta(wf, type_="video")
    assert meta["type"] == "video"
    # 所有默认字段都该有
    for k in DEFAULT_VIDEO_NODE_MAP:
        assert get_node_id(meta, k) == DEFAULT_VIDEO_NODE_MAP[k]["node_id"]
        assert get_widget(meta, k)  == DEFAULT_VIDEO_NODE_MAP[k]["widget"]


def test_user_overrides_default(tmp_path):
    wf = tmp_path / "custom.json"
    wf.write_text("{}", encoding="utf-8")
    meta_path = tmp_path / "custom.meta.json"
    meta_path.write_text(json.dumps({
        "version": 1,
        "type":    "video",
        "node_map": {
            "first_frame_image": {"node_id": 999, "widget": 0},
            "audio":             {"node_id": 1000, "widget": 1}
        }
    }), encoding="utf-8")

    meta = load_meta(wf, type_="video")
    assert get_node_id(meta, "first_frame_image") == 999
    assert get_node_id(meta, "audio") == 1000
    # 未提供的字段仍走默认
    assert get_node_id(meta, "width") == DEFAULT_VIDEO_NODE_MAP["width"]["node_id"]


def test_save_then_reload_roundtrip(tmp_path):
    wf = tmp_path / "rt.json"
    wf.write_text("{}", encoding="utf-8")
    new_meta = {
        "version": 1,
        "type":    "video",
        "node_map": {
            "first_frame_image": {"node_id": 77, "widget": 0},
            "positive_prompt":   {"node_id": 88, "widget": 2},
        },
        "notes": "test note",
    }
    save_meta(wf, new_meta)
    reloaded = load_meta(wf)
    assert get_node_id(reloaded, "first_frame_image") == 77
    assert get_node_id(reloaded, "positive_prompt") == 88
    assert get_widget(reloaded, "positive_prompt") == 2
    assert reloaded["notes"] == "test note"


def test_corrupt_meta_falls_back_silently(tmp_path):
    wf = tmp_path / "broken.json"
    (tmp_path / "broken.meta.json").write_text("not json {{{", encoding="utf-8")
    meta = load_meta(wf, type_="video")
    # 应当回退到默认，不抛
    assert get_node_id(meta, "first_frame_image") == \
        DEFAULT_VIDEO_NODE_MAP["first_frame_image"]["node_id"]
