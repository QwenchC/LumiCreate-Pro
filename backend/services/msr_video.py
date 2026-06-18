"""v1.6: MSR 多图参考 LTX-2.3 视频工作流的 patch（Phase B）。

按节点【连接拓扑】（而非硬编码 ID）定位关键节点，使工作流被重导出/改 ID 后仍稳健：
  - INTConstant → EmptyLTXVLatentVideo.{width,height,length}  ⇒ 视频尺寸/帧数
  - LiconMSR.{1,2,3} ← LoadImage(角色白底参考) / .background ← LoadImage(背景参考)
  - fps 写进 CreateVideo / LTXVConditioning / LTXVEmptyLatentAudio
  - 没分到参考图的 LoadImage 设 mode=4(bypass)
  - 正向提示词写进接到 LTXVConditioning.positive 的 CLIPTextEncode

只做 litegraph 层面的确定性变换；上传参考图 + 提交 ComfyUI 由调用方处理。
"""
from __future__ import annotations

import base64
import json
import math
import uuid
from typing import AsyncGenerator, Optional

import copy


def is_msr_workflow(workflow: dict) -> bool:
    """是否为 MSR 多图参考工作流（含 LiconMSR 节点即是）。"""
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not nodes:
        return False
    return any("LiconMSR" in str(n.get("type", "")) for n in nodes)


def load_bundled_msr_workflow() -> Optional[dict]:
    """从 bundled workflows/ 目录加载 MSR 多图参考工作流（按 LiconMSR 节点签名识别，
    不依赖具体文件名，工作流被重命名也能找到）。找不到返回 None。

    MSR 不在 SUPPORTED_VIDEO_WORKFLOWS 硬名单里——它不是用户可选的主工作流，
    而是【按分镜开关】，所以这里独立加载、与视频工作流下拉互不影响。
    """
    try:
        from services.comfyui import bundled_workflow_dir
    except Exception:
        return None
    base = bundled_workflow_dir()
    if base is None:
        return None
    import glob
    from pathlib import Path
    # 先按常见命名快速命中，再退化为「扫所有 json 找含 LiconMSR 的」
    candidates = sorted(glob.glob(str(base / "MSR_*.json"))) + \
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
        if is_msr_workflow(wf):
            return wf
    return None


def _nodes_by_type(wf: dict, type_name: str) -> list[dict]:
    return [n for n in wf.get("nodes", []) if n.get("type") == type_name]


def _link_src_node(wf: dict, link_id) -> int | None:
    """litegraph link 形如 [id, from_node, from_slot, to_node, to_slot, type]。"""
    if link_id is None:
        return None
    for l in wf.get("links", []):
        if l and l[0] == link_id:
            return l[1]
    return None


def _input_link(node: dict, input_name: str):
    for inp in node.get("inputs") or []:
        if inp.get("name") == input_name:
            return inp.get("link")
    return None


def _set_widget(node: dict, idx: int, value) -> None:
    wv = node.get("widgets_values")
    if not isinstance(wv, list):
        wv = []
        node["widgets_values"] = wv
    while len(wv) <= idx:
        wv.append(None)
    wv[idx] = value


def patch_msr_workflow(
    workflow: dict,
    *,
    width: int,
    height: int,
    fps: float,
    duration_secs: int,
    prompt: str = "",
    char_files: list[str] | None = None,
    bg_file: str | None = None,
) -> dict:
    """返回 patch 后的 litegraph workflow 深拷贝。

    char_files: 角色白底参考图（已上传到 ComfyUI 的文件名）按顺序填 LiconMSR 槽 1/2/3。
    bg_file:    背景参考图文件名，填 LiconMSR.background。
    多余的参考 LoadImage 节点会被 bypass(mode=4)。
    """
    wf = copy.deepcopy(workflow)
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    fps = float(fps)
    duration_secs = max(1, int(duration_secs))
    frames = max(9, int(round(fps * duration_secs)))
    char_files = [c for c in (char_files or []) if c]

    def _const_for(node: dict, input_name: str) -> dict | None:
        src = _link_src_node(wf, _input_link(node, input_name))
        n = nodes.get(src) if src is not None else None
        return n if (n and n.get("type") == "INTConstant") else None

    # 1) 尺寸/帧数：回溯 EmptyLTXVLatentVideo 的 width/height/length 输入到 INTConstant
    for empty in _nodes_by_type(wf, "EmptyLTXVLatentVideo"):
        for name, val, widx in (("width", width, 0), ("height", height, 1),
                                 ("length", frames, 2)):
            const = _const_for(empty, name)
            if const is not None:
                _set_widget(const, 0, int(val))
            else:
                _set_widget(empty, widx, int(val))   # 未接常量则直接写自身 widget
    # LiconMSR 的 width/height 跟随（frames widget 是引导帧，保留作者设置）
    for licon in _nodes_by_type(wf, "LiconMSR"):
        for name, val in (("width", width), ("height", height)):
            const = _const_for(licon, name)
            if const is not None:
                _set_widget(const, 0, int(val))
    # 音频 latent 帧数跟随
    for aud in _nodes_by_type(wf, "LTXVEmptyLatentAudio"):
        const = _const_for(aud, "frames_number")
        if const is not None:
            _set_widget(const, 0, int(frames))

    # 2) fps：CreateVideo[0] / LTXVConditioning[0] / LTXVEmptyLatentAudio[1]
    for n in _nodes_by_type(wf, "CreateVideo"):
        _set_widget(n, 0, fps)
    for n in _nodes_by_type(wf, "LTXVConditioning"):
        _set_widget(n, 0, fps)
    for n in _nodes_by_type(wf, "LTXVEmptyLatentAudio"):
        _set_widget(n, 1, fps)

    # 3) 正向提示词：接到 LTXVConditioning.positive 的 CLIPTextEncode
    if prompt:
        for cond in _nodes_by_type(wf, "LTXVConditioning"):
            src = _link_src_node(wf, _input_link(cond, "positive"))
            clip = nodes.get(src) if src is not None else None
            if clip is not None and clip.get("type") == "CLIPTextEncode":
                _set_widget(clip, 0, prompt)
                break

    # 4) 参考图：LiconMSR 槽 1/2/3 ← 角色白底参考；background ← 背景参考；未用的 bypass
    for licon in _nodes_by_type(wf, "LiconMSR"):
        slot_files: dict[str, str] = {}
        for i, name in enumerate(("1", "2", "3")):
            if i < len(char_files):
                slot_files[name] = char_files[i]
        if bg_file:
            slot_files["background"] = bg_file
        for name in ("1", "2", "3", "background"):
            src = _link_src_node(wf, _input_link(licon, name))
            ld = nodes.get(src) if src is not None else None
            if not ld or "LoadImage" not in str(ld.get("type", "")):
                continue
            if name in slot_files:
                ld["mode"] = 0                       # 启用
                _set_widget(ld, 0, slot_files[name])
            else:
                ld["mode"] = 4                       # bypass 未用的参考槽

    return wf


async def generate_msr_video(
    comfyui_url: str,
    workflow: dict,
    *,
    char_b64_list: list[str],
    bg_b64: Optional[str],
    width: int,
    height: int,
    fps: float,
    duration_ms: int,
    positive_prompt: str = "",
    scene_id: str = "",
) -> AsyncGenerator[dict, None]:
    """MSR 多图参考视频生成：上传角色白底参考 + 背景参考 → patch → 提交 ComfyUI →
    流式回传进度。输出视频含 LTX 自带音轨、【无 BGM】，事件 schema 与现有视频通路一致
    （uploading/queued/progress/completed/error），下游 record_asset/videos.json 0 改动。
    """
    # 复用 LTX 现成基础设施（上传/取视频/ws）+ comfyui 的 litegraph→api 转换
    import httpx
    from services.ltx2video import _upload_image, _fetch_video, websockets
    from services.comfyui import _litegraph_to_api

    yield {"event": "uploading", "scene_id": scene_id}

    # ── 1. 上传参考图（角色白底立绘 + 背景图）──────────────────────────────────
    try:
        char_files: list[str] = []
        for i, b in enumerate(char_b64_list or []):
            if not b:
                continue
            name = await _upload_image(
                comfyui_url, base64.b64decode(b), f"lumi_msr_{scene_id}_c{i}.png")
            char_files.append(name)
        bg_file = None
        if bg_b64:
            bg_file = await _upload_image(
                comfyui_url, base64.b64decode(bg_b64), f"lumi_msr_{scene_id}_bg.png")
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"参考图上传失败: {e}"}
        return
    if not char_files and not bg_file:
        yield {"event": "error", "scene_id": scene_id, "message": "至少需要 1 张参考图"}
        return

    # ── 2. patch + 转 API ─────────────────────────────────────────────────────
    duration_secs = max(1, math.ceil(duration_ms / 1000))
    patched_lg = patch_msr_workflow(
        workflow, width=width, height=height, fps=fps, duration_secs=duration_secs,
        prompt=positive_prompt, char_files=char_files, bg_file=bg_file,
    )
    try:
        api_workflow = _litegraph_to_api(patched_lg)
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"工作流转换失败: {e}"}
        return

    # ── 3. 提交任务 ────────────────────────────────────────────────────────────
    client_id = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(f"{comfyui_url}/prompt",
                                json={"prompt": api_workflow, "client_id": client_id})
            if r.status_code >= 400:
                try:
                    detail = r.json()
                    errmsg = detail.get("error", {}).get("message") or str(detail)
                except Exception:
                    errmsg = r.text[:500]
                yield {"event": "error", "scene_id": scene_id,
                       "message": f"提交任务失败 {r.status_code}: {errmsg}"}
                return
            r.raise_for_status()
            prompt_id = r.json()["prompt_id"]
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"提交任务失败: {e}"}
        return

    yield {"event": "queued", "prompt_id": prompt_id, "scene_id": scene_id}

    # ── 4. WebSocket 进度 + 取视频 ─────────────────────────────────────────────
    if websockets is None:
        yield {"event": "error", "scene_id": scene_id, "message": "websockets 包未安装"}
        return
    ws_url = comfyui_url.replace("http://", "ws://").replace("https://", "wss://")
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
                           "max": data.get("max", 1), "scene_id": scene_id}
                elif mtype == "executing":
                    if data.get("node") is None and data.get("prompt_id") == prompt_id:
                        video_data = await _fetch_video(comfyui_url, prompt_id)
                        if video_data:
                            # MSR 输出含 LTX 自带音轨、无 BGM —— 不替换音轨
                            yield {"event": "completed", "scene_id": scene_id,
                                   "video": video_data["data"],
                                   "filename": video_data["filename"], "mime": "video/mp4"}
                        else:
                            yield {"event": "error", "scene_id": scene_id,
                                   "message": "未找到输出视频文件"}
                        return
                elif mtype == "execution_error":
                    if data.get("prompt_id") == prompt_id:
                        yield {"event": "error", "scene_id": scene_id,
                               "message": data.get("exception_message", "ComfyUI 执行错误")}
                        return
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"WebSocket 错误: {e}"}
