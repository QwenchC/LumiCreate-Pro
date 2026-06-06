"""阻塞 IO/CPU 调用统一走线程池（B2）。

为什么不用 ProcessPool：
- subprocess.run 已经把工作丢给独立 OS 进程，外层只需要"不卡 event loop"
- 线程池开销远低于进程池；只要不持 GIL（subprocess.run 大部分时间在 syscall 等待）就够
- Whisper 用户在自己的 stable-whisper threading.Thread 里跑，已经隔离

用法：
    from services.exec_pool import run_blocking
    result = await run_blocking(subprocess.run, cmd, capture_output=True, timeout=300)

参数完全沿用 asyncio.to_thread 的签名，区别只在：
- 用一个共享 ThreadPoolExecutor（max_workers 可调），避免每次都 spawn 新线程
- 跨调用复用，比 to_thread 的"按需启动"更省
"""
from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

T = TypeVar("T")


# 默认并发：CPU 数 ×4（IO 密集场景），上限 32
_DEFAULT_WORKERS = min(32, (os.cpu_count() or 4) * 4)


def _make_pool() -> ThreadPoolExecutor:
    n = int(os.environ.get("LUMI_BLOCKING_WORKERS") or _DEFAULT_WORKERS)
    return ThreadPoolExecutor(
        max_workers=max(2, n),
        thread_name_prefix="lumi-blocking",
    )


_POOL: ThreadPoolExecutor | None = None


def get_pool() -> ThreadPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = _make_pool()
    return _POOL


async def run_blocking(fn: Callable[..., T], *args, **kwargs) -> T:
    """在共享线程池里跑同步函数，不阻塞 event loop。"""
    loop = asyncio.get_running_loop()
    if kwargs:
        # 包一层 lambda 让 kwargs 也能传
        return await loop.run_in_executor(get_pool(), lambda: fn(*args, **kwargs))
    return await loop.run_in_executor(get_pool(), fn, *args)


def shutdown(*, wait: bool = False) -> None:
    """进程退出时调用（pytest 也会用）。"""
    global _POOL
    if _POOL is not None:
        _POOL.shutdown(wait=wait, cancel_futures=True)
        _POOL = None
