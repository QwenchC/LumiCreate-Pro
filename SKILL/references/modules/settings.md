# settings 模块

LumiCreate 全局设置位于 `%APPDATA%/LumiCreate-Pro/settings.json`，通过 API 读写。

## 接口

| 方法 | 路径              | 用途                                                                 |
|------|-------------------|----------------------------------------------------------------------|
| GET  | `/api/settings`   | 返回完整 `AppSettings`                                               |
| POST | `/api/settings`   | **必须传入完整 AppSettings**（全量覆盖；先 GET → 修改字段 → POST）   |

## AppSettings 结构

```jsonc
{
  "projects_dir": "C:/Users/<u>/LumiCreate-Projects",
  "text_engine": {
    "engine_type": "ollama|lmstudio|deepseek|bailian|openai_compat",
    "base_url": "http://localhost:11434",
    "api_key": null,
    "model": "qwen2.5:7b",
    "temperature": 0.7,
    "top_p": 0.9
  },
  "image_engine": {
    "comfyui_url": "http://localhost:8188",
    "workflow_dir": "F:/ComfyUI/user/default/workflows",
    "default_workflow": "lumicreate-基础",
    "default_gen_count": 3,
    "image_width": 1920,
    "image_height": 1080,
    "style_preset": "",         // 见下方画风预设
    "custom_style_text": ""
  },
  "audio_engine": {
    "engine_type": "indextts|gptsovits|manual",
    "api_url": "http://localhost:7860",
    "default_gen_count": 3,
    "voice_ref_dir": "C:/voice-refs",
    "emotion_ref_dir": "C:/emo-refs",
    "default_voice_ref": "linxia.wav",
    "default_emo_weight": 0.8
  },
  "video_engine": {
    "comfyui_url": "http://localhost:8188",
    "workflow_dir": "F:/ComfyUI/user/default/workflows",
    "comfyui_input_dir": "F:/ComfyUI/input",
    "default_workflow": "flfa2i-lumicreate",
    "resolution": "720x1280",
    "fps": 25
  }
}
```

## 引擎类型选择

### text_engine.engine_type
- `ollama` → base_url 默认 `http://localhost:11434`，调用 `/api/chat`，不需要 api_key
- `lmstudio` → 调 `/v1/chat/completions`（OpenAI 兼容），不需要 api_key
- `deepseek` → DeepSeek 官方 OpenAI 兼容端点，需要 api_key
- `bailian` → 阿里云百炼（通义千问 OpenAI 兼容模式），需要 api_key，Qwen3 系列自动 `enable_thinking: False`
- `openai_compat` → 任意 OpenAI 兼容端点

### audio_engine.engine_type
- `indextts` → IndexTTS-2.0 Gradio API（推荐，需配音色/情感参考目录）
- `gptsovits` → GPT-SoVITS API
- `manual` → 手动导入；`/test` 始终成功，但 `generate-stream` 报错"manual 模式不支持自动生成"

### image_engine.style_preset 画风预设
仅在前端渲染时注入，不写入分镜 prompt：
- `""`（无） / `anime`（二次元） / `realistic`（写实）
- `watercolor`（水彩） / `cyberpunk`（赛博朋克） / `inkwash`（国风水墨）
- `pixel`（像素） / `__custom__`（用 `custom_style_text` 字段）

## 修改流程范例

```python
async def patch_settings(http, **partial):
    cur = (await http.get("http://127.0.0.1:18520/api/settings")).json()
    # 深度合并 partial 到 cur ...
    await http.post("http://127.0.0.1:18520/api/settings", json=cur)
```

**不要直接 POST 只含部分字段的对象**——pydantic 会用默认值填充缺失字段，等同重置。
