# LumiCreate-Pro

一个本地AI视频创作工具，集成文案生成、分镜设计、图片生成、音频生成、视频合成于一体。

## 项目架构

- **前端**：Vue 3 + Vite + Electron
- **后端**：FastAPI (Python) + ComfyUI (图片生成) + IndexTTS-2.0 (语音合成)
- **数据库**：本地 JSON 文件存储

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

全局设置存储在：`%APPDATA%/LumiCreate-Local/settings.json`

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
