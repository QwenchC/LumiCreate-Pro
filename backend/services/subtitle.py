"""
Subtitle service — align text to video audio using stable_whisper.

Supports 24fps (23.976), 25fps, 30fps (29.97) AI-generated videos.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Generator


# ── Text utilities ─────────────────────────────────────────────────────────────

def preprocess_text(text: str) -> str:
    """将原稿/台词文本转换为字幕格式：按标点断行，每行一句。
    第一步：将断句符号（，。？！：""——及空白）替换为换行
    第二步：反复折叠多余空行，直到只剩单换行"""
    # 第一步：替换断句符号和空白为换行
    text = re.sub(r'[\uff0c\u3002\uff1f\uff01\uff1a\u201c\u201d\u2014\u2026]+|\s+', '\n', text)
    # 第二步：反复折叠连续换行（循环至稳定）
    prev = None
    while prev != text:
        prev = text
        text = text.replace('\n\n', '\n')
    lines = [ln.strip() for ln in text.split('\n')]
    return '\n'.join(ln for ln in lines if ln)


def normalize_text(text: str) -> str:
    """Remove punctuation, keep Chinese characters, letters, digits."""
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text)


# ── FPS helpers ────────────────────────────────────────────────────────────────

_FPS_FILTER = {
    24: 'fps=24000/1001',   # 23.976 — standard for 24fps AI video output
    25: 'fps=25',           # exact PAL
    30: 'fps=30000/1001',   # 29.97 — standard NTSC 30fps
}


def _fps_filter(fps: int) -> str:
    return _FPS_FILTER.get(fps, f'fps={fps}')


# ── ffmpeg helpers ─────────────────────────────────────────────────────────────

def normalize_video(ffmpeg: str, input_video: str, output_video: str, fps: int = 24) -> None:
    """Convert AI video to CFR with correct timebase."""
    cmd = [
        ffmpeg, '-i', input_video,
        '-vf', _fps_filter(fps),
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
        '-af', 'aresample=async=1',
        '-c:a', 'aac', '-ar', '48000',
        '-movflags', '+faststart',
        '-y', output_video,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"视频标准化失败: {result.stderr.decode(errors='replace')[-400:]}")


def extract_audio(ffmpeg: str, video_path: str, audio_path: str) -> None:
    """Extract mono 16kHz WAV from video."""
    cmd = [
        ffmpeg, '-i', video_path,
        '-vn', '-ac', '1', '-acodec', 'pcm_s16le', '-ar', '16000',
        '-y', audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"音频提取失败: {result.stderr.decode(errors='replace')[-400:]}")


def probe_duration(ffprobe: str, path: str) -> float:
    """Return media duration in seconds."""
    cmd = [
        ffprobe, '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    return float(out) if out else 0.0


# libass (used by FFmpeg) requires English font names; Chinese display names won't work.
# Map display name → (libass English name, bold flag)
_FONT_MAP: dict[str, tuple[str, bool]] = {
    '等线 Bold':     ('DengXian', True),
    '等线':          ('DengXian', False),
    '微软雅黑 Bold': ('Microsoft YaHei', True),
    '微软雅黑':      ('Microsoft YaHei', False),
    '黑体':          ('SimHei', False),
    '宋体':          ('SimSun', False),
    '仿宋':          ('FangSong', False),
    '楷体':          ('KaiTi', False),
}


def embed_subtitles(
    ffmpeg: str,
    video_path: str,
    srt_path: str,
    output_path: str,
    font_name: str = '等线 Bold',
    font_size: int = 18,
    ffprobe: str = None,
    force_style: str = "",
) -> Generator[dict, None, None]:
    """Burn SRT subtitles into video, streaming ffmpeg progress events.

    D2: 调用方可传入完整的 force_style 字符串（来自 router）。若为空则用旧的默认样式
    （保留对外行为）。"""
    import threading

    # Get total duration for percentage calculation
    total_ms = 0.0
    if ffprobe:
        try:
            total_ms = probe_duration(ffprobe, video_path) * 1000
        except Exception:
            pass

    srt_escaped = srt_path.replace('\\', '/').replace(':', '\\:')

    if force_style:
        # 调用方已经构造好完整样式串（含 FontName 等），直接用
        # 但 FontName 可能是中文显示名，转成 libass 兼容名
        libass_name, bold = _FONT_MAP.get(font_name, (font_name, False))
        # 把 FontName= 替换成 libass 名
        style_parts = [seg for seg in force_style.split(",") if seg]
        new_parts = []
        for seg in style_parts:
            if seg.startswith("FontName="):
                new_parts.append(f"FontName={libass_name}")
            else:
                new_parts.append(seg)
        style = ",".join(new_parts)
    else:
        # 旧默认样式
        libass_name, bold = _FONT_MAP.get(font_name, (font_name, False))
        bold_val = '1' if bold else '0'
        style = (
            f"Fontname={libass_name},Fontsize={font_size},Bold={bold_val},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=1,Shadow=0,Alignment=2,MarginV=20"
        )
    cmd = [
        ffmpeg, '-i', video_path,
        '-vf', f"subtitles='{srt_escaped}':force_style='{style}'",
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
        '-c:a', 'copy',
        '-progress', 'pipe:1',
        '-nostats',
        '-y', output_path,
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace',
    )

    # Drain stderr in background to prevent pipe buffer deadlock
    stderr_buf: list[str] = []
    def _drain():
        for ln in proc.stderr:
            stderr_buf.append(ln)
    threading.Thread(target=_drain, daemon=True).start()

    try:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith('out_time_ms='):
                try:
                    cur_ms = int(line.split('=', 1)[1])
                    pct = min(99, int(cur_ms / total_ms * 100)) if total_ms > 0 else -1
                    yield {'step': 'progress', 'pct': pct,
                           'message': f'烧录中… {pct}%' if pct >= 0 else '烧录中…'}
                except (ValueError, ZeroDivisionError):
                    pass
        proc.wait()
        if proc.returncode != 0:
            err = ''.join(stderr_buf)[-400:]
            raise RuntimeError(f"字幕嵌入失败: {err}")
        yield {'step': 'done', 'message': '字幕嵌入完成', 'output_path': output_path, 'pct': 100}
    except Exception:
        proc.kill()
        raise


# ── Alignment ─────────────────────────────────────────────────────────────────

def split_by_lines(result, lines: list[str]) -> list[dict]:
    """Map each subtitle line to a timestamp range using stable_whisper word-level timestamps."""
    all_words = []
    for segment in result.segments:
        if hasattr(segment, 'words') and segment.words:
            for word in segment.words:
                if hasattr(word, 'word') and word.word.strip():
                    all_words.append(word)
    if not all_words:
        raise RuntimeError("stable_whisper 未返回单词级时间戳，请检查音频")

    norm_words = []
    word_info = []
    for w in all_words:
        raw = w.word.strip()
        norm = normalize_text(raw)
        if norm:
            norm_words.append(norm)
            word_info.append((raw, w.start, w.end))

    full_norm = ''.join(norm_words)
    total_chars = len(full_norm)

    char_to_word = []
    for i, w in enumerate(norm_words):
        char_to_word.extend([i] * len(w))

    segments = []
    pos = 0

    for idx, line in enumerate(lines):
        line_norm = normalize_text(line)
        if not line_norm:
            continue

        start_idx = full_norm.find(line_norm, pos)
        if start_idx == -1:
            best_pos, best_len = -1, 0
            search_range = min(500, total_chars - pos)
            for i in range(pos, min(pos + search_range, total_chars)):
                match_len = 0
                while (match_len < len(line_norm) and
                       i + match_len < total_chars and
                       line_norm[match_len] == full_norm[i + match_len]):
                    match_len += 1
                if match_len > best_len and match_len >= min(3, len(line_norm) // 2):
                    best_len = match_len
                    best_pos = i
                    if best_len == len(line_norm):
                        break
            if best_pos != -1:
                start_idx = best_pos
            else:
                start_idx = pos

        end_idx = start_idx + len(line_norm)
        if start_idx >= len(char_to_word):
            break
        start_w = char_to_word[start_idx]
        end_w = char_to_word[min(end_idx, len(char_to_word) - 1)]
        start_time = word_info[start_w][1]
        end_time = word_info[end_w][2]

        segments.append({'start': start_time, 'end': end_time, 'text': line.strip()})
        pos = end_idx

    # Pad any missing lines at the end with estimated timestamps
    if len(segments) < len(lines) and segments:
        last_end = segments[-1]['end']
        avg_dur = (last_end - segments[0]['start']) / len(segments)
        for i in range(len(segments), len(lines)):
            new_start = last_end + 0.1
            new_end = new_start + avg_dur
            segments.append({'start': new_start, 'end': new_end, 'text': lines[i].strip()})
            last_end = new_end

    return segments


def fix_overlaps(segments: list[dict], min_gap: float = 0.05) -> list[dict]:
    fixed = []
    prev_end = 0.0
    for seg in segments:
        start = max(seg['start'], prev_end + min_gap)
        end = max(start + 0.2, seg['end'])
        fixed.append({'start': start, 'end': end, 'text': seg['text']})
        prev_end = end
    return fixed


def fmt_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: list[dict], srt_path: str) -> None:
    with open(srt_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n{fmt_time(seg['start'])} --> {fmt_time(seg['end'])}\n{seg['text']}\n\n")


# ── Main generation pipeline ───────────────────────────────────────────────────

def generate_srt(
    ffmpeg: str,
    ffprobe: str,
    video_path: str,
    srt_path: str,
    lines: list[str],
    fps: int = 24,
    manual_advance: float = 0.0,
    model_name: str = 'base',
    fixed_cfr_path: str = None,   # if provided, save normalized video here (persistent)
) -> Generator[dict, None, None]:
    """
    Full pipeline: normalize video → extract audio → align → write SRT.
    Yields progress dicts: {step, message}
    fixed_cfr_path: path to save the CFR-normalized video for later embedding use.
    """
    try:
        import stable_whisper
    except ImportError:
        raise RuntimeError("未安装 stable_whisper，请运行: pip install stable-ts")

    tmp_dir = tempfile.mkdtemp(prefix='lumi_sub_')
    # Use the persistent path if provided, otherwise put in temp dir
    fixed_video = fixed_cfr_path if fixed_cfr_path else os.path.join(tmp_dir, 'fixed_cfr.mp4')
    audio_wav   = os.path.join(tmp_dir, 'audio.wav')

    try:
        yield {'step': 'normalize', 'message': f'标准化视频帧率（目标 {fps}fps）…', 'pct': 5}
        normalize_video(ffmpeg, video_path, fixed_video, fps)

        video_duration = probe_duration(ffprobe, fixed_video)
        yield {'step': 'audio', 'message': f'提取音频（视频时长 {video_duration:.1f}s）…', 'pct': 20}
        extract_audio(ffmpeg, fixed_video, audio_wav)

        wav_duration = probe_duration(ffprobe, audio_wav)
        time_scale = video_duration / wav_duration if wav_duration > 0 else 1.0
        yield {'step': 'align', 'message': f'加载 Whisper 模型（{model_name}）…', 'pct': 30}
        model = stable_whisper.load_model(model_name)
        yield {'step': 'align_running', 'message': '音频对齐中（可能需要数分钟）…', 'pct': -1}
        full_text = '\n'.join(lines)
        result = model.align(audio_wav, full_text, language='zh')

        yield {'step': 'split', 'message': '按行切分时间戳…', 'pct': 85}
        segments = split_by_lines(result, lines)

        # Scale timestamps from wav timeline to video timeline
        if abs(time_scale - 1.0) > 0.0001:
            for seg in segments:
                seg['start'] *= time_scale
                seg['end']   *= time_scale

        segments = fix_overlaps(segments, min_gap=0.05)

        # Auto-shift: start from 0
        auto_shift = -segments[0]['start'] if segments else 0.0
        total_shift = auto_shift - manual_advance

        SAFE_MARGIN = 0.18
        max_end = max(0.0, video_duration - SAFE_MARGIN)

        for seg in segments:
            seg['start'] = max(0.0, seg['start'] + total_shift)
            seg['end']   = max(seg['start'] + 0.1, seg['end'] + total_shift)

        if segments:
            segments[-1]['end'] = min(segments[-1]['end'], max_end)
            if segments[-1]['end'] - segments[-1]['start'] < 0.2:
                segments[-1]['start'] = max(0.0, max_end - 0.2)

        for seg in segments:
            seg['end'] = min(seg['end'], max_end)

        yield {'step': 'write', 'message': f'写入 SRT（共 {len(segments)} 条字幕）…', 'pct': 95}
        write_srt(segments, srt_path)

        yield {'step': 'done', 'message': 'SRT 生成完成', 'count': len(segments),
               'fixed_cfr_path': fixed_video, 'pct': 100}

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
