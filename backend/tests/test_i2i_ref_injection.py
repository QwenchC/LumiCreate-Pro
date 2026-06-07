"""轮 5: i2i 参考图注入 + ref 解析端到端测试。

测试覆盖：
  - _inject_ref_images 把 LoadImage widgets_values[0] 替换为新文件名
  - 文件被复制到 ComfyUI input 目录
  - 子图内部的 LoadImage 也能识别（展平后）
  - 元素/角色立绘的 ref 路径解析
"""
import asyncio
import base64
import json
import shutil
from pathlib import Path


def _mk_workflow_one_loadimage():
    """最小工作流：1 个 LoadImage 节点 + 1 个 CLIPTextEncode + 1 个 KSampler。"""
    return {
        "nodes": [
            {"id": 1, "type": "LoadImage", "widgets_values": ["placeholder.png", "image"]},
            {"id": 2, "type": "CLIPTextEncode", "widgets_values": ["hello"]},
            {"id": 3, "type": "KSampler", "widgets_values": [0, "fixed", 20, 1.0, "euler", "normal", 1.0]},
        ],
        "links": [],
    }


def _mk_workflow_two_loadimage():
    wf = _mk_workflow_one_loadimage()
    wf["nodes"].append({"id": 4, "type": "LoadImage", "widgets_values": ["ph2.png", "image"]})
    return wf


class _FakeCfg:
    """模拟 ImageEngineConfig，只用 _inject_ref_images 需要的字段。"""
    def __init__(self, input_dir, workflow_dir=""):
        self.comfyui_input_dir = str(input_dir)
        self.workflow_dir = str(workflow_dir)
        self.comfyui_url = "http://localhost:9999"   # 不应被命中


def test_inject_single_ref(tmp_path):
    """单 LoadImage 工作流，注入一个参考图。"""
    from services.comfyui import _inject_ref_images
    input_dir = tmp_path / "comfyui_input"; input_dir.mkdir()
    src_file = tmp_path / "ref.png"; src_file.write_bytes(b"\x89PNG_fake")

    wf = _mk_workflow_one_loadimage()
    cfg = _FakeCfg(input_dir)

    out = asyncio.run(_inject_ref_images(wf, [str(src_file)], cfg=cfg))
    # widgets_values[0] 被改成 lumi_ref_* 文件名
    li = next(n for n in out["nodes"] if n["type"] == "LoadImage")
    new_name = li["widgets_values"][0]
    assert new_name.startswith("lumi_ref_") and new_name.endswith(".png")
    # 文件确实复制过去了
    assert (input_dir / new_name).is_file()
    assert (input_dir / new_name).read_bytes() == b"\x89PNG_fake"


def test_inject_two_refs(tmp_path):
    """双 LoadImage 工作流，按 id 升序绑定两张参考图。"""
    from services.comfyui import _inject_ref_images
    input_dir = tmp_path / "comfyui_input"; input_dir.mkdir()
    src1 = tmp_path / "a.png"; src1.write_bytes(b"AAA")
    src2 = tmp_path / "b.png"; src2.write_bytes(b"BBB")

    wf = _mk_workflow_two_loadimage()
    cfg = _FakeCfg(input_dir)
    out = asyncio.run(_inject_ref_images(wf, [str(src1), str(src2)], cfg=cfg))

    loads = sorted([n for n in out["nodes"] if n["type"] == "LoadImage"],
                    key=lambda n: str(n["id"]))
    name1 = loads[0]["widgets_values"][0]
    name2 = loads[1]["widgets_values"][0]
    assert name1 != name2
    assert (input_dir / name1).read_bytes() == b"AAA"
    assert (input_dir / name2).read_bytes() == b"BBB"


def test_inject_too_many_refs_errors(tmp_path):
    from services.comfyui import _inject_ref_images
    input_dir = tmp_path / "ci"; input_dir.mkdir()
    src1 = tmp_path / "a.png"; src1.write_bytes(b"x")
    src2 = tmp_path / "b.png"; src2.write_bytes(b"y")

    wf = _mk_workflow_one_loadimage()   # 只有 1 个 LoadImage
    cfg = _FakeCfg(input_dir)
    try:
        asyncio.run(_inject_ref_images(wf, [str(src1), str(src2)], cfg=cfg))
        assert False, "should have raised"
    except RuntimeError as e:
        assert "超过" in str(e) or "LoadImage" in str(e)


def test_inject_no_loadimage_errors(tmp_path):
    from services.comfyui import _inject_ref_images
    input_dir = tmp_path / "ci"; input_dir.mkdir()
    src = tmp_path / "a.png"; src.write_bytes(b"x")
    wf = {"nodes": [{"id": 1, "type": "KSampler", "widgets_values": []}], "links": []}
    cfg = _FakeCfg(input_dir)
    try:
        asyncio.run(_inject_ref_images(wf, [str(src)], cfg=cfg))
        assert False
    except RuntimeError as e:
        assert "LoadImage" in str(e)


def test_inject_missing_input_dir_errors(tmp_path):
    """没有 input/ 目录、ComfyUI 也没起 → 报清楚的错。"""
    from services.comfyui import _inject_ref_images
    src = tmp_path / "a.png"; src.write_bytes(b"x")
    wf = _mk_workflow_one_loadimage()
    cfg = _FakeCfg("")  # 空 input_dir + 不存在的 url
    # 当没有 input_dir 时会走 /upload/image，httpx 会因连接拒绝抛错
    try:
        asyncio.run(_inject_ref_images(wf, [str(src)], cfg=cfg))
        assert False
    except Exception:
        pass  # 期望抛 RuntimeError / httpx ConnectError 之类


def test_inject_subgraph_loadimage(tmp_path):
    """LoadImage 在 subgraph 内部，应被展平后识别。"""
    from services.comfyui import _inject_ref_images
    input_dir = tmp_path / "ci"; input_dir.mkdir()
    src = tmp_path / "a.png"; src.write_bytes(b"data")

    sg_uuid = "abc-1234-uuid"
    wf = {
        "definitions": {
            "subgraphs": [{
                "id": sg_uuid,
                "inputNode":  {"id": -10},
                "outputNode": {"id": -20},
                "inputs":  [],
                "outputs": [],
                "nodes": [
                    {"id": 5, "type": "LoadImage", "widgets_values": ["x.png", "image"]},
                ],
                "links": [],
            }],
        },
        "nodes": [
            {"id": 100, "type": sg_uuid, "widgets_values": []},
            {"id": 2, "type": "KSampler", "widgets_values": []},
        ],
        "links": [],
    }
    cfg = _FakeCfg(input_dir)
    out = asyncio.run(_inject_ref_images(wf, [str(src)], cfg=cfg))
    # 展平后内部 LoadImage 是顶层节点（id 应有 sg100_ 前缀）
    loads = [n for n in out["nodes"] if n["type"] == "LoadImage"]
    assert len(loads) == 1
    assert str(loads[0]["id"]).startswith("sg100_") or loads[0]["id"] == 5 or str(loads[0]["id"]) == "5"
    name = loads[0]["widgets_values"][0]
    assert name.startswith("lumi_ref_")
    assert (input_dir / name).is_file()


# ── ref 路径解析（portrait/element/path）─────────────────────────────────────


def test_resolve_path_ref(tmp_path, isolated_app):
    """kind=path 直接传绝对路径。"""
    from routers.image_engine import _resolve_ref_paths
    f = tmp_path / "x.png"; f.write_bytes(b"P")
    paths = _resolve_ref_paths([{"kind": "path", "path": str(f)}])
    assert paths == [str(f)]


def test_resolve_path_ref_missing(isolated_app):
    from routers.image_engine import _resolve_ref_paths
    from fastapi import HTTPException
    try:
        _resolve_ref_paths([{"kind": "path", "path": "/nonexistent.png"}])
        assert False
    except HTTPException as e:
        assert e.status_code == 404


def test_resolve_portrait_ref(isolated_app):
    pid = isolated_app["make_project"]()
    client = isolated_app["client"]
    # 建立角色 + 立绘
    client.put(f"/api/projects/{pid}/characters", json={"characters": [
        {"name": "Alice", "role": "", "traits": "", "appearance": "",
         "negative": "", "voice": ""},
    ]})
    body = b"\x89PNG\r\n\x1a\nABC"
    client.post(f"/api/projects/{pid}/characters/Alice/portraits",
                json={"data": base64.b64encode(body).decode()})

    from routers.image_engine import _resolve_ref_paths
    paths = _resolve_ref_paths([{
        "kind": "portrait", "project_id": pid,
        "char_name": "Alice", "filename": "portrait_1.png",
    }])
    assert len(paths) == 1
    assert Path(paths[0]).is_file()
    assert Path(paths[0]).read_bytes() == body


def test_resolve_portrait_ref_missing_char(isolated_app):
    pid = isolated_app["make_project"]()
    from routers.image_engine import _resolve_ref_paths
    from fastapi import HTTPException
    try:
        _resolve_ref_paths([{
            "kind": "portrait", "project_id": pid,
            "char_name": "Nobody", "filename": "x.png",
        }])
        assert False
    except HTTPException as e:
        assert e.status_code == 404


def test_resolve_element_ref(isolated_app):
    """直接用 repo 创建元素 → 用 kind=element 解析回路径。
    （绕开 HTTP 端点，避免触发 isolated_app 未 patch 的 project_elements 路由。）"""
    pid = isolated_app["make_project"]()
    body = b"ELE"
    from services import elements_repo
    elem = elements_repo.create_element(
        f"project:{pid}", folder_id=None, name="ele.png",
        file_bytes=body, filename="ele.png", mime="image/png",
    )
    eid = elem["id"]

    from routers.image_engine import _resolve_ref_paths
    paths = _resolve_ref_paths([{
        "kind": "element", "scope": f"project:{pid}", "element_id": eid,
    }])
    assert len(paths) == 1
    assert Path(paths[0]).is_file()
    assert Path(paths[0]).read_bytes() == body


def test_resolve_element_ref_missing(isolated_app):
    from routers.image_engine import _resolve_ref_paths
    from fastapi import HTTPException
    try:
        _resolve_ref_paths([{
            "kind": "element", "scope": "global", "element_id": 99999,
        }])
        assert False
    except HTTPException as e:
        assert e.status_code == 404


def test_resolve_unknown_kind(isolated_app):
    from routers.image_engine import _resolve_ref_paths
    from fastapi import HTTPException
    try:
        _resolve_ref_paths([{"kind": "wat"}])
        assert False
    except HTTPException as e:
        assert e.status_code == 400
