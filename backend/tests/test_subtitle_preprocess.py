"""subtitle.preprocess_text 是字幕生成的标准首步——必须按所有定义的标点切行。"""
from services.subtitle import preprocess_text


def test_splits_by_chinese_punctuation():
    out = preprocess_text("她回头，看见月光下的剑。")
    assert out.splitlines() == ["她回头", "看见月光下的剑"]


def test_collapses_consecutive_separators():
    out = preprocess_text("第一句，，，第二句")
    assert out.splitlines() == ["第一句", "第二句"]


def test_handles_quotes_and_dash():
    # 用 “ / ” 显式拼，避免被编辑器误转成 ASCII 引号
    text = "他说“走吧”——然后转身离去"
    out = preprocess_text(text)
    lines = out.splitlines()
    # “ ” — 均在 preprocess 切分集合内
    assert "走吧" in lines, lines
    assert any("转身离去" in l for l in lines), lines


def test_strips_whitespace_only_segments():
    out = preprocess_text("hello\n\n  \n   world")
    assert out.splitlines() == ["hello", "world"]


def test_empty_input():
    assert preprocess_text("") == ""
    assert preprocess_text("   \n\n  ") == ""
