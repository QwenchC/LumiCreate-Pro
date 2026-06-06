"""C2 EngineAdapter：factory 选对 adapter + 接口契约。"""
import pytest

from services.engine_adapter import (
    AudioEngineAdapter,
    GptSoVitsAudioAdapter,
    IndexTTSAudioAdapter,
    ManualAudioAdapter,
    MsEdgeAudioAdapter,
    make_audio_adapter,
)


class _FakeAudioCfg:
    engine_type = "msedge"
    api_url = "http://localhost:7860"
    voice_ref_dir = ""
    default_voice_ref = ""
    emotion_ref_dir = ""
    default_emo_weight = 0.8
    msedge_voice = "zh-CN-XiaoxiaoNeural"
    msedge_rate  = "+0%"


class _FakeSettings:
    def __init__(self, et: str):
        self.audio_engine = type("X", (), {**_FakeAudioCfg.__dict__, "engine_type": et})()


def _patch_settings(monkeypatch, engine_type: str):
    import config
    monkeypatch.setattr(config, "load_settings", lambda: _FakeSettings(engine_type))


def test_factory_msedge(monkeypatch):
    _patch_settings(monkeypatch, "msedge")
    a = make_audio_adapter()
    assert isinstance(a, MsEdgeAudioAdapter)
    assert a.engine_type == "msedge"
    assert a.needs_voice_reference is False


def test_factory_indextts(monkeypatch):
    _patch_settings(monkeypatch, "indextts")
    a = make_audio_adapter()
    assert isinstance(a, IndexTTSAudioAdapter)
    assert a.needs_voice_reference is True


def test_factory_gptsovits(monkeypatch):
    _patch_settings(monkeypatch, "gptsovits")
    a = make_audio_adapter()
    assert isinstance(a, GptSoVitsAudioAdapter)
    assert a.needs_voice_reference is True


def test_factory_manual(monkeypatch):
    _patch_settings(monkeypatch, "manual")
    a = make_audio_adapter()
    assert isinstance(a, ManualAudioAdapter)


def test_factory_unknown_defaults_to_indextts(monkeypatch):
    _patch_settings(monkeypatch, "totally-unknown-engine-xyz")
    a = make_audio_adapter()
    assert isinstance(a, IndexTTSAudioAdapter)


def test_info_contract():
    a = MsEdgeAudioAdapter(default_voice="zh-CN-XiaoxiaoNeural", default_rate="+0%")
    info = a.info()
    assert info["engine_type"] == "msedge"
    assert info["needs_voice_reference"] is False


@pytest.mark.asyncio
async def test_manual_test_is_ok():
    a = ManualAudioAdapter()
    r = await a.test()
    assert r.success
    assert "手动" in r.message


@pytest.mark.asyncio
async def test_manual_synthesise_yields_error_event():
    a = ManualAudioAdapter()
    events = [ev async for ev in a.synthesise("hello")]
    assert len(events) == 1
    assert events[0]["event"] == "error"
