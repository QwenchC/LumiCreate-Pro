# LumiCreate-Pro

一个本地AI视频创作工具，集成文案生成、分镜设计、图片生成、音频生成、视频生成并合成于一体。

## 项目架构

- **前端**：Vue 3 + Vite + Electron
- **后端**：FastAPI (Python) + ComfyUI（图片/视频生成）+ IndexTTS-2.0（语音合成）
- **数据存储**：本地 JSON 文件 + 项目目录文件系统

## 核心功能

### 📝 文案创建
- **智能生成配置**：篇幅、目标受众、故事风格、故事基调、世界观设定、主要角色列表（姓名 + 定位 + 性格特征）
- **对白模式**：纯旁白 / 纯对话 / 旁白+对话混合 / **纯朗读（直读文案）**
- 基于配置 LLM 流式生成，支持在现有内容基础上改写
- 角色、世界观、基调等全部注入生成提示词，确保内容一致
- 配置与文案内容一起持久化保存，重新进入自动恢复

### 🎞 分镜设计
- 从文案自动生成分镜提纲，分镜生成时自动传入对白模式与主要角色配置
- **对白模式感知**：LLM 严格遵守所配置的对白模式；**纯朗读模式**无需 LLM，直接按句分割文案（每段 ≤28 秒），一键生成全部分镜
- **图片提示词与分镜分离**：先划分分镜，再按需生成首帧/尾帧英文提示词（单个分镜或批量全部）
- 编辑分镜描述、首帧/尾帧提示词、预估时长
- 添加 / 删除 / 重排分镜；**清空全部分镜**按钮
- 台词管理（角色 + 台词 + 情感）
- 可滚动分镜列表，支持大量分镜

### 🖼 图片生成
- 集成 ComfyUI 工作流
- Master-detail 分割布局
- 支持多工作流选择，自动保存工作流选择
- 批量生成（跳过已有图片）、单个分镜生成、单帧操作
- 图片预览和管理，WebSocket 流式进度更新
- 生成图片自动持久化保存/加载

### 🎙 音频生成
- 集成 **IndexTTS-2.0**（Gradio API，本地运行）及 **GPT-SoVITS**
- 分镜分组展示，每段音频独立配置音色参考、情感控制与情感权重
- 每段音频支持多版本生成（V1/V2/V3…），可单独试听、切换版本
- 可调整每段前/后静音时长（ms）
- **场景音频合并**：一键拼接场景内所有片段（含静音）为单个 WAV，供视频工作流使用
- **纯朗读模式**：自动切换为微软 Edge 神经语音（TTS）
  - 支持 10 种中文神经语音（晓晓/晓伊/云希/云扬等）
  - 可调节语速（很慢/慢/正常/快/很快）
  - 每个分镜独立生成一段语音，支持单独重新生成
  - 实时音频播放器预览，时长自动从音频元数据读取
  - 批量生成全部分镜语音并持久化
- 合并结果页内预览，持久化保存
- 支持手动导入模式

### 💬 字幕生成
- 内嵌字幕生成流水线：视频帧率标准化 → 音频提取 → **stable-whisper** 词级时间戳对齐 → SRT 输出
- 字幕脚本支持手动编辑、从分镜台词一键导入、断句工具（自动按标点切句）、从文案页复制原稿
- 可配置 Whisper 模型（base / small / medium）、帧率（24/25/30fps）、整体时间偏移
- SRT 生成带步骤式进度条（帧率标准化 → 提取音频 → 加载模型 → Whisper 对齐 → 切分时间戳 → 写入 SRT）
- 字幕烧录（hardcode）进视频：可选字体（等线 Bold / 微软雅黑 / 黑体 / 宋体 / 仿宋 / 楷体）及字号，实时百分比进度条
- 自动检测并优先使用帧率标准化后的 `fixed_cfr.mp4` 作为烧录源，保证时间轴吻合

### 🎬 视频生成
- 集成 **LTX-2.3** ComfyUI 工作流（首帧→末帧→音频驱动生成）
- LiteGraph UI 格式工作流自动转换为 ComfyUI API 格式（`_litegraph_to_api`）
  - 处理 SetNode/GetNode 传送对、Bypass 节点、虚拟节点过滤、UI-only 输入过滤等边缘情况
- 多分辨率支持（720p/576p/544p，竖屏/横屏），可选帧率（24/25/30fps）
- 每个分镜卡片展示就绪状态（首帧 / 末帧 / 合并音频）、生成进度条、视频预览
- 视频完成后自动用用户原始音频替换 AI 生成音频（通过 ffmpeg）
- 生成视频持久化保存，重新进入页面自动恢复预览
- **分镜合并**：所有分镜生成完毕后，一键 ffmpeg concat 合并为完整 MP4，保存到项目目录，支持直接打开或在文件夹中显示
- 视频提示词根据场景台词自动生成（角色开口对白描述）

## 安装与运行

### 前端设置
```sh
cd renderer
npm install
npm run dev      # 开发模式（Vite + HMR）
npm run build    # 生产构建
npx electron .   # 运行 Electron 应用
```

### 后端设置
```sh
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py   # 启动 FastAPI 服务 (http://localhost:18520)
```

- **外部依赖**
- **ComfyUI**：负责图片和视频生成，需单独安装并运行
- **IndexTTS-2.0**：负责语音合成，通过 Gradio API 调用（非朗读模式）
- **edge-tts**：微软神经语音（纯朗读模式，无需 API Key，`pip install edge-tts`）
- **ffmpeg**：用于音频替换和视频合并（可从 ComfyUI `.ext/Library/bin/` 自动检测）

## 项目结构

```
LumiCreate-Pro/
├── renderer/                   # Vue 3 + Electron 前端
│   ├── src/
│   │   ├── views/              # 页面（HomeView, ProjectView, SettingsView）
│   │   ├── components/
│   │   │   └── tabs/           # 功能标签页（AudioTab, VideoTab, ImageTab…）
│   │   ├── assets/             # 样式/资源
│   │   ├── router/             # Vue Router
│   │   └── main.js
│   ├── index.html
│   └── vite.config.js
├── backend/                    # FastAPI 后端
│   ├── routers/
│   │   ├── projects.py         # 项目 CRUD（场景/图片/音频/视频 存取）
│   │   ├── image_engine.py     # 图片生成 SSE 流
│   │   ├── audio_engine.py     # 音频生成 SSE 流（IndexTTS / GPT-SoVITS）
│   │   ├── text_engine.py      # 文案/分镜 LLM 生成
│   │   ├── video_engine.py     # 视频生成 SSE 流 + 分镜合并
│   │   ├── subtitle_engine.py  # 字幕生成 + 烧录 SSE 流
│   │   └── settings.py         # 全局设置读写
│   ├── services/
│   │   ├── comfyui.py          # ComfyUI API 封装 + LiteGraph→API 转换器
│   │   ├── ltx2video.py        # LTX-2.3 视频生成（上传/补丁工作流/拉取结果/音频替换）
│   │   ├── indextts.py         # IndexTTS-2.0 Gradio API
│   │   ├── gptsovits.py        # GPT-SoVITS API
│   │   ├── msedge_tts.py       # 微软 Edge 神经语音（纯朗读模式）
│   │   ├── subtitle.py         # 字幕处理（帧率标准化/音频提取/Whisper对齐/SRT生成/字幕烧录）
│   │   ├── llm.py              # LLM 推理（Ollama / OpenAI 兼容）
│   │   └── prompts.py          # Prompt 模板
│   ├── config.py               # 设置模型与加载
│   ├── main.py                 # FastAPI 应用入口
│   └── requirements.txt
├── electron/
│   ├── main.js                 # Electron 主进程（窗口 / IPC / shell 操作）
│   └── preload.js              # contextBridge API 暴露
├── SKILL/                      # OpenClaw 智能体 Skill（意图声明 + API 参考 + 示例脚本）
├── .gitignore
└── README.md
```

## 配置

全局设置存储在：`%APPDATA%/LumiCreate-Pro/settings.json`

支持的引擎配置：

| 引擎 | 配置项 |
|------|--------|
| **文本引擎** | Ollama / LM Studio / DeepSeek / 阿里云百炼（通义千问）/ 任意 OpenAI 兼容端点 |
| **图片引擎** | ComfyUI URL + 工作流目录 |
| **音频引擎** | IndexTTS-2.0 Gradio URL、音色/情感参考目录、默认音色/权重；朗读模式自动使用微软 Edge TTS |
| **视频引擎** | ComfyUI URL + 工作流目录 + ComfyUI input/ 目录 + 默认分辨率/帧率 |

## OpenClaw 智能体接入（SKILL）

LumiCreate-Pro 提供标准 **SKILL.md** 规范接口，可被 [OpenClaw](https://openclaw.ai) 等兼容智能体直接调用，实现端到端 AI 视频创作流水线的自动化驱动。

```
SKILL/
├── SKILL.md              # 技能声明（意图判断 / 调用规范 / 危险操作确认）
├── references/
│   ├── pipeline.md       # 完整流水线骨架与 SSE 消费示例
│   ├── dialogue-modes.md # 四种对白模式差异（旁白/对话/混合/朗读）
│   ├── manual-scenes.md  # 角色感知手动分镜算法（漫剧推荐）
│   ├── character-cards.md# 角色卡建立与 appearance 注入
│   ├── prompts.md        # 首/尾帧 & 视频提示词生成链路
│   ├── sse-events.md     # SSE 事件格式速查
│   └── modules/          # 各模块 API 接口文档
└── scripts/
    ├── lumi.py           # 完整功能 CLI（httpx）
    ├── lumi.sh           # bash 轻量版包装
    ├── end_to_end_example.py  # 端到端流水线示例脚本
    └── README.md         # 脚本使用说明
```

智能体在对话中出现以下意图时会自动激活本 Skill：「用 LumiCreate 生成视频」「做漫剧 / 解说视频 / 朗读视频」「调用 ComfyUI / IndexTTS / LTX-2.3」「批量出图 / 出视频 / 拼字幕」。

## 更新日志

### v1.4.5
本版本以 **Pollinations 云端图片生成引擎** 为主线，让无 GPU 用户也能跑漫剧出图。同时收紧布局/参数防御。

- ✅ **Pollinations 引擎**：`settings.image_engine.engine_type` 一字段切 ComfyUI ↔ Pollinations，配合 `pollinations_base_url / pollinations_api_key / pollinations_model` 三个字段；上层端点 (`/workflows`, `/workflow-info`, `/generate-stream`, `/generate-batch-stream`) 内部 dispatch，前端 UI 行为不变（仍是"选模型 → 输入 prompt → 生成"）
- ✅ **后端 `services/pollinations_image.py`**：
  - `generate_image_pollinations()` —— 单图 GET 模拟成 ComfyUI 风格 SSE 事件流（queued → progress 伪进度 → completed / error）；`seed=None` 强制随机注入；`?key=` 走 query 防 CDN 代理掉 header
  - `fetch_pollinations_image_models()` —— 拉 `/image/models` 活的模型列表，失败回退 `DEFAULT_POLLINATIONS_IMAGE_MODELS` 兜底
  - `test_pollinations_connection()` —— 连通性 + API key 校验（调 `/account/key` 返 key 类型）
- ✅ **路由分派**：`/workflows` 在 Pollinations 模式直接返模型列表；`/workflow-info` 返回 `{kind:"t2i", engine_type:"pollinations", ref_count:0}` —— 自动隐藏参考图槽、SD 高级面板
- ✅ **URL 参数收紧**：严格按 `gen.pollinations.ai` 白名单 `model / width / height / seed / key`，不传旧版的 `nologo / private`（这两个会触发 `400 Query parameter validation failed`）
- ✅ **错误诊断增强**：4xx JSON 错误解析 `error.details / issues / errors` 字段并拼到消息里，能立即定位是哪个 query 参数被拒绝
- ✅ **设置页**：图片引擎 tab 上方加 ComfyUI / Pollinations radio；Pollinations 模式下显示 base URL / API key (password 输入) / 默认模型下拉 / 「↻ 刷新模型列表」/「🔌 测试连接」按钮
- ✅ **图片生成页 toolbar 布局修复**：68 个 Pollinations 模型让工作流下拉变宽，「全部生成」按钮被挤换行 + 画风下拉与「每帧张数」label 重叠 —— 改 `flex-wrap: nowrap` + 按钮 `flex-shrink: 0` 锁住 + 画风选择器用专属类 `style-preset-select` 替换 inline 样式，91-150px 自适应
- ✅ **测试 + 集成**：后端 **236 / 236 pytest 通过**（v1.4.4 时 225 个），新增 11 个回归测覆盖 URL 构造白名单 / 完整流程 base64 一致性 / 401 解析 / 200 非图片诚实拒绝 / 模型列表解析 + 离线兜底 / engine_type 路由分派 / 400 details 透出（钉死本轮"validation failed"诊断改进）

### v1.4.4
本版本以 **通用 Stable Diffusion 工作流支持** 为主线，把 SD 的完整调参面板（Checkpoint / LoRA 链 / 采样器 / 调度器）暴露到图片生成页。

- ✅ **新增 sd_default_workflow 工作流**：通用 SD t2i + 7 槽 LoRA 链，加入 `SUPPORTED_IMAGE_WORKFLOWS` 硬白名单；分类器返 `t2i`
- ✅ **后端 `services/sd_workflow.py`**：
  - `patch_sd_workflow()` deep-copy 原工作流后写 widgets；用户传 N 个 LoRA → 链头 N 个槽位 enabled、剩余 `7-N` 个 `mode=4` bypass；name 为 `"None"/"none"` 或 strength=0 视为禁用 + bypass
  - 借用 `_litegraph_to_api` 已有的链路穿透机制，让 KSampler.model 引用正确绕过 bypassed LoRA 节点
  - `fetch_sd_model_info()` 从 ComfyUI `/object_info` 抽 4 个枚举（checkpoints / loras / samplers / schedulers）；ComfyUI 离线时返空列表 + error，不抛 500
- ✅ **新增 `GET /api/image-engine/model-info`**：给前端下拉填可选模型
- ✅ **请求 schema 扩展**：`SingleGenerateRequest` 和 `BatchGenerateRequest` 新增 `sd_params: SdParams | None`（含 `checkpoint / loras: [{name, strength}] / steps / cfg / sampler_name / scheduler`）；仅当 `workflow_name == "sd_default_workflow"` 时生效
- ✅ **前端 `SdParamsPanel.vue`**：可折叠面板，含 Checkpoint 下拉 + 动态增删 LoRA 链（0–7 行）+ 负面提示词 textarea + 4 项 KSampler 控件；自动从 `/model-info` 拉枚举；ImagesTab 检测到 `sd_default_workflow` 选中时挂载
- ✅ **SKILL 同步**：`modules/image.md` 新增"SD 工作流参数化（v1.4.4）"章节，含 `model-info` schema、`sd_params` 请求示例、LoRA bypass 机制、节点 ID 映射
- ✅ **测试 + 集成**：后端 **225 / 225 pytest 通过**（v1.4.3 时 215 个），新增 10 个回归测覆盖 SD 分类 / 硬名单 / Checkpoint + KSampler 补丁 / 7 槽 LoRA 链补丁 / 0–N 个 LoRA / `name='none'` 或 `strength=0` 禁用 / 不污染原工作流 / KSampler.model 正确穿透 bypassed LoRA / `/model-info` 离线兜底 / `/object_info` 正常解析

### v1.4.3
本版本聚焦 **i2i 工作流的灵活参考图支持** + **UI 槽位清理**。

- ✅ **i2i 工作流分类修复**：`classify_workflow` 改为节点数优先于名字关键词。`image_flux2_klein_image_edit_9b_base` 之前因名字含 `image_edit` 被强行判 `i2i_single`（只显示 1 个参考图槽位），现在按真实 LoadImage 数（展平 subgraph 后）正确识别为 `i2i_double`
- ✅ **新增 `i2i_multi` kind**：支持 3+ LoadImage 节点的工作流，`ref_count` 按真实节点数（上限 8 防 UI 撑爆）；`get_image_workflow_ref_count` 单一来源决定槽位数
- ✅ **单图驱动双图工作流**：参考图数 < LoadImage 节点数时，后端 `_inject_ref_images` 自动**复制最后一张 ref 填满剩余节点**。双图工作流既可单参考（语义=单图编辑）也可双参考（语义=双图合成）；前端验证从"严格等于"放宽到"≥ 1"
- ✅ **空槽自动剪枝 + 手动删除**：`getFrameSlotCount` 自动剪掉尾部 N 个空槽（保留中间断档以免位置错位），仍以 `genCount` 为下限；空槽 / 错误槽 hover 出现 🗑 删除按钮（之前只有图片槽可删）
- ✅ **测试 + 集成**：后端 **215 / 215 pytest 通过**（v1.4.2 时 207 个），新增 8 个回归测覆盖 Flux.2 强制 i2i_double / i2i_multi 节点扫描 / N 上限 / 硬名单 / 单图复制填槽 / 0 张拒绝 / 超出节点数拒绝

### v1.4.2
本版本以 **音乐生成（ACE-Step v1.5）** + **后期 BGM 混音** + **LLM 真实并发突破 Chromium 连接上限** 为主线。

- ✅ **音乐生成页（ACE-Step v1.5）**：项目内 🎵 tab + 主屏「🎵 音乐库」入口共用 `MusicGenerator` 组件；6 个结构化字段（时长 / BPM / 拍号 / 语言 / 调式 / 名字）+ 标签 textarea + 歌词 textarea；强制注入随机 seed 避免重复出同一首；「🔒 固定 seed」复选框可复现一首；「🧹 清理失效」一键删除丢失文件 / 体积 < 1KB 的"幽灵"条目
- ✅ **AI 助写**：「✨ AI 助写」按钮 → 用户输入简介 → LLM 同时产出"标签段落"+"分段歌词"（`[Intro] [Verse 1] [Chorus] [Outro]` 等英文标记，中文歌词主体）；系统提示双层禁止把 BPM / 拍号 / 调式 / 时长抄进标签段落（防参数双倍套用）；项目级可注入 `manuscript.txt` 片段让歌词贴合剧情
- ✅ **后期 BGM 混音**：合并视频 / 烧字幕完成后「🎵 添加 BGM」→ 共用 `BgmMixerDialog`；从音乐库选歌 → BGM/原音量滑块 + 淡入淡出 + 循环开关 → ffmpeg `-c:v copy` 不重编码视频流、只重编码音轨，秒级完成；输出 `<source>_with_bgm.mp4`
- ✅ **项目 BGM 直通**：音乐库每首歌「📌 设为 BGM」一键复制到 `<project>/bgm/bgm.<ext>`，下次合并视频时由 merge 端点自带 BGM 通道处理
- ✅ **真实 LLM 并发突破 Chromium 单 origin 连接上限**：发现批量提示词生成卡在 ~5 并发的真实原因 —— Chromium 对单 origin HTTP/1.1 连接数限制 = 6，前端就算 fire 50 个 fetch 也只放 6 个出去；新增 3 个**批量 SSE 端点** `/generate-frame-prompts-batch` / `/suggest-scene-characters-batch` / `/generate-video-prompts-batch`，前端只开 1 个连接吃 N 条任务，后端用 `asyncio.Semaphore(settings.concurrency)` 真并发；30 个分镜的视频提示词生成提速 ~6×
- ✅ **PrimitiveNode 内联**：修复 ComfyUI 400 "Node 'Song Duration' not found" —— 老式 `PrimitiveNode` 是 LiteGraph UI-only 常量源，必须把 `widgets_values[0]` 内联到下游消费者，不能作为节点提交
- ✅ **工作流硬名单 + 严格分类器**：图片 / 视频 / 音乐工作流下拉用三层防御（bundled 目录 + 严格分类器 + 硬名单 frozenset），确保只显示真正驱动的 6 个工作流；分类器默认从 `t2i` 改成 `unknown`，杜绝乱认
- ✅ **HomeView 侧边栏底部 2×2 grid**：📦 元素库 / 🎵 音乐库 / 📊 任务历史 / ⚙ 引擎设置 紧凑布局
- ✅ **ProjectView tab 行**：📦 / 🎵 移到最右、压缩成图标钮，主管线 7 tab 不再拥挤
- ✅ **测试 + 集成**：后端 **207 / 207 pytest 通过**（v1.4.1 时 169 个），新增 AI 音乐写作 / 批量 SSE 并发证明（in-flight 计数）/ PrimitiveNode 内联 / BGM 混音命令构造 / 死 track 过滤 / 设为项目 BGM 等 38 个回归测

### v1.4.1
本版本以 **视频引擎扩展 + ComfyUI 工作流真子图驱动稳定性** 为主线，配合一系列生产 bug 根因修复。

- ✅ **新视频工作流 video_ltx2_3_i2v**：LTX-2.3 单图 + 时长 → 视频 driver；新写 `patch_workflow_i2v` 同时遍历顶层和 subgraph 内部节点，按 ID 写入 widget；deep-copy 避免污染共享 subgraph 定义
- ✅ **flfa2i 无音频模式**：「🔇 无音频模式」复选框，每分镜单独设视频时长；后端自动生成等长静音 WAV 上传到 ComfyUI input/，绕过 LoadAudio 严格校验
- ✅ **视频工作流分类系统**：`classify_video_workflow()` 自动判别 `video_flfa2i / video_i2v / unknown`（meta.kind > 名字关键词 > 节点扫描）；`workflow-info` 端点供前端按 kind 动态切换 UI（i2v 隐藏末帧槽 + 音频开关）
- ✅ **VideoTab 工作流自适应布局**：kind 徽章、分镜资产指示器按 features 动态显隐；i2v 显示参考图 + 时长输入框、flfa2i 显示首末帧 + 音频/时长开关
- ✅ **Reroute 节点正确穿透**：`_litegraph_to_api` 把 Reroute 加入"穿透节点"集合，与 mode==4 bypass 一同处理（修复 i2v workflow `VAEDecodeTiled / LTXVLatentUpsampler / LTXVImgToVideoInplace` "Required input is missing: vae" 报错）
- ✅ **工作流下拉硬名单**：三层防御 —— bundled 目录扫描 + 严格分类器 + 硬名单。`SUPPORTED_IMAGE_WORKFLOWS / SUPPORTED_VIDEO_WORKFLOWS` frozenset 确保下拉只显示 5 个支持的工作流，绕不过去；硬名单只影响下拉，不影响生成 / `get_workflow_json` / `classify_*` / precheck / 用户的 `cfg.workflow_dir` 设置
- ✅ **OrchestratorPanel 视频/图片下拉分离**：之前一键全流程的"视频工作流"下拉错用了图片工作流列表；现在分别从 `/image-engine/workflows` 和 `/video-engine/workflows` 拉取
- ✅ **测试 + 集成**：后端 **172 / 172 pytest 通过**（v1.4.0 时 152 个），新增视频工作流分类 / i2v 补丁 / Reroute 穿透 / 静音 WAV / 硬名单等 20 个回归测；用真实生产工作流文件做集成测试

### v1.4.0
本版本围绕 **Flux.2 工作流支持**、**i2i 全链路**、**元素库**、**角色立绘** 四条主线落地。新增 6 轮重构 + 多个生产 bug 的根因修复。

- ✅ **ComfyUI Subgraph 支持**：完整解析 ComfyUI 新版 Subgraph（顶层节点 `type=UUID`），递归展平到顶层 + 重连外部 link + 重写内部节点 `inputs[*].link` ID 映射 → 真实生产 Flux.2 image-edit 工作流可直接提交
- ✅ **Type-aware bypass**：mode==4 节点按 input/output 类型匹配做穿透；不匹配的 slot 直接断链让消费者 fallback 到 widget 值（修复 `GetImageSize` IMAGE→INT 类型不匹配导致 ComfyUI 400）
- ✅ **工作流分类系统**：自动判别 `t2i / i2i_single / i2i_double / video`（meta.kind > 名字模式 > 节点扫描三级优先链）；前端按类型动态切换 ImagesTab 布局
- ✅ **元素库（全局 + 项目级）**：多级文件夹树、自动迁移物理目录、SQLite + APPDATA/elements.sqlite；scope-aware repo 一套接口覆盖 `global` 和 `project:{pid}`；主屏「📦 元素库」入口 + 项目「元素」标签页
- ✅ **角色立绘（Portraits）**：CharactersTab 新增立绘画廊 + 「🎨 生成立绘」弹窗；t2i 工作流自动过滤；画风预设下拉 + 1080×1920 竖幅 + 主图选择 / 删除 + 自动晋升主图；点击放大预览（Lightbox 含键盘导航）
- ✅ **图生图全链路（i2i）**：ImagesTab 检测 workflow_kind 后切换 i2i 布局，每帧 1–2 个 📎 参考图槽位；ReferencePicker 三 Tab 选择器（🎭 角色立绘 / 📦 元素库 / ⬆ 本地上传）；本地上传自动落入元素库 `local` 文件夹；scene._frame_refs 持久化到 scenes.json
- ✅ **i2i 提示词生成端点**：`POST /api/text-engine/generate-img2img-prompt` 把 refs + characters + 分镜信息送 LLM 生成"编辑指令"风格 prompt（不混 style tags，因为 i2i 模型自动继承参考图风格）；前端 isI2I 自动切到此端点
- ✅ **Flux.2 size patching**：`_patch_workflow` 白名单扩展 `EmptyFlux2LatentImage` + `Flux2Scheduler`（后者的分辨率相关 sigma 调度必须与 latent 同步），user 设置的 1080×1920 终于真正生效
- ✅ **错误诊断**：ComfyUI 400 / 500 解析 `error.message` + `node_errors[*].errors[*]` 提示具体哪个节点报错；patched workflow 自动转储 `%APPDATA%/LumiCreate-Pro/diagnostics/failed_prompt_<ts>.json` 方便对照
- ✅ **测试 + 集成**：后端 **152 / 152 pytest 通过**（v1.3.7 时 79 个），新增 subgraph 展平 / i2i ref 注入 / i2i prompt 端点 / Flux.2 size patching 等 73 个测；用真实 Flux.2 工作流文件做集成测试

### v1.3.0
- ✅ **字幕生成与烧录**：新增「字幕生成」Tab，集成 stable-whisper 音频对齐流水线，支持视频帧率标准化 → 音频提取 → Whisper 词级对齐 → SRT 生成全流程；字幕脚本可从分镜台词导入或通过断句工具自动切句；字幕烧录可选字体（等线 Bold / 微软雅黑 / 黑体 / 仿宋 / 楷体等）及字号；生成与烧录均有实时进度显示
- ✅ **多项目标签页**：支持同时打开多个项目，每个项目独立标签页，有未保存修改时显示脏标记，关闭时弹确认对话框；🏠 首页按钮常驻

### v1.2.0
- ✅ **角色管理接入文本引擎**：新增“检索/生成描述”能力
  - 用户输入角色名称后可先从文案配置与文案正文检索角色线索
  - 支持调用文本引擎基于文案生成角色定位与特征描述
  - 生成前增加覆盖提醒，避免误覆盖已有描述
- ✅ **角色导入增强**：角色管理新增“从文案导入角色”（仅新增，不覆盖已存在角色）
- ✅ **分镜角色一键自动选择**：按分镜描述/台词自动匹配角色并勾选
- ✅ **图片生成角色选择链路**：
  - 分镜支持手动选择出镜角色（可多选）
  - 支持 AI 自动建议出镜角色
  - 生成提示词仅基于已选择角色，未选择时不注入角色外观
- ✅ **视频生成体验优化**：
  - 新增“继续生成”按钮，仅补生成未完成分镜，避免重复生成
  - 点击“开始生成”时若检测到已有结果，弹确认保护避免误覆盖
  - 视频提示词支持显式编辑与手动修改

### v1.1.0
- ✅ **项目文件夹系统**：侧栏新增文件夹树（创建/重命名/删除/移动项目），支持自定义 Emoji 图标；文件夹展开/折叠状态持久化
- ✅ **侧栏折叠**：左侧侧栏支持一键折叠（◀/▶），折叠状态跨会话保留
- ✅ **项目重命名**：右键菜单支持就地重命名项目
- ✅ **文件夹数据自动恢复**：启动时自动从后端项目 `folder_id` 反推丢失的文件夹，防止 localStorage 丢失导致项目归属不可见
- ✅ **视频合并路径修复**：最终合并视频统一保存到 `video/final_video.mp4`，修复重新合并后播放按钮禁用的问题

### v1.0.0
- ✅ 首个正式发布版本（Electron 安装包）
- ✅ 修复安装版空白窗口（Vite `base: './'`）
- ✅ 完整功能：文案创建 → 分镜设计 → 图片生成 → 音频生成 → 视频生成

## 核心功能

### 📝 文案创建
- 创建和编辑项目文案
- 支持Markdown格式
- 自动保存进度

### 🎞 分镜设计
- 从文案自动生成分镜提纲
- 编辑分镜描述、起始帧提示词、结束帧提示词
- 添加/删除/重排分镜
- 支持台词管理和编辑
- 可滚动分镜列表（支持大量分镜）

### 🖼 图片生成
- 集成 ComfyUI 工作流
- Master-detail 分割布局
- 支持多工作流选择，自动保存工作流选择
- 批量生成（跳过已有图片）、单个分镜生成、单个帧操作
- 图片预览和管理
- WebSocket 流式进度更新
- 生成的图片自动保存和加载

### 🎙 音频生成
- 集成 **IndexTTS-2.0**（Gradio API，本地运行）
- 分镜分组展示，每个音频片段独立配置音色参考、情感控制方式、情感参考和情感权重
- 每段音频支持多版本生成（V1/V2/V3…），可单独试听、切换选用版本
- 可调整每段音频的前/后静音时长（ms）
- **场景音频合并**：一键将场景内所有片段（含静音）拼接成单个 WAV，供 LTX-2.3 视频工作流使用
- 合并结果在页面内预览播放，持久化保存
- 支持 GPT-SoVITS 和手动导入模式作为备选

### 🎬 视频生成  
- 集成 ComfyUI 工作流
- LTX-2.3图片音频生成视频工作流（或合并图片、音频、字幕）
- 支持多种分辨率和帧率
- 预览和导出

## 许可证

MIT
