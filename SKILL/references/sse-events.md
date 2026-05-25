# SSE 事件格式速查

LumiCreate 后端流式接口统一使用 `text/event-stream`：

```
data: {"event":"...","..."}\n\n
...
data: [DONE]\n\n
```

**结束信号**：固定字符串 `data: [DONE]`，**不是 JSON**，按字符串比较。

## 文本引擎

### `POST /api/text-engine/generate-manuscript`
```
data: {"text":"<增量片段>"}
data: {"text":"<增量片段>"}
data: {"error":"<异常字符串>"}    # 可选
data: [DONE]
```
客户端：把所有 `text` 顺序拼接得到完整文案。

### `POST /api/text-engine/generate-character-appearance` / `generate-video-prompt`
同上格式：`{"text":...}` 累积。

### `POST /api/text-engine/generate-scenes` / `generate-frame-prompts` / `generate-character-profile` / `suggest-scene-characters`
**不是流式 SSE，而是普通 JSON 响应**（虽然内部用 LLM 流式，但聚合后返回完整对象）。

## 图片引擎

### `POST /api/image-engine/generate-stream`（单张）
每个事件都带 meta：`scene_id` / `frame_type` / `slot_index`。

| event       | 关键字段                                       |
|-------------|------------------------------------------------|
| `queued`    | `{prompt_id}`                                  |
| `progress`  | `{value,max}` 0~max                            |
| `completed` | `{images:[{filename, data:<base64 png>, type}]}` |
| `error`     | `{message}`                                    |

最后一行：`data: [DONE]`。

### `POST /api/image-engine/generate-batch-stream`（并发批量）
事件流为所有任务的多路复用，**事件顺序非线性**（按完成时间）。每事件携带 `scene_id`/`frame_type`/`slot_index` 用于路由 UI。

| event        | 含义                                                  |
|--------------|-------------------------------------------------------|
| `queued`     | ComfyUI 已接受任务                                    |
| `progress`   | 单张进度                                              |
| `completed`  | 一张图完成（含 base64）                              |
| `error`      | 该任务失败                                            |
| `batch_done` | `{total}` 总任务数都已结算                            |

**注意**：`batch_done` 后还会发一行 `data: [DONE]`。

## 音频引擎

### `POST /api/audio-engine/generate-stream` / `generate-batch-stream`
每事件带 `scene_id` / `dialogue_id` / `slot_index`。

| event       | 关键字段                                                                    |
|-------------|------------------------------------------------------------------------------|
| `queued`    | (可选，IndexTTS 不一定发)                                                    |
| `progress`  | `{message}` 文本进度                                                         |
| `completed` | **`{data:<base64 wav>, mime:"audio/wav", id?}`**（字段就叫 `data`，**不是 `audio`**） |
| `error`     | `{message}`                                                                  |
| `batch_done`| 仅批量接口                                                                   |

⚠️ 客户端从 SSE 取音频 base64 用 `evt["data"]`，不是 `evt["audio"]`。

### `POST /api/audio-engine/ms-tts`
**普通 JSON**，不是 SSE：
```json
{"data":"<base64 mp3>","duration_ms":N,"format":"mp3"}
```

### `POST /api/audio-engine/stitch-scene`
**普通 JSON**：
```json
{"data":"<base64 wav>","duration_ms":N}
```

## 视频引擎

### `POST /api/video-engine/generate-stream`
分镜顺序执行，每镜事件序列：

| event           | 字段                                                                      |
|-----------------|---------------------------------------------------------------------------|
| `scene_start`   | `{scene_id, scene_index, current, total}`                                 |
| `queued`        | `{prompt_id, scene_id}` ComfyUI 任务已排队                                |
| `progress`      | `{value, max, scene_id}` (ComfyUI 进度)                                    |
| `scene_retrying`| `{scene_id, message}`（VRAM 自动重试一次）                                |
| `scene_done`    | **`{scene_id, scene_index, video:<b64 mp4>, filename, mime:"video/mp4"}`** |
| `scene_error`   | `{scene_id, scene_index, message}`                                        |
| `batch_done`    | `{total}`                                                                 |

最后：`data: [DONE]`。

⚠️ 客户端取视频 base64 用 `evt["video"]`，**不是 `evt["video_b64"]`**。前端 VideoTab 的实现是 `sceneVideos[scene_id] = evt.video`。

## 字幕引擎

### `POST /api/subtitle-engine/generate-srt`
每事件结构 `{step, message, pct?}`，`step` 取值：

1. `normalize_fps`      （生成 fixed_cfr.mp4，含 `pct`）
2. `extract_audio`
3. `load_model`
4. `align`              （含 `pct`）
5. `cut`
6. `write_srt`
7. `done`               （成功完成）
8. `error`              （`message` 字段为错误描述）

结束 `data: [DONE]`。

### `POST /api/subtitle-engine/embed`
事件 `{step, message, pct?}`：
- `embedding` (pct 0~100)
- `done` / `error`

结束 `data: [DONE]`。

## Python 参考解析骨架

```python
import httpx, json, asyncio

async def sse(url, json_body):
    async with httpx.AsyncClient(timeout=None) as c:
        async with c.stream("POST", url, json=json_body) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    return
                yield json.loads(payload)
```

调用：
```python
async for evt in sse("http://127.0.0.1:18520/api/text-engine/generate-manuscript",
                    {"config":{...}}):
    if "text" in evt:
        print(evt["text"], end="", flush=True)
```
