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


# ── v1.6.2: 智能分镜（导演式，分段多次续接）─────────────────────────────────────
# 对【文案片段】做电影感分镜；多次调用续接整篇，每段都能给丰富描述、不被单次输出上限逼简化。

SMART_SCENES_SYSTEM = (
    "你是一位资深漫剧【导演 + 分镜师】。把给定文案【片段】拆成有电影感的分镜，像导演一样安排镜头与节奏，"
    "让剧情靠【画面、动作、镜头语言、表情与环境氛围】演绎，而不是靠机械旁白堆砌、也不要按句子机械切分。\n\n"
    "原则：\n"
    "1. 理解剧情与情绪，按“情节节点 / 视角切换 / 关键动作 / 情绪转折 / 镜头语言”自然切分。\n"
    "2. 每个分镜给【具体、可拍】的画面描述：景别(特写/近景/中景/全景/远景)与运镜(推/拉/摇/移/跟/环绕)、"
    "构图、角色动作与表情变化、环境与光影氛围。即便本地 AI 视频表现力有限，也要让画面把剧情演清楚、让观众看懂。\n"
    "3. 控制节奏：关键情节多给镜头、过场从简，避免拖沓；宁可镜头短而精，不要又长又空。\n"
    "4. 对白按【对白模式】处理：纯旁白=不写角色对白、靠画面叙事；纯对话=角色开口；混合=交替；"
    "纯朗读=整段作画外音、画面贴合文意。\n"
    "5. 【重要】只对【本片段】做分镜，后续片段会另行续接——【不要】为了把全文塞进一次输出而压缩描述质量。\n\n"
    "输出：JSON 数组，每个元素 {\"index\":int, \"description\":丰富具体的中文画面描述, "
    "\"duration_estimate\":秒(3-15的浮点), \"start_frame_prompt\":\"\", \"end_frame_prompt\":\"\", "
    "\"dialogues\":[{\"character\":说话人, \"text\":台词, \"emotion\":情绪}]}。"
    "只输出 JSON 数组，不要解释、不要 markdown、不要代码块。"
)

SMART_SCENES_USER_TEMPLATE = (
    "{characters_hint}{dialogue_mode_hint}{continuity_hint}"
    "【需要分镜的文案片段】（只对这一段做分镜，不要分到这段以外的内容）：\n"
    "{segment}\n\n"
    "请对上面这段文案做有电影感的分镜，分镜编号从 {next_index} 开始，输出 JSON 数组。"
)


# ── Character Appearance ────────────────────────────────────────────────────────

CHARACTER_APPEARANCE_SYSTEM = """你是一位专业的AI图像提示词工程师，擅长为动漫/漫画风格角色撰写高质量的外观描述提示词。
你的提示词专为 Stable Diffusion / ComfyUI 等图像生成模型优化：
- 使用英文逗号分隔的标签形式（tag-based）
- 描述要具体、视觉化，便于模型准确还原角色形象
- 专注于固定外观特征（发型、服装、体型、五官等），不包含任何情绪、表情或神态描述（例如 smile、sad expression、angry、crying 等一律不写，表情由每帧提示词单独控制）
- 不包含画风、艺术风格等内容（那些由图片生成时的工作流提供）
- 不包含背景、场景等环境描述
- 输出纯英文提示词标签，不加任何解释说明"""

DERIVE_APPEARANCE_SYSTEM = """你是一位专业的AI图像提示词工程师，为动漫/漫画角色撰写「变体外观」提示词。
用户会给你该角色的【常态外观提示词】和一句【变体说明】（描述这个分镜/场景里该角色与常态的不同，例如换装、躺床、受伤、不同发型等）。
你的任务：在【尽量保留常态外观中的角色身份特征】（如发色发型、五官、体型、年龄感等不该变的识别性特征）的前提下，
按变体说明替换/新增相应的标签（如服装、姿态相关的可见特征、状态），输出该变体的【完整】英文外观提示词。
规则：
- 输出英文逗号分隔标签（tag-based），可直接用于 Stable Diffusion / ComfyUI
- 保留常态里属于「身份」的特征（发色、发型、瞳色、五官、体型、年龄）；当变体说明与常态冲突时（如常态「校服」vs 变体「睡衣」），以变体说明为准、替换掉冲突的常态标签
- 只描述固定可见外观与该变体的状态特征，不写表情/情绪（如 smile、sad），不写画风、不写背景场景
- 输出纯英文标签，不加任何解释说明"""

DERIVE_APPEARANCE_USER_TEMPLATE = """请据下面信息生成该角色【某个变体外观】的完整英文外观提示词：

【角色姓名】{name}
【常态外观提示词（身份基线，尽量保留其中的身份特征）】
{base_appearance}

【变体说明（这个外观与常态的不同点）】
{variation}

要求：
- 输出一组英文逗号分隔标签，15-28 个
- 保留常态中的身份特征（发色发型瞳色五官体型年龄等），按变体说明替换/新增服装姿态状态等可见特征
- 不含表情/情绪、不含画风、不含背景"""

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


# ── i2i Frame Prompt (image edit / img2img — Flux.2-Klein etc.) ───────────────
#
# 与 t2i 不同：i2i 模型基于参考图编辑。Prompt 是"编辑指令"，告诉模型如何把
# 参考图变成目标画面：
#   - 单图参考：通常是"在 reference 1 的基础上修改 X / 把人物放进 Y 场景"
#   - 双图参考：通常是"把 reference 1 中的人物放到 reference 2 的场景里"
#
# Flux.2-Klein 编辑模型不需要风格 token；它复刻参考图的风格。

I2I_PROMPT_SYSTEM = (
    "You are an expert AI image EDIT prompt engineer for ComfyUI image-edit models "
    "(Flux.2 Klein image edit / similar img2img models).\n\n"
    "These models DO NOT generate from scratch — they EDIT or COMPOSE existing reference images. "
    "Your prompt is an EDIT INSTRUCTION, not a scene description. The reference images are passed alongside.\n\n"
    "Two reference-image patterns:\n"
    "  - SINGLE REF (1 image): the reference is usually a character portrait OR a scene element. "
    "Write an instruction that places / poses / animates the subject from the reference into the target moment.\n"
    "  - DOUBLE REF (2 images): typically Image 1 = character, Image 2 = scene/element. "
    "Write an instruction that composites them: put the subject from Image 1 into the setting from Image 2.\n\n"
    "STRICT RULES:\n"
    "1. LANGUAGE: English only. Character names may keep their original spelling.\n"
    "2. REFERENCE IDENTIFICATION: Refer to references as 'image 1', 'image 2'. "
    "Describe what each contains before instructing the edit, so the model anchors correctly.\n"
    "3. EDIT INSTRUCTION FORM: Use imperative verbs such as 'place', 'pose', 'put', 'compose', 'add', 'replace', 'merge'. "
    "Avoid scene-description prose (no long descriptive paragraphs).\n"
    "4. PRESERVE IDENTITY: Identity-preserving instructions: 'keeping the same character / outfit / face from image 1'.\n"
    "5. NO STYLE TAGS: Do NOT add art-style words ('anime style', 'watercolor', '3D render', 'cartoon'). "
    "i2i models inherit the reference's style automatically — adding tags causes drift.\n"
    "6. CHARACTERS — only the listed characters may appear; do not invent others.\n"
    "7. ACTIONS: Describe pose, expression and action concisely. Bind every action to a named character.\n"
    "8. SEQUENTIAL FRAMING: start frame and end frame are TWO DIFFERENT MOMENTS — write distinct edit instructions for each.\n"
    "9. OUTPUT: Return ONLY a JSON object with keys \"start_frame_prompt\" and \"end_frame_prompt\". No extra text."
)

I2I_PROMPT_USER_TEMPLATE = (
    "{char_block}"
    "{ref_block}"
    "Scene description: {description}\n"
    "{dialogue_lines}"
    "\nWorkflow type: {workflow_kind} ({ref_count} reference image{ref_count_plural})\n"
    "Write an EDIT INSTRUCTION for the start frame and one for the end frame. "
    "Treat the references as fixed inputs and tell the model how to transform / compose them into the target moment.\n"
    "Return JSON only: {{\"start_frame_prompt\": \"...\", \"end_frame_prompt\": \"...\"}}"
)


# ── Music Prompt + Lyrics (ACE-Step v1.5)─────────────────────────────────────
#
# 用户给一段高层简介 → LLM 同时产出"标签段落"+"分段歌词"。
# 标签段落直接喂给 ACE-Step 的 tags 输入（中文长描述，越具体越好）；
# 歌词用 [Intro] / [Verse] / [Chorus] / [Outro] 等英文段落标记包裹内容，
# 段落标记可携带英文环境描述（intro / outro 处尤其有效）。

MUSIC_PROMPT_SYSTEM = (
    "You are an expert music prompt + lyricist for ACE-Step v1.5 and similar "
    "text-conditioned music models.\n\n"
    "Given a user's high-level brief for a song, produce TWO outputs:\n"
    "  1. tags — a SINGLE rich CHINESE paragraph (150-400 chars) describing the song's "
    "GENRE, INSTRUMENTS, ARRANGEMENT details, VOCAL STYLE, MOOD, MIX DYNAMICS, and "
    "INTRO / OUTRO flourishes. Use vivid sensory language — name specific instruments "
    "and textures (失真电吉他 / 古筝扫弦 / 鼻音 / 强混声), describe section contrast, "
    "describe instrument layering and panning. Richer stylistic descriptions reliably "
    "produce better music.\n"
    "  2. lyrics — sectioned with English-marker headers in brackets, e.g.:\n"
    "       [Intro — descriptive English of the opening sound]\n"
    "       [Verse 1]\n"
    "       (Chinese / target-language verse content here)\n"
    "       [Pre-Chorus]\n"
    "       [Chorus]\n"
    "       [Verse 2]\n"
    "       [Bridge]\n"
    "       [Outro — descriptive English of the closing sound]\n\n"
    "STRUCTURE RULES (pick based on target duration):\n"
    "  - < 45s: [Intro] + [Verse 1] + [Chorus] + [Outro]\n"
    "  - 45-90s: + [Pre-Chorus] before Chorus\n"
    "  - 90-150s: + [Verse 2] + [Chorus] (repeat)\n"
    "  - 150s+: optionally + [Bridge] between repeats\n\n"
    "LANGUAGE: verse / chorus body MUST be in the requested target language "
    "(default 中文 if not specified). Section markers stay English. Intro/Outro "
    "bracket descriptions stay English.\n\n"
    "** TAGS — CRITICAL DO-NOT-INCLUDE LIST: **\n"
    "Tempo / BPM / 速度 / 节拍数, time signature / 拍号 / 4/4 / 3/4, musical key / "
    "key signature / 调式 / 大调 / 小调 / major / minor, target duration / 时长 / "
    "song length, all live in SEPARATE structured form fields that the user already "
    "configured. The tags paragraph is STYLE ONLY. DO NOT mention any specific BPM "
    "number, any time signature, any key/scale name (e.g. 不要写 \"120 BPM\" / "
    "\"4/4 拍\" / \"C 大调\" / \"A minor\"), and DO NOT mention duration in seconds. "
    "If you need to convey energy / tempo feel use words like 急促 / 舒缓 / 鼓点密集 "
    "WITHOUT a number. Violating this rule degrades music quality because parameters "
    "get double-applied.\n\n"
    "OUTPUT: Return ONLY a JSON object with keys \"tags\" and \"lyrics\". No prose, "
    "no markdown fences, no extra commentary. Both values are strings; \"lyrics\" "
    "is multi-line with \\n separators between sections."
)

# 节奏/调式/时长是结构化参数，传给 LLM 仅作"配套写歌结构 + 情绪"的隐式参考，
# **不要让 LLM 把这些数字直接抄进 tags**。我们用 'hint' 而非显式 "BPM" / "key" 字样，
# 并在每一项后加显式禁止说明。
MUSIC_PROMPT_USER_TEMPLATE = (
    "Brief (the only stylistic source — base tags + lyrics on this): {user_request}\n"
    "Verse language: {language_display}\n"
    "\n"
    "Structural hints (use INTERNALLY to pick section count + rhythmic feel only — "
    "DO NOT mention these numbers / labels in the tags output):\n"
    "  - Duration hint: {duration_seconds}s\n"
    "  - Tempo hint: {bpm} BPM (express as 急促/舒缓 etc., never write the number)\n"
    "  - Time signature hint: {time_signature}/4 (never write \"4/4\" in tags)\n"
    "  - Key hint: {key_scale} (never write the key name in tags)\n"
    "{project_context}"
    "\nReturn JSON only: {{\"tags\": \"...\", \"lyrics\": \"...\"}}"
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
    "- Do NOT invent or repeat appearance tags \u2014 just name characters and describe their actions and expressions.\n"
    "- TEMPORAL ORDER (important): Describe actions, the appearance of things, and movements in the ORDER THEY HAPPEN IN TIME. "
    "Video models read the prompt roughly as a left-to-right timeline, so words placed earlier tend to render as happening first. "
    "Without breaking logic, arrange clauses/sentences so the sequence of what appears or moves matches the actual chronology of the clip "
    "(e.g. write 'Mia turns toward the door, the door slowly opens, then a figure steps through' \u2014 in that order). "
    "Use ordering/time cues (first, then, as, after) to make the sequence explicit.\n\n"
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


# ── v1.4.13: Ideogram 4 结构化 JSON caption 生成（分两步，避免单次响应过大）──

IDEOGRAM_OVERVIEW_SYSTEM = (
    "You are a prompt engineer for Ideogram 4, an image model trained on structured JSON captions.\n\n"
    "Given a scene description (any language), produce STEP 1 of the caption: the overview fields.\n\n"
    "Output STRICT JSON with EXACTLY these keys:\n"
    '{\n'
    '  "high_level_description": "<1-2 English sentences summarizing the whole image>",\n'
    '  "background": "<detailed English description of the background/environment>",\n'
    '  "style_description": { ... }\n'
    '}\n\n'
    "style_description rules (key ORDER matters):\n"
    '- If style type is "photo":     {"aesthetics", "lighting", "photo", "medium", "color_palette"}\n'
    '  · "photo" = camera/lens details (e.g. "35mm, f/1.4, shallow depth of field")\n'
    '  · "medium" = "photograph"\n'
    '- If style type is "art_style": {"aesthetics", "lighting", "medium", "art_style", "color_palette"}\n'
    '  · "medium" ∈ illustration / painting / 3d_render / graphic_design ...\n'
    '  · "art_style" = art style description (e.g. "chinese ink painting, flowing brushstrokes")\n'
    "- color_palette: 3-6 UPPERCASE #RRGGBB hex strings matching the scene mood (include background color)\n\n"
    "All values in English. Output ONLY the JSON object — no markdown fences, no commentary."
)

IDEOGRAM_OVERVIEW_USER_TEMPLATE = (
    "Style type: {style_type}\n"
    "{characters_block}"
    "Scene description:\n{description}\n\n"
    "Produce the overview JSON (high_level_description + background + style_description)."
)

IDEOGRAM_ELEMENTS_SYSTEM = (
    "You are a prompt engineer for Ideogram 4 structured JSON captions.\n\n"
    "Given a scene description and the already-written overview, produce STEP 2: the spatial elements list.\n\n"
    "Output STRICT JSON: {\"elements\": [ ... ]} with 1-6 elements.\n\n"
    "Element formats (key ORDER matters):\n"
    '- Object:  {"type": "obj",  "bbox": [ymin, xmin, ymax, xmax], "desc": "<detailed English description>"}\n'
    '- Text:    {"type": "text", "bbox": [ymin, xmin, ymax, xmax], "text": "<literal text to render>", "desc": "<font/color/placement description>"}\n\n'
    "bbox rules:\n"
    "- Normalized 0-1000 grid, origin top-left, format [ymin, xmin, ymax, xmax], integers only\n"
    "- The canvas pixel size is given in the user message — place elements so the composition reads naturally\n"
    "- Main subject should occupy a prominent area (e.g. center or rule-of-thirds)\n"
    "- Elements may partially overlap but must not be identical boxes\n\n"
    "desc rules: English, concrete and visual (pose, clothing, expression, material, color).\n"
    "Use type \"text\" ONLY if the image should literally render text (signs, titles, captions).\n"
    "Output ONLY the JSON object — no markdown fences, no commentary."
)

IDEOGRAM_ELEMENTS_USER_TEMPLATE = (
    "Canvas: {width}x{height}\n"
    "{characters_block}"
    "Scene description:\n{description}\n\n"
    "Overview already written (for consistency — do not repeat background in elements):\n{overview_json}\n\n"
    "Produce the elements JSON."
)


# ── v1.5.1: 给已有台词逐条指派说话人（音色 100% 可控的 AI 助手）─────────────────
# 要点：保持台词文本与顺序不变，只输出每条的说话人名字；用上下文消解人称代词；
# 只能用名单里的名字或"旁白"，输出严格 JSON 数组且长度等于台词条数。
TAG_SPEAKERS_SYSTEM = (
    "你是一名严谨的剧本说话人标注员。给定一组**按顺序排列**的台词，"
    "以及完整的角色名单和分镜/文案上下文，你要判断每一条台词是由谁说出的。\n\n"
    "硬性规则：\n"
    "1. 只能从【角色名单】里选名字；不属于任何角色的叙述/旁白用 \"旁白\"。\n"
    "2. 必须结合上下文把人称代词（他/她/他们/她们/我/你）还原为具体角色名 —— "
    "这是关键，不要被中文倒装语序或省略主语误导。\n"
    "3. 不得新增、删除、改写或重排台词；你只输出说话人。\n"
    "4. 输出**严格 JSON 数组**，元素是字符串（角色名或\"旁白\"），"
    "数组长度必须正好等于台词条数，顺序一一对应。\n"
    "5. 不确定时，选上下文中最可能正在说话的角色；纯环境/动作叙述用\"旁白\"。\n"
    "只输出 JSON 数组本身，不要任何解释、不要 markdown 围栏。"
)

TAG_SPEAKERS_USER_TEMPLATE = (
    "【角色名单】{roster}\n\n"
    "【上下文（文案/分镜，用于消解人称代词）】\n{context}\n\n"
    "【台词（按顺序，第 i 行对应输出数组第 i 个）】\n{lines}\n\n"
    "请输出与台词条数等长的 JSON 字符串数组，每个元素是该条台词的说话人"
    "（角色名单里的名字，或\"旁白\"）。"
)


# ── v1.6: 纯白背景角色立绘提示词优化（供 MSR 多图参考视频用）────────────────────
# 把角色外观描述改写成"单人、纯白背景、无任何场景/道具/阴影"的图像提示词，
# 让生成的立绘可直接作为 LTX 多图参考的角色参考图（背景干净、便于换景）。
WHITE_BG_PORTRAIT_SYSTEM = (
    "You are an expert image-prompt engineer for character reference sheets.\n\n"
    "Rewrite the given character description into ONE concise English image prompt that "
    "produces a SINGLE character isolated on a PURE WHITE background, suitable as a clean "
    "reference image for video generation. Hard rules:\n"
    "1. Keep ALL of the character's visual identity (hair, eyes, outfit, body, age, etc.).\n"
    "2. Background MUST be pure solid white — explicitly include strong cues like "
    "'isolated on pure white background, plain white studio backdrop, seamless white, "
    "no scenery, no props, no furniture, even flat lighting, no cast shadow on background'.\n"
    "3. Full-body, neutral standing pose, front view, the whole character visible.\n"
    "4. NO other people, NO environment, NO text/watermark.\n"
    "5. Output ONLY the final English prompt (no quotes, no commentary, no markdown)."
)

WHITE_BG_PORTRAIT_USER_TEMPLATE = (
    "Character appearance: {appearance}\n"
    "Existing draft prompt (optional, may refine): {base_prompt}\n\n"
    "Produce the pure-white-background full-body character reference prompt."
)


# ── v1.6: 无角色背景图提示词（彻底排除人物）─────────────────────────────────────
# 供 MSR 多图参考视频的“场景参考图”用：只描述空场景/环境，绝不出现任何人物。

BG_SCENE_PROMPT_SYSTEM = (
    "You write English image-generation prompts for EMPTY BACKGROUND / ENVIRONMENT plates "
    "(the stage/set with NO actors).\n\n"
    "The output describes ONLY the location and setting — architecture, landscape, streets, "
    "rooms, furniture, props, vegetation, sky, weather, lighting, time of day, mood, atmosphere.\n\n"
    "HARD RULES (must all hold):\n"
    "1. ABSOLUTELY NO people. No characters, no humans, no person, no figures, no silhouettes, "
    "no crowds, no body parts, no faces, no hands. The frame must be completely empty of any "
    "living person.\n"
    "2. If the scene description mentions people or their actions, IGNORE the people entirely and "
    "describe ONLY the empty place where the action would happen (the set without any actor).\n"
    "3. Keep the same location, time of day and mood as the scene; do not invent a different place.\n"
    "4. No text, no watermark, no logo.\n"
    "5. Output ONLY the final English prompt — one paragraph, no quotes, no commentary, no markdown."
)

BG_SCENE_PROMPT_USER_TEMPLATE = (
    "Scene description (it MAY mention people — describe ONLY the empty environment, never the people):\n"
    "{description}\n"
    "{context}"
    "\nWrite the empty-background environment image prompt now (English, strictly NO people)."
)


# ── v1.6: MSR 多图参考视频提示词（“参考图N + 动作叙述”固定格式，中文）──────────────
# 与 MSR 工作流自带 CLIPTextEncode 默认提示词同构：先逐行声明每张参考图（角色用标签 +
# 外观；最后一张是场景），再写动作叙述（用标签指代、融入台词、加镜头运动）。

MSR_VIDEO_PROMPT_SYSTEM = (
    "你是“多图参考视频”（LTX 多图参考工作流）的中文提示词专家。"
    "按【固定格式】输出中文提示词，用来驱动“多张参考图 + 动作描述”的视频生成。\n\n"
    "输出格式（严格遵守）：\n"
    "1) 先逐行声明参考图，顺序与给定的“参考图清单”完全一致：\n"
    "   参考图1：<标签>，<性别>，<外观>\n"
    "   参考图2：<标签>，<性别>，<外观>\n"
    "   …（有几个角色写几行）\n"
    "   最后一行是场景：参考图N（场景）：<场景/背景描述>\n"
    "2) 然后另起一段写【动作叙述】：描述画面中发生的动作、表情变化与镜头运动；"
    "台词必须【原样保留】并用中文引号「」或“”包裹。\n\n"
    "硬性规则：\n"
    "1. 只能出现“参考图清单”里给出的角色，一律用其【标签】指代；禁止引入任何其他人物。\n"
    "2. 角色出现几次都用同一个标签，禁止用“他/她/那个人/两人之一”等代词指代具体角色。\n"
    "3. <性别> 从外观推断（男人/女人 等）；拿不准就省略该字段。\n"
    "4. <外观> 必须沿用给定的角色外观原文，保持视觉特征不变，不要增删关键特征。\n"
    "5. 场景行用给定的“背景/场景描述”。\n"
    "6. 动作叙述 2–6 句，把给定台词逐字融入并保留引号，并加入合理的镜头运动（推近 / 拉远 / 跟拍 / 环绕 等）。\n"
    "7. 【时序一致 · 重要】动作叙述里事物的【出现顺序 / 运动先后】要与画面实际发生的时间先后尽量一致——"
    "视频模型大致按提示词从前往后当作时间线读取，靠前的文字更容易被当成先发生。在不破坏逻辑的前提下，"
    "把先发生的动作 / 先出现的事物写在前面、后发生的写在后面（如：先转身 → 再开门 → 再有人走进来），"
    "可用“先…接着…随后…之后…”等时间词把先后讲清楚。\n"
    "8. 只输出最终的中文提示词，不要解释、不要标题、不要 markdown、不要代码块。"
)

MSR_VIDEO_PROMPT_USER_TEMPLATE = (
    "参考图清单（顺序即参考图顺序；每个角色一张，最后追加一张场景参考图）：\n"
    "{ref_block}\n"
    "背景/场景描述（用于场景参考图行）：\n"
    "{background}\n\n"
    "本镜（第 {scene_index}/{total_scenes} 镜）画面描述：\n"
    "{description}\n"
    "{dialogues_block}"
    "{mode_guidance}"
    "\n请严格按格式输出该镜的多图参考视频中文提示词。"
)

# v1.6.2: 按【对白模式】给「动作叙述」的差异化指导（注入 MSR 用户提示词的 {mode_guidance}）。
# 只影响动作叙述如何处理台词/旁白，不改参考图格式。
MSR_VIDEO_MODE_GUIDANCE = {
    "narration": (
        "\n【对白模式 · 纯旁白】本镜没有角色直接对白。动作叙述【不要写带引号的角色台词】，"
        "改用【动作、表情、神态、环境与镜头语言】来叙事；可把旁白要点视觉化为画面（如缓缓推近、"
        "环境光与天气变化、角色无声的情绪流露），靠画面而非对白推进剧情。\n"
    ),
    "dialogue": (
        "\n【对白模式 · 纯对话】本镜以角色对白推进。动作叙述要让相应角色【开口说话、口型与表情随台词"
        "自然变化】，把上面给定的台词【逐字保留、用中文引号「」或“”包裹】并配合说话时的手势/神态；"
        "镜头可用正反打、近景/特写等对话景别。\n"
    ),
    "mixed": (
        "\n【对白模式 · 混合】旁白与角色对白交替。动作叙述既要体现角色【开口对白】（逐字保留、引号包裹、"
        "配口型与表情），也要用镜头运动与环境氛围承接【旁白/叙述】部分，两者自然切换。\n"
    ),
    "reading": (
        "\n【对白模式 · 纯朗读】整段文本作为【画外音朗读】，角色通常【不对口型】。动作叙述【不要把朗读文本"
        "写成角色带引号的对白】；让画面（动作、神态、镜头、氛围）【贴合朗读内容的节奏与意境】逐步推进，"
        "以画外音叙事的视觉化呈现为主。\n"
    ),
}
