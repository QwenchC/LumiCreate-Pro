"""v1.6: 视频后期【识别分段 → 逐条 RVC 变声 → 换音轨】工作流的 patch（Phase C）。

工作流拓扑（视频后期_识别分段_逐条变声_换音轨.json）：
  LoadAudio(从 input 里的 mp4 取音轨)
    → MelBandRoFormerSampler(人声/伴奏分离)
      → RedubAnalyze(Whisper 分段：whisper_model / language)
        → RedubReVoice(逐段 RVC 变声：voice_mapping / default_model / rvc_root / rvc_python / device)
          → RedubFinalize(把变声后的音轨换回原视频：video_path / finalize)

音色一致性做法：voice_mapping 留空 → 所有分段都用同一个 default_model（.pth）变声，
整条视频统一音色。需要外部 RVC 环境（默认 E:\\Clone\\RVC20240604Nvidia50x0）+ 训练好的 .pth。

只做 litegraph 层面的确定性变换；上传视频 + 提交 ComfyUI + 取回成片由调用方处理。
按节点【类型】定位（不硬编码 ID），与 msr_video.py 同思路，工作流重导出后仍稳健。
"""
from __future__ import annotations

import base64
import copy
import json
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional


# RedubReVoice 的 widgets_values 下标。
# 关键：node 的 inputs[0]=project_dir 是【widget 槽 + 已连线】，_litegraph_to_api 对这种
# “既有 link 又占 widget 槽”的输入仍会让 wv_idx +1（comfyui.py:811-816）。所以 widgets_values
# 的实际消费顺序是 [0]=project_dir(被连线值取代、槽丢弃) [1]=voice_mapping [2]=default_model …
# 即所有字段相对“纯 widget 计数”整体右移一位。下标按【实测 _litegraph_to_api 解析结果】校准。
_REVOICE_W = {
    "voice_mapping": 1,   # 逐说话人映射；留空=全用 default_model（[0] 是 project_dir 连线槽）
    "default_model": 2,   # 默认 RVC .pth
    "transpose":     3,
    # 4 = f0_method, 5 = index_rate, 6 = protect, 7 = rms_mix_rate,
    # 8 = filter_radius, 9 = edge_crossfade_ms
    "index_rate":    5,
    "protect":       6,
    "rvc_root":      10,
    "rvc_python":    11,
    "device":        12,
    # 13 = regen_seed, 14 = mixback_gain
}


def is_redub_workflow(workflow: dict) -> bool:
    """是否为视频后期变声工作流（含 RedubFinalize / RedubReVoice 节点即是）。"""
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not nodes:
        return False
    types = {str(n.get("type", "")) for n in nodes}
    return "RedubFinalize" in types or "RedubReVoice" in types


def load_bundled_redub_workflow() -> Optional[dict]:
    """从 bundled workflows/ 加载视频后期变声工作流（按 RedubFinalize 签名识别，
    不依赖文件名）。与 MSR 一样不在视频工作流硬名单里——它是【后期处理】专用。"""
    try:
        from services.comfyui import bundled_workflow_dir
    except Exception:
        return None
    base = bundled_workflow_dir()
    if base is None:
        return None
    import glob
    candidates = sorted(glob.glob(str(base / "*识别分段*.json"))) + \
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
        if is_redub_workflow(wf):
            return wf
    return None


def _nodes_by_type(wf: dict, type_name: str) -> list[dict]:
    return [n for n in wf.get("nodes", []) if n.get("type") == type_name]


def _set_widget(node: dict, idx: int, value) -> None:
    wv = node.get("widgets_values")
    if not isinstance(wv, list):
        wv = []
        node["widgets_values"] = wv
    while len(wv) <= idx:
        wv.append(None)
    wv[idx] = value


def patch_redub_workflow(
    workflow: dict,
    *,
    input_video_filename: str,
    video_full_path: str,
    default_model: str,
    voice_mapping: str = "",
    rvc_root: str = "",
    rvc_python: str = "",
    device: str = "",
    whisper_model: str = "",
    language: str = "",
    filename_prefix: str = "",
    transpose: Optional[int] = None,
    index_rate: Optional[float] = None,
    protect: Optional[float] = None,
) -> dict:
    """返回 patch 后的 litegraph workflow 深拷贝。

    input_video_filename: 已放进 ComfyUI/input 的 mp4 文件名（LoadAudio 从中取音轨）。
    video_full_path:      该视频在 ComfyUI 机器上的完整路径（RedubFinalize 换音轨用）。
    default_model:        默认 RVC .pth；voice_mapping 留空时所有分段都用它（音色一致）。
    其余（rvc_root/rvc_python/device/whisper_model/language/filename_prefix/...）
      仅在传入非空/非 None 时覆盖，否则保留工作流自带默认。
    """
    wf = copy.deepcopy(workflow)

    # 1) LoadAudio ← 上传到 input 的 mp4 文件名
    for n in _nodes_by_type(wf, "LoadAudio"):
        _set_widget(n, 0, input_video_filename)

    # 2) RedubAnalyze ← whisper_model(0) / language(1)（project_name/min_dur 保留）
    for n in _nodes_by_type(wf, "RedubAnalyze"):
        if whisper_model:
            _set_widget(n, 0, whisper_model)
        if language:
            _set_widget(n, 1, language)

    # 3) RedubReVoice ← voice_mapping / default_model / rvc_root / rvc_python / device …
    for n in _nodes_by_type(wf, "RedubReVoice"):
        _set_widget(n, _REVOICE_W["voice_mapping"], voice_mapping or "")
        if default_model:
            _set_widget(n, _REVOICE_W["default_model"], default_model)
        if rvc_root:
            _set_widget(n, _REVOICE_W["rvc_root"], rvc_root)
        if rvc_python:
            _set_widget(n, _REVOICE_W["rvc_python"], rvc_python)
        if device:
            _set_widget(n, _REVOICE_W["device"], device)
        if transpose is not None:
            _set_widget(n, _REVOICE_W["transpose"], int(transpose))
        if index_rate is not None:
            _set_widget(n, _REVOICE_W["index_rate"], float(index_rate))
        if protect is not None:
            _set_widget(n, _REVOICE_W["protect"], float(protect))

    # 4) RedubFinalize ← video_path(0) / filename_prefix(1) / finalize(2)=True / ffmpeg(3)
    for n in _nodes_by_type(wf, "RedubFinalize"):
        _set_widget(n, 0, video_full_path)
        if filename_prefix:
            _set_widget(n, 1, filename_prefix)
        _set_widget(n, 2, True)            # 必须 True 才真正写出成片

    # 5) bypass 纯 UI 节点（ShowText / PreviewAudio）—— headless 无需，且 ShowText 在
    #    API 提交（无 extra_pnginfo）时会刷 "extra_pnginfo[0] is not a dict" 噪声错。
    for n in wf.get("nodes", []):
        t = str(n.get("type", ""))
        if "ShowText" in t or t == "PreviewAudio":
            n["mode"] = 4

    return wf


async def _fetch_redub_output(comfyui_url: str, prompt_id: str) -> Optional[dict]:
    """取回 RedubFinalize 写出的成片。优先按 /history 里的输出走 /view 下载（可跨机），
    其次扫常见的 videos/gifs 输出键。返回 {filename, data(base64)} 或 None。"""
    import httpx
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.get(f"{comfyui_url}/history/{prompt_id}")
            r.raise_for_status()
            history = r.json()
        except Exception:
            return None

        outputs = history.get(prompt_id, {}).get("outputs", {})

        # a) 任何 mp4/mov/webm 的 UI 输出（videos/gifs/images）
        for node_out in outputs.values():
            for key in ("videos", "gifs", "images"):
                for item in node_out.get(key, []) or []:
                    fname = item.get("filename", "")
                    if fname.lower().endswith((".mp4", ".mov", ".webm")):
                        try:
                            dl = await client.get(
                                f"{comfyui_url}/view",
                                params={"filename": fname,
                                        "subfolder": item.get("subfolder", ""),
                                        "type": item.get("type", "output")})
                            dl.raise_for_status()
                            return {"filename": fname,
                                    "data": base64.b64encode(dl.content).decode()}
                        except Exception:
                            pass

        # b) RedubFinalize 的 output_path（STRING）—— 解析出 文件名 + 子目录再 /view
        for node_out in outputs.values():
            cand = []
            op = node_out.get("output_path")
            if isinstance(op, list):
                cand += [x for x in op if isinstance(x, str)]
            txt = node_out.get("text")
            if isinstance(txt, list):
                cand += [x for x in txt if isinstance(x, str)]
            for path_str in cand:
                if not path_str.lower().endswith((".mp4", ".mov", ".webm")):
                    continue
                p = path_str.replace("\\", "/")
                fname = p.rsplit("/", 1)[-1]
                # 取 output/ 之后的子目录作 subfolder（拿不到就用 filename_prefix 的目录）
                subfolder = ""
                if "/output/" in p:
                    tail = p.split("/output/", 1)[1]
                    subfolder = tail.rsplit("/", 1)[0] if "/" in tail else ""
                for sf in (subfolder, "redub", ""):
                    try:
                        dl = await client.get(
                            f"{comfyui_url}/view",
                            params={"filename": fname, "subfolder": sf, "type": "output"})
                        if dl.status_code == 200 and dl.content:
                            return {"filename": fname,
                                    "data": base64.b64encode(dl.content).decode()}
                    except Exception:
                        pass
    return None


def _find_redub_output_on_disk(input_dir: str, prefix: str,
                               since_ts: float) -> Optional[dict]:
    """RedubFinalize 是 OUTPUT_NODE 但只返回路径字符串、不进 /history（没有 ui 输出），
    所以 /view 取不到。这里直接从磁盘取：output 目录 = input 同级 output/，按 filename_prefix
    在子目录里找 since_ts 之后【最新】的 mp4。RVC 后期必为本地 ComfyUI，磁盘可达。"""
    try:
        out_root = Path(input_dir).parent / "output"
        sub, name = "", prefix
        if "/" in prefix:
            sub, name = prefix.rsplit("/", 1)
        elif "\\" in prefix:
            sub, name = prefix.rsplit("\\", 1)
        search_dir = (out_root / sub) if sub else out_root
        if not search_dir.is_dir():
            return None
        cands = [p for p in search_dir.glob(f"{name}_*.mp4")
                 if p.stat().st_mtime >= since_ts - 3]
        if not cands:
            return None
        newest = max(cands, key=lambda p: p.stat().st_mtime)
        return {"filename": newest.name,
                "data": base64.b64encode(newest.read_bytes()).decode()}
    except Exception:
        return None


async def generate_redub_video(
    comfyui_url: str,
    workflow: dict,
    *,
    video_bytes: bytes,
    default_model: str,
    voice_mapping: str = "",
    rvc_root: str = "",
    rvc_python: str = "",
    device: str = "",
    whisper_model: str = "",
    language: str = "",
    comfyui_input_dir: str = "",
    workflow_dir: str = "",
    scene_id: str = "",
) -> AsyncGenerator[dict, None]:
    """视频后期变声：把分镜视频放进 ComfyUI/input → patch → 提交 → 取回换好音轨的成片。

    事件 schema 与视频通路一致（uploading/queued/progress/completed/error）。
    completed.video 是 base64 mp4（音轨已 RVC 变声、画面不变），下游复用现有落盘通路。
    需要外部 RVC 环境（rvc_root / rvc_python）+ 训练好的 .pth（default_model）。
    """
    import httpx
    from services.ltx2video import _resolve_input_dir, websockets
    from services.comfyui import _litegraph_to_api

    yield {"event": "uploading", "scene_id": scene_id}

    # ── 1. 把视频放进 ComfyUI/input（LoadAudio 从中取音轨；RedubFinalize 也用同一文件）──
    input_dir = _resolve_input_dir(comfyui_input_dir, workflow_dir)
    if not input_dir:
        yield {"event": "error", "scene_id": scene_id,
               "message": "未配置 ComfyUI input 目录，无法放置视频做后期变声"}
        return
    base_id = scene_id or uuid.uuid4().hex
    fname = f"lumi_redub_{base_id}.mp4"
    out_prefix = f"redub/lumi_redub_{base_id}"   # 唯一前缀，便于从磁盘精确定位成片
    try:
        import asyncio
        dest = Path(input_dir) / fname
        await asyncio.to_thread(dest.write_bytes, video_bytes)
        video_full_path = str(dest)
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"视频写入 input 失败: {e}"}
        return

    # ── 2. patch + 转 API ─────────────────────────────────────────────────────
    patched = patch_redub_workflow(
        workflow,
        input_video_filename=fname, video_full_path=video_full_path,
        default_model=default_model, voice_mapping=voice_mapping,
        rvc_root=rvc_root, rvc_python=rvc_python, device=device,
        whisper_model=whisper_model, language=language,
        filename_prefix=out_prefix,
    )
    try:
        api_workflow = _litegraph_to_api(patched)
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"工作流转换失败: {e}"}
        return

    # ── 3. 提交任务 ────────────────────────────────────────────────────────────
    submit_ts = __import__("time").time()

    async def _get_out():
        # RedubFinalize 不进 /history → 先从磁盘按唯一前缀取；再退化 /view 兜底
        o = _find_redub_output_on_disk(input_dir, out_prefix, submit_ts)
        if o:
            return o
        return await _fetch_redub_output(comfyui_url, prompt_id)

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

    # ── 4. WebSocket 进度 + 取回成片 ───────────────────────────────────────────
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
                        out = await _get_out()
                        produced_terminal = True
                        if out:
                            yield {"event": "completed", "scene_id": scene_id,
                                   "video": out["data"], "filename": out["filename"],
                                   "mime": "video/mp4"}
                        else:
                            yield {"event": "error", "scene_id": scene_id,
                                   "message": "未找到后期成片（RedubFinalize 未写出？检查 RVC 环境）"}
                        return
                elif mtype == "execution_error":
                    if data.get("prompt_id") == prompt_id:
                        produced_terminal = True
                        yield {"event": "error", "scene_id": scene_id,
                               "message": data.get("exception_message", "ComfyUI 执行错误")}
                        return
        # WS 干净关闭却没给终止事件 —— 兜底取一次成片，别静默消失
        if not produced_terminal:
            out = await _get_out()
            if out:
                yield {"event": "completed", "scene_id": scene_id,
                       "video": out["data"], "filename": out["filename"], "mime": "video/mp4"}
            else:
                yield {"event": "error", "scene_id": scene_id,
                       "message": "ComfyUI 连接中断，未取得后期成片"}
    except Exception as e:
        yield {"event": "error", "scene_id": scene_id, "message": f"WebSocket 错误: {e}"}
