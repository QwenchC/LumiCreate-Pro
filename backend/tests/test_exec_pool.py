"""B2 exec_pool：阻塞函数走线程池 + 高并发不卡 event loop。"""
import asyncio
import time

import pytest

from services.exec_pool import run_blocking, shutdown


@pytest.fixture(autouse=True)
def _cleanup_pool():
    yield
    shutdown(wait=False)


@pytest.mark.asyncio
async def test_run_blocking_returns_value():
    def f(x, y):
        return x + y
    assert await run_blocking(f, 2, 3) == 5


@pytest.mark.asyncio
async def test_run_blocking_with_kwargs():
    def f(*, x, y):
        return x * y
    assert await run_blocking(f, x=4, y=5) == 20


@pytest.mark.asyncio
async def test_run_blocking_propagates_exception():
    def boom():
        raise ValueError("nope")
    with pytest.raises(ValueError):
        await run_blocking(boom)


@pytest.mark.asyncio
async def test_event_loop_not_blocked_while_sleeping():
    """关键测试：跑一个 1s 的阻塞调用，期间 event loop 必须仍能调度其它协程。"""
    progress = {"ticks": 0}

    async def ticker():
        for _ in range(8):
            await asyncio.sleep(0.05)
            progress["ticks"] += 1

    async def blocker():
        await run_blocking(time.sleep, 0.5)

    t0 = time.monotonic()
    await asyncio.gather(ticker(), blocker())
    elapsed = time.monotonic() - t0
    assert progress["ticks"] >= 7, f"event loop blocked (ticks={progress['ticks']})"
    # 总耗时应当 ~0.5s 而非 0.5 + 0.4 = 0.9s
    assert elapsed < 0.9


@pytest.mark.asyncio
async def test_parallel_blocking_calls_run_concurrently():
    """两个阻塞调用应当并行跑（线程池），总耗时 ≈ 单个耗时。"""
    async def one():
        return await run_blocking(time.sleep, 0.3)
    t0 = time.monotonic()
    await asyncio.gather(*(one() for _ in range(4)))
    elapsed = time.monotonic() - t0
    # 串行需要 1.2s；并行 ~0.3s。给宽容到 0.7s 防 CI 抖动
    assert elapsed < 0.7, f"calls likely serialized: {elapsed:.2f}s"
