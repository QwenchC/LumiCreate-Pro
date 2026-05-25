# 手动分镜（智能体"手动"等价）

LumiCreate 分镜设计页有两个按钮：

- **✨ 从文案自动生成分镜** → 调 `POST /api/text-engine/generate-scenes`（reading 模式走服务端 28s 切句，其它模式走 LLM）
- **✂ 从文案手动生成分镜** → 前端纯本地切句 + 用户点选每个分镜的范围

**漫剧 / 朗读视频默认走"手动分镜"路径**——智能体以编程方式"代替用户点选"，宁可多分，避免单个分镜过长。

## 前端原版算法（[ScenesTab.vue:417,486](../../renderer/src/components/tabs/ScenesTab.vue#L417)）

```js
function _splitSentences(text) {
  const result = []
  let buf = ''
  for (const ch of text) {
    buf += ch
    if ('。！？'.includes(ch) || ch === '\n') {
      const t = buf.replace(/\n/g, '').trim()
      if (t) result.push(t)
      buf = ''
    }
  }
  if (buf.trim()) result.push(buf.trim())
  return result
}

// 用户点击决定每个分镜的句子范围 [startIdx, endIdx]
// 拼接 sentences[startIdx..endIdx] 作为该分镜 description
```

每个分镜生成的对象：
```js
{
  id: `scene_${(i+1).padStart(3,'0')}_manual`,   // ⚠️ 后缀必须是 _manual
  index: i + 1,
  description: <拼接后的文本>,
  duration_estimate: Math.max(4, Math.round(text.length / 5)),  // ≈ 5 字符/秒
  start_frame_prompt: '',
  end_frame_prompt: '',
  _scene_characters: [],
  dialogues: [
    // reading 模式：单条整段，character 为空字符串（不是"旁白"）
    { character: '', text: <整段>, emotion: '平静' }
    // 其它模式：从「」“”'' 引号对里抽对白
  ]
}
```

## 智能体"手动"分镜的合并策略

**目标**：宁可多分，每段 ≤ 12-15 秒，**且每段出镜角色数 ≤ 1**。

**算法**：
1. 用上面相同的 `_splitSentences()` 切句
2. 准备**角色名集合** `known_names`（来自 `characters.json` 或 `manuscript.config.characters`）
3. 顺序遍历句子，维护当前分镜累积的**字符数**与**出镜角色集合 `cur_chars`**
4. 对每个新句子：
   - 计算该句出镜：`sent_chars = {n for n in known_names if n in sentence}`
   - 若 `cur` 非空，且任一条件成立 → **强制切镜**：
     a. `cur_len + len(sentence) > max_chars`（字符上限）
     b. `|cur_chars ∪ sent_chars| > max_characters_per_scene`（角色上限，默认 1）
   - 否则把句子并入当前分镜
5. `max_chars` 默认 **50**；`max_characters_per_scene` 默认 **1**
   - 用户要求"更碎" → `max_chars` 30~40
   - 用户要求"稍长" → `max_chars` 60~80（上限 112）
   - 双人对话型漫剧可放宽 `max_characters_per_scene=2`，但出图质量会下降
6. 单句本身就超长或自带 2+ 角色时 **不再切**——整句作为一个分镜（保证语义完整），警告但不阻止
7. 切完后 `_scene_characters` 直接由切分过程产出（命中的 ≤1 个名字），**不必再调 `suggest-scene-characters`**

**与"自动生成分镜" (`generate-scenes`) 的区别**：

| 项目                  | 自动（LLM）         | 手动（智能体）       |
|-----------------------|---------------------|----------------------|
| 是否调用 LLM          | 是                  | 否（纯文本切句）     |
| 分镜数量              | LLM 决定（常偏少）   | 算法保证不过长       |
| 描述内容              | LLM 改写/概括       | **原文逐句拼接**     |
| dialogues             | LLM 拆角色台词      | reading 整段；其它抽引号 |
| scene_id 后缀         | 无                  | `_manual`            |
| 适用                  | 短剧 / 创作型       | **漫剧 / 朗读 / 解说** |

## Python 参考实现

```python
import re

SENT_TERMINATORS = "。！？"

def split_sentences(text: str) -> list[str]:
    """与前端 _splitSentences 行为一致：按句末标点 + 换行切分，保留标点。"""
    out, buf = [], []
    for ch in text:
        buf.append(ch)
        if ch in SENT_TERMINATORS or ch == "\n":
            seg = "".join(buf).replace("\n", "").strip()
            if seg:
                out.append(seg)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def extract_dialogues(text: str, dialogue_mode: str) -> list[dict]:
    """与前端 _extractDialogues 行为一致。"""
    if dialogue_mode == "reading":
        return [{"character": "", "text": text.strip(), "emotion": "平静"}]
    dlgs = []
    for m in re.finditer(r"[「“‘](.*?)[」”’]", text, re.DOTALL):
        t = m.group(1).strip()
        if t:
            dlgs.append({"character": "", "text": t, "emotion": "平静"})
    return dlgs


def manual_split(
    manuscript: str,
    dialogue_mode: str = "reading",
    max_chars: int = 50,
    known_names: list[str] | None = None,
    max_characters_per_scene: int = 1,
) -> list[dict]:
    """
    宁可多分的"手动"分镜：按句切分，每分镜累积字符 ≤ max_chars，
    且出镜角色数 ≤ max_characters_per_scene。
    切分过程中直接产出 _scene_characters，避免之后再调 suggest-scene-characters。
    """
    sentences = split_sentences(manuscript)
    names = list(known_names or [])

    def chars_in(sent: str) -> set[str]:
        return {n for n in names if n and n in sent}

    groups: list[tuple[list[str], set[str]]] = []
    cur: list[str] = []
    cur_len = 0
    cur_chars: set[str] = set()

    for s in sentences:
        slen = len(s)
        sent_chars = chars_in(s)
        merged_chars = cur_chars | sent_chars
        force_cut = bool(cur) and (
            cur_len + slen > max_chars
            or len(merged_chars) > max_characters_per_scene
        )
        if force_cut:
            groups.append((cur, cur_chars))
            cur, cur_len, cur_chars = [s], slen, sent_chars
        else:
            cur.append(s); cur_len += slen; cur_chars = merged_chars
    if cur:
        groups.append((cur, cur_chars))

    scenes = []
    for i, (g, char_set) in enumerate(groups):
        text = "".join(g)
        scenes.append({
            "id": f"scene_{i+1:03d}_manual",
            "index": i + 1,
            "description": text,
            "duration_estimate": max(4, round(len(text) / 5)),
            "start_frame_prompt": "",
            "end_frame_prompt": "",
            # 命中的角色（≤ max_characters_per_scene），顺序按 known_names 给定顺序
            "_scene_characters": [n for n in names if n in char_set],
            "dialogues": extract_dialogues(text, dialogue_mode),
        })
    return scenes
```

调用与保存：
```python
data = await api.get(f"/api/projects/{pid}/manuscript")
manuscript = data["content"]
mode = data.get("config", {}).get("dialogue_mode", "reading")

chars_data = await api.get(f"/api/projects/{pid}/characters")
known_names = [c["name"] for c in chars_data.get("characters", [])]

scenes = manual_split(
    manuscript,
    dialogue_mode=mode,
    max_chars=50,
    known_names=known_names,
    max_characters_per_scene=1,
)
await api.put(f"/api/projects/{pid}/scenes", {"scenes": scenes})
```

**顺序约束**：必须先做完角色卡（[character-cards.md](./character-cards.md)）再做手动分镜，否则 `known_names=[]`，无法按角色拆分，回退成纯字数切分。

## 何时改 max_chars

- 默认 **50**（≈ 12.5 秒）足以避免大多数漫剧"分镜过长"问题
- 文案标点很密、句子普遍 < 20 字 → 可以放宽到 70~80，否则分镜数量爆炸
- 文案是长段独白、句子普遍 50+ 字 → 维持 50，单句作为独立分镜
- **永远不要超过 112**——超过后等同于服务端 reading 切句上限，不如直接调 `generate-scenes`
