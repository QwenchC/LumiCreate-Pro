"""v1.4.6: 图片放映视频生成（不走 AI 视频生成模型）。

为没 GPU 或不想跑 LTX-2.3 的用户准备的轻量路线：
  - 按分镜顺序逐个播放分镜图片 + 音频
  - 每个分镜时长 = 该分镜音频时长
  - 1 张图：静帧贴满整段音频
  - 2 张图：前半段 → 转场 → 后半段（图1淡出，图2淡入）
  - 镜次之间也可加转场（fade / slide / wipe 等，复用 merge-project-video 的 xfade 通道）

输出目录与 LTX 路径一致：
  <project>/video/<scene_id>.mp4   # 每镜单独 mp4
  <project>/video/final_video.mp4  # 合并后的成片（merge 阶段产出）
  <project>/videos.json            # scene_id → filename 映射（与 LTX 同 schema）
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


# ── 资源解析（从 scene_assets / 文件系统）─────────────────────────────────────


def _abs_asset(proj_dir: Path, rel_path: str) -> Optional[Path]:
    """把 scene_assets.file_path（相对路径）解析为绝对路径，文件不存在返 None。"""
    if not rel_path: return None
    p = proj_dir / rel_path
    return p if p.is_file() else None


def _resolve_scene_assets(
    project_id: str, proj_dir: Path,
    scene_id: str, *,
    use_end_frame: bool = True,
) -> dict:
    """返回 {start_image, end_image|None, audio|None, duration_ms}。"""
    from services.db import get_conn
    conn = get_conn(project_id)
    rows = conn.execute(
        "SELECT asset_type, slot_index, file_path, metadata_json, is_selected "
        "FROM scene_assets WHERE scene_id = ? "
        "ORDER BY asset_type, is_selected DESC, slot_index ASC",
        (scene_id,),
    ).fetchall()
    out = {"start_image": None, "end_image": None, "audio": None, "duration_ms": 0}
    seen_types: set = set()
    for r in rows:
        t = r["asset_type"]
        if t in seen_types: continue   # 同类型按 is_selected DESC 先到的为准
        path = _abs_asset(proj_dir, r["file_path"])
        if path is None: continue
        if t == "image_start":
            out["start_image"] = path; seen_types.add(t)
        elif t == "image_end" and use_end_frame:
            out["end_image"]   = path; seen_types.add(t)
        elif t == "audio":
            out["audio"] = path
            try:
                meta = json.loads(r["metadata_json"] or "{}")
                out["duration_ms"] = int(meta.get("duration_ms") or 0)
            except Exception:
                out["duration_ms"] = 0
            seen_types.add(t)
    return out


# ── ffprobe 时长兜底 ───────────────────────────────────────────────────────────


def _ffprobe_audio_duration_ms(ffmpeg_path: str, audio_path: Path) -> int:
    import shutil as _sh
    ffprobe = _sh.which("ffprobe") or str(Path(ffmpeg_path).parent / "ffprobe.exe")
    if not Path(ffprobe).is_file():
        ffprobe = "ffprobe"
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, timeout=15,
        )
        if out.returncode == 0:
            secs = float((out.stdout or b"").decode().strip() or "0")
            return int(secs * 1000)
    except Exception:
        pass
    return 0


# ── 单分镜渲染 ────────────────────────────────────────────────────────────────


# 转场预设映射到 ffmpeg xfade transition 名
TRANSITIONS = {
    "fade":         "fade",          # 默认：交叉淡入淡出
    "fadeblack":    "fadeblack",     # 经黑
    "fadewhite":    "fadewhite",     # 经白
    "slideleft":    "slideleft",
    "slideright":   "slideright",
    "slideup":      "slideup",
    "slidedown":    "slidedown",
    "wipeleft":     "wipeleft",
    "wiperight":    "wiperight",
    "zoomin":       "zoomin",
    "dissolve":     "dissolve",
}

# 画面动态（Ken Burns）预设
MOTION_EFFECTS = ("none", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down")


def _build_image_vf_chain(W: int, H: int, duration_s: float, fps: int, motion: str) -> str:
    """构造一段 -vf / filter_complex 里把"一张静图"变成"WxH 视频流"的 filter 链。

    - motion='none'：纯 scale + pad（黑边居中，最大兼容）
    - 其它：**预缩放到 4× 目标尺寸 + lanczos**，再 zoompan 在大画布上做 Ken Burns，
      最后下采样到 WxH —— 高分辨率采样让 zoompan 的整数像素抖动被下采样平均掉，
      画面看上去丝滑无震动。

    v1.4.6+ 抖动修复：之前是 1.2× 预缩放，zoompan 每帧 zoom 增量映射到目标分辨率
    时落在亚像素位置，ffmpeg 强制取整 → 帧间"震动"。改 4× lanczos 后单像素增量
    对应 0.25 输出像素 —— 远低于人眼可察的临界。
    """
    frames = max(2, int(round(duration_s * fps)))   # zoompan d 至少 2
    if motion in (None, "", "none") or motion not in MOTION_EFFECTS:
        return (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )

    # 4× lanczos 预缩放画布 —— 关键防抖技术
    BW, BH = int(W * 4), int(H * 4)
    pre = (
        f"scale={BW}:{BH}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={BW}:{BH}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )
    # zoompan 缩放量：5s@25fps 推 ~10%（视觉舒适且能看出运动）
    z_step = 0.0008
    z_max  = 1.0 + z_step * frames
    z_in  = f"1.0+{z_step}*on"
    z_out = f"{z_max:.4f}-{z_step}*on"
    cx = "(iw-iw/zoom)/2"
    cy = "(ih-ih/zoom)/2"

    if motion == "zoom_in":
        zp = f"zoompan=z='{z_in}':x='{cx}':y='{cy}':d={frames}:s={W}x{H}:fps={fps}"
    elif motion == "zoom_out":
        zp = f"zoompan=z='{z_out}':x='{cx}':y='{cy}':d={frames}:s={W}x{H}:fps={fps}"
    elif motion == "pan_left":
        # zoom 固定 1.1，x 从右到左
        x_expr = f"iw-iw/zoom-(iw-iw/zoom)*on/{frames}"
        zp = f"zoompan=z=1.1:x='{x_expr}':y='{cy}':d={frames}:s={W}x{H}:fps={fps}"
    elif motion == "pan_right":
        x_expr = f"(iw-iw/zoom)*on/{frames}"
        zp = f"zoompan=z=1.1:x='{x_expr}':y='{cy}':d={frames}:s={W}x{H}:fps={fps}"
    elif motion == "pan_up":
        y_expr = f"ih-ih/zoom-(ih-ih/zoom)*on/{frames}"
        zp = f"zoompan=z=1.1:x='{cx}':y='{y_expr}':d={frames}:s={W}x{H}:fps={fps}"
    elif motion == "pan_down":
        y_expr = f"(ih-ih/zoom)*on/{frames}"
        zp = f"zoompan=z=1.1:x='{cx}':y='{y_expr}':d={frames}:s={W}x{H}:fps={fps}"
    else:
        return (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
    # zoompan 输出会重置 SAR → 在链路末尾再 setsar=1 + 强制 yuv420p，避免
    # Windows 播放器拿到非方像素或 yuv444 报"编码设置不受支持"
    return pre + "," + zp + ",setsar=1,format=yuv420p"


def _build_sfx_audio_fc(main_audio_label: str,
                         sfx_overlays: list[dict],
                         start_input_idx: int) -> tuple[str, list[str]]:
    """构造 SFX 音频 filter_complex 片段。

    Args:
        main_audio_label: 主音轨在 fc 中的标签（如 "[1:a]" 或 "[a_main]"），
            会被先做 aresample 再参与 amix
        sfx_overlays: [{"path": Path, "offset_ms": int, "volume_db": float}, ...]
        start_input_idx: 第一个 SFX 在 ffmpeg `-i` 序列里的索引

    Returns:
        (filter_complex_segment, output_label)
        - filter_complex 字符串片段（用 ; 分隔的多个节点）
        - amix 输出标签 "[aout]"
    """
    parts = [f"{main_audio_label}aresample=async=1000:first_pts=0[a_main]"]
    sfx_labels: list[str] = []
    for i, ov in enumerate(sfx_overlays):
        idx = start_input_idx + i
        offset = max(0, int(ov.get("offset_ms") or 0))
        vol    = float(ov.get("volume_db") or 0.0)
        lbl = f"[sfx{i}]"
        # adelay 需要 per-channel 列表（用 | 分隔），stereo 给两次
        # volume 节点用 dB 单位
        parts.append(f"[{idx}:a]adelay={offset}|{offset},volume={vol}dB{lbl}")
        sfx_labels.append(lbl)
    # amix: 主音轨 + N 个 SFX；duration=first 让总长 = 主音轨长度（不被 SFX 拖长）
    inputs_chain = "[a_main]" + "".join(sfx_labels)
    n = 1 + len(sfx_labels)
    parts.append(
        f"{inputs_chain}amix=inputs={n}:duration=first:dropout_transition=0[aout]"
    )
    return ";".join(parts), "[aout]"


def build_scene_clip_cmd(
    ffmpeg_path: str, *,
    start_image: Path,
    end_image:   Optional[Path],
    audio:       Optional[Path],
    duration_ms: int,
    output_path: Path,
    width:       int,
    height:      int,
    fps:         int,
    intra_transition:    str = "fade",
    intra_transition_ms: int = 800,
    motion_effect:       str = "none",
    sfx_overlays:        Optional[list[dict]] = None,
) -> list[str]:
    """构造单分镜的 ffmpeg 命令。

    1 张图 + 音频：图片静帧贴满音频，可加 Ken Burns 动态
    2 张图 + 音频：图1 前半 → 转场 → 图2 后半，每张图各自独立动态
    无音频：按 duration_ms（< 1000 时回落 4000ms）渲染（仍无声轨）

    v1.4.6+: 所有输出加 `-movflags +faststart` —— 把 moov atom 放文件开头，
    Windows Media Player / 系统播放器才能播放（之前默认放末尾，仅浏览器/VLC 能流式读）。
    """
    duration_s = max(0.5, duration_ms / 1000.0)

    # 已识别的动态选项才走 filter_complex；未识别 / none 一律走 -vf 静态路径
    has_motion = motion_effect in MOTION_EFFECTS and motion_effect != "none"

    # v1.4.6+ 编码配置 —— **极保守**以匹配 Windows Media Player / Movies & TV：
    #   - profile=main + level=4.0：去掉 High profile 的 8x8 变换等特性，
    #     老硬解 / DXVA 也能播
    #   - preset=fast：veryfast 比这个再快 ~20% 但有时产出"编码设置不受支持"
    #   - 不用 -tune stillimage：tune 会改 motion estimation 参数，
    #     部分播放器无法处理
    #   - bt709 颜色空间显式打标，避免播放器猜错色域出现偏色或拒播
    _ENCODE_SAFE = [
        "-c:v", "libx264",
        "-profile:v", "main", "-level", "4.0",
        "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-colorspace",      "bt709",
        "-color_primaries", "bt709",
        "-color_trc",       "bt709",
        # v1.4.6++ WMP 拒播的第二根因：bitrate 太高（用户主诉"数据速率和总比特率
        # 过高"）。H.264 Level 4.0 在 Main profile 下的硬上限是 ~25Mbps，CRF=20
        # 配 1080p25 + Ken Burns 高频细节，可能瞬时冲到 30+Mbps → WMP 直接拒播。
        # 强制 maxrate 8M + bufsize 16M 让所有窗口都在合规线下，再保险。
        "-maxrate", "8M", "-bufsize", "16M",
        # v1.4.6+ WMP 关键：每镜 mp4 用相同的 video_track_timescale。
        # 单图分支走 -vf（默认 timebase=1/fps），动态分支走 zoompan(filter_complex)
        # 会重置 timebase —— 两者一起 concat -c copy 时 mvhd timescale 不一致 →
        # WMP 拒播。统一成 90kHz（MPEG-TS 标准）后所有镜次 mp4 头一致，concat 干净。
        "-video_track_timescale", "90000",
        # 强制 CFR + 关键帧节奏（每秒 1 个 IDR），便于 concat 边界对齐
        "-vsync", "cfr",
        "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
        "-movflags", "+faststart",
    ]

    # **始终注入音轨**：用 anullsrc 当无音频时的静音 AAC，让所有镜次的 mp4 流布局
    # 一致（视频+音频），concat -c copy 才不会因为流不匹配产出损坏 mp4。
    # 这是 Windows 播放器"编码设置不受支持"的另一常见诱因。
    _AUDIO_INPUT_SILENT = [
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
    ]

    # 1 张图（或没有 end_image）
    if end_image is None:
        vf = _build_image_vf_chain(width, height, duration_s, fps, motion_effect)
        cmd = [
            ffmpeg_path, "-y",
            "-loop", "1", "-framerate", str(fps),
            "-t", f"{duration_s:.3f}", "-i", str(start_image),
        ]
        if audio is not None:
            cmd += ["-i", str(audio)]
        else:
            cmd += _AUDIO_INPUT_SILENT
        # v1.4.8 SFX 路径：有叠加音效时把视频+音频统一压进 filter_complex（adelay+
        # volume+amix 必须在 fc 里跑），并把 SFX 文件追加为额外 -i 输入。
        if sfx_overlays:
            for ov in sfx_overlays:
                cmd += ["-i", str(ov["path"])]
            audio_fc, aout = _build_sfx_audio_fc(
                main_audio_label="[1:a]",
                sfx_overlays=sfx_overlays,
                start_input_idx=2,   # 0=image, 1=audio, 2..=sfx
            )
            video_fc = f"[0:v]{vf}[vout]"
            cmd += ["-filter_complex", f"{video_fc};{audio_fc}",
                    "-map", "[vout]", "-map", aout]
            cmd += _ENCODE_SAFE
            cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                    "-t", f"{duration_s:.3f}"]
            cmd += [str(output_path)]
            return cmd
        # 动态模式用 filter_complex（因为 zoompan 自带 fps），静态可走 -vf
        if not has_motion:
            cmd += ["-vf", vf, "-r", str(fps), "-map", "0:v:0"]
        else:
            cmd += ["-filter_complex", f"[0:v]{vf}[vout]", "-map", "[vout]"]
        cmd += _ENCODE_SAFE
        # v1.4.6++ A/V sync 修复：用户主诉 10min 视频音频比视频早 1min 结束。
        # 真因：每镜次音频比视频差 50-100ms 因 AAC 编码器 priming + -shortest
        # 截断，累积 200+ 镜次 → 60s drift。两手并用：
        #   (a) `-af aresample=async=1000:first_pts=0` 让重采样器在每镜次起点
        #       补 priming 静音 + 拉平到目标采样率（同时把任何 TTS 怪采样率
        #       —— 22050/24000/32000 —— 统一成 48k）
        #   (b) 用显式 `-t duration_s` 取代 `-shortest`：音视频末尾都被裁到完
        #       全相同的时间戳，concat 边界不会留任何"音频少一点"的窟窿
        # 48kHz 与下游 merge/burn 的 `-ar 48000` 对齐 → 全链路无重采样
        cmd += ["-map", "1:a:0",
                "-af", "aresample=async=1000:first_pts=0",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-t", f"{duration_s:.3f}"]
        cmd += [str(output_path)]
        return cmd

    # 2 张图：xfade（每张图都套自己的 Ken Burns）
    transition = TRANSITIONS.get(intra_transition, "fade")
    xfd  = max(0.1, intra_transition_ms / 1000.0)        # 转场时长
    # 单图持续时间：让总长 = duration_s；公式 t = (D + xfd) / 2
    each = (duration_s + xfd) / 2.0
    # offset = each - xfd（xfade 开始的秒）
    offset = max(0.0, each - xfd)

    vf_a = _build_image_vf_chain(width, height, each, fps, motion_effect)
    vf_b = _build_image_vf_chain(width, height, each, fps, motion_effect)

    cmd = [
        ffmpeg_path, "-y",
        "-loop", "1", "-framerate", str(fps),
        "-t", f"{each:.3f}", "-i", str(start_image),
        "-loop", "1", "-framerate", str(fps),
        "-t", f"{each:.3f}", "-i", str(end_image),
    ]
    if audio is not None:
        cmd += ["-i", str(audio)]
    else:
        cmd += _AUDIO_INPUT_SILENT
    fc_video = (
        f"[0:v]{vf_a}[v0];"
        f"[1:v]{vf_b}[v1];"
        f"[v0][v1]xfade=transition={transition}:duration={xfd:.3f}:offset={offset:.3f}[vout]"
    )
    # v1.4.8 SFX：2 图分支同样接 SFX —— 把 fc 拼成 video+audio 一整段
    if sfx_overlays:
        for ov in sfx_overlays:
            cmd += ["-i", str(ov["path"])]
        audio_fc, aout = _build_sfx_audio_fc(
            main_audio_label="[2:a]",
            sfx_overlays=sfx_overlays,
            start_input_idx=3,   # 0,1=images, 2=audio, 3..=sfx
        )
        cmd += ["-filter_complex", f"{fc_video};{audio_fc}",
                "-map", "[vout]", "-map", aout,
                "-r", str(fps), *_ENCODE_SAFE]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-t", f"{duration_s:.3f}"]
        cmd += [str(output_path)]
        return cmd
    cmd += ["-filter_complex", fc_video,
            "-map", "[vout]",
            "-r", str(fps), *_ENCODE_SAFE]
    # v1.4.6++ 同 1 图分支：aresample async + 显式 -t（避免 -shortest 的截断累积）
    cmd += ["-map", "2:a:0",
            "-af", "aresample=async=1000:first_pts=0",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", f"{duration_s:.3f}"]
    cmd += [str(output_path)]
    return cmd


# ── 整片渲染（per-scene 子片 + 落盘 videos.json）──────────────────────────────


def _suggest_parallel_workers() -> int:
    """根据 CPU 核数推荐并行数。

    单 ffmpeg+libx264 已经吃 4-6 核；多开太多会争抢。
    经验：核数 / 4，cap 在 [1, 4]。
    16 核机器 → 4 并行；8 核 → 2 并行；4 核以下 → 1。
    """
    import os as _os
    try:
        n = _os.cpu_count() or 4
    except Exception:
        n = 4
    return max(1, min(n // 4, 4))


def _load_sfx_timeline(proj_dir: Path) -> dict[str, list[dict]]:
    """读 <project>/sfx_timeline.json 并把 sfx_id 解析成 path（用全局 SFX 库）。

    返回 {scene_id: [{path, offset_ms, volume_db}, ...]}。SFX 缺失则跳过该条。
    """
    p = proj_dir / "sfx_timeline.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}

    from services.db import get_global_sfx_conn, global_sfx_root
    conn = get_global_sfx_conn()
    root = global_sfx_root()

    # 一次性把所有 sfx_id 拉出来，避免逐条查
    all_ids: set = set()
    for items in raw.values():
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and isinstance(it.get("sfx_id"), int):
                    all_ids.add(it["sfx_id"])
    if not all_ids:
        return {}
    placeholders = ",".join("?" * len(all_ids))
    rows = conn.execute(
        f"SELECT id, file_path FROM sfx_clips WHERE id IN ({placeholders})",
        list(all_ids),
    ).fetchall()
    id_to_path: dict[int, Path] = {}
    for r in rows:
        abs_p = root / r["file_path"]
        if abs_p.is_file():
            id_to_path[int(r["id"])] = abs_p

    out: dict[str, list[dict]] = {}
    for sid, items in raw.items():
        if not isinstance(items, list): continue
        resolved: list[dict] = []
        for it in items:
            if not isinstance(it, dict): continue
            sfx_id = it.get("sfx_id")
            path   = id_to_path.get(int(sfx_id)) if isinstance(sfx_id, int) else None
            if path is None: continue   # SFX 已删，静默跳过
            resolved.append({
                "path":      path,
                "offset_ms": max(0, int(it.get("offset_ms") or 0)),
                "volume_db": float(it.get("volume_db") or 0.0),
            })
        if resolved:
            out[sid] = resolved
    return out


def render_slideshow_project(
    project_id: str, *,
    proj_dir:    Path,
    scene_order: list[str],
    ffmpeg_path: str,
    width:       int,
    height:      int,
    fps:         int = 25,
    intra_transition:    str = "fade",
    intra_transition_ms: int = 800,
    default_no_audio_ms: int = 4000,
    motion_effect:       str = "none",
    parallel:            int = 0,    # 0 = 自动按 CPU 核数；1 = 顺序；>1 = 显式
) -> dict:
    """N 个分镜并行渲染 mp4 子片到 <project>/video/，更新 videos.json。

    返回 {ok, rendered, skipped, errors, output_dir, scene_files, parallel_workers}。
    """
    vdir = proj_dir / "video"
    vdir.mkdir(parents=True, exist_ok=True)
    meta_path = proj_dir / "videos.json"

    # 读现有 videos.json（增量更新，不抹掉用户已有的 LTX 视频）
    try:
        existing: dict = json.loads(meta_path.read_text(encoding="utf-8-sig")) \
            if meta_path.exists() else {}
    except Exception:
        existing = {}

    rendered: list[str] = []
    skipped:  list[dict] = []
    errors:   list[dict] = []
    scene_files: dict[str, str] = dict(existing)

    # v1.4.8: 读项目级 SFX 时间轴（{scene_id: [{path, offset_ms, volume_db}, ...]}）
    sfx_by_scene = _load_sfx_timeline(proj_dir)

    # 阶段 1：解析所有分镜的资产 + 算 duration（串行，纯 I/O，飞快）
    tasks: list[dict] = []   # {sid, start_img, end_img, audio, dur_ms, out_path, sfx}
    for sid in scene_order:
        assets = _resolve_scene_assets(project_id, proj_dir, sid)
        start_img = assets["start_image"]
        end_img   = assets["end_image"]
        audio     = assets["audio"]

        if start_img is None:
            skipped.append({"scene_id": sid, "reason": "缺首帧图"})
            continue

        # v1.4.6+ 音画同步修复：**总是用 ffprobe 取真实音频时长**，不信任 SQLite
        # metadata 里的 duration_ms（那是 TTS 请求时的"目标"时长，实际产出的 MP3
        # 比目标长 / 短几十至几百毫秒很常见）。
        # 之前用 metadata 值 → 用户主诉"音频早早放完字幕还在跑"——是因为视频被
        # 我们 `-t metadata_ms` 截断了，而字幕是按实际音频时长烧的。
        dur_ms = 0
        if audio is not None:
            dur_ms = _ffprobe_audio_duration_ms(ffmpeg_path, audio)
        if not dur_ms or dur_ms <= 0:
            dur_ms = assets["duration_ms"]   # 兜底
        if not dur_ms or dur_ms <= 0:
            dur_ms = default_no_audio_ms

        tasks.append({
            "sid": sid, "start_img": start_img, "end_img": end_img,
            "audio": audio, "dur_ms": dur_ms,
            "out_name": f"{sid}.mp4",
            "out_path": vdir / f"{sid}.mp4",
            "sfx_overlays": sfx_by_scene.get(sid) or [],
        })

    # 阶段 2：并行跑 ffmpeg
    workers = parallel if parallel and parallel > 0 else _suggest_parallel_workers()
    workers = max(1, min(workers, len(tasks), 8))

    def _run_one(t: dict) -> tuple[str, Optional[str]]:
        """返回 (scene_id, error_msg|None)。error_msg=None 表示成功。"""
        cmd = build_scene_clip_cmd(
            ffmpeg_path,
            start_image=t["start_img"],
            end_image=t["end_img"],
            audio=t["audio"],
            duration_ms=t["dur_ms"],
            output_path=t["out_path"],
            width=width, height=height, fps=fps,
            intra_transition=intra_transition,
            intra_transition_ms=intra_transition_ms,
            motion_effect=motion_effect,
            sfx_overlays=t.get("sfx_overlays") or None,
        )
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=600)
            if r.returncode != 0:
                err = (r.stderr or b"").decode(errors="replace")[-400:]
                return t["sid"], f"ffmpeg 失败: {err}"
            return t["sid"], None
        except subprocess.TimeoutExpired:
            return t["sid"], "ffmpeg 超时（>10min）"
        except Exception as e:
            return t["sid"], str(e)

    if workers <= 1:
        # 顺序路径（用于测试 + 单核机器）
        for t in tasks:
            sid, err = _run_one(t)
            if err is None:
                rendered.append(sid); scene_files[sid] = t["out_name"]
            else:
                errors.append({"scene_id": sid, "message": err})
    else:
        # 并行路径：ThreadPoolExecutor + map 保顺序
        from concurrent.futures import ThreadPoolExecutor
        sid_to_outname = {t["sid"]: t["out_name"] for t in tasks}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for sid, err in pool.map(_run_one, tasks):
                if err is None:
                    rendered.append(sid); scene_files[sid] = sid_to_outname[sid]
                else:
                    errors.append({"scene_id": sid, "message": err})

    # 写 videos.json
    meta_path.write_text(
        json.dumps(scene_files, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 同步 scene_assets 表（让现有 record_asset 流程接得上）
    try:
        from services.project_repo import record_asset
        for sid in rendered:
            record_asset(
                project_id, sid, "video",
                slot_index=0,
                file_path=f"video/{scene_files[sid]}",
                format="mp4", is_selected=True,
            )
    except Exception as e:
        print(f"[slideshow] record_asset failed: {e}", flush=True)

    return {
        "ok": not errors,
        "rendered": rendered,
        "skipped":  skipped,
        "errors":   errors,
        "output_dir": str(vdir),
        "scene_files": scene_files,
        "parallel_workers": workers,
    }
