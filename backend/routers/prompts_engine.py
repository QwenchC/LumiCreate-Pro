"""v1.4.9 提示词插件后端。

全局提示词标签库（不绑定项目）。按 category 分组，用户可：
  - 浏览内置标签（is_builtin=1，画风/构图/光照/情绪/角色/画质/负面词）
  - 添加自定义标签（is_builtin=0）
  - 编辑或删除自定义标签
  - 重置内置库（如果用户手抖删了哪个内置）

设计取舍：
  - 不预先要求用户挑选，开箱即用即得 ~50 个常用漫剧 / SD 通用提示词
  - 用户自定义的标签会和内置标签平铺在同一列表里（按 sort_order 排序）
  - 删除内置标签需要走"reset-builtins"才能恢复，避免误删后凭空消失
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.db import get_global_prompts_conn


router = APIRouter()


# ── 内置标签种子集（v1.4.9 出厂）────────────────────────────────────────────
# tuple: (category, name, content, description)
# category 用中文，content 是实际拼接到提示词里的英文短句。
_BUILTIN_TAGS: list[tuple[str, str, str, str]] = [
    # 画风（style）
    ("画风", "动漫", "anime style", "经典 2D 动漫风"),
    ("画风", "漫画", "manga style, black and white", "黑白漫画风"),
    ("画风", "厚涂", "thick paint, oil painting style", "厚重油画质感"),
    ("画风", "水彩", "watercolor painting, soft brush", "水彩淡彩"),
    ("画风", "吉卜力", "ghibli style, soft pastel", "吉卜力工作室风格"),
    ("画风", "皮克斯", "pixar style, 3d rendered", "皮克斯 3D 渲染"),
    ("画风", "写实", "photorealistic, ultra realistic", "照片级写实"),
    ("画风", "国风", "chinese ink painting style", "中国水墨"),
    ("画风", "赛博朋克", "cyberpunk, neon lights, futuristic", "赛博朋克霓虹"),
    ("画风", "蒸汽朋克", "steampunk, brass and gears", "蒸汽朋克"),

    # 构图 / 镜头（composition）
    ("构图", "特写", "close-up shot, face detail", "面部特写"),
    ("构图", "中景", "medium shot, waist up", "中景半身"),
    ("构图", "远景", "wide shot, full body, environment", "远景全身带环境"),
    ("构图", "俯视", "bird's eye view, top down", "鸟瞰视角"),
    ("构图", "仰视", "low angle, looking up", "低位仰视"),
    ("构图", "倾斜", "dutch angle, tilted camera", "荷兰角斜镜头"),
    ("构图", "过肩", "over-the-shoulder shot", "过肩镜头"),
    ("构图", "侧脸", "side profile, side view", "侧面剪影"),
    ("构图", "背影", "from behind, back view", "背影构图"),

    # 光照（lighting）
    ("光照", "黄昏", "golden hour, warm sunset glow", "黄金时刻暖光"),
    ("光照", "柔光", "soft diffused lighting", "柔和漫射光"),
    ("光照", "轮廓光", "rim lighting, backlit silhouette", "轮廓背光"),
    ("光照", "电影光", "cinematic lighting, dramatic shadows", "电影级光影"),
    ("光照", "低调", "low key lighting, moody dark", "暗调阴郁"),
    ("光照", "高调", "high key lighting, bright clean", "明亮高调"),
    ("光照", "霓虹", "neon glow, cyberpunk colors", "霓虹色光"),
    ("光照", "烛光", "candle light, warm intimate", "烛光温暖"),
    ("光照", "月光", "moonlight, cool blue tone", "月光冷蓝"),

    # 情绪 / 氛围（mood）
    ("情绪", "平静", "peaceful, serene atmosphere", "宁静祥和"),
    ("情绪", "紧张", "tense, suspenseful mood", "紧张悬疑"),
    ("情绪", "忧郁", "melancholic, somber tone", "忧伤"),
    ("情绪", "充满活力", "energetic, dynamic vibe", "活力四射"),
    ("情绪", "神秘", "mysterious, enigmatic", "神秘"),
    ("情绪", "浪漫", "romantic, dreamy atmosphere", "浪漫梦幻"),
    ("情绪", "戏剧化", "dramatic, intense emotion", "戏剧张力"),
    ("情绪", "温馨", "warm cozy heartwarming", "温馨"),
    ("情绪", "压抑", "oppressive, claustrophobic", "压抑窒息"),

    # 角色细节（character）
    ("角色", "精致面容", "detailed face, beautiful features", "面部精致"),
    ("角色", "灵动眼神", "expressive eyes, sparkling", "传神眼眸"),
    ("角色", "飘逸长发", "flowing long hair, dynamic", "飘逸长发"),
    ("角色", "动态姿势", "dynamic pose, energetic stance", "动感姿态"),
    ("角色", "华丽服饰", "intricate clothing, ornate details", "华丽繁复服饰"),
    ("角色", "古风汉服", "hanfu, traditional chinese dress", "汉服"),
    ("角色", "校服", "school uniform, japanese style", "校园制服"),
    ("角色", "西装", "formal suit, business attire", "正装"),

    # 画质（quality）
    ("画质", "最佳质量", "best quality, masterpiece", "通用提质"),
    ("画质", "超清细节", "ultra detailed, intricate", "极致细节"),
    ("画质", "8K", "8k, high resolution", "高分辨率"),
    ("画质", "高对比", "high contrast, vivid colors", "色彩饱满"),
    ("画质", "胶片感", "film grain, analog photo", "胶片质感"),

    # 负面词（negative，提示词通常放 negative_prompt 字段）
    ("负面词", "解剖错误", "bad anatomy, deformed", "防止扭曲"),
    ("负面词", "模糊", "blurry, out of focus", "防止模糊"),
    ("负面词", "低质", "low quality, worst quality", "通用负面"),
    ("负面词", "多肢", "extra limbs, missing fingers", "防止肢体异常"),
    ("负面词", "水印", "watermark, signature, text", "去水印 / 文字"),
    ("负面词", "丑陋", "ugly, disfigured", "防止丑化"),
]


def _seed_builtins_if_empty(conn) -> int:
    """如果 prompt_tags 表里没有任何 is_builtin=1 的行，把出厂集塞进去。
    返回插入的行数。"""
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM prompt_tags WHERE is_builtin = 1"
    ).fetchone()
    if int(row["c"] or 0) > 0:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    for sort, (cat, name, content, desc) in enumerate(_BUILTIN_TAGS):
        conn.execute(
            "INSERT INTO prompt_tags(category, name, content, description, "
            "is_builtin, sort_order, created_at) VALUES(?,?,?,?,?,?,?)",
            (cat, name, content, desc, 1, sort, now),
        )
    conn.commit()
    return len(_BUILTIN_TAGS)


def _row_dict(row) -> dict:
    return {
        "id":          int(row["id"]),
        "category":    row["category"],
        "name":        row["name"],
        "content":     row["content"],
        "description": row["description"],
        "is_builtin":  bool(row["is_builtin"]),
        "sort_order":  int(row["sort_order"]),
        "created_at":  row["created_at"],
    }


# ── Schemas ────────────────────────────────────────────────────────────────────


class PromptTagCreate(BaseModel):
    category:    str = Field("自定义", max_length=80)
    name:        str = Field(..., min_length=1, max_length=120)
    content:     str = Field(..., min_length=1, max_length=2000)
    description: str = Field("", max_length=500)


class PromptTagUpdate(BaseModel):
    category:    Optional[str] = Field(None, max_length=80)
    name:        Optional[str] = Field(None, min_length=1, max_length=120)
    content:     Optional[str] = Field(None, min_length=1, max_length=2000)
    description: Optional[str] = Field(None, max_length=500)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/categories")
async def list_categories():
    """按内置排在前 + 自定义在后的顺序返回去重 category。
    懒触发：首次访问时如果空库就 seed 内置集。"""
    conn = get_global_prompts_conn()
    _seed_builtins_if_empty(conn)
    rows = conn.execute(
        "SELECT category, MIN(is_builtin) AS bm "
        "FROM prompt_tags GROUP BY category "
        "ORDER BY bm DESC, category"
    ).fetchall()
    return {"categories": [r["category"] for r in rows]}


@router.get("/list")
async def list_tags(category: str = "", limit: int = 1000):
    conn = get_global_prompts_conn()
    _seed_builtins_if_empty(conn)
    limit = max(1, min(int(limit), 5000))
    if category:
        rows = conn.execute(
            "SELECT * FROM prompt_tags WHERE category = ? "
            "ORDER BY is_builtin DESC, sort_order ASC, id ASC LIMIT ?",
            (category, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM prompt_tags "
            "ORDER BY is_builtin DESC, category, sort_order ASC, id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"tags": [_row_dict(r) for r in rows]}


@router.post("/tag")
async def create_tag(req: PromptTagCreate):
    conn = get_global_prompts_conn()
    _seed_builtins_if_empty(conn)
    now = datetime.now(timezone.utc).isoformat()
    # 自定义标签放到自己 category 的末尾
    row = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) AS s "
        "FROM prompt_tags WHERE category = ?", (req.category,),
    ).fetchone()
    next_sort = int(row["s"] or -1) + 1
    cur = conn.execute(
        "INSERT INTO prompt_tags(category, name, content, description, "
        "is_builtin, sort_order, created_at) VALUES(?,?,?,?,?,?,?)",
        (req.category, req.name, req.content, req.description,
         0, next_sort, now),
    )
    conn.commit()
    new_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM prompt_tags WHERE id=?", (new_id,),
    ).fetchone()
    return _row_dict(row)


@router.put("/tag/{tag_id}")
async def update_tag(tag_id: int, payload: PromptTagUpdate):
    conn = get_global_prompts_conn()
    row = conn.execute(
        "SELECT * FROM prompt_tags WHERE id=?", (tag_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail="提示词标签不存在")
    if int(row["is_builtin"]) == 1:
        raise HTTPException(400, detail="内置标签不能编辑（请在自定义 category 里新建一个覆盖）")
    fields, values = [], []
    if payload.category is not None:
        fields.append("category = ?"); values.append(payload.category[:80])
    if payload.name is not None:
        fields.append("name = ?"); values.append(payload.name[:120])
    if payload.content is not None:
        fields.append("content = ?"); values.append(payload.content[:2000])
    if payload.description is not None:
        fields.append("description = ?"); values.append(payload.description[:500])
    if fields:
        values.append(tag_id)
        conn.execute(
            f"UPDATE prompt_tags SET {', '.join(fields)} WHERE id=?", values,
        )
        conn.commit()
    row = conn.execute(
        "SELECT * FROM prompt_tags WHERE id=?", (tag_id,)
    ).fetchone()
    return _row_dict(row)


@router.delete("/tag/{tag_id}", status_code=204)
async def delete_tag(tag_id: int):
    conn = get_global_prompts_conn()
    row = conn.execute(
        "SELECT is_builtin FROM prompt_tags WHERE id=?", (tag_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, detail="提示词标签不存在")
    if int(row["is_builtin"]) == 1:
        raise HTTPException(400, detail="内置标签不能删除（如要清掉，可以走 reset-builtins 后整体重置）")
    conn.execute("DELETE FROM prompt_tags WHERE id=?", (tag_id,))
    conn.commit()


@router.post("/reset-builtins")
async def reset_builtins():
    """清空所有 is_builtin=1 的行，重新塞出厂集。用户自定义标签不动。
    用于"我手贱删了一个内置词怎么找回"。"""
    conn = get_global_prompts_conn()
    conn.execute("DELETE FROM prompt_tags WHERE is_builtin = 1")
    conn.commit()
    inserted = _seed_builtins_if_empty(conn)
    return {"ok": True, "reseeded": inserted}
