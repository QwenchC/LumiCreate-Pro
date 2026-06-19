"""v1.6.1: 角色「标准造型」立绘生成（Z-Image-Turbo-ControlNet 工作流）。

用固定姿势图（assets/pic/character_default_pose.png）做 ControlNet 约束 + 角色外貌提示词，
生成【空白背景】的特定角色姿势图，供 MSR 多图参考视频做角色参考。

工作流要点（Z-Image-Turbo-ControlNet.json）：
  - LoadImage              ← 姿势图（ControlNet 参考）
  - QwenImageDiffsynthControlnet  ← 应用姿势
  - ImageScaleByAspectRatio V2 (aspect_ratio="original") → 按姿势图比例【自适应尺寸】
    （所以不约束竖幅；不要去改尺寸）
  - CLIPTextEncode(KSampler.positive) ← 空白背景 + 角色外貌
  - SaveImage → /history images（_fetch_images 取回）

按【节点类型/连接】定位（不硬编码 ID），与 msr_video / redub_video 同思路。
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional


def is_standard_pose_workflow(workflow: dict) -> bool:
    """是否为 Z-Image ControlNet 标准造型工作流（含 QwenImageDiffsynthControlnet 即是）。"""
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not nodes:
        return False
    return any("QwenImageDiffsynthControlnet" in str(n.get("type", "")) for n in nodes)


def load_bundled_zimage_workflow() -> Optional[dict]:
    """从 bundled workflows/ 加载 Z-Image ControlNet 工作流（按签名识别，不依赖文件名）。"""
    try:
        from services.comfyui import bundled_workflow_dir
    except Exception:
        return None
    base = bundled_workflow_dir()
    if base is None:
        return None
    import glob
    candidates = sorted(glob.glob(str(base / "Z-Image*.json"))) + \
        sorted(glob.glob(str(base / "*.json")))
    seen: set[str] = set()
    for fp in candidates:
        if fp in seen:
            continue
        seen.add(fp)
        try:
            wf = json.loads(Path(fp).read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if is_standard_pose_workflow(wf):
            return wf
    return None


def bundled_pose_image_path(orientation: str = "landscape") -> Optional[Path]:
    """固定姿势图路径（生成图按姿势图比例自适应，所以姿势图朝向 = 出图朝向）：
      - orientation='portrait'（竖幅，1114x1896）→ character_default_pose_2.png（用于竖幅视频）
      - 否则（横幅，1836x1024）            → character_default_pose.png（用于横幅视频）
    打包时 assets 通过 extraResources 落到 resources/assets，与 resources/workflows 同级。"""
    try:
        from services.comfyui import bundled_workflow_dir
    except Exception:
        return None
    base = bundled_workflow_dir()
    if base is None:
        return None
    fname = ("character_default_pose_2.png" if str(orientation).lower() == "portrait"
             else "character_default_pose.png")
    p = base.parent / "assets" / "pic" / fname
    return p if p.is_file() else None


def _link_src_node(wf: dict, link_id):
    if link_id is None:
        return None
    for l in wf.get("links", []):
        if l and l[0] == link_id:
            return l[1]
    return None


def _input_link(node: dict, name: str):
    for inp in node.get("inputs") or []:
        if inp.get("name") == name:
            return inp.get("link")
    return None


# 强制空白背景的正向前缀 + 兜底负面词（空白背景对 MSR 参考至关重要）
_BLANK_BG = ("empty background, white background, plain white backdrop, seamless white background, "
             "no scenery, no props, no furniture, simple background")
DEFAULT_NEGATIVE = ("complex background, scenery, room, indoor, outdoor, furniture, props, "
                    "gradient background, colored background, shadow on background, "
                    "blurry, bad hands, extra fingers, text, watermark, lowres, worst quality")


def build_standard_pose_prompt(appearance: str, style: str = "") -> str:
    """空白背景 + （画风）+ 角色外貌 + 全身独照。不含尺寸约束。"""
    parts = [_BLANK_BG]
    if (style or "").strip():
        parts.append(style.strip())
    if (appearance or "").strip():
        parts.append(appearance.strip())
    parts.append("solo, single character, full body, standing")
    return ", ".join(parts)


def patch_standard_pose_workflow(
    workflow: dict,
    *,
    pose_filename: str,
    positive_prompt: str,
    negative_prompt: Optional[str] = None,
) -> dict:
    """返回 patch 后的 litegraph workflow 深拷贝。
    - 所有 LoadImage 的文件名设为姿势图（工作流里只有 1 个 LoadImage）。
    - 接到 KSampler.positive 的 CLIPTextEncode ← positive_prompt；.negative ← negative_prompt。
    - 不动尺寸（ImageScaleByAspectRatio 'original' 按姿势图比例自适应）。
    """
    wf = copy.deepcopy(workflow)
    nodes = {n["id"]: n for n in wf.get("nodes", [])}

    # 1) 姿势图 → LoadImage
    for n in wf.get("nodes", []):
        if "LoadImage" in str(n.get("type", "")):
            wvs = list(n.get("widgets_values") or [])
            if not wvs:
                wvs = [pose_filename, "image"]
            else:
                wvs[0] = pose_filename
            n["widgets_values"] = wvs

    # 2) 正/负提示词 + 随机种子：按 KSampler 的 positive/negative 连接定位 CLIPTextEncode。
    #    种子必须每次随机化——'randomize' 是 UI-only 控件，API 提交会发字面种子，不随机化
    #    则每次都生成同一张（ComfyUI 还会命中缓存），无法重抽。只改 widget[0]（seed），
    #    其余槽位（control/steps/…）保持不动以免 _litegraph_to_api 的按序消费错位。
    import random
    for ks in wf.get("nodes", []):
        if ks.get("type") != "KSampler":
            continue
        wvs = list(ks.get("widgets_values") or [])
        if wvs:
            wvs[0] = random.randint(0, 2**63 - 1)   # Z-Image 种子可超 2**31
            ks["widgets_values"] = wvs
        pos = nodes.get(_link_src_node(wf, _input_link(ks, "positive")))
        neg = nodes.get(_link_src_node(wf, _input_link(ks, "negative")))
        if pos and pos.get("type") == "CLIPTextEncode":
            pos["widgets_values"] = [positive_prompt]
        if negative_prompt is not None and neg and neg.get("type") == "CLIPTextEncode":
            neg["widgets_values"] = [negative_prompt]

    return wf


async def generate_standard_pose(
    cfg,
    *,
    pose_image_bytes: bytes,
    appearance: str,
    style: str = "",
) -> AsyncGenerator[dict, None]:
    """生成标准造型立绘。事件 schema 与 image-engine 一致（queued/progress/completed/error），
    completed.images = [{filename, data(base64), type}]，前端复用现有立绘上传通路。"""
    import httpx
    from services.ltx2video import _upload_image, websockets
    from services.comfyui import _litegraph_to_api, _fetch_images

    workflow = load_bundled_zimage_workflow()
    if workflow is None:
        yield {"event": "error", "message": "未找到 Z-Image ControlNet 工作流（workflows/ 缺少含 QwenImageDiffsynthControlnet 的工作流）"}
        return

    yield {"event": "queued", "prompt_id": ""}

    # 1) 上传姿势图到 ComfyUI input
    try:
        pose_name = await _upload_image(
            cfg.comfyui_url, pose_image_bytes, f"lumi_pose_{uuid.uuid4().hex[:8]}.png")
    except Exception as e:
        yield {"event": "error", "message": f"姿势图上传失败: {e}"}
        return

    positive = build_standard_pose_prompt(appearance, style)
    patched = patch_standard_pose_workflow(
        workflow, pose_filename=pose_name, positive_prompt=positive,
        negative_prompt=DEFAULT_NEGATIVE)
    try:
        api_workflow = _litegraph_to_api(patched)
    except Exception as e:
        yield {"event": "error", "message": f"工作流转换失败: {e}"}
        return

    client_id = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(f"{cfg.comfyui_url}/prompt",
                                json={"prompt": api_workflow, "client_id": client_id})
            if r.status_code >= 400:
                try:
                    detail = r.json()
                    errmsg = detail.get("error", {}).get("message") or str(detail)
                except Exception:
                    errmsg = r.text[:600]
                yield {"event": "error", "message": f"提交任务失败 {r.status_code}: {errmsg}"}
                return
            r.raise_for_status()
            prompt_id = r.json()["prompt_id"]
    except Exception as e:
        yield {"event": "error", "message": f"提交任务失败: {e}"}
        return

    yield {"event": "queued", "prompt_id": prompt_id}

    if websockets is None:
        yield {"event": "error", "message": "websockets 包未安装"}
        return
    ws_url = cfg.comfyui_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws?clientId={client_id}"
    try:
        async with websockets.connect(ws_url, ping_interval=20) as ws:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                mtype = msg.get("type")
                data = msg.get("data", {})
                if mtype == "progress":
                    yield {"event": "progress", "value": data.get("value", 0),
                           "max": data.get("max", 1)}
                elif mtype == "executing":
                    if data.get("node") is None and data.get("prompt_id") == prompt_id:
                        images = await _fetch_images(cfg, prompt_id)
                        if images:
                            yield {"event": "completed", "images": images}
                        else:
                            yield {"event": "error", "message": "未取到标准造型生成结果"}
                        return
                elif mtype == "execution_error":
                    if data.get("prompt_id") == prompt_id:
                        yield {"event": "error",
                               "message": data.get("exception_message", "ComfyUI 执行错误")}
                        return
    except Exception as e:
        yield {"event": "error", "message": f"WebSocket 连接失败: {e}"}
