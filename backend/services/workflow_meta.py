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


# 视频工作流默认节点映射。flfa2i = LTX-2.3 双帧+音频；
# i2v = LTX-2.3 单帧+时长（无音频输入），按 video_ltx2_3_i2v.json 标定。
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

# i2v 工作流 (video_ltx2_3_i2v.json) 的节点映射。subgraph 内部 id；
# patch 时按原始 id 写入 subgraph definition 内部节点的 widgets_values，
# 然后展平照样能传递到顶层。
DEFAULT_VIDEO_I2V_NODE_MAP: dict[str, dict] = {
    "first_frame_image": {"node_id": 269, "widget": 0},   # top-level LoadImage
    "width":             {"node_id": 312, "widget": 0},   # PrimitiveInt 1280
    "height":            {"node_id": 299, "widget": 0},   # PrimitiveInt 720
    "fps":               {"node_id": 300, "widget": 0},   # PrimitiveInt 25
    "duration_secs":     {"node_id": 301, "widget": 0},   # PrimitiveInt 5
    "positive_prompt":   {"node_id": 319, "widget": 0},   # PrimitiveStringMultiline
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
    """返回 't2i' | 'i2i_single' | 'i2i_double' | 'video' | 'unknown'。

    严格模式：必须有明确证据才识别为支持的种类。否则返回 'unknown'，下游过滤
    时会把它隐藏掉，避免奇怪的 ComfyUI 工作流跑出来 400。
    """
    # 1) meta 显式声明（最强证据）
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

    name_l = (workflow_name or "").lower()

    # 2) 名字含"明显是视频"的关键词 → 先把视频踢出来（避免被后面 image 规则误判）
    _VIDEO_HINTS = (
        "flfa2i", "v2v", "i2v", "image_to_video", "img_to_video",
        "ltx", "wan_", "wan2", "wanvideo", "wanmove",
        "infinitetalk", "animatediff", "hunyuanvideo", "digital_human",
        "数字人", "首尾帧", "视频",
    )
    if any(k in name_l for k in _VIDEO_HINTS):
        return "video"

    # 3) 名字含"明显是图生图"的关键词
    if any(k in name_l for k in ("image_edit", "i2i", "img2img")):
        if any(k in name_l for k in ("double", "two_ref", "_two_", "2ref")):
            return "i2i_double"
        return "i2i_single"

    # 4) 名字含"明显是文生图"的关键词
    if any(k in name_l for k in ("t2i", "text_to_image", "text2image")):
        return "t2i"

    # 5) 节点扫描兜底——只在节点签名完整对得上时才识别（避免乱认）
    if workflow is not None:
        nodes = workflow.get("nodes") or []
        node_types = {n.get("type") for n in nodes}

        # 视频特征节点
        _VIDEO_TYPES = {
            "SaveAnimatedWEBP", "VHS_VideoCombine",
            "VHS_LoadVideo", "VHS_LoadVideoPath",
            "CreateVideo", "SaveVideo",
            "LTXVConditioning", "LTXVImgToVideoInplace",
            "LTXVCropGuides", "WanImageToVideo",
            "WanVaceToVideo",
        }
        if node_types & _VIDEO_TYPES:
            return "video"

        # 3D / 音频 / 其它非图生模型 → unknown
        _NON_IMAGE_TYPES = {
            "Hy3DCreateMesh", "Hy3DDecodeLatent",      # Hunyuan3D
            "AudioInputAccPosCondNode", "VAEEncodeAudio",  # audio
        }
        if node_types & _NON_IMAGE_TYPES:
            return "unknown"

        # 图生图：有 LoadImage + 标准 sampling 签名
        n_loadimage = sum(1 for n in nodes if n.get("type") == "LoadImage")
        has_sampler = bool(node_types & {
            "KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced",
        })
        has_clip_text = bool(node_types & {"CLIPTextEncode", "CLIPTextEncodeFlux"})
        has_latent_init = bool(node_types & {
            "EmptyLatentImage", "EmptySD3LatentImage",
            "EmptyHunyuanLatentVideo", "EmptyFlux2LatentImage",
        })

        # 严格：必须有 sampler + clip text encode + latent init/参考图
        full_image_gen = has_sampler and has_clip_text
        if full_image_gen:
            if n_loadimage >= 2:
                return "i2i_double"
            if n_loadimage == 1:
                return "i2i_single"
            if has_latent_init:
                return "t2i"

    # 6) 既无名字证据也无完整节点签名 → unknown
    return "unknown"


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


# ── 视频工作流分类（v1.4.1）────────────────────────────────────────────────────
#
# LumiCreate 视频引擎当前支持两类工作流（都基于 LTX-2.3）：
#   video_flfa2i  双图 (start+end) + 音频 → 视频 (flfa2i-lumicreate.json)
#   video_i2v     单图 + 时长 → 视频 (video_ltx2_3_i2v.json)
#
# 分类规则按优先级：
#   1. meta.json 显式声明 kind 字段
#   2. 名字模式 (flfa2i / i2v)
#   3. 顶层节点扫描（LoadAudio 节点的存在）


def classify_video_workflow(workflow_name: str, *, workflow: Optional[dict] = None,
                             workflow_path: Optional[str | Path] = None) -> str:
    """返回 'video_flfa2i' | 'video_i2v' | 'unknown'。"""
    # 1) meta 显式声明
    if workflow_path is not None:
        try:
            mp = _meta_path(workflow_path)
            if mp.exists():
                data = json.loads(mp.read_text(encoding="utf-8-sig"))
                explicit = (data.get("kind") or "").lower()
                if explicit in ("video_flfa2i", "video_i2v"):
                    return explicit
        except Exception:
            pass

    # 2) 名字模式
    name_l = (workflow_name or "").lower()
    if "flfa2i" in name_l:
        return "video_flfa2i"
    if "i2v" in name_l or "img_to_video" in name_l or "image_to_video" in name_l:
        return "video_i2v"

    # 3) 节点扫描：找 LoadAudio → flfa2i；找 LoadImage 数量 = 1 → i2v
    if workflow is not None:
        nodes = workflow.get("nodes") or []
        has_audio = any(n.get("type") == "LoadAudio" for n in nodes)
        loadimage_count = sum(1 for n in nodes if n.get("type") == "LoadImage")
        if has_audio and loadimage_count >= 2:
            return "video_flfa2i"
        if loadimage_count == 1:
            return "video_i2v"

    return "unknown"


def get_video_workflow_features(kind: str) -> dict:
    """返回 kind 对应的特性集合，供前端 UI 决定显示什么控件。"""
    if kind == "video_flfa2i":
        return {
            "kind": "video_flfa2i",
            "requires_start_image": True,
            "requires_end_image":   True,
            "supports_audio":       True,    # 可输入也可不输入
            "supports_duration":    True,    # 可调（无音频时必须）
            "label":                "首末帧 + 音频 (LTX-2.3 flfa2i)",
        }
    if kind == "video_i2v":
        return {
            "kind": "video_i2v",
            "requires_start_image": True,
            "requires_end_image":   False,
            "supports_audio":       False,
            "supports_duration":    True,
            "label":                "单帧 + 时长 (LTX-2.3 i2v)",
        }
    return {
        "kind": "unknown",
        "requires_start_image": False,
        "requires_end_image":   False,
        "supports_audio":       False,
        "supports_duration":    False,
        "label":                "未知工作流",
    }


# ── 支持的工作流过滤（v1.4.1）─────────────────────────────────────────────────
#
# 终极兜底：硬名单。**只有这五个工作流**才可能出现在 UI 下拉里。
#
# 这个名单只影响 /api/{image,video}-engine/workflows 这两个**列表端点**——
# 即仅供"用户选哪个工作流"的下拉。生成时 (generate-stream) 根本不调用
# is_supported_*；用户的 ComfyUI workflow_dir、get_workflow_json 的多级
# 回退、classifier、precheck 等机制全都保持原状。
#
# 想加新工作流：
#   1. 把 .json 放到仓库 workflows/ 下
#   2. 在下面的集合里加它的名字
#   3. （如果分类器没法靠名字 / 节点签名识别，加一份 <name>.meta.json 说 "kind": "..."）
#
# 这一硬名单确保用户不会再看见 ComfyUI 目录里几十个无关工作流，并且永远只
# 出现我们实际有 driver 能驱动的工作流。

SUPPORTED_IMAGE_WORKFLOWS: frozenset = frozenset({
    "t2i-lumicreate",
    "image_flux2_text_to_image_9b",
    "image_flux2_klein_image_edit_9b_base",
})

SUPPORTED_VIDEO_WORKFLOWS: frozenset = frozenset({
    "flfa2i-lumicreate",
    "video_ltx2_3_i2v",
})


def is_supported_image_workflow(name: str, workflow: Optional[dict] = None,
                                  workflow_path: Optional[str | Path] = None) -> bool:
    """image-engine 下拉过滤。
    硬名单（SUPPORTED_IMAGE_WORKFLOWS）+ 分类器双门控；硬名单为第一道闸。
    """
    if name not in SUPPORTED_IMAGE_WORKFLOWS:
        return False
    kind = classify_workflow(name, workflow=workflow, workflow_path=workflow_path)
    return kind in ("t2i", "i2i_single", "i2i_double")


def is_supported_video_workflow(name: str, workflow: Optional[dict] = None,
                                 workflow_path: Optional[str | Path] = None) -> bool:
    """video-engine 下拉过滤。
    硬名单（SUPPORTED_VIDEO_WORKFLOWS）+ 分类器双门控。
    """
    if name not in SUPPORTED_VIDEO_WORKFLOWS:
        return False
    kind = classify_video_workflow(name, workflow=workflow, workflow_path=workflow_path)
    return kind in ("video_flfa2i", "video_i2v")


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
