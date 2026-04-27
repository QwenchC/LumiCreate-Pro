"""
IndexTTS-2.0 API 测试脚本
测试两种模式：
  Mode 1: 与音色参考音频相同（仅参考音频决定情绪）
  Mode 2: 使用情感参考音频（单独指定情感音频）
"""

import json
import os
import sys
import tempfile
import time
import urllib.request
import urllib.parse

BASE_URL = "http://localhost:7860"
VOICE_REF  = r"C:\Users\LumiTree\Desktop\audio\reference\male1.mp3"
EMO_REF    = r"C:\Users\LumiTree\Desktop\audio\emotion\angry.wav"
TEST_TEXT  = "你好，这是一段测试语音，用来验证接口是否正常工作。"


# ── 工具函数 ────────────────────────────────────────────────────────────────────

def upload_file(local_path: str) -> dict:
    """上传文件到 Gradio，返回 FileData dict"""
    upload_url = f"{BASE_URL}/gradio_api/upload"
    filename   = os.path.basename(local_path)
    mime       = "audio/mpeg" if local_path.endswith(".mp3") else "audio/wav"

    # 手动构造 multipart/form-data
    boundary = "----LumiCreateBoundary"
    with open(local_path, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        upload_url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    server_path = result[0]
    print(f"  ✓ 上传成功: {filename} → {server_path}")
    return {"path": server_path, "orig_name": filename,
            "meta": {"_type": "gradio.FileData"}}


def call_gen_single(params: list) -> str:
    """调用 /gen_single 端点，返回生成的音频本地路径"""
    # 1. 发起调用
    call_url = f"{BASE_URL}/gradio_api/call/gen_single"
    payload   = json.dumps({"data": params}).encode()
    req = urllib.request.Request(
        call_url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        event_id = json.loads(resp.read())["event_id"]
    print(f"  ✓ 任务已提交，event_id={event_id}")

    # 2. 轮询 SSE 获取结果
    result_url = f"{BASE_URL}/gradio_api/call/gen_single/{event_id}"
    req = urllib.request.Request(result_url, method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if line.startswith("data:"):
                raw_data = line[5:].strip()
                data = json.loads(raw_data)
                if isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    # 结果包在 {"visible": true, "value": {...}} 中
                    file_info = item.get("value") if isinstance(item, dict) and "value" in item else item
                    url = file_info.get("url") or f"{BASE_URL}/gradio_api/file={file_info['path']}"
                    return url
    raise RuntimeError("未收到有效结果")


def download_audio(url: str, out_path: str):
    """下载音频文件"""
    if not url.startswith("http"):
        url = BASE_URL + url
    urllib.request.urlretrieve(url, out_path)
    print(f"  ✓ 音频已保存: {out_path}")


# ── 默认生成参数 ──────────────────────────────────────────────────────────────

DEFAULT_GEN = [
    True,   # do_sample
    0.8,    # top_p
    30,     # top_k
    0.8,    # temperature
    0.0,    # length_penalty
    3,      # num_beams
    10.0,   # repetition_penalty
    1500,   # max_mel_tokens
]


# ── 模式1：与音色参考音频相同 ─────────────────────────────────────────────────

def test_mode1():
    print("\n" + "="*60)
    print("模式1：与音色参考音频相同")
    print("="*60)

    print("正在上传音色参考音频...")
    voice_fd = upload_file(VOICE_REF)

    params = [
        "与音色参考音频相同",  # emo_control_method
        voice_fd,              # prompt（音色参考）
        TEST_TEXT,             # text
        None,                  # emo_ref_path（不需要）
        0.8,                   # emo_weight
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # vec1..vec8
        "",                    # emo_text
        False,                 # emo_random
        120,                   # max_text_tokens_per_sentence
        *DEFAULT_GEN,
    ]

    print("正在生成语音...")
    audio_url = call_gen_single(params)
    download_audio(audio_url, "test_output_mode1.wav")
    print("模式1 测试完成 ✓")


# ── 模式2：使用情感参考音频 ───────────────────────────────────────────────────

def test_mode2():
    print("\n" + "="*60)
    print("模式2：使用情感参考音频（愤怒情绪）")
    print("="*60)

    print("正在上传音色参考音频...")
    voice_fd = upload_file(VOICE_REF)

    print("正在上传情感参考音频...")
    emo_fd = upload_file(EMO_REF)

    params = [
        "使用情感参考音频",  # emo_control_method
        voice_fd,            # prompt（音色参考）
        TEST_TEXT,           # text
        emo_fd,              # emo_ref_path（情感参考）
        0.8,                 # emo_weight（情感权重）
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # vec1..vec8
        "",                  # emo_text
        False,               # emo_random
        120,                 # max_text_tokens_per_sentence
        *DEFAULT_GEN,
    ]

    print("正在生成语音...")
    audio_url = call_gen_single(params)
    download_audio(audio_url, "test_output_mode2.wav")
    print("模式2 测试完成 ✓")


# ── 入口 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"IndexTTS-2.0 API 测试")
    print(f"服务地址: {BASE_URL}")
    print(f"音色参考: {VOICE_REF}")
    print(f"情感参考: {EMO_REF}")

    try:
        test_mode1()
    except Exception as e:
        print(f"  ✗ 模式1 失败: {e}")

    try:
        test_mode2()
    except Exception as e:
        print(f"  ✗ 模式2 失败: {e}")

    print("\n测试完成，输出文件：test_output_mode1.wav / test_output_mode2.wav")
