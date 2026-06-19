"""v1.6.2: 多引擎视频槽 —— 每种生成方式给每个分镜各存【独立一份】，互不覆盖；
合并时按分镜所选「来源」挑选对应那份，实现跨引擎混合合成。

槽（kind）：
  ltx       —— LTX/i2v ComfyUI 默认（旧默认槽，向后兼容）  <scene>.mp4 / videos.json / asset 'video'
  msr       —— 多图参考 (ComfyUI)                          <scene>.msr.mp4 / videos_msr.json / 'video_msr'
  slideshow —— 图片放映 (ffmpeg)                            <scene>.slideshow.mp4 / videos_slideshow.json / 'video_slideshow'
  seedance  —— 火山引擎 Seedance (云端)                     <scene>.seedance.mp4 / videos_seedance.json / 'video_seedance'
"""

VIDEO_SLOTS: dict[str, dict] = {
    "ltx":       {"suffix": ".mp4",            "index": "videos.json",           "asset": "video"},
    "msr":       {"suffix": ".msr.mp4",        "index": "videos_msr.json",       "asset": "video_msr"},
    "slideshow": {"suffix": ".slideshow.mp4",  "index": "videos_slideshow.json", "asset": "video_slideshow"},
    "seedance":  {"suffix": ".seedance.mp4",   "index": "videos_seedance.json",  "asset": "video_seedance"},
}
DEFAULT_SLOT = "ltx"
SLOT_KINDS = tuple(VIDEO_SLOTS.keys())


def norm_kind(kind: str) -> str:
    """把传入的来源名归一到合法 kind；未知 → ltx。'old'/'normal'/'' 视为 ltx。"""
    k = (kind or "").strip().lower()
    if k in ("", "old", "normal", "default", "comfyui", "i2v"):
        return "ltx"
    return k if k in VIDEO_SLOTS else "ltx"


def slot_filename(scene_id: str, kind: str) -> str:
    return f"{scene_id}{VIDEO_SLOTS[norm_kind(kind)]['suffix']}"


def slot_index_name(kind: str) -> str:
    return VIDEO_SLOTS[norm_kind(kind)]["index"]


def slot_asset(kind: str) -> str:
    return VIDEO_SLOTS[norm_kind(kind)]["asset"]


def kind_query(kind: str) -> str:
    """video-file 端点的 ?kind= 查询串（ltx 默认槽不带参数，向后兼容旧 URL）。"""
    k = norm_kind(kind)
    return "" if k == "ltx" else f"?kind={k}"
