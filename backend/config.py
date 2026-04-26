"""Application settings stored in a local JSON file."""
import json
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "LumiCreate-Local" / "settings.json"


class TextEngineConfig(BaseModel):
    engine_type: Literal["ollama", "lmstudio", "deepseek", "openai_compat"] = "ollama"
    base_url: str = "http://localhost:11434"
    api_key: Optional[str] = None
    model: str = ""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)


class ImageEngineConfig(BaseModel):
    comfyui_url: str = "http://localhost:8188"
    workflow_dir: str = ""          # local path to ComfyUI workflows folder (e.g. F:/ComfyUI/user/default/workflows)
    default_workflow: str = ""
    default_gen_count: int = Field(default=3, ge=1, le=10)
    image_width: int = Field(default=1920, ge=64, le=8192)
    image_height: int = Field(default=1080, ge=64, le=8192)


class AudioEngineConfig(BaseModel):
    engine_type: Literal["gptsovits", "manual"] = "gptsovits"
    api_url: str = "http://localhost:9880"
    default_gen_count: int = Field(default=3, ge=1, le=10)


class VideoEngineConfig(BaseModel):
    comfyui_url: str = "http://localhost:8188"
    default_workflow: str = ""
    resolution: str = "1920x1080"
    fps: int = Field(default=30, ge=12, le=60)


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
