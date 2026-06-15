"""v1.5.1 回归：测试套件绝不能碰用户真实 APPDATA 的全局库。

历史 bug：conftest 用 os.environ.setdefault('APPDATA', ...)，但 Windows 上 APPDATA
一定已存在 → no-op → isolated_app 的"全局库清理"删掉用户真实的
music.sqlite / elements.sqlite / sfx / prompts（音乐库、元素库每次跑测试就消失）。
现已无条件锁到 .test-tmp，并在清理前加致命断言。这里把不变量显式钉死。
"""
import os


def test_appdata_redirected_to_test_dir():
    assert ".test-tmp" in os.environ.get("APPDATA", ""), \
        "APPDATA 必须被无条件重定向到测试目录，否则会删用户真实数据"


def test_global_store_paths_under_test_tmp(isolated_app, tmp_path):
    """isolated_app 激活时，所有全局库路径必须落在本测试的 tmp 目录下。"""
    from services import db
    assert str(tmp_path) in str(db.SETTINGS_PATH)
    for p in (db._global_music_path(), db._global_elements_path(),
              db._global_sfx_path(), db._global_prompts_path()):
        assert str(tmp_path) in str(p), f"全局库路径逃逸到非测试目录: {p}"
