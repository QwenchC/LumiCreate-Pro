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


# ── 工作流分类（轮 1）─────────────────────────────────────────────────────────
#
# LumiCreate 支持 4 种工作流：
#   t2i           文生图（Z-Image-Turbo / Flux.2-Klein-9b t2i / 其它）
#   i2i_single    图生图，1 张参考图
#   i2i_double    图生图，2 张参考图（Flux.2-Klein-9b image edit double）
#   video         首帧+末帧+音频 → 视频（LTX）
#
# 分类规则按优先级：
#   1. meta.json 显式声明 kind 字段 → 直接用
#   2. 名字模式：image_edit/i2i/img2img → i2i；text_to_image/t2i → t2i；
#      video/v2v/animate/flfa2i → video
#   3. 节点扫描兜底：含 LoadImage 节点数判断 i2i 张数；
#      含 SaveAnimatedWEBP / VHS_VideoCombine 等视频节点 → video


def classify_workflow(workflow_name: str, *, workflow: Optional[dict] = None,
                       workflow_path: Optional[str | Path] = None) -> str:
    """返回 't2i' | 'i2i_single' | 'i2i_double' | 'video'。"""
    # 1) meta 显式声明
    if workflow_path is not None:
        try:
            mp = _meta_path(workflow_path)
            if mp.exists():
                data = json.loads(mp.read_text(encoding="utf-8-sig"))
                explicit = (data.get("kind") or "").lower()
                if explicit in ("t2i", "i2i_single", "i2i_double", "video"):
                    return explicit
        except Exception:
            pass

    # 2) 名字模式
    name_l = (workflow_name or "").lower()
    if any(k in name_l for k in ("image_edit", "i2i", "img2img", "edit_")):
        # 名字里含 "double" 或 "two_ref" → 双图
        if any(k in name_l for k in ("double", "two", "2ref", "_two_")):
            return "i2i_double"
        return "i2i_single"
    if any(k in name_l for k in ("flfa2i", "video", "v2v", "animate", "ltx")):
        return "video"
    if any(k in name_l for k in ("t2i", "text_to_image", "text2image")):
        return "t2i"

    # 3) 节点扫描
    if workflow is not None:
        nodes = workflow.get("nodes") or []
        n_loadimage = sum(1 for n in nodes if n.get("type") == "LoadImage")
        has_video_save = any(
            n.get("type") in {"SaveAnimatedWEBP", "VHS_VideoCombine",
                              "VHS_LoadVideo", "VHS_LoadVideoPath"}
            for n in nodes
        )
        if has_video_save:
            return "video"
        if n_loadimage >= 2:
            return "i2i_double"
        if n_loadimage == 1:
            return "i2i_single"

    # 4) 默认 t2i
    return "t2i"


# i2i 工作流 meta 扩展：要让后端能注入参考图，需要知道哪个 LoadImage
# 是哪号参考图。可在 meta.json 加：
#   {
#     "kind": "i2i_double",
#     "ref_images": [
#       { "node_id": 81, "input_widget": 0 },   // ref #1 LoadImage
#       { "node_id": 76, "input_widget": 0 }    // ref #2 LoadImage
#     ]
#   }
# 缺时按工作流节点扫描：找所有 LoadImage 节点按 id 升序作为 ref 1..N。


def get_ref_image_nodes(meta: dict, workflow: Optional[dict] = None) -> list[dict]:
    """返回 [{node_id, input_widget}, ...]。"""
    refs = (meta or {}).get("ref_images") or []
    out = []
    for r in refs:
        if isinstance(r, dict) and r.get("node_id") is not None:
            out.append({
                "node_id": int(r["node_id"]),
                "input_widget": int(r.get("input_widget", 0)),
            })
    if out:
        return out
    # 兜底：扫工作流 LoadImage（含 subgraph 展平前）
    if workflow is not None:
        scan = sorted(
            [n for n in (workflow.get("nodes") or []) if n.get("type") == "LoadImage"],
            key=lambda n: int(n.get("id", 0)),
        )
        for n in scan:
            out.append({"node_id": int(n.get("id", 0)), "input_widget": 0})
    return out
