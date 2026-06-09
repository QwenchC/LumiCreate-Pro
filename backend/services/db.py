"""项目数据库（A2 地基）。

设计：
- 每个项目一个 `project.sqlite` 放在项目目录，与已有 JSON 文件并存
- 启动时调 `ensure_schema()` 建表（幂等）
- 用 WAL 模式：多读 + 串行写，且对掉电相对安全
- schema_version 表跟踪迁移版本，加列走 `MIGRATIONS` 字典

不替换已有 JSON 文件，是"双写 + 兼容读"过渡层：
- 写入：所有 router 写 JSON 时同步写 SQLite
- 读取：暂时仍从 JSON 读（避免一次性大爆炸）；后续 router 逐步切换

约定：
- scenes 表 = 分镜 + 状态（status）
- scene_assets 表 = 每镜的图片/音频/视频/字幕等产物，按 type 区分
- events 表 = 任务执行的事件流（trace_id 关联，配合 E1 结构化日志）
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from config import SETTINGS_PATH, load_settings

# 每个项目 db 的连接池（同进程内复用）
_CONNS: dict[str, sqlite3.Connection] = {}
_CONN_LOCK = threading.Lock()


# 当前 schema 版本；每次加列/建表 +1 并在 MIGRATIONS 注册 SQL
SCHEMA_VERSION = 1


# Initial DDL（version=1 含全部初始表）；未来 +column 走 MIGRATIONS
_ELEMENTS_DDL = """
CREATE TABLE IF NOT EXISTS element_folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    parent_id   INTEGER,                     -- NULL = 根
    -- path 是冗余字段（root/a/b），便于前端展示与跨表查询
    path        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE(parent_id, name),
    FOREIGN KEY(parent_id) REFERENCES element_folders(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_element_folders_parent ON element_folders(parent_id);

CREATE TABLE IF NOT EXISTS elements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id    INTEGER,                    -- NULL = 根目录
    name         TEXT NOT NULL,              -- 显示名（可以与文件名不同）
    file_path    TEXT NOT NULL,              -- 相对元素根目录的路径
    mime         TEXT NOT NULL DEFAULT 'image/png',
    source       TEXT NOT NULL DEFAULT 'upload',  -- upload | t2i | imported
    source_meta  TEXT NOT NULL DEFAULT '{}',      -- JSON: 来源详情（如生成时的 prompt / workflow）
    width        INTEGER,
    height       INTEGER,
    bytes        INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    FOREIGN KEY(folder_id) REFERENCES element_folders(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_elements_folder ON elements(folder_id);
CREATE INDEX IF NOT EXISTS idx_elements_created ON elements(created_at DESC);
"""


INITIAL_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
    id              TEXT PRIMARY KEY,
    idx             INTEGER NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    duration_estimate REAL NOT NULL DEFAULT 5.0,
    start_frame_prompt TEXT NOT NULL DEFAULT '',
    end_frame_prompt   TEXT NOT NULL DEFAULT '',
    dialogues_json     TEXT NOT NULL DEFAULT '[]',
    scene_characters_json TEXT NOT NULL DEFAULT '[]',
    -- A1 状态机：draft / prompted / image_drafted / audio_ready / video_ready / finalized / error
    status          TEXT NOT NULL DEFAULT 'draft',
    error_message   TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scenes_status ON scenes(status);
CREATE INDEX IF NOT EXISTS idx_scenes_idx ON scenes(idx);

CREATE TABLE IF NOT EXISTS scene_assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id        TEXT NOT NULL,
    -- 'image_start' | 'image_end' | 'audio' | 'video' | 'subtitle'
    asset_type      TEXT NOT NULL,
    slot_index      INTEGER NOT NULL DEFAULT 0,
    -- 相对项目目录的文件路径（D1 之后所有资产走文件 URL，这里登记路径）
    file_path       TEXT NOT NULL DEFAULT '',
    -- 'mp3' | 'wav' | 'png' | 'mp4' | 'srt' | ...
    format          TEXT NOT NULL DEFAULT '',
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    is_selected     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    UNIQUE(scene_id, asset_type, slot_index)
);
CREATE INDEX IF NOT EXISTS idx_assets_scene_type ON scene_assets(scene_id, asset_type);

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,   -- 'orchestrator' | 'images' | 'audio' | 'video' | 'merge' | 'subtitle' | 'prompts'
    status          TEXT NOT NULL DEFAULT 'pending', -- pending|running|success|failed|cancelled
    -- 任务输入 / 输出
    request_json    TEXT NOT NULL DEFAULT '{}',
    result_json     TEXT NOT NULL DEFAULT '{}',
    error_message   TEXT NOT NULL DEFAULT '',
    -- 度量
    items_total     INTEGER NOT NULL DEFAULT 0,
    items_done      INTEGER NOT NULL DEFAULT 0,
    items_failed    INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT,
    ended_at        TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- E1 结构化日志的 trace_id，串起一次任务的所有事件
    trace_id        TEXT NOT NULL,
    task_id         TEXT,
    scene_id        TEXT,
    level           TEXT NOT NULL DEFAULT 'info',  -- info|warn|error
    stage           TEXT NOT NULL DEFAULT '',      -- 'scenes' | 'images' | ...
    message         TEXT NOT NULL DEFAULT '',
    payload_json    TEXT NOT NULL DEFAULT '{}',
    ts              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id, id);
CREATE INDEX IF NOT EXISTS idx_events_task  ON events(task_id, id);
""" + _ELEMENTS_DDL


# 未来 column-add migration
# 例如:
#   2: "ALTER TABLE scenes ADD COLUMN energy_level INTEGER NOT NULL DEFAULT 0;"
MIGRATIONS: dict[int, str] = {}


def _db_path(project_id: str) -> Path:
    return Path(load_settings().projects_dir) / project_id / "project.sqlite"


def _make_conn(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL：读不阻塞写，且对掉电更友好
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(INITIAL_DDL)
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version").fetchone()
    current = int(row["v"] or 0)
    if current < 1:
        from datetime import datetime, timezone
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
            (1, datetime.now(timezone.utc).isoformat()),
        )
    # 增量 migration
    target = SCHEMA_VERSION
    for v in range(current + 1, target + 1):
        sql = MIGRATIONS.get(v)
        if sql:
            conn.executescript(sql)
            from datetime import datetime, timezone
            conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
                (v, datetime.now(timezone.utc).isoformat()),
            )
    conn.commit()


def get_conn(project_id: str) -> sqlite3.Connection:
    """获取项目数据库连接（连接池复用，幂等建 schema）。"""
    with _CONN_LOCK:
        c = _CONNS.get(project_id)
        if c is not None:
            return c
        c = _make_conn(_db_path(project_id))
        _ensure_schema(c)
        _CONNS[project_id] = c
        return c


@contextmanager
def project_db(project_id: str) -> Iterator[sqlite3.Connection]:
    """事务上下文：with project_db(pid) as conn: ... 自动 commit/rollback。"""
    conn = get_conn(project_id)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_all() -> None:
    """关闭所有连接（用于测试 / 进程退出）。"""
    with _CONN_LOCK:
        for c in _CONNS.values():
            try: c.close()
            except Exception: pass
        _CONNS.clear()


def drop_project_db(project_id: str) -> None:
    """删项目时一并删 sqlite 文件 + WAL/SHM 副本。"""
    with _CONN_LOCK:
        c = _CONNS.pop(project_id, None)
        if c is not None:
            try: c.close()
            except Exception: pass
    p = _db_path(project_id)
    for suffix in ("", "-wal", "-shm", "-journal"):
        f = Path(str(p) + suffix)
        if f.exists():
            try: f.unlink()
            except Exception: pass


# ── 全局元素库（轮 2）─────────────────────────────────────────────────────────
# 与项目 SQLite 独立的全局元素数据库，所有项目共享。
# 仅包含 element_folders + elements 两张表（schema 同项目库的元素表）。

_GLOBAL_ELEMENTS_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
""" + _ELEMENTS_DDL


_GLOBAL_KEY = "__global_elements__"
_GLOBAL_MUSIC_KEY = "__global_music__"
_GLOBAL_SFX_KEY   = "__global_sfx__"   # v1.4.8 音效库


# ── 全局音乐库（v1.4.2）─────────────────────────────────────────────────────────
# ACE-Step 生成的音乐落到 APPDATA/LumiCreate-Pro/music/ 下；元数据用 SQLite
# 记录（参数 json + 项目归属，便于"我在哪个项目生成的"查询和清理）

_GLOBAL_MUSIC_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL DEFAULT '',
    file_path    TEXT    NOT NULL DEFAULT '',
    mime         TEXT    NOT NULL DEFAULT 'audio/mpeg',
    project_id   TEXT    NOT NULL DEFAULT '',
    seed         INTEGER NOT NULL DEFAULT 0,
    duration_secs INTEGER NOT NULL DEFAULT 0,
    bpm          INTEGER NOT NULL DEFAULT 120,
    time_signature TEXT  NOT NULL DEFAULT '4',
    language     TEXT    NOT NULL DEFAULT 'zh',
    key_scale    TEXT    NOT NULL DEFAULT 'C major',
    tags         TEXT    NOT NULL DEFAULT '',
    lyrics       TEXT    NOT NULL DEFAULT '',
    bytes        INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tracks_project ON tracks(project_id);
CREATE INDEX IF NOT EXISTS idx_tracks_created ON tracks(created_at DESC);
"""


def _global_music_path() -> Path:
    return SETTINGS_PATH.parent / "music.sqlite"


def _ensure_global_music_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_GLOBAL_MUSIC_DDL)
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version").fetchone()
    if int(row["v"] or 0) < 1:
        from datetime import datetime, timezone
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
            (1, datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()


def get_global_music_conn() -> sqlite3.Connection:
    """全局音乐库连接（同进程单例）。"""
    with _CONN_LOCK:
        c = _CONNS.get(_GLOBAL_MUSIC_KEY)
        if c is not None:
            return c
        path = _global_music_path()
        c = _make_conn(path)
        _ensure_global_music_schema(c)
        _CONNS[_GLOBAL_MUSIC_KEY] = c
        return c


def global_music_root() -> Path:
    """全局音乐文件存储根目录。"""
    p = SETTINGS_PATH.parent / "music"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── 全局音效库（v1.4.8）─────────────────────────────────────────────────────
# 音效 (SFX) 库，用户上传 + ffmpeg 在镜次内特定时间点叠加。
# 与 music 平行的另一套：sfx 是"点状音效"（≤ 几秒，单次触发），music 是"乐曲"。
# 文件存 APPDATA/LumiCreate-Pro/sfx/，元数据 SQLite。

_GLOBAL_SFX_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sfx_clips (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL DEFAULT '',
    category     TEXT    NOT NULL DEFAULT 'uncategorized',
    file_path    TEXT    NOT NULL DEFAULT '',
    mime         TEXT    NOT NULL DEFAULT 'audio/mpeg',
    duration_ms  INTEGER NOT NULL DEFAULT 0,
    tags         TEXT    NOT NULL DEFAULT '',
    bytes        INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sfx_category ON sfx_clips(category);
CREATE INDEX IF NOT EXISTS idx_sfx_created  ON sfx_clips(created_at DESC);
"""


def _global_sfx_path() -> Path:
    return SETTINGS_PATH.parent / "sfx.sqlite"


def _ensure_global_sfx_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_GLOBAL_SFX_DDL)
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version").fetchone()
    if int(row["v"] or 0) < 1:
        from datetime import datetime, timezone
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
            (1, datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()


def get_global_sfx_conn() -> sqlite3.Connection:
    """全局音效库连接（同进程单例）。"""
    with _CONN_LOCK:
        c = _CONNS.get(_GLOBAL_SFX_KEY)
        if c is not None:
            return c
        path = _global_sfx_path()
        c = _make_conn(path)
        _ensure_global_sfx_schema(c)
        _CONNS[_GLOBAL_SFX_KEY] = c
        return c


def global_sfx_root() -> Path:
    """全局音效文件存储根目录。"""
    p = SETTINGS_PATH.parent / "sfx"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _global_elements_path() -> Path:
    # 与 settings.json 同目录（APPDATA/LumiCreate-Pro/）
    return SETTINGS_PATH.parent / "elements.sqlite"


def _ensure_global_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_GLOBAL_ELEMENTS_DDL)
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version").fetchone()
    if int(row["v"] or 0) < 1:
        from datetime import datetime, timezone
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
            (1, datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()


def get_global_elements_conn() -> sqlite3.Connection:
    """全局元素库连接（同进程单例）。"""
    with _CONN_LOCK:
        c = _CONNS.get(_GLOBAL_KEY)
        if c is not None:
            return c
        path = _global_elements_path()
        c = _make_conn(path)
        _ensure_global_schema(c)
        _CONNS[_GLOBAL_KEY] = c
        return c


def global_elements_root() -> Path:
    """全局元素的文件存储根目录。"""
    p = SETTINGS_PATH.parent / "elements"
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def global_elements_db() -> Iterator[sqlite3.Connection]:
    conn = get_global_elements_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
