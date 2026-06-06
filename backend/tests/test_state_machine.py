"""A1: 状态机转移 + invariant 校验。"""
import pytest

from services.project_state import (
    SceneStatus, SceneSnapshot,
    can_transition, check_can_enter, aggregate_project_stage,
    ProjectStage, InvalidTransition,
)


def _snap(status: SceneStatus, **kw) -> SceneSnapshot:
    defaults = dict(
        id="s1",
        has_start_frame_prompt=False, has_end_frame_prompt=False,
        image_start_count=0, image_end_count=0,
        has_audio=False, has_video=False,
    )
    defaults.update(kw)
    return SceneSnapshot(status=status, **defaults)


# ── 合法转移 ──────────────────────────────────────────────────────────────────

def test_draft_can_only_go_to_prompted_or_error():
    assert can_transition(SceneStatus.DRAFT, SceneStatus.PROMPTED)
    assert can_transition(SceneStatus.DRAFT, SceneStatus.ERROR)
    assert not can_transition(SceneStatus.DRAFT, SceneStatus.IMAGE_DRAFTED)
    assert not can_transition(SceneStatus.DRAFT, SceneStatus.VIDEO_READY)


def test_prompted_can_step_forward_or_back():
    # 向前
    assert can_transition(SceneStatus.PROMPTED, SceneStatus.IMAGE_DRAFTED)
    # 向后（回到 DRAFT，例如撤销提示词）
    assert can_transition(SceneStatus.PROMPTED, SceneStatus.DRAFT)


def test_error_can_recover_to_any_state():
    """error 是用户介入点；允许回退到任何状态。"""
    for target in SceneStatus:
        assert can_transition(SceneStatus.ERROR, target)


def test_no_skipping_stages():
    """不能跳级——例如从 prompted 直接到 audio_ready。"""
    assert not can_transition(SceneStatus.PROMPTED, SceneStatus.AUDIO_READY)
    assert not can_transition(SceneStatus.DRAFT, SceneStatus.VIDEO_READY)


# ── invariant ──────────────────────────────────────────────────────────────────

def test_prompted_requires_both_prompts():
    """进 prompted 必须 start + end frame prompt 都有。"""
    with pytest.raises(InvalidTransition):
        check_can_enter(SceneStatus.PROMPTED, _snap(SceneStatus.DRAFT))
    with pytest.raises(InvalidTransition):
        check_can_enter(SceneStatus.PROMPTED, _snap(
            SceneStatus.DRAFT, has_start_frame_prompt=True,
        ))
    # 两个都有 → 通过
    check_can_enter(SceneStatus.PROMPTED, _snap(
        SceneStatus.DRAFT,
        has_start_frame_prompt=True, has_end_frame_prompt=True,
    ))


def test_image_drafted_requires_both_frame_slots():
    """进 image_drafted 必须 start + end 至少各 1 张。"""
    with pytest.raises(InvalidTransition):
        check_can_enter(SceneStatus.IMAGE_DRAFTED, _snap(
            SceneStatus.PROMPTED, image_start_count=1, image_end_count=0,
        ))
    # 两边都有 → 通过
    check_can_enter(SceneStatus.IMAGE_DRAFTED, _snap(
        SceneStatus.PROMPTED, image_start_count=1, image_end_count=1,
    ))


def test_audio_ready_requires_audio():
    with pytest.raises(InvalidTransition):
        check_can_enter(SceneStatus.AUDIO_READY, _snap(SceneStatus.IMAGE_DRAFTED))
    check_can_enter(SceneStatus.AUDIO_READY, _snap(
        SceneStatus.IMAGE_DRAFTED, has_audio=True,
    ))


def test_video_ready_requires_video():
    with pytest.raises(InvalidTransition):
        check_can_enter(SceneStatus.VIDEO_READY, _snap(SceneStatus.AUDIO_READY))
    check_can_enter(SceneStatus.VIDEO_READY, _snap(
        SceneStatus.AUDIO_READY, has_video=True,
    ))


# ── 项目级聚合 ────────────────────────────────────────────────────────────────

def test_empty_project():
    assert aggregate_project_stage([]) == ProjectStage.EMPTY


def test_aggregate_uses_lowest_state():
    """项目阶段 = 最低分镜状态对应阶段。"""
    statuses = [
        SceneStatus.VIDEO_READY,
        SceneStatus.IMAGE_DRAFTED,
        SceneStatus.PROMPTED,    # 最低
    ]
    assert aggregate_project_stage(statuses) == ProjectStage.PROMPTED


def test_any_error_marks_partial_error():
    statuses = [SceneStatus.VIDEO_READY, SceneStatus.ERROR]
    assert aggregate_project_stage(statuses) == ProjectStage.PARTIAL_ERROR


def test_all_finalized():
    statuses = [SceneStatus.FINALIZED] * 5
    assert aggregate_project_stage(statuses) == ProjectStage.FINALIZED
