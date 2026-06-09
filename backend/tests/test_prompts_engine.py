"""v1.4.9 提示词插件后端测试：
内置 seed 触发 / 列表 / CRUD / 内置标签删改保护 / reset。"""

import pytest


@pytest.fixture
def client(isolated_app):
    """复用 isolated_app（已清掉全局 prompts.sqlite）。"""
    return isolated_app["client"]


def test_categories_auto_seeds_builtin_on_first_hit(client):
    """空库首次 GET /categories 应该懒触发 seed，把内置类目都返回回来。"""
    r = client.get("/api/prompts/categories")
    assert r.status_code == 200
    cats = r.json()["categories"]
    # v1.4.9 出厂内置至少 7 类
    for must in ("画风", "构图", "光照", "情绪", "角色", "画质", "负面词"):
        assert must in cats, f"missing builtin category {must!r}; got {cats}"


def test_list_returns_builtin_tags_with_metadata(client):
    r = client.get("/api/prompts/list?category=画风")
    assert r.status_code == 200
    tags = r.json()["tags"]
    assert len(tags) >= 5
    # 内置标签 is_builtin=True、有英文 content
    for t in tags:
        assert t["category"] == "画风"
        assert t["is_builtin"] is True
        assert t["name"]    # 中文显示名
        assert t["content"]  # 英文 content
        assert "id" in t


def test_create_custom_tag_round_trip(client):
    payload = {
        "category":    "自定义",
        "name":        "我的镜头",
        "content":     "extreme close-up, macro detail",
        "description": "test desc",
    }
    r = client.post("/api/prompts/tag", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_builtin"] is False
    assert body["name"] == "我的镜头"
    tag_id = body["id"]

    # list 里能看到
    r = client.get("/api/prompts/list?category=自定义")
    assert any(t["id"] == tag_id for t in r.json()["tags"])

    # categories 也能看到这个新类目
    r = client.get("/api/prompts/categories")
    assert "自定义" in r.json()["categories"]


def test_update_custom_tag(client):
    r = client.post("/api/prompts/tag", json={
        "category": "自定义", "name": "原名",
        "content": "old content",
    })
    tag_id = r.json()["id"]

    r = client.put(f"/api/prompts/tag/{tag_id}", json={
        "name": "改后名", "content": "new content",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "改后名"
    assert body["content"] == "new content"
    assert body["is_builtin"] is False


def test_delete_custom_tag(client):
    r = client.post("/api/prompts/tag", json={
        "category": "自定义", "name": "to-delete",
        "content": "x",
    })
    tag_id = r.json()["id"]
    r = client.delete(f"/api/prompts/tag/{tag_id}")
    assert r.status_code == 204
    # 已不存在
    r = client.put(f"/api/prompts/tag/{tag_id}", json={"name": "x"})
    assert r.status_code == 404


def test_cannot_edit_or_delete_builtin_tag(client):
    """内置标签必须受保护，否则用户改坏一个都不知道。"""
    # 触发 seed
    client.get("/api/prompts/categories")
    r = client.get("/api/prompts/list?category=画风")
    builtin_id = r.json()["tags"][0]["id"]

    r = client.put(f"/api/prompts/tag/{builtin_id}", json={"name": "黑客改"})
    assert r.status_code == 400
    assert "内置" in r.json()["detail"]

    r = client.delete(f"/api/prompts/tag/{builtin_id}")
    assert r.status_code == 400


def test_reset_builtins_restores_factory(client):
    """假装用户的库被破坏了（直接 DB 清掉），reset-builtins 必须把出厂集
    重新塞回，且不影响自定义标签。"""
    from services.db import get_global_prompts_conn
    # 先建一个自定义
    r = client.post("/api/prompts/tag", json={
        "category": "自定义", "name": "保留我",
        "content": "keep me",
    })
    custom_id = r.json()["id"]

    # 直接 DB 把内置清掉
    conn = get_global_prompts_conn()
    conn.execute("DELETE FROM prompt_tags WHERE is_builtin = 1")
    conn.commit()
    n_after_purge = conn.execute(
        "SELECT COUNT(*) AS c FROM prompt_tags WHERE is_builtin = 1"
    ).fetchone()["c"]
    assert n_after_purge == 0

    # reset
    r = client.post("/api/prompts/reset-builtins")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["reseeded"] >= 50   # 出厂至少 50 个

    # 自定义仍在
    r = client.get("/api/prompts/list?category=自定义")
    assert any(t["id"] == custom_id for t in r.json()["tags"])


def test_create_tag_validates_required_fields(client):
    """name 和 content 不能为空。"""
    r = client.post("/api/prompts/tag", json={"name": "", "content": "x"})
    assert r.status_code in (400, 422)
    r = client.post("/api/prompts/tag", json={"name": "ok", "content": ""})
    assert r.status_code in (400, 422)


def test_list_orders_builtin_before_custom_within_category(client):
    """同 category 下，is_builtin=1 排前面（用户自定义补在末尾）。"""
    client.get("/api/prompts/categories")   # seed
    r = client.post("/api/prompts/tag", json={
        "category": "画风", "name": "我的画风",
        "content": "my style",
    })
    custom_id = r.json()["id"]
    r = client.get("/api/prompts/list?category=画风")
    tags = r.json()["tags"]
    # 找到自定义在 builtin 之后
    builtin_indices = [i for i, t in enumerate(tags) if t["is_builtin"]]
    custom_index = next(i for i, t in enumerate(tags) if t["id"] == custom_id)
    assert custom_index > max(builtin_indices)
