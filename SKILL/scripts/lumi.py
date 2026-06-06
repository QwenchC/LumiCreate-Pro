#!/usr/bin/env python3
"""
lumi.py — LumiCreate-Pro 客户端 CLI

提供常用调用的便捷入口，封装：
- 普通 JSON 接口
- SSE 流式接口（自动累积/打印 / 写入回调）
- 大体积二进制（图片/音频/视频）的 base64 读写

依赖：httpx>=0.27   `pip install httpx`

环境变量：
  LUMI_API   默认 http://127.0.0.1:18520

子命令一览：
  health
  projects [list|new|info|delete]
  manuscript [get|put|generate]
  scenes [get|put|generate]
  characters [get|put|profile|appearance]
  images [list|generate]
  audio [generate|stitch|ms-tts]
  video [workflows|generate|merge]
  subtitle [status|script|generate-srt|embed]
  settings [get|patch]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

import httpx

LUMI_API = os.environ.get("LUMI_API", "http://127.0.0.1:18520")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _client(timeout: float | None = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=LUMI_API, timeout=timeout)


async def _get(path: str, **kw) -> Any:
    async with _client() as c:
        r = await c.get(path, **kw)
        r.raise_for_status()
        return r.json()


async def _post(path: str, json_body: Any | None = None, **kw) -> Any:
    async with _client() as c:
        r = await c.post(path, json=json_body, **kw)
        r.raise_for_status()
        return r.json() if r.content else None


async def _put(path: str, json_body: Any | None = None, **kw) -> Any:
    async with _client() as c:
        r = await c.put(path, json=json_body, **kw)
        r.raise_for_status()
        return r.json() if r.content else None


async def _delete(path: str) -> None:
    async with _client() as c:
        r = await c.delete(path)
        r.raise_for_status()


async def _sse(path: str, json_body: Any) -> AsyncIterator[dict]:
    """Stream SSE events as dicts; yields nothing on [DONE]."""
    async with _client(timeout=None) as c:
        async with c.stream("POST", path, json=json_body) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    return
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue


# ── Health ────────────────────────────────────────────────────────────────────

async def cmd_health(_):
    print(json.dumps(await _get("/api/health"), ensure_ascii=False, indent=2))


# ── Projects ──────────────────────────────────────────────────────────────────

async def cmd_projects_list(_):
    data = await _get("/api/projects")
    for p in data:
        print(f"{p['id']}  {p['progress']}  {p['name']}")


async def cmd_projects_new(args):
    body = {"name": args.name, "description": args.desc or "", "folder_id": args.folder or "default"}
    print(json.dumps(await _post("/api/projects", body), ensure_ascii=False, indent=2))


async def cmd_projects_info(args):
    print(json.dumps(await _get(f"/api/projects/{args.id}"), ensure_ascii=False, indent=2))


async def cmd_projects_delete(args):
    if not args.yes:
        print("DANGER: 这将永久删除项目目录。加 --yes 才执行。", file=sys.stderr)
        sys.exit(2)
    await _delete(f"/api/projects/{args.id}")
    print(f"deleted {args.id}")


# ── Manuscript ────────────────────────────────────────────────────────────────

async def cmd_manuscript_get(args):
    data = await _get(f"/api/projects/{args.id}/manuscript")
    print(json.dumps(data, ensure_ascii=False, indent=2))


async def cmd_manuscript_put(args):
    content = Path(args.content_file).read_text(encoding="utf-8") if args.content_file else (args.content or "")
    config = json.loads(Path(args.config_file).read_text(encoding="utf-8")) if args.config_file else {}
    body = {"content": content, "config": config}
    print(json.dumps(await _put(f"/api/projects/{args.id}/manuscript", body), ensure_ascii=False, indent=2))


async def cmd_manuscript_generate(args):
    cfg_path = Path(args.config_file)
    if not cfg_path.exists():
        sys.exit(f"config_file 不存在: {cfg_path}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    existing = Path(args.existing).read_text(encoding="utf-8") if args.existing else ""

    body = {"config": cfg, "existing_content": existing}
    full = []
    async for evt in _sse("/api/text-engine/generate-manuscript", body):
        if "text" in evt:
            sys.stdout.write(evt["text"])
            sys.stdout.flush()
            full.append(evt["text"])
        elif "error" in evt:
            print(f"\n[ERROR] {evt['error']}", file=sys.stderr)
    sys.stdout.write("\n")

    if args.save:
        await _put(f"/api/projects/{args.save}/manuscript",
                   {"content": "".join(full), "config": cfg})
        print(f"\nsaved to project {args.save}")


# ── Scenes ────────────────────────────────────────────────────────────────────

async def cmd_scenes_get(args):
    print(json.dumps(await _get(f"/api/projects/{args.id}/scenes"), ensure_ascii=False, indent=2))


async def cmd_scenes_generate(args):
    """从项目当前 manuscript 自动生成分镜。"""
    ms = await _get(f"/api/projects/{args.id}/manuscript")
    chars = (await _get(f"/api/projects/{args.id}/characters"))["characters"]
    cfg = ms.get("config", {})
    body = {
        "manuscript": ms.get("content", ""),
        "dialogue_mode": cfg.get("dialogue_mode", "mixed"),
        "characters": chars,
    }
    data = await _post("/api/text-engine/generate-scenes", body)
    print(f"generated {data.get('total', 0)} scenes")
    if args.save:
        await _put(f"/api/projects/{args.id}/scenes", {"scenes": data["scenes"]})
        print("saved.")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


# ── Manual split (intent-equivalent of the "✂ 从文案手动生成分镜" button) ────

import re as _re_mod
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
    for m in _re_mod.finditer(r"[「“‘](.*?)[」”’]", text, _re_mod.DOTALL):
        t = m.group(1).strip()
        if t:
            dlgs.append({"character": "", "text": t, "emotion": "平静"})
    return dlgs


def _manual_split(manuscript: str, dialogue_mode: str, max_chars: int,
                   known_names: list[str] | None = None,
                   max_characters_per_scene: int = 1) -> list[dict]:
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


async def cmd_scenes_split_manual(args):
    """漫剧首选：客户端按句切分 + ≤max-chars 合并 + ≤max-chars-per-scene 角色拆分。"""
    ms = await _get(f"/api/projects/{args.id}/manuscript")
    text = ms.get("content", "")
    if not text.strip():
        sys.exit("项目无文案，先 manuscript put/generate")
    mode = ms.get("config", {}).get("dialogue_mode", "reading")

    known_names: list[str] = []
    if not args.ignore_characters:
        chars_data = await _get(f"/api/projects/{args.id}/characters")
        known_names = [c["name"] for c in chars_data.get("characters", []) if c.get("name")]
        if not known_names:
            print("⚠ 项目无 characters，分镜将退化为纯字数切分；建议先 `characters auto-build`",
                  file=sys.stderr)

    scenes = _manual_split(
        text, mode, args.max_chars,
        known_names=known_names,
        max_characters_per_scene=args.max_chars_per_scene,
    )
    print(f"split into {len(scenes)} scenes "
          f"(max_chars={args.max_chars}, max_chars_per_scene={args.max_chars_per_scene}, "
          f"known_names={known_names}, mode={mode})")
    multi = 0
    for s in scenes:
        head = s["description"][:30].replace("\n", "")
        roster = s["_scene_characters"]
        flag = " ⚠多人" if len(roster) > args.max_chars_per_scene else ""
        if len(roster) > args.max_chars_per_scene:
            multi += 1
        print(f"  {s['id']}: ({len(s['description'])} chars){flag} chars={roster} {head}…")
    if multi:
        print(f"\n⚠ {multi} 个分镜出镜超过 {args.max_chars_per_scene}（单句已含多人名，无法再切）",
              file=sys.stderr)
    if args.save:
        await _put(f"/api/projects/{args.id}/scenes", {"scenes": scenes})
        print("saved.")


# ── Characters ────────────────────────────────────────────────────────────────

async def cmd_characters_get(args):
    print(json.dumps(await _get(f"/api/projects/{args.id}/characters"), ensure_ascii=False, indent=2))


async def cmd_characters_profile(args):
    ms = await _get(f"/api/projects/{args.id}/manuscript")
    body = {
        "name": args.name,
        "manuscript": ms.get("content", ""),
        "existing_role": args.role or "",
        "existing_traits": args.traits or "",
    }
    print(json.dumps(await _post("/api/text-engine/generate-character-profile", body),
                     ensure_ascii=False, indent=2))


async def cmd_characters_appearance(args):
    body = {"name": args.name, "role": args.role or "", "traits": args.traits or "", "existing": ""}
    async for evt in _sse("/api/text-engine/generate-character-appearance", body):
        if "text" in evt:
            sys.stdout.write(evt["text"])
            sys.stdout.flush()
    sys.stdout.write("\n")


async def cmd_characters_auto_build(args):
    """漫剧建卡：给定角色名清单，自动跑 profile + appearance，PUT characters，同步 manuscript.config。"""
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    if not names:
        sys.exit("--names 至少给一个角色名")

    ms = await _get(f"/api/projects/{args.id}/manuscript")
    ms_text = ms.get("content", "")
    if not ms_text.strip():
        sys.exit("项目无文案；先 manuscript put/generate")

    # 现有 characters：保留已有的（按名字去重）
    cur = (await _get(f"/api/projects/{args.id}/characters")).get("characters", []) or []
    by_name = {c["name"]: c for c in cur}

    for name in names:
        print(f"\n── {name} ──")
        existing = by_name.get(name, {})
        # 1) profile
        profile = await _post("/api/text-engine/generate-character-profile", {
            "name": name,
            "manuscript": ms_text,
            "existing_role": existing.get("role", ""),
            "existing_traits": existing.get("traits", ""),
        })
        print(f"  role:   {profile.get('role','')}")
        print(f"  traits: {profile.get('traits','')}")
        # 2) appearance（流式）
        appearance_parts = []
        async for evt in _sse("/api/text-engine/generate-character-appearance", {
            "name": name,
            "role": profile.get("role", ""),
            "traits": profile.get("traits", ""),
            "existing": existing.get("appearance", "") if args.overwrite_appearance else "",
        }):
            if "text" in evt:
                sys.stdout.write(evt["text"]); sys.stdout.flush()
                appearance_parts.append(evt["text"])
        print()
        by_name[name] = {
            "name": name,
            "role": profile.get("role", ""),
            "traits": profile.get("traits", ""),
            "appearance": "".join(appearance_parts).strip(),
            "negative": existing.get("negative", ""),
        }

    chars = list(by_name.values())
    await _put(f"/api/projects/{args.id}/characters", {"characters": chars})
    print(f"\nPUT characters: {len(chars)} total")

    # 同步 manuscript.config.characters（便于前端"从文案导入角色"复用）
    cfg = ms.get("config") or {}
    cfg["characters"] = [
        {"name": c["name"], "role": c["role"], "traits": c["traits"]}
        for c in chars
    ]
    await _put(f"/api/projects/{args.id}/manuscript",
               {"content": ms_text, "config": cfg})
    print("synced manuscript.config.characters")


# ── Prompts (frame / video) ───────────────────────────────────────────────────

async def _resolve_concurrency(cli_value: int | None) -> int:
    """CLI 显式值优先；否则读 settings.text_engine.concurrency；fallback 1。"""
    if cli_value and cli_value > 0:
        return cli_value
    try:
        s = await _get("/api/settings")
        return int((s.get("text_engine") or {}).get("concurrency", 1)) or 1
    except Exception:
        return 1


async def cmd_prompts_frame_batch(args):
    """对项目所有分镜批量生成 start/end frame prompts，并 hydrate 出镜角色为完整对象。"""
    scenes = (await _get(f"/api/projects/{args.id}/scenes")).get("scenes", [])
    if not scenes:
        sys.exit("项目无分镜")
    chars = (await _get(f"/api/projects/{args.id}/characters")).get("characters", []) or []
    chars_by_name = {c["name"]: c for c in chars}
    ms = await _get(f"/api/projects/{args.id}/manuscript")
    ms_text = ms.get("content", "")
    concurrency = await _resolve_concurrency(args.concurrency)
    print(f"  concurrency = {concurrency}")

    # 出场角色 appearance 非空校验
    needed = {n for s in scenes for n in (s.get("_scene_characters") or [])}
    bad_appearance = [n for n in needed
                       if n in chars_by_name
                       and not chars_by_name[n].get("appearance", "").strip()]
    if bad_appearance and not args.allow_empty_appearance:
        sys.exit(
            f"以下角色 appearance 为空，先跑 `characters auto-build`：{bad_appearance}\n"
            f"（或加 --allow-empty-appearance 强制继续，仅用于调试）"
        )
    missing_chars = [n for n in needed if n not in chars_by_name]
    if missing_chars:
        print(f"⚠ 分镜引用但 characters.json 中找不到的角色：{missing_chars}", file=sys.stderr)

    total = len(scenes)
    sem = asyncio.Semaphore(concurrency)

    async def gen_one(i: int, s: dict):
        if not args.force and s.get("start_frame_prompt") and s.get("end_frame_prompt"):
            print(f"  [{i+1}/{total}] {s['id']}: skip (--force 重生成)")
            return
        selected = set(s.get("_scene_characters") or [])
        scene_chars = [chars_by_name[n] for n in selected if n in chars_by_name]
        async with sem:
            try:
                r = await _post("/api/text-engine/generate-frame-prompts", {
                    "description":  s.get("description", ""),
                    "dialogues":    s.get("dialogues", []),
                    "characters":   scene_chars,
                    "manuscript":   ms_text,
                    "scene_index":  i + 1,
                    "total_scenes": total,
                })
            except Exception as e:
                print(f"  [{i+1}/{total}] {s['id']}: error {e}", file=sys.stderr)
                return
        s["start_frame_prompt"] = r.get("start_frame_prompt", "")
        s["end_frame_prompt"]   = r.get("end_frame_prompt", "")
        print(f"  [{i+1}/{total}] {s['id']} chars={list(selected)}: "
              f"{s['start_frame_prompt'][:60]}…")

    await asyncio.gather(*(gen_one(i, s) for i, s in enumerate(scenes)))
    await _put(f"/api/projects/{args.id}/scenes", {"scenes": scenes})
    print(f"saved {total} scenes")


async def cmd_prompts_video_batch(args):
    """对项目所有分镜批量生成视频 positive_prompt，写入 video_prompts.json。"""
    scenes = (await _get(f"/api/projects/{args.id}/scenes")).get("scenes", [])
    if not scenes:
        sys.exit("项目无分镜")
    chars = (await _get(f"/api/projects/{args.id}/characters")).get("characters", []) or []
    chars_by_name = {c["name"]: c for c in chars}
    ms = await _get(f"/api/projects/{args.id}/manuscript")
    ms_text = ms.get("content", "")

    existing = await _get(f"/api/projects/{args.id}/video-prompts")
    if not isinstance(existing, dict):
        existing = {}

    total = len(scenes)
    concurrency = await _resolve_concurrency(args.concurrency)
    print(f"  concurrency = {concurrency}")
    sem = asyncio.Semaphore(concurrency)

    async def gen_one(i: int, s: dict):
        sid = s["id"]
        if not args.force and existing.get(sid):
            print(f"  [{i+1}/{total}] {sid}: skip (--force 重生成)")
            return
        selected = set(s.get("_scene_characters") or [])
        scene_chars = [chars_by_name[n] for n in selected if n in chars_by_name]
        async with sem:
            parts = []
            async for evt in _sse("/api/text-engine/generate-video-prompt", {
                "description":        s.get("description", ""),
                "dialogues":          s.get("dialogues", []),
                "characters":         scene_chars,
                "start_frame_prompt": s.get("start_frame_prompt", ""),
                "end_frame_prompt":   s.get("end_frame_prompt", ""),
                "manuscript":         ms_text,
                "scene_index":        i + 1,
                "total_scenes":       total,
            }):
                if "text" in evt:
                    parts.append(evt["text"])
            existing[sid] = "".join(parts).strip()
        print(f"  [{i+1}/{total}] {sid}: {existing[sid][:60]}…")

    await asyncio.gather(*(gen_one(i, s) for i, s in enumerate(scenes)))
    await _put(f"/api/projects/{args.id}/video-prompts", existing)
    print(f"saved {len(existing)} video prompts")


# ── Images ────────────────────────────────────────────────────────────────────

async def cmd_images_list(args):
    print(json.dumps(await _get(f"/api/projects/{args.id}/images"), ensure_ascii=False, indent=2))


async def cmd_images_generate(args):
    """批量为项目所有分镜生成图片（首+末帧）。"""
    scenes_data = await _get(f"/api/projects/{args.id}/scenes")
    scenes = scenes_data.get("scenes", [])

    # 出图前预检：每镜的 frame prompt 都得有
    missing = [s["id"] for s in scenes
               if not s.get("start_frame_prompt") or not s.get("end_frame_prompt")]
    if missing and not args.skip_check:
        sys.exit(
            f"以下分镜 frame prompt 为空：{missing}\n"
            f"先跑 `lumi.py prompts frame-batch {args.id}`（会自动 hydrate 角色 appearance）。\n"
            f"--skip-check 可跳过但会出随机图。"
        )

    # 出图前再校验：每镜出场角色在 characters.json 中是否有非空 appearance
    chars = (await _get(f"/api/projects/{args.id}/characters")).get("characters", []) or []
    chars_by_name = {c["name"]: c for c in chars}
    bad = []
    for s in scenes:
        for n in (s.get("_scene_characters") or []):
            c = chars_by_name.get(n)
            if not c or not c.get("appearance", "").strip():
                bad.append(n)
    bad = sorted(set(bad))
    if bad and not args.skip_check:
        sys.exit(
            f"以下出镜角色 appearance 为空：{bad}\n"
            f"先 `characters auto-build {args.id} --names \"{','.join(bad)}\"` 再回来跑 prompts frame-batch。"
        )

    frames = []
    for s in scenes:
        if s.get("start_frame_prompt"):
            frames.append({"scene_id": s["id"], "frame_type": "start", "prompt": s["start_frame_prompt"]})
        if s.get("end_frame_prompt"):
            frames.append({"scene_id": s["id"], "frame_type": "end", "prompt": s["end_frame_prompt"]})

    if not frames:
        sys.exit("分镜没有 start_frame_prompt / end_frame_prompt，先用 `prompts frame-batch`")

    body = {
        "workflow_name": args.workflow,
        "gen_count": args.gen_count,
        "negative_prompt": args.negative or "",
        "width": args.width, "height": args.height,
        "frames": frames,
    }

    slot_keys = []
    counts: dict[str, int] = {}
    async for evt in _sse("/api/image-engine/generate-batch-stream", body):
        ev = evt.get("event")
        sid = evt.get("scene_id"); ft = evt.get("frame_type"); si = evt.get("slot_index")
        if ev == "progress":
            print(f"\r[{sid}:{ft}:{si}] {evt.get('value')}/{evt.get('max')}", end="", flush=True)
        elif ev == "completed":
            imgs = evt.get("images", [])
            if imgs and args.save:
                await _put(f"/api/projects/{args.id}/images/slot",
                           {"scene_id": sid, "frame_type": ft, "slot_index": si, "data": imgs[0]["data"]})
            slot_keys.append({"scene_id": sid, "frame_type": ft, "slot_index": si})
            key = f"{sid}:{ft}"
            counts[key] = max(counts.get(key, 0), si + 1)
            print(f"\n[DONE] {sid}:{ft}:{si}")
        elif ev == "error":
            print(f"\n[ERROR {sid}:{ft}:{si}] {evt.get('message')}", file=sys.stderr)
        elif ev == "batch_done":
            print(f"\nbatch_done: {evt.get('total')}")

    if args.save:
        selected = {f"{k}:{ft}": 0 for k in {(sk['scene_id'], sk['frame_type']) for sk in slot_keys}
                    for ft in []}  # placeholder
        selected = {f"{sk['scene_id']}:{sk['frame_type']}": 0 for sk in slot_keys}
        await _put(f"/api/projects/{args.id}/images/metadata",
                   {"counts": counts, "selected": selected, "slot_keys": slot_keys})
        print("metadata saved.")


# ── Audio ─────────────────────────────────────────────────────────────────────

async def cmd_audio_ms_tts(args):
    body = {"text": args.text, "voice": args.voice, "rate": args.rate}
    r = await _post("/api/audio-engine/ms-tts", body)
    out = Path(args.out)
    out.write_bytes(base64.b64decode(r["data"]))
    print(f"saved {out} ({r['duration_ms']}ms)")

    # 可选：按 reading 模式正确 key 写入项目音频（前端音频页能看到预览）
    if args.save_project:
        if not args.scene_id:
            print("WARN: --save-project 需要同时提供 --scene-id，跳过保存", file=sys.stderr)
            return
        cur = await _get(f"/api/projects/{args.save_project}/audio")
        if not isinstance(cur, dict):
            cur = {}
        cur[f"__ms_reading__{args.scene_id}"] = {
            "data": r["data"], "duration_ms": r["duration_ms"],
        }
        await _put(f"/api/projects/{args.save_project}/audio", cur)
        print(f"saved to project {args.save_project} as __ms_reading__{args.scene_id}")


async def cmd_audio_reading_all(args):
    """漫剧/朗读模式：对项目所有分镜批量调 Edge TTS，按 __ms_reading__{sceneId} 写入项目音频。"""
    scenes = (await _get(f"/api/projects/{args.id}/scenes")).get("scenes", [])
    if not scenes:
        sys.exit("项目没有分镜")

    cur = await _get(f"/api/projects/{args.id}/audio")
    if not isinstance(cur, dict):
        cur = {}

    done = 0
    for s in scenes:
        sid = s["id"]
        dialogues = s.get("dialogues", [])
        text = (dialogues[0].get("text") if dialogues else "") or s.get("description", "")
        if not text:
            print(f"  - {sid}: 无文本，跳过")
            continue
        r = await _post("/api/audio-engine/ms-tts",
                        {"text": text, "voice": args.voice, "rate": args.rate})
        cur[f"__ms_reading__{sid}"] = {"data": r["data"], "duration_ms": r["duration_ms"]}
        done += 1
        print(f"  + {sid}: {r['duration_ms']}ms")
    await _put(f"/api/projects/{args.id}/audio", cur)
    print(f"done: {done}/{len(scenes)} scenes saved as __ms_reading__*")


async def cmd_audio_stitch(args):
    """读多个 wav 文件 → 拼成一段。简单等长静音。"""
    clips = []
    for f in args.files:
        clips.append({
            "data": base64.b64encode(Path(f).read_bytes()).decode(),
            "pre_silence_ms": 0,
            "post_silence_ms": args.gap_ms,
        })
    r = await _post("/api/audio-engine/stitch-scene", {"clips": clips})
    Path(args.out).write_bytes(base64.b64decode(r["data"]))
    print(f"saved {args.out} ({r['duration_ms']}ms)")


# ── Video ─────────────────────────────────────────────────────────────────────

async def cmd_video_workflows(_):
    print(json.dumps(await _get("/api/video-engine/workflows"), ensure_ascii=False, indent=2))


async def cmd_video_merge(args):
    """按当前分镜顺序合并所有分镜视频。"""
    scenes = (await _get(f"/api/projects/{args.id}/scenes")).get("scenes", [])
    order = [s["id"] for s in scenes]
    if not order:
        sys.exit("项目没有分镜")
    r = await _post("/api/video-engine/merge-project-video",
                    {"project_id": args.id, "scene_order": order})
    print(json.dumps(r, ensure_ascii=False, indent=2))


# ── Subtitle ──────────────────────────────────────────────────────────────────

async def cmd_subtitle_status(args):
    print(json.dumps(await _get(f"/api/subtitle-engine/status/{args.id}"),
                     ensure_ascii=False, indent=2))


async def cmd_subtitle_script(args):
    print(json.dumps(await _get(f"/api/subtitle-engine/script/{args.id}"),
                     ensure_ascii=False, indent=2))


async def cmd_subtitle_generate_srt(args):
    """漫剧默认：manuscript → preprocess-text 细切 → generate-srt。
    --from-scenes 走旧路径（分镜聚合脚本，粒度粗）。"""
    if args.from_scenes:
        sc = await _get(f"/api/subtitle-engine/script/{args.id}")
        lines = sc.get("lines", [])
        source = "scenes"
    else:
        ms = await _get(f"/api/projects/{args.id}/manuscript")
        text = ms.get("content", "")
        if not text.strip():
            sys.exit("项目无文案，先 manuscript put/generate；或加 --from-scenes 走分镜抽取")
        r = await _post("/api/subtitle-engine/preprocess-text", {"text": text})
        lines = r.get("lines", [])
        source = "preprocess-text(manuscript)"

    if not lines:
        sys.exit("脚本为空")
    print(f"source={source}, lines={len(lines)}")

    body = {"project_id": args.id, "lines": lines,
            "fps": args.fps, "manual_advance": 0.0, "model_name": args.model}
    async for evt in _sse("/api/subtitle-engine/generate-srt", body):
        step = evt.get("step") or evt.get("event")
        pct = evt.get("pct")
        msg = evt.get("message", "")
        print(f"[{step}] {pct or ''}% {msg}".strip())


async def cmd_subtitle_embed(args):
    size = args.size
    if size is None:
        # 自适应：按当前视频分辨率方向选字号（竖屏 10 / 横屏 16）
        try:
            settings = await _get("/api/settings")
            res = settings.get("video_engine", {}).get("resolution", "720x1280")
            w, h = (int(x) for x in res.lower().split("x"))
            size = 10 if w < h else 16
            print(f"auto font_size = {size} (resolution {res}, {'竖屏' if w < h else '横屏'})")
        except Exception:
            size = 10
            print(f"auto font_size fallback = {size} (default vertical)")
    body = {"project_id": args.id, "font_name": args.font, "font_size": size}
    async for evt in _sse("/api/subtitle-engine/embed", body):
        print(f"[{evt.get('step')}] {evt.get('pct','')}% {evt.get('message','')}")


# ── Settings ──────────────────────────────────────────────────────────────────

async def cmd_settings_get(_):
    print(json.dumps(await _get("/api/settings"), ensure_ascii=False, indent=2))


async def cmd_settings_patch(args):
    """读 → 用 JSON 文件中字段覆盖 → 整体写回。"""
    cur = await _get("/api/settings")
    patch = json.loads(Path(args.patch_file).read_text(encoding="utf-8"))
    _deep_merge(cur, patch)
    print(json.dumps(await _post("/api/settings", cur), ensure_ascii=False, indent=2))


def _deep_merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


# ── CLI wiring ────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lumi", description="LumiCreate-Pro client")
    sp = p.add_subparsers(dest="cmd", required=True)

    sp.add_parser("health").set_defaults(func=cmd_health)

    # projects
    pp = sp.add_parser("projects").add_subparsers(dest="sub", required=True)
    pp.add_parser("list").set_defaults(func=cmd_projects_list)
    a = pp.add_parser("new"); a.add_argument("--name", required=True); a.add_argument("--desc"); a.add_argument("--folder"); a.set_defaults(func=cmd_projects_new)
    a = pp.add_parser("info"); a.add_argument("id"); a.set_defaults(func=cmd_projects_info)
    a = pp.add_parser("delete"); a.add_argument("id"); a.add_argument("--yes", action="store_true"); a.set_defaults(func=cmd_projects_delete)

    # manuscript
    mp = sp.add_parser("manuscript").add_subparsers(dest="sub", required=True)
    a = mp.add_parser("get"); a.add_argument("id"); a.set_defaults(func=cmd_manuscript_get)
    a = mp.add_parser("put"); a.add_argument("id"); a.add_argument("--content"); a.add_argument("--content-file"); a.add_argument("--config-file"); a.set_defaults(func=cmd_manuscript_put)
    a = mp.add_parser("generate"); a.add_argument("--config-file", required=True); a.add_argument("--existing"); a.add_argument("--save", help="project_id 直接保存"); a.set_defaults(func=cmd_manuscript_generate)

    # scenes
    scp = sp.add_parser("scenes").add_subparsers(dest="sub", required=True)
    a = scp.add_parser("get"); a.add_argument("id"); a.set_defaults(func=cmd_scenes_get)
    a = scp.add_parser("generate"); a.add_argument("id"); a.add_argument("--save", action="store_true"); a.set_defaults(func=cmd_scenes_generate)
    a = scp.add_parser("split-manual", help="漫剧首选：按句切分 + ≤max-chars 合并 + ≤max-chars-per-scene 角色拆分")
    a.add_argument("id")
    a.add_argument("--max-chars", type=int, default=50, help="单镜字符上限，默认 50 ≈ 12.5s")
    a.add_argument("--max-chars-per-scene", type=int, default=1, help="单镜出镜角色上限，默认 1（本地文生图限制）")
    a.add_argument("--ignore-characters", action="store_true", help="不读 characters.json，退化为纯字数切分")
    a.add_argument("--save", action="store_true")
    a.set_defaults(func=cmd_scenes_split_manual)

    # characters
    cp = sp.add_parser("characters").add_subparsers(dest="sub", required=True)
    a = cp.add_parser("get"); a.add_argument("id"); a.set_defaults(func=cmd_characters_get)
    a = cp.add_parser("profile"); a.add_argument("id"); a.add_argument("--name", required=True); a.add_argument("--role"); a.add_argument("--traits"); a.set_defaults(func=cmd_characters_profile)
    a = cp.add_parser("appearance"); a.add_argument("--name", required=True); a.add_argument("--role"); a.add_argument("--traits"); a.set_defaults(func=cmd_characters_appearance)
    a = cp.add_parser("auto-build", help="漫剧建卡：批量跑 profile + appearance，写入 characters.json")
    a.add_argument("id"); a.add_argument("--names", required=True, help="逗号分隔，例如 '林夏,张川,Boss'")
    a.add_argument("--overwrite-appearance", action="store_true", help="重生成已有 appearance（默认保留）")
    a.set_defaults(func=cmd_characters_auto_build)

    # prompts
    pmp = sp.add_parser("prompts").add_subparsers(dest="sub", required=True)
    a = pmp.add_parser("frame-batch", help="批量生成 start/end frame prompts，自动 hydrate 角色")
    a.add_argument("id")
    a.add_argument("--force", action="store_true", help="覆盖已有 prompt")
    a.add_argument("--allow-empty-appearance", action="store_true", help="允许角色 appearance 为空（仅调试）")
    a.add_argument("--concurrency", type=int, default=0, help="并发数；默认读 settings.text_engine.concurrency")
    a.set_defaults(func=cmd_prompts_frame_batch)
    a = pmp.add_parser("video-batch", help="批量生成视频 positive_prompt，写入 video_prompts.json")
    a.add_argument("id")
    a.add_argument("--force", action="store_true")
    a.add_argument("--concurrency", type=int, default=0, help="并发数；默认读 settings.text_engine.concurrency")
    a.set_defaults(func=cmd_prompts_video_batch)

    # images
    ip = sp.add_parser("images").add_subparsers(dest="sub", required=True)
    a = ip.add_parser("list"); a.add_argument("id"); a.set_defaults(func=cmd_images_list)
    a = ip.add_parser("generate"); a.add_argument("id"); a.add_argument("--workflow", required=True); a.add_argument("--gen-count", type=int, default=1); a.add_argument("--negative"); a.add_argument("--width", type=int, default=0); a.add_argument("--height", type=int, default=0); a.add_argument("--save", action="store_true"); a.add_argument("--skip-check", action="store_true", help="跳过 frame_prompt / appearance 预检"); a.set_defaults(func=cmd_images_generate)

    # audio
    ap = sp.add_parser("audio").add_subparsers(dest="sub", required=True)
    a = ap.add_parser("ms-tts"); a.add_argument("--text", required=True); a.add_argument("--voice", default="zh-CN-XiaoxiaoNeural"); a.add_argument("--rate", default="+25%", help="漫剧默认 +25%（快）"); a.add_argument("--out", required=True); a.add_argument("--save-project", help="同时按 reading 模式 key 写入项目音频"); a.add_argument("--scene-id", help="--save-project 时必填"); a.set_defaults(func=cmd_audio_ms_tts)
    a = ap.add_parser("reading-all", help="漫剧：对项目所有分镜批量 Edge TTS 并按正确 key 保存"); a.add_argument("id"); a.add_argument("--voice", default="zh-CN-XiaoxiaoNeural"); a.add_argument("--rate", default="+25%"); a.set_defaults(func=cmd_audio_reading_all)
    a = ap.add_parser("stitch"); a.add_argument("files", nargs="+"); a.add_argument("--gap-ms", type=int, default=300); a.add_argument("--out", required=True); a.set_defaults(func=cmd_audio_stitch)

    # video
    vp = sp.add_parser("video").add_subparsers(dest="sub", required=True)
    vp.add_parser("workflows").set_defaults(func=cmd_video_workflows)
    a = vp.add_parser("merge"); a.add_argument("id"); a.set_defaults(func=cmd_video_merge)

    # subtitle
    bp = sp.add_parser("subtitle").add_subparsers(dest="sub", required=True)
    a = bp.add_parser("status"); a.add_argument("id"); a.set_defaults(func=cmd_subtitle_status)
    a = bp.add_parser("script"); a.add_argument("id"); a.set_defaults(func=cmd_subtitle_script)
    a = bp.add_parser("generate-srt"); a.add_argument("id"); a.add_argument("--fps", type=int, default=24); a.add_argument("--model", default="base"); a.add_argument("--from-scenes", action="store_true", help="改用分镜聚合脚本（粒度粗，漫剧不推荐）"); a.set_defaults(func=cmd_subtitle_generate_srt)
    a = bp.add_parser("embed"); a.add_argument("id"); a.add_argument("--font", default="等线 Bold"); a.add_argument("--size", type=int, default=None, help="不填则按方向自适应：竖屏 10 / 横屏 16"); a.set_defaults(func=cmd_subtitle_embed)

    # settings
    stp = sp.add_parser("settings").add_subparsers(dest="sub", required=True)
    stp.add_parser("get").set_defaults(func=cmd_settings_get)
    a = stp.add_parser("patch"); a.add_argument("patch_file"); a.set_defaults(func=cmd_settings_patch)

    return p


def main() -> None:
    args = _build_parser().parse_args()
    try:
        asyncio.run(args.func(args))
    except httpx.HTTPStatusError as e:
        print(f"HTTP {e.response.status_code}: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
