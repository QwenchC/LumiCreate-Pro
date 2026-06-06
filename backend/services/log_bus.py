"""In-memory log bus (E1).

设计目标：
- 不改动现有 `print(..., file=sys.stderr, flush=True)` 的调用方
- 通过 TeeWriter 包装 stderr / stdout，每一行被同时写入：
   1) 原始 stderr（终端依旧能看）
   2) 环形 buffer（前端浮窗实时拉取）
- 暴露 `subscribe()` 返回 asyncio.Queue，新行入 queue 后 SSE 端点直接转发

线程安全：TeeWriter.write 可被多个线程调用（uvicorn + threads），用 threading.Lock 保护
buffer / subscribers 列表。
"""
from __future__ import annotations

import asyncio
import io
import sys
import threading
import time
from collections import deque
from typing import Optional


# 环形 buffer
_BUFFER: deque[dict] = deque(maxlen=2000)
_BUF_LOCK = threading.Lock()
_LINE_ID = [0]                      # 单元素 list 充当可变 int
_SUBSCRIBERS: list[asyncio.Queue] = []
_SUB_LOCK = threading.Lock()
_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Uvicorn 启动时调用一次：记下事件循环，用于跨线程投递。"""
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def _emit(line: str, level: str) -> None:
    line = line.rstrip("\n")
    if not line:
        return
    with _BUF_LOCK:
        _LINE_ID[0] += 1
        evt = {
            "id":    _LINE_ID[0],
            "ts":    time.time(),
            "level": level,                 # 'info' | 'error'
            "text":  line[:4000],           # 单行截断防大块二进制
        }
        _BUFFER.append(evt)

    # 通知所有订阅者（跨线程通过 call_soon_threadsafe 投递）
    with _SUB_LOCK:
        subs = list(_SUBSCRIBERS)
    if not subs or _MAIN_LOOP is None:
        return
    for q in subs:
        try:
            _MAIN_LOOP.call_soon_threadsafe(q.put_nowait, evt)
        except Exception:
            pass


def get_recent(limit: int = 200, after_id: int = 0) -> list[dict]:
    with _BUF_LOCK:
        if after_id:
            return [e for e in _BUFFER if e["id"] > after_id][-limit:]
        return list(_BUFFER)[-limit:]


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    with _SUB_LOCK:
        _SUBSCRIBERS.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _SUB_LOCK:
        try:
            _SUBSCRIBERS.remove(q)
        except ValueError:
            pass


class _TeeWriter(io.TextIOBase):
    """Wrap a stream so every write also goes to the log bus."""
    def __init__(self, inner, level: str):
        self._inner = inner
        self._level = level
        self._buf = ""

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if not isinstance(s, str):
            return self._inner.write(s)
        n = self._inner.write(s)
        try:
            # 按行切分；不完整的尾部留到下次
            self._buf += s
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                if line.strip():
                    _emit(line, self._level)
        except Exception:
            pass
        return n

    def flush(self) -> None:
        try:
            self._inner.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        try:
            return bool(self._inner.isatty())
        except Exception:
            return False

    @property
    def encoding(self) -> str:
        return getattr(self._inner, "encoding", "utf-8") or "utf-8"


def install_tee() -> None:
    """启动时调用一次：替换 sys.stderr / sys.stdout。幂等。"""
    if isinstance(sys.stderr, _TeeWriter):
        return
    sys.stderr = _TeeWriter(sys.stderr, "error")
    sys.stdout = _TeeWriter(sys.stdout, "info")
