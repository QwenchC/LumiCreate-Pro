# image 模块（ComfyUI 图片生成）

通过 ComfyUI 工作流生成首/末帧图片，支持单张实时与全分镜批量并发。

## 接口

| 方法 | 路径                                          | 流式 | 用途                                            |
|------|-----------------------------------------------|------|-------------------------------------------------|
| GET  | `/api/image-engine/test`                      | ✗    | 探活 ComfyUI                                    |
| GET  | `/api/image-engine/workflows`                 | ✗    | **v1.4.4** bundled + 硬白名单（4 个：`t2i-lumicreate / image_flux2_text_to_image_9b / image_flux2_klein_image_edit_9b_base / sd_default_workflow`） |
| GET  | `/api/image-engine/model-info`                | ✗    | **v1.4.4** SD 面板用：从 ComfyUI `/object_info` 抽 `{checkpoints, loras, samplers, schedulers}` 枚举 |
| GET  | `/api/image-engine/workflows-all`             | ✗    | 不过滤全量（调试用）                            |
| GET  | `/api/image-engine/workflow-info?workflow_name=X` | ✗ | **v1.4.3** `{kind, ref_count, ref_nodes}`；kind ∈ `t2i / i2i_single / i2i_double / i2i_multi / unknown` |
| GET  | `/api/image-engine/workflow/{name}`           | ✗    | 取单个工作流 JSON                               |
| POST | `/api/image-engine/generate-stream`           | ✓    | 单张生成；支持 `refs[]`（i2i 参考图）           |
| POST | `/api/image-engine/generate-batch-stream`     | ✓    | 全分镜 × N 并发；每 frame 可带 `refs`           |

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

## i2i 工作流参考图（v1.4.3）

### kind 与 ref_count 决策表

调 `generate-stream / generate-batch-stream` **前**先查 `workflow-info`：

```http
GET /api/image-engine/workflow-info?workflow_name=image_flux2_klein_image_edit_9b_base
→ {
  "kind": "i2i_double",        # 由真实 LoadImage 节点数（展平 subgraph 后）决定
  "ref_count": 2,
  "ref_nodes": [{"node_id": 76, "input_widget": 0}, {"node_id": 81, "input_widget": 0}],
  "actual_loadimage_count": 2,
  "found": true
}
```

| kind          | ref_count | 说明 |
|---------------|-----------|------|
| `t2i`         | 0         | 文生图，无参考图槽位                                  |
| `i2i_single`  | 1         | 1 张参考图                                             |
| `i2i_double`  | 2         | 2 张参考图（典型：Flux.2 image edit）                  |
| `i2i_multi`   | N (3-8)   | **v1.4.3**：3+ LoadImage 节点；ref_count 按真实节点数 |
| `unknown`     | 0         | 未识别，不出现在下拉里                                  |

**v1.4.3 关键修复**：分类器优先按**节点数**判（展平 subgraph 后数 LoadImage），名字关键词只在节点扫不到时兜底。
之前 `image_flux2_klein_image_edit_9b_base` 因为名字含 `image_edit` 被早期 return 强行判为 `i2i_single`，
UI 只显示 1 个参考图槽位，丢了第二张。

### 灵活参考图数（v1.4.3）

`generate-stream` 的 `refs` 字段**接受 1 到 ref_count 张参考图**（不再强制等于）：

```json
{
  "workflow_name": "image_flux2_klein_image_edit_9b_base",   // i2i_double
  "positive_prompt": "...",
  "refs": [
    {"kind":"portrait","project_id":"<pid>","char_name":"林夏","filename":"portrait_1.png"}
    // 只传 1 张也能成功
  ],
  ...
}
```

**后端行为**：当 `len(refs) < N (LoadImage 节点数)`，自动**复制最后一张 ref** 填满剩余节点。
- 双图工作流 + 1 张参考 → 两个 LoadImage 都填这张 → 模型当作"单图编辑"
- 双图工作流 + 2 张参考 → 各 LoadImage 填各自的 → 模型当作"双图合成"
- 0 张 → 拒绝（无意义生成）
- 超出 N → 拒绝（防止误传）

**对智能体的影响**：不再需要为"双图工作流"额外凑第二张参考图（如复制角色立绘充数）。
传 1 张就行，后端会复制。如果就是想"用两张不同图合成"，传 2 张。

### refs 字段 schema

每个 ref 三选一：

```jsonc
// portrait：项目角色立绘
{"kind":"portrait", "project_id":"<pid>", "char_name":"林夏", "filename":"portrait_1.png"}

// element：全局/项目元素库
{"kind":"element", "scope":"global", "element_id": 42}
{"kind":"element", "scope":"project:<pid>", "element_id": 7}

// path：绝对路径（测试 / 高级场景）
{"kind":"path", "path":"/abs/path/img.png"}
```

`generate-batch-stream` 在每个 `frames[i]` 里也接受 `refs`。

## SD 工作流参数化（v1.4.4）

`sd_default_workflow` 是通用 Stable Diffusion t2i 工作流，含 **Checkpoint + 7 槽 LoRA 链 + 正/负提示词 + 尺寸 + KSampler**，**所有参数都通过 `sd_params` 字段在生成请求里动态打补丁**，无需改工作流文件。

### 1) 查可选模型

```http
GET /api/image-engine/model-info
→ {
  "checkpoints": ["modelA.safetensors", "modelB.safetensors", ...],
  "loras":       ["lora1.safetensors", ...],
  "samplers":    ["euler", "euler_ancestral", "dpmpp_2m", "ddim", ...],
  "schedulers":  ["normal", "karras", "simple", "exponential", ...]
}
```

ComfyUI 离线时返回空列表 + `error` 字段，不抛 500。

### 2) 生成请求里加 `sd_params`

仅在 `workflow_name == "sd_default_workflow"` 时有效：

```http
POST /api/image-engine/generate-stream
{
  "workflow_name":   "sd_default_workflow",
  "positive_prompt": "<英文 prompt>",
  "negative_prompt": "worst quality, low quality, ...",  // 共享给整批
  "width":           904, "height": 1600,
  "scene_id": "...", "frame_type": "start", "slot_index": 0,
  "sd_params": {
    "checkpoint":   "modelA.safetensors",
    "loras": [
      {"name": "lora_a.safetensors", "strength": 0.8},
      {"name": "lora_b.safetensors", "strength": 0.5}
      // 0..7 个；可空数组（不用 LoRA），可少于 7 个（剩余槽位后端 mode=4 bypass）
    ],
    "steps":        25,
    "cfg":          4.5,
    "sampler_name": "dpmpp_2m",
    "scheduler":    "karras"
  }
}
```

### 3) LoRA 链 bypass 机制

工作流固定 7 个 `LoraLoaderModelOnly` 链式连接（`ckpt → L10 → L11 → L13 → L12 → L14 → L15 → L16 → KSampler`）。后端补丁规则：

- 用户传 N 个 LoRA（N ≤ 7）→ 链头 N 个槽写 `widgets_values = [name, strength]` 且 `mode=0`
- 剩余 `7-N` 个槽设 `mode=4`（bypass），借 `_litegraph_to_api` 的链路穿透机制让 model 引用绕过这些节点
- LoRA 条目中 `name == "None"/"none"` 或 `strength == 0` 同样视为禁用 + bypass

**对智能体的意义**：调用方只传想用的 LoRA，不用关心"工作流到底有几个槽"。批量生成 30 个分镜的 SD 出图，`sd_params` 整批共用（不需要逐镜复制），后端确认是同一批补丁。

### 4) 批量端点同样接受 sd_params

```http
POST /api/image-engine/generate-batch-stream
{
  "workflow_name": "sd_default_workflow",
  "gen_count": 3,
  "negative_prompt": "...",
  "width": 904, "height": 1600,
  "frames": [{"scene_id":"s1","frame_type":"start","prompt":"..."}, ...],
  "project_id": "<pid>",
  "sd_params": { ... }   // 顶层，所有 frames 共用
}
```

### 5) 关键节点 ID

如需进一步自定义（如改用其它 t2i 工作流并复用 `patch_sd_workflow`），节点 ID 映射定义在 `backend/services/sd_workflow.py::SD_NODES`：

```python
{
  "checkpoint":  17,  # CheckpointLoaderSimple
  "positive":     2,  # CLIPTextEncode (正面)
  "negative":     3,  # CLIPTextEncode (负面)
  "ksampler":    20,  # KSampler
  "latent_size":  6,  # EmptyLatentImage
  "lora_chain": [10, 11, 13, 12, 14, 15, 16],  # 链头到链尾
}
```

## 失败处理

- ComfyUI 进程未起：`GET /test` 返回 success=false；继续调 `/generate-stream` 会得到 connection refused
- 工作流名不存在：返回 404 `工作流 '<name>' 未找到`
- ComfyUI 报模型/节点缺失：在 SSE 中作为 `error{message}` 事件传回，**该任务跳过，其他任务继续**
- VRAM 不足：批量并发应降低 `gen_count`；视频引擎有自动重试，图片引擎无
