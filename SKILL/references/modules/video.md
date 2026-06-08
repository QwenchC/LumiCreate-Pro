# video 模块（LTX-2.3 视频生成）

通过 ComfyUI 加载 LTX-2.3 工作流，输入"首帧 + 末帧 + 音频"生成单分镜视频，最后用 ffmpeg concat 合并为成片。

## 接口

| 方法 | 路径                                       | 流式 | 用途                                       |
|------|--------------------------------------------|------|--------------------------------------------|
| GET  | `/api/video-engine/test`                   | ✗    | 探活视频 ComfyUI                            |
| GET  | `/api/video-engine/workflows`              | ✗    | **v1.4.2** 列工作流：bundled + 硬白名单，仅 `flfa2i-lumicreate` / `video_ltx2_3_i2v` |
| GET  | `/api/video-engine/workflow-info?workflow_name=X` | ✗ | **v1.4.1+** `{kind, requires_start_image, requires_end_image, supports_audio, supports_duration, label}` |
| POST | `/api/video-engine/generate-stream`        | ✓    | 按 kind 分发到 flfa2i / i2v driver           |
| POST | `/api/video-engine/merge-project-video`    | ✗    | ffmpeg 合并为 `final_video.mp4`             |
| POST | `/api/video-engine/mix-bgm`                | ✗    | **v1.4.2** 在已成视频上叠加音乐库 BGM       |
| PUT  | `/api/video-engine/bgm/{pid}`              | ✗    | 上传 BGM (`bgm.<ext>`)，merge 通道用        |
| GET / DELETE | `/api/video-engine/bgm/{pid}`      | ✗    | 查 / 删 BGM                                  |

## workflow-info（v1.4.1+）

调用 `generate-stream` **之前**先查 kind 决定走哪条管线：

```http
GET /api/video-engine/workflow-info?workflow_name=video_ltx2_3_i2v
→ {
  "kind": "video_i2v",
  "requires_start_image": true,
  "requires_end_image":   false,
  "supports_audio":       false,
  "supports_duration":    true,
  "label": "单帧 + 时长 (LTX-2.3 i2v)"
}
```

| kind            | 必填资产          | 说明                                                            |
|-----------------|-------------------|-----------------------------------------------------------------|
| `video_flfa2i`  | 首帧 + 末帧 + 音频 | 默认。`audio_b64=""` 时**自动注入等长静音 WAV**（绕过 LoadAudio 严格校验）|
| `video_i2v`     | 仅首帧            | 单图 + duration_ms 控制时长；不接受音频                          |

## generate-stream 请求

```json
{
  "workflow_name": "flfa2i-lumicreate",
  "resolution": "720x1280",      // 自动按 32 对齐, clamp 64..1280
  "fps": 25.0,                   // 24/25/30
  "scenes": [
    {
      "scene_id": "scene_001",
      "scene_index": 1,
      "start_image_b64": "...",  // 必填，base64 PNG
      "end_image_b64": "...",    // 必填
      "audio_b64": "...",        // 必填，wav 或 mp3 base64
      "duration_ms": 8000,
      "positive_prompt": "<英文 video prompt>"
    },
    ...
  ]
}
```

**必填三要素缺一不可**，缺失会发 `scene_error` 跳过该镜继续。

**关于 `audio_b64` 的格式**：
- WAV（IndexTTS stitch 结果）和 MP3（Edge TTS reading 模式）**都能直接用**。
- 后端写入 ComfyUI input/ 时强制命名为 `lumi_aud_{scene}.wav`，但内容字节不变；ComfyUI LoadAudio 节点按内容识别格式。
- 客户端只传纯 base64 字符串，**不要加 `data:audio/...;base64,` 前缀**。

**SKILL 调用 reading 模式时的常见错误**：
- ❌ 仅生成音频后直接进入视频生成，但**没有先生成图片** → 每镜 `scene_error: 缺少首帧图片`
- ❌ 直接把 `__ms_reading__{id}` 的 audio 在视频请求里再 base64 一次（双重编码）
- ✅ 正确流程：图片批量生成 → 等待全部 `completed` 落盘 → 取每镜 selected slot 的 PNG 转 base64 → 调 `ms-tts` 拿 mp3 base64 → 三件套传给 video-engine

## mix-bgm（v1.4.2）

合并视频 / 烧字幕完成后在已成视频上叠加音乐库 BGM。**视频流 `-c:v copy` 不重编码**，
30 秒成片秒级完成（只编码音轨）。源视频保留，输出新文件 `<source>_with_bgm.mp4`。

```http
POST /api/video-engine/mix-bgm
{
  "project_id":         "<pid>",
  "source":             "final_video",        // 或 "final_video_subbed"（烧字幕版）
  "track_id":           42,                    // 来自 /api/music/tracks
  "bgm_volume_db":      -12.0,                 // 推荐 -10 ~ -15
  "original_volume_db": 0.0,                   // 推荐 0 或略提
  "fade_in_ms":         800,
  "fade_out_ms":        1500,
  "loop_bgm":           true                   // BGM 短于视频时循环
}
→ {
  "output_path":     "<abs path>",
  "output_filename": "final_video_with_bgm.mp4",
  "duration_secs":   45.0,
  "bgm_track_id":    42
}
```

⚠️ `source` 只接受 `"final_video"` 或 `"final_video_subbed"`；其它字符串 400。
⚠️ ffmpeg `filter_complex` 自动按 ffprobe 出的视频时长对齐淡出起点 `st=duration-fade_out`。

**何时用 mix-bgm vs merge 内置 BGM？**
- **合并前注入**（`PUT /api/video-engine/bgm/{pid}` 或 `POST /api/music/track/{id}/set-as-bgm`）→ 下次合并视频时由 merge 端点的 BGM 通道处理。需要重新合并。
- **后期叠加**（mix-bgm）→ 不重新合并，直接在已成片上加 BGM。视频流不重编码。推荐用于"先做完字幕烧录、再选首歌叠 BGM"的工作流。

## SSE 事件

| event           | 字段                                                                          |
|-----------------|-------------------------------------------------------------------------------|
| `scene_start`   | `{scene_id, scene_index, current, total}`                                     |
| `queued`        | `{prompt_id, scene_id}` ComfyUI 已接受任务                                    |
| `progress`      | `{value, max, scene_id}` ComfyUI 推理进度                                      |
| `scene_retrying`| `{scene_id, message}` VRAM 自动重试                                           |
| `scene_done`    | **`{scene_id, scene_index, video:"<b64 mp4>", filename, mime:"video/mp4"}`** |
| `scene_error`   | `{scene_id, scene_index, message}`                                            |
| `batch_done`    | `{total}`                                                                     |

最后：`data: [DONE]`。

⚠️ 视频 base64 字段叫 **`video`**，不是 `video_b64`。前端 VideoTab.vue 实现：`sceneVideos[scene_id] = evt.video`。

## VRAM 自动重试

后端检测到 ComfyUI 报错包含 `should be the same`（CUDA/CPU 权重错配信号）时：
1. 发 `scene_retrying`
2. 调 `POST {comfyui_url}/free` 释放显存
3. 等 3 秒后重新跑当前 scene 一次
4. 仍失败则发 `scene_error` 跳过

**只重试一次**，不要在客户端再额外重试。

## LiteGraph → API 转换

LumiCreate 自动把 ComfyUI LiteGraph UI 格式的 workflow 转成 API 格式，处理：
- SetNode/GetNode 传送对
- Bypass 节点
- 虚拟节点过滤
- UI-only 输入过滤
- dict 形式 widgets_values
- wv_idx 偏移
- VAELoaderKJ → VAELoader 自动替换

如果用户自己导出的 workflow 报错，**优先确认是否走了这条路径**。

## 落盘协议

每个 `scene_done` 事件后，立即把 **`evt.video`**（注意：字段名 `video`）保存：
```http
PUT /api/projects/{id}/videos
[
  {"scene_id":"scene_001","data":"<b64 mp4 from evt.video>"}
]
```
（注意：当前 PUT 接口是整体覆盖，更优做法是攒齐所有分镜一次 PUT）

**音频替换**：后端 LTX 生成完后会自动用用户原始 `audio_b64` 通过 ffmpeg 替换 AI 解码音轨（更清晰、无失真），客户端拿到的 `evt.video` 已经是替换后的版本。

## 合并成片

```http
POST /api/video-engine/merge-project-video
{
  "project_id": "<id>",
  "scene_order": ["scene_001","scene_002","scene_003"]
}
→ {"output_path":".../video/final_video.mp4","output_dir":".../<project>"}
```

执行 `ffmpeg -f concat -safe 0 -i list.txt -c copy final_video.mp4`，要求：
- 所有分镜视频 codec / 分辨率 / fps 一致（由 LTX 工作流保证）
- 缺任意一镜的 mp4 会报 400 `分镜 X 尚无视频`

## ffmpeg 定位

后端通过 `services/ltx2video.py:_find_ffmpeg` 查找：
1. `settings.video_engine.comfyui_input_dir` 的祖先目录中 `.ext/Library/bin/ffmpeg.exe`
2. `settings.video_engine.workflow_dir` / `image_engine.workflow_dir` 的祖先
3. PATH

未找到时 `merge-project-video` 直接 500 `未找到 ffmpeg`。

## 性能与建议

- 单分镜 LTX-2.3 720×1280 / 8s 视频约 30s ~ 3min（看 GPU 与采样步数）
- 批量是**严格顺序**，不并发（单 GPU）
- 视频 base64 体积大，**前端流式收到后立即写盘并释放内存**
- 用户中断生成只能在前端断开 SSE，后端无显式 cancel；ComfyUI 当前作业会继续到完成
- **漫剧默认分辨率 `720x1280` 竖屏 / `fps=25`**，与 LTX-2.3 工作流匹配
- **分镜单段时长**：手动分镜 ≤ 50 字符约 12.5 秒，视频 `duration_ms` 取 `audio.duration_ms` 即可；超过 25 秒的分镜要警惕 LTX 工作流稳定性

## 视频提示词

视频 prompt 由 `text generate-video-prompt` 流式生成，前端把英文 prompt 缓存到：
```http
PUT /api/projects/{id}/video-prompts
{ "scene_001": "...", "scene_002": "..." }
```
下次进入视频页可直接取，无需重生成。
