# image 模块（ComfyUI 图片生成）

通过 ComfyUI 工作流生成首/末帧图片，支持单张实时与全分镜批量并发。

## 接口

| 方法 | 路径                                          | 流式 | 用途                                            |
|------|-----------------------------------------------|------|-------------------------------------------------|
| GET  | `/api/image-engine/test`                      | ✗    | 探活 ComfyUI                                    |
| GET  | `/api/image-engine/workflows`                 | ✗    | 列工作流名（先本地目录，再 ComfyUI HTTP）       |
| GET  | `/api/image-engine/workflow/{name}`           | ✗    | 取单个工作流 JSON                               |
| POST | `/api/image-engine/generate-stream`           | ✓    | 单张生成                                        |
| POST | `/api/image-engine/generate-batch-stream`     | ✓    | 全分镜 × N 并发                                 |

## 单张：generate-stream

```json
{
  "workflow_name": "lumicreate-基础",
  "positive_prompt": "<英文 prompt>",
  "negative_prompt": "",
  "seed": null,                  // null=随机
  "width": 0,                    // 0=用 settings.image_width
  "height": 0,
  "scene_id": "scene_001",       // 这些 meta 字段会回填到所有事件
  "frame_type": "start",         // start|end
  "slot_index": 0
}
```

SSE 事件链：
1. `queued{prompt_id}`
2. `progress{value,max}` 多次
3. `completed{images:[{filename,data:<base64 png>,type}]}`（或 `error{message}`）
4. `data: [DONE]`

## 批量：generate-batch-stream

```json
{
  "workflow_name": "lumicreate-基础",
  "gen_count": 3,
  "negative_prompt": "",
  "width": 0,
  "height": 0,
  "frames": [
    {"scene_id":"scene_001","frame_type":"start","prompt":"..."},
    {"scene_id":"scene_001","frame_type":"end",  "prompt":"..."},
    {"scene_id":"scene_002","frame_type":"start","prompt":"..."},
    {"scene_id":"scene_002","frame_type":"end",  "prompt":"..."}
  ]
}
```

后端 `asyncio.gather` 起 `len(frames) * gen_count` 个并发任务，所有事件多路复用到一个流。`gen_count` 上限 10。

**事件路由**：每事件都带 `scene_id` / `frame_type` / `slot_index`。结束信号：
1. `batch_done{total}`
2. `data: [DONE]`

## 落盘协议（推荐）

收到一张 `completed` 事件就立即写盘：
```http
PUT /api/projects/{id}/images/slot
{ "scene_id":"...","frame_type":"start","slot_index":0,"data":"<base64>" }
```

所有图片接收完后再写一次元数据：
```http
PUT /api/projects/{id}/images/metadata
{
  "counts": {"scene_001:start":3,"scene_001:end":3,...},
  "selected": {"scene_001:start":0,"scene_001:end":0,...},
  "slot_keys": [{"scene_id":"scene_001","frame_type":"start","slot_index":0},...]
}
```

## 画风一致性约定（重要）

- **prompt 不含画风词**（如 "anime style"）—— 画风由 `settings.image_engine.style_preset` 在工作流节点中注入
- **prompt 不含情绪/表情词**（如 smile/sad）—— 这是 LumiCreate 的硬规则，由 LLM prompt 模板保证
- 多角色场景必须在 prompt 中显式点名（"林夏 wearing X, 张川 wearing Y"），禁止用人称代词

## 工作流文件位置

ComfyUI 端：默认 `<ComfyUI>/user/default/workflows/*.json`
LumiCreate 通过 `settings.image_engine.workflow_dir` 直接读本地文件（更快）。

如果本地目录为空或不可达，会回退到 ComfyUI 的 `/api/userdata?dir=workflows`。

## 失败处理

- ComfyUI 进程未起：`GET /test` 返回 success=false；继续调 `/generate-stream` 会得到 connection refused
- 工作流名不存在：返回 404 `工作流 '<name>' 未找到`
- ComfyUI 报模型/节点缺失：在 SSE 中作为 `error{message}` 事件传回，**该任务跳过，其他任务继续**
- VRAM 不足：批量并发应降低 `gen_count`；视频引擎有自动重试，图片引擎无
