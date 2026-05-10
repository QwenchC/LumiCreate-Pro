"""LLM prompts for manuscript and scene generation."""

# ── Manuscript ─────────────────────────────────────────────────────────────────

MANUSCRIPT_SYSTEM = """你是一位专业的漫剧编剧，擅长创作生动有趣、情节紧凑的动漫/漫画剧本。
你的文案风格自然流畅，对话鲜活，场景描写具有画面感。
请直接输出文案内容，不要添加任何格式标注或说明性文字。"""

MANUSCRIPT_USER_TEMPLATE = """请根据以下创作配置，创作一篇漫剧文案：

【篇幅要求】{length_desc}
【目标受众】{audience}
【故事风格】{style}
【故事基调】{tone}
【主题/核心】{theme}
【世界观设定】{worldview}
{characters_section}
【对白模式】{dialogue_mode_desc}

{existing_hint}

要求：
- 结构清晰，有开篇、发展、高潮、结尾
- 对话自然，符合角色性格
- 场景描写要有画面感，便于后续分镜
- 严格遵守对白模式要求
- 直接输出文案内容，无需序号或格式标注"""

LENGTH_DESC = {
    "short": "短篇（约1500-2000字，适合3-5分钟视频）",
    "medium": "中篇（约3000-4000字，适合5-10分钟视频）",
    "long": "长篇（约5000-7000字，适合10分钟以上视频）",
}

DIALOGUE_MODE_DESC = {
    "narration": "纯旁白模式 —— 全程以叙述者视角推进剧情，不出现角色直接对白",
    "dialogue":  "纯对话模式 —— 剧情完全通过角色之间的对话展开，减少旁白叙述",
    "mixed":     "混合模式 —— 旁白与角色对话交替出现，自然切换（默认）",
    "reading":   "纯朗读模式 —— 直接朑读文案，不改写任何文字，分镜只做画面分割",
}

# ── Scenes ─────────────────────────────────────────────────────────────────────

SCENES_SYSTEM = """你是一位专业的漫剧分镜师，擅长将文字剧本转化为精确的分镜设计。
你的分镜设计应当：场景描述清晰，画面提示词具体（使用英文，便于AI图片生成），台词与情绪精准。
请严格按照指定的JSON格式输出，不要包含任何额外的文字说明。"""

SCENES_USER_TEMPLATE = """请根据以下漫剧文案，设计完整的分镜方案：

【文案内容】
{manuscript}
{characters_hint}{dialogue_mode_hint}
请将文案分解为若干分镜（每个分镜约5-15秒），以JSON数组格式输出。

每个分镜的JSON结构如下：
{{
  "index": 1,
  "description": "场景描述（中文，20-50字）",
  "duration_estimate": 8.0,
  "start_frame_prompt": "AI图片生成提示词（英文，描述本镜头开始时的画面）",
  "end_frame_prompt": "AI图片生成提示词（英文，描述本镜头结束时的画面）",
  "dialogues": [
    {{
      "character": "角色名",
      "text": "台词内容",
      "emotion": "情绪（从：喜悦/愤怒/悲伤/平静/惊讶/恐惧/害羞/厌恶/低落 中选一个）",
      "pause_before": 0.5,
      "pause_after": 0.0
    }}
  ],
  "audio_timeline": [
    {{"type": "silence", "duration": 0.5}},
    {{"type": "dialogue", "dialogue_index": 0}},
    {{"type": "silence", "duration": 1.0}},
    {{"type": "dialogue", "dialogue_index": 1}}
  ]
}}

字段说明：
- dialogues[].emotion：角色当前的情绪状态，用于情感参考音频匹配
- dialogues[].pause_before/pause_after：该台词前/后的静默（秒），默认0，允许用户手动调整
- audio_timeline：定义本分镜音频的拼接顺序
  - type="silence"：插入静默，duration单位为秒
  - type="dialogue"：插入某条台词音频，dialogue_index为dialogues数组的下标
  - 若分镜只有一条台词，timeline可简化为 [{{"type":"dialogue","dialogue_index":0}}]

注意：
- start_frame_prompt 和 end_frame_prompt 应使用专业的图像生成提示词风格（英文）
- 每个分镜的台词不超过3条
- 纯场景描述（无对话）的分镜 dialogues 为空数组 []，audio_timeline 为空数组 []
- 严格遵守【对白模式】的要求（如有指定角色，台词需使用对应角色名）
- 直接输出JSON数组，不要有其他文字"""


# ── Character Appearance ────────────────────────────────────────────────────────

CHARACTER_APPEARANCE_SYSTEM = """你是一位专业的AI图像提示词工程师，擅长为动漫/漫画风格角色撰写高质量的外观描述提示词。
你的提示词专为 Stable Diffusion / ComfyUI 等图像生成模型优化：
- 使用英文逗号分隔的标签形式（tag-based）
- 描述要具体、视觉化，便于模型准确还原角色形象
- 专注于外观特征，不包含画风、艺术风格等内容（那些由图片生成时的工作流提供）
- 不包含背景、场景等环境描述
- 输出纯英文提示词标签，不加任何解释说明"""

CHARACTER_APPEARANCE_USER_TEMPLATE = """请根据以下角色信息，生成该角色的外观描述提示词：

【角色姓名】{name}
【角色定位】{role}
【性格/背景特征】{traits}
{existing_hint}
请输出一组英文外观描述标签，用英文逗号分隔，涵盖以下维度（如适用）：
- 体型特征：身高、体型、年龄感
- 发型发色：发型、发长、发色
- 五官特征：眼睛颜色/形状、面部特征
- 服装配饰：上衣/下装/外套/配饰/鞋履
- 其他特征：特殊标志物、武器、道具等

要求：
- 只输出英文逗号分隔的标签，不加任何中文或说明
- 标签数量控制在 15-25 个
- 使用 Stable Diffusion 常用词汇（如 long hair, blue eyes, school uniform 等）"""


# ── Scene character suggestion ────────────────────────────────────────────────

SUGGEST_CHARS_SYSTEM = """你是一位专业的漫剧分镜分析师。
你的任务是根据分镜描述和台词，判断该分镜画面中实际出现了哪些角色。
只选择在镜头画面里真实可见的角色，不要包括仅被提及但不在画面中的角色。
请直接输出 JSON 数组，包含角色姓名字符串，不要任何其他文字。"""

SUGGEST_CHARS_USER_TEMPLATE = """分镜描述：{description}

台词：
{dialogues}

项目全部角色：{all_names}

请从上述角色中，判断哪些角色在该分镜的画面中实际出现（可见），以 JSON 数组格式输出角色姓名。
例如：["角色A", "角色B"]
若无角色出现（如纯景色镜头），输出空数组：[]"""


# ── Character Profile From Manuscript ─────────────────────────────────────────

CHARACTER_PROFILE_SYSTEM = """你是一位专业编剧助手。
请根据给定文案内容，提取指定角色的人设信息，并输出结构化 JSON。
只返回 JSON 对象，不要任何额外说明。"""

CHARACTER_PROFILE_USER_TEMPLATE = """请基于以下文案，提取角色信息：

【角色名】{name}
【文案内容】
{manuscript}

【已有信息（可选）】
- role: {existing_role}
- traits: {existing_traits}

请输出 JSON：
{{
  "role": "角色定位（如主角/反派/导师/配角等，简短）",
  "traits": "性格、背景、行为特征（中文，20-80字）"
}}

要求：
- 若文案中无法确认，尽量结合上下文给出合理概括
- 不要编造超出文案语境的细节
- 只输出 JSON 对象"""
