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
- **多引擎**：ComfyUI 本地工作流 / Pollinations 云端（v1.4.5）/ 火山引擎 Seedream 5.0 云端（v1.4.11，支持国风水墨 + 汉字）
- 内置工作流：t2i / Flux.2 文生图 / Flux.2 Klein 图生图 / 通用 SD（多 LoRA 链）/ **Ideogram 4 结构化 JSON 文生图**（v1.4.12）
- **Ideogram 4 可视化提示词构建器**（v1.4.12）：画布拖拽画区域（区域可 **8 手柄缩放** + 拖拽移动 + 数值微调，v1.5.0）+ 类型/描述/配色 + 风格字段 → 一键生成结构化 JSON caption 填入提示词框；✨ AI 分步生成整个 caption，并复用「出镜角色」选择器把所选角色外观写进元素描述以保持角色一致性
- Master-detail 分割布局，支持多工作流选择 + 自动保存
- 批量生成（跳过已有图片）、单个分镜生成、单帧操作、本地导入 + 比例剪裁
- i2i 参考图槽位（角色立绘 / 元素库 / 本地上传）、SD 高级参数面板
- 图片预览和管理，WebSocket 流式进度更新，自动持久化保存/加载

### 📦 元素库
- **全局库 + 项目库共通**（v1.5.0）：项目「元素」标签页一键在「本项目 / 全局库」间切换；每个元素可「⇄」跨库复制（全局 ↔ 项目，双向，新落一份独立文件）
- 多级文件夹树、拖拽上传 / 移动、SQLite + 物理目录同步；一套 scope-aware 接口覆盖 `global` 与 `project:{pid}`
- **内置图片生成引擎**（v1.5.0，「✨ 生成图片」）：复用现有图片引擎全套工作流（ComfyUI t2i / Flux.2 / SD / Ideogram 4 / Pollinations / Seedream），Ideogram 内嵌同款 🧩 提示词构建器；生成结果自动入库当前文件夹

### 🎙 音频生成
- 集成 **IndexTTS-2.0**（Gradio API，本地运行）及 **GPT-SoVITS**
- **说话人 100% 可控**（v1.5.1）：每条台词的说话人 = 角色表绑定下拉（旁白 + 角色名单），音色按"说话人 → 角色 voice"确定性映射、生成时纯查表不推断；支持 `角色名：台词` 标注剧本确定性解析；「🎭 标注说话人」AI 助手结合上下文为已有台词逐条指派说话人（消解人称代词，批量并发），再用下拉一键确认；**纯朗读区分音色**下还可把整段文本拆成小段、逐段指派说话人（🎭 说话人分段 + AI 标注）
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
- **三通路**（v1.4.6+ / v1.4.10+）：
  - **LTX-2.3**（有 GPU）— ComfyUI 工作流首帧→末帧→音频驱动
  - **图片放映视频**（无 GPU / 低显存）— `render-slideshow` 端点直接 ffmpeg 渲染图片 + 音频；7 种 Ken Burns 动态（zoom_in/out + pan_left/right/up/down）+ 镜内/镜间转场 + 按 CPU 核数自动选并行 worker
  - **火山引擎 Seedance 2.0**（云端付费，v1.4.10）— 每分镜可独立配置模式（t2v / 首帧 / 首末帧 / 多模态参考）+ 时长 + 参考图（首尾帧 / 角色立绘 / 元素库）
  - 三个通路输出 schema 一致（`<scene_id>.mp4` + `videos.json`），下游 merge / 字幕 / BGM 无感复用
- LiteGraph UI 格式工作流自动转换为 ComfyUI API 格式（`_litegraph_to_api`）
- 多分辨率支持（720p/576p/544p，竖屏/横屏），可选帧率（24/25/30fps）
- 每个分镜卡片展示就绪状态（首帧 / 末帧 / 合并音频）、生成进度条、视频预览
- 生成视频持久化保存，重新进入页面自动恢复预览
- **分镜合并**：一键 ffmpeg concat 合并为完整 MP4，全链 Windows-safe 编码档（main/4.0 + bt709 + bitrate cap + aresample 同步）确保 WMP 可播 + 音画对齐
- **试播预览**（v1.4.8）：「▶︎ 试播」按钮，合并前不出文件即可在浏览器里按 scene 顺序串播现有素材（三档自动回退 video > image+audio > image-only）
- **音效（SFX）通路**（v1.4.8）：「🔊 音效」按钮 → 全局 SFX 库 + 项目级时间轴，给每镜次在精确时间点叠加点状音效（脚步 / 关门 / 抽刀）；ffmpeg `adelay+volume+amix` 直接烧进 slideshow 镜次 mp4

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
│   │   ├── video_engine.py     # 视频生成 SSE 流 + 分镜合并 + render-slideshow
│   │   ├── subtitle_engine.py  # 字幕生成 + 烧录 SSE 流
│   │   ├── music.py            # ACE-Step v1.5 音乐生成（v1.4.2）
│   │   ├── sfx_engine.py       # 音效库 + 项目时间轴（v1.4.8）
│   │   ├── prompts_engine.py   # 全局提示词标签库（v1.4.9）
│   │   └── settings.py         # 全局设置读写
│   ├── services/
│   │   ├── comfyui.py          # ComfyUI API 封装 + LiteGraph→API 转换器（含 Ideogram4 专用注入）
│   │   ├── ltx2video.py        # LTX-2.3 视频生成（上传/补丁工作流/拉取结果/音频替换）
│   │   ├── volcengine_seedance.py  # 火山引擎 Seedance 2.0 云端视频（v1.4.10）
│   │   ├── slideshow_video.py  # 图片放映视频（v1.4.6，无 GPU 通路，支持 SFX 叠加）
│   │   ├── pollinations_image.py   # Pollinations 云端图片（v1.4.5）
│   │   ├── volcengine_seedream.py  # 火山引擎 Seedream 5.0 云端图片（v1.4.11）
│   │   ├── text_platforms.py   # 文本引擎平台清单（builtin 16 + 自定义，v1.4.11）
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

### v1.5.1
本版本解决**音色不可控**的根因 —— 把"说话人"从"运行时 AI 推断"改成"显式结构化 + 人工锁定"，让每条台词的音色 **100% 可控**。三层方案，全 additive。

- ✅ **诊断**：音色映射本就是确定性的(`说话人 → 角色 voice`)；不可控的唯一根因是**每条台词的说话人字段是 LLM 从自由叙述里"猜"的**(中文倒装/省略主语/人称代词 → 原理上不可能 100%)，且只能用一个自由文本框纠正
- ✅ **① 说话人改成角色表绑定下拉**(`ScenesTab` + `AudioTab`)
  - 台词说话人由自由输入 → `旁白/默认 + 角色名单`下拉(表外旧值保留可见)，杜绝打错字 / AI 错配；一眼扫过去一键改正 → 音色立刻 100% 正确
  - AudioTab 的说话人也可改且**随项目落盘**(`audio.json` 增 `character` 覆盖)，生成时只读该字段、纯查表、绝不再推断
- ✅ **② 确定性说话人标注解析**(`services/dialogue_tags.py` + 前端同规则)
  - 支持 `角色名：台词` / `@角色名：台词` 标注行，**分隔符解析(非推断)** —— 给定角色名单时仅名单内的名字才当标签，避免散文冒号(如`时间：下午`)误切
  - `_extractDialogues` 优先走标注解析：带标注的文案/分镜重抽台词时说话人 100% 保留
  - **AI 助手** `POST /text-engine/tag-dialogue-speakers`：对**已有台词逐条指派说话人**(不改台词、只返回 speakers 数组)，结合上下文消解人称代词，服务端按名单校验(未知名归旁白)；ScenesTab「🎭 标注说话人」单镜 / 批量一键跑，再用下拉确认
- ✅ **③ 纯朗读「区分音色」逐段说话人编辑器**(`AudioTab`)
  - 纯朗读模式下每个分镜是**一整段文本**、内含各角色台词；开启「区分音色」后每个分镜出现 **🎭 说话人分段**：「构建分段」把整段按 `角色：台词` 标注 / 引号 / 句子拆成小段，每段一个**说话人下拉**(旁白 + 角色名单) → 区分音色按此 100% 分配，不再靠引号猜
  - **🎭 AI 标注**：对分段逐段指派说话人(消解人称代词)，再用下拉确认；分段随项目落盘(`__ms_reading__` 增 `segments`)，生成时优先用锁定分段、无则退回自动切分
- ✅ **批量标注并发**：ScenesTab「🎭 标注说话人(全部)」按 4 路并发跑(逐镜独立请求)，大幅缩短整片标注耗时
- ✅ **图片槽位竖幅自适应**：图片生成页槽位尺寸跟随设置的图片宽高比(竖幅→高窄、横幅→宽矮)且整图 `contain` 显示，竖幅图无需逐个点开即可看清完整内容
- ✅ **持久化修复(音乐库/元素库/角色立绘不再丢失)** —— 多智能体根因排查 + 对抗验证定位到 3 个独立缺陷:
  - **测试套件误删真实数据**: `conftest.py` 用 `os.environ.setdefault("APPDATA", …)`,Windows 上 APPDATA 必已存在 → no-op,导致每次 `pytest` 都把用户真实 `%APPDATA%/LumiCreate-Pro` 的 `music.sqlite`/`elements.sqlite`/sfx/prompts 及媒体目录删掉。改为**无条件**重定向到 `.test-tmp` + 每个 `isolated_app` 用例把 `db.SETTINGS_PATH` 钉到独立 tmp + 清理前加**致命断言**(非测试路径直接报错)
  - **项目元素未提交**: `elements_repo._commit_scope` 缺 `project:` 分支 → 项目库 INSERT 停在未提交事务,后端被 Electron 杀掉重启即回滚丢失。补上 project 分支显式 commit
  - **角色立绘被保存抹掉**: 角色页保存走后端 PUT 盲覆盖 `characters.json`,且前端不带 `portraits` 字段 → 立绘元数据被清空(PNG 沦为孤儿)。后端改为**载入合并**(按角色名保留磁盘已有 portraits、丢弃运行期 `_portraits` 缓存键),前端保存不再发送 `portraits`(由专用立绘端点维护)
  - 新增 5 个回归测试(隔离不变量 / 项目元素重连后仍在 / 立绘保存往返不丢),后端 **354 通过**
- ✅ **视频生成两个 bug(多智能体排查 + 实盘 ffprobe 验证)**:
  - **ComfyUI 视频重开项目不显示、无法合成(真因:540MB 巨型响应)**: `GET /videos` 把**每个分镜视频 base64 塞进同一个 JSON 响应**,ComfyUI 高清成片一个项目(如 81 镜 ~400MB)→ 单响应 ~540MB → 前端请求失败/超时 → 整页无预览、无法合成(小项目因体积小恰好能用)。改为返回**每镜流式 URL**(新增 `GET /video-file/{scene_id}`,支持 Range),`<video>` 按需懒加载,响应只剩几 KB;并附带 `videos.json` ∪ `scene_assets` 自愈索引
  - **加 BGM 合并后末尾画面定格(音画不同步、画面早结束)**: 实测每个分镜 TTS 音频比生成画面长 ~30–130ms,合并后成片音频比画面长 ~70–120ms;两条重编码合并路径原本都没有 `-t`/`-shortest` → 输出取最长流(音频) → 末帧在 `-vsync cfr` 下被定格到音频放完。改为按**视频流总时长**给输出封顶(`-t video_total`,BGM 淡出/裁剪也对齐到画面真正片尾;探测失败则安全回退不封顶)
  - 新增 3 个回归测试(videos 自愈 / 悬空键跳过 / 含 BGM 合并按视频流封顶),后端 **357 通过**
- ✅ **测试**：后端 **349 / 349 通过**(+14：`dialogue_tags` 解析 8 个 + `tag-dialogue-speakers` 端点 6 个)

### v1.5.0
本版本围绕 **元素库** 做了三件事：构建器区域可缩放、全局库 ↔ 项目库共通、元素库内置图片生成引擎 —— 全部 additive，现有图片/视频/元素通路 0 破坏。

- ✅ **Ideogram 构建器区域缩放**（`Ideogram4PromptBuilder.vue`）
  - 选中区域显示 **8 个缩放手柄**（四角 + 四边），拖拽即改 bbox（0–1000 网格，最小边长 10，自动夹紧），不再只能整体位移；缩放与原有"拖拽移动 / 数值微调"并存
- ✅ **全局元素库与项目元素库共通**（`ElementsBrowser.vue` + `elements_repo.copy_element`）
  - **scope 切换**：项目「元素」标签页顶部新增「本项目 / 全局库」切换 chip —— 一个面板内浏览两个库，互不干扰各自的文件夹树
  - **跨库复制**：每个元素卡新增「⇄」按钮，一键把元素复制到另一个库（全局 ↔ 本项目，双向）；后端 `POST /copy` 读源字节 + 在目标 scope 另落一份新元素（新 id、独立文件，`source_meta.copied_from` 记录来源），原件保留
  - 纯全局面板（主屏 📦 元素库）无项目上下文，仅显示全局库，行为不变
- ✅ **元素库内置图片生成引擎**（`ElementGenerateDialog.vue`，「✨ 生成图片」按钮）
  - **复用现有图片引擎全套**：直接调 `POST /image-engine/generate-stream`，按 `engine_type` 自动分派 —— ComfyUI 全部工作流（t2i / Flux.2 / SD / **Ideogram 4**）/ Pollinations / 火山引擎 Seedream 通吃，无新增生成后端
  - **Ideogram 提示词构建器内嵌**：选中 `image_ideogram4_t2i` 时弹窗内显示「🧩 构建器」→ 复用同一个 `Ideogram4PromptBuilder`（画布尺寸跟随表单宽高）→ 应用纯 JSON caption；Ideogram 走纯 JSON、不拼负面/画风前缀
  - **生成即入库**：可设工作流 / 提示词 / 宽高 / 数量(1–8，按序错开 seed) / 种子，生成结果实时显示并自动存入当前 scope 的当前文件夹（`source=t2i` + `source_meta` 记录工作流/提示词/种子），完成后网格自动刷新
- ✅ **测试**：后端 **335 / 335 pytest 通过**（v1.4.12 时 333 个），新增 2 个 `copy_element` 回归（跨文件夹复制字节一致 + 原件保留 + source_meta 来源记录；缺失元素 KeyError）

### v1.4.12
本版本新增 **Ideogram 4 文生图工作流支持 + 可视化结构化 JSON 提示词构建器** —— 完全 additive，现有 ComfyUI t2i / i2i / SD / Flux.2 / Pollinations / Seedream 图片通路 0 改动。

- ✅ **新工作流 `image_ideogram4_t2i`**（第 5 个白名单 ComfyUI 图片工作流）
  - **打包副本**：`workflows/image_ideogram4_t2i.json` 从用户 ComfyUI 工作流精简而来，剥掉 KJ 预览 / debug `showAnything` / 孤儿 `LoadImage` 三类节点，只留单一真实图片输出（避免 `_fetch_images` 抓到编辑器预览图）
  - **专用提示词注入**（`comfyui.py _patch_workflow`）：Ideogram 4 的 prompt 是结构化 JSON caption，流向 `Ideogram4PromptBuilderKJ.out0 → 子图 CLIPTextEncode(wire) + JsonExtractString(抽 mu/std/steps)`，**不能**被通用 CLIPTextEncode literal 注入割断 wire。正确做法：caption JSON 写进 KJ 的上游 `StringConstantMultiline.string` + 把 `import_mode` 翻成 `always` 让 wired JSON 成为权威源，全链一致；命中即 return，跳过通用 prompt/size 注入
- ✅ **可视化 JSON 提示词构建器**（`Ideogram4PromptBuilder.vue` + `PaletteEditor.vue`，仿 ComfyUI 的 KJ 节点）
  - **左·画布**：拖拽画区域，bbox 自动归一化到 0–1000 网格 `[ymin,xmin,ymax,xmax]`；可拖动移动 / 点选 / 删除；**画布长宽比跟随设置页图片引擎的 `image_width/height`**（bbox 摆放所见即所得）
  - **中·区域列表 + 编辑**：type（obj/text）、desc、text（图中文字）、bbox 数值微调、区域配色（≤5）
  - **右·全局字段**：`high_level_description` / `background` / `style_description`（photo ↔ art_style 二选一 + aesthetics/lighting/medium + 整体配色 ≤16）
  - **底**：JSON 实时预览 + token 估算 + 复制 + 「✓ 应用到提示词框」；严格按 schema 的 key 顺序组装；支持回填已有 JSON 再编辑
  - **入口**：图片生成页选中 `image_ideogram4_t2i` 时，首/尾帧标题栏显示「🧩 构建器」按钮 → 弹窗 → 应用后写回该帧 prompt（复用 `onPromptInput`）
- ✅ **✨ AI 分步生成整个 caption**（结构化 JSON 较大 → 拆两步小响应，避免单次截断）
  - **后端 `POST /text-engine/generate-ideogram-caption`**：走当前文本引擎，`step=overview` 出 `high_level_description + background + style_description`（按 photo/art_style 引导 key 顺序），`step=elements` 出 `elements` 数组；服务端 bbox 校验 + 0–1000 夹紧 + 非法元素过滤 + 幻觉字段剥除 + 上限 9 元素
  - **前端构建器右栏 ✨ AI 生成块**：描述输入框（打开时自动预填该分镜描述 + 携带出镜角色卡含 appearance）→ 一键两步生成（进度「1/2 概览与风格 → 2/2 元素布局」）→ 自动填充全部字段与画布区域，生成后可继续手动微调
- ✅ **角色一致性贯通**（复用「🎭 出镜角色」选择器，不在构建器里重做一个）
  - **来源即选择器**：构建器的 AI 生成直接读取图片生成页「出镜角色」选择器已选中的角色（用户手动勾选或「✦ AI 自动选」均可），按角色名 hydrate 成完整角色卡（携带角色管理页填写的 `appearance` 外观）传给后端两步生成
  - **可见提示**：构建器 AI 块只读展示「参考角色」chip（hover 看外观；未填外观的角色标 ⚠），未选角色时给出引导文案 —— 让用户确认正在按所选角色出图，而非黑盒
  - **强约束注入**：后端 `_ideogram_chars_block` 升级为角色一致性指令 —— 要求把每个出镜角色的**完整外观逐字写进对应 `obj` 元素的 desc**，且外观与角色一一绑定、禁止跨角色混用/迁移特征；overview + elements 两步都注入该块
- ✅ **打包修复**：electron-builder `extraResources` 增加 `workflows/` 目录 —— 打包后 `bundled_workflow_dir()` 才能解析仓库自带工作流（否则回退到用户 ComfyUI 目录，rename 后的工作流不在那 → 下拉漏掉）
- ✅ **测试**：后端 **333 / 333 pytest 通过**（v1.4.11 时 301 个），新增 18 个回归测覆盖：打包工作流单输出 / classify t2i / 白名单 / 注入正确性（StringConstant + import_mode=always + CLIPTextEncode wire 不被割断 + 种子）/ KJ 隐藏必填 widget（elements_data / style_palette_data / bg_brightness）补全 + setdefault 不覆盖已有值 / 未接线 import_json 兜底 / 非 ideogram 仍走原 CLIP 路径 / AI caption overview 幻觉字段剥除 / elements bbox 夹紧 + 非法过滤 / 空描述 400 / 非法 step 400 / LLM 垃圾输出 502 / **角色一致性：所选角色 appearance 进入 overview + elements 两步提示、未选角色不注入 Characters 块**
- ⚠️ **已知限制**：**输出**分辨率仍由工作流自带的 `ResolutionSelector`（默认 16:9 / 2MP）决定（构建器画布长宽比已跟随设置，但 ComfyUI 实际出图尺寸需在该工作流的 ResolutionSelector 改默认或等后续映射）

### v1.4.11
本版本扩展 **文本引擎平台清单（下拉 + 自定义平台）** + 新增 **火山引擎 Seedream 5.0 图片引擎** —— 均为 additive，现有引擎通路 0 改动。

- ✅ **文本引擎平台清单**（`services/text_platforms.py`）
  - 内置 16 个常见 OpenAI-compatible 平台：Ollama / LM Studio / DeepSeek / 阿里云百炼 / 火山方舟 / 月之暗面 Kimi / 智谱 GLM / 阶跃星辰 / 硅基流动 / MiniMax / OpenAI / Anthropic / Gemini / OpenRouter / 通用兜底
  - `engine_type` 从 Literal 收紧改为**自由 str**（老 settings.json 里任意 engine_type 不再因校验炸；driver 早就是"ollama vs 其它 OpenAI-compat"两分支，新平台 0 driver 改动）
  - **自定义平台 CRUD**：`/settings/text-platforms` GET/POST/DELETE，用户可加私有端点存进 `custom_platforms`，内置平台受保护不可删 / 撞名拒绝
  - 前端：设置页文本引擎从 radio 改为**下拉**（节省空间）+「＋ 新增自定义」弹窗 +「✕ 删除当前」；切换平台自动同步 base_url
- ✅ **新图片引擎：火山引擎 Seedream 5.0**（云端付费，国产顶级文生图，支持国风水墨 + 汉字）
  - **服务**：`backend/services/volcengine_seedream.py` —— Ark `images/generations` 同步 POST，包成与 ComfyUI/Pollinations 一致的 SSE 事件 schema（queued/progress/completed），下游批量处理 0 改动
  - **第 3 档 engine_type**：`comfyui / pollinations / volcengine_seedream`；`/test` `/workflows` `/workflow-info` 单图 + 批量生成 4 处 dispatch 全部按 engine_type 分派
  - 前端：设置页图片引擎加 Seedream radio + 配置块（base URL / API Key / 模型 ID / 尺寸 / 响应格式 / seed）+ 🔌 测试连接
- ✅ **测试**：后端 **301 / 301 pytest 通过**（v1.4.10 时 296 个），新增 platforms（builtin 清单 / CRUD round-trip / 撞名 + 删内置保护 / 老配置 str 兼容）+ Seedream（默认值保 comfyui / dispatch / driver SSE schema / 错误兜底）回归

### v1.4.10
本版本新增 **火山引擎 Seedance 2.0 云端 API 视频生成通路** —— 完全可选，与现有 LTX-2.3 / slideshow 通路并存。

- ✅ **新引擎：火山引擎 Seedance 2.0**（云端付费 API）
  - **服务**：`backend/services/volcengine_seedance.py` —— Ark 异步任务模式（POST 创建 → GET 轮询 → 下载 mp4），暴露同 LTX 完全一致的 SSE 事件 schema（queued / progress / completed / error）
  - **Settings 字段**：`engine_type ∈ {"comfyui", "volcengine_seedance"}` + 8 个可配置项（base_url / api_key / model_id / duration / resolution / use_image / poll_timeout / poll_interval）
  - **完全非侵入**：默认 `engine_type="comfyui"`，老 settings.json 升上来 0 改变；切换到火山引擎模式时 ComfyUI 配置仍保留，切回去无需重填
  - **路由 dispatch**：`/generate-stream` / `/test` / `/workflows` 都按 `engine_type` 自动分派；新增 `/volcengine-test` 独立连接测试端点（不依赖 engine_type 切换，让用户切之前先验证 API key）
  - **下游零改动**：driver SSE 事件 schema 与 LTX 完全相同 → `record_asset` / `videos.json` / merge-project-video / 字幕烧录 / SFX 全部无感复用
- ✅ **前端 SettingsView 视频引擎 tab**：
  - 引擎模式 radio 切换（ComfyUI 本地 ↔ 火山引擎云端）
  - Volcengine 配置块：base URL / API Key / 模型 ID / 时长（5/10s）/ 分辨率（480p/720p/1080p）/ 是否 i2v / 轮询参数
  - 🔌 测试连接按钮，调 `/volcengine-test` 并显示具体错误（4xx 错误体透传，方便用户对照官方文档改字段）
  - 切到火山引擎模式时下方仍保留 ComfyUI 配置（标注"备用"），随时切回去
- ✅ **VideoTab 引擎徽章**：工具栏左上挂 `☁ 火山引擎云端` / `🖥 本地` 徽章，提醒用户"现在跑批会花钱"
- ✅ **SKILL 同步**：模块表 + 决策树（"火山引擎 / Seedance / API 生成视频"意图分支）；新建 `references/modules/volcengine-seedance.md`（含 API 协议 + dispatch 数据流 + 全配置字段表 + 与现有通路相容性说明）
- ✅ **测试**：后端 **296 / 296 pytest 通过**（v1.4.9 时 285 个），新增 11 个回归测覆盖：老 settings.json 兼容（无新字段 → 默认值填充）/ `/workflows` 和 `/test` engine_type 分派 / 独立 `/volcengine-test` 端点 / driver SSE 事件序列与 LTX 一致 / content payload 字段构造（prompt + image + hint 注入）/ 状态同义词收敛
- ⚠️ **API 文档对照**：本版本按 Ark 通用约定（Bearer auth + 多模态 content 数组）实现 driver。所有端点 / 字段都在设置页可配置；如果官方 Seedance 2.0 实际字段不一样，driver 会从 4xx 响应里把原始错误体透传到 SSE error 事件，用户能立即看到具体哪个字段被拒，对照文档调设置即可

### v1.4.9
本版本新增 **全局提示词插件** —— 不绑定项目，TitleBar 一键打开。

- ✅ **提示词插件（PromptsPlugin）**：标题栏 `📋` 日志按钮右侧新增 `💡` 按钮，点开弹窗
  - **数据**：全局 SQLite `APPDATA/LumiCreate-Pro/prompts.sqlite`，表 `prompt_tags`（category/name/content/description/is_builtin/sort_order）
  - **内置出厂集**：~60 个常用漫剧 + SD 提示词，分 7 类（画风 / 构图 / 光照 / 情绪 / 角色 / 画质 / 负面词）；懒触发 seed，首次访问自动塞入
  - **后端路由**：`backend/routers/prompts_engine.py`，6 端点 `/categories /list /tag (POST/PUT/DELETE) /reset-builtins`；内置标签受保护不能改 / 删（防误操作），整体 reset 才能恢复出厂
  - **前端弹窗**：三段式（类目侧栏 / 标签网格 / 撰写区）。点击标签追加到撰写区，分隔符可切（逗号 / 空格 / 换行），撰写区可自由键入；「📋 复制到剪贴板」走 `navigator.clipboard.writeText`（老浏览器 `execCommand` 兜底）
  - **新增自定义**：「＋ 新增自定义」可填类目 + 显示名 + 内容 + 描述，立即落地；自定义标签左侧黄边 + hover 显示删除按钮
  - **搜索**：跨 name / content / description 即时过滤
- ✅ **SKILL 同步**：模块表 + 决策树（"提示词 / 标签 / 画风 / 复制提示词"意图分支）；新建 `references/modules/prompts.md`（含数据模型 + 内置集 + API + UX wireframe）
- ✅ **测试**：后端 **285 / 285 pytest 通过**（v1.4.8 时 276 个），新增 9 个回归测覆盖懒 seed 触发 / 列表排序（内置在前自定义在后）/ CRUD round-trip / 内置删改保护 / reset-builtins 不影响自定义 / required 字段校验

### v1.4.8
本版本聚焦 **生产环境反馈环路** —— 合并前不出文件即可试播全片节奏 + 给静帧叙事加点状音效。

- ✅ **试播预览（PreviewPlayer）**：VideoTab 工具栏新增「▶︎ 试播」按钮。Teleport 模态，按 scene 顺序在浏览器里串播现有素材，**0 后端调用、0 文件落盘**。三档自动回退：video mp4 > image+audio（HTMLAudio 同步）> image-only（4s 静帧）。媒体出错自动跳过该镜，长片合并前可秒看节奏
- ✅ **音效（SFX）通路（v1.4.8 新模块）**：漫剧叙事需要的脚步 / 关门 / 抽刀等点状音效，从 BGM 通路独立出来
  - **全局 SFX 库**：`services/db.py` 新增 `sfx.sqlite` + `APPDATA/sfx/`；空库出厂，用户按需上传（避免版权风险）
  - **新路由 `backend/routers/sfx_engine.py`**：8 端点 `/categories /list /upload /file/{id} /clip/{id} (PUT/DELETE) /timeline/{pid} (GET/PUT)`
  - **项目级时间轴 `<project>/sfx_timeline.json`**：`{scene_id: [{sfx_id, offset_ms, volume_db}]}`；volume_db ∈ [-40, 20]
  - **渲染集成**：`slideshow_video.build_scene_clip_cmd` 加 `sfx_overlays` 参数。无 SFX 走原快路径，有 SFX 时进 filter_complex：`[a:main]aresample → [a:N]adelay+volume → amix duration=first`。单图 + 双图 xfade 均支持；引用已删除 sfx_id 静默跳过不让整片崩
  - **前端 `SfxTimelineDialog.vue`**：三栏（分镜列表 / 时间轴表 / SFX 库），上传 + 试听 + 删除 + 按镜次增删 overlay；选中分镜 accent 高亮 + badge 反色
  - **适用范围**：MVP 仅 slideshow 通路烧 SFX；LTX 视频本版本不接。改了时间轴必须重跑 `render-slideshow` 才生效
- ✅ **SKILL 同步**：SKILL.md 模块表 + 决策树（"试播 / SFX"两个新意图分支）；新建 `references/modules/sfx.md`（接口 + ffmpeg cmd 模板 + 适用范围警告）
- ✅ **测试**：后端 **276 / 276 pytest 通过**（v1.4.7 时 267 个），新增 9 个回归测覆盖单/双图分支 SFX 注入 / 缺失 sfx_id 安全跳过 / 无 SFX 走回退路径 / 时间轴 PUT-GET round-trip / volume_db 校验 / SFX 上传扩展名守门 / 项目 404
- ✅ **Hotfix（已合入本版本）**：
  - **SFX 对话框视觉**：用 `var(--color-background)` 这种不存在的 CSS token → fallback `#1e1e1e` + light 主题深色文本 = 字背景同色看不清；body grid `min-height:60vh + max-height:70vh` 死值导致内容溢出 modal 90vh 上限。改用项目实际 design tokens（`--bg-panel / --text / --border / --bg-input / --accent`）+ `flex:1 + min-height:0` 弹性体壳 + 各栏独立 overflow 滚动 + sticky 区段标题
  - **试播预览初版三个 bug 连环**：(1) `fetch('HEAD', ...)` 探活而 FastAPI `@router.get` 不接受 HEAD 返 405；(2) `/assets` 端点返回 `{assets, count}` 不是 `{items}`；(3) `axios.get` 但 axios 未 import → ReferenceError 被 try/catch 吞成 console.warn → inventory 永远空 dict → 所有分镜被判 "empty"。全部修复

### v1.4.7
**hotfix release** —— 实机测试 v1.4.6 后用户报告两个新问题，本版本根治：

- ✅ **WMP 拒播合并 / 烧字幕成品**：用户主诉"数据速率和总比特率过高"——CRF=20 在 1080p25 + Ken Burns 高频细节下瞬时码率可冲到 30+Mbps，破 H.264 Level 4.0 上限 ~25Mbps → WMP 拒播。全链 `-maxrate 8M -bufsize 16M` + CRF 22 收紧
- ✅ **10min 视频音频比视频早结束 ~1min（10% drift）**：
  - 真因：AAC 编码器 priming + `-shortest` 在每镜次截断 50-100ms，concat re-encode 时不补 → 累积成秒级 drift
  - 每镜次音频 `-ar 44100` → `48000`（与 merge/burn 对齐，全链路无重采样）
  - 全链 `-af aresample=async=1000:first_pts=0` 填 PTS 间隙
  - 移除 `-shortest`，改为显式 `-t {duration_s}` 双向裁剪
  - merge 快路径 / 慢路径 `final_audio` 均接 aresample 滤镜
- ✅ **测试**：后端 **267 / 267 pytest 通过**，+4 个 A/V drift + bitrate ceiling 锁住回归

### v1.4.6
本版本以 **无 GPU 通路（图片放映视频）** 为主线，并附带一次大型 **WMP 兼容 + 音画同步** 修复，覆盖 ffmpeg 全链路（每镜次 → 合并 → 字幕烧录）。

- ✅ **新模块 `backend/services/slideshow_video.py`**：图片放映视频生成器（不走 ComfyUI / LTX，纯 ffmpeg）。给低显存 / 无 GPU 用户的轻量通路，输出与 LTX 同 schema（`<project>/video/<scene_id>.mp4` + `videos.json`），后续 merge / 字幕烧录无感复用
- ✅ **新端点 `POST /api/video-engine/render-slideshow`**：参数含 `width / height / fps / intra_transition / motion_effect / parallel`；Ken Burns 7 种动态（zoom_in/out + pan_left/right/up/down）+ 转场预设映射到 xfade；`parallel=0` 自动按 `cpu_count // 4` 选 worker（capped at 1-4），16 核机能撑到 60%+ 利用率
- ✅ **抖动修复（4× lanczos 预放大）**：zoompan 直接在目标分辨率上跑会因整像素取整在帧间"震动"，改 4× 大画布采样 + 下采样 → 单像素增量映射到 0.25 输出像素，画面丝滑
- ✅ **音画同步根治（贯穿全链）**：
  - 每镜次时长一律以 **ffprobe 实测音频时长**为准（不再信 SQLite metadata.duration_ms — TTS 目标长度与实际产出差几十-几百 ms 累积成"音频先于字幕结束"）
  - 每镜次 `-shortest` → 显式 `-t duration_s`：音视频末尾对齐到精确时间戳
  - 加 `-af aresample=async=1000:first_pts=0`：填补 AAC 编码器 priming 静音
  - 全链统一 48kHz 立体声（消除跨阶段重采样累积漂移）
  - merge 路径 filter_complex 末尾追加 aresample 节点（**v1.4.5 之前**：用户报"10min 视频音频比视频早 1min 结束"，本版本根治）
  - 字幕烧录 `-c:a copy` → `-c:a aac -ar 48000`：音频与视频共享 demux→encode 通路，杜绝 PTS 漂移
- ✅ **Windows Media Player 兼容（贯穿全链）**：用户报"合并视频和烧字幕视频本地播放器打不开"，root cause 是混合 LTX/slideshow 的 concat -c copy 产物 mvhd timescale 不一致 + 瞬时码率超 Level 4.0 上限：
  - **移除 merge 快路径的 `-c copy`**，改成清编码 + 统一 `-video_track_timescale 90000`
  - **全链强制保守编码**：`-profile:v main -level 4.0 -preset fast -crf 22 -pix_fmt yuv420p`
  - **全链 bitrate cap**：`-maxrate 8M -bufsize 16M`（Level 4.0 硬上限 ~25 Mbps，留足边距防 WMP 拒播）
  - 色彩空间显式 tag `bt709`（避免播放器猜色域偏色）
  - `+faststart` 落到所有 4 条 ffmpeg 输出路径（per-scene / merge 快慢路径 / 字幕烧录 / BGM 混音）
- ✅ **前端：图片导入 + 比例裁剪（v1.4.6）**：每个图片槽旁新增 📥 导入按钮，本地选图后弹 `ImageCropDialog.vue`（Canvas，4 角拖动+移动+自动居中），裁剪比例锁死 `settings.image_engine.image_width/height`；用户不再需要外部工具预裁剪
- ✅ **前端：图片生成页比例提醒条**：顶部显示当前 settings 的输出比例，避免出图后才发现比例不对
- ✅ **前端：视频生成页两种模式 radio**：LTX-2.3（高质量 AI 视频）↔ 图片放映（无 GPU），slideshow 模式有 Ken Burns 下拉 + 转场 + 时长 + 分辨率 + fps + 一键生成
- ✅ **SKILL 同步**：`modules/video.md` 新增 render-slideshow 全文 + v1.4.6 merge 重构说明 + 视频生成路径决策树；`modules/subtitle.md` 新增 burn A/V sync 修复历史；`modules/image.md` 新增导入+裁剪段；SKILL.md 模块表 + 决策树更新
- ✅ **测试**：后端 **263 / 263 pytest 通过**（v1.4.5 时 236 个），新增 27 个回归测覆盖单镜命令构造 / 转场+动态映射 / 音频静音注入 / videos.json 落盘 / 并行 worker 推荐 / Windows-safe 编码档 / ffprobe 优先于 metadata / 显式 `-t` 同步 / 跨链路 `+faststart` / merge 路径 bitrate cap / aresample 同步节点 / 字幕烧录重编码音频

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

## 许可证

MIT
