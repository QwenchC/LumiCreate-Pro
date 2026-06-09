---
name: lumicreate
description: 驱动 LumiCreate-Pro 本地 AI 视频创作流水线（文案 → 分镜 → 图片 → 音频 → 视频 → 字幕 → 音乐 / BGM）。当用户要求"用 LumiCreate / 用本地 AI 工具 创作视频"、"生成短剧/漫剧/解说/朗读视频"、"做 AI 文案+分镜+配音"、"调用 ComfyUI / IndexTTS / LTX-2.3 / ACE-Step 生成内容"、"批量出图/出视频/拼字幕"、"用 AI 写歌 / 生成 BGM / 给视频加背景音乐"，或对话中出现项目目录 LumiCreate-Pro / LumiCreate-Projects、API 端口 18520 时使用本 Skill。
---

# LumiCreate-Pro Skill

通过本地 FastAPI 后端 (`http://127.0.0.1:18520`) 驱动 LumiCreate-Pro 的端到端 AI 视频创作流水线。

## 漫剧 / 朗读视频默认配置（必读）

当用户说"做漫剧"、"做朗读视频"、"做解说视频"或没有明确指定对白模式时，**默认采用 `reading`（纯朗读，直读文案）模式 + 竖屏 + 手动分镜**：

| 配置项                   | 默认值                                                        | 来源                                          |
|--------------------------|---------------------------------------------------------------|-----------------------------------------------|
| `dialogue_mode`          | `reading`                                                     | 写入 `manuscript.config.dialogue_mode`        |
| **角色卡片**             | **文案→提取角色名→生成 role/traits/appearance→PUT characters**（漫剧必做） | 见 [character-cards.md](./references/character-cards.md) |
| **分镜划分方式**         | **角色感知"手动"分镜**（智能体按句切分，每段 ≤ 50 字符且出镜 ≤ 1 人） | **不调** `text-engine/generate-scenes`；客户端本地合并后 `PUT scenes`，详见 [manual-scenes.md](./references/manual-scenes.md) |
| **每镜出镜角色数上限**   | **1**（受限于本地文生图模型，多人物会角色融合/错位）          | 在切分阶段约束；无角色镜头（空镜）允许且推荐 |
| 分镜 id 后缀             | `_manual`（保持与前端一致：`scene_001_manual`）              | 同上                                          |
| 音频引擎                 | **微软 Edge TTS**（不是 IndexTTS）                            | `POST /api/audio-engine/ms-tts`               |
| 默认音色 (`voice`)       | `zh-CN-XiaoxiaoNeural`（晓晓）                                | ms-tts body                                   |
| 默认语速 (`rate`)        | **`+25%`（快）**                                              | ms-tts body                                   |
| 音频持久化 key           | **`__ms_reading__{sceneId}`**                                 | `PUT /api/projects/{id}/audio` 的 payload     |
| 视频 audio_b64 来源       | **直接用 ms-tts 返回的 mp3 base64**（不需要 stitch）          | video-engine 接受 mp3                          |
| **视频分辨率**           | **`720x1280`（竖屏 HD）**                                     | video-engine `resolution` 字段                 |
| 视频帧率                 | `25`                                                          | video-engine `fps` 字段                        |
| **视频生成路径**         | **有 GPU → LTX-2.3；无 GPU/低显存 → render-slideshow（图片放映 v1.4.6）** | `POST /api/video-engine/generate-stream` 或 `POST /api/video-engine/render-slideshow` |
| **字幕脚本来源**         | **`POST /api/subtitle-engine/preprocess-text`(manuscript 原文)** → lines | 比 `script/{id}` 切得更细（含逗号断句），符合字幕阅读节奏 |
| **字幕字号（按方向）**   | **竖屏 `720x1280` → `font_size=10`**<br>**横屏 `1280x720` → `font_size=16`** | `POST /api/subtitle-engine/embed` 的 `font_size` |
| 字幕字体                 | `等线 Bold`                                                   | embed `font_name`                              |

⚠️ **分镜默认走"手动"**：客户端**不要直接调 `text-engine/generate-scenes`**——LLM 倾向少分镜，单镜文本会过长导致单段视频时长超过 LTX 工作流上限或音频偏长。改成"按句切分 + 累积 ≤ 50 字符 → 一镜"的本地算法，宁可多分。

⚠️ **必须先建角色卡再分镜**：漫剧顺序固定为 文案 → **角色卡** → 分镜 → 出图。如果角色卡为空，"角色感知"切分会退化为纯字数切分，分镜可能挤进多人物 → 出图崩坏。角色卡建立流程见 [character-cards.md](./references/character-cards.md)。

⚠️ **每镜出镜 ≤ 1 人**：本地文生图（SDXL / Flux / Pony 等）对多人物极不稳定。`manual_split()` 用 `max_characters_per_scene=1`（默认）保证；遇到原文一句话同时点名两人时，算法会让该句独占一镜并发出 warning，**不要再合并相邻句子**。

⚠️ **出图前必须先跑提示词**：`scenes[i]._scene_characters` 只是名字列表，**不会**自动让出图带上角色 appearance。完整链路是：
1. `characters auto-build` 生成每个角色的英文 `appearance` 标签
2. **对每镜调 `text-engine/generate-frame-prompts`，把 `_scene_characters` hydrate 成 `characters.json` 里的完整对象**传过去（含 appearance）
3. 把返回的 `start_frame_prompt` / `end_frame_prompt` 回写到 `scenes[i]` 并 `PUT /scenes`
4. 出图前断言所有分镜的 frame_prompt 非空，否则 ComfyUI 会用空 positive_prompt 出随机图。

详细链路与典型病灶诊断见 [prompts.md](./references/prompts.md)。

⚠️ **批量提示词建议并发**：`prompts frame-batch` / `prompts video-batch` / `characters auto-build` 等遍历所有分镜的命令默认读 `settings.text_engine.concurrency` 并发。本地模型（Ollama/LM Studio）保持 **1–4**；云端高并发模型（DeepSeek v4-flash 上限 2500、Bailian 等）可设到 **50–500**，整片提示词生成从串行的几十分钟降到分钟级。CLI 可临时覆盖：`--concurrency 100`。

⚠️ **音频持久化 key 必须是 `__ms_reading__{sceneId}`**，否则前端"音频生成"页打不开预览。直接以 `{sceneId}` 为 key 写入会保存进文件但 UI 看不到。

⚠️ **视频生成前必须先生成图片**：reading 模式只省了音频拼接，每个分镜仍然需要 `start` / `end` 两张图。跳过图片步骤会得到 `scene_error: 缺少首帧图片`。

⚠️ **字幕字号要按方向自适应**：客户端调 `subtitle-engine/embed` 前先读视频引擎当前 `resolution`（或刚才生成时用的），分辨率 `WxH` 中 `W < H` 视为竖屏用 10，反之用 16。**不要无脑用前端默认 18**——漫剧竖屏 18 字号会盖住画面。

## 严格禁止 (NEVER DO)
- **不要直接修改项目目录文件**（如 `manuscript.md`、`scenes.json`、`images/*.png`），始终通过 API 写入；后端会维护进度元数据。
- **不要编造 `project_id` / `scene_id` / `dialogue_id`**：必须先调用列表/获取接口，从返回值中提取。
- **不要将大体积二进制（图片/视频/音频）粘贴到对话**：通过 base64 / 文件 URL 字段引用，必要时通过 `/api/projects/{id}/images/file/{filename}` 直接拉取。
- **不要跳过对白模式 (dialogue_mode) 的传递**：`reading`（纯朗读）与其它模式走完全不同的代码路径，错传会导致分镜/音频结构不兼容。
- **不要在 ComfyUI / IndexTTS / Edge-TTS / ffmpeg 未运行时调用对应接口**：先 `GET /test` 探活，向用户报告再继续。
- **不要并发触发同一项目的多个写接口**（如同时 PUT scenes 又 PUT manuscript），LumiCreate 用整文件覆盖，会丢数据。
- **不要把 audio 用 `{sceneId}` 直接作为 key 写入**（reading 模式必须 `__ms_reading__{sceneId}`，普通模式 stitch 结果必须 `__stitched__{sceneId}`，单段必须 `{sceneId}:{idx}`）。**写错 key 不会报错，但前端看不到**。
- **不要在视频/音频 SSE 事件里假设字段叫 `video_b64` / `audio`**：视频 `completed`/`scene_done` 用 **`video`** 字段，音频 `completed` 用 **`data`** 字段（含 base64）。

## 严格要求 (MUST DO)
- 所有 HTTP 调用 base URL 固定为 `http://127.0.0.1:18520`；中文文本一律 **UTF-8** 编码，不加 BOM。
- 流式接口（generate-stream、generate-batch-stream、generate-manuscript、generate-srt、embed）必须按 **SSE (`text/event-stream`)** 解析；遇到 `data: [DONE]` 结束。
- 任何破坏性操作（`DELETE /api/projects/{id}`、覆盖已有 `final_video.mp4`、ffmpeg 合并、字幕烧录）执行前必须 **先向用户展示影响范围并取得明确同意**。
- 写入文案/分镜/音频/视频/字符等数据前先 **GET 当前状态**，在内存中合并字段后整体 PUT，避免覆盖用户其它字段。
- 引用项目本地资源（图片/音频/视频）时优先使用 **`/api/projects/{id}/images/file/{filename}` 等文件流端点**；只有必须传 base64 的字段（如视频生成的 `start_image_b64`）才走 base64。

## 模块总览

| 模块         | 用途                                                                 | 参考文件                                              |
|--------------|----------------------------------------------------------------------|-------------------------------------------------------|
| `settings`   | 引擎配置（文本/图片/音频/视频），全局项目根目录                       | [settings.md](./references/modules/settings.md)       |
| `project`    | 项目 CRUD、文案/分镜/角色/图片/音频/视频元数据读写                   | [project.md](./references/modules/project.md)         |
| `text`       | LLM 生成文案、分镜、首/尾帧提示词、视频提示词、角色描述、出镜建议    | [text.md](./references/modules/text.md)               |
| `image`      | ComfyUI 图片生成（单张/批量并发 SSE），工作流管理                     | [image.md](./references/modules/image.md)             |
| `audio`      | IndexTTS-2.0 / GPT-SoVITS / Microsoft Edge TTS 语音合成与场景拼接   | [audio.md](./references/modules/audio.md)             |
| `video`      | LTX-2.3 视频生成；**v1.4.6** 新增 render-slideshow（无 GPU 通路）+ 合并通路 WMP 兼容修复；**v1.4.10** 新增火山引擎 Seedance 2.0 云端 API 通路 | [video.md](./references/modules/video.md) / [volcengine-seedance.md](./references/modules/volcengine-seedance.md) |
| `subtitle`   | stable-whisper 字幕生成 + 烧录                                       | [subtitle.md](./references/modules/subtitle.md)       |
| `music`      | **v1.4.2** ACE-Step v1.5 音乐生成 + 全局音乐库 + 项目 BGM 直通       | [music.md](./references/modules/music.md)             |
| `sfx`        | **v1.4.8** 音效 (SFX) 库 + 项目时间轴，每镜次点状音效叠加（脚步/关门/抽刀）；slideshow 渲染时直接烧进 mp4 | [sfx.md](./references/modules/sfx.md)                 |
| `prompts`    | **v1.4.9** 全局提示词标签库（画风/构图/光照/情绪/角色/画质/负面词，~60 内置 + 用户自定义）；TitleBar 💡 弹窗，按类目点击 → 撰写区 → 一键复制 | [prompts.md](./references/modules/prompts.md)         |

通用约定与流水线骨架见 [pipeline.md](./references/pipeline.md)。
SSE 事件格式速查见 [sse-events.md](./references/sse-events.md)。
对白模式（dialogue_mode）差异详解见 [dialogue-modes.md](./references/dialogue-modes.md)。
角色 appearance 注入提示词链路见 [prompts.md](./references/prompts.md)（出图与目标不符时**必读**）。

## 意图判断决策树

用户提到"**漫剧 / 朗读视频 / 解说视频 / 直读文案**" → 锁定 `dialogue_mode="reading"` + Edge TTS + `rate="+25%"` + 竖屏 `720x1280` + **角色卡** + 角色感知手动分镜（≤1 人）+ 字幕字号 10，参考 [character-cards.md](./references/character-cards.md)、[dialogue-modes.md](./references/dialogue-modes.md) 与 [manual-scenes.md](./references/manual-scenes.md)
用户提到"创建项目 / 新项目 / 文件夹组织" → `project`（create / folder）
用户提到"写文案 / 生成剧本 / 续写文案 / 改写" → `text` (generate-manuscript) → 保存 `project` (PUT manuscript)
用户提到"分镜 / 切分 / 切场景 / 镜头列表"：
  - 漫剧/朗读 → **手动分镜**（本地按句切分 + ≤ 50 字符合并 + PUT scenes），见 [manual-scenes.md](./references/manual-scenes.md)
  - 短剧/创作型 → `text` (generate-scenes) → 保存 `project` (PUT scenes)
用户提到"首帧 / 末帧 / 图片提示词 / 出图提示词 / 英文 prompt" → `text` (generate-frame-prompts) — **调用前必须 hydrate `_scene_characters` 为完整角色对象**，否则 prompt 不带 appearance；详见 [prompts.md](./references/prompts.md)
用户提到"角色 / 角色设定 / 角色描述 / 角色外观 / 出镜角色检测" → `text` (generate-character-* / suggest-scene-characters)
用户提到"出图 / 生成图片 / 批量出图 / ComfyUI 跑图" → `image` (generate-stream / generate-batch-stream)
用户提到"配音 / TTS / 朗读 / 音色克隆 / IndexTTS / Edge TTS" → `audio` (generate-stream / ms-tts) → `audio` (stitch-scene)
用户提到"视频生成 / LTX / 首末帧驱动视频 / 分镜视频 / 合并视频" → `video` (generate-stream → merge-project-video)；**用户说"无 GPU / 显存不够 / 跑不动 LTX / 图片放映视频"** → **`video render-slideshow`（v1.4.6）** → merge-project-video
用户提到"火山引擎 / Seedance / 云端视频 / API 生成视频 / 高质量视频" → 设置页切到 `engine_type='volcengine_seedance'`（v1.4.10），同套 generate-stream 端点自动 dispatch 到云端 Ark API。详见 [volcengine-seedance.md](./references/modules/volcengine-seedance.md)
用户提到"试播 / 预览 / 看看节奏 / 合并前预览" → **v1.4.8 前端 PreviewPlayer 串播分镜素材**（无后端调用，浏览器顺序播 video / image+audio / image-only）；合并前不出文件
用户提到"音效 / SFX / 脚步声 / 关门声 / 抽刀声 / 给画面加音效" → `sfx`（v1.4.8 上传 + 时间轴）→ 下次跑 `render-slideshow` 时**自动烧进**镜次 mp4。详见 [sfx.md](./references/modules/sfx.md)
用户提到"提示词 / 标签 / 画风 / 光照 / 构图 / 复制提示词 / 自定义提示词" → **`prompts`（v1.4.9 全局插件）**：TitleBar 💡 按钮打开弹窗 → 按类目点击标签 → 撰写区合成 → 一键复制；可以新增 / 删除自定义标签，内置 ~60 词受保护。详见 [prompts.md](./references/modules/prompts.md)
用户提到"字幕 / SRT / 烧字幕 / Whisper / 硬字幕" → `subtitle`（**漫剧**：manuscript → `preprocess-text` → generate-srt → embed；**非漫剧**：`script` → generate-srt → embed）
用户提到"配置 / 模型 / 引擎 / API key / ComfyUI 地址" → `settings`

**关键区分**：
- `text generate-manuscript`（流式 SSE）↔ `project PUT /manuscript`（持久化）——LLM 出文本后必须显式保存。
- `text generate-scenes`：`dialogue_mode="reading"` 走服务端纯文本切句（无 LLM），其它模式走 LLM；返回结构相同。
- `audio generate-stream` (IndexTTS/GPT-SoVITS) ↔ `audio ms-tts`（Edge TTS）：**纯朗读模式专用 Edge TTS**，其余模式用 IndexTTS。
- `image generate-stream`（单张）↔ `generate-batch-stream`（全分镜 × N 并发）：批量自动跳过已有图。
- `video generate-stream`：**强制要求每个 scene 同时具备 start_image_b64 / end_image_b64 / audio_b64**，缺一报 `scene_error` 跳过。
- `subtitle generate-srt`：要求 `final_video.mp4` 已存在（即所有分镜 video 已合并）。
- `project PUT /images`（含图片数据）↔ `project PUT /images/metadata`（仅元数据）：1.3.4 后图片落盘改为单张 `PUT /images/slot` + `PUT /images/metadata`，**禁止重新上传已有图片的 base64**。

## 危险操作确认

以下操作不可逆或会覆盖用户成果，**执行前必须显示操作摘要并获得用户明确同意**：

| 模块       | 操作                                            | 说明                                                                 |
|------------|-------------------------------------------------|----------------------------------------------------------------------|
| `project`  | `DELETE /api/projects/{id}`                      | 删除整个项目目录（文案/分镜/图片/音频/视频/字幕全部删除）            |
| `project`  | `PUT /api/projects/{id}/manuscript` 覆盖已有内容 | 文案会整体覆盖，请先 GET 并征求"覆盖/扩写"意图                       |
| `project`  | `PUT /api/projects/{id}/scenes` 在已生成图/音后  | 重排或删除分镜会导致后续图片/音频/视频与新分镜不再匹配               |
| `image`    | `generate-batch-stream` 已有图片场景             | 默认跳过已有，但 `gen_count > 已有数` 会新增 slot；用户可能想保留旧图 |
| `video`    | `generate-stream`                               | 单分镜单次 30s~3min GPU 推理，批量耗时长，用户应确认                 |
| `video`    | `merge-project-video`                           | 覆盖 `video/final_video.mp4`，可能丢失上次合并结果                   |
| `subtitle` | `embed`                                         | 覆盖 `final_video_subbed.mp4`                                        |
| `settings` | `POST /api/settings`                            | 全量覆盖；必须先 GET → 修改 → POST，否则丢失其它字段                  |

### 确认流程
```
Step 1 → 展示操作摘要（操作类型 + 目标对象 + 影响范围 + 不可逆性）
Step 2 → 用户明确回复确认（"确认" / "执行" / "好的"）
Step 3 → 调用接口
```

## 核心流程

作为创作助手，**首要任务是理解用户的完整创作意图与已有进度**，不可直接跳到某一步执行：

### 1. 探活 + 定位
- `GET /api/health` 探活后端；任一外部引擎（ComfyUI、IndexTTS、edge-tts、ffmpeg）报错时先告知用户。
- `GET /api/projects` 列出现有项目；若用户没指定项目，**先询问"使用现有项目还是新建？"**。

### 2. 读取上下文
进入项目后立即读：
- `GET /api/projects/{id}/manuscript`（含 config: length/audience/style/tone/theme/worldview/characters/dialogue_mode）
- `GET /api/projects/{id}/scenes`
- `GET /api/projects/{id}/characters`
- `GET /api/projects/{id}/images`（仅元数据，url 字段引用文件流）
- `GET /api/projects/{id}/audio`
- `GET /api/projects/{id}/videos`（注意：会返回所有视频的 base64，列表用项目 meta 的 progress 判断更轻量）

根据 `progress.{manuscript|scenes|images|audio|video}` 判断当前阶段，**只问下一步需要的信息**，不要重复让用户填已有数据。

### 3. 按对白模式分流
读取 `manuscript.config.dialogue_mode`，**强制按下表选择路径**——这是最常见的执行错误来源：

| dialogue_mode | 分镜生成                       | 音频生成                            |
|---------------|--------------------------------|--------------------------------------|
| `narration`   | LLM 出旁白型分镜               | IndexTTS（每段台词独立）             |
| `dialogue`    | LLM 出纯对话型分镜             | IndexTTS（每段台词独立）             |
| `mixed`       | LLM 出混合型分镜               | IndexTTS                             |
| `reading`     | **服务端纯文本切句，无 LLM**   | **Edge TTS（`/api/audio-engine/ms-tts`）** |

详见 [dialogue-modes.md](./references/dialogue-modes.md)。

### 4. 流水线执行
完整流程见 [pipeline.md](./references/pipeline.md)，简版骨架：

```
manuscript  → text.generate-manuscript (SSE) → project.PUT /manuscript
scenes      → text.generate-scenes        → project.PUT /scenes
characters  → text.generate-character-*   → project.PUT /characters
prompts     → text.generate-frame-prompts → 写回 scenes[i].start_frame_prompt/end_frame_prompt
images      → image.generate-batch-stream (SSE) → project.PUT /images/slot + /images/metadata
audio       → audio.generate-batch-stream / ms-tts (SSE) → audio.stitch-scene → project.PUT /audio
video       → video.generate-stream (SSE) → project.PUT /videos → video.merge-project-video
subtitle    → subtitle.script → subtitle.generate-srt (SSE) → subtitle.embed (SSE)
```

### 5. 错误与重试
- ComfyUI 视频生成遇到 `should be the same` (CUDA/CPU 权重错配) 已由后端自动 free + 重试一次；若仍失败需要用户检查显存。
- LLM 返回非 JSON（分镜/提示词期望 JSON 结构）后端会尝试正则提取 `[...]` / `{...}`；若仍失败应提示用户切换更强模型。
- 字幕生成超时上限 300s，烧录 600s；接近上限时主动告知用户视频可能过长。

## 快速调用约定

- 推荐通过 `scripts/lumi.py`（Python）或 `scripts/lumi.sh`（curl）发起调用，避免在对话里手写长 JSON 体。
- 所有脚本默认 base URL 为 `http://127.0.0.1:18520`，可通过环境变量 `LUMI_API` 覆盖。
- 中文路径与文件名在 Windows 上务必走 API（后端读 `utf-8-sig` 兼容 BOM），**不要让用户用 PowerShell 直接编辑** UTF-8 JSON 文件。
