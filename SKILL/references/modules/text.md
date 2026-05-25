# text 模块（LLM 文本引擎）

驱动 LLM 完成所有文本生成任务：文案、分镜、首/尾帧提示词、视频提示词、角色描述、场景出镜角色建议。

后端通过 `services/llm.py:stream_chat` 路由到对应引擎（Ollama / OpenAI 兼容），统一返回字符串增量。

## 接口

| 方法 | 路径                                              | 流式 SSE | 用途                                                  |
|------|---------------------------------------------------|----------|-------------------------------------------------------|
| GET  | `/api/text-engine/test`                           | ✗        | 测试连接，返回 `{success, message, models[]}`          |
| POST | `/api/text-engine/generate-manuscript`            | ✓        | 文案生成（含改写）                                    |
| POST | `/api/text-engine/generate-scenes`                | ✗        | 分镜划分（reading 模式无 LLM）                        |
| POST | `/api/text-engine/generate-frame-prompts`         | ✗        | 单个分镜的首/尾帧英文 prompt                          |
| POST | `/api/text-engine/generate-character-appearance`  | ✓        | 单角色外观英文标签（流式）                            |
| POST | `/api/text-engine/generate-character-profile`     | ✗        | 由角色名 + 文案反推 role/traits                      |
| POST | `/api/text-engine/suggest-scene-characters`       | ✗        | 根据分镜描述/台词推荐出镜角色（仅返回 all_names 子集）|
| POST | `/api/text-engine/generate-video-prompt`          | ✓        | 单镜视频英文 prompt（强调镜头运动 + 角色对白）       |

## 关键请求 body

### generate-manuscript
```json
{
  "config": {
    "length": "short|medium|long",
    "audience": "...",
    "style": "...",
    "tone": "...",
    "theme": "...",
    "worldview": "...",
    "characters": [{"name":"...","role":"...","traits":"..."}],
    "dialogue_mode": "narration|dialogue|mixed|reading"
  },
  "existing_content": ""
}
```
- `length` → `LENGTH_DESC` 映射成中文描述并注入 prompt
- `existing_content` 非空时 LLM 会在其基础上扩写/改写
- `dialogue_mode` 注入约束（不同模式的台词比例）

### generate-scenes
```json
{
  "manuscript": "<完整文案>",
  "dialogue_mode": "mixed",
  "characters": [{"name":"...","role":"...","traits":"..."}]
}
```
返回 `{scenes:[...], total:N}`。
- reading 模式：服务端按句切分 (≤28s/段)，**不调用 LLM**
- 其它模式：LLM 输出 JSON 数组，后端用正则提取并修正 `id/index`

⚠️ **漫剧不要调本接口**：改用 [manual-scenes.md](../manual-scenes.md) 描述的客户端"手动分镜"算法（按句切分 + ≤ 50 字符 + ≤ 1 个出镜角色），分镜更碎、单段不会过长、不会混入多人物。

⚠️ **角色阶段是分镜的前置**：分镜前必须先建好 `characters.json`（[character-cards.md](../character-cards.md)），否则手动分镜的角色感知部分会失效。

### generate-frame-prompts
```json
{
  "description": "镜头描述",
  "dialogues": [{"character":"...","text":"..."}],
  "characters": [{"name":"...","role":"...","appearance":"...","traits":"..."}],
  "manuscript": "<完整文案>",
  "scene_index": 1,
  "total_scenes": 10
}
```
返回 `{start_frame_prompt, end_frame_prompt}`，均为英文，无画风词，无情绪/表情词。
**characters 列表里必须只放本镜出镜角色**，否则 LLM 会把其他人带入图。

### generate-video-prompt
```json
{
  "description": "...",
  "dialogues": [{"character":"...","text":"...","emotion":"..."}],
  "characters": [{"name":"...","role":"...","appearance":"...","traits":"..."}],
  "start_frame_prompt": "...",
  "end_frame_prompt": "...",
  "manuscript": "...",
  "scene_index": N,
  "total_scenes": M
}
```
流式返回 SSE `{text}`，最终拼成英文 prompt（描述镜头运动 + 角色开口对白）。

### generate-character-profile
```json
{
  "name": "林夏",
  "manuscript": "<完整文案>",
  "existing_role": "侦探",
  "existing_traits": "冷静"
}
```
返回 `{role, traits}`（中文）。

### generate-character-appearance
```json
{
  "name": "林夏",
  "role": "侦探",
  "traits": "冷静、寡言",
  "existing": ""
}
```
流式返回 SSE `{text}`，拼成英文标签字符串（不含情绪/表情）。

### suggest-scene-characters
```json
{
  "description": "...",
  "dialogues": [...],
  "all_names": ["林夏","张川","Boss"],
  "manuscript": "..."
}
```
返回 `{characters: ["林夏"]}`，**只会包含 all_names 中的合法名**。

## 错误恢复

- LLM 返回非 JSON 时，后端尝试用正则 `\[[\s\S]*\]` / `\{[\s\S]*\}` 提取；若仍失败：
  - `generate-scenes`: 返回 502 `LLM 未返回有效 JSON: ...`
  - `generate-frame-prompts`: 返回空字符串字段，让前端再试
- 流式接口在中途抛错时会发 `data: {"error":"..."}` 而非中断 SSE。

## 提示词模板位置

模板字符串在 `backend/services/prompts.py`，包含：
- `MANUSCRIPT_SYSTEM` / `MANUSCRIPT_USER_TEMPLATE`
- `SCENES_SYSTEM` / `SCENES_USER_TEMPLATE`
- `FRAME_PROMPT_SYSTEM` / `FRAME_PROMPT_USER_TEMPLATE`
- `VIDEO_PROMPT_SYSTEM` / `VIDEO_PROMPT_USER_TEMPLATE`
- `CHARACTER_APPEARANCE_SYSTEM` / `..._USER_TEMPLATE`
- `CHARACTER_PROFILE_SYSTEM` / `..._USER_TEMPLATE`
- `SUGGEST_CHARS_SYSTEM` / `..._USER_TEMPLATE`
- `LENGTH_DESC`, `DIALOGUE_MODE_DESC` 字典

如需调整生成风格，**直接编辑 prompts.py 重启 backend** 而不是在 client 端绕开。
