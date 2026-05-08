<template>
  <div class="tab-panel video-tab">

    <!-- ── Toolbar ── -->
    <div class="video-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">视频生成</h3>
        <span class="text-muted" style="font-size:13px" v-if="scenes.length">
          {{ readyCount }} / {{ scenes.length }} 个分镜就绪
        </span>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-danger btn-sm" v-if="running" @click="stopGeneration">⏹ 停止</button>
        <template v-else>
          <button
            class="btn btn-success btn-sm"
            :disabled="!allVideosReady || merging"
            :title="!allVideosReady ? '所有分镜视频生成完毕后才能合并' : '合并所有分镜视频'"
            @click="mergeVideos"
          >{{ merging ? '合并中…' : '🎬 合并视频' }}</button>
          <button
            class="btn btn-secondary btn-sm"
            :disabled="!scenes.length"
            title="为所有分镜自动生成视频提示词"
            @click="generateAllPrompts"
          >✦ 全部生成提示词</button>
          <button
            class="btn btn-primary btn-sm"
            :disabled="!selectedWorkflow || !readyCount"
            @click="startGeneration"
            :title="!readyCount ? '需要首帧图片、末帧图片和合并音频' : ''"
          >▶ 开始生成</button>
        </template>
      </div>
    </div>

    <!-- ── Config ── -->
    <div class="video-config card" v-if="!running">
      <div class="config-row">
        <div class="config-group">
          <label class="cfg-label">工作流</label>
          <select class="input select-compact" v-model="selectedWorkflow">
            <option value="">— 选择工作流 —</option>
            <option v-for="wf in workflows" :key="wf" :value="wf">{{ wf }}</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">分辨率（宽×高）</label>
          <select class="input select-compact" v-model="resolution">
            <option value="720x1280">720×1280（竖屏 HD）</option>
            <option value="1280x720">1280×720（横屏 HD）</option>
            <option value="576x1024">576×1024（竖屏 中）</option>
            <option value="1024x576">1024×576（横屏 中）</option>
            <option value="544x960">544×960（竖屏 小）</option>
            <option value="960x544">960×544（横屏 小）</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">帧率</label>
          <select class="input select-compact" v-model.number="fps" style="width:90px">
            <option :value="24">24fps</option>
            <option :value="25">25fps</option>
            <option :value="30">30fps</option>
          </select>
        </div>
      </div>
      <p class="config-hint">
        ⚠ 视频分辨率限制在 1280px 以内（本地算力有限），每边自动对齐至 32px 倍数
      </p>
    </div>

    <!-- ── Loading / Empty ── -->
    <div v-if="loadingScenes" class="empty-state"><div class="spinner" /><p class="text-muted">加载中…</p></div>
    <div v-else-if="!scenes.length" class="empty-state">
      <div class="empty-icon">🎞</div><p>请先完成「分镜设计」</p>
    </div>

    <!-- ── Overall progress ── -->
    <div v-if="(running || genFinished) && scenes.length" class="progress-wrap card">
      <div class="progress-label">
        <span>整体进度</span><span>{{ completedCount }} / {{ scenes.length }}</span>
      </div>
      <div class="progress-track"><div class="progress-fill" :style="{ width: overallPct + '%' }" /></div>
    </div>

    <!-- ── Scene list ── -->
    <div class="scene-video-list" v-if="scenes.length">
      <div v-for="scene in scenesWithData" :key="scene.id" class="scene-video-card card">

        <!-- Header -->
        <div class="svcard-header">
          <span class="scene-num">{{ String(scene.index).padStart(2,'0') }}</span>
          <span class="svcard-desc">{{ scene.description || '（无描述）' }}</span>
          <span class="svcard-status" :class="sceneStatusClass(scene.id)">
            {{ sceneStatusLabel(scene.id) }}
          </span>
          <!-- Per-scene regen button -->
          <button
            class="btn btn-ghost btn-xs"
            :disabled="running || !sceneReady(scene)"
            @click="generateOne(scene)"
            title="单独生成此分镜"
          >↺</button>
        </div>

        <!-- Readiness indicators -->
        <div class="asset-checks">
          <span class="asset-tag" :class="scene.hasStart ? 'ok' : 'miss'">
            {{ scene.hasStart ? '✓' : '✗' }} 首帧
          </span>
          <span class="asset-tag" :class="scene.hasEnd ? 'ok' : 'miss'">
            {{ scene.hasEnd ? '✓' : '✗' }} 末帧
          </span>
          <span class="asset-tag" :class="scene.hasAudio ? 'ok' : 'miss'">
            {{ scene.hasAudio ? '✓' : '✗' }} 合并音频
            <template v-if="scene.hasAudio"> ({{ formatMs(scene.audioDurationMs) }})</template>
          </span>
        </div>

        <!-- Prompt section -->
        <div class="prompt-section">
          <div class="prompt-header">
            <span class="prompt-label">
              视频提示词
              <span v-if="scenePrompts[scene.id]" class="prompt-set-badge">已设置</span>
            </span>
            <div class="prompt-actions">
              <button class="btn btn-ghost btn-xs" @click="generatePrompt(scene)" title="根据分镜信息自动生成提示词">
                ✦ 生成
              </button>
              <button
                v-if="scenePrompts[scene.id]"
                class="btn btn-ghost btn-xs"
                @click="togglePrompt(scene.id)"
              >{{ promptVisible[scene.id] ? '收起' : '展开' }}</button>
            </div>
          </div>
          <div v-if="promptVisible[scene.id]" class="prompt-editor-wrap">
            <textarea
              class="prompt-textarea"
              :value="scenePrompts[scene.id]"
              @input="onPromptInput(scene.id, $event.target.value)"
              placeholder="输入视频生成提示词，或点击「生成」自动填写…"
              rows="3"
            />
          </div>
        </div>

        <!-- Per-scene progress bar -->
        <div class="scene-mini-bar-wrap" v-if="sceneState[scene.id] === 'active'">
          <div class="scene-mini-bar">
            <div class="scene-mini-fill" :style="{ width: sceneProgressPct(scene.id) + '%' }" />
          </div>
          <span class="text-muted" style="font-size:11px">{{ sceneProgressPct(scene.id) }}%</span>
        </div>

        <!-- Video result -->
        <div v-if="sceneVideos[scene.id]" class="video-result">
          <video
            :src="'data:video/mp4;base64,' + sceneVideos[scene.id]"
            controls
            class="video-player"
          />
        </div>

      </div>
    </div>

    <!-- ── Error banner ── -->
    <div v-if="genError" class="error-banner">
      ⚠ {{ genError }}
      <button class="btn btn-ghost btn-xs" @click="genError = ''">关闭</button>
    </div>

    <!-- ── Merge result dialog ── -->
    <div v-if="mergeResult" class="merge-dialog-overlay" @click.self="mergeResult = null">
      <div class="merge-dialog card">
        <h4 class="merge-dialog-title">🎬 合并完成</h4>
        <p class="merge-dialog-path">{{ mergeResult.output_path }}</p>
        <div class="merge-dialog-actions">
          <button class="btn btn-primary" @click="openMergedVideo">▶ 打开视频</button>
          <button class="btn btn-secondary" @click="showMergedInFolder">📂 打开所在目录</button>
          <button class="btn btn-ghost" @click="mergeResult = null">关闭</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps({ projectId: String })
const emit  = defineEmits(['dirty', 'saved'])

const API = 'http://localhost:18520/api'

// ── state ──────────────────────────────────────────────────────────────────────
const scenes          = ref([])
const imagesData      = ref({})   // slot key → base64 PNG
const imagesSelected  = ref({})   // "{scene_id}:start"|":end" → slot_index
const audioData       = ref({})   // "__stitched__{sceneId}" → {data, duration_ms}
const loadingScenes   = ref(false)
const workflows       = ref([])
const selectedWorkflow = ref('')
const resolution      = ref('720x1280')
const fps             = ref(25)
const running         = ref(false)
const genFinished     = ref(false)
const stopFlag        = ref(false)
const genError        = ref('')
const sceneState      = ref({})   // id → pending|active|done|error
const sceneProgress   = ref({})   // id → {value, max}
const sceneVideos     = ref({})   // id → base64 mp4
const mergeResult     = ref(null) // { output_path, output_dir } once merged
const merging         = ref(false)
const scenePrompts    = ref({})   // scene_id → prompt string
const promptVisible   = ref({})   // scene_id → bool (expanded)
let _promptSaveTimer  = null

// ── derived ────────────────────────────────────────────────────────────────────
const scenesWithData = computed(() =>
  scenes.value.map(s => {
    const startKey = `${s.id}:start`
    const endKey   = `${s.id}:end`
    const startSlot = imagesSelected.value[startKey] ?? 0
    const endSlot   = imagesSelected.value[endKey]   ?? 0
    const startImg  = imagesData.value[`${startKey}:${startSlot}`] || null
    const endImg    = imagesData.value[`${endKey}:${endSlot}`]     || null
    const stitchKey = `__stitched__${s.id}`
    const stitched  = audioData.value[stitchKey] || null
    return {
      ...s,
      hasStart:      !!startImg,
      hasEnd:        !!endImg,
      hasAudio:      !!stitched,
      startImageB64: startImg || '',
      endImageB64:   endImg   || '',
      audioB64:      stitched?.data || '',
      audioDurationMs: stitched?.duration_ms || 0,
    }
  })
)

const readyCount = computed(() =>
  scenesWithData.value.filter(s => s.hasStart && s.hasEnd && s.hasAudio).length
)

const completedCount = computed(() =>
  Object.values(sceneState.value).filter(v => v === 'done' || v === 'error').length
)

const overallPct = computed(() =>
  scenes.value.length ? Math.round(completedCount.value / scenes.value.length * 100) : 0
)

const allVideosReady = computed(() =>
  scenes.value.length > 0 &&
  scenes.value.every(s => !!sceneVideos.value[s.id])
)

function sceneReady(s) { return s.hasStart && s.hasEnd && s.hasAudio }
function sceneStatusClass(id) { return sceneState.value[id] || 'pending' }
function sceneStatusLabel(id) {
  return ({ pending: '', active: '生成中…', done: '✓ 完成', error: '✗ 错误' })[sceneState.value[id]] || ''
}
function sceneProgressPct(id) {
  const p = sceneProgress.value[id]
  return p?.max ? Math.round(p.value / p.max * 100) : 0
}
function formatMs(ms) { return ms ? `${(ms/1000).toFixed(1)}s` : '' }

// ── load ───────────────────────────────────────────────────────────────────────
async function loadData() {
  if (!props.projectId) return
  loadingScenes.value = true
  try {
    const [scenesRes, imgRes, audRes, settingsRes, wfRes, vidRes, promptsRes] = await Promise.all([
      axios.get(`${API}/projects/${props.projectId}/scenes`),
      axios.get(`${API}/projects/${props.projectId}/images`).catch(() => ({ data: { slots: [], selected: {} } })),
      axios.get(`${API}/projects/${props.projectId}/audio`).catch(() => ({ data: {} })),
      axios.get(`${API}/settings`).catch(() => ({ data: {} })),
      axios.get(`${API}/video-engine/workflows`).catch(() => ({ data: [] })),
      axios.get(`${API}/projects/${props.projectId}/videos`).catch(() => ({ data: {} })),
      axios.get(`${API}/projects/${props.projectId}/video-prompts`).catch(() => ({ data: {} })),
    ])

    scenes.value = scenesRes.data?.scenes || []

    // Build images lookup: "{sceneId}:start:{slotIndex}" → base64
    const imgLookup = {}
    for (const slot of (imgRes.data?.slots || [])) {
      const key = `${slot.scene_id}:${slot.frame_type}:${slot.slot_index}`
      imgLookup[key] = slot.data
    }
    imagesData.value    = imgLookup
    imagesSelected.value = imgRes.data?.selected || {}

    // Audio stitched data
    // Also map reading-mode MS TTS clips (__ms_reading__{id}) into the same
    // __stitched__{id} key so scenesWithData picks them up transparently.
    const aud = audRes.data || {}
    const stitched = {}
    for (const [k, v] of Object.entries(aud)) {
      if (k.startsWith('__stitched__')) {
        stitched[k] = v
      } else if (k.startsWith('__ms_reading__')) {
        const sceneId = k.slice('__ms_reading__'.length)
        // Only apply if no stitched entry already exists for this scene
        if (!stitched[`__stitched__${sceneId}`]) {
          stitched[`__stitched__${sceneId}`] = v
        }
      }
    }
    audioData.value = stitched

    // Settings
    const vCfg = settingsRes.data?.video_engine || {}
    resolution.value = vCfg.resolution || '720x1280'
    fps.value        = vCfg.fps ?? 25
    if (vCfg.default_workflow) selectedWorkflow.value = vCfg.default_workflow
    workflows.value  = wfRes.data || []

    // Saved videos
    sceneVideos.value = vidRes.data || {}

    // Saved video prompts
    scenePrompts.value = promptsRes.data || {}

  } catch (e) {
    genError.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loadingScenes.value = false
  }
}

onMounted(loadData)

// ── generation ─────────────────────────────────────────────────────────────────
let currentReader = null

async function startGeneration() {
  if (!selectedWorkflow.value) return
  running.value     = true
  genFinished.value = false
  stopFlag.value    = false
  genError.value    = ''

  const states = {}
  for (const s of scenes.value) states[s.id] = 'pending'
  sceneState.value    = states
  sceneProgress.value = {}

  const readyScenes = scenesWithData.value.filter(sceneReady)
  await _runGeneration(readyScenes)
}

async function generateOne(scene) {
  if (running.value || !sceneReady(scene)) return
  running.value = true
  stopFlag.value = false
  sceneState.value = { ...sceneState.value, [scene.id]: 'pending' }
  await _runGeneration([scene])
}

function _buildPrompt(scene) {
  // Start with visual description
  const base = scene.start_frame_prompt || scene.description || ''
  // Add dialogue lines: only named characters, not narration
  const dialogues = (scene.dialogues || []).filter(d => d.character && d.character !== '旁白' && d.text)
  if (!dialogues.length) return base
  const dlgParts = dialogues.map(d => `${d.character} opens mouth saying: "${d.text}"`)
  return base ? `${base}. ${dlgParts.join(', ')}.` : dlgParts.join(', ') + '.'
}

function generatePrompt(scene) {
  const p = _buildPrompt(scene)
  scenePrompts.value = { ...scenePrompts.value, [scene.id]: p }
  promptVisible.value = { ...promptVisible.value, [scene.id]: true }
  _scheduleSavePrompts()
}

function generateAllPrompts() {
  const updated = { ...scenePrompts.value }
  const vis = { ...promptVisible.value }
  for (const s of scenesWithData.value) {
    updated[s.id] = _buildPrompt(s)
    vis[s.id] = true
  }
  scenePrompts.value  = updated
  promptVisible.value = vis
  _scheduleSavePrompts()
}

function togglePrompt(sceneId) {
  promptVisible.value = { ...promptVisible.value, [sceneId]: !promptVisible.value[sceneId] }
}

function onPromptInput(sceneId, value) {
  scenePrompts.value = { ...scenePrompts.value, [sceneId]: value }
  _scheduleSavePrompts()
}

function _scheduleSavePrompts() {
  clearTimeout(_promptSaveTimer)
  _promptSaveTimer = setTimeout(_savePrompts, 800)
}

async function _savePrompts() {
  if (!props.projectId) return
  try {
    await axios.put(`${API}/projects/${props.projectId}/video-prompts`, scenePrompts.value)
  } catch (e) {
    console.warn('提示词保存失败:', e)
  }
}

async function _runGeneration(sceneList) {
  const payload = {
    workflow_name: selectedWorkflow.value,
    resolution:    resolution.value,
    fps:           fps.value,
    scenes: sceneList.map(s => ({
      scene_id:        String(s.id),
      scene_index:     s.index,
      start_image_b64: s.startImageB64,
      end_image_b64:   s.endImageB64,
      audio_b64:       s.audioB64,
      duration_ms:     s.audioDurationMs || 4000,
      positive_prompt: scenePrompts.value[s.id] ?? _buildPrompt(s),
    }))
  }

  try {
    const response = await fetch(`${API}/video-engine/generate-stream`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    })
    currentReader = response.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      if (stopFlag.value) { currentReader.cancel(); break }
      const { done, value } = await currentReader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') { genFinished.value = true; break }
        try { handleEvent(JSON.parse(raw)) } catch {}
      }
    }
  } catch (e) {
    if (!stopFlag.value) genError.value = `生成失败: ${e.message}`
  } finally {
    running.value   = false
    currentReader   = null
    emit('dirty')
  }
}

function handleEvent(evt) {
  const { event, scene_id } = evt
  if (event === 'scene_start') {
    sceneState.value = { ...sceneState.value, [scene_id]: 'active' }
  } else if (event === 'progress') {
    sceneProgress.value = { ...sceneProgress.value, [scene_id]: { value: evt.value, max: evt.max } }
  } else if (event === 'scene_done') {
    sceneState.value = { ...sceneState.value, [scene_id]: 'done' }
    if (evt.video) {
      sceneVideos.value = { ...sceneVideos.value, [scene_id]: evt.video }
      // Persist all completed videos to project
      _saveVideos()
    }
  } else if (event === 'scene_error') {
    sceneState.value = { ...sceneState.value, [scene_id]: 'error' }
    genError.value = `分镜 ${scene_id} 失败: ${evt.message}`
  } else if (event === 'batch_done') {
    genFinished.value = true
  }
}

function stopGeneration() {
  stopFlag.value = true
  currentReader?.cancel()
  running.value = false
}

async function _saveVideos() {
  if (!props.projectId) return
  try {
    const slots = Object.entries(sceneVideos.value).map(([scene_id, data]) => ({ scene_id, data }))
    await axios.put(`${API}/projects/${props.projectId}/videos`, slots)
  } catch (e) {
    // Non-critical — just log, don't surface to user
    console.warn('视频保存失败:', e)
  }
}

async function mergeVideos() {
  if (!allVideosReady.value || merging.value) return
  merging.value = true
  genError.value = ''
  try {
    const scene_order = scenes.value.map(s => String(s.id))
    const { data } = await axios.post(`${API}/video-engine/merge-project-video`, {
      project_id: props.projectId,
      scene_order,
    })
    mergeResult.value = data
  } catch (e) {
    genError.value = e?.response?.data?.detail || e.message || '合并失败'
  } finally {
    merging.value = false
  }
}

async function openMergedVideo() {
  if (!mergeResult.value) return
  await window.electronAPI?.openPath(mergeResult.value.output_path)
  mergeResult.value = null
}

async function showMergedInFolder() {
  if (!mergeResult.value) return
  await window.electronAPI?.showItemInFolder(mergeResult.value.output_path)
  mergeResult.value = null
}
</script>

<style scoped>
.video-tab { display:flex; flex-direction:column; height:100%; overflow:hidden; }
.video-toolbar {
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 16px 8px; flex-shrink:0;
}
.toolbar-left  { display:flex; align-items:center; gap:12px; }
.toolbar-right { display:flex; align-items:center; gap:8px; }
.toolbar-title { margin:0; font-size:15px; font-weight:600; }

.video-config  { flex-shrink:0; margin:0 16px 8px; padding:12px; }
.config-row    { display:flex; flex-wrap:wrap; gap:12px; }
.config-group  { display:flex; align-items:center; gap:6px; }
.cfg-label     { font-size:12px; color:var(--text-muted); white-space:nowrap; }
.select-compact { font-size:12px; }
.config-hint   { margin:8px 0 0; font-size:11px; color:var(--text-muted); }

.progress-wrap { flex-shrink:0; margin:0 16px 8px; padding:10px 12px; }
.progress-label { display:flex; justify-content:space-between; font-size:12px; color:var(--text-muted); margin-bottom:4px; }
.progress-track { height:6px; border-radius:4px; background:var(--bg-tertiary); overflow:hidden; }
.progress-fill  { height:100%; background:var(--accent); transition:width .3s; }

.scene-video-list {
  flex:1; overflow-y:auto; padding:0 16px 16px; display:flex; flex-direction:column; gap:10px;
}
.scene-video-card { padding:12px; display:flex; flex-direction:column; gap:8px; }

.svcard-header { display:flex; align-items:center; gap:8px; }
.svcard-desc   { flex:1; font-size:13px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.svcard-status { font-size:12px; font-weight:600; }
.svcard-status.active { color:var(--accent); }
.svcard-status.done   { color:var(--color-success,#4caf50); }
.svcard-status.error  { color:var(--color-error,#f44336); }

.scene-num { font-size:11px; font-weight:700; background:var(--accent); color:#fff; border-radius:4px; padding:1px 6px; }

.asset-checks { display:flex; gap:6px; flex-wrap:wrap; }
.asset-tag { font-size:11px; padding:2px 7px; border-radius:10px; border:1px solid; font-weight:500; }
.asset-tag.ok   { border-color:var(--color-success,#4caf50); color:var(--color-success,#4caf50); }
.asset-tag.miss { border-color:var(--color-warning,#ff9800); color:var(--color-warning,#ff9800); }

.scene-mini-bar-wrap { display:flex; align-items:center; gap:8px; }
.scene-mini-bar { flex:1; height:4px; border-radius:2px; background:var(--bg-tertiary); overflow:hidden; }
.scene-mini-fill{ height:100%; background:var(--accent); transition:width .2s; }

.video-result { border-top:1px dashed var(--border-color); padding-top:8px; }
.video-player { width:100%; max-height:320px; border-radius:6px; background:#000; }

.empty-state {
  flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; opacity:.7;
}
.empty-icon { font-size:40px; }
.spinner { width:24px; height:24px; border:2px solid var(--border-color); border-top-color:var(--accent); border-radius:50%; animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }

.error-banner {
  flex-shrink:0; margin:0 16px 8px; padding:8px 12px; border-radius:6px;
  background:color-mix(in srgb, var(--color-error,#f44336) 12%, transparent);
  border:1px solid var(--color-error,#f44336);
  font-size:13px; display:flex; align-items:center; gap:8px;
}

.merge-dialog-overlay {
  position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:200;
  display:flex; align-items:center; justify-content:center;
}
.merge-dialog {
  min-width:360px; max-width:520px; padding:20px 24px; display:flex; flex-direction:column; gap:14px;
}
.merge-dialog-title { margin:0; font-size:16px; font-weight:700; }
.merge-dialog-path {
  font-size:12px; color:var(--text-muted); word-break:break-all;
  background:var(--bg-tertiary); padding:6px 10px; border-radius:4px;
}
.merge-dialog-actions { display:flex; gap:8px; justify-content:flex-end; flex-wrap:wrap; }

/* ── Prompt section ── */
.prompt-section {
  border-top: 1px dashed var(--border-color);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.prompt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.prompt-label {
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}
.prompt-set-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent);
}
.prompt-actions { display: flex; gap: 4px; }
.prompt-editor-wrap { display: flex; flex-direction: column; gap: 4px; }
.prompt-textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  font-size: 12px;
  line-height: 1.5;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-family: inherit;
  min-height: 64px;
}
.prompt-textarea:focus {
  outline: none;
  border-color: var(--accent);
}
</style>
