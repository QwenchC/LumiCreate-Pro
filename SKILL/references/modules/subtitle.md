# subtitle 模块（字幕生成与烧录）

基于 stable-whisper 的词级对齐流水线，输出 SRT 后烧入视频。

## 接口

| 方法 | 路径                                       | 流式 | 用途                                                       |
|------|--------------------------------------------|------|------------------------------------------------------------|
| GET  | `/api/subtitle-engine/status/{project_id}` | ✗    | 查产物存在性                                               |
| GET  | `/api/subtitle-engine/script/{project_id}` | ✗    | 从分镜 dialogues/description 抽脚本（**漫剧不推荐：粒度过粗**） |
| POST | `/api/subtitle-engine/preprocess-text`     | ✗    | **字幕标准首步**：按 `，。？！：""——…` 与空白断行          |
| POST | `/api/subtitle-engine/generate-srt`        | ✓    | 完整生成 SRT 流水线                                        |
| POST | `/api/subtitle-engine/embed`               | ✓    | SRT 烧入视频                                               |

## 前置条件

- `<project>/video/final_video.mp4` 已存在（通过 `video merge-project-video` 产出）
- ffmpeg + ffprobe 可定位
- 首次调 generate-srt 会下载 Whisper 模型（base ~150MB）

## status 返回

```json
{
  "has_final_video": true,
  "has_fixed_cfr":   true,
  "has_srt":         true,
  "has_embedded":    false,
  "srt_path":        ".../video/subtitles.srt",
  "embedded_path":   ""
}
```

`fixed_cfr.mp4` 是字幕生成时帧率标准化（CFR）的中间产物，`embed` 会优先用它。

## script（不推荐用于漫剧）

```json
GET /api/subtitle-engine/script/{project_id}
→ { "lines": ["<scene_001 整段>", "<scene_002 整段>", ...], "count": 23 }
```

抽取规则：优先 `scenes[*].dialogues[*].text`；本镜无台词则用 `scenes[*].description`。

⚠️ 漫剧 reading 模式下，每个分镜的 dialogues 是**整段未切的长文本**（手动分镜的产物），直接拿来当 lines 会出现"单条字幕几十字、屏幕一行装不下"的情况。**漫剧应改走 preprocess-text 路径**（下一节）。

## preprocess-text（字幕标准首步）

后端 [services/subtitle.py:18](../../../backend/services/subtitle.py#L18) `preprocess_text()`：

```python
# 替换断句符号和空白为换行 → 反复折叠连续换行
text = re.sub(r'[，。？！：""——…]+|\s+', '\n', text)
```

吃下的断句符号集合：
- `，` 中文逗号
- `。` 中文句号
- `？` 全角问号
- `！` 全角感叹号
- `：` 全角冒号
- `""` 中文双引号（U+201C / U+201D）
- `——` 破折号
- `…` 省略号
- 任意空白（空格 / Tab / 换行）

即比 [手动分镜](../manual-scenes.md) 的 `_splitSentences`（只切 `。！？\n`）**更碎**——逗号也是断句点，这样每条字幕都很短，符合视频字幕的阅读节奏。

```http
POST /api/subtitle-engine/preprocess-text
{"text":"她回头，看见月光下的剑。"}
→ {
    "text": "她回头\n看见月光下的剑",
    "lines": ["她回头", "看见月光下的剑"],
    "count": 2
}
```

### 推荐流程（漫剧/朗读视频）

```python
ms_text = (await api.get(f"/api/projects/{pid}/manuscript"))["content"]
r = await api.post("/api/subtitle-engine/preprocess-text", {"text": ms_text})
lines = r["lines"]                          # 已经去空、去重换行的细碎字幕
# 直接喂给 generate-srt：
await api.sse("/api/subtitle-engine/generate-srt", {
    "project_id": pid, "lines": lines, "fps": 24,
    "manual_advance": 0.0, "model_name": "base",
})
```

**为什么用 manuscript 而不是 script**：
- manuscript 是用户/智能体写的原稿（reading 模式下也是音频的最终来源）
- script 是从分镜聚合，漫剧分镜每段已经合并几句话，再切就经过两次损耗
- preprocess-text 直接读原文按逗号断句，得到的 lines 数量约等于"原文逗号数 + 句号数"，与音频朗读节奏自然吻合，stable-whisper 词级对齐能稳稳对上时间戳

## generate-srt 请求

```json
{
  "project_id": "...",
  "lines":      ["第一句","第二句",...],
  "fps":        24,           // 24|25|30
  "manual_advance": 0.0,      // 整体偏移秒
  "model_name": "base"        // base|small|medium
}
```

SSE 步骤（每步含 `step`/`message`/`pct?`）：

1. **`normalize_fps`** — ffmpeg 转 `fixed_cfr.mp4`（CFR，匹配 fps）
2. **`extract_audio`** — ffmpeg 提取 16k 单声道 wav
3. **`load_model`** — 加载 whisper
4. **`align`** — whisper 词级对齐到 lines（含 pct）
5. **`cut`** — 按 lines 切分时间戳
6. **`write_srt`** — 写 `<project>/video/subtitles.srt`
7. **`done`** 或 **`error`**

末尾 `data: [DONE]`。

## embed 请求

```json
{
  "project_id": "...",
  "font_name":  "等线 Bold",     // 等线 Bold|微软雅黑|黑体|宋体|仿宋|楷体
  "font_size":  10               // ⚠️ 按视频方向自适应，见下表
}
```

**字号默认（不要照搬前端的 18）**：

| 分辨率              | 方向 | `font_size` |
|---------------------|------|-------------|
| `720x1280`（漫剧默认）| 竖屏 | **10**      |
| `1280x720`          | 横屏 | **16**      |
| 其它 `WxH`          | `W<H` 竖屏 → 10；`W>H` 横屏 → 16 | — |

调用前先读 `GET /api/settings` 的 `video_engine.resolution`（用户上次生成视频时的设置）或 `GET /api/projects/{id}` 推断；漫剧不指定时默认竖屏 10。

后端：
- 优先用 `fixed_cfr.mp4` 作为源（时间轴与 SRT 严格匹配）
- 中文字体名 → libass 英文名映射（如 黑体 → SimHei；含 Bold 字段时附 `Bold=1`）
- 输出 `<project>/video/final_video_subbed.mp4`

SSE：`{step:"embedding",pct:0~100}` → `done` 或 `error`，最后 `[DONE]`。

烧录耗时上限 600 秒，超时报 `嵌入超时`。

## 实操建议

- 默认路径 + 默认字体 + base 模型对 5 分钟内的视频效果最佳
- 长视频或方言可改 `model_name: "small"` / `"medium"`，耗时和显存随之增加
- 用户改 `manual_advance` 一般 ±0.2~0.5 秒之间调整唇形对位
- 烧录是不可逆的（覆盖 `final_video_subbed.mp4`），**确认后再执行**
- **漫剧字幕：字号 10，竖屏不要更大**——前端默认 18 是横屏经验值，竖屏会盖住画面
