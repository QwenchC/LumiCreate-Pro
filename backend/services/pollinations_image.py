"""v1.4.5: Pollinations 图片生成驱动。

Pollinations API（https://gen.pollinations.ai）走纯 HTTP GET，单次请求返回完整 PNG/JPEG。
没有 SSE / WebSocket 进度，所以我们模拟成与 ComfyUI 一致的事件流：
  queued → progress(伪进度) → completed → error

API 形态：
  GET /image/{url-encoded-prompt}?model=flux&width=1024&height=1024&seed=12345&nologo=true
  Authorization: Bearer sk_xxx     OR     ?key=sk_xxx
返回：image/png 或 image/jpeg
"""
from __future__ import annotations

import asyncio
import base64
import random
import urllib.parse
from typing import AsyncGenerator, Optional

import httpx


# 已知图片模型（用户配置 / 模型下拉的兜底，活的列表从 /image/models 拉）
DEFAULT_POLLINATIONS_IMAGE_MODELS = [
    "flux", "kontext", "gptimage", "gptimage-large", "gpt-image-2",
    "nanobanana", "nanobanana-2", "nanobanana-pro",
    "seedream", "seedream5", "seedream-pro",
    "zimage", "wan-image", "wan-image-pro",
    "qwen-image", "grok-imagine", "grok-imagine-pro",
    "klein", "p-image", "p-image-edit", "nova-canvas",
]


def _build_url(base_url: str, prompt: str, *,
                model: str, width: int, height: int, seed: Optional[int],
                api_key: str) -> str:
    """构造 GET URL。

    v1.4.5+：参数清单严格按当前 gen.pollinations.ai 文档收紧——只传
    `model / width / height / seed / key`。旧版的 `nologo / private` 不再发，
    因为新 API 校验严格会 400 "Query parameter validation failed"。

    api_key 走 query 参 `?key=` 传，避免某些 CDN 代理掉 Authorization header。
    """
    encoded = urllib.parse.quote(prompt, safe="")
    qs: dict[str, object] = {"model": model or "flux"}
    if width  and int(width)  > 0: qs["width"]  = int(width)
    if height and int(height) > 0: qs["height"] = int(height)
    if seed is not None:           qs["seed"]   = int(seed)
    if api_key:                    qs["key"]    = api_key
    return f"{base_url.rstrip('/')}/image/{encoded}?" + urllib.parse.urlencode(qs)


async def generate_image_pollinations(
    *,
    base_url:        str,
    api_key:         str,
    model:           str,
    prompt:          str,
    width:           int,
    height:          int,
    seed:            Optional[int] = None,
    timeout_secs:    int = 240,
) -> AsyncGenerator[dict, None]:
    """生成单张图，模拟 ComfyUI 事件流。

    Yields:
      {"event": "queued",    "prompt_id": str}
      {"event": "progress",  "value": int, "max": int}
      {"event": "completed", "images": [{"filename": str, "data": str (base64), "type": "image/png"}]}
      {"event": "error",     "message": str}
    """
    # seed=None 必须显式注入，否则 Pollinations 内部用确定性 hash 容易重复
    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    url = _build_url(base_url, prompt, model=model, width=width, height=height,
                      seed=seed, api_key=api_key)
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    prompt_id = f"poll_{seed}"
    yield {"event": "queued", "prompt_id": prompt_id}

    # 一边等响应一边推几个伪进度（防止前端进度条卡在 0），
    # 实际耗时由 Pollinations 服务端决定，无法获得真实步数
    progress_stop = asyncio.Event()

    async def _fake_progress():
        i = 0
        try:
            while not progress_stop.is_set() and i < 40:
                await asyncio.sleep(0.5)
                i += 1
                # 由调用方拉取生成器；这里只 set 共享状态，下面 main loop 推
        except asyncio.CancelledError:
            return

    progress_task = asyncio.create_task(_fake_progress())

    try:
        async with httpx.AsyncClient(timeout=timeout_secs, follow_redirects=True) as client:
            # 边等 HTTP 响应边推假进度；用 asyncio.wait 实现"先到先服务"
            req_task = asyncio.create_task(client.get(url, headers=headers))
            i = 0
            while not req_task.done():
                wait_done, _ = await asyncio.wait(
                    {req_task}, timeout=0.6, return_when=asyncio.FIRST_COMPLETED,
                )
                if req_task in wait_done:
                    break
                i += 1
                # 伪进度：到 95% 就停，留给真正的 completed
                pct = min(95, i * 5)
                yield {"event": "progress", "value": pct, "max": 100}
            r = req_task.result()

            if r.status_code >= 400:
                # 解析 Pollinations 的 JSON 错误格式 —— 尽力把"哪个字段错了"塞进消息
                try:
                    j = r.json()
                    err = (j.get("error") or {})
                    msg = err.get("message") or err.get("code") or f"HTTP {r.status_code}"
                    # validation 错误时把 details / 字段名也带出来，方便诊断
                    details = err.get("details") or err.get("issues") or err.get("errors")
                    if details:
                        msg = f"{msg} | {details}"
                    yield {"event": "error",
                           "message": f"Pollinations {r.status_code}: {msg}"}
                except Exception:
                    yield {"event": "error",
                           "message": f"Pollinations {r.status_code}: {r.text[:400]}"}
                return

            mime = r.headers.get("content-type", "image/png").split(";")[0].strip()
            if not mime.startswith("image/"):
                yield {"event": "error",
                       "message": f"Pollinations 返回非图片内容（{mime}）；可能 API key 无效或配额不足"}
                return

            data_b64 = base64.b64encode(r.content).decode()
            filename = f"pollinations_{seed}.png"
            yield {"event": "completed",
                   "images": [{"filename": filename, "data": data_b64, "type": mime}]}
    except httpx.HTTPError as e:
        yield {"event": "error", "message": f"Pollinations 网络错误: {e}"}
    except Exception as e:
        yield {"event": "error", "message": f"Pollinations 调用失败: {e}"}
    finally:
        progress_stop.set()
        try: progress_task.cancel()
        except Exception: pass


# ── 模型列表 / 连通性测试 ────────────────────────────────────────────────────


async def fetch_pollinations_image_models(base_url: str) -> list[str]:
    """从 Pollinations 拉活的图片模型列表。失败时回退到内置兜底列表。"""
    url = f"{base_url.rstrip('/')}/image/models"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                # API 形态可能是 list 或 {data:[...]}；两个都兼容
                names: list[str] = []
                if isinstance(data, list):
                    for m in data:
                        if isinstance(m, str): names.append(m)
                        elif isinstance(m, dict) and m.get("name"):
                            names.append(str(m["name"]))
                        elif isinstance(m, dict) and m.get("id"):
                            names.append(str(m["id"]))
                elif isinstance(data, dict) and isinstance(data.get("data"), list):
                    for m in data["data"]:
                        if isinstance(m, dict) and m.get("id"):
                            names.append(str(m["id"]))
                # 排序去重
                if names:
                    return sorted(set(names))
    except Exception:
        pass
    return list(DEFAULT_POLLINATIONS_IMAGE_MODELS)


async def test_pollinations_connection(base_url: str, api_key: str) -> dict:
    """简单连通性测试：调一次 /image/models（不需 key）+ 验证 key（如果给了）。"""
    url_models = f"{base_url.rstrip('/')}/image/models"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url_models)
            if r.status_code != 200:
                return {"success": False,
                        "message": f"Pollinations 不可达: HTTP {r.status_code}"}
        if not api_key:
            return {"success": True,
                    "message": "Pollinations 已连通（未配置 API key，仅 publishable 模式）"}
        # key 验证：调 /account/key
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{base_url.rstrip('/')}/account/key",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if r.status_code == 200:
                info = r.json()
                key_type = info.get("type", "unknown")
                return {"success": True,
                        "message": f"Pollinations 连接成功（key 类型: {key_type}）"}
            if r.status_code == 401:
                return {"success": False, "message": "API key 无效"}
            return {"success": False,
                    "message": f"key 校验失败 HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {e}"}
