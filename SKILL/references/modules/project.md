# project 模块

项目元数据 + 文案 / 分镜 / 角色 / 图片 / 音频 / 视频 / 视频提示词的 CRUD。

## ProjectMeta

```json
{
  "id": "proj_20250105143022_a1b2c3",
  "name": "悬疑短剧 Demo",
  "description": "",
  "created_at": "2025-01-05T06:30:22Z",
  "updated_at": "2025-01-05T07:12:01Z",
  "progress": {"manuscript":100,"scenes":100,"images":100,"audio":100,"video":100},
  "has_final_video": true,
  "folder_id": "default"
}
```

`progress.*` 由后端根据数据存在性自动维护，**不要手动构造**。

## 接口

### 项目 CRUD

| 方法   | 路径                                  | 说明                                                |
|--------|---------------------------------------|-----------------------------------------------------|
| GET    | `/api/projects`                       | 列表，按 `updated_at` 倒序                          |
| POST   | `/api/projects`                       | body: `{name, description?, folder_id?}` → ProjectMeta |
| GET    | `/api/projects/{id}`                   | 单个 ProjectMeta（含 has_final_video 即时检测）     |
| PUT    | `/api/projects/{id}`                   | 部分字段更新（merge）；不要传 `progress.*` 字段     |
| DELETE | `/api/projects/{id}`                   | **删除整个目录，不可逆**——确认后执行             |
| POST   | `/api/projects/{id}/copy-config`       | body: `{source_project_id}`；复制 manuscript_config.json + characters.json |

### 文案

| 方法 | 路径                                  | body                                  |
|------|---------------------------------------|---------------------------------------|
| GET  | `/api/projects/{id}/manuscript`        | →`{content, config}`                  |
| PUT  | `/api/projects/{id}/manuscript`        | `{content:string, config:{...}}`      |

`config` 结构见 `dialogue-modes.md` 或 `pipeline.md` 第 2 节。

### 分镜

| 方法 | 路径                            | body                          |
|------|---------------------------------|-------------------------------|
| GET  | `/api/projects/{id}/scenes`     | →`{scenes:[...]}`             |
| PUT  | `/api/projects/{id}/scenes`     | `{scenes:[...完整数组...]}`   |

### 角色

| 方法 | 路径                                | body                                |
|------|-------------------------------------|-------------------------------------|
| GET  | `/api/projects/{id}/characters`     | →`{characters:[...]}`               |
| PUT  | `/api/projects/{id}/characters`     | `{characters:[...]}`                |

角色对象：`{name, role, traits, appearance, negative?, ...}`。

### 图片

| 方法 | 路径                                              | 说明                                                            |
|------|---------------------------------------------------|-----------------------------------------------------------------|
| GET  | `/api/projects/{id}/images`                       | 元数据 + 文件流 URL，**不带 base64**                            |
| PUT  | `/api/projects/{id}/images`                       | **旧版整 batch 上传**（含 base64），仅在小项目用                 |
| GET  | `/api/projects/{id}/images/file/{filename}`       | 直接拉 PNG 二进制                                                |
| PUT  | `/api/projects/{id}/images/slot`                  | 单张图片落盘，body: `{scene_id, frame_type, slot_index, data}`  |
| PUT  | `/api/projects/{id}/images/metadata`              | 仅更新元数据：`{counts, selected, slot_keys[]}`                  |

**1.3.4 之后强烈推荐 slot+metadata 两步法**，避免单次 PUT 携带超大 base64 字符串。

### 音频

| 方法 | 路径                          | body                                          |
|------|-------------------------------|-----------------------------------------------|
| GET  | `/api/projects/{id}/audio`    | →`{scene_id: {data, duration_ms, slots?[]}}`  |
| PUT  | `/api/projects/{id}/audio`    | 同上结构                                      |

### 视频

| 方法 | 路径                            | body                                              |
|------|---------------------------------|---------------------------------------------------|
| GET  | `/api/projects/{id}/videos`     | →`{scene_id:"<base64 mp4>"}`（大！避免常调用）   |
| PUT  | `/api/projects/{id}/videos`     | `[{scene_id, data:<base64 mp4>},...]`             |

### 视频提示词缓存

| 方法 | 路径                                 | body                          |
|------|--------------------------------------|-------------------------------|
| GET  | `/api/projects/{id}/video-prompts`   | →`{scene_id: "english prompt..."}` |
| PUT  | `/api/projects/{id}/video-prompts`   | 同上结构                      |

## 项目目录结构

```
<projects_dir>/<project_id>/
├── project.json                # ProjectMeta
├── manuscript.md
├── manuscript_config.json      # 创作配置（dialogue_mode 等）
├── characters.json
├── scenes.json
├── images.json                 # {saved_slots[], counts{}, selected{}}
├── images/                     # *.png
│   └── scene_001_start_0.png
├── audio.json                  # 每镜音频元数据 + base64
├── audio/
├── video/
│   ├── scene_001.mp4
│   ├── final_video.mp4         # 合并成片
│   ├── fixed_cfr.mp4           # 字幕生成时帧率标准化产物
│   ├── subtitles.srt
│   └── final_video_subbed.mp4  # 烧字幕产物
├── videos.json                 # {scene_id: filename}
├── video_prompts.json
└── cache/
```

## Windows 兼容性

- 所有 JSON 用 `utf-8-sig` 读取（兼容 BOM），写入用 `utf-8`（无 BOM）
- 中文路径与文件名通过 API 操作，**禁止 PowerShell 直接编辑** UTF-8 JSON 文件（会写入 GBK 导致后续读失败）

## 列表 vs 详情的取舍

- 探查多个项目状态用 `GET /api/projects`，按 `progress.*` 判断；**不要遍历每个项目调详情接口**。
- `GET /api/projects/{id}/videos` 会返回所有视频的 base64，体积巨大；判断是否已生成应该看 ProjectMeta 的 `progress.video` 或 `has_final_video`。
