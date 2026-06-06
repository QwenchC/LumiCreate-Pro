"""一键全流程：把文案→分镜→提示词→图片→音频→视频→字幕→合并 串成一个 SSE 流。

设计：
- 每个 stage 独立可跳过（用 `stages` 字段控制）
- 每个 stage 已有产物时默认 skip（已生成的图片/音频不会重做）
- 失败的 stage 通过 SSE event `stage_error` 报出，整体不中断（继续下一个 stage）
- 全部完成时 emit `pipeline_done`
- 重要约束：图片 / 视频 / 字幕 这些计算密集的阶段依赖外部 ComfyUI 与 ffmpeg —— 调用方需要把 settings 配好

Frontend 消费：HomeView 或项目顶栏加一个"🚀 一键全流程"按钮，open 该 SSE 流。
SKILL: 客户端也可以通过此端点替代 end_to_end_example.py。
"""
import asyncio
import base64
import json
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import load_settings

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

# 顺序很关键：subtitle 依赖 merge 后的 final_video.mp4
DEFAULT_STAGES = ["scenes", "prompts", "images", "audio", "video", "merge", "subtitle"]


class OrchestratorRequest(BaseModel):
    project_id: str
    stages:     list[str] = DEFAULT_STAGES
    # 工作流名（用户在前端选好）
    image_workflow:    str = ""
    video_workflow:    str = ""
    subtitle_font:     str = "等线 Bold"
    subtitle_font_size: int = 0  # 0=按方向自适应（竖屏10 / 横屏16）
    # 分镜策略：
    # - manual_split=False（默认）：调 LLM 的 generate-scenes，**AI 有机分镜**
    #   根据情节/视角/情绪/动作变化自然切分，宁多不少
    # - manual_split=True：纯文本按句切 + 字符上限，机械稳定但忽略语义
    manual_split:      bool = False
    max_chars_per_scene: int = 50    # 仅 manual_split=True 时生效
    rate:              str = "+25%"
    fps:               int = 24


# ── Helpers ────────────────────────────────────────────────────────────────────

API_BASE = "http://127.0.0.1:18520"


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _emit_stage(stage: str, status: str, **extra) -> str:
    return _sse({"event": f"stage_{status}", "stage": stage, **extra})


async def _http_get(client: httpx.AsyncClient, path: str) -> dict:
    r = await client.get(f"{API_BASE}{path}", timeout=120)
    r.raise_for_status()
    return r.json()


async def _http_put(client: httpx.AsyncClient, path: str, payload: dict | list) -> dict:
    r = await client.put(f"{API_BASE}{path}", json=payload, timeout=120)
    r.raise_for_status()
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else {}


async def _http_post(client: httpx.AsyncClient, path: str, payload: dict) -> dict:
    r = await client.post(f"{API_BASE}{path}", json=payload, timeout=300)
    r.raise_for_status()
    return r.json()


async def _stream_sse(client: httpx.AsyncClient, path: str, payload: dict):
    """转发上游 SSE 流；yield 反序列化后的 dict 事件。"""
    async with client.stream("POST", f"{API_BASE}{path}", json=payload, timeout=None) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if raw == "[DONE]":
                return
            try:
                yield json.loads(raw)
            except Exception:
                continue


# ── Manual split (mirrors SKILL/scripts/lumi.py and ScenesTab) ────────────────

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


def _extract_dialogues_for_mode(text: str, mode: str) -> list[dict]:
    import re
    t0 = (text or "").strip()
    if not t0:
        return []
    if mode in ("reading", "narration"):
        return [{"character": "", "text": t0, "emotion": "平静"}]
    dlgs = []
    for m in re.finditer(r"[「“‘\"'](.*?)[」”’\"']", t0, re.DOTALL):
        seg = m.group(1).strip()
        if seg:
            dlgs.append({"character": "", "text": seg, "emotion": "平静"})
    if not dlgs and mode == "mixed":
        return [{"character": "", "text": t0, "emotion": "平静"}]
    return dlgs


def _manual_split(manuscript: str, dialogue_mode: str, max_chars: int,
                  known_names: list[str]) -> list[dict]:
    sentences = _split_sentences(manuscript)
    groups: list[tuple[list[str], set[str]]] = []
    cur: list[str] = []
    cur_len = 0
    cur_chars: set[str] = set()

    def chars_in(s: str) -> set[str]:
        return {n for n in known_names if n and n in s}

    for s in sentences:
        sent_chars = chars_in(s)
        merged = cur_chars | sent_chars
        if cur and (cur_len + len(s) > max_chars or len(merged) > 1):
            groups.append((cur, cur_chars))
            cur, cur_len, cur_chars = [s], len(s), sent_chars
        else:
            cur.append(s); cur_len += len(s); cur_chars = merged
    if cur:
        groups.append((cur, cur_chars))

    scenes = []
    for i, (group, char_set) in enumerate(groups):
        text = "".join(group)
        scenes.append({
            "id": f"scene_{i+1:03d}_manual",
            "index": i + 1,
            "description": text,
            "duration_estimate": max(4, round(len(text) / 5)),
            "start_frame_prompt": "",
            "end_frame_prompt": "",
            "_scene_characters": [n for n in known_names if n in char_set],
            "dialogues": _extract_dialogues_for_mode(text, dialogue_mode),
        })
    return scenes


# ── Stage runners ─────────────────────────────────────────────────────────────


async def _stage_scenes(client: httpx.AsyncClient, req: OrchestratorRequest, ms: dict) -> Optional[list[dict]]:
    """生成分镜（如果不存在）；返回 scenes list。"""
    pid = req.project_id
    existing = await _http_get(client, f"/api/projects/{pid}/scenes")
    scenes = existing.get("scenes") or []
    if scenes:
        return scenes
    mode = (ms.get("config") or {}).get("dialogue_mode") or "mixed"
    chars_data = await _http_get(client, f"/api/projects/{pid}/characters")
    known_names = [c.get("name", "") for c in (chars_data.get("characters") or []) if c.get("name")]
    if req.manual_split:
        scenes = _manual_split(ms.get("content", ""), mode, req.max_chars_per_scene, known_names)
    else:
        # AI 有机分镜：宁多不少，按情节/视角/动作切分。
        # force_llm=True 确保 reading 模式也走 LLM 路径（默认会绕过 LLM）
        sc = await _http_post(client, "/api/text-engine/generate-scenes", {
            "manuscript": ms.get("content", ""),
            "dialogue_mode": mode,
            "characters": (ms.get("config") or {}).get("characters") or [],
            "force_llm": True,
        })
        scenes = sc.get("scenes") or []
    await _http_put(client, f"/api/projects/{pid}/scenes", {"scenes": scenes})
    return scenes


async def _stage_prompts(client: httpx.AsyncClient, req: OrchestratorRequest, scenes: list[dict], ms: dict):
    """对每镜调 generate-frame-prompts；空 prompt 才生成（已生成的跳过）。"""
    pid = req.project_id
    chars = (await _http_get(client, f"/api/projects/{pid}/characters")).get("characters") or []
    chars_by_name = {c.get("name", ""): c for c in chars}

    settings = load_settings()
    concurrency = max(1, min(settings.text_engine.concurrency, 100))
    sem = asyncio.Semaphore(concurrency)
    manuscript = ms.get("content", "")

    async def gen_one(i: int, s: dict):
        if s.get("start_frame_prompt") and s.get("end_frame_prompt"):
            return
        selected = set(s.get("_scene_characters") or [])
        scene_chars = [chars_by_name[n] for n in selected if n in chars_by_name]
        async with sem:
            try:
                r = await _http_post(client, "/api/text-engine/generate-frame-prompts", {
                    "description":  s.get("description", ""),
                    "dialogues":    s.get("dialogues") or [],
                    "characters":   scene_chars,
                    "manuscript":   manuscript,
                    "scene_index":  i + 1,
                    "total_scenes": len(scenes),
                })
                s["start_frame_prompt"] = r.get("start_frame_prompt", "")
                s["end_frame_prompt"]   = r.get("end_frame_prompt", "")
            except Exception as e:
                print(f"[orchestrator] prompts {s.get('id')}: {e}", flush=True)

    await asyncio.gather(*(gen_one(i, s) for i, s in enumerate(scenes)))
    await _http_put(client, f"/api/projects/{pid}/scenes", {"scenes": scenes})


async def _precheck_workflow(workflow_name: str, kind: str) -> tuple[bool, list[dict]]:
    """D2: kind='image' | 'video' — 失败时返回 (False, issues)。"""
    if not workflow_name:
        return True, []
    try:
        from services.comfyui_precheck import (
            precheck_image_workflow, precheck_video_workflow,
        )
        settings = load_settings()
        if kind == "image":
            url = settings.image_engine.comfyui_url
            r = await precheck_image_workflow(url, workflow_name)
        else:
            url = settings.video_engine.comfyui_url
            r = await precheck_video_workflow(url, workflow_name)
        return r.ok, r.issues
    except Exception as e:
        print(f"[precheck {kind} {workflow_name}] {e}", flush=True)
        return True, []   # precheck 自身崩溃不应阻塞主任务


async def _stage_images(client: httpx.AsyncClient, req: OrchestratorRequest, scenes: list[dict]):
    """批量出图 + 逐张落盘到 <项目>/images/。

    ⚠️ image-engine 的 SSE 端点只 yield 事件、不写文件——常规使用时由前端 ImagesTab
    监听 completed 事件并调 PUT /projects/.../images/slot 落盘。orchestrator 跳过了
    前端，所以这里必须自己消费 SSE 把图片写盘 + 维护 images.json metadata。
    """
    if not req.image_workflow:
        raise RuntimeError("image_workflow 未提供")

    # D2: 前置检查（缺节点/缺模型直接告知，不浪费 GPU 时间）
    ok, issues = await _precheck_workflow(req.image_workflow, "image")
    if not ok:
        yield {"event": "precheck_failed", "issues": issues}
        raise RuntimeError(f"image workflow precheck failed: {len(issues)} issue(s)")

    frames = []
    for s in scenes:
        for ft in ("start", "end"):
            prompt = s.get(f"{ft}_frame_prompt")
            if prompt:
                frames.append({"scene_id": s["id"], "frame_type": ft, "prompt": prompt})
    if not frames:
        return

    pid = req.project_id
    counts: dict[str, int]    = {}      # "scene_id:frame_type" -> 当前已落盘张数
    selected: dict[str, int]  = {}      # "scene_id:frame_type" -> 选中的 slot_index（默认第 0 张）
    slot_keys: list[dict]     = []      # [{scene_id, frame_type, slot_index}]
    save_errors = 0

    async for ev in _stream_sse(client, "/api/image-engine/generate-batch-stream", {
        "workflow_name":   req.image_workflow,
        "gen_count":       1,
        "negative_prompt": "",
        "width":  0, "height": 0,
        "frames": frames,
        "project_id": pid,
    }):
        # 透传上游事件给前端日志
        yield ev

        # 仅在 completed 时落盘
        if ev.get("event") != "completed":
            continue
        sid = ev.get("scene_id"); ft = ev.get("frame_type")
        slot_idx = int(ev.get("slot_index") or 0)
        if not sid or not ft:
            continue

        # D1: image_engine 在 project_id 提供时已经自己落盘 + record_asset
        # 事件里若带 file_path，直接用，跳过 PUT base64 一次
        if ev.get("file_path"):
            ck = f"{sid}:{ft}"
            counts[ck] = counts.get(ck, 0) + 1
            slot_keys.append({"scene_id": sid, "frame_type": ft, "slot_index": slot_idx})
            selected.setdefault(ck, slot_idx)
            continue

        # 老路径 fallback：自己 PUT base64
        images = ev.get("images") or []
        first_b64 = (images[0] or {}).get("data") if images else ""
        if not first_b64:
            continue
        try:
            await _http_put(client, f"/api/projects/{pid}/images/slot", {
                "scene_id":   sid,
                "frame_type": ft,
                "slot_index": slot_idx,
                "data":       first_b64,
            })
        except Exception as e:
            save_errors += 1
            print(f"[orch images] save slot {sid}:{ft}:{slot_idx} failed: {e}", flush=True)
            continue

        ck = f"{sid}:{ft}"
        counts[ck] = counts.get(ck, 0) + 1
        slot_keys.append({"scene_id": sid, "frame_type": ft, "slot_index": slot_idx})
        selected.setdefault(ck, slot_idx)   # 第一张落盘的作为默认选中

    # 写 metadata —— 视频阶段会按 selected[sid:start/end] 找图
    try:
        await _http_put(client, f"/api/projects/{pid}/images/metadata", {
            "counts":    counts,
            "selected":  selected,
            "slot_keys": slot_keys,
        })
        yield {"event": "images_metadata_saved", "count": len(slot_keys),
               "errors": save_errors}
    except Exception as e:
        print(f"[orch images] save metadata failed: {e}", flush=True)
        yield {"event": "images_metadata_error", "message": str(e)[:200]}


async def _stage_audio_reading(client: httpx.AsyncClient, req: OrchestratorRequest, scenes: list[dict], ms: dict):
    """漫剧朗读模式：每镜调 ms-tts，按 __ms_reading__ key 增量写入。"""
    pid = req.project_id
    settings = load_settings()
    rate = req.rate or settings.audio_engine.msedge_rate
    voice = settings.audio_engine.msedge_voice or "zh-CN-XiaoxiaoNeural"
    saved = 0
    for s in scenes:
        text = ""
        if s.get("dialogues"):
            text = (s["dialogues"][0] or {}).get("text", "")
        if not text:
            text = s.get("description", "")
        if not text:
            continue
        try:
            r = await _http_post(client, "/api/audio-engine/ms-tts", {
                "text": text, "voice": voice, "rate": rate, "format": "mp3",
            })
            await _http_put(client, f"/api/projects/{pid}/audio/slot", {
                "key":   f"__ms_reading__{s['id']}",
                "entry": {"data": r.get("data", ""), "duration_ms": r.get("duration_ms", 0), "format": "mp3"},
            })
            saved += 1
            yield {"event": "audio_scene_done", "scene_id": s["id"]}
        except Exception as e:
            yield {"event": "audio_scene_error", "scene_id": s["id"], "message": str(e)[:200]}
    yield {"event": "audio_done", "saved": saved}


async def _stage_video(client: httpx.AsyncClient, req: OrchestratorRequest, scenes: list[dict]):
    """对每镜：取 selected 首末帧图片 → b64 + 朗读音频 → b64 → 调 video-engine/generate-stream。
    透传 SSE 给上游；写盘由 video_engine 在 scene_done 后通过前端逻辑完成——这里 orchestrator
    多干一步：每收到 scene_done 就调 /projects/.../videos/slot 保存。"""
    if not req.video_workflow:
        raise RuntimeError("video_workflow 未提供")

    # D2: 前置检查
    ok, issues = await _precheck_workflow(req.video_workflow, "video")
    if not ok:
        yield {"event": "precheck_failed", "issues": issues}
        raise RuntimeError(f"video workflow precheck failed: {len(issues)} issue(s)")

    pid = req.project_id
    # 1) 拉 images metadata（按 scene_id:frame_type 找 selected url）
    img_meta = await _http_get(client, f"/api/projects/{pid}/images")
    slots = img_meta.get("slots") or []
    selected = img_meta.get("selected") or {}
    url_by_key: dict[str, str] = {}
    for s in slots:
        key = f"{s['scene_id']}:{s['frame_type']}:{s['slot_index']}"
        url_by_key[key] = s["url"]

    # D1: 直读磁盘代替 HTTP 自循环。所有图片/音频本来就在本进程的磁盘上，
    #      没必要先 HTTP fetch base64 再 fetch 出来——浪费 RTT + 内存
    def _read_b64_from_disk(rel_path: str) -> str:
        full = Path(load_settings().projects_dir) / pid / rel_path
        return base64.b64encode(full.read_bytes()).decode()

    # 2) 拉 audio：reading 模式按 __ms_reading__{sid} 取 file/data
    audio_state = await _http_get(client, f"/api/projects/{pid}/audio")

    def _audio_for_scene(sid: str) -> tuple[str, int]:
        entry = audio_state.get(f"__ms_reading__{sid}") or {}
        b64 = entry.get("data") or ""
        dur = entry.get("duration_ms") or 4000
        return b64, dur

    # 3) 构造 scenes payload — 直接 io 读 png，不再 HTTP fetch
    scenes_payload = []
    for i, s in enumerate(scenes):
        sid = s["id"]
        start_idx = selected.get(f"{sid}:start", 0)
        end_idx   = selected.get(f"{sid}:end",   0)
        start_url = url_by_key.get(f"{sid}:start:{start_idx}")
        end_url   = url_by_key.get(f"{sid}:end:{end_idx}")
        aud_b64, dur = _audio_for_scene(sid)
        if not (start_url and end_url and aud_b64):
            yield {"event": "scene_error", "scene_id": sid,
                   "message": f"缺少素材：start={bool(start_url)} end={bool(end_url)} audio={bool(aud_b64)}"}
            continue
        # 把 "/api/projects/{pid}/images/file/<filename>" 还原成磁盘相对路径
        # 兼容两种 url 形态：旧的 /images/file/X.png 和新的 /assets/file/...
        try:
            if "/images/file/" in start_url:
                start_rel = "images/" + start_url.split("/images/file/")[1]
                end_rel   = "images/" + end_url.split("/images/file/")[1]
            else:
                # 新 assets 路径不再独立保存文件名，只能 fall back 到 HTTP
                start_rel = end_rel = None
            if start_rel and end_rel:
                start_b64 = _read_b64_from_disk(start_rel)
                end_b64   = _read_b64_from_disk(end_rel)
            else:
                # 兼容路径未识别时的 fallback
                r1 = await client.get(f"{API_BASE}{start_url}"); r1.raise_for_status()
                r2 = await client.get(f"{API_BASE}{end_url}");   r2.raise_for_status()
                start_b64 = base64.b64encode(r1.content).decode()
                end_b64   = base64.b64encode(r2.content).decode()
        except Exception as e:
            yield {"event": "scene_error", "scene_id": sid,
                   "message": f"读取首末帧失败: {e}"}
            continue
        scenes_payload.append({
            "scene_id":        sid,
            "scene_index":     i + 1,
            "start_image_b64": start_b64,
            "end_image_b64":   end_b64,
            "audio_b64":       aud_b64,
            "duration_ms":     dur,
            "positive_prompt": s.get("start_frame_prompt", ""),
        })

    if not scenes_payload:
        yield {"event": "video_skip", "message": "无可生成的镜次（缺图片/音频）"}
        return

    # 4) D1: video_engine 在 project_id 提供时已经自动落盘 + record_asset，
    #        orchestrator 不再调 /videos/slot —— 把那次 PUT base64 节省掉
    async for ev in _stream_sse(client, "/api/video-engine/generate-stream", {
        "workflow_name": req.video_workflow,
        "resolution":    load_settings().video_engine.resolution,
        "fps":           int(req.fps),
        "scenes":        scenes_payload,
        "project_id":    pid,
    }):
        yield ev


async def _stage_subtitle(client: httpx.AsyncClient, req: OrchestratorRequest, ms: dict, resolution_w: int, resolution_h: int):
    """文案 → preprocess-text → generate-srt → embed。前置：需要 video/merge/final_video.mp4。"""
    pid = req.project_id
    # 检查 final_video.mp4 是否存在；不在就 skip（避免上游 400 把整片 pipeline 染红）
    settings = load_settings()
    final_video_path = Path(settings.projects_dir) / pid / "video" / "final_video.mp4"
    if not final_video_path.exists():
        yield {"event": "subtitle_skip",
               "message": "final_video.mp4 不存在，请先勾选 video + merge 阶段或单独跑视频与合并"}
        return

    text = (ms.get("content") or "").strip()
    if not text:
        return
    pre = await _http_post(client, "/api/subtitle-engine/preprocess-text", {"text": text})
    lines = pre.get("lines") or []
    if not lines:
        return
    # 生成 SRT（SSE）
    async for ev in _stream_sse(client, "/api/subtitle-engine/generate-srt", {
        "project_id": pid, "lines": lines, "fps": req.fps,
        "manual_advance": 0.0, "model_name": "base",
    }):
        yield ev

    # 烧字幕：字号按方向自适应
    font_size = req.subtitle_font_size or (10 if resolution_w < resolution_h else 16)
    async for ev in _stream_sse(client, "/api/subtitle-engine/embed", {
        "project_id": pid, "font_name": req.subtitle_font, "font_size": font_size,
    }):
        yield ev


async def _stage_merge(client: httpx.AsyncClient, req: OrchestratorRequest, scenes: list[dict]):
    """合并所有分镜视频。video-engine 的合并端点是非流式 POST /merge-project-video。"""
    pid = req.project_id
    # 需要 scene_order；按 scenes 顺序取 id
    scene_order = [s["id"] for s in scenes]
    if not scene_order:
        yield {"event": "merge_skip", "message": "无分镜可合并"}
        return
    try:
        r = await client.post(f"{API_BASE}/api/video-engine/merge-project-video",
                              json={"project_id": pid, "scene_order": scene_order},
                              timeout=600)
        r.raise_for_status()
        out = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
        yield {"event": "merge_done", "output_path": out.get("output_path","")}
    except httpx.HTTPStatusError as e:
        detail = ""
        try: detail = e.response.json().get("detail", "")
        except Exception: detail = e.response.text[:300]
        yield {"event": "merge_error",
               "message": f"HTTP {e.response.status_code}: {detail}"}


# ── Main entry ─────────────────────────────────────────────────────────────────


@router.post("/generate-all")
async def generate_all(req: OrchestratorRequest):
    """SSE：按顺序跑所有 stage。前端接事件流，实时显示进度。"""

    async def main():
        # E1: 整次 pipeline 起一个根 trace_id；每个 stage 内部再起子 trace_id
        from services.structured_log import use_trace, log_event, new_trace_id
        from services.project_migrate import ensure_migrated
        ensure_migrated(req.project_id)

        async with httpx.AsyncClient(timeout=None) as client:
            pipeline_trace = new_trace_id()
            yield _sse({"event": "pipeline_start", "stages": req.stages,
                        "project_id": req.project_id, "trace_id": pipeline_trace})

            # 提前拉文案 + 分镜元数据
            try:
                ms = await _http_get(client, f"/api/projects/{req.project_id}/manuscript")
            except Exception as e:
                yield _sse({"event": "pipeline_error", "message": f"读取文案失败: {e}"})
                return

            scenes: list[dict] = []

            # A1: 用 SQLite scene.status 跳过已完成的镜次（skip 时不重新生成）
            def _build_status_map() -> dict[str, str]:
                try:
                    from services.project_repo import list_scene_status
                    return {r["id"]: r["status"] for r in list_scene_status(req.project_id)}
                except Exception:
                    return {}

            # 简单的 helper：执行 stage 并自动包 trace_id + 事件日志
            async def run_stage(stage_name: str, runner, *args, count=None):
                """runner 是 async generator；自动透传事件 + 写结构化日志。"""
                with use_trace(stage=stage_name, project_id=req.project_id,
                               trace_id=f"{pipeline_trace}-{stage_name}"):
                    log_event("info", f"{stage_name} start", payload={"count": count})
                    extra = {"count": count} if count is not None else {}
                    yield _emit_stage(stage_name, "start", **extra)
                    try:
                        async for ev in runner(*args):
                            yield _sse({**ev, "stage": stage_name,
                                        "trace_id": f"{pipeline_trace}-{stage_name}"})
                        log_event("info", f"{stage_name} done")
                        yield _emit_stage(stage_name, "done")
                    except Exception as e:
                        log_event("error", f"{stage_name} error: {e}")
                        yield _emit_stage(stage_name, "error", message=str(e)[:300])

            # ── scenes ─────────────────────
            if "scenes" in req.stages:
                with use_trace(stage="scenes", project_id=req.project_id,
                               trace_id=f"{pipeline_trace}-scenes"):
                    yield _emit_stage("scenes", "start")
                    try:
                        scenes = await _stage_scenes(client, req, ms) or []
                        log_event("info", "scenes done", payload={"count": len(scenes)})
                        yield _emit_stage("scenes", "done", count=len(scenes))
                    except Exception as e:
                        log_event("error", f"scenes error: {e}")
                        yield _emit_stage("scenes", "error", message=str(e)[:300])
            else:
                scenes = (await _http_get(client, f"/api/projects/{req.project_id}/scenes")).get("scenes") or []

            # A1: 拉一次状态图，让后续 stage 决定跳过
            status_map = _build_status_map()

            # ── prompts ────────────────────（跳过已 prompted+ 的镜次）
            if "prompts" in req.stages and scenes:
                pending_prompts = [s for s in scenes if status_map.get(s.get("id"), "draft") == "draft"]
                if not pending_prompts:
                    log_event("info", "prompts skip — all scenes already prompted+")
                    yield _emit_stage("prompts", "skipped", message="所有分镜已具备 frame prompt")
                else:
                    with use_trace(stage="prompts", project_id=req.project_id,
                                   trace_id=f"{pipeline_trace}-prompts"):
                        yield _emit_stage("prompts", "start", count=len(pending_prompts))
                        try:
                            await _stage_prompts(client, req, pending_prompts, ms)
                            yield _emit_stage("prompts", "done")
                        except Exception as e:
                            yield _emit_stage("prompts", "error", message=str(e)[:300])
                    status_map = _build_status_map()   # refresh

            # ── images ─────────────────────（跳过已 image_drafted+ 的镜次）
            if "images" in req.stages and scenes:
                pending_images = [
                    s for s in scenes
                    if status_map.get(s.get("id"), "draft") in ("draft", "prompted")
                ]
                if not pending_images:
                    log_event("info", "images skip — all scenes already image_drafted+")
                    yield _emit_stage("images", "skipped", message="所有分镜已有图片")
                else:
                    async for ev in run_stage("images", _stage_images, client, req, pending_images,
                                              count=len(pending_images) * 2):
                        yield ev
                    status_map = _build_status_map()

            # ── audio ──────────────────────（跳过已 audio_ready+ 的镜次）
            if "audio" in req.stages and scenes:
                pending_audio = [
                    s for s in scenes
                    if status_map.get(s.get("id"), "draft") not in
                        ("audio_ready", "video_ready", "finalized")
                ]
                if not pending_audio:
                    log_event("info", "audio skip — all scenes already audio_ready+")
                    yield _emit_stage("audio", "skipped", message="所有分镜已有音频")
                else:
                    async for ev in run_stage("audio", _stage_audio_reading, client, req,
                                              pending_audio, ms,
                                              count=len(pending_audio)):
                        yield ev
                    status_map = _build_status_map()

            # ── video ──────────────────────（跳过已 video_ready+ 的镜次）
            if "video" in req.stages and scenes:
                pending_video = [
                    s for s in scenes
                    if status_map.get(s.get("id"), "draft") not in
                        ("video_ready", "finalized")
                ]
                if not pending_video:
                    log_event("info", "video skip — all scenes already video_ready+")
                    yield _emit_stage("video", "skipped", message="所有分镜已有视频")
                else:
                    async for ev in run_stage("video", _stage_video, client, req, pending_video,
                                              count=len(pending_video)):
                        yield ev

            # ── merge ──────────────────────（必须在 subtitle 之前——subtitle 需要 final_video.mp4）
            if "merge" in req.stages and scenes:
                async for ev in run_stage("merge", _stage_merge, client, req, scenes):
                    yield ev

            # ── subtitle ───────────────────
            if "subtitle" in req.stages:
                w, h = 720, 1280
                try:
                    settings = load_settings()
                    parts = (settings.video_engine.resolution or "720x1280").split("x")
                    w, h = int(parts[0]), int(parts[1])
                except Exception:
                    pass
                with use_trace(stage="subtitle", project_id=req.project_id,
                               trace_id=f"{pipeline_trace}-subtitle"):
                    yield _emit_stage("subtitle", "start")
                try:
                    async for ev in _stage_subtitle(client, req, ms, w, h):
                        yield _sse({**ev, "stage": "subtitle"})
                    yield _emit_stage("subtitle", "done")
                except Exception as e:
                    yield _emit_stage("subtitle", "error", message=str(e)[:300])

            log_event("info", "pipeline done", payload={"trace_id": pipeline_trace})
            yield _sse({"event": "pipeline_done", "trace_id": pipeline_trace})
            yield "data: [DONE]\n\n"

    return StreamingResponse(main(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
