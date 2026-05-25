# scripts/

LumiCreate-Pro 客户端示例。

## lumi.py
完整功能 CLI，依赖 `httpx`：
```bash
pip install httpx
python scripts/lumi.py health
python scripts/lumi.py projects list
python scripts/lumi.py manuscript generate --config-file my_cfg.json --save <project_id>
# 漫剧建卡：批量生成角色 role / traits / appearance（多镜出图角色一致性的前提）
python scripts/lumi.py characters auto-build <project_id> --names "林夏,张川,Boss"
# 漫剧首选：客户端"手动"分镜，每段 ≤ 50 字符 且 ≤ 1 个出镜角色（宁可多分）
python scripts/lumi.py scenes split-manual <project_id> --save --max-chars 50 --max-chars-per-scene 1
# 短剧/创作型可走 LLM 自动分镜
python scripts/lumi.py scenes generate <project_id> --save
# 出图前必跑：把每镜出镜角色 hydrate 成完整对象后调 generate-frame-prompts，回写 scenes
python scripts/lumi.py prompts frame-batch <project_id>
# 视频前推荐：生成视频 positive_prompt（聚焦运动/表情/镜头）
python scripts/lumi.py prompts video-batch <project_id>
# 出图：自动预检 frame_prompt 与角色 appearance 是否非空
python scripts/lumi.py images generate <project_id> --workflow lumicreate-基础 --gen-count 1 --save
# 漫剧/朗读模式：一键给所有分镜批量生成 Edge TTS 音频并按正确 key 保存
python scripts/lumi.py audio reading-all <project_id>
# 单段试听
python scripts/lumi.py audio ms-tts --text "测试朗读" --out out.mp3
python scripts/lumi.py video merge <project_id>
# 字幕：默认从 manuscript 原文走 preprocess-text 细切（逗号也断句）；--from-scenes 用旧路径
python scripts/lumi.py subtitle generate-srt <project_id> --fps 24 --model base
# 不传 --size 时自动按视频方向选字号：竖屏 10 / 横屏 16
python scripts/lumi.py subtitle embed <project_id> --font "等线 Bold"
```

> 漫剧默认音频参数：`voice=zh-CN-XiaoxiaoNeural`，`rate=+25%`（快）。
> 写入 key 固定为 `__ms_reading__{sceneId}`，否则前端音频页和视频页都看不到。

环境变量 `LUMI_API` 覆盖 base URL（默认 `http://127.0.0.1:18520`）。

## lumi.sh
Bash + curl + jq 轻量版，覆盖常用只读/简单写入接口。Windows 用户可在 Git Bash 中运行。

## end_to_end_example.py
完整流水线示例：从新建项目 → 文案 → 分镜 → 提示词 → 图片 → 音频 → 视频 → 合并 → 字幕。

最小可跑（reading 模式 + Edge TTS，无 GPU 也能跑前 4 步 + 第 7 步）：
```bash
python scripts/end_to_end_example.py --name MyDemo --dialogue-mode reading --rate "+25%"
```
默认就是 `--dialogue-mode reading --rate +25%`，无需显式指定。

完整跑通（需要 ComfyUI + IndexTTS + LTX-2.3 工作流）：
```bash
python scripts/end_to_end_example.py \
  --name FullPipeline \
  --dialogue-mode mixed \
  --voice-ref linxia.wav \
  --image-workflow lumicreate-基础 \
  --video-workflow flfa2i-lumicreate \
  --resolution 720x1280 \
  --fps 25
```
