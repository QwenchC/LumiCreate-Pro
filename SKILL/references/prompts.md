# 提示词链路（frame prompt / video prompt）

角色 `appearance` 怎样进到最终图片/视频里？SKILL 调用方最容易踩坑的就是这一段。

## 整体链路

```
characters.json[*].appearance          (英文标签字符串)
        │
        ▼
scenes[i]._scene_characters: ["林夏"]   (只有名字，没有 appearance)
        │  ◀── ⚠️ 客户端必须 hydrate：用名字到 characters.json 取完整对象
        ▼
text-engine/generate-frame-prompts
   body.characters = [{name,role,appearance,traits}]    ◀── 完整对象
        │
        ▼
scenes[i].start_frame_prompt / end_frame_prompt        (英文，含 appearance 标签)
        │
        ▼
image-engine/generate-batch-stream  → ComfyUI positive_prompt
        │
        ▼
images/{scene}_{frame}_{slot}.png                       ← 角色视觉锁定来自这里
        │
        ▼
video-engine/generate-stream
   scene.start_image_b64 / end_image_b64                ← 视频角色一致性源于首末帧
   scene.positive_prompt = <video prompt>               ← 描述运动，不重复 appearance
```

## 角色错位 / 动作互换 / 首末帧角色相同 的处理

### 后端 prompt 模板（FRAME_PROMPT_SYSTEM）做了哪些保证

[prompts.py:187](../../backend/services/prompts.py#L187) 的 system rule 关键约束：

| Rule              | 作用                                                                                       |
|-------------------|--------------------------------------------------------------------------------------------|
| **SEQUENTIAL FRAMING** | start frame 与 end frame 是**同一场景的两个不同瞬间**。一个角色不一定同时出现在两帧。LLM 会按描述的叙事顺序自行判断"A 走进来 → B 回答"这类场景，把 A 放进 start、B 放进 end |
| **APPEARANCE ISOLATION** | 每个角色的外观标签（发型/衣着/配饰）严格归属，不会被借给别的角色                       |
| **ACTION ISOLATION** | 每个角色的动作 / 姿势 / 位置 / 表情严格归属。**当 2 个角色同帧时禁止使用代词**，必须用 `Alice raises sword on the left, Bob recoils on the right` 这种命名 + 动作显式绑定 |
| **LOCAL MODEL LIMITATION** | 每帧角色数硬上限 2；列了 3 个就拆开放到 start/end                                  |

### 客户端这边能做的"分流"

后端 LLM 已经会自己判断首末帧角色，但客户端可以再往前一步——**直接告诉模板"哪段台词属于哪一帧"**：

- `dialogues` 顺序非常关键：前几条 → start 帧素材，后几条 → end 帧素材。手动分镜或编辑分镜时**保持原文顺序**。
- reading 模式 `dialogues[i].character` 为空 → 后端会显示成 `[Narration]: 整段文本`，让 LLM 知道这是旁白而非对话。**不要把 `character` 填成 `"旁白"` / `"narrator"`**——后端约定空字符串才是旁白。
- 同帧 2 角色容易出错时，更好的解决办法是回到分镜阶段，把这一镜按"先 A 后 B"再切成 2 镜（max_chars_per_scene=1 + 多分），完全规避同帧多角色问题。

## 角色 appearance 注入到 frame prompt 的实际位置

后端 [text_engine.py:303-364](../../backend/routers/text_engine.py#L303) 和 [prompts.py:187-214](../../backend/services/prompts.py#L187) 的实现：

```python
# generate-frame-prompts 收到 characters=[{name,role,appearance,traits},...] 后构造：
for c in characters:
    visual = c.get("appearance") or c.get("traits") or ""
    char_parts.append(f"  - {name} ({role}): {visual}")
char_block = (
    "Characters in this scene (ONLY these characters exist in this frame — do not add any others):\n"
    + "\n".join(char_parts) + "\n\n"
)
# 然后塞进 FRAME_PROMPT_USER_TEMPLATE，由 LLM 转成 positive_prompt
```

**关键**：`appearance` 为空字符串时，`visual` 会 fallback 到 `traits`（中文性格描述）。`traits` 不是视觉标签，给到 ComfyUI 等同于没角色锁定。

## ⚠️ 客户端最容易犯的 4 类错

| 错误                                                    | 表现                              | 修复                                              |
|---------------------------------------------------------|-----------------------------------|---------------------------------------------------|
| 1. 完全没调 `generate-frame-prompts`                    | scenes[i].start_frame_prompt 为空 | 出图前必须批量跑 prompts                          |
| 2. 调了但 `characters` 字段传空数组 `[]`                | 生成的 prompt 没有角色视觉描述    | 调用前 hydrate `_scene_characters` 到完整对象     |
| 3. `appearance` 字段是空字符串（建卡阶段流式累加丢了）  | char_block 退化为 traits（中文）  | 跑完 build 后**必须 assert 每个角色 appearance 非空** |
| 4. 调完没把 prompt 回写 scenes 再 PUT                   | 下一次进入读到的还是空 prompt     | 调用流程必须以 `PUT /scenes` 收尾                 |

## 正确的批量实现

```python
# 1) 取齐数据
project_chars = (await api.get(f"/api/projects/{pid}/characters"))["characters"]
chars_by_name = {c["name"]: c for c in project_chars}
scenes = (await api.get(f"/api/projects/{pid}/scenes"))["scenes"]
ms_text = (await api.get(f"/api/projects/{pid}/manuscript"))["content"]

# 2) 校验 appearance 非空（每个角色至少要有几十字的英文标签）
for c in project_chars:
    if not c.get("appearance", "").strip():
        raise RuntimeError(
            f"角色 {c['name']} 的 appearance 为空 —— 先跑 characters auto-build"
        )

# 3) 对每镜调 generate-frame-prompts，hydrate 出镜角色
for i, s in enumerate(scenes):
    selected = set(s.get("_scene_characters") or [])
    scene_chars = [chars_by_name[n] for n in selected if n in chars_by_name]
    r = await api.post("/api/text-engine/generate-frame-prompts", {
        "description":  s["description"],
        "dialogues":    s.get("dialogues", []),
        "characters":   scene_chars,        # ◀── 完整对象，包含 appearance
        "manuscript":   ms_text,
        "scene_index":  i + 1,
        "total_scenes": len(scenes),
    })
    s["start_frame_prompt"] = r.get("start_frame_prompt", "")
    s["end_frame_prompt"]   = r.get("end_frame_prompt", "")

# 4) 回写 scenes（必须！）
await api.put(f"/api/projects/{pid}/scenes", {"scenes": scenes})
```

## Video prompt 的特殊性

`generate-video-prompt` 同样接收 `characters[]`，但 system 提示词明确：
> Do NOT invent or repeat appearance tags — just name characters and describe their actions and expressions.

也就是说：
- 视频 prompt **不应该重复 appearance 标签**——这些标签已经在首末帧图片里"固化"，LTX 模型会按首末帧推断中间帧的角色样貌
- 视频 prompt 关注 **动作 / 表情变化 / 镜头运动 / 氛围**
- **但仍然必须传 `characters[]`**——LLM 要知道"哪些名字属于角色，不能凭空引入旁人"

视频 prompt 的批量调用：
```python
for i, s in enumerate(scenes):
    selected = set(s.get("_scene_characters") or [])
    scene_chars = [chars_by_name[n] for n in selected if n in chars_by_name]
    parts = []
    async for evt in api.sse("/api/text-engine/generate-video-prompt", {
        "description":        s["description"],
        "dialogues":          s.get("dialogues", []),
        "characters":         scene_chars,
        "start_frame_prompt": s["start_frame_prompt"],
        "end_frame_prompt":   s["end_frame_prompt"],
        "manuscript":         ms_text,
        "scene_index":        i + 1,
        "total_scenes":       len(scenes),
    }):
        if "text" in evt:
            parts.append(evt["text"])
    video_prompts[s["id"]] = "".join(parts).strip()

await api.put(f"/api/projects/{pid}/video-prompts", video_prompts)
```

video-prompts 持久化到 `video_prompts.json`，video-engine 调用时把它作为 `scenes[].positive_prompt` 传入。

## 出图前 sanity check

任何调 `image-engine/generate-batch-stream` 之前必跑：

```python
scenes = (await api.get(f"/api/projects/{pid}/scenes"))["scenes"]
bad = [s["id"] for s in scenes
       if not s.get("start_frame_prompt") or not s.get("end_frame_prompt")]
if bad:
    raise RuntimeError(
        f"以下分镜 frame prompt 为空，先跑 prompts batch：{bad}"
    )
```

否则 ComfyUI 会用空 positive_prompt 出图（基本是随机图），表现就是"图片和目标完全不符"。

## 漫剧典型病灶 → 解决路径速查

| 表现                                  | 诊断步骤                                                                 |
|---------------------------------------|--------------------------------------------------------------------------|
| 图片完全不像角色                       | `GET characters` → 查 appearance 是否为空 → 空就重跑 `characters auto-build` |
| 不同分镜角色样貌飘                     | `GET scenes` → 查 `_scene_characters` 是否填了 → 没填就重跑 `scenes split-manual` |
| frame_prompt 里没有角色英文标签        | 客户端调 `generate-frame-prompts` 时没 hydrate；用本文 §"正确的批量实现"  |
| 视频里角色对，但表情/动作完全不对劲    | `GET video-prompts` 是否生成；视频 prompt 没生成 = positive_prompt 退回 frame prompt（静态描述），LTX 无运动指令 |
| 一镜里出现了别的角色                    | 分镜 `_scene_characters` 数量 > 1，或 LLM 推断错；提高 `max_characters_per_scene` 限制，或手工编辑 scenes |
