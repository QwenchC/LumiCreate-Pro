<template>
  <div class="tab-panel">

    <!-- ── Toolbar ── -->
    <div class="scenes-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">分镜设计</h3>
        <span class="scene-count text-muted">共 {{ scenes.length }} 个分镜</span>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-secondary btn-sm" :disabled="!manuscript || generating" @click="generateScenes">
          {{ generating ? '生成中...' : '✨ 从文案自动生成分镜' }}
        </button>
        <button class="btn btn-secondary btn-sm" :disabled="!manuscript" @click="openManualSplit">
          ✂ 从文案手动生成分镜
        </button>
        <button
          class="btn btn-secondary btn-sm"
          :disabled="!scenes.length"
          @click="rewriteDialoguesByMode"
          :title="'保留所有分镜与提示词，仅按当前对白模式重新拆分每镜的台词（适合切换对白模式后同步）'"
        >
          ♻ 按对白模式重抽台词
        </button>
        <button
          class="btn btn-secondary btn-sm"
          :disabled="!scenes.length || generatingPrompts || generatingPromptIdx !== null"
          @click="generateAllPrompts"
          :title="'为所有分镜生成首帧/尾帧提示词'"
        >
          {{ generatingPrompts ? `提示词 ${promptProgress}/${scenes.length}...` : '🖼 生成全部提示词' }}
        </button>
        <button
          v-if="generatingPrompts || generatingPromptIdx !== null"
          class="btn btn-danger btn-sm"
          @click="stopPromptGeneration"
          title="中断当前提示词生成"
        >⏹ 中断提示词生成</button>
        <button
          class="btn btn-secondary btn-sm"
          :disabled="!scenes.length || !manuscriptConfig.characters.length || detectingChars"
          @click="autoDetectSceneCharacters"
          title="用 LLM 结合完整文案自动检测出镜角色（可识别人称代词）"
        >
          {{ detectingChars ? `🔍 检测中 ${detectProgress}/${scenes.length}…` : '🔍 自动检测角色' }}
        </button>
        <button
          v-if="detectingChars"
          class="btn btn-danger btn-sm"
          @click="stopDetectCharacters"
        >⏹ 中断检测</button>
        <button
          class="btn btn-secondary btn-sm"
          :disabled="!scenes.length || !manuscriptConfig.characters.length || taggingAll"
          @click="tagAllSpeakers"
          title="为所有分镜的每条台词指派说话人（AI 消解人称代词）→ 音色按说话人确定性映射"
        >
          {{ taggingAll ? `🎭 标注中 ${tagProgress}/${scenes.length}…` : '🎭 标注说话人' }}
        </button>
        <button
          v-if="taggingAll"
          class="btn btn-danger btn-sm"
          @click="stopTagging"
        >⏹ 中断标注</button>
        <button class="btn btn-secondary btn-sm" @click="addScene">+ 添加分镜</button>
        <button
          class="btn btn-ghost btn-sm"
          :disabled="!scenes.length"
          @click="clearAllScenes"
          title="清空所有分镜"
        >🗑 清空</button>
        <button class="btn btn-primary btn-sm" :disabled="!isDirty || saving" @click="save">
          {{ saving ? '保存中...' : '💾 保存分镜' }}
        </button>
      </div>
    </div>

    <!-- ── No manuscript warning ── -->
    <div v-if="!manuscript && !scenes.length" class="empty-state">
      <div class="empty-icon">📄</div>
      <p>请先在「文案创建」标签页完成文案并保存</p>
      <p class="text-muted" style="font-size:12px">文案保存后可点击「从文案生成分镜」</p>
    </div>

    <!-- ── Generating overlay ── -->
    <div v-else-if="generating" class="gen-state">
      <div class="spinner" />
      <p>LLM 正在分析文案并设计分镜...</p>
      <p class="text-muted" style="font-size:12px">这可能需要 30–120 秒，取决于文案长度</p>
    </div>

    <!-- ── Error ── -->
    <div v-else-if="genError" class="error-state">
      <div class="error-icon">⚠</div>
      <p>{{ genError }}</p>
      <button class="btn btn-secondary btn-sm" @click="genError = ''">关闭</button>
    </div>

    <!-- ── Scene list ── -->
    <div v-else class="scene-list">
      <div
        v-for="(scene, idx) in scenes"
        :key="scene.id"
        class="scene-card card"
        :class="{ expanded: expandedIdx === idx }"
      >
        <!-- Card header -->
        <div class="scene-card-header" @click="toggleExpand(idx)">
          <div class="scene-header-left">
            <span class="scene-num">{{ String(scene.index).padStart(2, '0') }}</span>
            <span class="scene-desc-preview truncate">{{ scene.description || '（无描述）' }}</span>
            <span class="scene-duration text-muted">~{{ scene.duration_estimate }}s</span>
            <span class="dialogue-badge badge badge-blue" v-if="scene.dialogues.length">
              {{ scene.dialogues.length }} 条台词
            </span>
          </div>
          <div class="scene-header-right">
            <button class="btn btn-ghost btn-sm icon-btn" title="上移" @click.stop="moveScene(idx, -1)" :disabled="idx === 0">▲</button>
            <button class="btn btn-ghost btn-sm icon-btn" title="下移" @click.stop="moveScene(idx, 1)" :disabled="idx === scenes.length - 1">▼</button>
            <button class="btn btn-ghost btn-sm icon-btn danger" title="删除" @click.stop="removeScene(idx)">✕</button>
            <span class="expand-arrow">{{ expandedIdx === idx ? '▲' : '▼' }}</span>
          </div>
        </div>

        <!-- Card body (expanded) -->
        <Transition name="expand">
          <div v-if="expandedIdx === idx" class="scene-card-body">
            <div class="scene-body-grid">

              <!-- Left column -->
              <div class="scene-col">
                <div class="form-group">
                  <label>场景描述</label>
                  <textarea
                    v-model="scene.description"
                    class="input textarea sm"
                    placeholder="简述该镜头的场景、情绪、动作..."
                    rows="3"
                    @input="markDirty"
                  />
                </div>
                <div class="form-row">
                  <div class="form-group half">
                    <label>预估时长（秒）</label>
                    <input type="number" v-model.number="scene.duration_estimate" class="input" min="1" max="60" @input="markDirty" />
                  </div>
                </div>
              </div>

              <!-- Right column: prompts -->
              <div class="scene-col">
                <!-- Character selector for this scene -->
                <div class="form-group" v-if="manuscriptConfig.characters.length">
                  <label class="label-char-select">
                    出镜角色
                    <span class="label-hint">（决定提示词包含哪些角色外观）</span>
                  </label>
                  <div class="char-chips">
                    <label
                      v-for="c in manuscriptConfig.characters" :key="c.name"
                      class="char-chip"
                      :class="{ selected: (scene._scene_characters || []).includes(c.name) }"
                    >
                      <input
                        type="checkbox"
                        :value="c.name"
                        :checked="(scene._scene_characters || []).includes(c.name)"
                        @change="toggleSceneChar(scene, c.name)"
                      />
                      {{ c.name }}
                    </label>
                    <span v-if="!manuscriptConfig.characters.length" class="text-muted" style="font-size:11px">（角色管理中无角色）</span>
                  </div>
                </div>
                <div class="form-group">
                  <label>
                    首帧提示词
                    <span class="label-hint">（英文，给 ComfyUI）</span>
                    <button
                      class="btn-gen-prompt"
                      :disabled="generatingPrompts || generatingPromptIdx !== null"
                      @click.stop="generateScenePrompt(scene, idx)"
                      title="用 LLM 生成该分镜的图片提示词"
                    >{{ generatingPromptIdx === idx ? '生成中...' : '✦ 生成提示词' }}</button>
                  </label>
                  <textarea
                    v-model="scene.start_frame_prompt"
                    class="input textarea sm prompt-input"
                    placeholder="e.g. anime girl in a cozy cafe, morning sunlight, soft bokeh..."
                    rows="3"
                    @input="markDirty"
                  />
                </div>
                <div class="form-group">
                  <label>
                    尾帧提示词
                    <span class="label-hint">（英文，给 ComfyUI）</span>
                  </label>
                  <textarea
                    v-model="scene.end_frame_prompt"
                    class="input textarea sm prompt-input"
                    placeholder="e.g. same girl smiling at camera, zoom in, warm colors..."
                    rows="3"
                    @input="markDirty"
                  />
                </div>
              </div>
            </div>

            <!-- Dialogues section -->
            <div class="dialogues-section">
              <div class="dialogues-header">
                <label class="dialogues-title">🗣 角色台词</label>
                <button
                  class="btn btn-secondary btn-sm"
                  v-if="rosterNames.length && scene.dialogues.length"
                  :disabled="taggingSceneId === (scene.id || scene.index)"
                  @click="tagSpeakers(scene)"
                  title="用 AI 结合上下文为每条台词指派说话人（消解人称代词）→ 再用下拉一键校正，音色 100% 可控"
                >{{ taggingSceneId === (scene.id || scene.index) ? '标注中…' : '🎭 标注说话人' }}</button>
                <button class="btn btn-secondary btn-sm" @click="addDialogue(scene)">+ 添加台词</button>
              </div>
              <div class="dialogue-list">
                <div
                  v-for="(dlg, di) in scene.dialogues"
                  :key="di"
                  class="dialogue-item"
                >
                  <div class="dialogue-controls">
                    <!-- v1.5.1: 说话人改成角色表绑定下拉（旁白 + 角色 + 表外保留），杜绝打错字/AI 错配 -->
                    <select
                      v-model="dlg.character"
                      class="input dlg-character select"
                      :title="'说话人 → 决定音色（在角色管理给角色配音色）'"
                      @change="markDirty"
                    >
                      <option value="">旁白/默认</option>
                      <option v-for="c in rosterNames" :key="c" :value="c">{{ c }}</option>
                      <option v-if="dlg.character && !rosterNames.includes(dlg.character)"
                              :value="dlg.character">{{ dlg.character }}（表外）</option>
                    </select>
                    <select v-model="dlg.emotion" class="input dlg-emotion select" @change="markDirty">
                      <option v-for="e in EMOTIONS" :key="e" :value="e">{{ e }}</option>
                    </select>
                    <button class="btn btn-ghost btn-sm icon-btn danger" @click="removeDialogue(scene, di)">✕</button>
                  </div>
                  <textarea
                    v-model="dlg.text"
                    class="input textarea dlg-text"
                    placeholder="台词内容..."
                    rows="2"
                    @input="markDirty"
                  />
                </div>
                <div v-if="!scene.dialogues.length" class="no-dialogue text-muted">
                  此分镜暂无台词（纯场景镜头）
                </div>
              </div>
            </div>
          </div>
        </Transition>
      </div>

      <!-- Add button at bottom -->
      <button class="btn btn-secondary add-bottom" @click="addScene">
        + 添加新分镜
      </button>
    </div>
  </div>

  <!-- ── Manual split modal ── -->
  <Teleport to="body">
    <div v-if="showManualSplit" class="ms-overlay" @click.self="showManualSplit = false">
      <div class="ms-dialog">
        <!-- Header -->
        <div class="ms-header">
          <div class="ms-header-left">
            <span class="ms-scene-label">
              {{ manualAssignedUpTo >= manualSentences.length - 1
                  ? `✅ 划分完成，共 ${manualPendingScenes.length} 个分镜`
                  : `正在划分第 ${manualCurrentScene} 分镜` }}
            </span>
            <span class="ms-hint text-muted">
              {{ manualCurrentScene === 1 && manualAssignedUpTo < 0
                  ? '将鼠标移至文案中某句上，高亮内容即为第 1 分镜范围，点击确认'
                  : manualAssignedUpTo >= manualSentences.length - 1
                    ? '点击「确认分镜」生成场景列表'
                    : '继续点击某句作为当前分镜的结束位置' }}
            </span>
          </div>
          <div class="ms-header-right">
            <button
              class="btn btn-ghost btn-sm"
              :disabled="!manualPendingScenes.length"
              @click="undoLastSplit"
              title="撤销上一次划分"
            >↩ 撤销</button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="!manualPendingScenes.length || manualSplitting"
              @click="finishManualSplit"
            >{{ manualSplitting ? '处理中...' : '✔ 确认分镜' }}</button>
            <button class="btn btn-ghost btn-sm" @click="showManualSplit = false">✕</button>
          </div>
        </div>
        <!-- Manuscript body -->
        <div class="ms-body" ref="msBodyRef">
          <template v-for="(item, k) in manualRenderItems" :key="k">
            <span
              v-if="item.type === 'sentence'"
              class="ms-sent"
              :class="{
                'ms-done': item.idx <= manualAssignedUpTo,
                'ms-hl':   manualHoverIdx >= 0 && item.idx > manualAssignedUpTo && item.idx <= manualHoverIdx,
                'ms-cur':  item.idx > manualAssignedUpTo,
              }"
              @mouseenter="item.idx > manualAssignedUpTo && (manualHoverIdx = item.idx)"
              @mouseleave="manualHoverIdx = -1"
              @click="item.idx > manualAssignedUpTo && clickSentence(item.idx)"
            >{{ item.text }}</span>
            <span v-else class="ms-divider">┄ 第 {{ item.sceneNum }} 分镜 ┄</span>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted, onDeactivated } from 'vue'

const props = defineProps({ projectId: String })
const emit = defineEmits(['dirty', 'saved'])

const API = 'http://127.0.0.1:18520/api'

const EMOTIONS = ['平静', '喜悦', '愤怒', '悲伤', '惊讶', '恐惧', '害羞', '紧张']

// ── State ──────────────────────────────────────────────────────────────────────
const scenes           = ref([])
const manuscript       = ref('')
const manuscriptConfig = ref({ dialogue_mode: 'mixed', characters: [] })
const isDirty          = ref(false)
const saving           = ref(false)
const generating         = ref(false)
const genError           = ref('')
const expandedIdx        = ref(null)
const generatingPrompts  = ref(false)
const generatingPromptIdx = ref(null)  // idx of single scene being generated
const promptProgress     = ref(0)
let promptAbortController = null
const detectingChars     = ref(false)
const detectProgress     = ref(0)
let detectAbortController = null

// v1.5.1: 说话人标注（音色 100% 可控）
const rosterNames    = computed(() => (manuscriptConfig.value.characters || []).map(c => c.name))
const taggingSceneId = ref(null)   // 单镜标注中
const taggingAll     = ref(false)  // 批量标注中
const tagProgress    = ref(0)
let tagStopFlag      = false

// ── Manual split state ──────────────────────────────────────────────────────────────────
const showManualSplit     = ref(false)
const manualSentences     = ref([])     // array of sentence strings
const manualPendingScenes = ref([])     // [{ startIdx, endIdx }]
const manualCurrentScene  = ref(1)
const manualAssignedUpTo  = ref(-1)     // index of last assigned sentence (-1 = none)
const manualHoverIdx      = ref(-1)
const manualSplitting     = ref(false)
const msBodyRef           = ref(null)
const manualRenderItems = computed(() => {
  const sceneEndMap = new Map(manualPendingScenes.value.map((s, i) => [s.endIdx, i + 1]))
  const items = []
  for (let i = 0; i < manualSentences.value.length; i++) {
    items.push({ type: 'sentence', text: manualSentences.value[i], idx: i })
    if (sceneEndMap.has(i)) items.push({ type: 'divider', sceneNum: sceneEndMap.get(i) })
  }
  return items
})

// ── Load ───────────────────────────────────────────────────────────────────────
onMounted(async () => {
  // Load manuscript (needed for generation)
  try {
    const r = await fetch(`${API}/projects/${props.projectId}/manuscript`)
    if (r.ok) {
      const d = await r.json()
      manuscript.value = d.content || ''
      if (d.config) {
        manuscriptConfig.value = {
          dialogue_mode: d.config.dialogue_mode || 'mixed',
          characters:    d.config.characters    || [],
        }
      }
    }
  } catch {}
  // Load enriched characters (includes appearance from CharactersTab)
  try {
    const r = await fetch(`${API}/projects/${props.projectId}/characters`)
    if (r.ok) {
      const d = await r.json()
      if (d.characters?.length) manuscriptConfig.value.characters = d.characters
    }
  } catch {}
  // Load saved scenes
  try {
    const r = await fetch(`${API}/projects/${props.projectId}/scenes`)
    if (r.ok) {
      const d = await r.json()
      scenes.value = (d.scenes || []).map(s => ({
        ...s,
        _scene_characters: Array.isArray(s._scene_characters) ? s._scene_characters : [],
      }))
    }
  } catch {}
  _initHistory()    // B2: scenes 加载完成 → 建立撤销基线

  window.addEventListener('lumi:save-project', onGlobalSave)
  window.addEventListener('lumi:undo', _onProjectUndo)
  window.addEventListener('lumi:redo', _onProjectRedo)
})
onUnmounted(() => {
  window.removeEventListener('lumi:save-project', onGlobalSave)
  window.removeEventListener('lumi:undo', _onProjectUndo)
  window.removeEventListener('lumi:redo', _onProjectRedo)
})
// Auto-save when navigating away (KeepAlive: onDeactivated fires on every tab switch)
onDeactivated(async () => { if (isDirty.value) await save() })

// ── Generate from manuscript ──────────────────────────────────────────────────
async function generateScenes() {
  if (!manuscript.value.trim()) return
  generating.value = true
  genError.value = ''
  try {
    const res = await fetch(`${API}/text-engine/generate-scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        manuscript:    manuscript.value,
        dialogue_mode: manuscriptConfig.value.dialogue_mode,
        characters:    manuscriptConfig.value.characters,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || res.statusText)
    }
    const data = await res.json()
    scenes.value = (data.scenes || []).map(s => ({ ...s, _scene_characters: [] }))
    if (scenes.value.length) {
      expandedIdx.value = 0
      isDirty.value = true
      emit('dirty')
    }
  } catch (e) {
    genError.value = `分镜生成失败：${e.message}`
  } finally {
    generating.value = false
  }
}

// ── Manual split helpers ──────────────────────────────────────────────────────────────────
function _splitSentences(text) {
  const result = []
  let buf = ''
  for (const ch of text) {
    buf += ch
    if ('。！？'.includes(ch) || ch === '\n') {
      const t = buf.replace(/\n/g, '').trim()
      if (t) result.push(t)
      buf = ''
    }
  }
  if (buf.trim()) result.push(buf.trim())
  return result
}

// v1.5.1: 说话人标注的确定性 JS 解析（与后端 services/dialogue_tags.py 同规则）
const _NARR_ALIASES = new Set(['旁白', '叙述', '旁白/默认', 'narration', 'narrator'])
const _TAG_RE = /^[@＠]?\s*([^:：\n]{1,20}?)\s*[:：]\s*(.+?)\s*$/

function parseSpeakerTags(text, knownNames = []) {
  const known = new Set(knownNames)
  const out = []
  for (const raw of (text || '').split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    const m = line.match(_TAG_RE)
    if (m) {
      const name = m[1].trim(), body = m[2].trim()
      if (_NARR_ALIASES.has(name) || _NARR_ALIASES.has(name.toLowerCase())) {
        out.push({ character: '', text: body }); continue
      }
      if ((!known.size || known.has(name)) && body) {
        out.push({ character: name, text: body }); continue
      }
    }
    out.push({ character: '', text: line })
  }
  return out
}
function hasSpeakerTags(text, knownNames = []) {
  const known = new Set(knownNames)
  for (const raw of (text || '').split(/\r?\n/)) {
    const m = raw.trim().match(_TAG_RE)
    if (!m) continue
    const name = m[1].trim()
    if (_NARR_ALIASES.has(name) || _NARR_ALIASES.has(name.toLowerCase())) return true
    if (!known.size || known.has(name)) return true
  }
  return false
}

function _extractDialogues(text) {
  const t0 = (text || '').trim()
  if (!t0) return []
  // v1.5.1: 显式说话人标注（角色：台词）→ 确定性解析，保留说话人（所有模式优先）
  if (hasSpeakerTags(t0, rosterNames.value)) {
    return parseSpeakerTags(t0, rosterNames.value)
      .map(d => ({ character: d.character, text: d.text, emotion: '平静' }))
  }
  const mode = manuscriptConfig.value.dialogue_mode
  // reading / narration：整段都作为单条（reading=直读全文，narration=旁白叙述）
  if (mode === 'reading' || mode === 'narration') {
    return [{ character: '', text: t0, emotion: '平静' }]
  }
  // dialogue：仅引号里的对白（混合模式同样使用此抽取；旁白部分留给 reading/narration 处理）
  // 兼顾中英文引号
  const dlgs = []
  const re = /[「“‘"'](.*?)[」”’"']/gs
  let m
  while ((m = re.exec(t0)) !== null) {
    const seg = m[1].trim()
    if (seg) dlgs.push({ character: '', text: seg, emotion: '平静' })
  }
  // mixed 模式下若一句也没抽到（描述里没引号），fallback 成整段 1 条以免音频生成完全没内容
  if (!dlgs.length && mode === 'mixed') {
    return [{ character: '', text: t0, emotion: '平静' }]
  }
  return dlgs
}

function rewriteDialoguesByMode() {
  if (!scenes.value.length) return
  const mode = manuscriptConfig.value.dialogue_mode || 'mixed'
  const modeLabel = {
    reading:   '纯朗读（整段直读）',
    narration: '纯旁白',
    dialogue:  '纯对话（仅引号内）',
    mixed:     '旁白+对话',
  }[mode] || mode
  if (!confirm(
    `将按当前对白模式「${modeLabel}」重新拆分每个分镜的台词。\n\n` +
    `→ 仅会覆盖每镜的 dialogues 字段\n` +
    `→ 分镜 id / 描述 / 首末帧提示词 / 出镜角色 / 已生成的图片 全部保留\n\n` +
    `继续吗？`
  )) return
  for (const s of scenes.value) {
    s.dialogues = _extractDialogues(s.description || '')
  }
  markDirty()
}

function openManualSplit() {
  if (!manuscript.value.trim()) return
  manualSentences.value    = _splitSentences(manuscript.value)
  manualPendingScenes.value = []
  manualCurrentScene.value  = 1
  manualAssignedUpTo.value  = -1
  manualHoverIdx.value      = -1
  manualSplitting.value     = false
  showManualSplit.value     = true
}

async function clickSentence(idx) {
  if (idx <= manualAssignedUpTo.value) return
  manualPendingScenes.value.push({ startIdx: manualAssignedUpTo.value + 1, endIdx: idx })
  manualAssignedUpTo.value = idx
  manualCurrentScene.value++
  manualHoverIdx.value = -1
  // If all text now assigned, auto-finish
  if (idx >= manualSentences.value.length - 1) {
    await nextTick()
    finishManualSplit()
    return
  }
  // Scroll next unassigned sentence into view
  await nextTick()
  const els = msBodyRef.value?.querySelectorAll('.ms-sent')
  if (els?.[idx + 1]) els[idx + 1].scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function undoLastSplit() {
  if (!manualPendingScenes.value.length) return
  manualPendingScenes.value.pop()
  manualCurrentScene.value--
  manualAssignedUpTo.value = manualPendingScenes.value.length > 0
    ? manualPendingScenes.value.at(-1).endIdx
    : -1
}

function finishManualSplit() {
  // Any remaining unassigned text becomes the last scene
  if (manualAssignedUpTo.value < manualSentences.value.length - 1) {
    manualPendingScenes.value.push({
      startIdx: manualAssignedUpTo.value + 1,
      endIdx:   manualSentences.value.length - 1,
    })
  }
  if (!manualPendingScenes.value.length) return
  manualSplitting.value = true
  const newScenes = manualPendingScenes.value.map((split, i) => {
    const text = manualSentences.value.slice(split.startIdx, split.endIdx + 1).join('')
    return {
      id:                 `scene_${String(i + 1).padStart(3, '0')}_manual`,
      index:              i + 1,
      description:        text,
      duration_estimate:  Math.max(4, Math.round(text.length / 5)),
      start_frame_prompt: '',
      end_frame_prompt:   '',
      _scene_characters:  [],
      dialogues:          _extractDialogues(text),
    }
  })
  scenes.value      = newScenes
  expandedIdx.value = 0
  markDirty()
  manualSplitting.value = false
  showManualSplit.value  = false
}
function toggleSceneChar(scene, charName) {
  const current = scene._scene_characters || []
  if (current.includes(charName)) {
    scene._scene_characters = current.filter(n => n !== charName)
  } else {
    scene._scene_characters = [...current, charName]
  }
  markDirty()
}

// ── Text-engine concurrency helper ────────────────────────────────────────────
// Pulls settings.text_engine.concurrency every time we kick off a batch, so the
// user-facing 设置-文本引擎-批量并发数 actually controls 角色自动识别 + 帧 prompt.
async function _resolveTextConcurrency() {
  try {
    const r = await fetch(`${API}/settings`)
    if (r.ok) {
      const s = await r.json()
      const n = Number(s?.text_engine?.concurrency)
      if (Number.isFinite(n) && n >= 1) return Math.min(n, 2500)
    }
  } catch { /* ignore */ }
  return 4
}

// ── Frame prompt generation ───────────────────────────────────────────────────
async function _fetchFramePrompts(scene) {
  // Use only the characters selected for this scene.
  // If none selected, pass an empty list so no role appearance is injected.
  const selected = scene._scene_characters || []
  const allChars = manuscriptConfig.value.characters || []
  const chars = allChars.filter(c => selected.includes(c.name))
  const res = await fetch(`${API}/text-engine/generate-frame-prompts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: promptAbortController?.signal,
    body: JSON.stringify({
      description:  scene.description,
      dialogues:    scene.dialogues,
      characters:   chars,
      manuscript:   manuscript.value,
      scene_index:  scene.index,
      total_scenes: scenes.value.length,
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

async function generateScenePrompt(scene, idx) {
  promptAbortController = new AbortController()
  generatingPromptIdx.value = idx
  try {
    const data = await _fetchFramePrompts(scene)
    scene.start_frame_prompt = data.start_frame_prompt || scene.start_frame_prompt
    scene.end_frame_prompt   = data.end_frame_prompt   || scene.end_frame_prompt
    markDirty()
  } catch (e) {
    if (e.name !== 'AbortError') alert(`提示词生成失败：${e.message}`)
  } finally {
    generatingPromptIdx.value = null
    promptAbortController = null
  }
}

async function generateAllPrompts() {
  // v1.4.2: 单 SSE 批量端点。前端只开 1 个 connection，并发完全由后端
  // settings.text_engine.concurrency 决定，绕开 Chromium 单 origin 6 连接上限。
  promptAbortController = new AbortController()
  generatingPrompts.value = true
  promptProgress.value = 0
  const total = scenes.value.length
  const sceneById = {}
  scenes.value.forEach((s, i) => { sceneById[String(s.id)] = i })

  // 收集每个 scene 用到的角色子集（与原单调用语义一致：传 _scene_characters）
  const allCharsByName = Object.fromEntries(
    (manuscriptConfig.value.characters || []).map(c => [c.name, c])
  )
  const buildFrames = () => scenes.value.map(s => {
    const selected = s._scene_characters || []
    const sceneChars = selected.length
      ? selected.map(n => allCharsByName[n]).filter(Boolean)
      : null   // null = 让后端用共享 characters（即"所有角色"）
    return {
      scene_id:    String(s.id),
      description: s.description,
      dialogues:   s.dialogues || [],
      ...(sceneChars ? { characters: sceneChars } : {}),
    }
  })

  try {
    const resp = await fetch(`${API}/text-engine/generate-frame-prompts-batch`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      signal:  promptAbortController.signal,
      body:    JSON.stringify({
        frames:       buildFrames(),
        characters:   manuscriptConfig.value.characters || [],
        manuscript:   manuscript.value,
        total_scenes: scenes.value.length,
        // concurrency=0 → 后端跟 settings 走
      }),
    })
    if (!resp.ok) throw new Error('HTTP ' + resp.status)
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      if (promptAbortController?.signal.aborted) { try { reader.cancel() } catch {} ; break }
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        try {
          const ev = JSON.parse(raw)
          if (ev.event === 'result' && ev.scene_id != null) {
            const i = sceneById[String(ev.scene_id)]
            if (i != null) {
              scenes.value[i].start_frame_prompt = ev.start_frame_prompt || scenes.value[i].start_frame_prompt
              scenes.value[i].end_frame_prompt   = ev.end_frame_prompt   || scenes.value[i].end_frame_prompt
              markDirty()
            }
            promptProgress.value++
          } else if (ev.event === 'item_error') {
            promptProgress.value++
          }
        } catch {}
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      console.warn('batch frame-prompts failed', e)
    }
  } finally {
    generatingPromptIdx.value = null
    generatingPrompts.value   = false
    promptAbortController     = null
  }
}

function stopPromptGeneration() {
  if (promptAbortController) {
    promptAbortController.abort()
    promptAbortController = null
  }
  generatingPromptIdx.value = null
  generatingPrompts.value = false
}

// ── Auto-detect scene characters (LLM-based, pronoun-aware) ──────────────────
function stopDetectCharacters() {
  detectAbortController?.abort()
  detectAbortController = null
  detectingChars.value = false
}

// ── v1.5.1: 给每条台词指派说话人（AI 助手 + 角色名单校验，前端再用下拉确认）─────
function stopTagging() { tagStopFlag = true }

async function tagSpeakers(scene) {
  const sceneKey = scene.id || scene.index
  const lines = (scene.dialogues || []).map(d => d.text || '')
  if (!lines.some(t => t.trim()) || !rosterNames.value.length) return
  taggingSceneId.value = sceneKey
  try {
    const res = await fetch(API + '/text-engine/tag-dialogue-speakers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lines,
        characters: rosterNames.value,
        // 上下文：分镜描述 + 完整文案，帮 LLM 消解人称代词
        context: `${scene.description || ''}\n\n${manuscript.value || ''}`.trim(),
      }),
    })
    if (!res.ok) throw new Error(await res.text())
    const speakers = (await res.json()).speakers || []
    // 只把非空说话人写回（空=旁白/未识别，保留原值，避免把已对的清掉）
    scene.dialogues.forEach((d, i) => {
      if (speakers[i]) d.character = speakers[i]
    })
    markDirty()
  } catch (e) {
    console.error('tagSpeakers failed', e)
  } finally {
    if (taggingSceneId.value === sceneKey) taggingSceneId.value = null
  }
}

async function tagAllSpeakers() {
  if (taggingAll.value || !rosterNames.value.length) return
  taggingAll.value = true
  tagStopFlag = false
  tagProgress.value = 0
  try {
    for (const scene of scenes.value) {
      if (tagStopFlag) break
      if ((scene.dialogues || []).some(d => (d.text || '').trim())) {
        await tagSpeakers(scene)
      }
      tagProgress.value++
    }
  } finally {
    taggingAll.value = false
    tagStopFlag = false
  }
}

async function autoDetectSceneCharacters() {
  const allCharNames = (manuscriptConfig.value.characters || []).map(c => c.name)
  if (!allCharNames.length || detectingChars.value) return

  detectingChars.value = true
  detectProgress.value = 0
  detectAbortController = new AbortController()

  let changed = false
  const sceneById = {}
  scenes.value.forEach((s, i) => { sceneById[String(s.id)] = i })

  try {
    const resp = await fetch(`${API}/text-engine/suggest-scene-characters-batch`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      signal:  detectAbortController.signal,
      body:    JSON.stringify({
        scenes: scenes.value.map(s => ({
          scene_id:    String(s.id),
          description: s.description,
          dialogues:   s.dialogues || [],
        })),
        all_names:  allCharNames,
        manuscript: manuscript.value,
      }),
    })
    if (!resp.ok) throw new Error('HTTP ' + resp.status)
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      if (detectAbortController?.signal.aborted) { try { reader.cancel() } catch {} ; break }
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        try {
          const ev = JSON.parse(raw)
          if (ev.event === 'result' && ev.scene_id != null) {
            const i = sceneById[String(ev.scene_id)]
            if (i != null) {
              const scene = scenes.value[i]
              const detected = (ev.characters || []).sort()
              const current  = [...(scene._scene_characters || [])].sort()
              if (JSON.stringify(current) !== JSON.stringify(detected)) {
                scene._scene_characters = ev.characters || []
                changed = true
              }
            }
            detectProgress.value++
          } else if (ev.event === 'item_error') {
            detectProgress.value++
          }
        } catch {}
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      console.warn('batch suggest-chars failed', e)
    }
  }

  if (changed) markDirty()
  detectingChars.value = false
  detectAbortController = null
}

function clearAllScenes() {
  if (!confirm(`确定清空全部 ${scenes.value.length} 个分镜？此操作不可撤销。`)) return
  scenes.value = []
  expandedIdx.value = null
  markDirty()
}

// ── CRUD helpers ──────────────────────────────────────────────────────────────
function addScene() {
  const idx = scenes.value.length + 1
  scenes.value.push({
    id: `scene_${String(idx).padStart(3, '0')}_manual`,
    index: idx,
    description: '',
    duration_estimate: 8.0,
    start_frame_prompt: '',
    end_frame_prompt: '',
    _scene_characters: [],
    dialogues: [],
  })
  expandedIdx.value = scenes.value.length - 1
  markDirty()
}

function removeScene(idx) {
  if (!confirm(`确定删除分镜 ${scenes.value[idx].index}？`)) return
  scenes.value.splice(idx, 1)
  // Re-index
  scenes.value.forEach((s, i) => { s.index = i + 1 })
  if (expandedIdx.value >= scenes.value.length) expandedIdx.value = null
  markDirty()
}

function moveScene(idx, dir) {
  const to = idx + dir
  if (to < 0 || to >= scenes.value.length) return
  const arr = scenes.value
  ;[arr[idx], arr[to]] = [arr[to], arr[idx]]
  arr.forEach((s, i) => { s.index = i + 1 })
  expandedIdx.value = to
  markDirty()
}

function addDialogue(scene) {
  scene.dialogues.push({ character: '', text: '', emotion: '平静' })
  markDirty()
}
function removeDialogue(scene, di) {
  scene.dialogues.splice(di, 1)
  markDirty()
}

function toggleExpand(idx) {
  expandedIdx.value = expandedIdx.value === idx ? null : idx
}

// ── B2: 撤销 / 重做 ─────────────────────────────────────────────────────────
// 模型：_history 存"过去的稳定状态"；_lastStable 存"当前显示状态对应的稳定 snapshot"
// 每次 markDirty 把 _lastStable 推入 _history，然后更新 _lastStable=当前 snapshot。
// undo: _lastStable 推 _future，弹 _history 最顶应用 + 更新 _lastStable
// redo: _lastStable 推 _history，弹 _future 最顶应用 + 更新 _lastStable
const _history = []
const _future  = []
const HIST_MAX = 20
let   _lastStable = null     // 初始化时填
let   _suppressHist = false  // apply 时关闭防止递归

function _snapshot() {
  return JSON.parse(JSON.stringify(scenes.value))
}
function _applySnapshot(snap) {
  _suppressHist = true
  scenes.value = JSON.parse(JSON.stringify(snap))
  _suppressHist = false
}

function _initHistory() {
  // load 完后调一次：把"初始状态"作为基线
  _lastStable = _snapshot()
  _history.length = 0
  _future.length  = 0
}

function _recordChange() {
  if (_suppressHist) return
  if (_lastStable == null) { _lastStable = _snapshot(); return }
  _history.push(_lastStable)
  if (_history.length > HIST_MAX) _history.shift()
  _lastStable = _snapshot()
  _future.length = 0
}

function undo() {
  if (!_history.length) return
  _future.push(_lastStable ?? _snapshot())
  const prev = _history.pop()
  _applySnapshot(prev)
  _lastStable = prev
  isDirty.value = true
  emit('dirty')
}

function redo() {
  if (!_future.length) return
  _history.push(_lastStable ?? _snapshot())
  const next = _future.pop()
  _applySnapshot(next)
  _lastStable = next
  isDirty.value = true
  emit('dirty')
}

function markDirty() {
  _recordChange()
  isDirty.value = true
  window.__lumiUnsaved = true
  emit('dirty')
}

function _onProjectUndo(e) {
  if (e?.detail?.tab && e.detail.tab !== 'scenes') return
  undo()
}
function _onProjectRedo(e) {
  if (e?.detail?.tab && e.detail.tab !== 'scenes') return
  redo()
}

// ── Save ───────────────────────────────────────────────────────────────────────
async function save() {
  saving.value = true
  try {
    const res = await fetch(`${API}/projects/${props.projectId}/scenes`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenes: scenes.value }),
    })
    if (!res.ok) throw new Error(await res.text())
    isDirty.value = false
    window.__lumiUnsaved = false
    emit('saved')
  } catch (e) {
    alert(`保存失败：${e.message}`)
  } finally {
    saving.value = false
  }
}

function onGlobalSave(e) { if (e?.detail?.projectId && e.detail.projectId !== props.projectId) return; if (isDirty.value) save() }
</script>

<style scoped>
.tab-panel { height: 100%; display: flex; flex-direction: column; overflow: hidden; }

/* ── Toolbar ── */
.scenes-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--color-border); flex-shrink: 0;
  background: var(--color-surface);
}
.toolbar-left  { display: flex; align-items: center; gap: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.toolbar-title { font-size: 15px; font-weight: 700; }
.scene-count   { font-size: 12px; }

/* ── States ── */
.empty-state, .gen-state, .error-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 10px;
  color: var(--color-text-muted);
}
.empty-icon  { font-size: 52px; }
.error-icon  { font-size: 40px; color: var(--color-error); }
.spinner {
  width: 36px; height: 36px; border-radius: 50%;
  border: 3px solid var(--color-border); border-top-color: var(--color-accent);
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Scene list ── */
.scene-list {
  flex: 1; overflow-y: auto; padding: 14px 16px;
  display: flex; flex-direction: column; gap: 10px;
}

/* ── Scene card ── */
.scene-card { padding: 0; overflow: hidden; flex-shrink: 0; }
.scene-card-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; cursor: pointer;
  transition: background var(--transition);
}
.scene-card-header:hover { background: rgba(255,255,255,0.04); }
.scene-header-left  { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.scene-header-right { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.scene-num  { font-size: 16px; font-weight: 700; color: var(--color-accent); min-width: 28px; }
.scene-desc-preview { flex: 1; font-size: 13px; }
.scene-duration { font-size: 11px; }
.expand-arrow { font-size: 11px; color: var(--color-text-muted); margin-left: 6px; }

.icon-btn { padding: 3px 7px; min-width: 0; }
.icon-btn.danger:hover { color: var(--color-error); }

/* ── Card body ── */
.scene-card-body { padding: 0 14px 14px; border-top: 1px solid var(--color-border); }
.scene-body-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding-top: 14px; }
.scene-col { display: flex; flex-direction: column; gap: 0; }
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 12px; color: var(--color-text-muted); margin-bottom: 5px; }
.label-hint { font-size: 11px; opacity: 0.7; }
.form-row   { display: flex; gap: 12px; }
.half       { flex: 1; }
.textarea.sm { min-height: 60px; resize: vertical; font-family: inherit; }
.prompt-input { font-family: 'Consolas', monospace; font-size: 12px; }

/* ── Character chips ── */
.label-char-select { color: var(--color-text-muted); }
.char-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.char-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px; border-radius: 99px; font-size: 12px; cursor: pointer;
  border: 1px solid var(--color-border); background: var(--color-surface);
  transition: border-color .15s, background .15s; user-select: none;
}
.char-chip input { display: none; }
.char-chip:hover { border-color: var(--color-accent); }
.char-chip.selected {
  border-color: var(--color-accent);
  background: rgba(99,179,237,.15);
  color: var(--color-accent); font-weight: 600;
}

/* ── Dialogues ── */
.dialogues-section { margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--color-border); }
.dialogues-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.dialogues-title  { font-size: 13px; font-weight: 600; }
.dialogue-list { display: flex; flex-direction: column; gap: 10px; }
.dialogue-item { background: var(--color-bg); border: 1px solid var(--color-border); border-radius: var(--radius); padding: 10px 12px; }
.dialogue-controls { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.dlg-character { width: 110px; flex-shrink: 0; }
.dlg-emotion   { width: 90px; flex-shrink: 0; appearance: none; }
.dlg-text      { resize: none; min-height: 48px; font-family: inherit; }
.no-dialogue   { font-size: 12px; padding: 8px 0; }

.add-bottom { width: 100%; justify-content: center; }

/* prompt generate button inside label */
.btn-gen-prompt {
  margin-left: 8px;
  padding: 1px 8px;
  font-size: 11px;
  background: none;
  border: 1px solid var(--color-accent);
  border-radius: var(--radius);
  color: var(--color-accent);
  cursor: pointer;
  transition: background var(--transition), color var(--transition);
}
.btn-gen-prompt:hover:not(:disabled) { background: var(--color-accent); color: #fff; }
.btn-gen-prompt:disabled { opacity: 0.45; cursor: default; }

/* ── Expand transition ── */
.expand-enter-active, .expand-leave-active { transition: max-height 0.25s ease, opacity 0.2s; overflow: hidden; }
.expand-enter-from, .expand-leave-to { max-height: 0; opacity: 0; }
.expand-enter-to, .expand-leave-from { max-height: 2000px; opacity: 1; }

/* ── Manual split modal ── */
.ms-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.65);
  display: flex; align-items: center; justify-content: center;
  z-index: 9999;
}
.ms-dialog {
  width: min(820px, 95vw); height: min(78vh, 700px);
  background: var(--color-surface); border-radius: 10px;
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
  display: flex; flex-direction: column; overflow: hidden;
}
.ms-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-bottom: 1px solid var(--color-border); flex-shrink: 0;
  background: var(--color-surface-2); gap: 12px;
}
.ms-header-left  { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
.ms-header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ms-scene-label  { font-size: 15px; font-weight: 700; }
.ms-hint         { font-size: 12px; }
.ms-body {
  flex: 1; overflow-y: auto; padding: 20px 24px;
  font-size: 15px; line-height: 2.2; color: var(--color-text);
}
.ms-sent {
  border-radius: 3px; padding: 1px 3px;
  transition: background .1s, color .1s;
}
.ms-cur  { cursor: pointer; }
.ms-cur:not(.ms-hl):hover { background: rgba(99,179,237,.1); }
.ms-hl   { background: rgba(99,179,237,.28); color: var(--color-accent); }
.ms-done { color: var(--color-text-muted); opacity: 0.4; cursor: default; }
.ms-divider {
  display: inline-block; margin: 0 8px;
  font-size: 11px; color: var(--color-accent); opacity: 0.85;
  vertical-align: middle; letter-spacing: 0.05em;
  border-left: 2px solid var(--color-accent);
  padding-left: 6px;
}
</style>

