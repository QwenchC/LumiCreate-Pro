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
│   │   └── settings.py         # 全局设置读写
│   ├── services/
│   │   ├── comfyui.py          # ComfyUI API 封装 + LiteGraph→API 转换器
│   │   ├── ltx2video.py        # LTX-2.3 视频生成（上传/补丁工作流/拉取结果/音频替换）
│   │   ├── indextts.py         # IndexTTS-2.0 Gradio API
│   │   ├── gptsovits.py        # GPT-SoVITS API
│   │   ├── msedge_tts.py       # 微软 Edge 神经语音（纯朗读模式）
│   │   ├── llm.py              # LLM 推理（Ollama / OpenAI 兼容）
│   │   └── prompts.py          # Prompt 模板
│   ├── config.py               # 设置模型与加载
│   ├── main.py                 # FastAPI 应用入口
│   └── requirements.txt
├── electron/
│   ├── main.js                 # Electron 主进程（窗口 / IPC / shell 操作）
│   └── preload.js              # contextBridge API 暴露
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

## 更新日志

### v1.2.0（当前）
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

### v1.0.1
- ✅ **画风一致性**：图片提示词生成时 LLM 被明确禁止输出画风标签；图片生成页新增画风选择器（7 种预设：二次元动漫/写实风格/水彩插画/赛博朋克/国风水墨/像素风格/自定义），画风仅在生成时注入，不修改已存储的提示词
- ✅ **角色一致性系统**：新增角色管理 Tab（姓名/定位/特征/外观英文标签/负向描述），支持从文案配置一键同步角色；分镜提示词生成自动注入角色外观标签；图片生成页显示角色外观参考面板（点击复制）
- ✅ **阿里云百炼支持**：文本引擎新增百炼（通义千问）选项，自动填充兼容端点 URL，修复 Qwen3 思考模型 `enable_thinking: False` 参数，超时延长至 300 s
- ✅ **设置持久化修复**：切换引擎类型时不再覆盖已保存配置；获取模型列表前自动先保存当前设置

### v1.0.0
- ✅ 首个正式发布版本（Electron 安装包）
- ✅ 修复安装版空白窗口（Vite `base: './'`）
- ✅ 完整功能：文案创建 → 分镜设计 → 图片生成 → 音频生成 → 视频生成

### v0.4
- ✅ **文案创建**：扩展配置面板 — 故事基调、世界观设定、主要角色（姓名+定位+性格）、对白模式，全部注入 LLM 生成提示词
- ✅ **纯朗读模式**：新增第四种对白模式，文案分镜/音频均有专属处理路径
  - 分镜：服务端按标点切句分割，无需 LLM，每段 ≤28 s
  - 音频：微软 Edge 神经语音（10 种中文声音 × 5 种语速），无需 API Key
  - 视频：MS TTS 生成的 MP3 自动映射为合并音频，ffmpeg 直接使用
- ✅ **分镜设计**：图片提示词与分镜生成分离（单个/全部按需生成）；清空全部分镜按钮；分镜生成传入角色配置与对白模式
- ✅ **音频生成**：朗读模式 UI（语音/语速选择、逐段播放器、真实时长显示）；重新生成时旧音频即时清除
- ✅ 视频生成页自动识别朗读模式，将 MS TTS 音频作为视频音轨输入

### v0.3
- ✅ LTX-2.3 视频生成完整流程（首帧 + 末帧 + 音频 → MP4）
- ✅ LiteGraph→API 转换器：修复 6 类边缘情况（SetNode/GetNode / Bypass / 虚拟节点 / UI-only 输入 / dict widgets_values / wv_idx 偏移）
- ✅ VAELoaderKJ → VAELoader 自动替换（规避 KJNodes 版本 Bug）
- ✅ 音频上传改为直接写入 ComfyUI input/ 目录（兼容旧版 ComfyUI）
- ✅ 视频完成后用用户原始音频替换 AI 解码音频（ffmpeg 后处理）
- ✅ 视频提示词自动注入角色开口对白（跳过旁白）
- ✅ 生成视频持久化保存 + 重新进入页面自动恢复预览
- ✅ 分镜合并：ffmpeg concat → 项目目录 `final_video.mp4`，结果弹窗支持打开/定位
- ✅ 设置页新增 ComfyUI input/ 目录配置及分辨率标签

### v0.2
- ✅ 音频引擎切换至 IndexTTS-2.0（Gradio API）
- ✅ 音频页按场景分组，音色/情感参考配置
- ✅ 每段音频前/后静音可调，多版本生成与选用
- ✅ 场景音频一键合并（WAV 拼接）+ 持久化保存
- ✅ ImageTab master-detail 分割布局 + 图片持久化
- ✅ 工作流选择自动记忆
- ✅ 项目保存状态（dirty/saved）正确联动

## 后续规划

- [ ] 图片生成：IP-Adapter 角色参考图一致性控制
- [ ] 整体软件窗口布局优化

## 开发指南

### 热重载
- 前端：Vite HMR 自动刷新
- 后端：修改代码后手动重启 `python main.py`

### 文件编码（Windows GBK 环境）
不要用 PowerShell `Get-Content`/`Set-Content` 编辑 UTF-8 文件，使用 Python 脚本或 VS Code 编辑器处理中文字符。

### 项目数据存储
```
~\LumiCreate-Projects\
└── {project_id}\
    ├── project.json        # 元数据与进度
    ├── manuscript.md       # 文案
    ├── scenes.json         # 分镜列表（含台词）
    ├── images.json         # 图片槽位元数据
    ├── images\             # PNG 文件
    ├── audio.json          # 音频数据（含合并结果）
    ├── videos.json         # 分镜视频元数据
    ├── video\              # MP4 文件（各分镜 + final_video.mp4）
    └── cache\              # 临时缓存
```

## 许可证

MIT


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

## 项目结构

```
LumiCreate-Pro/
├── renderer/              # Vue 3 + Electron 前端
│   ├── src/
│   │   ├── views/        # 页面
│   │   ├── components/   # 组件（tabs/*, common/*）
│   │   ├── assets/       # 样式/资源
│   │   ├── stores/       # Pinia 状态管理
│   │   ├── router/       # Vue Router
│   │   └── main.js       # 应用入口
│   ├── index.html        # HTML 入口
│   └── vite.config.js    # Vite 配置
├── backend/              # FastAPI 后端
│   ├── routers/         # API 路由
│   │   ├── projects.py  # 项目 CRUD
│   │   ├── image_engine.py
│   │   ├── audio_engine.py
│   │   ├── text_engine.py
│   │   ├── video_engine.py
│   │   └── settings.py
│   ├── services/        # 外部服务集成
│   │   ├── comfyui.py
│   │   ├── indextts.py
│   │   ├── gptsovits.py
│   │   ├── llm.py
│   │   └── prompts.py
│   ├── config.py        # 设置管理
│   ├── main.py          # FastAPI 应用
│   └── requirements.txt  # Python 依赖
├── electron/            # Electron 主进程
│   ├── main.js
│   └── preload.js
├── .gitignore           # Git 配置
├── project.md           # 项目进度跟踪
└── README.md            # 本文件
```

## 配置

全局设置存储在：`%APPDATA%/LumiCreate-Pro/settings.json`

支持的引擎配置：
- **文本引擎**：Ollama / LM Studio / Deepseek / OpenAI 兼容
- **图片引擎**：ComfyUI + 可选工作流选择记忆
- **音频引擎**：IndexTTS-2.0（默认）/ GPT-SoVITS / 手动导入
  - IndexTTS 配置：Gradio 地址、音色参考文件夹、情感参考文件夹、默认音色文件、默认情感权重
- **视频引擎**：ComfyUI + FFmpeg

## 最近更新（v0.2）

- ✅ 音频引擎切换至 **IndexTTS-2.0**（Gradio API）
- ✅ 音频页按场景分组，支持音色/情感参考配置
- ✅ 每段音频前/后静音可调，多版本生成与选用
- ✅ 场景音频一键合并（WAV 拼接），供视频工作流使用
- ✅ 合并音频页内预览 + 持久化保存
- ✅ 设置页音频引擎完整 IndexTTS 配置项
- ✅ ImageTab master-detail 分割布局
- ✅ 图片持久化保存/加载
- ✅ 分镜/音频列表滚动支持
- ✅ 工作流选择自动记忆
- ✅ 项目保存状态（dirty/saved）正确联动

## 开发指南

### 热重载
- 前端：Vite HMR 自动刷新
- 后端：修改代码后手动重启 `python main.py`

### 文件编码注意事项（Windows GBK 环境）
- 不要用 PowerShell `Get-Content`/`Set-Content` 编辑 UTF-8 文件
- 使用 Python 脚本或 VS Code 编辑器处理中文字符

### 项目保存机制
- 标签页组件监听 `lumi:save-project` 事件并自动保存数据
- 所有数据更新应触发 `emit('dirty')` 来标记项目修改
- 项目数据存储：`~\LumiCreate-Projects\{project_id}\`

## 常见问题

**Q: 分镜标签过多时会被压缩？**
A: 已修复 — 卡片设置 `flex-shrink: 0` 并支持滚动

**Q: 图片生成后进度仍显示 0%？**
A: 已修复 — 保存图片时自动更新 `progress.images`

**Q: 每次进入都要重选工作流？**
A: 已修复 — 选择的工作流自动保存到全局设置

## 许可证

MIT
