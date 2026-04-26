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

async def list_workflows(cfg: ImageEngineConfig) -> list[str]:
    """Return names of saved workflows.

    Priority:
      1. Local filesystem (cfg.workflow_dir) — fastest and version-independent.
      2. ComfyUI /api/userdata?dir=workflows — fallback for remote setups.
    """
    # ── 1. Local directory ────────────────────────────────────────────────────
    if cfg.workflow_dir:
        from pathlib import Path as _Path
        d = _Path(cfg.workflow_dir)
        if d.is_dir():
            return sorted(p.stem for p in d.glob("*.json"))

    # ── 2. ComfyUI API ────────────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            r = await client.get(f"{cfg.comfyui_url}/api/userdata", params={"dir": "workflows"})
            if r.status_code == 200:
                items = r.json()
                return [Path(p).stem for p in items if str(p).endswith(".json")]
        except Exception:
            pass
    return []


async def get_workflow_json(cfg: ImageEngineConfig, workflow_name: str) -> Optional[dict]:
    """Download a saved workflow JSON by name.

    Priority:
      1. Local filesystem (cfg.workflow_dir) — reads file directly.
      2. ComfyUI /api/userdata/{path} — HTTP fallback.
    """
    import json as _json

    # ── 1. Local directory ────────────────────────────────────────────────────
    if cfg.workflow_dir:
        from pathlib import Path as _Path
        p = _Path(cfg.workflow_dir) / f"{workflow_name}.json"
        if p.is_file():
            try:
                return _json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass

    # ── 2. ComfyUI API ────────────────────────────────────────────────────────
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
) -> AsyncGenerator[dict, None]:
    """
    Queue a ComfyUI prompt and stream progress events.

    Yields dicts:
      {"event": "queued",     "prompt_id": str}
      {"event": "progress",   "value": int, "max": int}
      {"event": "completed",  "images": [{"filename": str, "data": str (base64)}]}
      {"event": "error",      "message": str}
    """
    client_id = str(uuid.uuid4())

    # Patch workflow prompts
    patched = _patch_workflow(workflow, positive_prompt, negative_prompt, seed, width, height)

    # Queue the prompt
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(
                f"{cfg.comfyui_url}/prompt",
                json={"prompt": patched, "client_id": client_id},
            )
            r.raise_for_status()
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


# ── LiteGraph → API format converter ──────────────────────────────────────────

def _litegraph_to_api(workflow: dict) -> dict:
    """
    Convert a ComfyUI LiteGraph (UI-save) workflow to API-prompt format.

    LiteGraph format has 'nodes' and 'links' arrays.
    API format is {node_id_str: {class_type, inputs, _meta}}.

    Handles the KSampler seed_control_mode extra widget by type-checking:
    if a widgets_values entry doesn't match the expected type of the current
    widget input, it is treated as a hidden control widget and skipped.
    """
    nodes      = workflow.get("nodes", [])
    links_list = workflow.get("links", [])

    # link_id -> [source_node_id_str, source_slot]
    link_map: dict = {}
    for lnk in links_list:
        link_id, src_node, src_slot = lnk[0], lnk[1], lnk[2]
        link_map[link_id] = [str(src_node), src_slot]

    # ── Handle bypassed nodes (LiteGraph mode == 4) ────────────────────────
    # A bypassed node passes its Nth output through its Nth input.
    # Re-route every downstream link that came from a bypassed node's output
    # to instead come from that node's corresponding input.
    # Multiple passes handles chains of bypassed nodes.
    for _ in range(len(nodes)):
        changed = False
        for node in nodes:
            if node.get("mode") != 4:
                continue
            inp_link_ids = [inp.get("link") for inp in node.get("inputs", [])]
            for slot_idx, out in enumerate(node.get("outputs", [])):
                if slot_idx >= len(inp_link_ids):
                    continue
                in_link_id  = inp_link_ids[slot_idx]
                passthrough = link_map.get(in_link_id) if in_link_id is not None else None
                for out_link_id in (out.get("links") or []):
                    if out_link_id is not None and passthrough is not None:
                        if link_map.get(out_link_id) != passthrough:
                            link_map[out_link_id] = passthrough
                            changed = True
        if not changed:
            break

    # Type checkers for widget → API value matching
    _type_ok = {
        "INT":     lambda v: isinstance(v, int) and not isinstance(v, bool),
        "FLOAT":   lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "STRING":  lambda v: isinstance(v, str),
        "COMBO":   lambda v: isinstance(v, str),
        "BOOLEAN": lambda v: isinstance(v, bool),
    }

    api: dict = {}
    for node in nodes:
        # Skip bypassed nodes — they are transparently re-routed above
        if node.get("mode") == 4:
            continue
        node_id        = str(node["id"])
        class_type     = node.get("type", "")
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

            if link_id is not None:
                if link_id in link_map:
                    api_inputs[inp_name] = link_map[link_id]
            elif has_widget:
                checker = _type_ok.get(inp_type)
                # Skip widgets_values entries that don't match expected type
                # (e.g. KSampler's seed_control_mode "randomize" between seed and steps)
                while wv_idx < len(widgets_values):
                    val = widgets_values[wv_idx]
                    wv_idx += 1
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

        # Image size
        if class_type in ("EmptySD3LatentImage", "EmptyLatentImage", "EmptyHunyuanLatentVideo"):
            if width  and "width"  in inputs: inputs["width"]  = width
            if height and "height" in inputs: inputs["height"] = height

    return w
