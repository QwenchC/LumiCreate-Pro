#!/usr/bin/env python3
"""
end_to_end_example.py — 用 lumi.py 的客户端能力组合出"零到带字幕成片"的最小流水线

这是一个**示例**，演示从空项目到合成视频 + 烧字幕的全部 API 调用顺序。
跑通需要：后端 + ComfyUI + IndexTTS（或 reading 模式 + edge-tts）+ ffmpeg。

用法：
  python end_to_end_example.py --name "Demo" --dialogue-mode reading
  python end_to_end_example.py --name "Demo" --dialogue-mode mixed  # 需要 IndexTTS + 音色参考
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

LUMI_API = os.environ.get("LUMI_API", "http://127.0.0.1:18520")


# ── Manual scene split (与前端 ScenesTab 的"✂ 从文案手动生成分镜"等价) ────────

_SENT_TERMS = "。！？"

def _split_sentences(text: str) -> list[str]:
    out, buf = [], []
    for ch in text:
        buf.append(ch)
        if ch in _SENT_TERMS or ch == "\n":
            seg = "".join(buf).replace("\n", "").strip()
            if seg:
                out.append(seg)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _extract_dialogues(text: str, dialogue_mode: str) -> list[dict]:
    if dialogue_mode == "reading":
        return [{"character": "", "text": text.strip(), "emotion": "平静"}]
    dlgs = []
    for m in re.finditer(r"[「“‘](.*?)[」”’]", text, re.DOTALL):
        t = m.group(1).strip()
        if t:
            dlgs.append({"character": "", "text": t, "emotion": "平静"})
    return dlgs


def manual_split(manuscript: str, dialogue_mode: str, max_chars: int,
                  known_names: list[str] | None = None,
                  max_characters_per_scene: int = 1) -> list[dict]:
    """智能体"手动"分镜：单段 ≤ max_chars 字符 且 出镜角色数 ≤ max_characters_per_scene。"""
    sentences = _split_sentences(manuscript)
    names = list(known_names or [])

    def chars_in(sent: str) -> set:
        return {n for n in names if n and n in sent}

    groups: list[tuple] = []
    cur: list[str] = []
    cur_len = 0
    cur_chars: set = set()
    for s in sentences:
        slen = len(s)
        sent_chars = chars_in(s)
        merged = cur_chars | sent_chars
        force_cut = bool(cur) and (
            cur_len + slen > max_chars or len(merged) > max_characters_per_scene
        )
        if force_cut:
            groups.append((cur, cur_chars))
            cur, cur_len, cur_chars = [s], slen, sent_chars
        else:
            cur.append(s); cur_len += slen; cur_chars = merged
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
            "_scene_characters": [n for n in names if n in char_set],
            "dialogues": _extract_dialogues(text, dialogue_mode),
        })
    return scenes


# ── HTTP ──────────────────────────────────────────────────────────────────────

class API:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=LUMI_API, timeout=None)

    async def close(self):
        await self.client.aclose()

    async def get(self, p, **k):  r = await self.client.get(p, **k);  r.raise_for_status(); return r.json()
    async def post(self, p, j=None):  r = await self.client.post(p, json=j);  r.raise_for_status(); return r.json() if r.content else None
    async def put(self, p, j=None):   r = await self.client.put(p, json=j);   r.raise_for_status(); return r.json() if r.content else None

    async def sse(self, p, j):
        async with self.client.stream("POST", p, json=j) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload == "[DONE]":
                        return
                    try:
                        yield json.loads(payload)
                    except json.JSONDecodeError:
                        continue


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run(args):
    api = API()

    # 1) 探活
    print("[1/9] health check")
    await api.get("/api/health")

    # 2) 新建项目
    print(f"[2/9] create project: {args.name}")
    proj = await api.post("/api/projects", {"name": args.name})
    pid = proj["id"]
    print(f"     id = {pid}")

    # 3) 生成文案（流式累积）
    print("[3/9] generate manuscript (LLM streaming)")
    cfg = {
        "length": "short",
        "audience": "普通观众",
        "style": "悬疑短剧",
        "tone": "压抑",
        "theme": "失踪",
        "worldview": "近未来上海",
        "characters": [{"name":"林夏","role":"侦探","traits":"冷静、寡言"}],
        "dialogue_mode": args.dialogue_mode,
    }
    parts = []
    async for evt in api.sse("/api/text-engine/generate-manuscript",
                              {"config": cfg, "existing_content": ""}):
        if "text" in evt:
            parts.append(evt["text"])
    manuscript = "".join(parts).strip()
    if not manuscript:
        print("文案生成失败，退出"); await api.close(); return
    await api.put(f"/api/projects/{pid}/manuscript",
                  {"content": manuscript, "config": cfg})

    # 3.5) 角色卡片（漫剧必做：保证多镜角色一致性）
    # 漫剧默认从 cfg.characters 取角色名；用户没给则从 args.character_names 取。
    char_names = (
        [c["name"] for c in cfg.get("characters", []) if c.get("name")]
        or [n.strip() for n in (args.character_names or "").split(",") if n.strip()]
    )
    project_chars: list[dict] = []
    if char_names:
        print(f"[3.5/9] build character cards: {char_names}")
        for name in char_names:
            profile = await api.post("/api/text-engine/generate-character-profile", {
                "name": name, "manuscript": manuscript,
                "existing_role": "", "existing_traits": "",
            })
            appearance = []
            async for evt in api.sse("/api/text-engine/generate-character-appearance", {
                "name": name,
                "role": profile.get("role", ""),
                "traits": profile.get("traits", ""),
                "existing": "",
            }):
                if "text" in evt:
                    appearance.append(evt["text"])
            project_chars.append({
                "name": name,
                "role": profile.get("role", ""),
                "traits": profile.get("traits", ""),
                "appearance": "".join(appearance).strip(),
                "negative": "",
            })
            print(f"     {name}: {profile.get('role','')} / {profile.get('traits','')[:30]}…")
        # 校验：appearance 必须非空，否则图片角色一致性无从谈起
        bad = [c["name"] for c in project_chars if not c.get("appearance", "").strip()]
        if bad:
            sys.exit(f"角色 appearance 流式累积为空：{bad}（LLM 输出异常，请检查文本引擎设置或重试）")

        await api.put(f"/api/projects/{pid}/characters", {"characters": project_chars})
        # 同步 manuscript.config.characters
        cfg["characters"] = [
            {"name": c["name"], "role": c["role"], "traits": c["traits"]}
            for c in project_chars
        ]
        await api.put(f"/api/projects/{pid}/manuscript",
                       {"content": manuscript, "config": cfg})
    else:
        print("[3.5/9] skip character cards (no names given; pass --character-names a,b,c)")

    # 4) 分镜（角色感知 + 字符上限）
    print(f"[4/9] split scenes (manual, max_chars={args.max_chars}, "
          f"max_chars_per_scene={args.max_chars_per_scene})")
    if args.dialogue_mode == "reading" or args.manual_scenes:
        scenes = manual_split(
            manuscript,
            args.dialogue_mode,
            args.max_chars,
            known_names=[c["name"] for c in project_chars],
            max_characters_per_scene=args.max_chars_per_scene,
        )
    else:
        sc = await api.post("/api/text-engine/generate-scenes",
                             {"manuscript": manuscript,
                              "dialogue_mode": args.dialogue_mode,
                              "characters": cfg.get("characters", [])})
        scenes = sc["scenes"]
    print(f"     {len(scenes)} scenes")
    for s in scenes:
        if s.get("_scene_characters"):
            print(f"       {s['id']}: {s['_scene_characters']}")
    await api.put(f"/api/projects/{pid}/scenes", {"scenes": scenes})

    # 5) 为每镜生成首/末帧 prompt — 只传该镜出镜的角色（避免多人物干扰）
    # 并发数取自 settings.text_engine.concurrency；本地模型 1~4，云端 deepseek-v4-flash 等可设几百
    settings_now = await api.get("/api/settings")
    text_concurrency = int(settings_now.get("text_engine", {}).get("concurrency", 1)) or 1
    print(f"[5/9] generate frame prompts (concurrency={text_concurrency})")
    chars_by_name = {c["name"]: c for c in project_chars}
    frame_sem = asyncio.Semaphore(text_concurrency)

    async def gen_frame(i: int, s: dict):
        selected = set(s.get("_scene_characters") or [])
        scene_chars = [chars_by_name[n] for n in selected if n in chars_by_name]
        async with frame_sem:
            r = await api.post("/api/text-engine/generate-frame-prompts", {
                "description": s["description"],
                "dialogues":   s.get("dialogues", []),
                "characters":  scene_chars,            # 0 或 1 个
                "manuscript":  manuscript,
                "scene_index": i + 1,
                "total_scenes": len(scenes),
            })
        s["start_frame_prompt"] = r.get("start_frame_prompt", "")
        s["end_frame_prompt"]   = r.get("end_frame_prompt", "")
        print(f"     scene {i+1} chars={list(selected)}: {s['start_frame_prompt'][:50]}…")

    await asyncio.gather(*(gen_frame(i, s) for i, s in enumerate(scenes)))
    await api.put(f"/api/projects/{pid}/scenes", {"scenes": scenes})

    # 6) 图片批量生成（需要 workflow_name & ComfyUI）
    if args.image_workflow:
        print(f"[6/9] generate images via ComfyUI workflow: {args.image_workflow}")
        frames = []
        for s in scenes:
            for ft in ("start", "end"):
                prompt = s.get(f"{ft}_frame_prompt", "")
                if prompt:
                    frames.append({"scene_id": s["id"], "frame_type": ft, "prompt": prompt})
        slot_keys = []
        counts = {}
        async for evt in api.sse("/api/image-engine/generate-batch-stream", {
            "workflow_name": args.image_workflow,
            "gen_count": 1,
            "negative_prompt": "",
            "width": 0, "height": 0,
            "frames": frames,
        }):
            if evt.get("event") == "completed":
                sid, ft, si = evt["scene_id"], evt["frame_type"], evt["slot_index"]
                imgs = evt.get("images") or []
                if imgs:
                    await api.put(f"/api/projects/{pid}/images/slot",
                                  {"scene_id": sid, "frame_type": ft,
                                   "slot_index": si, "data": imgs[0]["data"]})
                    slot_keys.append({"scene_id": sid, "frame_type": ft, "slot_index": si})
                    counts[f"{sid}:{ft}"] = counts.get(f"{sid}:{ft}", 0) + 1
                    print(f"     image saved: {sid}:{ft}:{si}")
        await api.put(f"/api/projects/{pid}/images/metadata", {
            "counts": counts,
            "selected": {f"{sk['scene_id']}:{sk['frame_type']}": 0 for sk in slot_keys},
            "slot_keys": slot_keys,
        })
    else:
        print("[6/9] skip image gen (--image-workflow 未提供)")

    # 7) 音频（按 dialogue_mode 分流）
    # 关键：reading 模式必须用 key "__ms_reading__{sceneId}"，
    #       否则前端音频页和视频页都看不到。
    print(f"[7/9] generate audio (mode={args.dialogue_mode})")
    audio_state: dict = {}
    # scene_id → 用于视频生成的 base64 + duration
    audio_for_video: dict[str, dict] = {}

    if args.dialogue_mode == "reading":
        for s in scenes:
            text = s["dialogues"][0]["text"]
            r = await api.post("/api/audio-engine/ms-tts", {
                "text": text, "voice": args.voice, "rate": args.rate,
            })
            key = f"__ms_reading__{s['id']}"
            audio_state[key] = {"data": r["data"], "duration_ms": r["duration_ms"]}
            audio_for_video[s["id"]] = {"data": r["data"], "duration_ms": r["duration_ms"]}
            print(f"     ms-tts {s['id']}: {r['duration_ms']}ms (key={key})")
    else:
        # IndexTTS：每镜每段单独生成 → stitch
        dialogues_payload = []
        for s in scenes:
            for j, d in enumerate(s.get("dialogues", [])):
                if d.get("text"):
                    dialogues_payload.append({
                        "scene_id": s["id"], "dialogue_id": f"{s['id']}:{j}",
                        "text": d["text"], "voice_ref": args.voice_ref,
                        "emo_ref": None, "emo_weight": 0.8,
                    })
        scene_clips: dict[str, list] = {}
        slot_data: dict[str, list] = {}        # clip_id -> [{data,duration}]
        async for evt in api.sse("/api/audio-engine/generate-batch-stream", {
            "gen_count": 1, "speed": 1.0, "dialogues": dialogues_payload,
        }):
            if evt.get("event") == "completed":
                sid = evt["scene_id"]; cid = evt["dialogue_id"]
                # ⚠️ SSE 字段是 data, 不是 audio
                b64 = evt["data"]
                slot_data.setdefault(cid, []).append({"data": b64, "duration": ""})
                scene_clips.setdefault(sid, []).append({
                    "data": b64, "pre_silence_ms": 0, "post_silence_ms": 300
                })
        # 单段 key = "{sceneId}:{dialogueIdx}"
        for cid, slots in slot_data.items():
            audio_state[cid] = {
                "voiceRef": args.voice_ref or "", "emoRef": None,
                "emoMethod": "与音色参考音频相同", "emoWeight": 0.8,
                "selectedSlot": 0, "slots": slots,
            }
        # 拼接 key = "__stitched__{sceneId}"
        for sid, clips in scene_clips.items():
            r = await api.post("/api/audio-engine/stitch-scene", {"clips": clips})
            audio_state[f"__stitched__{sid}"] = {"data": r["data"], "duration_ms": r["duration_ms"]}
            audio_for_video[sid] = {"data": r["data"], "duration_ms": r["duration_ms"]}

    await api.put(f"/api/projects/{pid}/audio", audio_state)

    # 8) 视频（需要 LTX workflow 与全套 start/end/audio）
    if args.video_workflow and args.image_workflow:
        # 8a) 视频提示词批量生成（关注运动 / 表情 / 镜头，不重复 appearance 标签）
        print(f"[8a/9] generate video prompts (concurrency={text_concurrency})")
        video_prompts: dict[str, str] = {}
        vp_sem = asyncio.Semaphore(text_concurrency)

        async def gen_video_prompt(i: int, s: dict):
            selected_names = set(s.get("_scene_characters") or [])
            scene_chars = [chars_by_name[n] for n in selected_names if n in chars_by_name]
            async with vp_sem:
                parts = []
                async for evt in api.sse("/api/text-engine/generate-video-prompt", {
                    "description":        s.get("description", ""),
                    "dialogues":          s.get("dialogues", []),
                    "characters":         scene_chars,
                    "start_frame_prompt": s.get("start_frame_prompt", ""),
                    "end_frame_prompt":   s.get("end_frame_prompt", ""),
                    "manuscript":         manuscript,
                    "scene_index":        i + 1,
                    "total_scenes":       len(scenes),
                }):
                    if "text" in evt:
                        parts.append(evt["text"])
                video_prompts[s["id"]] = "".join(parts).strip()
            print(f"     {s['id']}: {video_prompts[s['id']][:60]}…")

        await asyncio.gather(*(gen_video_prompt(i, s) for i, s in enumerate(scenes)))
        await api.put(f"/api/projects/{pid}/video-prompts", video_prompts)

        print(f"[8/9] generate video via LTX workflow: {args.video_workflow}")
        # 读图片元数据，取每镜 selected slot
        imgs = await api.get(f"/api/projects/{pid}/images")
        slot_by_key = {
            f"{s['scene_id']}:{s['frame_type']}:{s['slot_index']}": s["url"]
            for s in imgs.get("slots", [])
        }
        selected = imgs.get("selected", {})

        async def fetch_b64(url: str) -> str:
            r = await api.client.get(url)
            r.raise_for_status()
            return base64.b64encode(r.content).decode()

        scenes_payload = []
        for i, s in enumerate(scenes):
            sid = s["id"]
            start_url = slot_by_key.get(f"{sid}:start:{selected.get(f'{sid}:start', 0)}")
            end_url   = slot_by_key.get(f"{sid}:end:{selected.get(f'{sid}:end', 0)}")
            aud = audio_for_video.get(sid)
            if not (start_url and end_url and aud):
                print(f"     skip scene {sid} (missing assets: "
                      f"start={bool(start_url)} end={bool(end_url)} audio={bool(aud)})")
                continue
            scenes_payload.append({
                "scene_id": sid, "scene_index": i + 1,
                "start_image_b64": await fetch_b64(start_url),
                "end_image_b64":   await fetch_b64(end_url),
                # reading: mp3 base64；其它模式: stitched wav base64。两者后端都接受。
                "audio_b64":       aud["data"],
                "duration_ms":     aud["duration_ms"],
                # 优先用刚生成的 video prompt（含运动/表情）；缺失时退回 frame prompt
                "positive_prompt": video_prompts.get(sid) or s.get("start_frame_prompt", ""),
            })
        if not scenes_payload:
            print("     no scene ready for video gen, skip")
        else:
            videos_save = []
            async for evt in api.sse("/api/video-engine/generate-stream", {
                "workflow_name": args.video_workflow,
                "resolution": args.resolution,
                "fps": args.fps,
                "scenes": scenes_payload,
            }):
                ev = evt.get("event")
                if ev == "scene_done":
                    # ⚠️ 字段是 video，不是 video_b64
                    videos_save.append({"scene_id": evt["scene_id"], "data": evt["video"]})
                    print(f"     video done: {evt['scene_id']}")
                elif ev == "scene_error":
                    print(f"     ! {evt['scene_id']}: {evt.get('message')}", file=sys.stderr)
                elif ev == "progress":
                    print(f"\r     [{evt.get('scene_id')}] {evt.get('value')}/{evt.get('max')}", end="", flush=True)
            print()
            if videos_save:
                await api.put(f"/api/projects/{pid}/videos", videos_save)

            # 视频段全部产出后合并成片，字幕生成需要 final_video.mp4
            try:
                order = [s["id"] for s in scenes]
                r = await api.post("/api/video-engine/merge-project-video",
                                    {"project_id": pid, "scene_order": order})
                print(f"     final video: {r['output_path']}")
            except Exception as e:
                print(f"     merge failed: {e}", file=sys.stderr)
    else:
        print("[8/9] skip video (--video-workflow & --image-workflow 未都提供)")

    # 9) 字幕
    status = await api.get(f"/api/subtitle-engine/status/{pid}")
    if status["has_final_video"]:
        print("[9/9] generate + embed subtitles (manuscript → preprocess-text → generate-srt)")
        # 漫剧字幕首选：manuscript 原文 → preprocess-text 细切（逗号也断句）
        pr = await api.post("/api/subtitle-engine/preprocess-text", {"text": manuscript})
        lines = pr.get("lines", [])
        print(f"     {len(lines)} subtitle lines after preprocess")
        async for evt in api.sse("/api/subtitle-engine/generate-srt", {
            "project_id": pid, "lines": lines, "fps": args.fps,
            "manual_advance": 0.0, "model_name": "base",
        }):
            print(f"     srt step={evt.get('step')} pct={evt.get('pct','')}")
        # 字幕字号按视频方向自适应：竖屏 10 / 横屏 16
        try:
            w, h = (int(x) for x in args.resolution.lower().split("x"))
            font_size = 10 if w < h else 16
        except Exception:
            font_size = 10
        print(f"     embed font_size={font_size} (resolution {args.resolution})")
        async for evt in api.sse("/api/subtitle-engine/embed", {
            "project_id": pid, "font_name": "等线 Bold", "font_size": font_size,
        }):
            print(f"     embed step={evt.get('step')} pct={evt.get('pct','')}")
    else:
        print("[9/9] skip subtitle (no final_video.mp4)")

    print(f"\nDone. Open project dir to see results: project id = {pid}")
    await api.close()


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--name", default=f"E2E-{int(time.time())}")
    p.add_argument("--dialogue-mode", default="reading",
                   choices=["narration","dialogue","mixed","reading"])
    p.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="reading 模式 Edge TTS 声音")
    p.add_argument("--rate", default="+25%", help="漫剧默认 +25%（快）")
    p.add_argument("--voice-ref", default="", help="IndexTTS 模式音色文件名")
    p.add_argument("--image-workflow", default="", help="留空则跳过出图")
    p.add_argument("--video-workflow", default="", help="留空则跳过视频")
    p.add_argument("--resolution", default="720x1280", help="漫剧默认 720x1280 竖屏；横屏可用 1280x720")
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--max-chars", type=int, default=50, help="手动分镜：单镜字符上限，默认 50 ≈ 12.5s")
    p.add_argument("--max-chars-per-scene", type=int, default=1,
                   help="单镜出镜角色上限，默认 1（本地文生图限制）")
    p.add_argument("--character-names", default="",
                   help="逗号分隔的角色名清单（如 '林夏,张川'）；缺省时从 manuscript.config.characters 读取")
    p.add_argument("--manual-scenes", action="store_true",
                   help="非 reading 模式也强制走手动分镜（reading 默认就是手动）")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse()))
