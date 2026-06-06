"""Lightweight retry utilities for transient network/timeout errors.

设计目标：
- 只重试**真正的瞬态错误**（network reset、超时、5xx），不要重试用户输入错误（4xx）
- 指数退避（默认 0.5s → 1s → 2s → 4s），避免雪崩
- 对**普通幂等请求**用 `async_retry`
- 对**流式 SSE/生成器**用 `async_retry_streaming`，仅在尚未产出任何内容时重试，避免重复输出
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import AsyncGenerator, Awaitable, Callable, TypeVar

import httpx

T = TypeVar("T")

# 哪些异常视为瞬态、值得重试
TRANSIENT_EXC = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
    asyncio.TimeoutError,
    ConnectionError,
    ConnectionResetError,
    OSError,    # 涵盖 WinError 10054 等
)


def _is_transient_status(exc: BaseException) -> bool:
    """5xx 视为瞬态；4xx 不视为瞬态。"""
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return False


async def async_retry(
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    label: str = "",
) -> T:
    """重试普通幂等异步调用。失败时 sleep 后重试，最后一次仍失败则抛原异常。"""
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return await func()
        except TRANSIENT_EXC as e:
            last_exc = e
        except httpx.HTTPStatusError as e:
            if _is_transient_status(e):
                last_exc = e
            else:
                raise
        # 退避
        wait = min(max_delay, base_delay * (2 ** i))
        print(
            f"[retry{f' {label}' if label else ''}] attempt {i+1}/{attempts} "
            f"failed: {type(last_exc).__name__}: {last_exc}; sleeping {wait:.1f}s",
            file=sys.stderr, flush=True,
        )
        await asyncio.sleep(wait)
    assert last_exc is not None
    raise last_exc


async def async_retry_streaming(
    gen_factory: Callable[[], AsyncGenerator[T, None]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    label: str = "",
) -> AsyncGenerator[T, None]:
    """流式生成器的重试：仅在尚未产出任何元素时重试，避免重复输出。

    一旦产出过一个元素就不再重试——继续传给调用方，由调用方决定如何处理后续断流。
    """
    for i in range(attempts):
        produced = False
        try:
            async for item in gen_factory():
                produced = True
                yield item
            return
        except TRANSIENT_EXC as e:
            if produced:
                # 已经产生过内容，重试会重复输出，交还给上层
                raise
            wait = min(max_delay, base_delay * (2 ** i))
            print(
                f"[retry-stream{f' {label}' if label else ''}] attempt {i+1}/{attempts} "
                f"failed before any output: {type(e).__name__}: {e}; sleeping {wait:.1f}s",
                file=sys.stderr, flush=True,
            )
            if i == attempts - 1:
                raise
            await asyncio.sleep(wait)
        except httpx.HTTPStatusError as e:
            if produced or not _is_transient_status(e):
                raise
            wait = min(max_delay, base_delay * (2 ** i))
            print(
                f"[retry-stream{f' {label}' if label else ''}] attempt {i+1}/{attempts} "
                f"5xx before any output: {e}; sleeping {wait:.1f}s",
                file=sys.stderr, flush=True,
            )
            if i == attempts - 1:
                raise
            await asyncio.sleep(wait)
