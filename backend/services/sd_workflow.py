"""v1.4.4: Stable Diffusion 通用 t2i 工作流参数化 (sd_default_workflow.json)。

工作流 schema：
  CheckpointLoaderSimple(17) → LoraLoaderModelOnly(10) → ... (链式) → KSampler(20)
  CLIPTextEncode(2,3)          正面 / 负面
  EmptyLatentImage(6)          尺寸
  KSampler(20)                 步数 / CFG / 采样器 / 调度器

用户可调：
  - checkpoint name
  - 0..N 个 LoRA + 各自权重（多余的 LoRA 节点用 mode=4 跳过）
  - 正面 / 负面提示词
  - 宽 / 高
  - KSampler: steps / cfg / sampler_name / scheduler / seed
"""
from __future__ import annotations

import copy
from typing import Optional

import httpx


# 默认工作流节点 ID 映射（如果用户后期改 ID，可加 meta.json 覆盖；当前硬编码）
SD_NODES = {
    "checkpoint":  17,
    "positive":     2,
    "negative":     3,
    "ksampler":    20,
    "latent_size":  6,
    # LoraLoaderModelOnly 链：顺序固定，链头到链尾
    "lora_chain": [10, 11, 13, 12, 14, 15, 16],
}


def patch_sd_workflow(
    workflow: dict,
    *,
    checkpoint:      str = "",
    loras:           Optional[list[dict]] = None,
    positive_prompt: str = "",
    negative_prompt: str = "",
    width:           int = 0,
    height:          int = 0,
    seed:            Optional[int] = None,
    steps:           int = 0,
    cfg:             float = 0.0,
    sampler_name:    str = "",
    scheduler:       str = "",
) -> dict:
    """按 SD 参数原地补丁工作流（返回深拷贝）。

    loras: [{"name": "x.safetensors", "strength": 0.6}, ...]
      - 多余的 LoRA 节点设 mode=4（bypass），用 _litegraph_to_api 的链路穿透机制把
        model 链直接传到 KSampler，效果等同"不加载这个 LoRA"
      - 不够的（用户传 3 个、工作流有 7 槽）→ 余下 4 个 bypass
      - 用户传得过多（> 7）→ 截到 7，忽略多余
    """
    import random as _random
    wf = copy.deepcopy(workflow)
    nodes_by_id = {n["id"]: n for n in (wf.get("nodes") or [])}

    def _set_widget(node_id: int, idx: int, value):
        n = nodes_by_id.get(node_id)
        if n is None: return
        wv = n.get("widgets_values")
        if not isinstance(wv, list): return
        while len(wv) <= idx:
            wv.append(None)
        wv[idx] = value

    # 1) Checkpoint
    if checkpoint:
        _set_widget(SD_NODES["checkpoint"], 0, checkpoint)

    # 2) Positive / Negative prompt
    if positive_prompt:
        _set_widget(SD_NODES["positive"], 0, positive_prompt)
    if negative_prompt:
        _set_widget(SD_NODES["negative"], 0, negative_prompt)

    # 3) Image size
    if width and height:
        _set_widget(SD_NODES["latent_size"], 0, int(width))
        _set_widget(SD_NODES["latent_size"], 1, int(height))

    # 4) KSampler
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)
    _set_widget(SD_NODES["ksampler"], 0, int(seed))
    # widget[1] is control mode ('randomize' / 'fixed')；不动它
    if steps and steps > 0:
        _set_widget(SD_NODES["ksampler"], 2, int(steps))
    if cfg and cfg > 0:
        _set_widget(SD_NODES["ksampler"], 3, float(cfg))
    if sampler_name:
        _set_widget(SD_NODES["ksampler"], 4, sampler_name)
    if scheduler:
        _set_widget(SD_NODES["ksampler"], 5, scheduler)

    # 5) LoRA 链
    lora_list = list(loras or [])
    for i, node_id in enumerate(SD_NODES["lora_chain"]):
        node = nodes_by_id.get(node_id)
        if node is None: continue
        if i < len(lora_list):
            entry = lora_list[i] or {}
            name = (entry.get("name") or "").strip()
            strength = entry.get("strength")
            if name and name.lower() != "none" and (strength is None or float(strength) != 0):
                # 启用：写 name + strength
                _set_widget(node_id, 0, name)
                _set_widget(node_id, 1, float(strength if strength is not None else 1.0))
                node["mode"] = 0   # 显式 enable
                continue
        # 否则 bypass（mode=4，链路穿透机制会让 model 链跳过这一节点）
        node["mode"] = 4
    return wf


# ── 列举 ComfyUI 可用模型 ────────────────────────────────────────────────────


async def fetch_sd_model_info(comfyui_url: str) -> dict:
    """查 ComfyUI /object_info，提取 SD 工作流相关的可选值。"""
    url = comfyui_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{url}/object_info")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {
            "checkpoints": [], "loras": [],
            "samplers":    [], "schedulers": [],
            "error": str(e),
        }

    def _extract(node_class: str, input_name: str) -> list:
        """提取节点 input 的合法枚举值。"""
        node = (data or {}).get(node_class) or {}
        inputs = (node.get("input") or {}).get("required") or {}
        # ComfyUI 格式：input[name] = [type_or_enum_list, optional_opts]
        spec = inputs.get(input_name)
        if not spec:
            return []
        first = spec[0] if isinstance(spec, list) else None
        return first if isinstance(first, list) else []

    checkpoints = _extract("CheckpointLoaderSimple", "ckpt_name")
    loras       = _extract("LoraLoaderModelOnly",  "lora_name")
    samplers    = _extract("KSampler",              "sampler_name")
    schedulers  = _extract("KSampler",              "scheduler")
    return {
        "checkpoints": sorted(checkpoints),
        "loras":       sorted(loras),
        "samplers":    samplers,         # 顺序保留 ComfyUI 自己的（流行度排序）
        "schedulers":  schedulers,
    }
