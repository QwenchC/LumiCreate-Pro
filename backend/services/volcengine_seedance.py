"""v1.4.10 火山引擎 Seedance 2.0 视频生成 driver。

云端 API 通路，给"不想 / 不能跑 LTX-2.3"的用户用。与现有
`ltx2video.generate_video()` 暴露**同样的 SSE 事件流**（queued → progress →
completed / error），所以 router 层只需要在 `engine_type` 上做一次 dispatch，
下游 `record_asset` / `videos.json` / merge / 字幕 / SFX 全部无感复用。

火山方舟 (Volcengine Ark) 视频生成 API 参考：
    https://www.volcengine.com/docs/82379/1520757

实现按照 Volcengine Ark 通用约定（Bearer token + 异步 task 模式）写：
    POST  {base_url}/contents/generations/tasks      —— 创建任务
    GET   {base_url}/contents/generations/tasks/{id} —— 查询任务

接口路径前缀来自 settings.video_engine.volcengine_base_url（默认
`https://ark.cn-beijing.volces.com/api/v3`），如果实际不一样，用户在设置页
改一下即可，无需改代码。模型 ID 同理走 settings 字段。

请求体最小集（按 Ark 通用 JSON 约定，本地实现以可配置为先）：
    {
      "model": <endpoint_id_or_alias>,
      "content": [
        {"type": "text", "text": "<prompt>"},
        {"type": "image_url", "image_url": {"url": "<base64_or_url>"}}
      ]
    }

如果用户实际官方文档字段名 / 结构不同，本模块向上抛出原始 4xx body 让 router
透传给前端 —— 用户能立即看到"是哪个字段被拒"，按设置页改后重试不浪费配额。
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import AsyncIterator, Optional

import httpx


# ── 错误识别 ──────────────────────────────────────────────────────────────────

_VRAM_OFFLOAD_SIG = ""   # 云端无 VRAM 问题；保留占位避免 router 引用断


# ── 连通性 + 鉴权测试 ──────────────────────────────────────────────────────────


async def test_seedance_connection(base_url: str, api_key: str) -> tuple[bool, str]:
    """快速验证 base_url + api_key 能正常握手。

    跑一次 list-tasks（GET tasks 列表）的最小 limit 调用：
      - 200 → 鉴权 + 端点都对
      - 401 / 403 → API key 错
      - 404 → base_url 不对
      - 其它 → 透传错误体

    返回 (ok, message)。
    """
    if not base_url:
        return False, "未配置 volcengine_base_url"
    if not api_key:
        return False, "未配置 volcengine_api_key（在火山方舟控制台获取 ARK_API_KEY）"

    url = f"{base_url.rstrip('/')}/contents/generations/tasks?page_num=1&page_size=1"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=headers)
        if r.status_code == 200:
            return True, "鉴权通过"
        if r.status_code in (401, 403):
            return False, f"鉴权失败（HTTP {r.status_code}）：{_short_err(r)}"
        if r.status_code == 404:
            return False, f"端点未找到（HTTP 404）：检查 volcengine_base_url 是否正确：{base_url}"
        return False, f"HTTP {r.status_code}：{_short_err(r)}"
    except httpx.HTTPError as e:
        return False, f"连接失败：{e}"


def _short_err(r: httpx.Response) -> str:
    try:
        j = r.json()
        # Ark 错误常见形态：{"error": {"code": "...", "message": "..."}}
        if isinstance(j, dict):
            err = j.get("error")
            if isinstance(err, dict):
                return f"{err.get('code', '')} {err.get('message', '')}".strip()
            return json.dumps(j, ensure_ascii=False)[:400]
        return str(j)[:400]
    except Exception:
        return (r.text or "")[:400]


# ── 任务创建 / 查询 / 视频下载 ──────────────────────────────────────────────────


def _build_content_payload(
    prompt: str,
    *,
    first_frame_b64: str = "",
    last_frame_b64:  str = "",
    use_image:       bool = True,
) -> list[dict]:
    """组装 Ark 视频生成的 `content` 数组。

    按官方文档 v1.4.10+：
      - text：纯提示词文本，**不再贴 --hints**（生成参数走 request body 强校验）
      - image_url.role：图生视频-首帧 → 'first_frame'（或省略）；
        图生视频-首尾帧 → 'first_frame' + 'last_frame' 两张
    """
    parts: list[dict] = [{"type": "text", "text": prompt or ""}]
    if not use_image:
        return parts
    # 双图：必须同时给 role，文档约定 "图生视频-首尾帧" 场景 role 必填
    if first_frame_b64 and last_frame_b64:
        parts.append({
            "type": "image_url",
            "image_url": {"url": _ensure_data_url(first_frame_b64)},
            "role": "first_frame",
        })
        parts.append({
            "type": "image_url",
            "image_url": {"url": _ensure_data_url(last_frame_b64)},
            "role": "last_frame",
        })
    elif first_frame_b64:
        # 单图：文档允许省略 role；显式 first_frame 更稳
        parts.append({
            "type": "image_url",
            "image_url": {"url": _ensure_data_url(first_frame_b64)},
            "role": "first_frame",
        })
    return parts


def _ensure_data_url(image_b64: str) -> str:
    """图片可能传纯 base64 / data:URL / http(s) URL。统一成 Ark 接受的 data URL。"""
    s = (image_b64 or "").strip()
    if not s:
        return s
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("data:"):
        return s
    # 假设 PNG 兜底；jpg/webp 浏览器 / Ark 通常都能识别
    return f"data:image/png;base64,{s}"


async def _post_create_task(
    base_url:        str,
    api_key:         str, *,
    model_id:        str,
    content:         list[dict],
    resolution:      str = "720p",
    duration:        int = 5,
    ratio:           str = "adaptive",
    seed:            Optional[int] = None,
    camera_fixed:    bool = False,
    watermark:       bool = False,
    generate_audio:  bool = True,
) -> tuple[Optional[str], str]:
    """POST 创建任务，返回 (task_id, raw_error_msg)。

    v1.4.10 文档对齐：新方式（推荐）把 resolution / ratio / duration / seed /
    camera_fixed / watermark / generate_audio 直接放 request body，**强校验**。
    """
    url = f"{base_url.rstrip('/')}/contents/generations/tasks"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    body: dict = {
        "model":   model_id,
        "content": content,
    }
    # 生成参数（新方式，request body 直传）
    if resolution:           body["resolution"]   = resolution
    if ratio:                body["ratio"]        = ratio
    if duration:             body["duration"]     = int(duration)
    if seed is not None and int(seed) >= 0:
        body["seed"] = int(seed)
    if camera_fixed:         body["camera_fixed"] = True
    if watermark:            body["watermark"]    = True
    # generate_audio 默认 true（文档默认），漫剧 reading 模式建议设 false，
    # 因为我们的 TTS 已经独立产出音频，后续 ffmpeg 合成
    body["generate_audio"] = bool(generate_audio)
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=body)
        if r.status_code in (200, 201, 202):
            j = r.json()
            # 文档明确：响应顶层 `id` 字段即任务 ID
            task_id = j.get("id") or j.get("task_id") or (j.get("data") or {}).get("id")
            if not task_id:
                return None, f"未识别 task id（响应：{json.dumps(j, ensure_ascii=False)[:300]}）"
            return str(task_id), ""
        return None, f"HTTP {r.status_code}：{_short_err(r)}"
    except httpx.HTTPError as e:
        return None, f"请求失败：{e}"


async def _get_task_status(
    base_url: str, api_key: str, task_id: str,
) -> tuple[str, Optional[str], str]:
    """GET 单个任务，返回 (status, video_url | None, raw_error_msg)。
    status ∈ queued / running / succeeded / failed / cancelled
    （不同后端用字差别可能存在；本函数把常见同义词收敛到这 5 个）。"""
    url = f"{base_url.rstrip('/')}/contents/generations/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers)
    except httpx.HTTPError as e:
        return "failed", None, f"轮询失败：{e}"
    if r.status_code != 200:
        return "failed", None, f"HTTP {r.status_code}：{_short_err(r)}"
    j = r.json()
    raw_status = (j.get("status") or (j.get("data") or {}).get("status") or "").lower()
    status_map = {
        "queued": "queued", "pending": "queued", "waiting": "queued",
        "running": "running", "processing": "running", "in_progress": "running",
        "succeeded": "succeeded", "success": "succeeded", "completed": "succeeded",
        "failed": "failed", "error": "failed",
        "cancelled": "cancelled", "canceled": "cancelled",
    }
    status = status_map.get(raw_status, raw_status or "running")
    # 视频 URL 常见位置：content.video_url / content.url / data.video.url / output.video_url
    video_url = (
        ((j.get("content") or {}).get("video_url"))
        or ((j.get("content") or {}).get("url"))
        or ((j.get("data") or {}).get("video_url"))
        or (((j.get("data") or {}).get("video") or {}).get("url"))
        or ((j.get("output") or {}).get("video_url"))
    )
    err_msg = ""
    if status == "failed":
        err_msg = (j.get("error") or {}).get("message") or json.dumps(j, ensure_ascii=False)[:300]
    return status, video_url, err_msg


async def _download_video(url: str) -> bytes:
    """从 Ark 返回的视频 URL 拉 mp4 字节。"""
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


# ── 主 driver（与 ltx2video.generate_video 同 SSE 事件 schema）────────────────


async def generate_video_seedance(
    *,
    base_url:        str,
    api_key:         str,
    model_id:        str,
    first_frame_b64: str = "",
    last_frame_b64:  str = "",
    positive_prompt: str = "",
    duration_secs:   int = 5,
    resolution:      str = "720p",
    ratio:           str = "adaptive",
    use_image:       bool = True,
    generate_audio:  bool = False,   # 漫剧 reading：TTS 独立产出 → 默认 false
    watermark:       bool = False,
    camera_fixed:    bool = False,
    seed:            Optional[int] = None,
    poll_interval:   int = 5,
    poll_timeout:    int = 600,
    scene_id:        str = "",
) -> AsyncIterator[dict]:
    """异步迭代器：yields {"event": "queued"|"progress"|"completed"|"error", ...}。

    与 ltx2video.generate_video 同 schema，router 不需要分辨引擎：
      - "queued"    {message}
      - "progress"  {pct, message}
      - "completed" {video: base64 mp4}    ← router 会把 base64 落到 video/{sid}.mp4
      - "error"     {message}
    """
    # 0) 校验
    if not api_key:
        yield {"event": "error", "message": "火山引擎未配置 API Key", "scene_id": scene_id}
        return
    if not model_id:
        yield {"event": "error",
               "message": "火山引擎未配置模型 ID（请在设置页填入 endpoint ID 或模型别名）",
               "scene_id": scene_id}
        return

    yield {"event": "queued", "message": "提交火山引擎任务…", "scene_id": scene_id}

    # 1) 创建任务
    content = _build_content_payload(
        positive_prompt,
        first_frame_b64=first_frame_b64,
        last_frame_b64=last_frame_b64,
        use_image=use_image,
    )
    task_id, err = await _post_create_task(
        base_url, api_key, model_id=model_id, content=content,
        resolution=resolution, duration=duration_secs, ratio=ratio,
        seed=seed, camera_fixed=camera_fixed, watermark=watermark,
        generate_audio=generate_audio,
    )
    if err or not task_id:
        yield {"event": "error",
               "message": f"创建任务失败：{err}",
               "scene_id": scene_id}
        return

    yield {"event": "progress", "pct": 5,
           "message": f"任务已创建：{task_id}", "scene_id": scene_id}

    # 2) 轮询
    started = time.monotonic()
    last_status = ""
    while True:
        if time.monotonic() - started > poll_timeout:
            yield {"event": "error",
                   "message": f"轮询超时（>{poll_timeout}s），task_id={task_id}",
                   "scene_id": scene_id}
            return
        await asyncio.sleep(max(1, poll_interval))
        status, video_url, err_msg = await _get_task_status(base_url, api_key, task_id)
        if status != last_status:
            yield {"event": "progress",
                   "pct": {"queued": 10, "running": 50,
                            "succeeded": 95, "failed": 0,
                            "cancelled": 0}.get(status, 30),
                   "message": f"任务状态：{status}",
                   "scene_id": scene_id}
            last_status = status
        if status == "succeeded":
            if not video_url:
                yield {"event": "error",
                       "message": "succeeded 但响应里没拿到视频 URL（设置页可能需要调端点字段映射）",
                       "scene_id": scene_id}
                return
            try:
                blob = await _download_video(video_url)
            except Exception as e:
                yield {"event": "error",
                       "message": f"下载视频失败：{e}",
                       "scene_id": scene_id}
                return
            yield {"event": "completed",
                   "video": base64.b64encode(blob).decode("ascii"),
                   "scene_id": scene_id}
            return
        if status in ("failed", "cancelled"):
            yield {"event": "error",
                   "message": f"任务 {status}：{err_msg or '未知原因'}",
                   "scene_id": scene_id}
            return
        # 继续轮询
