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

import copy


def is_msr_workflow(workflow: dict) -> bool:
    """是否为 MSR 多图参考工作流（含 LiconMSR 节点即是）。"""
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not nodes:
        return False
    return any("LiconMSR" in str(n.get("type", "")) for n in nodes)


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
