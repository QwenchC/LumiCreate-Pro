# 对白模式 (dialogue_mode) 详解

LumiCreate 的所有路径都受 `manuscript.config.dialogue_mode` 影响，**误传会导致流水线断裂**。

> **漫剧 / 朗读视频默认值**：`dialogue_mode = "reading"`，Edge TTS 声音 `zh-CN-XiaoxiaoNeural`（晓晓），语速 **`+25%`（快）**，**分镜走"手动"路径**（[manual-scenes.md](./manual-scenes.md)，每段 ≤ 50 字符），视频 `720x1280` 竖屏，字幕字号 10。这是用户在 SKILL 调用场景下的开箱配置。

四种模式：

| 值          | 含义              | LLM 任务                       | 音频引擎   | 一镜结构                          |
|-------------|-------------------|--------------------------------|------------|-----------------------------------|
| `narration` | 纯旁白            | 生成"旁白"角色单段文本         | IndexTTS   | dialogues 中 character 多为 "旁白" |
| `dialogue`  | 纯对话            | 生成多角色对话                 | IndexTTS   | dialogues 多于一条                |
| `mixed`     | 旁白+对话混合     | 灵活组合                       | IndexTTS   | 旁白与对话穿插                    |
| `reading`   | 纯朗读（直读文案）| **不调 LLM**，服务端按句切分    | Edge TTS   | dialogues 仅一条 "旁白" + audio_timeline |

## 不同模式下流水线的差异

### 1. 分镜生成阶段
- `narration|dialogue|mixed`：
  - 调 `POST /api/text-engine/generate-scenes`
  - LLM 出 JSON 数组，每镜含 `dialogues[]`
  - 调用必须传入 `dialogue_mode` 让 LLM 严格遵守
- `reading`（漫剧/朗读默认）：
  - **首选"手动分镜"路径**：客户端本地按句切分 + ≤ 50 字符合并，详见 [manual-scenes.md](./manual-scenes.md)。优势：可控分镜数量、宁可多分、scene id 带 `_manual` 后缀与前端一致。
  - 备选 `generate-scenes`：后端**绕过 LLM**，调用 `_split_reading_scenes`：
    - 按 `[。！？……\n]` 分句
    - 累积 ≤ `_READING_MAX_SECS * _READING_CPS = 28 * 4 = 112` 字符为一镜（**过长，漫剧不推荐**）
    - 自动给每镜放一个 `dialogues=[{character:"旁白",...}]` 和 `audio_timeline=[{type:"dialogue",dialogue_index:0}]`

### 2. 音频生成阶段
- `narration|dialogue|mixed`：
  - 对每个 dialogue 调 `POST /api/audio-engine/generate-stream` (单条) 或 `generate-batch-stream`
  - 必须配置 `voice_ref_dir` 与 `default_voice_ref`（IndexTTS）；否则报错"未配置音色参考音频"
  - 多段后调 `POST /api/audio-engine/stitch-scene` 拼接为一段
- `reading`：
  - **不调 IndexTTS**，对每镜整段文本调 `POST /api/audio-engine/ms-tts`
  - 一镜=一段 mp3，不需要 `stitch-scene`
  - 不需要 `voice_ref_dir`，无需任何外部模型，纯网络调用 edge-tts
  - **必须以 `__ms_reading__{sceneId}` 为 key** 保存到 `audio.json`，结构 `{data:<b64 mp3>, duration_ms}`，**这一点前端硬编码**：
    - 前端音频页 `loadData()`：`savedAudio["__ms_reading__" + scene.id]` 读取
    - 视频页 `loadData()`：把 `__ms_reading__{id}` 自动映射到 `__stitched__{id}` 复用音频
  - 写 `audio.{sceneId}` 不会报错，但前端看不到、视频页拿不到音频

### 3. 视频生成阶段
- 视频引擎需要的 `audio_b64`：
  - `narration|dialogue|mixed`：用 `stitch-scene` 输出的 WAV base64
  - `reading`：用 `ms-tts` 输出的 MP3 base64
  - 都通过 ComfyUI 工作流加载，后端始终以 `.wav` 后缀写入 ComfyUI input/，但内容是原始字节（mp3 也按 wav 命名）；ComfyUI LoadAudio 节点用 ffmpeg/torchaudio 按内容识别格式，所以 mp3 也能跑通 LTX 工作流（与前端 reading 模式一致路径）

## 实操判定逻辑（执行前先 GET）

```python
async def pick_audio_strategy(project_id, http):
    r = await http.get(f"http://127.0.0.1:18520/api/projects/{project_id}/manuscript")
    mode = r.json().get("config", {}).get("dialogue_mode", "mixed")
    return "edge" if mode == "reading" else "indextts"
```

## Edge TTS 可用声音

仅中文神经语音，统一前缀 `zh-CN-`：

| voice                | 标签 |
|----------------------|------|
| `XiaoxiaoNeural`     | 晓晓（默认） |
| `XiaoyiNeural`       | 晓伊 |
| `YunjianNeural`      | 云健 |
| `YunxiNeural`        | 云希 |
| `YunxiaNeural`       | 云夏 |
| `YunyangNeural`      | 云扬 |
| `liaoning-XiaobeiNeural` | 辽宁-晓北（方言） |
| `shaanxi-XiaoniNeural`   | 陕西-晓妮（方言） |
| `XiaohanNeural`      | 晓涵 |
| `XiaomengNeural`     | 晓梦 |

`rate` 取值（**漫剧默认 `+25%` 快**）：
- `-50%` 很慢 / `-25%` 慢 / `+0%` 正常 / **`+25%` 快（推荐）** / `+50%` 很快

## 常见误用与排查

- **症状**：`generate-scenes` 返回的分镜与文案"几乎不一样" → 检查 `dialogue_mode` 是否为 `reading` 而你期望的是 LLM 创作。
- **症状**：`audio-engine/generate-stream` 报"未配置音色参考音频" → 这是 IndexTTS 路径；如果用户用 reading 模式应改调 `/ms-tts`。
- **症状**：朗读视频生成失败"缺少场景合并音频" → 朗读模式不需要 stitch，但仍需把 `ms-tts` 返回的 base64 作为 `audio_b64` 传给视频引擎。
