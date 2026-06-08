"""
ComfyUI integration service.

Handles:
- Fetching available workflows (JSON files from ComfyUI's workflow folder)
- Queuing prompts and tracking completion via WebSocket
- Downloading result images
"""

import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

import httpx
import websockets

from config import ImageEngineConfig


# ── Workflow listing ───────────────────────────────────────────────────────────
#
# v1.4.1+: 仅显示项目自带 workflows/ 目录里的工作流。ComfyUI 用户目录里的
# 工作流虽然能跑，但软件没适配过的不在下拉里出现，避免用户选了不支持的
# 工作流然后 ComfyUI 400 一脸懵。
#
# bundled 目录解析顺序：
#   1. 显式环境变量 LUMI_WORKFLOWS_DIR（测试或定制部署用）
#   2. 仓库根 workflows/ 子目录（开发/正常运行）
#   3. cfg.workflow_dir（最后兜底，便于用户自己加但已经通过 classifier 校验）


def bundled_workflow_dir() -> Optional[Path]:
    """返回项目自带工作流目录的绝对路径，找不到则 None。"""
    import os
    env = os.environ.get("LUMI_WORKFLOWS_DIR", "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    # backend/services/comfyui.py → parents[2] 是仓库根
    candidate = Path(__file__).resolve().parents[2] / "workflows"
    if candidate.is_dir():
        return candidate
    return None


async def list_workflows(cfg: ImageEngineConfig) -> list[str]:
    """Return names of bundled workflows (project-shipped `workflows/`).

    Only files inside the bundled directory are listed; the user's ComfyUI
    workflow directory is intentionally NOT scanned to prevent unsupported
    workflows from appearing in the UI. cfg.workflow_dir is still used as
    a fallback when the bundled directory is unavailable (test fixtures etc).
    """
    bundled = bundled_workflow_dir()
    if bundled is not None:
        return sorted(p.stem for p in bundled.glob("*.json"))

    # 兜底：cfg.workflow_dir（测试隔离环境 / 仓库结构异常时）
    if cfg.workflow_dir:
        from pathlib import Path as _Path
        d = _Path(cfg.workflow_dir)
        if d.is_dir():
            return sorted(p.stem for p in d.glob("*.json"))
    return []


async def get_workflow_json(cfg: ImageEngineConfig, workflow_name: str) -> Optional[dict]:
    """Load a workflow JSON by name. Priority: bundled dir → cfg.workflow_dir → ComfyUI API."""
    import json as _json
    from pathlib import Path as _Path

    # 1. Bundled
    bundled = bundled_workflow_dir()
    if bundled is not None:
        p = bundled / f"{workflow_name}.json"
        if p.is_file():
            try:
                return _json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                pass

    # 2. cfg.workflow_dir
    if cfg.workflow_dir:
        p = _Path(cfg.workflow_dir) / f"{workflow_name}.json"
        if p.is_file():
            try:
                return _json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                pass

    # 3. ComfyUI API
    async with httpx.AsyncClient(timeout=8) as client:
        for url in [
            f"{cfg.comfyui_url}/api/userdata/workflows/{workflow_name}.json",
            f"{cfg.comfyui_url}/userdata/workflows/{workflow_name}.json",
        ]:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                continue
    return None


# ── Single image generation ────────────────────────────────────────────────────

async def generate_image(
    cfg: ImageEngineConfig,
    workflow: dict,
    positive_prompt: str,
    negative_prompt: str = "",
    seed: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    ref_image_paths: Optional[list[str]] = None,
    workflow_name: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """
    Queue a ComfyUI prompt and stream progress events.

    轮 5：ref_image_paths 是绝对路径列表（i2i 工作流），会按顺序填入 LoadImage 节点。
    需要 workflow_name 才能查 meta.json 中声明的 ref_nodes，否则按节点 id 升序自动绑定。

    Yields dicts:
      {"event": "queued",     "prompt_id": str}
      {"event": "progress",   "value": int, "max": int}
      {"event": "completed",  "images": [{"filename": str, "data": str (base64)}]}
      {"event": "error",      "message": str}
    """
    client_id = str(uuid.uuid4())

    # 轮 5: i2i 工作流注入参考图
    if ref_image_paths:
        try:
            workflow = await _inject_ref_images(workflow, ref_image_paths,
                                                 cfg=cfg, workflow_name=workflow_name)
        except Exception as e:
            yield {"event": "error", "message": f"参考图注入失败: {e}"}
            return

    # Patch workflow prompts
    patched = _patch_workflow(workflow, positive_prompt, negative_prompt, seed, width, height)

    # Queue the prompt
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(
                f"{cfg.comfyui_url}/prompt",
                json={"prompt": patched, "client_id": client_id},
            )
            if r.status_code >= 400:
                # ComfyUI 400 / 500 的 body 通常含 {error, node_errors} —— 这是诊断关键
                detail = ""
                try:
                    j = r.json()
                    err = j.get("error") or {}
                    err_msg = err.get("message") or err.get("type") or str(err)
                    parts = [f"ComfyUI {r.status_code}: {err_msg}"] if err_msg else \
                            [f"ComfyUI {r.status_code}"]
                    node_errs = j.get("node_errors") or {}
                    for nid, ne in node_errs.items():
                        cls = (ne or {}).get("class_type", "?")
                        errs = (ne or {}).get("errors") or []
                        for e in errs:
                            etype = e.get("type", "?")
                            emsg = e.get("message", "")
                            edet = e.get("details", "")
                            parts.append(f"  • 节点 {nid} ({cls}) {etype}: {emsg} {edet}".rstrip())
                    detail = "\n".join(parts)
                except Exception:
                    detail = f"ComfyUI {r.status_code}: {r.text[:500]}"
                # 把出错的 workflow 落盘，方便 ComfyUI 控制台对照
                try:
                    from pathlib import Path as _P
                    import os as _os, time as _t
                    dump_dir = _P(_os.environ.get("APPDATA") or _P.home()) / \
                               "LumiCreate-Pro" / "diagnostics"
                    dump_dir.mkdir(parents=True, exist_ok=True)
                    dump_path = dump_dir / f"failed_prompt_{int(_t.time())}.json"
                    dump_path.write_text(
                        json.dumps(patched, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    detail += f"\n（已转储到 {dump_path}）"
                except Exception:
                    pass
                yield {"event": "error", "message": f"提交任务失败:\n{detail}"}
                return
            prompt_id = r.json()["prompt_id"]
    except Exception as e:
        yield {"event": "error", "message": f"提交任务失败: {e}"}
        return

    yield {"event": "queued", "prompt_id": prompt_id}

    # Listen via WebSocket
    ws_url = cfg.comfyui_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws?clientId={client_id}"

    try:
        async with websockets.connect(ws_url, ping_interval=20) as ws:
            async for raw in ws:
                # ComfyUI sends binary preview frames (bytes); skip them
                if isinstance(raw, bytes):
                    continue
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                mtype = msg.get("type")
                data  = msg.get("data", {})

                if mtype == "progress":
                    yield {
                        "event": "progress",
                        "value": data.get("value", 0),
                        "max":   data.get("max", 1),
                    }

                elif mtype == "executing":
                    if data.get("node") is None and data.get("prompt_id") == prompt_id:
                        # Generation finished — fetch images
                        images = await _fetch_images(cfg, prompt_id)
                        yield {"event": "completed", "images": images}
                        return

                elif mtype == "execution_error":
                    if data.get("prompt_id") == prompt_id:
                        yield {"event": "error", "message": data.get("exception_message", "未知错误")}
                        return

    except Exception as e:
        yield {"event": "error", "message": f"WebSocket 连接失败: {e}"}


# ── Fetch result images ────────────────────────────────────────────────────────

async def _fetch_images(cfg: ImageEngineConfig, prompt_id: str) -> list[dict]:
    """Download all output images for a completed prompt, return as base64."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(f"{cfg.comfyui_url}/history/{prompt_id}")
            r.raise_for_status()
            history = r.json()
        except Exception:
            return []

        outputs = history.get(prompt_id, {}).get("outputs", {})
        images = []
        for node_id, node_output in outputs.items():
            for img_info in node_output.get("images", []):
                filename = img_info["filename"]
                subfolder = img_info.get("subfolder", "")
                img_type  = img_info.get("type", "output")
                try:
                    img_r = await client.get(
                        f"{cfg.comfyui_url}/view",
                        params={"filename": filename, "subfolder": subfolder, "type": img_type},
                    )
                    img_r.raise_for_status()
                    b64 = base64.b64encode(img_r.content).decode()
                    images.append({"filename": filename, "data": b64, "type": "image/png"})
                except Exception:
                    pass
    return images


# ── 轮 5: 参考图注入（图生图工作流）───────────────────────────────────────────
#
# i2i 工作流通常有 1-2 个 LoadImage 节点。其 widgets_values[0] 是 ComfyUI input/
# 目录里的文件名。我们：
#   1) 把 ref 文件复制到 ComfyUI input/ 目录（文件名加 lumi_ref_ 前缀防冲突）
#   2) 改写 LoadImage 节点 widgets_values[0] 为新文件名
#
# 节点匹配优先级：meta.json ref_images > 工作流里按 LoadImage 节点 id 升序


async def _inject_ref_images(workflow: dict, ref_paths: list[str], *,
                              cfg, workflow_name: Optional[str] = None) -> dict:
    """注入参考图，返回展平 + patch 后的 workflow。

    步骤：
      1) 先展平 subgraph，让 LoadImage 节点全部到顶层（不管 Flux.2 子图还是普通工作流）
      2) 找出 flattened 的 LoadImage 节点（按 id 升序，subgraph 内部节点 id 会有 sg{N}_ 前缀）
      3) meta.json 的 ref_images 可指定 node_id（展平后的 id）做精确绑定
      4) 把 ref 文件拷到 ComfyUI input/ 或经 /upload/image 上传
      5) 改写每个目标 LoadImage 节点的 widgets_values[input_widget] 为新文件名
    """
    import shutil
    from pathlib import Path as _P

    # 1) 展平
    flat = _flatten_subgraphs(workflow)

    # 2) 找 LoadImage（顺序：id 字典序，str(id) 保证 int/str 都能排）
    loadimage_nodes = sorted(
        [n for n in (flat.get("nodes") or []) if n.get("type") == "LoadImage"],
        key=lambda n: str(n.get("id", "")),
    )
    if not loadimage_nodes:
        raise RuntimeError("工作流缺少 LoadImage 节点（i2i 工作流必备）")
    if not ref_paths:
        raise RuntimeError("i2i 工作流至少需要 1 张参考图")
    if len(ref_paths) > len(loadimage_nodes):
        raise RuntimeError(
            f"参考图数 ({len(ref_paths)}) 超过工作流支持的 LoadImage 节点数 ({len(loadimage_nodes)})"
        )
    # v1.4.3: 当参考图少于 LoadImage 节点数时，复制最后一张填满剩余节点。
    # 这样双图工作流（Flux.2 image-edit 等）也能只用单张参考图驱动 —— 模型
    # 看到两个相同输入，效果等同"单图编辑"，比 ComfyUI 默认 widget 文件名
    # （指向不存在的文件，会直接 400）健壮。
    effective_paths = list(ref_paths)
    while len(effective_paths) < len(loadimage_nodes):
        effective_paths.append(ref_paths[-1])
    ref_paths = effective_paths

    # 3) meta 覆盖
    from services.workflow_meta import load_meta
    meta = {}
    if workflow_name:
        wf_dir_str = getattr(cfg, "workflow_dir", "") or ""
        if wf_dir_str:
            wf_path = _P(wf_dir_str) / f"{workflow_name}.json"
            meta = load_meta(str(wf_path), type_="image")
    ref_specs = (meta.get("ref_images") or [])

    # 4) input_dir（本地复制）or 远程 /upload/image
    try:
        from services.ltx2video import _resolve_input_dir
        input_dir = _resolve_input_dir(
            getattr(cfg, "comfyui_input_dir", "") or "",
            getattr(cfg, "workflow_dir", "") or "",
        )
    except Exception:
        input_dir = ""

    async def _upload_ref_via_api(src_path: _P, dst_name: str) -> str:
        """Fallback: POST 到 /upload/image。返回 ComfyUI 端文件名。"""
        boundary = f"LumiCreateBoundary{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{dst_name}"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + src_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{cfg.comfyui_url}/upload/image",
                content=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            r.raise_for_status()
            data = r.json()
            return data.get("name") or dst_name

    # 5) 拷贝 + 注入
    for i, src_path in enumerate(ref_paths):
        # 选择目标 LoadImage 节点
        if i < len(ref_specs) and isinstance(ref_specs[i], dict) \
           and ref_specs[i].get("node_id") is not None:
            target_id = str(ref_specs[i]["node_id"])
            widget_slot = int(ref_specs[i].get("input_widget", 0))
            node = next((n for n in loadimage_nodes
                         if str(n.get("id")) == target_id), None)
            if node is None:
                raise RuntimeError(
                    f"meta.json 声明 ref_images[{i}].node_id={target_id} 但工作流找不到对应 LoadImage 节点"
                )
        else:
            node = loadimage_nodes[i]
            widget_slot = 0

        src = _P(src_path)
        if not src.is_file():
            raise FileNotFoundError(f"参考图文件不存在: {src}")
        dst_name = f"lumi_ref_{uuid.uuid4().hex[:8]}{src.suffix.lower() or '.png'}"
        if input_dir:
            dst = _P(input_dir) / dst_name
            await asyncio.to_thread(shutil.copyfile, str(src), str(dst))
            comfy_name = dst_name
        else:
            comfy_name = await _upload_ref_via_api(src, dst_name)

        wvs = list(node.get("widgets_values") or [])
        while len(wvs) <= widget_slot:
            wvs.append("")
        wvs[widget_slot] = comfy_name
        node["widgets_values"] = wvs

    return flat


# ── LiteGraph → API format converter ──────────────────────────────────────────

# ── Subgraph flattening (ComfyUI 'Subgraphs' feature, used by Flux.2 etc.) ───
#
# 新版本 ComfyUI 工作流可用 Subgraph 把一组节点封装为复合节点（顶层节点
# `type` 是 UUID）。这种工作流提交到 /prompt API 之前必须**展平**——把
# subgraph 内部节点提升到顶层 + 重连外部 link。
#
# Subgraph 结构:
#   - workflow['definitions']['subgraphs'] = [{ id: UUID, inputNode, outputNode,
#                                               inputs, outputs, nodes, links, ... }]
#   - 顶层节点 type=UUID 是该 subgraph 的"实例"
#   - 内部 inputNode (id 通常是 -10) 是 sentinel：外部 link 进入 subgraph
#     的 input 端口后，内部从 inputNode 的同序号 slot 出发
#   - outputNode (-20) 是另一个 sentinel：内部接到它的源就是该 subgraph
#     对外的 output
#
# 展平算法见 _flatten_subgraphs。


def _flatten_subgraphs(workflow: dict) -> dict:
    """递归把所有 subgraph 实例展平到顶层。返回新 workflow（不修改原对象）。"""
    defs = (workflow.get("definitions") or {}).get("subgraphs") or []
    if not defs:
        return workflow

    # 索引：subgraph UUID -> subgraph definition
    sg_by_id = {sg.get("id"): sg for sg in defs if sg.get("id")}
    if not sg_by_id:
        return workflow

    nodes  = list(workflow.get("nodes") or [])
    links  = list(workflow.get("links") or [])

    # 没有 subgraph 实例 → 无事可做
    if not any(n.get("type") in sg_by_id for n in nodes):
        return workflow

    next_link_id = max((l[0] for l in links if isinstance(l, list) and l), default=0) + 1
    new_nodes: list[dict] = []
    new_links: list[list] = list(links)

    # 工具：给 link 列表里某个 link_id 重新指向 (src_node, src_slot)
    def _rewrite_link_origin(link_id: int, new_src_id, new_src_slot: int) -> None:
        for i, l in enumerate(new_links):
            if isinstance(l, list) and l and l[0] == link_id:
                new_links[i] = [l[0], new_src_id, new_src_slot] + list(l[3:])
                return

    def _rewrite_link_target(link_id: int, new_tgt_id, new_tgt_slot: int) -> None:
        for i, l in enumerate(new_links):
            if isinstance(l, list) and l and l[0] == link_id:
                new_links[i] = list(l[:3]) + [new_tgt_id, new_tgt_slot] + list(l[5:])
                return

    # 收集需要删除的外层 link（被 subgraph 的内部展平替代后）
    drop_link_ids: set[int] = set()

    for inst in nodes:
        sg_uuid = inst.get("type")
        sg = sg_by_id.get(sg_uuid) if sg_uuid else None
        if sg is None:
            # 普通节点直接保留
            new_nodes.append(inst)
            continue

        inst_id = inst.get("id")
        prefix = f"sg{inst_id}_"   # 内部节点 id 前缀防冲突

        inputNode_id  = (sg.get("inputNode")  or {}).get("id")   # 通常 -10
        outputNode_id = (sg.get("outputNode") or {}).get("id")   # 通常 -20

        sg_inputs  = sg.get("inputs")  or []   # 实例的 input 端口定义
        sg_outputs = sg.get("outputs") or []   # 实例的 output 端口定义

        inner_nodes = sg.get("nodes") or []
        inner_links = sg.get("links") or []

        # 1) 把内部节点复制到顶层，rename id
        def _rename(node_id) -> str:
            if node_id == inputNode_id or node_id == outputNode_id:
                # sentinel 不真实存在，标记为 None
                return None
            return f"{prefix}{node_id}"

        # 同时记录每个 cloned 节点（按原 inner id 索引），便于后面回写 inputs[*].link
        cloned_by_inner_id: dict = {}
        for innode in inner_nodes:
            cloned = json.loads(json.dumps(innode))   # 深拷贝，免得改 widgets/inputs 影响原 def
            cloned["id"] = _rename(innode.get("id"))
            new_nodes.append(cloned)
            cloned_by_inner_id[innode.get("id")] = cloned

        # 内部 link id → 展平后的新 link id（用来重写 cloned 节点的 inputs[*].link）
        link_id_remap: dict = {}

        # 2) 内部 link 复制到顶层 link 列表
        for il in inner_links:
            if not isinstance(il, dict):
                continue
            inner_link_id = il.get("id")
            origin_id  = il.get("origin_id")
            origin_slot = il.get("origin_slot", 0)
            target_id  = il.get("target_id")
            target_slot = il.get("target_slot", 0)
            ltype = il.get("type") or ""

            # 情况 A：origin 是 inputNode → 外部 link 接到该 subgraph 实例的对应 slot
            if origin_id == inputNode_id:
                outer_src = None
                for ol in new_links:
                    if isinstance(ol, list) and len(ol) >= 5 and \
                       ol[3] == inst_id and ol[4] == origin_slot:
                        outer_src = (ol[1], ol[2])
                        drop_link_ids.add(ol[0])
                        break
                if outer_src is None:
                    # 外部没接 → 这个 input 用 widget 值；不创建 link
                    continue
                src_id, src_slot = outer_src
                new_id = next_link_id
                next_link_id += 1
                new_links.append([
                    new_id, src_id, src_slot,
                    _rename(target_id), target_slot, ltype,
                ])
                link_id_remap[inner_link_id] = new_id
                continue

            # 情况 B：target 是 outputNode → 外部 link 源自该 subgraph 实例的对应 slot
            if target_id == outputNode_id:
                for ol in new_links:
                    if isinstance(ol, list) and len(ol) >= 5 and \
                       ol[1] == inst_id and ol[2] == target_slot:
                        # 把外层 link 的 source 改成 (rename(origin_id), origin_slot)
                        ol_new_origin = _rename(origin_id)
                        idx = new_links.index(ol)
                        new_links[idx] = [
                            ol[0], ol_new_origin, origin_slot,
                            ol[3], ol[4], ltype,
                        ]
                continue

            # 情况 C：纯内部 link
            new_id = next_link_id
            next_link_id += 1
            new_links.append([
                new_id, _rename(origin_id), origin_slot,
                _rename(target_id), target_slot, ltype,
            ])
            link_id_remap[inner_link_id] = new_id

        # 2.5) 把每个 cloned 节点的 inputs[*].link 重写到新的 link id
        # 否则 _litegraph_to_api 会按旧 id 查 link_map 查不到 → "Required input is missing"
        for cloned in cloned_by_inner_id.values():
            for inp in (cloned.get("inputs") or []):
                lk = inp.get("link")
                if lk is None: continue
                if lk in link_id_remap:
                    inp["link"] = link_id_remap[lk]
                else:
                    # 没有对应（比如内部 link 是 origin=inputNode 但外面没接）→ 视为未连接
                    inp["link"] = None
            # outputs[*].links 留给 _litegraph_to_api 忽略（它只看 inputs）
            outs = cloned.get("outputs") or []
            for op in outs:
                new_lks = []
                for lk in (op.get("links") or []):
                    if lk in link_id_remap: new_lks.append(link_id_remap[lk])
                op["links"] = new_lks or None

        # 3) widget 分发：subgraph 实例的 widgets_values（或 inputs[i].widget）
        # 需要灌给"内部接 inputNode" 的对应节点的 widgets_values。
        # 实践中很多 Flux2 工作流 instance.widgets_values 是空——内部节点直接
        # 用默认值或者已有 widgets_values；不强制处理。
        inst_wvs = inst.get("widgets_values") or []
        if inst_wvs:
            # 每个外层 wv 对应一个 sg_inputs[i] (widget 类型)；
            # 内部接到 inputNode slot=i 的节点的对应 widget 写入
            for slot_idx, wv in enumerate(inst_wvs):
                # 找到内部哪个节点的 input slot 接到 inputNode 的 slot_idx
                target = None
                for il in inner_links:
                    if isinstance(il, dict) and \
                       il.get("origin_id") == inputNode_id and \
                       il.get("origin_slot") == slot_idx:
                        target = (il.get("target_id"), il.get("target_slot"))
                        break
                if target is None:
                    continue
                tgt_inner_id, tgt_inner_slot = target
                renamed = _rename(tgt_inner_id)
                # 找展平后的节点 + 写入 widgets_values
                for nn in new_nodes:
                    if nn.get("id") == renamed:
                        wvs = list(nn.get("widgets_values") or [])
                        while len(wvs) <= tgt_inner_slot:
                            wvs.append(None)
                        wvs[tgt_inner_slot] = wv
                        nn["widgets_values"] = wvs
                        break

    # 4) 删除被替换掉的外层 link
    final_links = [l for l in new_links if not (isinstance(l, list) and l and l[0] in drop_link_ids)]

    # 5) 删除已被展平的 subgraph 实例的"接到它"的外层 link 残留（safety）
    inst_ids = {n.get("id") for n in nodes if n.get("type") in sg_by_id}
    final_links = [
        l for l in final_links
        if not (isinstance(l, list) and len(l) >= 5
                and (l[1] in inst_ids or l[3] in inst_ids))
    ]

    out = dict(workflow)
    out["nodes"] = new_nodes
    out["links"] = final_links
    # 递归处理嵌套 subgraph
    if any(n.get("type") in sg_by_id for n in new_nodes):
        return _flatten_subgraphs(out)
    return out


def _litegraph_to_api(workflow: dict) -> dict:
    """
    Convert a ComfyUI LiteGraph (UI-save) workflow to API-prompt format.

    LiteGraph format has 'nodes' and 'links' arrays.
    API format is {node_id_str: {class_type, inputs, _meta}}.

    Handles the KSampler seed_control_mode extra widget by type-checking:
    if a widgets_values entry doesn't match the expected type of the current
    widget input, it is treated as a hidden control widget and skipped.

    Also resolves SetNode/GetNode teleport pairs (used in complex workflows
    to avoid long-distance wires) and bypassed nodes (mode==4).

    Pre-pass: flattens ComfyUI subgraphs (UUID-typed nodes), required for
    Flux.2 workflows.
    """
    # B1.1: 先展平所有 subgraph 实例，让后续逻辑不必关心 subgraph
    workflow   = _flatten_subgraphs(workflow)
    nodes      = workflow.get("nodes", [])
    links_list = workflow.get("links", [])

    # link_id -> [source_node_id_str, source_slot]
    link_map: dict = {}
    for lnk in links_list:
        link_id, src_node, src_slot = lnk[0], lnk[1], lnk[2]
        link_map[link_id] = [str(src_node), src_slot]

    # ── Handle bypassed nodes (LiteGraph mode == 4) ────────────────────────
    # Must run BEFORE SetNode/GetNode resolution so set_map sees resolved links.
    # A bypassed node passes its Nth output through its Nth input — but ONLY
    # when the input and output types match. ComfyUI's real bypass is type-aware:
    # e.g. GetImageSize takes IMAGE→INT (width/height/batch), so slot 0 input
    # IMAGE doesn't pass through to slot 0 output INT (would cause
    # "return_type_mismatch"). Consumer falls back to widget value instead.
    def _types_compat(a, b) -> bool:
        # 同类型或一边是通配 '*' 视为兼容
        if not a or not b: return False
        if a == '*' or b == '*': return True
        return str(a).upper() == str(b).upper()

    # Reroute (虚拟节点) 在概念上等同于 bypass：直接把 slot 0 input 透传到
    # slot 0 output。Reroute 的 input.type 通常是 '*'，所以 _types_compat 自然兼容。
    # 不处理的话，下游消费 Reroute 输出的节点会因为 link 指向被 skip 的虚拟节点
    # 而拿不到上游源 → "Required input is missing"。
    def _is_passthrough(node) -> bool:
        return node.get("mode") == 4 or node.get("type") == "Reroute"

    for _ in range(len(nodes)):
        changed = False
        for node in nodes:
            if not _is_passthrough(node):
                continue
            inputs_meta = node.get("inputs", [])
            inp_link_ids = [inp.get("link") for inp in inputs_meta]
            for slot_idx, out in enumerate(node.get("outputs", [])):
                if slot_idx >= len(inp_link_ids):
                    continue
                in_link_id  = inp_link_ids[slot_idx]
                if in_link_id is None:
                    continue
                in_type  = inputs_meta[slot_idx].get("type")
                out_type = out.get("type")
                if not _types_compat(in_type, out_type):
                    # 类型不匹配 → bypass 在这个 slot 不传透。链路里所有连出
                    # 这个 output 的 link 也要从 link_map 删掉，让下游 fallback 到 widget。
                    for out_link_id in (out.get("links") or []):
                        if out_link_id in link_map:
                            del link_map[out_link_id]
                            changed = True
                    continue
                passthrough = link_map.get(in_link_id)
                for out_link_id in (out.get("links") or []):
                    if out_link_id is not None and passthrough is not None:
                        if link_map.get(out_link_id) != passthrough:
                            link_map[out_link_id] = passthrough
                            changed = True
        if not changed:
            break

    # ── Resolve SetNode/GetNode teleport pairs ──────────────────────────────
    set_map: dict = {}  # name -> [src_node_id_str, src_slot]
    for node in nodes:
        if node.get("type") == "SetNode":
            name = (node.get("widgets_values") or [None])[0]
            inputs = node.get("inputs") or []
            if name and inputs:
                in_link_id = inputs[0].get("link")
                if in_link_id is not None and in_link_id in link_map:
                    set_map[name] = link_map[in_link_id]

    for node in nodes:
        if node.get("type") == "GetNode":
            name = (node.get("widgets_values") or [None])[0]
            source = set_map.get(name) if name else None
            if source is None:
                continue
            for out in node.get("outputs") or []:
                for out_link_id in (out.get("links") or []):
                    if out_link_id is not None:
                        link_map[out_link_id] = source

    # Nodes that exist only as LiteGraph helpers — skip them in API output.
    # PrimitiveNode is a legacy UI-only constant source: its widget value must be
    # inlined into downstream consumers (handled below via `primitive_values`).
    # Submitting it as a class_type makes ComfyUI 400 with "node not found".
    _VIRTUAL_TYPES = {"SetNode", "GetNode", "Note", "Reroute", "MarkdownNote",
                      "Fast Groups Bypasser (rgthree)", "PrimitiveNode"}

    # PrimitiveNode 节点 id (字符串) → 其常量值（widgets_values[0]）。下游消费者
    # 不再走 link_map，直接拿这个字面量塞进 api_inputs。
    primitive_values: dict = {}
    for node in nodes:
        if node.get("type") == "PrimitiveNode":
            wvs = node.get("widgets_values") or []
            if wvs:
                primitive_values[str(node.get("id"))] = wvs[0]

    # Input types that are purely UI widgets — never sent to ComfyUI API
    _UI_ONLY_TYPES = {"IMAGEUPLOAD", "AUDIOUPLOAD", "AUDIO_UI", "VIDEO_UI", "MASK_UI"}

    # Type checkers for widget → API value matching
    _type_ok = {
        "INT":     lambda v: isinstance(v, int) and not isinstance(v, bool),
        "FLOAT":   lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "STRING":  lambda v: isinstance(v, str),
        "COMBO":   lambda v: isinstance(v, str),
        "BOOLEAN": lambda v: isinstance(v, bool),
    }

    # Pre-compute the set of nodes that will land in the API. A link pointing
    # to a skipped node (bypassed or virtual) must be treated as "no link" so
    # the consumer falls back to its widget value — matches ComfyUI's behavior
    # for partially-bypassed nodes like GetImageSize (1 input / 3 outputs:
    # output slots 1 and 2 can't be passed through → consumer reads widget).
    alive_node_ids: set = set()
    for node in nodes:
        if node.get("mode") == 4:
            continue
        if node.get("type", "") in _VIRTUAL_TYPES:
            continue
        alive_node_ids.add(str(node.get("id")))

    api: dict = {}
    for node in nodes:
        # Skip bypassed and virtual helper nodes
        if node.get("mode") == 4:
            continue
        class_type = node.get("type", "")
        if class_type in _VIRTUAL_TYPES:
            continue

        node_id        = str(node["id"])
        inp_list       = node.get("inputs", [])
        widgets_values = node.get("widgets_values", [])
        title          = node.get("title", class_type)

        api_inputs: dict = {}
        wv_idx = 0

        for inp in inp_list:
            inp_name = inp.get("name", "")
            inp_type = inp.get("type", "")
            link_id  = inp.get("link")
            has_widget = "widget" in inp

            # Skip UI-only widget types — these are never real computational inputs
            if isinstance(inp_type, str) and inp_type in _UI_ONLY_TYPES:
                wv_idx += 1  # still need to advance past their widgets_values slot
                continue

            # Resolve the link — but only if it points to a node that survives
            # the bypass/virtual filter. Otherwise the consumer must fall back
            # to its widget value (else ComfyUI 400s on "validating inner node").
            resolved = None         # 形如 [node_id, slot] 的链接引用
            literal_value = None    # 来自 PrimitiveNode 的内联常量（取代链接）
            if link_id is not None and link_id in link_map:
                cand = link_map[link_id]
                src_id = cand[0]
                if src_id in primitive_values:
                    # PrimitiveNode → 把常量塞进 inputs，跳过 ComfyUI 端节点查找
                    literal_value = primitive_values[src_id]
                elif src_id in alive_node_ids:
                    resolved = cand

            if literal_value is not None:
                api_inputs[inp_name] = literal_value
                if has_widget and not isinstance(widgets_values, dict):
                    wv_idx += 1
                continue

            if resolved is not None:
                api_inputs[inp_name] = resolved
                # If this input has both a link AND a widget slot, still advance wv_idx
                # so that subsequent pure-widget inputs read the correct slot.
                if has_widget and not isinstance(widgets_values, dict):
                    wv_idx += 1
            elif has_widget:
                if isinstance(widgets_values, dict):
                    # Dict-style widgets_values (e.g. VHS_VideoCombine): key is input name
                    val = widgets_values.get(inp_name)
                    if val is not None:
                        api_inputs[inp_name] = val
                else:
                    checker = _type_ok.get(inp_type)
                    # Skip widgets_values entries that don't match expected type
                    # (e.g. KSampler's seed_control_mode "randomize" between seed and steps)
                    while wv_idx < len(widgets_values):
                        val = widgets_values[wv_idx]
                        wv_idx += 1
                        if val is None:
                            # None means a UI-only placeholder (e.g. audioUI, upload button)
                            break
                        if checker is None or checker(val):
                            api_inputs[inp_name] = val
                            break

        api[node_id] = {
            "class_type": class_type,
            "inputs": api_inputs,
            "_meta": {"title": title},
        }

    return api


# ── Workflow patching ──────────────────────────────────────────────────────────

def _patch_workflow(
    workflow: dict,
    positive: str,
    negative: str,
    seed: Optional[int],
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> dict:
    """
    Patch a ComfyUI API-format workflow with prompt, seed, and image size.

    Accepts both LiteGraph format (has 'nodes' key) and API format
    (dict of node_id -> node). LiteGraph format is auto-converted.

    Positive/negative detection order:
      1. Node title containing '正面'/'负面' (Chinese)
      2. Node title containing 'positive'/'negative' (case-insensitive)
      3. First / second CLIPTextEncode order fallback
    """
    import copy, random

    # Auto-convert LiteGraph format
    if "nodes" in workflow:
        workflow = _litegraph_to_api(workflow)

    w = copy.deepcopy(workflow)
    _seed = seed if seed is not None else random.randint(0, 2**31 - 1)

    # Pre-classify CLIPTextEncode nodes by title
    positive_node_ids: list = []
    negative_node_ids: list = []
    unclassified_clip: list = []

    for node_id, node in w.items():
        if node.get("class_type") != "CLIPTextEncode":
            continue
        title = (node.get("_meta") or {}).get("title", "").lower()
        if "正面" in title or "positive" in title:
            positive_node_ids.append(node_id)
        elif "负面" in title or "negative" in title:
            negative_node_ids.append(node_id)
        else:
            unclassified_clip.append(node_id)

    # Fallback: first unclassified = positive, second = negative
    if not positive_node_ids and unclassified_clip:
        positive_node_ids.append(unclassified_clip.pop(0))
    if not negative_node_ids and unclassified_clip:
        negative_node_ids.append(unclassified_clip.pop(0))

    for nid in positive_node_ids:
        w[nid]["inputs"]["text"] = positive
    for nid in negative_node_ids:
        w[nid]["inputs"]["text"] = negative

    # Patch each node
    for node_id, node in w.items():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})

        # Seed
        if class_type in ("KSampler", "KSamplerAdvanced"):
            if "seed" in inputs:       inputs["seed"]       = _seed
            if "noise_seed" in inputs: inputs["noise_seed"] = _seed
        if class_type == "RandomNoise":
            if "noise_seed" in inputs: inputs["noise_seed"] = _seed

        # Image size — covers SD1.5 / SDXL / SD3 / Hunyuan / Flux.2
        # Flux2Scheduler ALSO has width/height for resolution-dependent sigma scheduling;
        # must match the latent size or output will be miscalibrated.
        _SIZE_NODES = {
            "EmptySD3LatentImage", "EmptyLatentImage", "EmptyHunyuanLatentVideo",
            "EmptyFlux2LatentImage", "Flux2Scheduler",
        }
        if class_type in _SIZE_NODES:
            if width  and "width"  in inputs: inputs["width"]  = width
            if height and "height" in inputs: inputs["height"] = height

    return w
