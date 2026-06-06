// Microsoft Edge neural voices used across SettingsView / CharactersTab / AudioTab.
// 与 backend/routers/audio_engine.MSEDGE_BUILTIN_VOICES 保持一致。

export const MSEDGE_VOICES = [
  // 女声
  { value: 'zh-CN-XiaoxiaoNeural', gender: 'female', label: '晓晓 · 自然' },
  { value: 'zh-CN-XiaoyiNeural',   gender: 'female', label: '晓伊 · 活泼' },
  { value: 'zh-CN-XiaohanNeural',  gender: 'female', label: '晓涵 · 温暖' },
  { value: 'zh-CN-XiaomengNeural', gender: 'female', label: '晓梦 · 萝莉' },
  { value: 'zh-CN-XiaomoNeural',   gender: 'female', label: '晓墨 · 多情感' },
  { value: 'zh-CN-XiaoqiuNeural',  gender: 'female', label: '晓秋 · 成熟' },
  { value: 'zh-CN-XiaoruiNeural',  gender: 'female', label: '晓睿 · 长者' },
  { value: 'zh-CN-XiaoxuanNeural', gender: 'female', label: '晓萱 · 御姐' },
  // 男声
  { value: 'zh-CN-YunxiNeural',    gender: 'male',   label: '云希 · 阳光' },
  { value: 'zh-CN-YunjianNeural',  gender: 'male',   label: '云健 · 沉稳' },
  { value: 'zh-CN-YunyangNeural',  gender: 'male',   label: '云扬 · 播报' },
  { value: 'zh-CN-YunfengNeural',  gender: 'male',   label: '云枫 · 阳刚' },
  { value: 'zh-CN-YunhaoNeural',   gender: 'male',   label: '云皓 · 广告' },
  // 童声
  { value: 'zh-CN-YunxiaNeural',   gender: 'child',  label: '云夏 · 男童' },
]

export const MSEDGE_GENDER_LABEL = { female: '女声', male: '男声', child: '童声' }

/**
 * 按 settings.audio_engine.msedge_available_voices 过滤。
 *   - allowed 为 null / undefined / [] → 不过滤（首次使用未跑测试时所有音色都可见）
 *   - allowed 非空 → 仅保留 allowed 中的音色
 * extraSelected: 当前角色 / 设置已选中的 voice，即便不在 allowed 也要保留显示，避免下拉无对应项
 */
export function filterVoices(allowed, extraSelected = []) {
  if (!allowed || !allowed.length) return MSEDGE_VOICES
  const ok = new Set(allowed)
  const keep = new Set([...extraSelected].filter(Boolean))
  return MSEDGE_VOICES.filter(v => ok.has(v.value) || keep.has(v.value))
}

/** 按性别分组（已过滤后的列表）便于下拉用 <optgroup> 渲染。 */
export function groupByGender(voices) {
  const groups = { female: [], male: [], child: [] }
  for (const v of voices) groups[v.gender]?.push(v)
  return [
    { gender: 'female', label: MSEDGE_GENDER_LABEL.female, items: groups.female },
    { gender: 'male',   label: MSEDGE_GENDER_LABEL.male,   items: groups.male   },
    { gender: 'child',  label: MSEDGE_GENDER_LABEL.child,  items: groups.child  },
  ].filter(g => g.items.length)
}
