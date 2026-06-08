"""v1.4.1 — 视频工作流分类 / 支持列表 / i2v 补丁 / flfa2i 无音频模式。"""
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / "workflows"


def _load(name: str) -> dict:
    p = WORKFLOWS / name
    if not p.exists():
        pytest.skip(f"workflow {name} not present")
    return json.loads(p.read_text(encoding="utf-8-sig"))


# ── 分类 ──────────────────────────────────────────────────────────────────────

def test_classify_flfa2i_video():
    from services.workflow_meta import classify_video_workflow
    wf = _load("flfa2i-lumicreate.json")
    assert classify_video_workflow("flfa2i-lumicreate", workflow=wf) == "video_flfa2i"


def test_classify_i2v_video():
    from services.workflow_meta import classify_video_workflow
    wf = _load("video_ltx2_3_i2v.json")
    assert classify_video_workflow("video_ltx2_3_i2v", workflow=wf) == "video_i2v"


def test_classify_unknown_workflow():
    from services.workflow_meta import classify_video_workflow
    # 图片工作流不应识别为视频
    wf = _load("image_flux2_text_to_image_9b.json")
    assert classify_video_workflow("image_flux2_text_to_image_9b",
                                    workflow=wf) == "unknown"


def test_video_features_flfa2i():
    from services.workflow_meta import get_video_workflow_features
    f = get_video_workflow_features("video_flfa2i")
    assert f["requires_start_image"] is True
    assert f["requires_end_image"]   is True
    assert f["supports_audio"]       is True
    assert f["supports_duration"]    is True


def test_video_features_i2v():
    from services.workflow_meta import get_video_workflow_features
    f = get_video_workflow_features("video_i2v")
    assert f["requires_start_image"] is True
    assert f["requires_end_image"]   is False
    assert f["supports_audio"]       is False
    assert f["supports_duration"]    is True


# ── 支持过滤 ──────────────────────────────────────────────────────────────────

def test_supported_workflow_filter_image():
    """图片工作流过滤器：t2i / i2i_* → True；视频工作流 → False。"""
    from services.workflow_meta import is_supported_image_workflow
    wf_t2i = _load("image_flux2_text_to_image_9b.json")
    wf_i2i = _load("image_flux2_klein_image_edit_9b_base.json")
    wf_v   = _load("flfa2i-lumicreate.json")
    assert is_supported_image_workflow("image_flux2_text_to_image_9b", workflow=wf_t2i)
    assert is_supported_image_workflow("image_flux2_klein_image_edit_9b_base",
                                        workflow=wf_i2i)
    # 视频工作流 → False
    assert not is_supported_image_workflow("flfa2i-lumicreate", workflow=wf_v)


def test_supported_workflow_filter_video():
    from services.workflow_meta import is_supported_video_workflow
    wf_v1 = _load("flfa2i-lumicreate.json")
    wf_v2 = _load("video_ltx2_3_i2v.json")
    wf_img = _load("image_flux2_text_to_image_9b.json")
    assert is_supported_video_workflow("flfa2i-lumicreate", workflow=wf_v1)
    assert is_supported_video_workflow("video_ltx2_3_i2v", workflow=wf_v2)
    # 图片工作流 → False
    assert not is_supported_video_workflow("image_flux2_text_to_image_9b",
                                            workflow=wf_img)


# ── i2v 补丁 ──────────────────────────────────────────────────────────────────

def test_patch_workflow_i2v_writes_widgets():
    """补丁后内部 PrimitiveInt 节点应反映 width/height/fps/duration，顶层 LoadImage 应反映 image。"""
    from services.ltx2video import patch_workflow_i2v
    wf = _load("video_ltx2_3_i2v.json")
    out = patch_workflow_i2v(wf, "my_img.png", 720, 1280, 24, 8, "a cat walking")
    inner_by_id = {}
    for sg in (out.get("definitions") or {}).get("subgraphs") or []:
        for inn in sg.get("nodes") or []:
            inner_by_id[inn.get("id")] = inn
    # node ids 来自 DEFAULT_VIDEO_I2V_NODE_MAP
    assert inner_by_id[312]["widgets_values"][0] == 720    # width
    assert inner_by_id[299]["widgets_values"][0] == 1280   # height
    assert inner_by_id[300]["widgets_values"][0] == 24     # fps
    assert inner_by_id[301]["widgets_values"][0] == 8      # duration_secs
    assert inner_by_id[319]["widgets_values"][0] == "a cat walking"
    # 顶层 LoadImage
    for top in out.get("nodes") or []:
        if top.get("id") == 269:
            assert top["widgets_values"][0] == "my_img.png"
            break
    else:
        pytest.fail("top-level LoadImage 269 not found")


def test_patch_workflow_i2v_does_not_mutate_input():
    """deep-copy 必须，不能改原 workflow（多次生成时复用 workflow 对象）。"""
    from services.ltx2video import patch_workflow_i2v
    wf = _load("video_ltx2_3_i2v.json")
    orig_str = json.dumps(wf, sort_keys=True)
    _ = patch_workflow_i2v(wf, "x.png", 720, 1280, 24, 5, "prompt")
    after_str = json.dumps(wf, sort_keys=True)
    assert orig_str == after_str, "patch_workflow_i2v mutated its input!"


# ── flfa2i 无音频模式：patch_workflow 跳过 audio 节点 ─────────────────────────

def test_flfa2i_patch_skips_audio_node_when_empty():
    """audio_file='' → 不应写入 LoadAudio 节点的 widgets_values[0]。"""
    from services.ltx2video import patch_workflow
    wf = _load("flfa2i-lumicreate.json")
    out = patch_workflow(wf,
                          first_frame_file="ff.png", last_frame_file="lf.png",
                          audio_file="",   # 无音频模式
                          width=720, height=1280, fps=25.0,
                          duration_secs=6, positive_prompt="x")
    # LoadAudio 节点 232 的 widgets_values[0] 应保留原值（不被覆盖为空）
    for n in out.get("nodes") or []:
        if n.get("id") == 232:
            wv = n.get("widgets_values") or []
            assert wv and wv[0] != "", \
                f"LoadAudio widgets_values[0] should keep its default, got {wv}"
            break


def test_flfa2i_patch_writes_audio_when_provided():
    from services.ltx2video import patch_workflow
    wf = _load("flfa2i-lumicreate.json")
    out = patch_workflow(wf,
                          first_frame_file="ff.png", last_frame_file="lf.png",
                          audio_file="my_audio.wav",
                          width=720, height=1280, fps=25.0,
                          duration_secs=6, positive_prompt="x")
    for n in out.get("nodes") or []:
        if n.get("id") == 232:
            assert n["widgets_values"][0] == "my_audio.wav"
            break
    else:
        pytest.fail("LoadAudio 232 not found")


def test_i2v_reroute_propagates_vae():
    """Real-world bug: Reroute 293 in i2v subgraph fan-outs VAE from
    CheckpointLoaderSimple (slot 2) to three consumers (LTXVLatentUpsampler,
    LTXVImgToVideoInplace, VAEDecodeTiled). Previously the converter would
    drop the Reroute from the API output but leave consumer.vae pointing at
    the dead Reroute → ComfyUI 'Required input is missing: vae' on all three."""
    from services.comfyui import _litegraph_to_api
    from services.ltx2video import patch_workflow_i2v
    wf = _load("video_ltx2_3_i2v.json")
    patched = patch_workflow_i2v(wf, "x.png", 720, 1280, 24, 5, "test")
    api = _litegraph_to_api(patched)

    for nid in ("sg320_287", "sg320_288", "sg320_315"):
        n = api.get(nid)
        assert n is not None, f"{nid} missing from API"
        vae = (n.get("inputs") or {}).get("vae")
        assert isinstance(vae, list) and len(vae) == 2, \
            f"{nid}.vae should be a [node, slot] link, got {vae!r}"
        # 应该绕过 Reroute 293 直接接到 CheckpointLoaderSimple 316 的 slot 2 (VAE)
        assert vae[0] == "sg320_316" and vae[1] == 2, \
            f"{nid}.vae should bypass Reroute and point at CheckpointLoaderSimple, got {vae!r}"

    # 全工作流不应有任何 dangling 链路
    alive = set(api.keys())
    for nid, n in api.items():
        for inp_name, v in (n.get("inputs") or {}).items():
            if isinstance(v, list) and v:
                assert v[0] in alive, \
                    f"{nid}.{inp_name} dangling: {v}"


def test_silent_wav_generation_valid():
    """_make_silent_wav 必须产出 ComfyUI 能解析的有效 WAV：RIFF/WAVE header + data 段。"""
    from services.ltx2video import _make_silent_wav
    wav = _make_silent_wav(2000)   # 2 秒
    assert wav.startswith(b"RIFF")
    assert b"WAVE" in wav[:12]
    assert b"fmt " in wav[:24]
    assert b"data" in wav
    # 44100 Hz mono 16-bit, 2 秒 → ~176400 字节数据 + 44 字节 header
    expected_data = 44100 * 2 * 2
    assert len(wav) == 44 + expected_data, \
        f"silent wav size mismatch: {len(wav)} vs {44 + expected_data}"


def test_list_workflows_only_returns_bundled(tmp_path):
    """v1.4.1+: list_workflows 应只读项目自带 workflows/，不读用户的 ComfyUI 目录。"""
    import asyncio
    from services.comfyui import list_workflows, bundled_workflow_dir

    bundled = bundled_workflow_dir()
    assert bundled is not None, "bundled workflows dir must exist in repo"
    bundled_names = sorted(p.stem for p in bundled.glob("*.json"))
    assert bundled_names, "bundled dir should not be empty"

    # 即使 cfg.workflow_dir 指向另一个塞满乱七八糟工作流的目录，list 也只回 bundled
    fake_dir = tmp_path / "user_comfyui_workflows"
    fake_dir.mkdir()
    (fake_dir / "random_workflow_should_not_appear.json").write_text('{"nodes": []}')

    class _Cfg:
        workflow_dir = str(fake_dir)
        comfyui_url  = "http://localhost:9999"

    listed = asyncio.run(list_workflows(_Cfg()))
    assert listed == bundled_names, \
        f"list_workflows must only return bundled set, got {listed!r}"
    assert "random_workflow_should_not_appear" not in listed


def test_list_workflows_respects_env_override(tmp_path, monkeypatch):
    """LUMI_WORKFLOWS_DIR 环境变量可定制 bundled 目录（测试/部署用）。"""
    import asyncio
    from services.comfyui import list_workflows

    custom_dir = tmp_path / "custom_workflows"
    custom_dir.mkdir()
    (custom_dir / "only_this.json").write_text('{"nodes": []}')
    monkeypatch.setenv("LUMI_WORKFLOWS_DIR", str(custom_dir))

    class _Cfg:
        workflow_dir = ""
        comfyui_url  = "http://localhost:9999"

    listed = asyncio.run(list_workflows(_Cfg()))
    assert listed == ["only_this"]


def test_hard_whitelist_caps_image_dropdown():
    """v1.4.1+: 硬名单兜底——任何不在 SUPPORTED_IMAGE_WORKFLOWS 里的名字
    一律拒绝。即使分类器误把某个工作流认成 t2i，硬名单也会把它挡住。"""
    from services.workflow_meta import (
        is_supported_image_workflow, SUPPORTED_IMAGE_WORKFLOWS
    )
    # 1) 白名单内的全部能通过（前提是文件存在）
    assert SUPPORTED_IMAGE_WORKFLOWS == frozenset({
        "t2i-lumicreate",
        "image_flux2_text_to_image_9b",
        "image_flux2_klein_image_edit_9b_base",
        "sd_default_workflow",   # v1.4.4
    })
    # 2) 任何不在白名单的名字直接返回 False —— 不读 workflow / 不调分类器
    bogus = ["3d_hunyuan3d-v2.1", "EasyFlow v1.5", "_temp_relay",
             "video_wan2_2_14B_i2v", "image_qwen_image_edit",
             "image_flux2_text_to_image_9b_FAKE"]  # 多带俩字也不行
    for n in bogus:
        assert not is_supported_image_workflow(n, workflow=None), \
            f"{n!r} leaked through hard whitelist"


def test_hard_whitelist_caps_video_dropdown():
    from services.workflow_meta import (
        is_supported_video_workflow, SUPPORTED_VIDEO_WORKFLOWS
    )
    assert SUPPORTED_VIDEO_WORKFLOWS == frozenset({
        "flfa2i-lumicreate",
        "video_ltx2_3_i2v",
    })
    bogus = ["LTX-2.3首尾帧+语音数字人", "infinitetalk单人 I2V",
             "video_wan2_2_5B_ti2v", "fishaudio+ltx2.3",
             "flfa2i-lumicreate-modified", "video_ltx2_3_i2v_eros"]
    for n in bogus:
        assert not is_supported_video_workflow(n, workflow=None), \
            f"{n!r} leaked through hard whitelist"


def test_hard_whitelist_does_not_block_generation():
    """终极保障：硬名单只影响下拉（is_supported_*），不影响 get_workflow_json
    / classify_video_workflow / generate_video 等生成路径。
    生成依然能跑任何已落盘的工作流。"""
    from services.workflow_meta import classify_video_workflow
    from services.comfyui import get_workflow_json
    import asyncio
    # 假设用户在 ComfyUI 目录里有一个自定义 i2v workflow，名字不在白名单
    # classify 仍能识别它，get_workflow_json 仍能读它（因为白名单不参与这两步）
    assert classify_video_workflow("my_custom_image_to_video") == "video_i2v"
    assert classify_video_workflow("my_custom_flfa2i_workflow") == "video_flfa2i"
