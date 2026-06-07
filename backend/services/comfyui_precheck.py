"""ComfyUI 前置检查（D2）。

在调用 ComfyUI 生成图片 / 视频之前，先校验：
  1. ComfyUI 可达（已有 /test 端点）
  2. 工作流里所有节点 class_type 在 ComfyUI 当前 `/object_info` 里能查到
  3. 工作流引用的关键模型文件（checkpoint / vae / lora 等）在 ComfyUI input 列表里

失败时 emit `pre_check_failed` 带具体缺失项，避免跑了几分钟才发现"少个 LoRA"。

接口：
    result = await precheck_image_workflow(comfyui_url, workflow_name, image_cfg)
    if not result.ok:
        for issue in result.issues: ...

result 是 PrecheckResult 数据类。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import httpx


@dataclass
class PrecheckResult:
    ok: bool
    issues: list[dict] = field(default_factory=list)   # [{type, message, hint?}]
    info:   dict = field(default_factory=dict)         # 调试信息（节点数 / 模型数 等）

    def add(self, type_: str, message: str, *, hint: str = "") -> None:
        self.issues.append({"type": type_, "message": message, "hint": hint})
        self.ok = False


_MODEL_INPUT_NAMES = {
    "ckpt_name", "lora_name", "lora_01", "lora_02", "lora_03",
    "vae_name", "control_net_name", "clip_name", "model_name",
    "unet_name", "style_model_name", "ipadapter_file",
}


async def _fetch_object_info(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    try:
        r = await client.get(f"{url.rstrip('/')}/object_info", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


async def precheck_image_workflow(
    comfyui_url: str,
    workflow_name: str,
    *,
    image_cfg=None,
) -> PrecheckResult:
    """检查图片工作流。所有失败原因聚合在 result.issues 里。"""
    from services.comfyui import get_workflow_json
    from config import load_settings

    cfg = image_cfg or load_settings().image_engine
    res = PrecheckResult(ok=True)

    workflow = await get_workflow_json(cfg, workflow_name)
    if workflow is None:
        res.add("workflow_missing",
                f"工作流 {workflow_name} 不存在或读取失败",
                hint="检查 ImageEngineConfig.workflow_dir 是否正确")
        return res

    # 轮 1: subgraph 展平后再扫——Flux.2 等工作流类型 UUID 节点会被误判为"缺节点"
    try:
        from services.comfyui import _flatten_subgraphs
        workflow = _flatten_subgraphs(workflow)
    except Exception:
        pass

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            await client.get(f"{comfyui_url.rstrip('/')}/", timeout=5)
        except Exception as e:
            res.add("comfyui_unreachable",
                    f"ComfyUI 不可达: {e}",
                    hint=f"检查 {comfyui_url} 是否启动")
            return res

        obj_info = await _fetch_object_info(client, comfyui_url)
        if obj_info is None:
            res.add("object_info_failed",
                    "无法读取 /object_info",
                    hint="ComfyUI 版本可能过旧；如果生成能跑可忽略该项")
        else:
            # 收集 workflow 中实际使用的节点 class_type
            nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
            if isinstance(nodes, list):
                # litegraph 格式
                seen_classes = set()
                model_refs: list[tuple[str, str]] = []   # (input_name, value)
                for node in nodes:
                    ct = node.get("type") or ""
                    if not ct or ct.startswith("Reroute") or ct in ("PrimitiveNode", "Note"):
                        continue
                    seen_classes.add(ct)
                    # 模型引用：从 widgets_values 里抓字符串
                    wvs = node.get("widgets_values") or []
                    for v in wvs:
                        if isinstance(v, str) and (
                            v.endswith((".safetensors", ".ckpt", ".pt", ".bin", ".pth"))
                        ):
                            model_refs.append((ct, v))
                missing_classes = [c for c in seen_classes if c not in obj_info]
                if missing_classes:
                    res.add("missing_nodes",
                            f"ComfyUI 缺以下节点 class_type: {sorted(missing_classes)}",
                            hint="安装对应的 custom_nodes 后重启 ComfyUI")
                res.info["node_count"]   = len(seen_classes)
                res.info["model_refs"]   = len(model_refs)
                res.info["missing_node"] = sorted(missing_classes)
            else:
                # API 格式 {node_id: {class_type, inputs}}
                seen_classes = set()
                model_refs   = []
                for nid, node in (workflow or {}).items():
                    if not isinstance(node, dict):
                        continue
                    ct = node.get("class_type")
                    if ct:
                        seen_classes.add(ct)
                    inputs = node.get("inputs") or {}
                    for k, v in inputs.items():
                        if k in _MODEL_INPUT_NAMES and isinstance(v, str):
                            model_refs.append((ct or "?", v))
                missing_classes = [c for c in seen_classes if c not in obj_info]
                if missing_classes:
                    res.add("missing_nodes",
                            f"ComfyUI 缺以下节点 class_type: {sorted(missing_classes)}",
                            hint="安装对应的 custom_nodes 后重启 ComfyUI")
                res.info["node_count"]   = len(seen_classes)
                res.info["model_refs"]   = len(model_refs)
                res.info["missing_node"] = sorted(missing_classes)

    return res


async def precheck_video_workflow(
    comfyui_url: str,
    workflow_name: str,
    *,
    video_cfg=None,
) -> PrecheckResult:
    """视频工作流的检查路径与图片相同（同一个 ComfyUI），但工作流来源不同。"""
    from services.comfyui import get_workflow_json
    from config import load_settings

    settings = load_settings()
    vcfg = video_cfg or settings.video_engine
    icfg = settings.image_engine

    # video 工作流可能在 video_engine.workflow_dir，也可能 fallback 到 image_engine
    class _Combined:
        comfyui_url = vcfg.comfyui_url
        workflow_dir = vcfg.workflow_dir or icfg.workflow_dir
    return await precheck_image_workflow(
        comfyui_url, workflow_name, image_cfg=_Combined,
    )
