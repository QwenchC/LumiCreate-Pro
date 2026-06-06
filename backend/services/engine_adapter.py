"""EngineAdapter — 统一的引擎适配器抽象（C2）。

之前每个引擎（IndexTTS / GPT-SoVITS / msedge / Ollama / DeepSeek / ComfyUI ...）
都是一个独立 service 模块，调用方式各异；audio_engine.py 里堆了一大段
`if cfg.engine_type == 'indextts': ... elif 'gptsovits': ... elif 'msedge': ...`
路由分发逻辑。

EngineAdapter 把这套机制抽象出来：
- 每种引擎实现一个 `EngineAdapter` 子类
- 调用方走 `get_adapter(domain, engine_type)` 拿到对应实例
- 新增引擎（Replicate / Civitai / RunningHub 等）只需要新写一个 adapter

接口设计原则：
- `test()` 同步 / 异步连通性测试
- `synthesise(...)` 流式生成（async generator），事件 schema 统一
- `info()` 返回 metadata（名字 / 是否支持参考音频 / 是否在线 / 等）

当前只覆盖 audio 域；后续可加 ImageAdapter / TextLLMAdapter / VideoAdapter。
"""
from __future__ import annotations

import abc
import base64
from dataclasses import dataclass
from typing import AsyncIterator, Optional


# ── Events (统一事件 schema) ───────────────────────────────────────────────────


@dataclass
class TestResult:
    success: bool
    message: str


# audio synthesise 事件 — 与现有 indextts.synthesise / msedge_tts.synthesise 兼容
#   {"event": "started",   "id": ...}
#   {"event": "completed", "id": ..., "data": <b64>, "mime": "audio/..."}
#   {"event": "error",     "id": ..., "message": ...}


# ── 抽象基类 ──────────────────────────────────────────────────────────────────


class AudioEngineAdapter(abc.ABC):
    """所有音频引擎的统一接口。"""
    # adapter 标识，必须与 settings.audio_engine.engine_type 一致
    engine_type: str = ""
    # adapter 是否需要"音色参考音频"（IndexTTS 等是 True；msedge 是 False）
    needs_voice_reference: bool = False

    @abc.abstractmethod
    async def test(self) -> TestResult:
        """连通性测试。"""

    @abc.abstractmethod
    def synthesise(self, text: str, **opts) -> AsyncIterator[dict]:
        """流式合成。返回 async generator，事件 schema 见模块说明。

        opts 通用键：
            voice_ref:   str | None   音色参考音频路径（IndexTTS 必填；msedge 忽略）
            emo_ref:     str | None   情感参考（IndexTTS 可选）
            emo_weight:  float        情感权重
            voice:       str          MS Edge voice 名（msedge 必填，其它忽略）
            rate:        str          MS Edge 语速（msedge 用）
            speed:       float        GPT-SoVITS 速度
            lang:        str          GPT-SoVITS / IndexTTS 语言代码
            speaker:     str | None   GPT-SoVITS 角色名

        子类实现时未支持的键忽略即可。
        """

    def info(self) -> dict:
        return {
            "engine_type": self.engine_type,
            "needs_voice_reference": self.needs_voice_reference,
        }


# ── msedge ────────────────────────────────────────────────────────────────────


class MsEdgeAudioAdapter(AudioEngineAdapter):
    engine_type = "msedge"
    needs_voice_reference = False

    def __init__(self, *, default_voice: str, default_rate: str):
        self._default_voice = default_voice
        self._default_rate  = default_rate

    async def test(self) -> TestResult:
        try:
            from services.msedge_tts import synthesise_mp3
            await synthesise_mp3("测试", self._default_voice, self._default_rate)
            return TestResult(True, "微软神经语音 (edge-tts) 连接成功")
        except Exception as e:
            return TestResult(False, f"edge-tts: {e}")

    async def synthesise(self, text: str, **opts):
        from services.msedge_tts import synthesise as ms_synthesise
        voice = opts.get("voice") or self._default_voice
        rate  = opts.get("rate")  or self._default_rate
        async for ev in ms_synthesise(text, voice, rate):
            yield ev


# ── IndexTTS ──────────────────────────────────────────────────────────────────


class IndexTTSAudioAdapter(AudioEngineAdapter):
    engine_type = "indextts"
    needs_voice_reference = True

    def __init__(self, *, api_url: str, voice_ref_dir: str = "",
                 default_voice_ref: str = "", emotion_ref_dir: str = "",
                 default_emo_weight: float = 0.8):
        self._api_url = api_url
        self._voice_ref_dir = voice_ref_dir
        self._default_voice_ref = default_voice_ref
        self._emotion_ref_dir = emotion_ref_dir
        self._default_emo_weight = default_emo_weight

    async def test(self) -> TestResult:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.get(f"{self._api_url.rstrip('/')}/")
            return TestResult(True, "IndexTTS-2.0 连接成功")
        except Exception as e:
            return TestResult(False, str(e))

    async def synthesise(self, text: str, **opts):
        from services.indextts import synthesise
        from routers.audio_engine import _resolve_ref
        # 解析参考音频路径
        voice_path = (
            _resolve_ref(opts.get("voice_ref"), self._voice_ref_dir)
            or _resolve_ref(self._default_voice_ref, self._voice_ref_dir)
        )
        if not voice_path:
            yield {"event": "error", "message": "未配置音色参考音频，请在设置中指定 voice_ref_dir"}
            return
        emo_path = _resolve_ref(opts.get("emo_ref"), self._emotion_ref_dir)
        emo_weight = float(opts.get("emo_weight", self._default_emo_weight))
        # 重用一个简单的 config 适配器
        class _Cfg:
            api_url = self._api_url
        # 调用 service 层（保持原有签名）
        from services.indextts import synthesise as idx
        async for ev in idx(_Cfg, text, voice_path, emo_path, emo_weight):
            yield ev


# ── GPT-SoVITS ────────────────────────────────────────────────────────────────


class GptSoVitsAudioAdapter(AudioEngineAdapter):
    engine_type = "gptsovits"
    needs_voice_reference = True

    def __init__(self, *, api_url: str):
        self._api_url = api_url

    async def test(self) -> TestResult:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.get(f"{self._api_url.rstrip('/')}/")
            return TestResult(True, "GPT-SoVITS 连接成功")
        except Exception as e:
            return TestResult(False, str(e))

    async def synthesise(self, text: str, **opts):
        from services.gptsovits import synthesise
        class _Cfg:
            api_url = self._api_url
        speed   = float(opts.get("speed", 1.0))
        lang    = opts.get("lang") or "zh"
        speaker = opts.get("speaker")
        voice_ref = opts.get("voice_ref")
        async for ev in synthesise(_Cfg, text, lang, speaker, voice_ref, None, lang, speed=speed):
            yield ev


# ── Manual (no-op) ────────────────────────────────────────────────────────────


class ManualAudioAdapter(AudioEngineAdapter):
    engine_type = "manual"

    async def test(self) -> TestResult:
        return TestResult(True, "手动导入模式，无需连接")

    async def synthesise(self, text: str, **opts):
        yield {"event": "error", "message": "manual 模式不支持自动生成"}


# ── Factory ───────────────────────────────────────────────────────────────────


def make_audio_adapter() -> AudioEngineAdapter:
    """根据当前 settings 创建对应 adapter（每次调用都新建——保证拿到最新设置）。"""
    from config import load_settings
    cfg = load_settings().audio_engine
    et = (cfg.engine_type or "indextts").lower()
    if et == "msedge":
        return MsEdgeAudioAdapter(
            default_voice=cfg.msedge_voice,
            default_rate=cfg.msedge_rate,
        )
    if et == "gptsovits":
        return GptSoVitsAudioAdapter(api_url=cfg.api_url)
    if et == "manual":
        return ManualAudioAdapter()
    # default indextts
    return IndexTTSAudioAdapter(
        api_url=cfg.api_url,
        voice_ref_dir=cfg.voice_ref_dir,
        default_voice_ref=cfg.default_voice_ref,
        emotion_ref_dir=cfg.emotion_ref_dir,
        default_emo_weight=cfg.default_emo_weight,
    )
