"""services.retry — 瞬态错误重试。"""
import asyncio
import httpx
import pytest

from services.retry import async_retry, async_retry_streaming


def _make_response(status: int) -> httpx.Response:
    return httpx.Response(status_code=status, request=httpx.Request("GET", "http://test/"))


@pytest.mark.asyncio
async def test_async_retry_success_first_try():
    async def fn():
        return 42
    assert await async_retry(fn, attempts=3, base_delay=0.0) == 42


@pytest.mark.asyncio
async def test_async_retry_recovers_after_transient():
    calls = {"n": 0}
    async def fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ReadTimeout("boom")
        return "ok"
    out = await async_retry(fn, attempts=3, base_delay=0.0)
    assert out == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_async_retry_does_not_swallow_4xx():
    async def fn():
        raise httpx.HTTPStatusError("bad", request=None, response=_make_response(400))
    with pytest.raises(httpx.HTTPStatusError):
        await async_retry(fn, attempts=3, base_delay=0.0)


@pytest.mark.asyncio
async def test_streaming_retries_only_before_first_yield():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        # 第一次直接抛瞬态错；第二次正常输出
        if calls["n"] == 1:
            raise httpx.ConnectError("net down")
        yield "a"
        yield "b"

    items = []
    async for x in async_retry_streaming(factory, attempts=3, base_delay=0.0):
        items.append(x)
    assert items == ["a", "b"]
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_streaming_does_not_retry_after_first_yield():
    """一旦产出过元素，后续异常不能重试（避免重复输出）。"""
    async def factory():
        yield "first"
        raise httpx.ReadTimeout("dropped midway")

    items = []
    with pytest.raises(httpx.ReadTimeout):
        async for x in async_retry_streaming(factory, attempts=3, base_delay=0.0):
            items.append(x)
    assert items == ["first"]


# 让 pytest-asyncio 自动 enable
def pytest_collection_modifyitems(items):
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
