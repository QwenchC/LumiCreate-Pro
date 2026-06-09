# SFX Module (v1.4.8+)

漫剧叙事强烈依赖点状音效（脚步、关门、抽刀）。v1.4.8 在 BGM 通路之外
单独建一套 **SFX (Sound Effect) 通路**：

- **全局 SFX 库**：用户上传的短音效（≤ 几秒），元数据 SQLite + 文件 APPDATA/sfx/。空库出厂，不预置内容（避免版权）
- **项目级时间轴**：`<project>/sfx_timeline.json` —— 每镜次 N 个 `[offset_ms, sfx_id, volume_db]`
- **渲染集成**：`render-slideshow` 读时间轴，把 SFX 通过 ffmpeg `adelay + volume + amix` **烧进镜次 mp4**
- **不影响合并 / 字幕**：SFX 已经在镜次 mp4 里，merge-project-video / subtitle-engine/embed 不需要改

## API（前缀 `/api/sfx`）

| Method | Path                          | Auth | Note |
|--------|-------------------------------|------|------|
| GET    | `/categories`                  | ✗    | 已存在的分类去重列表 |
| GET    | `/list?category=&limit=`       | ✗    | SFX 库列表（自动过滤丢失/损坏文件） |
| POST   | `/upload`                       | ✗    | 上传 SFX，body: `{filename, name?, category?, tags?, data(b64)}`；返回新 clip |
| GET    | `/file/{sfx_id}`                | ✗    | 流式拉音频（试听用） |
| PUT    | `/clip/{sfx_id}`                | ✗    | 改 name/category/tags |
| DELETE | `/clip/{sfx_id}`                | ✗    | 204；文件 + DB 一并清 |
| GET    | `/timeline/{project_id}`        | ✗    | 项目时间轴 JSON `{timeline: {scene_id: [overlay...]}}` |
| PUT    | `/timeline/{project_id}`        | ✗    | 整体替换写入；volume_db ∈ [-40, 20]，offset_ms ≥ 0 |

## Upload（最小请求）

```http
POST /api/sfx/upload
Content-Type: application/json
{
  "filename": "door_close.mp3",
  "name":     "Door Close",        // 缺省取 filename 前缀
  "category": "ambient",           // 缺省 "uncategorized"
  "tags":     "door,interior",     // 自由文本
  "data":     "<base64 audio>"
}
→ 200 { "id": 7, "name":..., "url": "/api/sfx/file/7", "duration_ms": 850, ... }
```

允许扩展名：`.mp3 .m4a .wav .aac .ogg .flac`，其它直接 400。

## Timeline 数据结构

```json
{
  "scene_001": [
    { "sfx_id": 7,  "offset_ms": 1200, "volume_db": -8 },
    { "sfx_id": 12, "offset_ms": 3500, "volume_db": -6 }
  ],
  "scene_002": [
    { "sfx_id": 5,  "offset_ms": 0,    "volume_db": 0 }
  ]
}
```

- `offset_ms`：从该镜次起点起算的偏移
- `volume_db` 区间 `[-40, 20]`，0 为不动音量
- 引用已删除的 sfx_id 在渲染时**静默跳过**（不让整片崩）
- 时间轴写整体替换 —— 客户端要先 GET 再合并改动再 PUT，别只 PUT 一镜

## ffmpeg 渲染（slideshow per-scene cmd）

无 SFX 走原快路径（`-af aresample`）。有 SFX 时进入 filter_complex 分支：

```bash
ffmpeg -y \
  -loop 1 -framerate 25 -t 5.000 -i image.png \
  -i audio.mp3 \
  -i sfx_door.mp3 \
  -i sfx_steps.mp3 \
  -filter_complex "
    [0:v]<vf_chain>[vout];
    [1:a]aresample=async=1000:first_pts=0[a_main];
    [2:a]adelay=1200|1200,volume=-8.0dB[sfx0];
    [3:a]adelay=3500|3500,volume=-6.0dB[sfx1];
    [a_main][sfx0][sfx1]amix=inputs=3:duration=first:dropout_transition=0[aout]
  " \
  -map [vout] -map [aout] \
  <ENCODE_SAFE> \
  -c:a aac -b:a 192k -ar 48000 -ac 2 -t 5.000 \
  scene_X.mp4
```

关键点：
- **amix `duration=first`**：让总长 = 主音轨长度（不会被尾随的 SFX 拖长）
- **adelay 用 `ms|ms` 双声道格式**（stereo amix 必须两个通道都给）
- SFX 编码同主音轨 → AAC 48k 立体声，与 merge/burn 全链对齐

## 实操推荐

- 漫剧用户先在 SFX 编辑器里上传一批常用音效（关门 / 脚步 / 衣物摩擦 / 风声 / 心跳），分类管理
- 时间点对齐：常用 ffprobe 看音频波形或在试播时反复听判断 offset_ms
- 音量：环境音效 -8 ~ -12dB；强烈动作（关门、抽刀）-4 ~ -6dB；不要超过 0dB（容易爆音）

## ⚠️ 适用范围

- **目前只在 slideshow (`render-slideshow`) 通路烧 SFX**，LTX 视频不接 SFX
- 改了时间轴后**必须重新跑 `render-slideshow`** 才能在镜次 mp4 里听到效果
- 合并阶段（`merge-project-video`）和字幕烧录都不会重新处理 SFX —— SFX 已经在每镜次 mp4 里
- LTX 用户想要 SFX 可以：先生成 LTX 视频 → 后期用 video clipper 类工具叠加；或用 BGM 通路放一首"环境音"

## 回归测试

`backend/tests/test_slideshow_video.py::test_sfx_overlay_*`：cmd 构造正确性 + 缺失 sfx_id 不崩
`backend/tests/test_sfx_engine.py`：API 端到端（上传 / 时间轴 / 校验）
