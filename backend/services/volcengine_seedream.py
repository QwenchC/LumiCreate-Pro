"""v1.4.11+ 火山方舟 Seedream 图片生成驱动。

按官方文档（https://www.volcengine.com/docs/82379/1541523）实现。
Ark 图片生成走 OpenAI-compatible 风格的同步 POST：
    POST {base_url}/images/generations
    Authorization: Bearer ARK_API_KEY
    {
      "model": "doubao-seedream-5-0-260128",   # 或 endpoint id
      "prompt": "...",
      "size": "1024x1024",                     # 字符串档位
      "response_format": "url" | "b64_json",
      "seed": 12345,                           # 可选
      "n": 1,
    }

响应：
    {"data": [{"url": "https://..."}]} 或 {"data": [{"b64_json": "..."}]}

为了和 ComfyUI / Pollinations 驱动保持事件 schema 一致，本模块包成同样的
SSE 事件流：queued → progress(伪进度) → completed → error，下游
record_asset / image_engine.py 已经的处理逻辑不需要改。
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import AsyncGenerator, Optional

import httpx


async def test_seedream_connection(base_url: str, api_key: str) -> tuple[bool, str]:
    """快速验证 base_url + api_key 能正常握手。
    没有 GET /images list 端点，用最廉价的 POST + 错误 model 探活
    （400 才是真"能联通"，401/403 是 key 错，404 是 URL 错）。"""
    if not base_url:
        return False, "未配置 seedream_base_url"
    if not api_key:
        return False, "未配置 seedream_api_key（火山方舟控制台 → API Key 管理）"
    url = f"{base_url.rstrip('/')}/images/generations"
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}
    body = {"model": "__test_probe__", "prompt": "probe", "size": "512x512", "n": 1}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, headers=headers, json=body)
        if r.status_code == 401:
            return False, "鉴权失败：API Key 无效或过期"
        if r.status_code == 403:
            return False, "鉴权失败：权限不足或模型未开通"
        if r.status_code == 404:
            return False, f"端点未找到：检查 base_url 是否正确：{base_url}"
        if r.status_code in (400, 422):
            # 我们故意用了假模型，400/422 说明端点可达 + 鉴权过了
            return True, "端点可达 + 鉴权通过（请在主表单填正确模型 ID）"
        if r.status_code in (200, 201):
            return True, "测试请求意外成功（端点正常）"
        return False, f"HTTP {r.status_code}：{_short_err(r)}"
    except httpx.HTTPError as e:
        return False, f"连接失败：{e}"


def _short_err(r: httpx.Response) -> str:
    try:
        j = r.json()
        if isinstance(j, dict):
            err = j.get("error")
            if isinstance(err, dict):
                return f"{err.get('code', '')} {err.get('message', '')}".strip()
            return json.dumps(j, ensure_ascii=False)[:400]
        return str(j)[:400]
    except Exception:
        return (r.text or "")[:400]


# ── 主 driver ─────────────────────────────────────────────────────────────────


async def generate_image_seedream(
    *,
    base_url:         str,
    api_key:          str,
    model:            str,
    prompt:           str,
    width:            int = 1024,
    height:           int = 1024,
    seed:             Optional[int] = None,
    response_format:  str = "url",
    timeout:          int = 180,
) -> AsyncGenerator[dict, None]:
    """异步迭代器：与 ComfyUI/Pollinations 驱动同 schema：
      queued / progress / completed (image: base64 png) / error
    """
    # 0) 校验
    if not api_key:
        yield {"event": "error", "message": "火山引擎未配置 API Key"}
        return
    if not model:
        yield {"event": "error", "message": "火山引擎未配置 Seedream 模型 ID"}
        return
    if not prompt:
        yield {"event": "error", "message": "提示词为空"}
        return

    yield {"event": "queued", "message": "提交 Seedream 任务…"}

    # 1) 伪进度 ticker（与 Pollinations 驱动一致：用户体感"在跑"）
    progress_task: asyncio.Task | None = None
    progress_evt_queue: asyncio.Queue[dict] = asyncio.Queue()

    async def _tick():
        pct = 5
        while True:
            await asyncio.sleep(2)
            pct = min(pct + 7, 90)
            await progress_evt_queue.put({"event": "progress", "pct": pct,
                                           "message": "Seedream 渲染中…"})

    progress_task = asyncio.create_task(_tick())

    # 2) 真请求
    url = f"{base_url.rstrip('/')}/images/generations"
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}
    # size 用字符串档位（文档常用 1024x1024 / 1024x576 / 720x1280…）
    size = f"{int(width)}x{int(height)}"
    body: dict = {
        "model":  model,
        "prompt": prompt,
        "size":   size,
        "n":      1,
        "response_format": response_format if response_format in ("url", "b64_json") else "url",
    }
    if seed is not None and int(seed) >= 0:
        body["seed"] = int(seed)

    async def _do_request() -> tuple[Optional[dict], str]:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, headers=headers, json=body)
            if r.status_code in (200, 201):
                return r.json(), ""
            return None, f"HTTP {r.status_code}：{_short_err(r)}"
        except httpx.HTTPError as e:
            return None, f"请求失败：{e}"

    req_task = asyncio.create_task(_do_request())

    # 3) 在 req 跑的时候持续吐 progress；req 完成时跳出
    while not req_task.done():
        try:
            evt = await asyncio.wait_for(progress_evt_queue.get(), timeout=0.5)
            yield evt
        except asyncio.TimeoutError:
            continue

    progress_task.cancel()

    j, err = req_task.result()
    if err or j is None:
        yield {"event": "error", "message": err or "未知错误"}
        return

    # 4) 解析 data[0] —— 兼容 url / b64_json
    data = (j.get("data") or [])
    if not data:
        yield {"event": "error",
               "message": f"响应无 data 字段：{json.dumps(j, ensure_ascii=False)[:300]}"}
        return
    item = data[0]
    img_b64 = ""
    if "b64_json" in item and item["b64_json"]:
        img_b64 = item["b64_json"]
    elif "url" in item and item["url"]:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                ir = await client.get(item["url"])
                ir.raise_for_status()
                img_b64 = base64.b64encode(ir.content).decode("ascii")
        except Exception as e:
            yield {"event": "error", "message": f"下载图片失败：{e}"}
            return
    if not img_b64:
        yield {"event": "error", "message": "响应里没拿到图片"}
        return

    # 对齐 ComfyUI / Pollinations 驱动事件 schema —— images: [{filename, data, type}]
    # 这样下游 image_engine.py 的批量 / 单图 SSE 处理逻辑不需要改
    filename = f"seedream_{seed if seed is not None else 'random'}.png"
    yield {"event": "completed",
           "images": [{"filename": filename, "data": img_b64, "type": "image/png"}],
           "pct": 100, "message": "Seedream 生成完成"}
