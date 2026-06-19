"""v1.6: 视频去水印/去字幕（LTX-2.3 V2V）工作流的 patch + 运行。

工作流（LTX-2.3_-_V2V_视频去水印去字幕.json）用 LTX IC-LoRA（去字幕 + 去水印）做
视频到视频重绘。关键可调项：
  - VHS_LoadVideoFFmpeg.video       ← 上传到 ComfyUI/input 的待处理视频
  - INTConstant「MAX PIXEL SIZE (longest)」← 输出视频最长边像素（应按【输入视频最长边】设定；
    低显存可调小，note 535 原话：原视频更小就设成和原视频一样、别放大）
  - INTConstant「MAX SECONDS」       ← 输入视频最大时长（可选）
  - VHS_VideoCombine.save_output    ← 置 True 才落 output/ 并进 /history（可 /view 取回）

按节点【类型/标题】定位（不硬编码 ID），与 msr_video / redub_video 同思路。
"""
from __future__ import annotations

import base64
import copy
import json
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional


def is_watermark_workflow(workflow: dict) -> bool:
    """是否为去水印/去字幕 V2V 工作流（含 VHS_LoadVideoFFmpeg + 去水印/去字幕 IC-LoRA）。"""
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not nodes:
        return False
    has_loadvid = any("VHS_LoadVideoFFmpeg" in str(n.get("type", "")) for n in nodes)
    has_iclora = any("ICLoRA" in str(n.get("type", "")) for n in nodes)
    blob = json.dumps(workflow, ensure_ascii=False).lower()
    hints = ("watermark" in blob) or ("subtitle" in blob) or ("去水印" in blob) or ("去字幕" in blob)
    return has_loadvid and (has_iclora or hints)


def load_bundled_watermark_workflow() -> Optional[dict]:
    """从 bundled workflows/ 加载去水印/去字幕工作流（按签名识别，不依赖文件名）。"""
    try:
        from services.comfyui import bundled_workflow_dir
    except Exception:
        return None
    base = bundled_workflow_dir()
    if base is None:
        return None
    import glob
    candidates = sorted(glob.glob(str(base / "*去水印*.json"))) + \
        sorted(glob.glob(str(base / "*V2V*.json"))) + \
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
        if is_watermark_workflow(wf):
            return wf
    return None


def _nodes_by_type(wf: dict, type_name: str) -> list[dict]:
    return [n for n in wf.get("nodes", []) if n.get("type") == type_name]


def _set_list_widget(node: dict, idx: int, value) -> None:
    wv = node.get("widgets_values")
    if not isinstance(wv, list):
        wv = []
        node["widgets_values"] = wv
    while len(wv) <= idx:
        wv.append(None)
    wv[idx] = value


def patch_watermark_workflow(
    workflow: dict,
    *,
    input_video_filename: str,
    longest_edge: int,
    max_seconds: Optional[int] = None,
    output_prefix: Optional[str] = None,
) -> dict:
    """返回 patch 后的 litegraph workflow 深拷贝。

    longest_edge: 输出视频最长边像素（调用方按【输入视频最长边】算好，含低显存上限）。
    """
    wf = copy.deepcopy(workflow)
    longest_edge = max(64, int(longest_edge))

    # 1) 待处理视频 → VHS_LoadVideoFFmpeg（widgets_values 是 dict，键 'video'）
    for n in _nodes_by_type(wf, "VHS_LoadVideoFFmpeg"):
        wv = n.get("widgets_values")
        if isinstance(wv, dict):
            wv["video"] = input_video_filename
            vp = wv.get("videopreview")
            if isinstance(vp, dict) and isinstance(vp.get("params"), dict):
                vp["params"]["filename"] = input_video_filename
        else:
            _set_list_widget(n, 0, input_video_filename)

    # 2) 最长边像素 → 标题含 PIXEL/LONGEST 的 INTConstant（MAX PIXEL SIZE）
    for n in _nodes_by_type(wf, "INTConstant"):
        title = str(n.get("title") or "").upper()
        if "PIXEL" in title or "LONGEST" in title or "LONGER" in title:
            _set_list_widget(n, 0, longest_edge)

    # 3) 可选最大时长 → 标题含 SECOND 的 INTConstant（MAX SECONDS）
    if max_seconds:
        for n in _nodes_by_type(wf, "INTConstant"):
            if "SECOND" in str(n.get("title") or "").upper():
                _set_list_widget(n, 0, int(max_seconds))

    # 4) VHS_VideoCombine：save_output=True 才落 output/ 并进 /history；可改唯一前缀
    for n in _nodes_by_type(wf, "VHS_VideoCombine"):
        wv = n.get("widgets_values")
        if isinstance(wv, dict):
            wv["save_output"] = True
            if output_prefix:
                wv["filename_prefix"] = output_prefix

    return wf


async def generate_watermark_removal(
    comfyui_url: str,
    workflow: dict,
    *,
    video_bytes: bytes,
    longest_edge: int,
    max_seconds: Optional[int] = None,
    comfyui_input_dir: str = "",
    workflow_dir: str = "",
    scene_id: str = "",
) -> AsyncGenerator[dict, None]:
    """去水印/去字幕：把视频放进 ComfyUI/input → patch → 提交 → 取回重绘成片。

    事件 schema 与视频通路一致（uploading/queued/progress/completed/error）。
    longest_edge 由调用方按【输入视频最长边】（含低显存上限）算好传入。
    """
    import httpx
    from services.ltx2video import _resolve_input_dir, _fetch_video, websockets
    from services.comfyui import _litegraph_to_api

    yield {"event": "uploading", "scene_id": scene_id}

    input_dir = _resolve_input_dir(comfyui_input_dir, workflow_dir)
    if not input_dir:
        yield {"event": "error", "scene_id": scene_id,
               "message": "未配置 ComfyUI input 目录，无法放置视频做去水印"}
        return
    base_id = scene_id or uuid.uuid4().hex
    fname = f"lumi_dewm_{base_id}.mp4"
    out_prefix = f"lumi_dewm_{base_id}"
    try:
        import asyncio
        dest = Path(input_dir) / fname
        await asyncio.to_thread(dest.write_bytes, video_bytes)
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"视频写入 input 失败: {e}"}
        return

    patched = patch_watermark_workflow(
        workflow, input_video_filename=fname, longest_edge=longest_edge,
        max_seconds=max_seconds, output_prefix=out_prefix,
    )
    try:
        api_workflow = _litegraph_to_api(patched)
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"工作流转换失败: {e}"}
        return

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
                    errmsg = r.text[:600]
                yield {"event": "error", "scene_id": scene_id,
                       "message": f"提交任务失败 {r.status_code}: {errmsg}"}
                return
            r.raise_for_status()
            prompt_id = r.json()["prompt_id"]
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"提交任务失败: {e}"}
        return

    yield {"event": "queued", "prompt_id": prompt_id, "scene_id": scene_id}

    if websockets is None:
        yield {"event": "error", "scene_id": scene_id, "message": "websockets 包未安装"}
        return
    ws_url = comfyui_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws?clientId={client_id}"
    produced_terminal = False
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
                        out = await _fetch_video(comfyui_url, prompt_id)
                        produced_terminal = True
                        if out:
                            yield {"event": "completed", "scene_id": scene_id,
                                   "video": out["data"], "filename": out["filename"],
                                   "mime": "video/mp4"}
                        else:
                            yield {"event": "error", "scene_id": scene_id,
                                   "message": "未找到去水印成片（VHS_VideoCombine 未输出？）"}
                        return
                elif mtype == "execution_error":
                    if data.get("prompt_id") == prompt_id:
                        produced_terminal = True
                        yield {"event": "error", "scene_id": scene_id,
                               "message": data.get("exception_message", "ComfyUI 执行错误")}
                        return
        if not produced_terminal:
            out = await _fetch_video(comfyui_url, prompt_id)
            if out:
                yield {"event": "completed", "scene_id": scene_id,
                       "video": out["data"], "filename": out["filename"], "mime": "video/mp4"}
            else:
                yield {"event": "error", "scene_id": scene_id,
                       "message": "ComfyUI 连接中断，未取得去水印成片"}
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"WebSocket 错误: {e}"}
