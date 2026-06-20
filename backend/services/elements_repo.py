"""ElementsRepo — 元素库数据访问层（轮 2）。

支持两个 scope：
- "global"          全局元素库 → elements.sqlite + APPDATA/LumiCreate-Pro/elements/
- "project:{pid}"   项目级元素 → 项目 sqlite + <project>/elements/

接口统一：传 scope 字符串决定走哪条。

设计要点：
- 文件夹是树形：parent_id NULL 表示根；自引用支持任意层级
- path 字段是冗余（root/a/b/c），便于前端展示和模糊查询
- 删文件夹时级联删子文件夹（SQLite FK ON DELETE CASCADE）+ 文件夹内 element 设 folder_id = NULL（fallback 到"未分类"）
- 元素文件落盘到 `<root>/<folder_path>/<filename>`，元素表存相对 root 的 file_path
- 唯一性：同父下不能同名文件夹（UNIQUE constraint）
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.db import (
    get_global_elements_conn, global_elements_db, global_elements_root,
    project_db, get_conn as _get_project_conn,
    get_series_elements_conn, series_elements_root,
)
from config import load_settings


# ── Scope 解析 ────────────────────────────────────────────────────────────────


def _resolve_scope(scope: str) -> tuple[sqlite3.Connection, Path, str]:
    """返回 (conn, root_dir, scope_label)。root_dir 是元素文件根目录。"""
    if scope == "global" or not scope:
        conn = get_global_elements_conn()
        return conn, global_elements_root(), "global"
    if scope.startswith("project:"):
        pid = scope[len("project:"):]
        conn = _get_project_conn(pid)
        proot = Path(load_settings().projects_dir) / pid / "elements"
        proot.mkdir(parents=True, exist_ok=True)
        return conn, proot, scope
    if scope.startswith("series:"):
        # v1.6.2: 系列级元素库（同系列各集共用）
        sid = scope[len("series:"):]
        return get_series_elements_conn(sid), series_elements_root(sid), scope
    raise ValueError(f"unknown scope: {scope}")


def scope_root(scope: str) -> Path:
    """返回某 scope 的元素文件根目录（供文件服务端点用，避免重复推算路径）。"""
    return _resolve_scope(scope)[1]


def _commit_scope(scope: str) -> None:
    """Scope-aware commit。

    v1.5.1 修复：project 分支此前缺失 → 项目库的 INSERT/UPDATE 一直停在未提交事务里，
    单进程内读同一连接看得到（假象），但后端被 Electron 杀掉重启后未提交事务被回滚，
    项目元素/文件夹全部消失。这里对 project scope 也显式 commit。
    """
    if scope == "global" or not scope:
        try:
            get_global_elements_conn().commit()
        except Exception:
            pass
    elif scope.startswith("project:"):
        try:
            _get_project_conn(scope[len("project:"):]).commit()
        except Exception:
            pass
    elif scope.startswith("series:"):
        try:
            get_series_elements_conn(scope[len("series:"):]).commit()
        except Exception:
            pass


# ── Folder CRUD ───────────────────────────────────────────────────────────────


def _folder_path(conn: sqlite3.Connection, folder_id: Optional[int]) -> str:
    """从根算出文件夹路径串（"a/b/c"）。"""
    if folder_id is None:
        return ""
    chain: list[str] = []
    cur = folder_id
    seen: set[int] = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        row = conn.execute(
            "SELECT name, parent_id FROM element_folders WHERE id = ?", (cur,)
        ).fetchone()
        if row is None:
            break
        chain.append(row["name"])
        cur = row["parent_id"]
    return "/".join(reversed(chain))


def create_folder(scope: str, name: str, parent_id: Optional[int] = None) -> dict:
    conn, root, _ = _resolve_scope(scope)
    if not name or "/" in name or "\\" in name:
        raise ValueError("folder name must not contain '/' or '\\\\'")
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO element_folders(name, parent_id, path, created_at) "
        "VALUES(?, ?, '', ?)",
        (name.strip(), parent_id, now),
    )
    fid = cur.lastrowid
    # 更新 path
    path = _folder_path(conn, fid)
    conn.execute("UPDATE element_folders SET path = ? WHERE id = ?", (path, fid))
    # 物理目录也建出来（方便上传文件直接放进去）
    (root / path).mkdir(parents=True, exist_ok=True)
    _commit_scope(scope)
    return _get_folder(conn, fid)


def _get_folder(conn: sqlite3.Connection, folder_id: int) -> dict:
    row = conn.execute(
        "SELECT id, name, parent_id, path, created_at FROM element_folders WHERE id = ?",
        (folder_id,),
    ).fetchone()
    return dict(row) if row else {}


def list_folders(scope: str) -> list[dict]:
    """返回所有 folders 平铺（前端自己构树或按 parent_id 查）。"""
    conn, _, _ = _resolve_scope(scope)
    rows = conn.execute(
        "SELECT id, name, parent_id, path, created_at FROM element_folders "
        "ORDER BY path ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def rename_folder(scope: str, folder_id: int, new_name: str) -> dict:
    conn, root, _ = _resolve_scope(scope)
    if not new_name or "/" in new_name or "\\" in new_name:
        raise ValueError("name invalid")
    old = _get_folder(conn, folder_id)
    if not old:
        raise KeyError(folder_id)
    conn.execute("UPDATE element_folders SET name = ? WHERE id = ?",
                 (new_name.strip(), folder_id))
    # 自身与所有子孙重算 path
    _recalc_path_subtree(conn, folder_id)
    # 移动物理目录
    old_phys = root / old["path"]
    new_path = _folder_path(conn, folder_id)
    new_phys = root / new_path
    if old_phys != new_phys and old_phys.exists():
        new_phys.parent.mkdir(parents=True, exist_ok=True)
        try:
            old_phys.rename(new_phys)
        except OSError:
            pass
    _commit_scope(scope)
    return _get_folder(conn, folder_id)


def move_folder(scope: str, folder_id: int, new_parent_id: Optional[int]) -> dict:
    conn, root, _ = _resolve_scope(scope)
    # 防止把节点移动到自己的子孙下（自环）
    if new_parent_id is not None:
        ancestor = new_parent_id
        seen = set()
        while ancestor is not None and ancestor not in seen:
            if ancestor == folder_id:
                raise ValueError("cannot move folder under itself or its descendant")
            seen.add(ancestor)
            row = conn.execute(
                "SELECT parent_id FROM element_folders WHERE id = ?", (ancestor,)
            ).fetchone()
            ancestor = row["parent_id"] if row else None

    old = _get_folder(conn, folder_id)
    if not old:
        raise KeyError(folder_id)
    conn.execute("UPDATE element_folders SET parent_id = ? WHERE id = ?",
                 (new_parent_id, folder_id))
    _recalc_path_subtree(conn, folder_id)
    new_phys = root / _folder_path(conn, folder_id)
    old_phys = root / old["path"]
    if old_phys != new_phys and old_phys.exists():
        new_phys.parent.mkdir(parents=True, exist_ok=True)
        try:
            old_phys.rename(new_phys)
        except OSError:
            pass
    _commit_scope(scope)
    return _get_folder(conn, folder_id)


def _recalc_path_subtree(conn: sqlite3.Connection, root_id: int) -> None:
    """重算某节点及其所有子孙的 path。"""
    stack = [root_id]
    while stack:
        nid = stack.pop()
        new_path = _folder_path(conn, nid)
        conn.execute("UPDATE element_folders SET path = ? WHERE id = ?",
                     (new_path, nid))
        kids = conn.execute(
            "SELECT id FROM element_folders WHERE parent_id = ?", (nid,)
        ).fetchall()
        stack.extend(int(k["id"]) for k in kids)


def delete_folder(scope: str, folder_id: int, *, cascade: bool = True) -> None:
    """删除文件夹。cascade=True 时递归删子文件夹 + 文件夹内元素文件落盘。
    cascade=False 时若有内容报错（防止误删）。"""
    conn, root, _ = _resolve_scope(scope)
    info = _get_folder(conn, folder_id)
    if not info:
        return
    if not cascade:
        kids = conn.execute(
            "SELECT 1 FROM element_folders WHERE parent_id = ? LIMIT 1", (folder_id,)
        ).fetchone()
        elems = conn.execute(
            "SELECT 1 FROM elements WHERE folder_id = ? LIMIT 1", (folder_id,)
        ).fetchone()
        if kids or elems:
            raise RuntimeError("folder not empty")

    # 先收集所有子孙 folder_id（用于先删物理文件再删 SQLite 行——FK CASCADE 会删 SQLite，
    # 但我们要把文件夹下的 element file 也删掉）
    descendants = [folder_id]
    stack = [folder_id]
    while stack:
        nid = stack.pop()
        kids = conn.execute(
            "SELECT id FROM element_folders WHERE parent_id = ?", (nid,)
        ).fetchall()
        for k in kids:
            descendants.append(int(k["id"]))
            stack.append(int(k["id"]))

    # 删该文件夹及子孙下所有 element 的物理文件
    placeholders = ",".join("?" * len(descendants))
    elem_rows = conn.execute(
        f"SELECT file_path FROM elements WHERE folder_id IN ({placeholders})",
        descendants,
    ).fetchall()
    for r in elem_rows:
        try:
            (root / r["file_path"]).unlink(missing_ok=True)
        except OSError:
            pass

    # 删 SQLite 行（CASCADE 一并删子孙 + 关联 element）
    conn.execute("DELETE FROM element_folders WHERE id = ?", (folder_id,))
    # 物理目录递归删
    phys = root / info["path"]
    if phys.exists() and phys.is_dir():
        import shutil
        try: shutil.rmtree(phys)
        except OSError: pass
    _commit_scope(scope)


# ── Element CRUD ──────────────────────────────────────────────────────────────


def create_element(
    scope: str,
    *,
    folder_id: Optional[int],
    name: str,
    file_bytes: bytes,
    filename: str,
    mime: str = "image/png",
    source: str = "upload",
    source_meta: Optional[dict] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> dict:
    """落盘文件 + 写元素行。返回新元素 dict。"""
    conn, root, _ = _resolve_scope(scope)
    # 解析所在路径
    folder_path = ""
    if folder_id is not None:
        row = conn.execute("SELECT path FROM element_folders WHERE id = ?",
                           (folder_id,)).fetchone()
        if row is None:
            raise KeyError(folder_id)
        folder_path = row["path"]
    rel_dir = Path(folder_path)
    abs_dir = root / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    # 同名文件加序号
    safe_name = _safe_filename(filename or name or "element.png")
    rel_path = _unique_path(abs_dir, safe_name, rel_dir)
    (root / rel_path).write_bytes(file_bytes)

    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO elements("
        "  folder_id, name, file_path, mime, source, source_meta, "
        "  width, height, bytes, created_at"
        ") VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            folder_id, name or safe_name, str(rel_path).replace("\\", "/"),
            mime, source,
            json.dumps(source_meta or {}, ensure_ascii=False),
            width, height, len(file_bytes), now,
        ),
    )
    eid = cur.lastrowid
    _commit_scope(scope)
    return get_element(scope, eid)


def get_element(scope: str, element_id: int) -> Optional[dict]:
    conn, _, _ = _resolve_scope(scope)
    row = conn.execute(
        "SELECT id, folder_id, name, file_path, mime, source, source_meta, "
        "       width, height, bytes, created_at "
        "FROM elements WHERE id = ?", (element_id,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try: d["source_meta"] = json.loads(d["source_meta"] or "{}")
    except Exception: d["source_meta"] = {}
    return d


def list_elements(scope: str, *, folder_id: Optional[int] = None,
                  recursive: bool = False, limit: int = 500) -> list[dict]:
    """folder_id=None 时列根目录的元素。recursive=True 时把所有子孙的元素也列出来。"""
    conn, _, _ = _resolve_scope(scope)
    if recursive and folder_id is not None:
        # 收集所有子孙 folder id
        ids = [folder_id]
        stack = [folder_id]
        while stack:
            nid = stack.pop()
            kids = conn.execute(
                "SELECT id FROM element_folders WHERE parent_id = ?", (nid,)
            ).fetchall()
            for k in kids:
                ids.append(int(k["id"])); stack.append(int(k["id"]))
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT id, folder_id, name, file_path, mime, source, width, height, "
            f"       bytes, created_at FROM elements "
            f"WHERE folder_id IN ({placeholders}) ORDER BY created_at DESC LIMIT ?",
            ids + [int(max(1, min(limit, 2000)))],
        ).fetchall()
    elif folder_id is None:
        rows = conn.execute(
            "SELECT id, folder_id, name, file_path, mime, source, width, height, "
            "       bytes, created_at FROM elements "
            "WHERE folder_id IS NULL ORDER BY created_at DESC LIMIT ?",
            (int(max(1, min(limit, 2000))),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, folder_id, name, file_path, mime, source, width, height, "
            "       bytes, created_at FROM elements "
            "WHERE folder_id = ? ORDER BY created_at DESC LIMIT ?",
            (folder_id, int(max(1, min(limit, 2000)))),
        ).fetchall()
    return [dict(r) for r in rows]


def update_element(scope: str, element_id: int,
                   *, name: Optional[str] = None,
                   folder_id: Optional[int] = ...,
                   ) -> dict:
    """重命名 / 移动文件夹。folder_id=... 哨兵表示不动；None 表示移到根。"""
    conn, root, _ = _resolve_scope(scope)
    elem = get_element(scope, element_id)
    if elem is None:
        raise KeyError(element_id)

    parts: list[str] = []
    params: list = []
    if name is not None:
        parts.append("name = ?"); params.append(name)
    if folder_id is not ...:
        parts.append("folder_id = ?"); params.append(folder_id)
    if parts:
        params.append(element_id)
        conn.execute(f"UPDATE elements SET {', '.join(parts)} WHERE id = ?", params)

    # 如果换了文件夹，物理文件也移动
    if folder_id is not ...:
        new_folder_path = ""
        if folder_id is not None:
            row = conn.execute("SELECT path FROM element_folders WHERE id = ?",
                                (folder_id,)).fetchone()
            if row is None:
                raise KeyError(folder_id)
            new_folder_path = row["path"]
        old_full = root / elem["file_path"]
        new_dir = root / new_folder_path
        new_dir.mkdir(parents=True, exist_ok=True)
        new_rel = _unique_path(new_dir, Path(elem["file_path"]).name, Path(new_folder_path))
        try:
            old_full.rename(root / new_rel)
            conn.execute("UPDATE elements SET file_path = ? WHERE id = ?",
                         (str(new_rel).replace("\\", "/"), element_id))
        except OSError:
            pass

    _commit_scope(scope)
    return get_element(scope, element_id)


def delete_element(scope: str, element_id: int) -> None:
    conn, root, _ = _resolve_scope(scope)
    elem = get_element(scope, element_id)
    if elem is None:
        return
    try:
        (root / elem["file_path"]).unlink(missing_ok=True)
    except OSError:
        pass
    conn.execute("DELETE FROM elements WHERE id = ?", (element_id,))
    _commit_scope(scope)


# ── helpers ───────────────────────────────────────────────────────────────────


_INVALID_CHARS = '<>:"|?*\x00'


def _safe_filename(name: str) -> str:
    n = "".join(c for c in name if c not in _INVALID_CHARS)
    return n.strip() or "element"


def _unique_path(abs_dir: Path, base_name: str, rel_dir: Path) -> Path:
    """避免同名覆盖：若已存在则 base(2).png / base(3).png ..."""
    stem = Path(base_name).stem
    suffix = Path(base_name).suffix
    candidate = abs_dir / base_name
    rel = rel_dir / base_name
    n = 2
    while candidate.exists():
        cand_name = f"{stem}({n}){suffix}"
        candidate = abs_dir / cand_name
        rel = rel_dir / cand_name
        n += 1
    return rel


def get_element_path(scope: str, element_id: int) -> Optional[Path]:
    """轮 5: 返回元素的绝对路径（i2i 注入用）。元素不存在或文件丢失则返回 None。"""
    elem = get_element(scope, element_id)
    if not elem:
        return None
    _, root, _ = _resolve_scope(scope)
    p = root / elem["file_path"]
    return p if p.is_file() else None


def copy_element(src_scope: str, element_id: int, dst_scope: str,
                 *, dst_folder_id: Optional[int] = None) -> dict:
    """v1.5.0: 把一个元素从 src_scope 复制到 dst_scope（让全局库与项目库共通）。

    读取源文件字节 + 元数据，在目标 scope 落一份新元素（新 id，独立文件）。
    src/dst 同 scope 也允许（相当于"另存一份到其它文件夹"）。
    """
    elem = get_element(src_scope, element_id)
    if elem is None:
        raise KeyError(element_id)
    src_path = get_element_path(src_scope, element_id)
    if src_path is None:
        raise FileNotFoundError(f"element {element_id}@{src_scope} 文件丢失")
    file_bytes = src_path.read_bytes()
    src_meta = elem.get("source_meta") or {}
    if not isinstance(src_meta, dict):
        src_meta = {}
    new_meta = {**src_meta, "copied_from": {"scope": src_scope, "element_id": element_id}}
    return create_element(
        dst_scope,
        folder_id=dst_folder_id,
        name=elem.get("name") or "element",
        file_bytes=file_bytes,
        filename=Path(elem["file_path"]).name,
        mime=elem.get("mime") or "image/png",
        source="copy",
        source_meta=new_meta,
        width=elem.get("width"),
        height=elem.get("height"),
    )


def ensure_local_folder(scope: str) -> int:
    """确保有一个名为 'local' 的根目录文件夹（前端"本地上传"快速入口）。"""
    conn, _, _ = _resolve_scope(scope)
    row = conn.execute(
        "SELECT id FROM element_folders WHERE parent_id IS NULL AND name = 'local'"
    ).fetchone()
    if row:
        return int(row["id"])
    return int(create_folder(scope, "local", parent_id=None)["id"])
