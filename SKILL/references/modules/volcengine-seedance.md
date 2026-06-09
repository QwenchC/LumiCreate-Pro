# Volcengine Seedance 视频引擎（v1.4.10+）

云端付费 API 通路。给"不想跑 LTX-2.3 / 没 GPU / 想要更高画质"的用户用。
**完全可选**：默认 `engine_type="comfyui"`，老配置升上来行为 0 改变。

## 数据流

```
VideoTab.startGeneration
  → POST /api/video-engine/generate-stream
    → router 读 settings.video_engine.engine_type
      ├─ "comfyui"            → 原 ltx2video.generate_video / generate_video_i2v
      └─ "volcengine_seedance" → services/volcengine_seedance.generate_video_seedance
```

Driver 暴露 **同样的 SSE 事件 schema**（queued / progress / completed / error），
所以下游 `record_asset` / `videos.json` / merge / 字幕烧录 / SFX 全部无感复用。

## API 协议（按火山方舟 Ark 通用约定）

> 火山引擎 Seedance 2.0 官方文档：
> https://www.volcengine.com/docs/82379/1520757

**鉴权**：`Authorization: Bearer <ARK_API_KEY>`

**异步任务模式**（与 Ark chat 不同——视频生成是耗时操作，走 task）：

| 步骤 | Method + Path | 说明 |
|------|---------------|------|
| 1. 创建任务 | `POST {base_url}/contents/generations/tasks` | body: `{model, content[]}` |
| 2. 轮询状态 | `GET  {base_url}/contents/generations/tasks/{task_id}` | 直到 `status == "succeeded"` |
| 3. 下载视频 | `GET  <response.content.video_url>` | mp4 字节流 |

**Content 数组**（按官方文档 v1.4.10 对齐）：
```json
[
  {"type": "text", "text": "a dragon flies over mountains"},
  {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}, "role": "first_frame"},
  {"type": "image_url", "image_url": {"url": "..."}, "role": "last_frame"}
]
```

- text 保持干净的提示词，**不再贴 `--key value` hint**（生成参数走 request body）
- 单图（图生视频-首帧）：1 个 image_url，role 显式打 `first_frame`（更稳）
- 双图（图生视频-首尾帧）：2 个 image_url，role 必填 `first_frame` + `last_frame`
- url 字段接受 base64 data URL（`data:image/png;base64,xxx`）或公网 https URL；驱动自动判断+加前缀

**生成参数走 request body**（新方式，强校验；旧方式 prompt --hints 仍兼容）：
```json
{
  "model": "doubao-seedance-2-0-260128",
  "content": [...],
  "resolution": "720p",          // 480p / 720p / 1080p
  "ratio": "adaptive",           // 16:9 / 9:16 / 1:1 / 4:3 / 3:4 / 21:9 / adaptive
  "duration": 5,                 // 整数秒；Seedance 2.0/1.5 范围 4-15
  "seed": -1,                    // -1 随机；其它复现
  "generate_audio": false,       // 漫剧 reading 模式 = false（TTS 独立产出）
  "watermark": false,            // AI 生成水印
  "camera_fixed": false          // 固定摄像头（Seedance 2.0 不支持）
}
```

**状态收敛**：driver 把 `success / completed → succeeded`，`processing / in_progress
→ running` 等同义词都映射到固定 5 状态 `queued / running / succeeded / failed /
cancelled`。

## 设置项（settings.video_engine.*）

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `engine_type` | `"comfyui"` | 切换：`"comfyui"` ↔ `"volcengine_seedance"` |
| `volcengine_base_url` | `https://ark.cn-beijing.volces.com/api/v3` | Ark 端点；用户在控制台看自己区域 |
| `volcengine_api_key` | `""` | ARK_API_KEY，控制台 → API Key 管理 |
| `volcengine_model_id` | `""` | endpoint ID（典型 `ep-2024...-xxxxx`）或模型别名（如 `doubao-seedance-2-0-260128`） |
| `volcengine_duration_secs` | `5` | 单镜时长，整数秒；Seedance 2.0/1.5 范围 4-15 |
| `volcengine_resolution` | `"720p"` | 480p / 720p / 1080p（Seedance 2.0 fast 不支持 1080p） |
| `volcengine_ratio` | `"adaptive"` | 16:9 / 9:16 / 1:1 / 4:3 / 3:4 / 21:9 / adaptive |
| `volcengine_use_image` | `true` | 是否走 i2v / flf2v；`false` 则纯 t2v |
| `volcengine_generate_audio` | `false` | 漫剧 reading 模式 = false（TTS 独立产出）；非漫剧 = true 让模型自带音频 |
| `volcengine_watermark` | `false` | 视频右下角 "AI 生成" 水印 |
| `volcengine_camera_fixed` | `false` | 固定摄像头（Seedance 2.0 暂不支持） |
| `volcengine_seed` | `-1` | -1 随机；其它整数复现 |
| `volcengine_poll_interval` | `5` | 轮询间隔（秒） |
| `volcengine_poll_timeout` | `600` | 轮询总超时（秒） |

## API 端点

| Method | Path | Note |
|--------|------|------|
| GET    | `/api/video-engine/test`              | 按 `engine_type` 分派：comfyui 探 ComfyUI；volcengine 探 Ark |
| GET    | `/api/video-engine/volcengine-test`   | **不依赖** engine_type，独立测火山引擎连通性（用户切换之前可以先测） |
| GET    | `/api/video-engine/workflows`         | volcengine 模式下返合成名 `["volcengine_seedance"]` |
| POST   | `/api/video-engine/generate-stream`   | SSE，按 engine_type dispatch |

## 与现有通路的相容性

- **LTX 与 slideshow 完全保留**：volcengine 选项是新增的第三条路；切到 volcengine
  时 ComfyUI 配置仍保留在 settings.json，切回去无需重新填
- **音频通路独立**：Seedance 是纯画面 i2v，不接受 audio_b64。reading 模式下
  TTS 仍然先跑，然后视频生成完成后由 ffmpeg 后期合成（与 LTX 流程一致）
- **分辨率约定不同**：LTX 用 "1280x720" 这种 WxH 字符串；Seedance 用 "720p"
  档位字符串。两者各自管自己的字段（`resolution` vs `volcengine_resolution`）

## 成本说明

云端 API 按生成时长 / 分辨率 / 模型计费。**前端 TitleBar 不展示余额** ——
用户在火山方舟控制台查。VideoTab 工具栏左上有 `☁ 火山引擎云端` 徽章提醒"现在
跑批会花钱"，徽章 hover title 解释。

## ⚠️ 实操注意

- **跑批前必测连接**：设置页填完 base_url + api_key + model_id 后点「🔌 测试连接」，
  确认 200 OK 再去 VideoTab 跑批。错误的 model_id / key 会让每一镜都失败但仍计费
- **官方文档与本实现的字段映射**：本实现按 Ark 通用约定做（Bearer auth + 多模态
  content 数组），如果官方 Seedance 2.0 文档实际字段不一样（比如要求把 image 放
  到顶层 `image` 字段而不是 content 数组），驱动会从 4xx 响应里把原始错误体回传
  到 SSE error 事件 —— 用户看到具体哪个字段被拒，对照文档改设置页 base_url
  或后续小升级补 driver 即可
- **轮询超时**：单镜 5s 视频通常 30-120s 出结果；批量 30 镜的话 600s 超时是按
  单镜算的，每镜次独立计时

## 回归测试

`backend/tests/test_volcengine_seedance.py`：
- 老配置兼容（无新字段 → 默认值填充）
- /workflows + /test dispatch 按 engine_type 分支
- 独立 /volcengine-test 端点
- driver SSE 事件序列与 LTX 一致
- content payload 字段构造正确性
- 状态同义词收敛
