<template>
  <div class="tab-panel video-tab">

    <!-- ── Toolbar ── -->
    <div class="video-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">视频生成</h3>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-danger btn-sm" v-if="running" @click="stopGeneration">⏹ 停止</button>
        <button
          class="btn btn-primary btn-sm"
          v-else
          :disabled="!selectedWorkflow || !scenes.length"
          @click="startGeneration"
        >▶ 开始生成</button>
      </div>
    </div>

    <!-- ── Config panel ── -->
    <div class="video-config card" v-if="!running">
      <div class="config-row">
        <div class="config-group">
          <label class="cfg-label">ComfyUI 工作流</label>
          <select class="input select-compact" v-model="selectedWorkflow">
            <option value="">— 选择工作流 —</option>
            <option v-for="wf in workflows" :key="wf" :value="wf">{{ wf }}</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">分辨率</label>
          <select class="input select-compact" v-model="resolution">
            <option>1920x1080</option>
            <option>1280x720</option>
            <option>1080x1920</option>
            <option>720x1280</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">帧率</label>
          <select class="input select-compact" v-model.number="fps" style="width:90px">
            <option :value="24">24fps</option>
            <option :value="30">30fps</option>
            <option :value="60">60fps</option>
          </select>
        </div>
      </div>

      <!-- Status pre-checks -->
      <div class="prechecks" v-if="scenes.length">
        <div class="precheck-item" :class="scenes.length ? 'ok' : 'warn'">
          <span>{{ scenes.length ? '✓' : '✗' }}</span>
          <span>分镜：{{ scenes.length }} 个</span>
        </div>
        <div class="precheck-item" :class="selectedWorkflow ? 'ok' : 'warn'">
          <span>{{ selectedWorkflow ? '✓' : '✗' }}</span>
          <span>工作流：{{ selectedWorkflow || '未选择' }}</span>
        </div>
      </div>

      <div v-if="!scenes.length && !loadingScenes" class="empty-state" style="padding:20px">
        <div class="empty-icon">🎞</div>
        <p>请先完成「分镜设计」</p>
      </div>
    </div>

    <!-- ── Generation progress ── -->
    <div v-if="running || genFinished" class="gen-progress-panel card">
      <!-- Overall progress -->
      <div class="progress-overall">
        <div class="progress-label">
          <span>整体进度</span>
          <span>{{ completedScenes }} / {{ scenes.length }} 个分镜</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: overallPct + '%' }" />
        </div>
      </div>

      <!-- Per-scene rows -->
      <div class="scene-progress-list">
        <div
          v-for="scene in scenes"
          :key="scene.id"
          class="scene-progress-row"
        >
          <span class="scene-num-sm">{{ String(scene.index).padStart(2, '0') }}</span>
          <span class="scene-desc-sm truncate">{{ scene.description || '（无描述）' }}</span>

          <!-- Status indicator -->
          <span class="scene-status" :class="sceneStatus(scene.id)">
            {{ sceneStatusLabel(scene.id) }}
          </span>

          <!-- Per-scene progress bar (only when in-progress) -->
          <div class="scene-mini-bar" v-if="sceneStatus(scene.id) === 'active'">
            <div class="scene-mini-fill" :style="{ width: sceneProgressPct(scene.id) + '%' }" />
          </div>
        </div>
      </div>
    </div>

    <!-- ── Result videos ── -->
    <div v-if="results.length" class="result-panel card">
      <div class="result-header">生成结果</div>
      <div v-for="r in results" :key="r.scene_id" class="result-item">
        <span class="scene-num-sm">{{ String(r.scene_index).padStart(2, '0') }}</span>
        <div class="result-thumbs">
          <img
            v-for="(img, i) in r.images"
            :key="i"
            :src="`data:image/png;base64,${img.data}`"
            class="result-thumb"
            :alt="`分镜${r.scene_index} 帧${i+1}`"
          />
        </div>
        <span class="text-muted" style="font-size:11px">{{ r.images.length }} 帧</span>
      </div>
    </div>

    <!-- ── Error banner ── -->
    <div v-if="genError" class="error-banner">
      ⚠ {{ genError }}
      <button class="btn btn-ghost btn-xs" @click="genError = ''">关闭</button>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps({ projectId: String })
const emit  = defineEmits(['dirty', 'saved'])

const API = 'http://localhost:18520/api'

// ── State ──────────────────────────────────────────────────────────────────────
const scenes          = ref([])
const loadingScenes   = ref(false)
const workflows       = ref([])
const selectedWorkflow = ref('')
const resolution      = ref('1920x1080')
const fps             = ref(30)
const running         = ref(false)
const genFinished     = ref(false)
const stopFlag        = ref(false)
const genError        = ref('')
const results         = ref([])   // [{scene_id, scene_index, images}]

// Per-scene progress tracking
const sceneState = ref({})    // scene_id → 'pending'|'active'|'done'|'error'
const sceneProgress = ref({}) // scene_id → {value, max}

// ── Helpers ────────────────────────────────────────────────────────────────────
const completedScenes = computed(() =>
  Object.values(sceneState.value).filter(s => s === 'done' || s === 'error').length
)
const overallPct = computed(() =>
  scenes.value.length ? Math.round((completedScenes.value / scenes.value.length) * 100) : 0
)

function sceneStatus(id)  { return sceneState.value[id] || 'pending' }
function sceneStatusLabel(id) {
  const s = sceneState.value[id] || 'pending'
  return { pending: '等待', active: '生成中', done: '✓ 完成', error: '✗ 错误' }[s] || ''
}
function sceneProgressPct(id) {
  const p = sceneProgress.value[id]
  if (!p || !p.max) return 0
  return Math.round((p.value / p.max) * 100)
}

// ── Load ───────────────────────────────────────────────────────────────────────
async function loadData() {
  loadingScenes.value = true
  try {
    const [scenesRes, settingsRes, wfRes] = await Promise.all([
      axios.get(`${API}/projects/${props.projectId}/scenes`),
      axios.get(`${API}/settings`),
      axios.get(`${API}/video-engine/workflows`).catch(() => ({ data: [] }))
    ])
    scenes.value    = scenesRes.data?.scenes || []
    const vCfg      = settingsRes.data?.video_engine || {}
    resolution.value = vCfg.resolution || '1920x1080'
    fps.value        = vCfg.fps ?? 30
    if (vCfg.default_workflow) selectedWorkflow.value = vCfg.default_workflow
    workflows.value  = wfRes.data || []
  } catch (e) {
    genError.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loadingScenes.value = false
  }
}

onMounted(loadData)

// ── Generation ─────────────────────────────────────────────────────────────────
let currentReader = null

async function startGeneration() {
  if (!selectedWorkflow.value) return
  running.value    = true
  genFinished.value = false
  stopFlag.value   = false
  genError.value   = ''
  results.value    = []

  // Init states
  const states = {}
  const progs  = {}
  for (const s of scenes.value) {
    states[s.id] = 'pending'
    progs[s.id]  = { value: 0, max: 1 }
  }
  sceneState.value    = states
  sceneProgress.value = progs

  const payload = {
    workflow_name: selectedWorkflow.value,
    resolution:    resolution.value,
    fps:           fps.value,
    scenes: scenes.value.map(s => ({
      scene_id:        s.id,
      scene_index:     s.index,
      start_image:     '',
      end_image:       '',
      duration:        s.duration_estimate ?? 4,
      positive_prompt: s.start_frame_prompt || s.description || '',
      negative_prompt: ''
    }))
  }

  try {
    const response = await fetch(`${API}/video-engine/generate-stream`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload)
    })

    currentReader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      if (stopFlag.value) { currentReader.cancel(); break }
      const { done, value } = await currentReader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') { genFinished.value = true; break }
        try { handleVideoEvent(JSON.parse(raw)) } catch {}
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

function handleVideoEvent(evt) {
  const { event, scene_id } = evt
  if (event === 'scene_start') {
    sceneState.value[scene_id] = 'active'
  } else if (event === 'progress') {
    if (scene_id) sceneProgress.value[scene_id] = { value: evt.value, max: evt.max }
  } else if (event === 'scene_done') {
    sceneState.value[scene_id] = 'done'
    results.value.push({
      scene_id,
      scene_index: evt.scene_index,
      images: evt.images || []
    })
  } else if (event === 'scene_error') {
    sceneState.value[scene_id] = 'error'
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
</script>

<style scoped>
/* ── Layout ── */
.video-tab {
  height: 100%;
  display: flex; flex-direction: column;
  gap: 0; overflow-y: auto;
}

/* ── Toolbar ── */
.video-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex-shrink: 0;
}
.toolbar-left  { display: flex; align-items: center; gap: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.toolbar-title { font-weight: 700; font-size: 15px; margin: 0; }

/* ── Config panel ── */
.video-config {
  margin: 14px;
  padding: 16px;
}
.config-row {
  display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end; margin-bottom: 14px;
}
.config-group { display: flex; flex-direction: column; gap: 6px; }
.cfg-label    { font-size: 12px; color: var(--text-muted); }
.select-compact { height: 32px; padding: 0 8px; font-size: 13px; min-width: 160px; }

/* ── Pre-checks ── */
.prechecks { display: flex; gap: 14px; margin-top: 6px; flex-wrap: wrap; }
.precheck-item {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; padding: 4px 10px;
  border-radius: 6px;
}
.precheck-item.ok   { background: rgba(72,187,120,.12); color: #48bb78; }
.precheck-item.warn { background: rgba(252,129,74,.12);  color: #fc814a; }

/* ── Empty ── */
.empty-state {
  display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--text-muted);
}
.empty-icon { font-size: 40px; }

/* ── Gen progress panel ── */
.gen-progress-panel {
  margin: 0 14px 14px;
  padding: 16px;
}
.progress-overall { margin-bottom: 14px; }
.progress-label {
  display: flex; justify-content: space-between;
  font-size: 12px; color: var(--text-muted); margin-bottom: 4px;
}
.progress-track { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
.progress-fill  { height: 100%; background: var(--accent); border-radius: 3px; transition: width .4s ease; }

/* ── Scene progress rows ── */
.scene-progress-list { display: flex; flex-direction: column; gap: 6px; }
.scene-progress-row  {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 0; border-bottom: 1px solid var(--border);
}
.scene-progress-row:last-child { border-bottom: none; }
.scene-num-sm  { font-size: 13px; font-weight: 700; color: var(--accent); min-width: 24px; }
.scene-desc-sm { font-size: 12px; flex: 1; min-width: 0; }
.scene-status  {
  font-size: 11px; padding: 2px 8px; border-radius: 4px; white-space: nowrap;
  flex-shrink: 0;
}
.scene-status.pending  { background: rgba(160,160,160,.12); color: var(--text-muted); }
.scene-status.active   { background: rgba(99,179,237,.15);  color: #63b3ed; }
.scene-status.done     { background: rgba(72,187,120,.12);  color: #48bb78; }
.scene-status.error    { background: rgba(252,129,74,.12);  color: #fc814a; }
.scene-mini-bar {
  width: 80px; height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; flex-shrink: 0;
}
.scene-mini-fill { height: 100%; background: var(--accent); transition: width .3s ease; }

/* ── Results ── */
.result-panel { margin: 0 14px 14px; padding: 16px; }
.result-header { font-weight: 700; font-size: 14px; margin-bottom: 12px; }
.result-item   { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); }
.result-item:last-child { border-bottom: none; }
.result-thumbs { display: flex; gap: 6px; flex-wrap: wrap; }
.result-thumb  { width: 80px; height: 56px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border); }

/* ── Error banner ── */
.error-banner {
  margin: 0 14px 14px;
  padding: 10px 14px;
  background: rgba(252,129,74,.12);
  color: #fc814a;
  border-radius: 8px;
  font-size: 13px;
  display: flex; align-items: center; gap: 10px;
}
.btn-danger { background: var(--danger,#e53e3e); color:#fff; border-color:var(--danger,#e53e3e); }
.btn-danger:hover { opacity:.85; }
.btn-xs { padding: 2px 6px; font-size: 12px; height: 24px; line-height: 1; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
