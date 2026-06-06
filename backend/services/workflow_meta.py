"""Workflow node-ID mapping (C1).

每个工作流文件 `<name>.json` 旁边可以放一个 `<name>.meta.json`，描述其
关键节点的 ID 与字段下标，让自定义工作流不再需要改代码。

Schema:
  {
    "version": 1,
    "type":    "video" | "image",
    "node_map": {
      "first_frame_image": { "node_id": 45,  "widget": 0 },
      "last_frame_image":  { "node_id": 47,  "widget": 0 },
      "audio":             { "node_id": 232, "widget": 0 },
      "width":             { "node_id": 166, "widget": 0 },
      "height":            { "node_id": 167, "widget": 0 },
      "duration_secs":     { "node_id": 169, "widget": 0 },
      "fps":               { "node_id": 164, "widget": 0 },
      "positive_prompt":   { "node_id": 16,  "widget": 0 }
    },
    "notes": "可选的中文备注"
  }

行为：
  - 缺 `meta.json` → 用 DEFAULT_VIDEO_NODE_MAP 兜底（保持现有 flfa2i-lumicreate 行为）
  - meta.json 缺某个字段 → 该字段也用默认值
  - meta.json 节点 ID 改了 → 直接生效，不用改后端代码
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


# 视频工作流默认节点映射（与 ltx2video.py 原写死值保持一致）
DEFAULT_VIDEO_NODE_MAP: dict[str, dict] = {
    "first_frame_image": {"node_id": 45,  "widget": 0},
    "last_frame_image":  {"node_id": 47,  "widget": 0},
    "audio":             {"node_id": 232, "widget": 0},
    "width":             {"node_id": 166, "widget": 0},
    "height":            {"node_id": 167, "widget": 0},
    "duration_secs":     {"node_id": 169, "widget": 0},
    "fps":               {"node_id": 164, "widget": 0},
    "positive_prompt":   {"node_id": 16,  "widget": 0},
}

# 图片工作流默认（image_engine 已经会自动找 CLIPTextEncode + KSampler，
# 这里的 meta 仅在用户想强制指定节点 ID 时生效，否则空 = 自动）
DEFAULT_IMAGE_NODE_MAP: dict[str, dict] = {}


def _meta_path(workflow_path: str | Path) -> Path:
    p = Path(workflow_path)
    return p.with_name(p.stem + ".meta.json")


def load_meta(workflow_path: str | Path, type_: str = "video") -> dict:
    """读取 meta.json；不存在或损坏时返回默认骨架。"""
    mp = _meta_path(workflow_path)
    default_node_map = DEFAULT_VIDEO_NODE_MAP if type_ == "video" else DEFAULT_IMAGE_NODE_MAP
    if not mp.exists():
        return {"version": 1, "type": type_, "node_map": dict(default_node_map), "notes": ""}
    try:
        data = json.loads(mp.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"version": 1, "type": type_, "node_map": dict(default_node_map), "notes": ""}

    # 合并默认值（缺失字段补回，避免 None.get）
    node_map = dict(default_node_map)
    user_map = data.get("node_map") or {}
    for k, v in user_map.items():
        if not isinstance(v, dict):
            continue
        node_map[k] = {
            "node_id": v.get("node_id"),
            "widget":  int(v.get("widget", 0)) if v.get("widget") is not None else 0,
        }
    return {
        "version": data.get("version", 1),
        "type":    data.get("type", type_),
        "node_map": node_map,
        "notes":   data.get("notes", ""),
    }


def save_meta(workflow_path: str | Path, meta: dict) -> None:
    mp = _meta_path(workflow_path)
    payload = {
        "version":  int(meta.get("version", 1)),
        "type":     meta.get("type", "video"),
        "node_map": {
            k: {
                "node_id": (v or {}).get("node_id"),
                "widget":  int((v or {}).get("widget", 0)),
            }
            for k, v in (meta.get("node_map") or {}).items()
            if isinstance(v, dict) and (v or {}).get("node_id") is not None
        },
        "notes":    meta.get("notes", ""),
    }
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_node_id(meta: dict, key: str) -> Optional[int]:
    """取某个键对应的 ComfyUI 节点 ID（LiteGraph 整数 id）。"""
    nm = (meta or {}).get("node_map") or {}
    v = nm.get(key)
    if not isinstance(v, dict):
        return None
    nid = v.get("node_id")
    return int(nid) if isinstance(nid, int) else None


def get_widget(meta: dict, key: str) -> int:
    nm = (meta or {}).get("node_map") or {}
    v = nm.get(key)
    if not isinstance(v, dict):
        return 0
    return int(v.get("widget", 0))
