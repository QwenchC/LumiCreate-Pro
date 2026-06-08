"""Application settings stored in a local JSON file."""
import json
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "LumiCreate-Pro" / "settings.json"


class TextEngineConfig(BaseModel):
    engine_type: Literal["ollama", "lmstudio", "deepseek", "bailian", "openai_compat"] = "ollama"
    base_url: str = "http://localhost:11434"
    api_key: Optional[str] = None
    model: str = ""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    # 批量任务（角色检测 / 帧 prompt / 视频 prompt 等）的最大并发数。
    # 本地模型(ollama/lmstudio)通常 1~4；deepseek-v4-flash 等云端模型可设到几百~2500。
    concurrency: int = Field(default=4, ge=1, le=2500)


class ImageEngineConfig(BaseModel):
    # v1.4.5: 多引擎切换 — 默认走本地 ComfyUI，可切到云端 Pollinations
    engine_type: Literal["comfyui", "pollinations"] = "comfyui"
    comfyui_url: str = "http://localhost:8188"
    workflow_dir: str = ""          # local path to ComfyUI workflows folder (e.g. F:/ComfyUI/user/default/workflows)
    default_workflow: str = ""
    default_gen_count: int = Field(default=3, ge=1, le=10)
    image_width: int = Field(default=1920, ge=64, le=8192)
    image_height: int = Field(default=1080, ge=64, le=8192)
    style_preset: str = ""           # selected style preset value
    custom_style_text: str = ""      # text when style_preset == '__custom__'
    # v1.4.5: Pollinations 字段（仅 engine_type='pollinations' 时使用）
    pollinations_base_url: str = "https://gen.pollinations.ai"
    pollinations_api_key:  str = ""               # sk_... 或 pk_...
    pollinations_model:    str = "flux"           # 默认模型；可被 default_workflow 覆盖


class AudioEngineConfig(BaseModel):
    engine_type: Literal["gptsovits", "indextts", "msedge", "manual"] = "indextts"
    api_url: str = "http://localhost:7860"
    default_gen_count: int = Field(default=3, ge=1, le=10)
    # IndexTTS reference audio settings
    voice_ref_dir: str = ""       # folder containing reference .mp3/.wav files
    emotion_ref_dir: str = ""     # folder containing emotion reference .wav files
    default_voice_ref: str = ""   # default voice reference filename (relative to voice_ref_dir)
    default_emo_weight: float = Field(default=0.8, ge=0.0, le=1.6)
    # Microsoft Edge TTS (used when engine_type == "msedge", works for ALL dialogue_modes)
    msedge_voice: str = "zh-CN-XiaoxiaoNeural"
    msedge_rate:  str = "+25%"    # "-100%" ~ "+100%"
    # 经"全部音色测试"通过的音色列表；非空时前端各处下拉只显示这些。
    # 空 = 未跑测试，不过滤（首次使用时各音色都可见）。
    msedge_available_voices: list[str] = Field(default_factory=list)


class VideoEngineConfig(BaseModel):
    comfyui_url: str = "http://localhost:8188"
    workflow_dir: str = ""          # local path to ComfyUI workflows folder (same as image_engine.workflow_dir usually)
    comfyui_input_dir: str = ""     # local path to ComfyUI input/ directory (for audio upload workaround)
    default_workflow: str = "flfa2i-lumicreate"
    resolution: str = "720x1280"
    fps: int = Field(default=25, ge=12, le=60)


class AppSettings(BaseModel):
    projects_dir: str = str(Path.home() / "LumiCreate-Projects")
    text_engine: TextEngineConfig = Field(default_factory=TextEngineConfig)
    image_engine: ImageEngineConfig = Field(default_factory=ImageEngineConfig)
    audio_engine: AudioEngineConfig = Field(default_factory=AudioEngineConfig)
    video_engine: VideoEngineConfig = Field(default_factory=VideoEngineConfig)


def load_settings() -> AppSettings:
    if SETTINGS_PATH.exists():
        try:
            return AppSettings(**json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return AppSettings()


def save_settings(settings: AppSettings) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
