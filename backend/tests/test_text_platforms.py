"""v1.4.11+ 文本引擎平台清单测试。

不影响现有 LLM 驱动测试 —— driver 在 services/llm.py 没有改动，
仅"配置/平台管理"层加了 builtin 列表 + custom CRUD + 平台清单 API。
"""
import pytest


def test_builtin_platforms_include_volcengine_and_common_ones():
    from services.text_platforms import BUILTIN_TEXT_PLATFORMS
    ids = {p.id for p in BUILTIN_TEXT_PLATFORMS}
    # 这些是真实存在 / 常用的，必须保留
    must = {"ollama", "lmstudio", "deepseek", "bailian", "openai_compat",
            "volcengine", "moonshot", "openai", "siliconflow"}
    assert must.issubset(ids), f"missing builtin: {must - ids}"
    # volcengine 默认指向北京 Ark
    volc = next(p for p in BUILTIN_TEXT_PLATFORMS if p.id == "volcengine")
    assert "ark.cn-beijing.volces.com" in volc.base_url
    # ollama 标记为 is_ollama=True
    ol = next(p for p in BUILTIN_TEXT_PLATFORMS if p.id == "ollama")
    assert ol.is_ollama is True


def test_get_text_platforms_returns_builtin(isolated_app):
    """空 settings 时 /settings/text-platforms 仅返 builtin。"""
    client = isolated_app["client"]
    r = client.get("/api/settings/text-platforms")
    assert r.status_code == 200
    data = r.json()
    assert len(data["platforms"]) >= 10
    assert all(p["is_builtin"] for p in data["platforms"])
    # builtin_ids 暴露给前端做"是否可删"判断
    assert "ollama" in data["builtin_ids"]
    assert "volcengine" in data["builtin_ids"]


def test_add_custom_platform_round_trip(isolated_app):
    """POST 新增 → GET 返回时包含 → DELETE 又消失。"""
    client = isolated_app["client"]
    r = client.post("/api/settings/text-platforms", json={
        "id": "my_corp",
        "label": "我司私有 LLM",
        "base_url": "https://llm.mycorp.com/v1",
        "model_hint": "qwen2.5-72b",
    })
    assert r.status_code == 200

    r = client.get("/api/settings/text-platforms")
    found = next((p for p in r.json()["platforms"] if p["id"] == "my_corp"), None)
    assert found is not None
    assert found["is_builtin"] is False
    assert found["base_url"] == "https://llm.mycorp.com/v1"

    r = client.delete("/api/settings/text-platforms/my_corp")
    assert r.status_code == 204
    r = client.get("/api/settings/text-platforms")
    assert all(p["id"] != "my_corp" for p in r.json()["platforms"])


def test_add_custom_platform_rejects_builtin_id_conflict(isolated_app):
    client = isolated_app["client"]
    r = client.post("/api/settings/text-platforms", json={
        "id": "volcengine",   # builtin 撞名
        "label": "x", "base_url": "https://x",
    })
    assert r.status_code == 400
    assert "冲突" in r.json()["detail"]


def test_delete_builtin_platform_is_forbidden(isolated_app):
    client = isolated_app["client"]
    r = client.delete("/api/settings/text-platforms/ollama")
    assert r.status_code == 400
    assert "不可删除" in r.json()["detail"]


def test_legacy_engine_type_string_still_loads():
    """老 settings.json 里 engine_type='deepseek' 不能因为 Literal 收紧而炸。
    v1.4.11+ 改成 free str 后必须接受任意值。"""
    from config import AppSettings
    legacy = {
        "text_engine": {
            "engine_type": "deepseek",   # builtin id 之一
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
        }
    }
    s = AppSettings(**legacy)
    assert s.text_engine.engine_type == "deepseek"
    assert s.text_engine.base_url == "https://api.deepseek.com"
    # 新增字段默认空 list
    assert s.text_engine.custom_platforms == []


def test_arbitrary_string_engine_type_accepted():
    """支持任意新 id（用户自定义平台 / 未来 builtin）。"""
    from config import AppSettings
    s = AppSettings(**{
        "text_engine": {"engine_type": "my_brand_new_platform"}
    })
    assert s.text_engine.engine_type == "my_brand_new_platform"
