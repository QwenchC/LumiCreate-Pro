# LumiCreate 端到端流水线参考

完整的从空白项目到带字幕成片的调用顺序。所有接口 base URL：`http://127.0.0.1:18520`。

## 0. 探活

```http
GET /api/health
→ {"status":"ok","version":"0.1.0"}
```

各引擎可选探活：
- `GET /api/text-engine/test` → `{success, message, models[]}`
- `GET /api/image-engine/test` / `GET /api/video-engine/test` → ComfyUI 连通性
- `GET /api/audio-engine/test` → IndexTTS / GPT-SoVITS 连通性

## 1. 项目准备

| 步骤             | 接口                                      | 关键字段                              |
|------------------|-------------------------------------------|---------------------------------------|
| 列出项目         | `GET /api/projects`                       | 返回 `ProjectMeta[]`                  |
| 新建项目         | `POST /api/projects`                      | body: `{name, description, folder_id}` |
| 可选：复制配置   | `POST /api/projects/{id}/copy-config`     | body: `{source_project_id}`           |

返回的 `project.id` 是后续所有调用的主键，**必须从这里取**，不能凭空构造。

## 2. 文案 (manuscript)

### 2.1 生成（流式）
```http
POST /api/text-engine/generate-manuscript
Content-Type: application/json

{
  "config": {
    "length": "medium",          // short|medium|long
    "audience": "都市白领",
    "style": "悬疑短剧",
    "tone": "压抑",
    "theme": "失踪",
    "worldview": "近未来上海",
    "characters": [
      {"name":"林夏","role":"侦探","traits":"冷静、寡言"}
    ],
    "dialogue_mode": "mixed"     // narration|dialogue|mixed|reading
  },
  "existing_content": ""         // 续写时填入旧文案
}
```
返回 SSE：`data: {"text":"..."}` 多次 → `data: [DONE]`。客户端累积全部 `text` 得到完整文案。

### 2.2 持久化
```http
PUT /api/projects/{project_id}/manuscript
{ "content": "<拼接得到的完整文案>", "config": { ...同上 config... } }
```
保存后 `progress.manuscript` 置 100。

## 3. 角色 (characters) — 漫剧必做

**漫剧创作顺序固定**：文案 → **角色卡** → 分镜 → 出图。跳过角色卡会让分镜阶段角色感知失效、出图阶段角色每镜飘移。详细流程见 [character-cards.md](./character-cards.md)。

| 接口                                                            | 用途                                                          |
|-----------------------------------------------------------------|---------------------------------------------------------------|
| `GET /api/projects/{id}/characters`                             | 返回 `{characters:[{name,role,traits,appearance,...}]}`       |
| `PUT /api/projects/{id}/characters`                             | 覆盖式写入                                                    |
| `POST /api/text-engine/generate-character-profile`              | 已知 name + manuscript，让 LLM 反推 role / traits             |
| `POST /api/text-engine/generate-character-appearance`           | 流式生成 appearance（英文标签，禁止情绪/表情词）              |
| `POST /api/text-engine/suggest-scene-characters`                | 给定分镜描述/台词 + all_names + manuscript，返回出镜子集（可解析他/她）|

漫剧最小流程：
```python
# 1) 智能体读 manuscript 提取角色名 names = ["林夏","张川"]（LumiCreate 无该端点）
# 2) 对每个 name：
for name in names:
    profile = await api.post("/api/text-engine/generate-character-profile",
                              {"name": name, "manuscript": ms_text,
                               "existing_role":"", "existing_traits":""})
    appearance = ""
    async for evt in api.sse("/api/text-engine/generate-character-appearance",
                              {"name": name, "role": profile["role"],
                               "traits": profile["traits"], "existing": ""}):
        if "text" in evt: appearance += evt["text"]
    chars.append({"name":name, **profile, "appearance":appearance, "negative":""})

# 3) 写入 characters.json + 同步 manuscript.config.characters
await api.put(f"/api/projects/{pid}/characters", {"characters": chars})
ms = await api.get(f"/api/projects/{pid}/manuscript")
cfg = ms.get("config") or {}
cfg["characters"] = [{"name":c["name"],"role":c["role"],"traits":c["traits"]} for c in chars]
await api.put(f"/api/projects/{pid}/manuscript", {"content": ms["content"], "config": cfg})
```

## 4. 分镜 (scenes)

### 4.0 漫剧 / 朗读视频：角色感知手动分镜（默认）

漫剧默认**不调 `generate-scenes`**，改用客户端本地切句 + 合并算法。详见 [manual-scenes.md](./manual-scenes.md)。

**必须先完成 §3 角色卡片**，否则 known_names 为空，无法按角色拆分：

```python
known_names = [c["name"] for c in (await api.get(f"/api/projects/{pid}/characters"))["characters"]]
scenes = manual_split(
    manuscript,
    dialogue_mode="reading",
    max_chars=50,
    known_names=known_names,
    max_characters_per_scene=1,   # 漫剧硬约束：单镜出镜 ≤ 1 人
)
await api.put(f"/api/projects/{pid}/scenes", {"scenes": scenes})
```

- key 与前端一致：`scene_001_manual`、`scene_002_manual`…
- `_scene_characters` 由切分过程直接产出（命中的 ≤ 1 个名字），无需再调 `suggest-scene-characters`
- 无角色的纯环境/物件镜头（`_scene_characters = []`）**是漫剧重要节奏**，保留即可

### 4.1 生成（非漫剧用）
```http
POST /api/text-engine/generate-scenes
{
  "manuscript": "<完整文案>",
  "dialogue_mode": "mixed",   // reading 模式走纯文本切句，无 LLM
  "characters": [{"name":"林夏","role":"侦探","traits":"..."}]
}
→ { "scenes":[...], "total": N }
```
单个 scene 结构：
```json
{
  "id": "scene_001", "index": 1,
  "description": "...", "duration_estimate": 8.0,
  "start_frame_prompt": "", "end_frame_prompt": "",
  "dialogues": [
    {"character":"林夏","text":"...","emotion":"平静",
     "pause_before":0.0,"pause_after":0.3}
  ]
}
```
**reading 模式额外提供 `audio_timeline`**：`[{"type":"dialogue","dialogue_index":0}]`。

### 4.2 首/末帧提示词（按需逐个或全部）
```http
POST /api/text-engine/generate-frame-prompts
{
  "description": "...", "dialogues": [...],
  "characters": [<仅本镜 _scene_characters 命中的角色，0 或 1 个>],
  "manuscript": "<完整文案>",
  "scene_index": 1, "total_scenes": N
}
→ { "start_frame_prompt": "...英文...", "end_frame_prompt": "...英文..." }
```
**生成出的英文 prompt 应回写到 `scenes[i].start_frame_prompt / end_frame_prompt` 中再 PUT。**

⚠️ `characters` 字段**绝对不要传全部项目角色**——LLM 会把其他角色的 appearance 混进当前画面。
正确做法（与前端 `_fetchFramePrompts()` 一致）：
```python
selected = set(scene.get("_scene_characters") or [])
chars_for_prompt = [c for c in all_chars if c["name"] in selected]   # 0 或 1 个
```

**v1.4.2 批量优化**：调用方有 N 个 scene 要批量跑时，**强烈推荐改用单 SSE 批量端点**
`POST /api/text-engine/generate-frame-prompts-batch`（每 frame 可带 `characters` 子集），
N 个 fetch 同时走会被 Chromium 单 origin HTTP/1.1 连接上限（6）卡住，30 个分镜的
批量生成 ≈ 6× 慢。批量端点用单连接 + SSE 流式回吐，后端 `settings.concurrency`
真生效。详见 [modules/text.md](./modules/text.md#批量-sse-端点-v142)。

### 4.3 出镜角色建议
```http
POST /api/text-engine/suggest-scene-characters
{ "description":"...","dialogues":[...],"all_names":["林夏","张川"],"manuscript":"..." }
→ { "characters": ["林夏"] }   // 仅返回 all_names 中存在的子集
```

### 4.4 持久化
```http
PUT /api/projects/{id}/scenes
{ "scenes": [...完整分镜数组...] }
```
保存后 `progress.scenes` 置 100。

## 5. 图片 (images)

### 5.1 工作流
- `GET /api/image-engine/workflows` → `["默认工作流","二次元"...]`
- `GET /api/image-engine/workflow/{name}` → 完整工作流 JSON（一般不需要客户端查看）

### 5.2 批量生成（推荐）
```http
POST /api/image-engine/generate-batch-stream
{
  "workflow_name": "lumicreate-基础-1.5",
  "gen_count": 3,              // 每帧并发份数
  "negative_prompt": "",
  "width": 0, "height": 0,     // 0 = 用设置中的默认
  "frames": [
    {"scene_id":"scene_001","frame_type":"start","prompt":"<英文>"},
    {"scene_id":"scene_001","frame_type":"end",  "prompt":"<英文>"}
  ]
}
```
SSE 事件类型（详见 `sse-events.md`）：
- `queued` / `progress` / `completed` / `error` / `batch_done`
- `completed.images = [{filename, data:<base64 png>, type}]`

### 5.3 持久化（1.3.4+ 推荐：分两步，避免一次性大 base64）

**单张图片落盘**：
```http
PUT /api/projects/{id}/images/slot
{ "scene_id":"scene_001","frame_type":"start","slot_index":0,"data":"<base64 png>" }
```

**元数据写入（含计数与已选 slot）**：
```http
PUT /api/projects/{id}/images/metadata
{
  "counts": {"scene_001:start":3,"scene_001:end":3},
  "selected": {"scene_001:start":0,"scene_001:end":1},
  "slot_keys": [
    {"scene_id":"scene_001","frame_type":"start","slot_index":0},
    ...
  ]
}
```

读取时图片走文件流，**不要把整 JSON 拉回**：
```http
GET /api/projects/{id}/images
→ slots[i].url = "/api/projects/{id}/images/file/{scene}_{frame}_{slot}.png"
```

## 6. 音频 (audio)

### 6.1 选择路径
- `dialogue_mode in {narration,dialogue,mixed}` → IndexTTS / GPT-SoVITS（按 `settings.audio_engine.engine_type`）
- `dialogue_mode == "reading"` → **Microsoft Edge TTS**（一镜一段，不分台词）

### 6.2 IndexTTS / GPT-SoVITS 批量
```http
GET /api/audio-engine/voice-refs        → ["bgm.wav","linxia.wav",...]
GET /api/audio-engine/emotion-refs      → [...]

POST /api/audio-engine/generate-batch-stream
{
  "gen_count": 1,
  "speed": 1.0,
  "dialogues": [
    {"scene_id":"scene_001","dialogue_id":"d0","text":"<台词>",
     "voice_ref":"linxia.wav","emo_ref":"emo_sad.wav","emo_weight":0.8}
  ]
}
```
SSE `completed` 事件结构：`{event:"completed", scene_id, dialogue_id, slot_index, data:"<base64 wav>", mime:"audio/wav"}`。**取 base64 用 `data` 字段，不是 `audio`**。

### 6.3 Edge TTS（朗读模式）
```http
POST /api/audio-engine/ms-tts
{ "text": "<整段分镜文本>", "voice": "zh-CN-XiaoxiaoNeural", "rate": "+0%" }
→ { "data": "<base64 mp3>", "duration_ms": N, "format": "mp3" }
```
常用 voice：晓晓 `XiaoxiaoNeural`（漫剧默认）、晓伊 `XiaoyiNeural`、云希 `YunxiNeural`、云扬 `YunyangNeural`。
rate 取值：`-50%` / `-25%` / `+0%` / **`+25%`（漫剧默认：快）** / `+50%`。

### 6.4 场景拼接（IndexTTS 模式必做）
```http
POST /api/audio-engine/stitch-scene
{
  "clips": [
    {"data":"<base64 wav>","pre_silence_ms":0,"post_silence_ms":300},
    ...
  ]
}
→ { "data":"<base64 wav>", "duration_ms": N }
```
拼接结果作为视频生成阶段的 `audio_b64`。

### 6.5 持久化（前端 hard-coded 的 key，写错前端看不到）

**reading 模式（Edge TTS，每镜一段 mp3）**：
```http
PUT /api/projects/{id}/audio
{
  "__ms_reading__scene_001": {"data":"<base64 mp3>","duration_ms":18420},
  "__ms_reading__scene_002": {"data":"<base64 mp3>","duration_ms":12300}
}
```

**普通模式（IndexTTS / GPT-SoVITS）**：
```http
PUT /api/projects/{id}/audio
{
  "scene_001:0": {                                      // 单段：{sceneId}:{dialogueIdx}
    "voiceRef":"linxia.wav","emoRef":null,
    "emoMethod":"与音色参考音频相同","emoWeight":0.8,
    "selectedSlot":0,
    "slots":[{"data":"<b64 wav>","duration":"4.3s"}, ...]
  },
  "scene_001:1": { ... },
  "__stitched__scene_001": {                            // 场景拼接结果
    "data":"<base64 stitched wav>","duration_ms":18420
  }
}
```

| 模式      | 单段 key                          | 场景汇总 key（视频引擎据此取音频） |
|-----------|-----------------------------------|------------------------------------|
| reading   | —（无单段）                       | `__ms_reading__{sceneId}`          |
| 其它模式  | `{sceneId}:{dialogueIdx}`         | `__stitched__{sceneId}`            |

后端按 payload 中 `v.data` 或 `v.slots[*].data` 任一存在判定该镜完成，并更新 `progress.audio`。
**视频页加载时自动把 `__ms_reading__{id}` 复制成 `__stitched__{id}`**——所以视频生成代码统一从 `__stitched__` 取，但 SKILL 客户端写入时仍必须按上表分模式选 key。

## 7. 视频 (videos)

### 7.1 视频提示词（每镜）
```http
POST /api/text-engine/generate-video-prompt
{
  "description":"...","dialogues":[...],"characters":[...],
  "start_frame_prompt":"...","end_frame_prompt":"...",
  "manuscript":"...","scene_index":N,"total_scenes":M
}
```
返回 SSE 流式英文 prompt（强调镜头运动 + 角色开口对白）。

**v1.4.2 批量**：批量 30 镜推荐用 `POST /api/text-engine/generate-video-prompts-batch`
（单 SSE 连接，N 条结果），见 [modules/text.md](./modules/text.md#批量-sse-端点-v142)。

可选：保存到 `PUT /api/projects/{id}/video-prompts` 以便下次复用：
```json
{ "scene_001": "...", "scene_002": "..." }
```

### 7.2 工作流（v1.4.2 硬白名单）
```http
GET /api/video-engine/workflows
→ ["flfa2i-lumicreate", "video_ltx2_3_i2v"]
```
仅这两个；用户 ComfyUI 目录里其它视频工作流不会出现在列表。

**提交前先查 kind**：
```http
GET /api/video-engine/workflow-info?workflow_name=video_ltx2_3_i2v
→ {kind:"video_i2v", requires_end_image:false, supports_audio:false, ...}
```
`video_i2v` 不需要末帧也不需要音频，仅靠首帧 + duration 出片。

### 7.3 分镜视频生成（顺序，单 GPU 不并发）
```http
POST /api/video-engine/generate-stream
{
  "workflow_name":"flfa2i-lumicreate",
  "resolution":"720x1280",          // 自动按 32 像素对齐
  "fps":25.0,                       // 24/25/30
  "scenes":[
    {
      "scene_id":"scene_001","scene_index":1,
      "start_image_b64":"...","end_image_b64":"...",
      "audio_b64":"<scene merged wav/mp3 base64>",
      "duration_ms":8000,
      "positive_prompt":"<英文视频 prompt>"
    }
  ]
}
```
SSE 事件：
- `scene_start{scene_id,scene_index,current,total}`
- `queued{prompt_id,scene_id}`
- `progress{value,max,scene_id}`
- `scene_retrying{scene_id,message}`（VRAM 自动重试）
- `scene_error{scene_id,scene_index,message}`（缺图/缺音/失败）
- `scene_done{scene_id,scene_index, video:"<b64 mp4>", filename, mime:"video/mp4"}`  ⚠️ 字段叫 **`video`**，不是 `video_b64`
- `batch_done{total}` + `[DONE]`

**视频引擎对 audio_b64 的处理**：后端 `_upload_audio` 始终命名为 `lumi_aud_{scene}.wav` 写入 ComfyUI input/，**内容是什么字节就写什么字节**。所以：
- reading 模式 `audio_b64` 是 mp3 base64 也能跑通（ComfyUI LoadAudio 节点用 ffmpeg/torchaudio 按内容识别）
- 客户端不需要、也不应该 `data:audio/mp3;base64,` 前缀；只传纯 base64 字符串
- 后端 ffmpeg 后处理（替换 AI 解码音轨）同样按内容识别，不依赖后缀

### 7.4 持久化
```http
PUT /api/projects/{id}/videos
[
  {"scene_id":"scene_001","data":"<base64 mp4>"},
  ...
]
```

### 7.5 合并所有分镜为成片
```http
POST /api/video-engine/merge-project-video
{ "project_id":"<id>","scene_order":["scene_001","scene_002",...] }
→ { "output_path":".../video/final_video.mp4", "output_dir":"<project dir>" }
```
后端用 ffmpeg `concat demuxer + -c copy`，**所有分镜必须 codec/分辨率一致**，由 LTX 工作流统一保证。

## 8. 字幕 (subtitle)

### 8.1 状态
```http
GET /api/subtitle-engine/status/{project_id}
→ { has_final_video, has_fixed_cfr, has_srt, has_embedded, srt_path, embedded_path }
```

### 8.2 取脚本（漫剧不推荐）
```http
GET /api/subtitle-engine/script/{project_id}
→ { "lines":["<scene_001 整段>",...], "count": N }
```
优先取每镜 dialogues.text，无台词时 fallback 到 description。漫剧 reading 模式下每行是整段，字幕过长——**改走 §8.3**。

### 8.3 字幕脚本断句（漫剧标准首步）
```http
POST /api/subtitle-engine/preprocess-text
{ "text":"<完整 manuscript 原文>" }
→ { "text":"按 ，。？！：""——… 与空白断行后的版本","lines":[...],"count":N }
```

后端 [services/subtitle.py:18](../../backend/services/subtitle.py#L18) 实现：把 `，。？！：""——…` 和任意空白都替换为换行，比手动分镜的 `_splitSentences`（仅 `。！？\n`）切得更碎。

**漫剧推荐组合**：
```python
ms = await api.get(f"/api/projects/{pid}/manuscript")
r  = await api.post("/api/subtitle-engine/preprocess-text", {"text": ms["content"]})
lines = r["lines"]   # 喂给下面的 generate-srt
```

### 8.4 生成 SRT（流式）
```http
POST /api/subtitle-engine/generate-srt
{
  "project_id":"...","lines":["...","..."],
  "fps":24,                       // 24|25|30
  "manual_advance":0.0,           // 整体时间偏移（秒）
  "model_name":"base"             // base|small|medium
}
```
SSE 步骤：
1. `normalize_fps` → 标准化帧率 → 生成 `video/fixed_cfr.mp4`
2. `extract_audio`
3. `load_model`
4. `align`（whisper 词级对齐）
5. `cut`
6. `write_srt` → 保存 `video/subtitles.srt`

### 8.5 烧录
```http
POST /api/subtitle-engine/embed
{ "project_id":"...","font_name":"等线 Bold","font_size":10 }
```
合法字体：`等线 Bold` / `微软雅黑` / `黑体` / `宋体` / `仿宋` / `楷体`。
SSE 中 `pct` 字段为 0~100 进度。
输出 `video/final_video_subbed.mp4`。

**字号默认（按视频方向自适应，不要照搬前端的 18）**：

| 分辨率              | 方向 | `font_size` |
|---------------------|------|-------------|
| `720x1280`（漫剧默认）| 竖屏 | **10**      |
| `1280x720`          | 横屏 | **16**      |
| 其它 `WxH`          | `W<H` → 竖屏 10；`W>H` → 横屏 16 | — |

读取当前分辨率：先查 `GET /api/projects/{id}` 或之前发起视频生成时用的 `resolution` 字段；找不到时默认竖屏（漫剧默认走竖屏）。

## 8.6 可选：音乐 / BGM（v1.4.2）

不是主管线步骤，但智能体若需要"AI 写歌"、"给视频加 BGM"应当用：

```http
# 1. AI 助写：根据简介 + 项目剧情自动产出 tags + 分段歌词
POST /api/text-engine/generate-music-prompt
{ "user_request":"...","language":"zh","duration_seconds":60,"bpm":120,
  "time_signature":"4","key_scale":"A minor","project_id":"<pid>","include_lyrics":true }
→ { "tags":"...", "lyrics":"[Intro]\n[Verse 1]\n..." }

# 2. ACE-Step 生成 mp3
POST /api/music/generate-stream
{ "duration_seconds":60,"bpm":120,"time_signature":"4","language":"zh","key_scale":"A minor",
  "tags":"...","lyrics":"...","project_id":"<pid>","seed":null }
→ SSE: queued → progress → completed{track_id,url}

# 3a. 把生成结果设为项目 BGM（下次合并视频时自动用，全程混响）
POST /api/music/track/{track_id}/set-as-bgm
{ "project_id":"<pid>" }

# 3b. 或在已成视频上后期叠加（视频流不重编码，秒级完成）
POST /api/video-engine/mix-bgm
{ "project_id":"<pid>","source":"final_video","track_id":<id>,
  "bgm_volume_db":-12,"original_volume_db":0,"fade_in_ms":800,"fade_out_ms":1500,"loop_bgm":true }
→ { "output_filename":"final_video_with_bgm.mp4", "duration_secs":... }
```

**关键点**：
- ACE-Step `seed` 字段：**`null` 必传**或省略 —— 后端会注入新随机数，不然每次出同一首
- AI 助写的 tags 不会写 BPM / 调式数字（结构化字段会被双倍套用）
- BGM 两条路：**3a 重合并**（与镜间过渡 + 全程 BGM 同源） vs **3b 后期叠加**（不重编码视频流）

完整接口见 [modules/music.md](./modules/music.md)。

## 9. 设置 (settings)

```http
GET  /api/settings            → 全量 AppSettings
POST /api/settings            → 必须传入完整 AppSettings（先 GET 再修改字段再 POST）
```
字段定义见 `references/modules/settings.md`。
