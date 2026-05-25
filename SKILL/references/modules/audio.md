# audio 模块（语音合成）

三种音频路径：IndexTTS-2.0、GPT-SoVITS、Microsoft Edge TTS。前两者通过 `settings.audio_engine.engine_type` 选择，Edge TTS 通过专门接口调用，**仅在朗读模式使用**。

## 接口总览

| 方法 | 路径                                      | 流式 | 用途                                         |
|------|-------------------------------------------|------|----------------------------------------------|
| GET  | `/api/audio-engine/test`                  | ✗    | 探活当前 engine_type                          |
| GET  | `/api/audio-engine/voice-refs`            | ✗    | 列出音色参考文件                              |
| GET  | `/api/audio-engine/emotion-refs`          | ✗    | 列出情感参考文件                              |
| POST | `/api/audio-engine/generate-stream`       | ✓    | 单段 IndexTTS/GPT-SoVITS 生成                |
| POST | `/api/audio-engine/generate-batch-stream` | ✓    | 多段并发 IndexTTS/GPT-SoVITS                  |
| POST | `/api/audio-engine/stitch-scene`          | ✗    | 拼接同场景多段 WAV（含前后静音）              |
| POST | `/api/audio-engine/ms-tts`                | ✗    | Microsoft Edge TTS（朗读模式专用）            |

## IndexTTS / GPT-SoVITS（普通模式）

### 单段
```json
{
  "text": "<台词>",
  "voice_ref": "linxia.wav",       // 相对 voice_ref_dir 或绝对路径
  "emo_ref": "emo_sad.wav",        // 可选
  "emo_weight": 0.8,
  "lang": "zh",
  "speaker": null,                  // GPT-SoVITS 用
  "speed": 1.0,
  "scene_id": "scene_001",
  "dialogue_id": "d0",
  "slot_index": 0
}
```
SSE：`queued|progress|completed{data:<b64 wav>, mime:"audio/wav", id?}|error|[DONE]`

⚠️ `completed` 的 base64 字段是 **`data`**，不是 `audio`。客户端：`b64 = evt["data"]`。

### 批量
```json
{
  "gen_count": 1,
  "speed": 1.0,
  "dialogues": [
    {"scene_id":"scene_001","dialogue_id":"d0","text":"...",
     "voice_ref":"linxia.wav","emo_ref":"emo_sad.wav","emo_weight":0.8},
    ...
  ]
}
```
事件多路复用，结束 `batch_done{total}` + `[DONE]`。

### 音色 / 情感参考解析
- `voice_ref` 相对路径 → `voice_ref_dir + voice_ref`
- 缺省 → 用 `default_voice_ref`
- 都缺 → 报错 `未配置音色参考音频`

## Microsoft Edge TTS（朗读模式专用）

```json
{
  "text": "<整段分镜文本>",
  "voice": "zh-CN-XiaoxiaoNeural",
  "rate": "+25%"
}
```
返回 `{data:<b64 mp3>,duration_ms,format:"mp3"}`。

**漫剧默认参数**：`voice="zh-CN-XiaoxiaoNeural"`、`rate="+25%"`（快）。
SKILL 调用时若用户未明确指定，按此默认。

**特性**：
- 无需 API key、无需 GPU、不依赖 ComfyUI / IndexTTS
- 速度极快（秒级），适合朗读模式批量
- 中文神经语音清单见 `dialogue-modes.md`

## 场景拼接（IndexTTS 模式必做）

```json
{
  "clips": [
    {"data":"<b64 wav>","pre_silence_ms":0,"post_silence_ms":300},
    {"data":"<b64 wav>","pre_silence_ms":200,"post_silence_ms":300}
  ]
}
→ {"data":"<b64 wav>","duration_ms":N}
```

- 所有 clip 必须是 WAV 且参数（通道/采样位深/采样率）一致——以第一段为准
- 空 clips 列表返回 100ms 静音
- 拼接后的 WAV 作为视频引擎 `audio_b64`

## 持久化范例（前端硬编码的 key，必须严格匹配）

### reading 模式（Edge TTS）
**唯一允许的 key 是 `__ms_reading__{sceneId}`**：
```json
{
  "__ms_reading__scene_001": {"data":"<base64 mp3>","duration_ms":24500},
  "__ms_reading__scene_002": {"data":"<base64 mp3>","duration_ms":18200}
}
```

写入 `"scene_001": {...}` 不会报错，但：
- 前端"音频生成"页打不开音频预览
- 前端"视频生成"页拿不到 `__stitched__scene_001` 因为无映射来源

### 普通模式（IndexTTS / GPT-SoVITS）
**每段单独存为 `{sceneId}:{dialogueIdx}`，场景拼接结果存为 `__stitched__{sceneId}`**：
```json
{
  "scene_001:0": {
    "voiceRef":"linxia.wav","emoRef":null,
    "emoMethod":"与音色参考音频相同","emoWeight":0.8,
    "selectedSlot":0,
    "slots":[{"data":"<b64 wav>","duration":"4.3s"}]
  },
  "scene_001:1": { /* 同上 */ },
  "__stitched__scene_001": {"data":"<base64 wav>","duration_ms":18420}
}
```

| 模式      | 单段 key                       | 场景汇总 key（视频引擎据此取） |
|-----------|--------------------------------|--------------------------------|
| reading   | —                              | `__ms_reading__{sceneId}`      |
| 其它模式  | `{sceneId}:{dialogueIdx}`      | `__stitched__{sceneId}`        |

后端 `PUT /api/projects/{id}/audio` 仅根据 `v.data` 或 `v.slots[*].data` 有值来计 `progress.audio`——所以错 key 也会被计入进度（这是 bug 表现：进度满了但 UI 没图）。**永远使用上表的正确 key**。

## 失败处理

- `engine_type == manual` 时 generate-* 全部返回错误事件 `manual 模式不支持自动生成`
- IndexTTS 7860 端口未启动：探活返回 success=false，且 generate 会卡到超时；先告知用户启动 IndexTTS
- Edge TTS 无网络：抛 HTTPException 500，错误描述包含 `edge-tts` 字样
- 拼接：若任一 clip 不是合法 WAV 会抛 `wave.Error`

## 静音控制建议

`pre_silence_ms` / `post_silence_ms` 来源于分镜 `dialogues[i].pause_before/pause_after`（秒），客户端调用 `stitch-scene` 时换算成毫秒。

旁白与角色对话之间通常 300~500ms 静音。
