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

SCENES_SYSTEM = """你是一位专业的漫剧分镜师，擅长把文字剧本拆成"有机分镜"——按情节节点、视角变化、关键动作、情绪转折和镜头语言自然切分，而不是按字数机械切。

【核心原则——宁多不少】
- 用户使用本地 AI 图片/视频生成，单张画面承载内容越少越稳定。所以**分镜数量要尽量多，宁可碎、不要长**。
- 任何下列情况都要单独成一镜，不允许合并：
  1. 场景/地点变化（街上 → 屋内）
  2. 视角/景别变化（远景 → 近景、面部特写 → 全景）
  3. 镜头主体变化（A 出现 → B 出现 → 物件特写）
  4. 时间跳跃（白天 → 夜晚、片刻后 → 几小时后）
  5. 关键情绪/态度转折（平静 → 愤怒）
  6. 一个动作的开始/结果（举起酒杯/砸到地上）
  7. 旁白与对话之间的承接
- 单镜时长 **3-8 秒**为佳，超过 10 秒就要再拆。**不要追求"每镜都是完整一句话"**——半句话/一个停顿/一个反应镜头都可以单独成镜。
- 如果文案只有 200 字也可以拆 10-15 镜。**镜次多 ≠ 画面碎，反而 = 节奏好**。

【描述与提示词】
- 场景描述清晰、具体到画面元素（光线、角度、人物位置、动作瞬间）
- 首末帧英文提示词具体到能直接给 SD/ComfyUI 出图
- 台词与情绪精准

请严格按指定 JSON 格式输出，不要包含任何额外文字说明。"""

SCENES_USER_TEMPLATE = """请根据以下漫剧文案，设计完整的分镜方案：

【文案内容】
{manuscript}
{characters_hint}{dialogue_mode_hint}
请按上述"有机分镜"原则把文案拆成尽可能多的分镜（每镜 3-8 秒，宁多不少），以 JSON 数组格式输出。
**重要**：拆得碎不是缺点，是优点——多一个反应镜头/特写镜头/留白镜头都比一个长镜头好。
即使文案只有 200 字，分镜数量也可达到 10-20 个。

每个分镜的JSON结构如下：
{{
  "index": 1,
  "description": "场景描述（中文，完整描述该镜头的场景、人物、动作、氛围，不限字数）",
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
- 专注于固定外观特征（发型、服装、体型、五官等），不包含任何情绪、表情或神态描述（例如 smile、sad expression、angry、crying 等一律不写，表情由每帧提示词单独控制）
- 不包含画风、艺术风格等内容（那些由图片生成时的工作流提供）
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

严格禁止：
- 不得包含任何表情或情绪标签（如 smile、smiling、happy、sad、angry、crying、tears、grin、frown、expression 等）
- 表情应留给每帧的提示词单独指定，角色外观描述只负责固定视觉特征

要求：
- 只输出英文逗号分隔的标签，不加任何中文或说明
- 标签数量控制在 15-25 个
- 使用 Stable Diffusion 常用词汇（如 long hair, blue eyes, school uniform 等）"""


# ── Scene character suggestion ────────────────────────────────────────────────

SUGGEST_CHARS_SYSTEM = """你是一位专业的漫剧分镜分析师。
你的任务是根据完整文案、分镜描述和台词，判断该分镜画面中实际出现了哪些角色。

重要规则：
- 当描述或台词中出现"他"、"她"、"他们"、"她们"等人称代词时，必须结合文案上下文推断代词所指的具体角色姓名。
- 只选择在镜头画面里真实可见的角色，不要包括仅被提及但不在画面中的角色。
- 如果无法确认某代词所指角色，可从文案前后文中推断出场最合理的角色。
请直接输出 JSON 数组，包含角色姓名字符串，不要任何其他文字。"""

SUGGEST_CHARS_USER_TEMPLATE = """完整文案（用于理解人称代词和情节背景）：
{manuscript}

---
当前分镜描述：{description}

台词：
{dialogues}

项目全部角色：{all_names}

请结合文案上下文，将描述和台词中的人称代词（他/她/他们等）还原为具体角色姓名，然后判断哪些角色在该分镜的画面中实际出现（可见）。
以 JSON 数组格式输出角色姓名。
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


# ── Frame Prompt (image generation) ───────────────────────────────────────────

FRAME_PROMPT_SYSTEM = (
    "You are an expert AI image prompt engineer for local text-to-image models (Stable Diffusion / ComfyUI).\n"
    "Write two concise English image prompts: one for the START frame and one for the END frame of a short scene clip.\n\n"
    "STRICT RULES — follow exactly:\n"
    "1. LANGUAGE: Write entirely in English. Character names may keep their original spelling (e.g. Chinese names are fine).\n"
    "2. CHARACTERS — most critical rule: You may include ONLY characters explicitly listed in the Characters block. "
    "Do NOT add, infer, or import any other character from the description, dialogues, or background knowledge. "
    "If no characters are listed, describe the scene without any named person (environment/object shot is fine).\n"
    "3. SEQUENTIAL FRAMING — the start frame and end frame are TWO DIFFERENT MOMENTS of the same scene. "
    "A character listed in the Characters block does NOT have to appear in BOTH frames. "
    "Read the description and dialogues in narrative order, then decide for each frame which subset of the listed characters is naturally present:\n"
    "   - If the description shows entrance / departure / handover / camera cut (e.g. 'A walks in, then B answers', 'A leaves, B stays'), put A in only the start frame and B in only the end frame.\n"
    "   - If the description treats both characters as continuously co-present (e.g. 'A and B argue across the table'), both may appear in both frames.\n"
    "   - When unsure, prefer a single character per frame — fewer characters per frame produces dramatically better local-model output.\n"
    "4. LOCAL MODEL LIMITATION: Local models produce poor results with many characters in one frame. "
    "Aim for 1 character per frame. 2 is a hard maximum; never put 3+ in a single frame even if 3 are listed (split them across start/end instead).\n"
    "5. APPEARANCE ISOLATION: Each character's visual tags belong strictly to that character alone. "
    "Never mix, blend, or transfer any visual feature (hair, clothing, accessories, body shape) between characters.\n"
    "6. ACTION / POSITION ISOLATION — CRITICAL when 2 characters share a frame: "
    "Each character's actions, gestures, pose, facial expression, and spatial position belong strictly to that character. "
    "NEVER swap actions between characters. NEVER use pronouns (he / she / they) when 2 characters are present — always write the character's name immediately before their action "
    "(e.g. 'Alice raises her sword on the left, Bob recoils on the right' — NOT 'she raises a sword while he recoils').\n"
    "7. NO STYLE TAGS: Do not include art style, painting style, or rendering style "
    "(no 'anime style', 'watercolor', '3D render', 'photorealistic', 'cartoon', 'manga', 'illustration', etc.).\n"
    "8. CONTENT: Describe environment, lighting, mood, composition, and each present character's pose and expression.\n"
    "9. OUTPUT: Return ONLY a JSON object with keys \"start_frame_prompt\" and \"end_frame_prompt\". No extra text."
)

FRAME_PROMPT_USER_TEMPLATE = (
    "{char_block}"
    "Scene description: {description}\n"
    "{dialogue_lines}"
    "\nNote: any pronouns (he/she/they/him/her/他/她) in the description or dialogue refer to the characters listed above. "
    "Resolve them accordingly — do not introduce any character not listed above.\n"
    "Decide for EACH frame independently which subset of the listed characters is naturally present at that moment. "
    "Bind every action / gesture / position to a specific character's name; never swap actions between characters.\n"
    "Return JSON only: {{\"start_frame_prompt\": \"...\", \"end_frame_prompt\": \"...\"}}"
)


# ── Video Prompt ───────────────────────────────────────────────────────────────

VIDEO_PROMPT_SYSTEM = (
    "You are an expert video prompt engineer for AI video generation models (e.g. WAN2.1, LTX-Video, CogVideoX).\n\n"
    "Write ONE detailed English video generation prompt for a short animated scene clip (4\u201315 seconds).\n\n"
    "A great video prompt focuses on MOTION \u2014 what changes over time. Include:\n"
    "1. CHARACTER ACTIONS: What each listed character does \u2014 body movements, gestures, facial expression changes.\n"
    "2. CAMERA: Camera behavior (static, slow push-in, gentle pan, zoom out, handheld shake, etc.).\n"
    "3. ATMOSPHERE: Lighting, mood progression, environmental details within the clip.\n\n"
    "STRICT RULES:\n"
    "- LANGUAGE: Write entirely in English. Character names may keep their original spelling (e.g. Chinese names are fine).\n"
    "- CHARACTERS: Include ONLY the characters explicitly listed in the Characters block. "
    "Do NOT introduce or mention any other character.\n"
    "- Use each character's name explicitly. NEVER use pronouns (he/she/they/him/her).\n"
    "- Do NOT invent or repeat appearance tags \u2014 just name characters and describe their actions and expressions.\n\n"
    "OUTPUT: Plain English, 3\u20135 cinematic sentences. No style tags, no JSON, no markdown."
)

VIDEO_PROMPT_USER_TEMPLATE = (
    "Story context (for narrative understanding only):\n"
    "{manuscript}\n\n"
    "This is scene {scene_index} of {total_scenes}.\n\n"
    "Scene description: {description}\n"
    "{characters_block}"
    "{dialogues_block}"    "Note: any pronouns (he/she/they/him/her/他/她) in the description or dialogue refer to the characters listed above. "
    "Resolve them accordingly.\n"    "Start frame visual: {start_frame_prompt}\n"
    "End frame visual: {end_frame_prompt}\n\n"
    "Write an English video generation prompt for this scene. "
    "Include ONLY the characters listed above \u2014 no others. "
    "Focus on motion, expressions, and camera work."
)
