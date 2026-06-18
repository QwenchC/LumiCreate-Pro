"""Application settings stored in a local JSON file."""
import json
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "LumiCreate-Pro" / "settings.json"


class TextPlatform(BaseModel):
    """v1.4.11+: 文本引擎平台清单条目。
    用户在 setting 页能从下拉里选 builtin / 自定义平台。
    所有非 ollama 平台都走 OpenAI-compatible 通道（services/llm.py 不需要改）。
    """
    id: str             # 唯一 key（builtin 用名字如 'volcengine'，自定义用 'custom_xxx'）
    label: str          # 显示名（中文）
    base_url: str       # 默认 base URL（用户仍可在主表单覆盖）
    api_path: str = "chat/completions"   # 一般 OpenAI-compat 都是这个
    model_hint: str = ""                 # 模型 ID 示例 / 提示，供 UI 显示
    is_ollama: bool = False              # ollama 走 /api/chat（非 openai-compat）
    is_builtin: bool = False             # builtin 不可删除


class TextEngineConfig(BaseModel):
    # v1.4.11+: 改为自由 str。下游 services/llm.py 早就是"ollama / 其它"两分支，
    # 老平台 id（ollama/lmstudio/deepseek/bailian/openai_compat）行为不变；
    # 新平台 id（volcengine / moonshot / siliconflow / 用户自定义）走同一 OpenAI-compat 通道
    engine_type: str = "ollama"
    base_url: str = "http://localhost:11434"
    api_key: Optional[str] = None
    model: str = ""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    # 批量任务（角色检测 / 帧 prompt / 视频 prompt 等）的最大并发数。
    # 本地模型(ollama/lmstudio)通常 1~4；deepseek-v4-flash 等云端模型可设到几百~2500。
    concurrency: int = Field(default=4, ge=1, le=2500)
    # v1.4.11+: 用户自定义平台（builtin 不进这里，前端合并展示）
    custom_platforms: list[TextPlatform] = Field(default_factory=list)


class ImageEngineConfig(BaseModel):
    # v1.4.5+: 多引擎切换 — 默认 ComfyUI 本地，可切到 Pollinations 或火山引擎 Seedream
    engine_type: Literal["comfyui", "pollinations", "volcengine_seedream"] = "comfyui"
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
    # v1.4.11+: 火山引擎 Seedream（文生图）字段（仅 engine_type='volcengine_seedream' 时用）
    seedream_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    seedream_api_key:  str = ""                    # ARK_API_KEY
    seedream_model:    str = ""                    # 模型 ID，如 doubao-seedream-5-0-260128
    seedream_size:     str = "1024x1024"           # 默认输出尺寸
    seedream_response_format: str = "url"          # 'url' | 'b64_json'
    seedream_seed:     int = -1                    # -1 随机；其它整数复现


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
    # v1.4.10: 引擎切换 —— 默认本地 ComfyUI（LTX-2.3），可切到云端 API（火山引擎 Seedance）。
    # 老配置文件没有这字段时，Pydantic 自动用默认 "comfyui"，行为与之前完全一致。
    engine_type: Literal["comfyui", "volcengine_seedance"] = "comfyui"
    comfyui_url: str = "http://localhost:8188"
    workflow_dir: str = ""          # local path to ComfyUI workflows folder (same as image_engine.workflow_dir usually)
    comfyui_input_dir: str = ""     # local path to ComfyUI input/ directory (for audio upload workaround)
    default_workflow: str = "flfa2i-lumicreate"
    resolution: str = "720x1280"
    fps: int = Field(default=25, ge=12, le=60)
    # v1.4.10: 火山引擎 Ark（Seedance）字段（仅 engine_type='volcengine_seedance' 时使用）
    # 端点 / 模型 ID 全部可在前端设置页改，避免本地实现假设和官方文档脱节
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_api_key:  str = ""
    # 模型 ID：用户在火山方舟控制台创建的 endpoint ID（典型形如 ep-2024xxxxxxx-xxxxx），
    # 或官方模型别名。空字符串 → 调用前会校验失败提醒用户先填
    volcengine_model_id: str = ""
    # 任务轮询超时（秒）。Seedance 一段 5s 视频通常 30-120s 出结果
    volcengine_poll_timeout: int = Field(default=600, ge=30, le=3600)
    volcengine_poll_interval: int = Field(default=5, ge=1, le=60)
    # 单条视频时长（秒，整数）—— Seedance 2.0 常见档位 5 / 10 秒
    volcengine_duration_secs: int = Field(default=5, ge=2, le=10)
    # 分辨率（480p / 720p / 1080p；Seedance 2.0 fast 不支持 1080p）
    volcengine_resolution: str = "720p"
    # 宽高比（16:9 / 4:3 / 1:1 / 3:4 / 9:16 / 21:9 / adaptive）；
    # adaptive = 模型按输入图片自动选最接近的比例（Seedance 2.0/1.5 推荐）
    volcengine_ratio: str = "adaptive"
    # 是否使用首末帧驱动（Seedance i2v / flf2v）；False 即纯文生视频
    volcengine_use_image: bool = True
    # 是否让 Seedance 自带生成音频（漫剧 reading 模式 = False，由 TTS 独立产出
    # → 后期 ffmpeg 合成；非漫剧场景可以开 True 让模型自带音频）
    volcengine_generate_audio: bool = False
    # 输出视频是否带"AI 生成"水印
    volcengine_watermark: bool = False
    # 是否固定摄像头（Seedance 2.0 暂不支持，此项仅对老模型生效）
    volcengine_camera_fixed: bool = False
    # seed：-1 = 随机；其它整数 = 复现
    volcengine_seed: int = -1

    # ── v1.6: 视频后期 RVC 变声（仅对已生成的视频做后期换音轨，实现音色一致性）──
    # 需要外部 RVC 环境（RVC-WebUI 整合包）+ 训练好的 .pth 模型。老配置自动取默认值。
    redub_rvc_root:      str = "E:\\Clone\\RVC20240604Nvidia50x0"
    redub_rvc_python:    str = ""        # 空 → 工作流默认 <rvc_root>\\runtime\\python.exe
    redub_device:        str = "cuda:0"
    redub_default_model: str = ""        # 默认 RVC .pth（voice_mapping 留空时整片统一此音色）
    redub_whisper_model: str = "medium"  # Whisper 分段模型：tiny/base/small/medium/large-v3
    redub_language:      str = "zh"


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
