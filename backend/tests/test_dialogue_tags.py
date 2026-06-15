"""v1.5.1: 说话人标注确定性解析测试。"""
from services.dialogue_tags import parse_speaker_tagged_lines, has_speaker_tags


ROSTER = ["张三", "李四"]


def test_parse_basic_tags():
    text = "张三：你来了。\n李四：嗯，路上堵车。"
    out = parse_speaker_tagged_lines(text, ROSTER)
    assert out == [
        {"character": "张三", "text": "你来了。"},
        {"character": "李四", "text": "嗯，路上堵车。"},
    ]


def test_at_prefix_and_fullwidth_colon():
    text = "@张三：台词A\n＠李四：台词B"
    out = parse_speaker_tagged_lines(text, ROSTER)
    assert [d["character"] for d in out] == ["张三", "李四"]
    assert [d["text"] for d in out] == ["台词A", "台词B"]


def test_narration_alias_maps_to_empty():
    out = parse_speaker_tagged_lines("旁白：他擦了擦汗。", ROSTER)
    assert out == [{"character": "", "text": "他擦了擦汗。"}]


def test_unknown_name_not_treated_as_tag():
    """名字不在名单 → 不当标签，避免把散文冒号误切（整行作旁白）。"""
    text = "时间：下午三点，阳光正好。"
    out = parse_speaker_tagged_lines(text, ROSTER)
    assert out == [{"character": "", "text": "时间：下午三点，阳光正好。"}]


def test_untagged_line_is_narration():
    out = parse_speaker_tagged_lines("他走进房间，环顾四周。", ROSTER)
    assert out == [{"character": "", "text": "他走进房间，环顾四周。"}]


def test_empty_roster_accepts_any_name():
    """无名单时，任何 `名字：台词` 都当标签（用户自带标注剧本场景）。"""
    out = parse_speaker_tagged_lines("王五：哈喽", [])
    assert out == [{"character": "王五", "text": "哈喽"}]


def test_has_speaker_tags():
    assert has_speaker_tags("张三：你好", ROSTER) is True
    assert has_speaker_tags("旁白：黄昏。", ROSTER) is True
    assert has_speaker_tags("时间：下午", ROSTER) is False   # 名字不在名单
    assert has_speaker_tags("纯叙述没有冒号", ROSTER) is False


def test_blank_lines_skipped():
    out = parse_speaker_tagged_lines("\n张三：A\n\n李四：B\n", ROSTER)
    assert len(out) == 2
