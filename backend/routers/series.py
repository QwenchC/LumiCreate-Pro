"""v1.6.2: 系列连载（series）—— 一组【共用角色/立绘/元素/音乐】+ 文案章节管理的漫剧项目。

系列存储：<projects_dir>/_series/<series_id>/
  series.json    {id, name, emoji, created_at, updated_at}
  chapters.json  [{id, title, content, order}]
  characters.json + characters/<name>/portrait_N.png   ← 系列内项目【实时共用】角色池
  （角色/立绘的共用由 projects.py 的 _character_base 在项目归属系列时重定向到这里实现）

只管系列自身 + 章节；角色/元素/音乐的共用解析在各自模块里按 project.series_id 重定向。
"""
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import load_settings

router = APIRouter()


def _series_root() -> Path:
    return Path(load_settings().projects_dir) / "_series"


def _series_dir(sid: str) -> Path:
    return _series_root() / sid


class SeriesMeta(BaseModel):
    id: str
    name: str
    emoji: str = "📚"
    created_at: str
    updated_at: str


def _read_series(sid: str) -> SeriesMeta:
    f = _series_dir(sid) / "series.json"
    if not f.exists():
        raise HTTPException(404, detail="系列不存在")
    return SeriesMeta(**json.loads(f.read_text(encoding="utf-8-sig")))


def _write_series(m: SeriesMeta) -> None:
    d = _series_dir(m.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "series.json").write_text(m.model_dump_json(indent=2), encoding="utf-8")


def _chapters_path(sid: str) -> Path:
    return _series_dir(sid) / "chapters.json"


def _read_chapters(sid: str) -> list:
    p = _chapters_path(sid)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def _write_chapters(sid: str, chapters: list) -> None:
    _chapters_path(sid).write_text(
        json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")


def _iter_project_metas():
    """遍历所有 project.json（用于统计章节被哪个项目用过 / 列系列下项目）。"""
    from routers.projects import _projects_root
    root = _projects_root()
    if not root.exists():
        return
    for e in root.iterdir():
        mf = e / "project.json"
        if not mf.is_file():
            continue
        try:
            yield json.loads(mf.read_text(encoding="utf-8-sig"))
        except Exception:
            continue


def _chapter_usage(sid: str) -> dict:
    """{chapter_id: [{project_id, project_name, episode_no}]} —— 该系列下哪些项目用过哪些章节。
    带 episode_no，便于章节列表显示「第n集：项目名」。调用前应先 _ensure_episode_numbers。"""
    usage: dict = {}
    for meta in _iter_project_metas():
        if meta.get("series_id") != sid:
            continue
        try:
            no = int(meta.get("episode_no") or 0)
        except Exception:
            no = 0
        for cid in meta.get("chapter_ids") or []:
            usage.setdefault(cid, []).append(
                {"project_id": meta.get("id", ""), "project_name": meta.get("name", ""),
                 "episode_no": no})
    for cid in usage:
        usage[cid].sort(key=lambda u: u.get("episode_no") or 0)
    return usage


def _ensure_episode_numbers(sid: str) -> list:
    """回填/修复该系列内项目的 episode_no（1-based、唯一）。
    - 已有正数集号：保留（同号冲突时保最早创建的，其余顺延到末尾）。
    - 缺集号（旧项目，episode_no<=0）：按 created_at 接在当前最大集号之后。
    返回该系列全部 project metas（已带正确 episode_no）。"""
    from routers.projects import _patch_meta_fields
    metas = [m for m in _iter_project_metas() if m.get("series_id") == sid]

    def _no(m):
        try:
            return int(m.get("episode_no") or 0)
        except Exception:
            return 0

    # 已分配者优先（按集号、再按创建时间），未分配者按创建时间排在最后
    metas_sorted = sorted(
        metas,
        key=lambda m: (0, _no(m), m.get("created_at", "")) if _no(m) > 0
        else (1, 0, m.get("created_at", "")))
    used: set = set()
    for m in metas_sorted:
        no = _no(m)
        if no <= 0 or no in used:
            no = (max(used) if used else 0) + 1
            _patch_meta_fields(m.get("id", ""), {"episode_no": no})
            m["episode_no"] = no
        used.add(no)
    return metas


# ── Series CRUD ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[SeriesMeta])
async def list_series():
    root = _series_root()
    out: list = []
    if root.exists():
        for e in root.iterdir():
            f = e / "series.json"
            if f.is_file():
                try:
                    out.append(SeriesMeta(**json.loads(f.read_text(encoding="utf-8-sig"))))
                except Exception:
                    pass
    out.sort(key=lambda s: s.updated_at, reverse=True)
    return out


class CreateSeriesRequest(BaseModel):
    name: str
    emoji: str = "📚"


@router.post("", response_model=SeriesMeta, status_code=201)
async def create_series(req: CreateSeriesRequest):
    now = datetime.now(timezone.utc).isoformat()
    sid = f"series_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    m = SeriesMeta(id=sid, name=req.name, emoji=req.emoji or "📚",
                   created_at=now, updated_at=now)
    _write_series(m)
    (_series_dir(sid) / "characters").mkdir(parents=True, exist_ok=True)
    (_series_dir(sid) / "elements").mkdir(parents=True, exist_ok=True)
    return m


@router.get("/{sid}", response_model=SeriesMeta)
async def get_series(sid: str):
    return _read_series(sid)


class UpdateSeriesRequest(BaseModel):
    name: Optional[str] = None
    emoji: Optional[str] = None


@router.put("/{sid}", response_model=SeriesMeta)
async def update_series(sid: str, req: UpdateSeriesRequest):
    m = _read_series(sid)
    if req.name is not None:
        m.name = req.name
    if req.emoji is not None:
        m.emoji = req.emoji
    m.updated_at = datetime.now(timezone.utc).isoformat()
    _write_series(m)
    return m


@router.delete("/{sid}", status_code=204)
async def delete_series(sid: str):
    _read_series(sid)
    # 仅在无归属项目时允许删除，避免删掉共享池让项目角色丢失
    for meta in _iter_project_metas():
        if meta.get("series_id") == sid:
            raise HTTPException(
                409, detail="该系列下仍有项目，请先移出/删除这些项目再删除系列")
    # 先关闭系列级元素库连接，避免 Windows 上文件被占用导致删除失败
    try:
        from services.db import close_series_conns
        close_series_conns(sid)
    except Exception:
        pass
    shutil.rmtree(_series_dir(sid), ignore_errors=True)


@router.get("/{sid}/projects")
async def series_projects(sid: str):
    """返回按集数排序的剧集列表，含「空白集」占位（删中间集保留空位时产生的编号空缺）。
    episodes: 覆盖 1..max_no 的完整序列；blank=True 表示该集号无项目占用。
    projects: 仅真实项目（升序），兼容旧调用方。"""
    _read_series(sid)
    metas = _ensure_episode_numbers(sid)
    by_no: dict = {}
    for m in metas:
        try:
            no = int(m.get("episode_no") or 0)
        except Exception:
            no = 0
        if no > 0:
            by_no[no] = m
    max_no = max(by_no.keys()) if by_no else 0
    episodes = []
    for n in range(1, max_no + 1):
        m = by_no.get(n)
        if m:
            episodes.append({"no": n, "project_id": m.get("id", ""),
                             "project_name": m.get("name", ""),
                             "updated_at": m.get("updated_at", ""), "blank": False})
        else:
            episodes.append({"no": n, "project_id": "", "project_name": "",
                             "updated_at": "", "blank": True})
    projects = [{"id": e["project_id"], "name": e["project_name"],
                 "updated_at": e["updated_at"], "episode_no": e["no"]}
                for e in episodes if not e["blank"]]
    return {"episodes": episodes, "projects": projects, "max_no": max_no}


# ── Chapters ────────────────────────────────────────────────────────────────────

@router.get("/{sid}/chapters")
async def list_chapters(sid: str):
    _read_series(sid)
    _ensure_episode_numbers(sid)        # 先回填集号 → used_by 才带正确「第n集」
    chapters = _read_chapters(sid)
    usage = _chapter_usage(sid)
    for c in chapters:
        c["used_by"] = usage.get(c.get("id"), [])
    return {"chapters": chapters}


class ChapterIn(BaseModel):
    title: str = ""
    content: str = ""


@router.post("/{sid}/chapters")
async def add_chapter(sid: str, req: ChapterIn):
    _read_series(sid)
    chapters = _read_chapters(sid)
    cid = f"ch_{uuid.uuid4().hex[:8]}"
    chapters.append({"id": cid, "title": req.title, "content": req.content,
                     "order": len(chapters)})
    _write_chapters(sid, chapters)
    return {"id": cid}


@router.put("/{sid}/chapters/{cid}")
async def update_chapter(sid: str, cid: str, req: ChapterIn):
    chapters = _read_chapters(sid)
    found = False
    for c in chapters:
        if c.get("id") == cid:
            c["title"] = req.title
            c["content"] = req.content
            found = True
            break
    if not found:
        raise HTTPException(404, detail="章节不存在")
    _write_chapters(sid, chapters)
    return {"ok": True}


@router.delete("/{sid}/chapters/{cid}", status_code=204)
async def delete_chapter(sid: str, cid: str):
    chapters = [c for c in _read_chapters(sid) if c.get("id") != cid]
    _write_chapters(sid, chapters)


class ReorderChaptersRequest(BaseModel):
    order: List[str]    # chapter id 顺序


@router.put("/{sid}/chapters-order")
async def reorder_chapters(sid: str, req: ReorderChaptersRequest):
    chapters = _read_chapters(sid)
    by_id = {c.get("id"): c for c in chapters}
    new = [by_id[cid] for cid in req.order if cid in by_id]
    # 把未列出的补在后面
    new += [c for c in chapters if c.get("id") not in set(req.order)]
    for i, c in enumerate(new):
        c["order"] = i
    _write_chapters(sid, new)
    return {"ok": True}


# ── 剧集（集数）删除 ──────────────────────────────────────────────────────────────
# 删最后一集：直接删，无空缺。删中间集：调用方二选一策略：
#   shift —— 删除并把后续各集集号 -1（保持连续编号）
#   blank —— 保留该集号为「空白集」占位，后续集号不变

class DeleteEpisodeRequest(BaseModel):
    project_id: str
    strategy: str = "blank"     # "shift" | "blank"


@router.post("/{sid}/delete-episode")
async def delete_episode(sid: str, req: DeleteEpisodeRequest):
    _read_series(sid)
    from routers.projects import _patch_meta_fields, delete_project
    _ensure_episode_numbers(sid)
    target = None
    for m in _iter_project_metas():
        if m.get("series_id") == sid and m.get("id") == req.project_id:
            target = m
            break
    if target is None:
        raise HTTPException(404, detail="该集不属于此系列")
    try:
        d = int(target.get("episode_no") or 0)
    except Exception:
        d = 0
    # 删除项目本体（复用标准删除：清 sqlite / 目录 / ComfyUI 残留）
    await delete_project(req.project_id)
    # shift 策略 = 「保持连续编号」：把剩余各集整体重排为 1..N，
    # 这样既消除本次删除产生的空缺，也消除此前遗留的空白集（真正连续无空缺）。
    if req.strategy == "shift":
        survivors = [m for m in _iter_project_metas()
                     if m.get("series_id") == sid and m.get("id") != req.project_id]

        def _eno(m):
            try:
                return int(m.get("episode_no") or 0)
            except Exception:
                return 0

        survivors.sort(key=lambda m: (0, _eno(m), m.get("created_at", "")) if _eno(m) > 0
                       else (1, 0, m.get("created_at", "")))
        for i, m in enumerate(survivors, start=1):
            if _eno(m) != i:
                _patch_meta_fields(m.get("id", ""), {"episode_no": i})
    return await series_projects(sid)


class DeleteBlankRequest(BaseModel):
    episode_no: int = Field(..., ge=1)      # 1-based；ge=1 拒绝 0/负数（防整体集号被 -1 腐蚀）


@router.post("/{sid}/delete-blank")
async def delete_blank(sid: str, req: DeleteBlankRequest):
    """删除一个「空白集」占位：把其后所有集号 -1（消除该空缺）。"""
    _read_series(sid)
    from routers.projects import _patch_meta_fields
    d = int(req.episode_no)
    if d < 1:
        raise HTTPException(400, detail="非法集号")
    # 用【当前持久化集号】校验占用（不先回填——否则脏/0 集号项目会被回填进该空白槽位被误判）。
    for m in _iter_project_metas():
        if m.get("series_id") != sid:
            continue
        try:
            cur = int(m.get("episode_no") or 0)
        except Exception:
            cur = 0
        if cur == d:
            raise HTTPException(400, detail="该集数不是空白集，请用删除剧集")
    for m in _iter_project_metas():
        if m.get("series_id") != sid:
            continue
        try:
            no = int(m.get("episode_no") or 0)
        except Exception:
            no = 0
        if no > d:
            _patch_meta_fields(m.get("id", ""), {"episode_no": no - 1})
    return await series_projects(sid)
