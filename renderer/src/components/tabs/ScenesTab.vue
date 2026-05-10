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
          {{ generating ? '生成中...' : '✨ 从文案生成分镜' }}
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
          :disabled="!scenes.length || !manuscriptConfig.characters.length"
          @click="autoDetectSceneCharacters"
          title="根据分镜文案自动检测出镜角色"
        >🔍 自动检测角色</button>
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
                      :disabled="generatingPromptIdx !== null"
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
                <button class="btn btn-secondary btn-sm" @click="addDialogue(scene)">+ 添加台词</button>
              </div>
              <div class="dialogue-list">
                <div
                  v-for="(dlg, di) in scene.dialogues"
                  :key="di"
                  class="dialogue-item"
                >
                  <div class="dialogue-controls">
                    <input
                      v-model="dlg.character"
                      class="input dlg-character"
                      placeholder="角色名"
                      @input="markDirty"
                    />
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
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

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

  window.addEventListener('lumi:save-project', onGlobalSave)
})
onUnmounted(() => window.removeEventListener('lumi:save-project', onGlobalSave))

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

// ── Character selection per scene ─────────────────────────────────────────────
function toggleSceneChar(scene, charName) {
  const current = scene._scene_characters || []
  if (current.includes(charName)) {
    scene._scene_characters = current.filter(n => n !== charName)
  } else {
    scene._scene_characters = [...current, charName]
  }
  markDirty()
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
      description: scene.description,
      dialogues:   scene.dialogues,
      characters:  chars,
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
  promptAbortController = new AbortController()
  generatingPrompts.value = true
  promptProgress.value = 0
  for (let i = 0; i < scenes.value.length; i++) {
    if (!promptAbortController) break
    generatingPromptIdx.value = i
    try {
      const data = await _fetchFramePrompts(scenes.value[i])
      scenes.value[i].start_frame_prompt = data.start_frame_prompt || scenes.value[i].start_frame_prompt
      scenes.value[i].end_frame_prompt   = data.end_frame_prompt   || scenes.value[i].end_frame_prompt
      markDirty()
    } catch (e) {
      if (e.name === 'AbortError') break
      /* skip failed scene */
    }
    promptProgress.value = i + 1
  }
  generatingPromptIdx.value = null
  generatingPrompts.value = false
  promptAbortController = null
}

function stopPromptGeneration() {
  if (promptAbortController) {
    promptAbortController.abort()
    promptAbortController = null
  }
  generatingPromptIdx.value = null
  generatingPrompts.value = false
}

// ── Auto-detect scene characters ──────────────────────────────────────────────
function autoDetectSceneCharacters() {
  const allCharNames = (manuscriptConfig.value.characters || []).map(c => c.name)
  if (!allCharNames.length) return
  
  let changed = false
  for (const scene of scenes.value) {
    const detected = new Set()
    
    // Check description
    const desc = (scene.description || '').toLowerCase()
    for (const name of allCharNames) {
      if (desc.includes(name.toLowerCase())) {
        detected.add(name)
      }
    }
    
    // Check dialogues: both character names and text content
    for (const dlg of (scene.dialogues || [])) {
      for (const name of allCharNames) {
        const nameLower = name.toLowerCase()
        const charLower = (dlg.character || '').toLowerCase()
        const textLower = (dlg.text || '').toLowerCase()
        
        if (charLower === nameLower || textLower.includes(nameLower)) {
          detected.add(name)
        }
      }
    }
    
    // Update scene characters if different
    const current = scene._scene_characters || []
    const detected_arr = Array.from(detected)
    if (JSON.stringify(current.sort()) !== JSON.stringify(detected_arr.sort())) {
      scene._scene_characters = detected_arr
      changed = true
    }
  }
  
  if (changed) {
    markDirty()
  }
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

function markDirty() {
  isDirty.value = true
  window.__lumiUnsaved = true
  emit('dirty')
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

function onGlobalSave() { if (isDirty.value) save() }
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
</style>

