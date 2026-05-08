"""Microsoft Edge TTS service via the edge-tts package (no API key required)."""
import base64

import edge_tts


async def synthesise_mp3(text: str, voice: str, rate: str = "+0%") -> bytes:
    """
    Generate speech using a Microsoft Edge neural voice.

    Args:
        text:  The text to speak.
        voice: Microsoft voice name, e.g. "zh-CN-XiaoxiaoNeural".
        rate:  Speed adjustment, e.g. "+0%", "-25%", "+50%".

    Returns:
        Raw MP3 bytes.
    """
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)
