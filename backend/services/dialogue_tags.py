"""v1.5.1: 说话人标注的确定性解析。

100% 可控音色的基石：把"说话人"从"运行时 AI 推断"变成"显式标注 + 确定性解析"。
显式标注行形如：

    张三：你来了。
    @李四：嗯，路上堵车。
    旁白：他擦了擦汗。

`角色名：台词` 是分隔符解析（不是推断）—— 给定角色名单时，只有名单里的名字
（或"旁白/叙述"等叙述别名）才会被当作说话人标签，避免把散文里的冒号
（如"时间：下午"、"心想：…"）误判成标签。
"""
from __future__ import annotations

import re

# 行首可选 @／＠ + 短名字 + 中/英文冒号 + 台词
_TAG_RE = re.compile(r"^[@＠]?\s*([^:：\n]{1,20}?)\s*[:：]\s*(.+?)\s*$")

# 叙述别名 → 视为旁白（character=""）
NARRATION_ALIASES = {"旁白", "叙述", "旁白/默认", "narration", "narrator"}


def _is_narration(name: str) -> bool:
    return name in NARRATION_ALIASES or name.lower() in NARRATION_ALIASES


def parse_speaker_tagged_lines(text: str, known_names=None) -> list[dict]:
    """把多行文本解析成 [{character, text}]。

    - 命中 `角色名：台词` 且角色名在 known_names 内（或 known_names 为空）→ 该说话人
    - 命中叙述别名（旁白/叙述/…）→ character=""（旁白）
    - 其它行（无标签 / 名字不在名单）→ 整行作为旁白 character=""
    """
    known = set(known_names or [])
    out: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _TAG_RE.match(line)
        if m:
            name = m.group(1).strip()
            body = m.group(2).strip()
            if _is_narration(name):
                out.append({"character": "", "text": body})
                continue
            if (not known or name in known) and body:
                out.append({"character": name, "text": body})
                continue
        # 非标签行 → 旁白（保留整行）
        out.append({"character": "", "text": line})
    return out


def has_speaker_tags(text: str, known_names=None) -> bool:
    """文本里是否存在至少一行合法的说话人标签（用于决定走确定性解析还是兜底）。"""
    known = set(known_names or [])
    for raw in (text or "").splitlines():
        m = _TAG_RE.match(raw.strip())
        if not m:
            continue
        name = m.group(1).strip()
        if _is_narration(name):
            return True
        if not known or name in known:
            return True
    return False
