# video 模块（视频生成）

两条产出路径，**输出协议完全一致**（`<project>/video/<scene_id>.mp4` + `videos.json`）：

1. **LTX-2.3（v1.4.0+）**：ComfyUI 工作流"首帧 + 末帧 + 音频" → AI 视频。需要 GPU/VRAM。
2. **图片放映（v1.4.6+）**：图片+音频→ffmpeg 渲染静态/Ken Burns 画面。**无 GPU 也能跑**，给低显存用户用。

两路产出的子片 schema 相同，merge 流程统一。

## 接口

| 方法 | 路径                                       | 流式 | 用途                                       |
|------|--------------------------------------------|------|--------------------------------------------|
| GET  | `/api/video-engine/test`                   | ✗    | 探活视频 ComfyUI                            |
| GET  | `/api/video-engine/workflows`              | ✗    | **v1.4.2** 列工作流：bundled + 硬白名单，仅 `flfa2i-lumicreate` / `video_ltx2_3_i2v` |
| GET  | `/api/video-engine/workflow-info?workflow_name=X` | ✗ | **v1.4.1+** `{kind, requires_start_image, requires_end_image, supports_audio, supports_duration, label}` |
| POST | `/api/video-engine/generate-stream`        | ✓    | 按 kind 分发到 flfa2i / i2v driver           |
| POST | `/api/video-engine/render-slideshow`       | ✗    | **v1.4.6** 图片放映视频：图片+音频 → ffmpeg 渲染（无 GPU 通路） |
| POST | `/api/video-engine/merge-project-video`    | ✗    | ffmpeg 合并为 `final_video.mp4` —— **v1.4.6 改为清编码**（移除 -c copy，统一 WMP 兼容）|
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

## render-slideshow（v1.4.6）

**给没 GPU 或不想跑 LTX 的用户的轻量通路**：用每镜次的图片 + 音频通过 ffmpeg 直接渲染。
输出与 LTX 同 schema → 后续 `merge-project-video` / `subtitle-engine/embed` 都能直接复用。

```http
POST /api/video-engine/render-slideshow
{
  "project_id":          "<pid>",
  "scene_order":         ["scene_001","scene_002",...],
  "width":               1920,            // 输出宽度
  "height":              1080,            // 输出高度
  "fps":                 25,              // 24|25|30 标准帧率
  "intra_transition":    "fade",          // 单镜内 2 张图之间的转场
  "intra_transition_ms": 800,
  "default_no_audio_ms": 4000,            // 无音频镜次默认时长
  "motion_effect":       "none",          // Ken Burns 画面动态
  "parallel":            0                // 0=按 CPU 自动；1=顺序；≥2=显式
}
→ {
  "ok": true,
  "rendered": ["scene_001","scene_002"],
  "skipped":  [{"scene_id":"scene_003","reason":"缺首帧图"}],
  "errors":   [],
  "output_dir": ".../<project>/video",
  "scene_files": {"scene_001":"scene_001.mp4", ...},
  "parallel_workers": 4
}
```

`motion_effect` ∈ `none / zoom_in / zoom_out / pan_left / pan_right / pan_up / pan_down`：
- `none` → 纯静帧（最快）
- 其它 → Ken Burns，**4× lanczos 预放大 + zoompan + 下采样** 防整像素抖动
- 无 GPU 用户优先 `none` 或 `zoom_in/zoom_out`，平移类的 GPU/CPU 开销略高

**镜次资产解析**：
- 首帧：从 `scene_assets.image_start`（优先 selected slot）
- 末帧：可选；存在则单镜内做转场
- 音频：从 `scene_assets.audio`（同样选 selected slot）
- **时长**：v1.4.6+ 一律以 **ffprobe 实测音频时长** 为准，**不再信** `scene_assets.metadata.duration_ms`（TTS 请求时的目标时长，与产出常差几十-几百 ms，累积到字幕拖尾/音画错位）

**ffmpeg 编码档**（每镜次 + 合并 + 烧字幕全链统一）：
- `-c:v libx264 -profile:v main -level 4.0 -preset fast -crf 22`
- `-pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709`
- `-maxrate 8M -bufsize 16M` ← 关键：Level 4.0 上限 ~25 Mbps，CRF 撞顶会让 WMP 拒播
- `-video_track_timescale 90000 -vsync cfr -g 30 -keyint_min 30 -sc_threshold 0`（concat 边界对齐）
- `-c:a aac -b:a 192k -ar 48000 -ac 2`（48k 与 merge/burn 对齐）
- `-af aresample=async=1000:first_pts=0`（修复 AAC priming 累积 drift）
- `-movflags +faststart`（moov atom 提前，WMP / Movies & TV 可播）

**典型组合**：
```python
# 低显存用户漫剧默认（720x1280 竖屏 + 静帧 + 1s 转场）
await api.post("/api/video-engine/render-slideshow", {
    "project_id": pid,
    "scene_order": [s["id"] for s in scenes],
    "width": 720, "height": 1280, "fps": 25,
    "intra_transition": "fade", "intra_transition_ms": 800,
    "motion_effect": "none",
})
# → 直接接 merge-project-video 合并成片
```

⚠️ **画面是否动态**与目标用户群有关：用 Ken Burns 增加动态会让"图片放映"看起来更像 AI 视频，但 motion=`pan_*` 在 16 核机器上每镜次仍要 5-15s。如果用户机器是 4 核以下，建议默认 `motion_effect="none"` + 仅靠镜间转场撑动感。

⚠️ **并行渲染**：默认 `parallel=0` 时按 `cpu_count // 4` 自动选 worker 数（capped at 1-4）。libx264 单进程内部已用 4-6 核 → 多开 4 个进程在 16 核上能撑到 60%+ 利用率。机器很弱时显式 `parallel=1` 跑串行。

⚠️ **必须先有图 + 音频**：图片来自 `images` 模块（手动分镜每镜 ≥ 1 张首帧图），音频来自 `audio` 模块（reading 模式 `__ms_reading__{sceneId}`）。否则镜次进 `skipped`。

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
  "scene_order": ["scene_001","scene_002","scene_003"],
  "transition":             "cut",      // cut|fade|dissolve|wipeleft|wiperight|slideleft|slideright
  "transition_duration_ms": 300,
  "bgm_volume_db":          -20.0,      // -100 表示关闭 BGM
  "bgm_fade_in_ms":         1000,
  "bgm_fade_out_ms":        1500
}
→ {"output_path":".../video/final_video.mp4","output_dir":".../<project>"}
```

**v1.4.6 重大改造**：移除 `-c copy` 快路径，统一改为**清编码**。两条路径产出同样的 Windows-safe mp4：

| 场景 | 路径 | 编码 |
|------|------|------|
| 无 BGM / 无 xfade | "快路径" concat demuxer → libx264 re-encode | 同下面编码档 |
| 有 BGM 或 xfade  | "慢路径" filter_complex(xfade/acrossfade/amix) → libx264 re-encode | 同下面编码档 |

**关键编码（v1.4.6）**：
- `libx264 -profile:v main -level 4.0 -crf 20~22 -maxrate 8M -bufsize 16M`
- `-vsync cfr -video_track_timescale 90000`
- 音频 **aresample=async=1000:first_pts=0 → aac -ar 48000 -ac 2**（消除跨镜次 PTS 间隙累积的 drift）

**为什么不再用 `-c copy`**（重要历史背景，diagnoses 见 [audio-video-sync.md](./audio-video-sync.md)）：
- `concat demuxer + -c copy` 要求所有输入 SPS/PPS/timebase/timescale 完全一致
- LTX 视频 + slideshow 静态/动态分镜混合时往往不一致 → 浏览器/VLC 能播，**WMP 拒播**
- 用户报告"数据速率和总比特率过高"是 WMP 的拒播信号
- 清编码 + bitrate cap 一次性消除所有跨镜次时基差异，多花 30s-数分钟换 100% 兼容

**先决条件**：
- 所有分镜视频已就位（缺任意一镜 → 400 `分镜 X 尚无视频`）
- 来自 LTX 或 slideshow 都可，schema 一致

## 视频生成路径选择决策树（v1.4.6）

```
用户机器有支持 LTX-2.3 的 GPU？  ──否──> render-slideshow（图片放映）
                              │
                              是
                              │
            用户要做漫剧/朗读视频，只需要静态画面？
                ├──是──> render-slideshow（更快、可控）
                │
                ├──否──> 用户明确要"动态镜头" → LTX-2.3 generate-stream
                │
                └──不确定 → 默认 LTX；用户反馈"生成太慢/显存不够"再降级到 slideshow
```

**漫剧 / 朗读视频的默认建议**：
- 高端 GPU（24G+）：LTX-2.3，画面有 AI 动态
- 中端 GPU（8-16G）：LTX-2.3 + 单镜短时长（≤ 5s）
- 低端 / 无 GPU：**render-slideshow + motion=`zoom_in` + 1s 转场**，体验已经很接近"AI 视频"

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
