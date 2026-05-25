# 角色卡片建立（智能体职责）

漫剧靠"角色卡片"保证图片中同一角色长得一致。流程是：
**智能体读文案 → 提取角色名 → 调 LumiCreate 接口生成 role/traits/appearance → 写入 characters.json → 分镜阶段自动检测出镜 → 图片提示词带 appearance 标签**

## 为什么必须做这件事

- `text-engine/generate-frame-prompts` 接收 `characters[]` 字段，里面的 `appearance`（英文标签）会**注入到 ComfyUI 工作流的 positive prompt**，让 SD/Flux 出图时锁定该角色的视觉特征
- 分镜的 `_scene_characters` 指定出镜角色名，前端 `_fetchFramePrompts()` 只传该名字对应的 appearance 给 LLM → 多镜串联时角色不漂移
- 文生图模型对多人物场景容易"角色融合 / 错位"，所以单镜出镜 ≤ 1 人（详见 [manual-scenes.md](./manual-scenes.md) 的角色感知拆分）

## 步骤 1：从文案提取角色名

LumiCreate 后端**没有"角色名抽取"端点**。这是智能体自己的任务（用宿主 LLM 读文案得到名字列表）。

策略：
- 文案的"主要角色"通常在前几段就出现，用专有名词
- 排除常见词、地名、物品名
- 也包括反复出现的代号（如"老板"、"小女孩"——若文案中没有真名，把代号当作角色名）

约束：
- 名字数量 ≤ 6（超过容易混淆）
- 名字必须能在 `manuscript` 中 substring 匹配命中（后续 substring-based 出镜检测依赖此）
- 若用户已经在 `manuscript.config.characters` 里给过角色，**优先使用用户的清单**（智能体不要凭空替换）

## 步骤 2：调 LumiCreate 端点生成角色卡

对每个角色名：

### 2.1 反推 role / traits（中文，定位 + 性格）
```http
POST /api/text-engine/generate-character-profile
{
  "name": "林夏",
  "manuscript": "<完整文案>",
  "existing_role": "",          // 用户已填的就传过来，LLM 会保留/增强
  "existing_traits": ""
}
→ { "role": "侦探", "traits": "冷静、寡言、习惯抽冷烟" }
```

### 2.2 生成 appearance（英文标签，禁止情绪/表情词）
```http
POST /api/text-engine/generate-character-appearance
{
  "name": "林夏",
  "role": "侦探",
  "traits": "冷静、寡言",
  "existing": ""
}
```
**流式 SSE**，事件 `{text:"..."}` 拼接得到完整字符串：
```
short black hair, sharp eyes, slim build, wearing dark trench coat, leather gloves, ...
```
关键规则（由后端 prompt 模板保证）：
- 必须**英文**输出
- **不能含情绪/表情词**（smile、sad、smirk、frown 等）——会污染多镜的表情多样性
- 每个标签是稳定视觉特征：发色发型 / 体型 / 穿着 / 配饰 / 显著特征

### 2.3 negative（可选）
后端无生成端点，需要时由智能体手动写入（如"no beard, no glasses"），用于 ComfyUI negative prompt。

## 步骤 3：写入项目

**双写**——`characters.json` 是角色管理页主源，`manuscript_config.json.characters` 是兼容前端"从文案导入角色"按钮：

```python
chars = [
  {"name":"林夏","role":"侦探","traits":"冷静、寡言","appearance":"...","negative":""},
  {"name":"张川","role":"嫌疑人","traits":"急躁、易怒","appearance":"...","negative":""},
]

# 写 characters.json
await api.put(f"/api/projects/{pid}/characters", {"characters": chars})

# 同步到 manuscript.config，便于以后用前端"从文案导入角色"复用
ms = await api.get(f"/api/projects/{pid}/manuscript")
cfg = ms.get("config", {}) or {}
cfg["characters"] = [
    {"name":c["name"],"role":c["role"],"traits":c["traits"]}
    for c in chars
]
await api.put(f"/api/projects/{pid}/manuscript",
              {"content": ms.get("content",""), "config": cfg})
```

## 步骤 4：分镜出镜角色自动检测

### 4.1 客户端 substring 检测（推荐 / 最快）
手动分镜时，对每镜 description 做 `name in description` 检测，把命中的填进 `_scene_characters`。
（这是 [manual-scenes.md](./manual-scenes.md) 角色感知拆分的副产品——切分过程中已经在跟踪 character set，直接复用即可）

### 4.2 LLM 检测（备用，能解析"他/她"代词）
```http
POST /api/text-engine/suggest-scene-characters
{
  "description": "<分镜文本>",
  "dialogues":   [...],
  "all_names":   ["林夏","张川","Boss"],
  "manuscript":  "<完整文案>"
}
→ { "characters": ["林夏"] }   // 只会包含 all_names 子集
```
比 substring 慢、但能处理"他点燃烟头"这种代词指代回前文。**漫剧批量场景不要每镜都调，太慢；保留给精修。**

## 步骤 5：图片提示词带 appearance

前端 `_fetchFramePrompts()` 只把 `_scene_characters` 命中的角色传给后端：

```python
selected = set(scene.get("_scene_characters") or [])
chars_for_prompt = [c for c in all_chars if c["name"] in selected]

await api.post("/api/text-engine/generate-frame-prompts", {
  "description":  scene["description"],
  "dialogues":    scene["dialogues"],
  "characters":   chars_for_prompt,   # ← 只传出镜角色，0 或 1 个
  "manuscript":   manuscript_text,
  "scene_index":  scene["index"],
  "total_scenes": len(scenes),
})
```

- 0 角色场景（纯环境/物件镜头）→ characters 传 `[]`，LLM 出风景/物件 prompt，**漫剧很需要这种镜头作"留白"**
- 1 角色场景 → LLM 把该角色的 appearance 标签拼到 positive prompt 主体里
- 2+ 角色场景 → 受限于本地文生图模型，应在分镜阶段就已被切分，**到这一步不应再出现**

## 智能体常见误用

- ❌ 仅依据"文案 config.characters"——若用户没填，跳过角色阶段直接出图 → 角色每镜样貌都飘
- ❌ 一次给 6 个名字都跑 appearance，每个 traits 都让 LLM 重新发明 → 风格不统一。**先一次性确定全部 name + role + traits**，再分别跑 appearance
- ❌ 把 `appearance` 写中文 → ComfyUI prompt 大多英文 backbone 处理中文很差
- ❌ 分镜出镜超过 1 人还往下走 → 必须回到分镜阶段拆分或人工删减
- ❌ 文案有"小张"、"老张"两个不同人物 → substring 检测会把"老张"误算两人都出现；这种情况要在角色提取阶段去歧义（合并/重命名）
