# Music Module (v1.4.2+)

ACE-Step v1.5 音乐生成 + 全局音乐库 + 后期 BGM 混音 + 项目 BGM 直通。所有端点
都挂在 `http://127.0.0.1:18520/api/music/`，库数据落 `%APPDATA%/LumiCreate-Pro/music.sqlite`，
文件落同目录 `music/`。

## 端点

| 方法   | 路径                                      | 说明                                                             |
|--------|------------------------------------------|------------------------------------------------------------------|
| GET    | `/api/music/workflows`                   | 列举支持的音乐工作流（硬名单 + bundled）                          |
| POST   | `/api/music/generate-stream`             | SSE：生成 → 进度 → 完成自动入库；空 seed = 后端强制随机           |
| GET    | `/api/music/tracks?project_id=<pid>`     | 列表；自动过滤文件丢失或 < 1KB 的"幽灵"条目                       |
| GET    | `/api/music/track/{id}`                  | 单条元数据                                                         |
| PUT    | `/api/music/track/{id}`                  | `{name}` 重命名                                                   |
| DELETE | `/api/music/track/{id}`                  | 删除 DB + 文件                                                    |
| GET    | `/api/music/file/{id}`                   | 流式播放 MP3（前端可直接 `<audio :src>`）                          |
| POST   | `/api/music/cleanup`                     | 物理清理失效条目（文件丢失 / < 1KB），返回 `{deleted_count, deleted_ids}` |
| POST   | `/api/music/track/{id}/set-as-bgm`       | 复制为项目 BGM（`<project>/bgm/bgm.<ext>`），下次 merge 自动用     |

## 支持的工作流（硬白名单）

```
audio_ace_step_1_5_split_4b   # ACE-Step v1.5
```

仅识别此一个；用户 ComfyUI 目录里其它音频工作流不会出现在 `/workflows` 列表。

## 生成请求 schema

```http
POST /api/music/generate-stream
{
  "workflow_name":    "audio_ace_step_1_5_split_4b",
  "duration_seconds": 60,
  "bpm":              120,
  "time_signature":   "4",       // "3" | "4" | "6"
  "language":         "zh",      // "zh" | "en" | "ja" | "ko"
  "key_scale":        "C major", // 24 选 1：C/C#/D/.../B + major/minor
  "tags":             "国风电子摇滚...",   // 必填：风格段落（中文长描述）
  "lyrics":           "[Verse 1]\n...",    // 可选：纯器乐时留空
  "name":             "开场主题曲",        // 可选：track 显示名
  "project_id":       "<pid>",             // 可选：归属项目（仅过滤用）
  "seed":             null                 // null = 后端强制随机；显式数 = 复现
}
```

⚠️ **seed=null 必须送 `null` 或省略**：ComfyUI 的 "randomize" widget 是客户端逻辑，
经 `/prompt` API 永远用 literal seed。后端拿到 `null` 会注入 `random.randint(0, 2**63-1)`，
保证每次重新生成都是新曲；显式整数则可复现一首。

## SSE 事件

```
{"event": "queued",     "prompt_id": "...", "seed": 1234}
{"event": "progress",   "value": 1, "max": 20}
{"event": "completed",  "track_id": 42, "seed": 1234,
 "url": "/api/music/file/42", "filename": "lumi_music_*.mp3"}
{"event": "error",      "message": "..."}
```

`completed` 时后端**已自动入库 + 落盘**，前端只需重新拉 `/tracks` 刷新即可。

## AI 助写音乐 prompt（在 text 模块）

```http
POST /api/text-engine/generate-music-prompt
{
  "user_request":     "一首武侠燃曲...",   // 必填，用户简介
  "language":         "zh",
  "duration_seconds": 60,
  "bpm":              120,
  "time_signature":   "4",
  "key_scale":        "C major",
  "project_id":       "<pid>",       // 可选：读 manuscript.txt 注入剧情上下文
  "include_lyrics":   true            // false = 纯器乐，LLM 只填 tags
}
→ {"tags": "...", "lyrics": "[Intro]\n[Verse 1]\n...\n[Chorus]\n..."}
```

⚠️ LLM 提示词显式禁止把 BPM / 拍号 / 调式 / 时长写进 tags，因为这些都有独立结构化字段，
重复会被 ACE-Step 双倍套用降低质量。

## 项目 BGM 直通

```http
POST /api/music/track/{track_id}/set-as-bgm
{"project_id": "<pid>"}
→ {"ok": true, "track_name": "...", "bgm_path": ".../bgm/bgm.mp3", "filename": "bgm.mp3"}
```

- 清掉项目 `bgm/` 目录里所有旧 `bgm.<ext>`（mp3/m4a/wav/aac/ogg/flac 全部检查）
- 复制源音乐到 `bgm.<src 后缀>`
- 下次 `POST /api/video-engine/merge-project-video` 时由 merge 端点自带的 BGM 通道处理
  （`bgm_volume_db / bgm_fade_in_ms / bgm_fade_out_ms` 参数）

不影响原 track，库里这首仍可继续用。

## 失效条目处理

`/tracks` 列表**永远不返回**：
- 文件丢失（路径不存在）
- 文件体积 < 1KB（MP3 帧无法解析 → 提交失败留下的空壳）

调 `POST /api/music/cleanup` 物理清理；返回的 `deleted_count` 可向用户报告。

## 失败处理

- ComfyUI 报 `Node 'Song Duration' not found`：**已修复** —— 老式 `PrimitiveNode` 内联，
  不再当作 class_type 提交。如再次出现，检查 `services/comfyui.py::_litegraph_to_api`
  的 `primitive_values` 逻辑是否被改坏
- 入库失败（磁盘满 / 权限）：SSE 发 `{event:"error", message:"音乐入库失败: ..."}`
- 工作流不支持：`POST /generate-stream` 返 400 `不支持的音乐工作流: <name>`
