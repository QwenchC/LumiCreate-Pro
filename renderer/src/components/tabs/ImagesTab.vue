<template>
  <div class="tab-panel images-tab">

    <!-- == Toolbar == -->
    <div class="img-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">图片生成</h3>
        <span class="scene-count text-muted" v-if="scenes.length">
          {{ scenes.length }} 个分镜 · 每帧 {{ genCount }} 张 · {{ imgWidth }}×{{ imgHeight }}</span>
      </div>
      <div class="toolbar-right">
        <select class="input select-compact" v-model="selectedWorkflow" :disabled="running">
          <option value="">— 选择工作流 —</option>
          <option v-for="wf in workflows" :key="wf" :value="wf">{{ wf }}</option>
        </select>
        <div class="gen-count-group">
          <label class="text-muted" style="font-size:12px;white-space:nowrap">每帧张数</label>
          <input class="input input-num" type="number" min="1" max="10" step="1"
            v-model.number="genCount" :disabled="running" />
        </div>
        <template v-if="running && !paused">
          <button class="btn btn-warning btn-sm" @click="pauseBatch">⏸ 暂停</button>
        </template>
        <template v-else-if="paused">
          <button class="btn btn-primary btn-sm" @click="resumeBatch">▶ 继续</button>
          <button class="btn btn-secondary btn-sm" @click="cancelBatch">✕ 取消</button>
        </template>
        <template v-else>
          <button class="btn btn-primary btn-sm"
            :disabled="!selectedWorkflow || !scenes.length" @click="startBatch">▶ 全部生成</button>
        </template>
      </div>
    </div>

    <!-- == Progress bar == -->
    <div v-if="running || paused || batchDone" class="batch-progress-bar-wrap">
      <div class="batch-progress-label">
        <span v-if="paused">⏸ 已暂停 · 下次从第 {{ batchResumeFrom + 1 }} 个分镜继续</span>
        <span v-else-if="running && batchCurrentIdx >= 0">生成中 · 第 {{ batchCurrentIdx + 1 }}/{{ scenes.length }} 个分镜</span>
        <span v-else-if="batchDone">✔ 生成完成</span>
        <span v-else>准备中…</span>
        <span>{{ completedCount }} / {{ totalCount }}</span>
      </div>
      <div class="batch-progress-track">
        <div class="batch-progress-fill" :style="{ width: progressPct + '%' }" />
      </div>
    </div>

    <!-- == States == -->
    <div v-if="loadError" class="full-state error-state">
      <div class="state-icon">⚠</div><p>{{ loadError }}</p>
      <button class="btn btn-secondary btn-sm" @click="loadData">重试</button>
    </div>
    <div v-else-if="!scenes.length && !loadingScenes" class="full-state empty-state">
      <div class="state-icon">🎞</div><p>请先在「分镜设计」完成分镜并保存</p>
    </div>
    <div v-else-if="loadingScenes" class="full-state empty-state">
      <div class="spinner" /><p class="text-muted">加载分镜中…</p>
    </div>

    <!-- == Main: left list + right detail == -->
    <div v-else class="images-main">

      <!-- Left panel: scene list -->
      <div class="scene-list-panel">
        <div
          v-for="scene in scenes" :key="scene.id"
          class="scene-list-item"
          :class="{
            active: activeSceneId === scene.id,
            generating: !!sceneGenerating[scene.id],
            'batch-current': batchCurrentIdx >= 0 && scenes[batchCurrentIdx]?.id === scene.id
          }"
          @click="activeSceneId = scene.id"
        >
          <div class="scene-list-thumbs">
            <div class="mini-thumb">
              <img v-if="getImage(scene.id, 'start', scene._selected_start)"
                   :src="getImage(scene.id, 'start', scene._selected_start)" />
              <div v-else-if="isLoading(scene.id, 'start', scene._selected_start)" class="mini-spinner"><div class="spinner spinner-xs"/></div>
              <div v-else class="mini-empty">首</div>
            </div>
            <div class="mini-thumb">
              <img v-if="getImage(scene.id, 'end', scene._selected_end)"
                   :src="getImage(scene.id, 'end', scene._selected_end)" />
              <div v-else-if="isLoading(scene.id, 'end', scene._selected_end)" class="mini-spinner"><div class="spinner spinner-xs"/></div>
              <div v-else class="mini-empty">尾</div>
            </div>
          </div>
          <div class="scene-list-info">
            <div class="scene-list-num">{{ String(scene.index).padStart(2,'0') }}</div>
            <div class="scene-list-desc truncate">{{ scene.description || '(无描述)' }}</div>
            <div class="scene-list-status">
              <span v-if="sceneGenerating[scene.id]" class="status-dot dot-active">⏳</span>
              <span v-else-if="hasAnyImage(scene)" class="status-dot dot-done">✓</span>
            </div>
          </div>
          <button class="scene-list-gen-btn"
            :disabled="running || !!sceneGenerating[scene.id] || !selectedWorkflow"
            @click.stop="generateOneScene(scene)" :title="'生成此分镜'">
            <span v-if="sceneGenerating[scene.id]">⏳</span>
            <span v-else>▶</span>
          </button>
        </div>
      </div>

      <!-- Right panel: detail -->
      <div class="scene-detail-panel" v-if="activeScene">
        <div class="detail-header">
          <span class="detail-num">{{ String(activeScene.index).padStart(2,'0') }}</span>
          <span class="detail-desc truncate">{{ activeScene.description || '(无描述)' }}</span>
          <button class="btn btn-secondary btn-sm"
            :disabled="running || !!sceneGenerating[activeScene.id] || !selectedWorkflow"
            @click="generateOneScene(activeScene)">
            <span v-if="sceneGenerating[activeScene.id]">⏳ 生成中…</span>
            <span v-else>▶ 生成此分镜</span>
          </button>
        </div>

        <!-- Start frame -->
        <div class="detail-frame-section">
          <div class="detail-frame-header">
            <span class="frame-badge badge-blue">首帧</span>
            <span class="frame-prompt text-muted truncate">{{ activeScene.start_frame_prompt || '(无提示词)' }}</span>
            <button class="btn btn-ghost btn-xs" :disabled="running" @click="regenFrame(activeScene,'start')">↺ 重新生成所有</button>
          </div>
          <div class="image-slots">
            <div
              v-for="slot in getFrameSlotCount(activeScene.id, 'start')" :key="slot-1"
              class="image-slot"
              :class="{
                selected: activeScene._selected_start === slot-1,
                loading:  isLoading(activeScene.id,'start',slot-1),
                errored:  isErrored(activeScene.id,'start',slot-1)
              }"
              @click="selectImage(activeScene,'start',slot-1)"
            >
              <img v-if="getImage(activeScene.id,'start',slot-1)"
                   :src="getImage(activeScene.id,'start',slot-1)" alt="首帧" />
              <div v-else-if="isLoading(activeScene.id,'start',slot-1)" class="slot-loading">
                <div class="spinner spinner-sm"/>
                <span class="slot-progress-text">{{ getProgress(activeScene.id,'start',slot-1) }}</span>
              </div>
              <div v-else-if="isErrored(activeScene.id,'start',slot-1)" class="slot-error">
                <span>⚠</span><span class="slot-err-msg">{{ getError(activeScene.id,'start',slot-1) }}</span>
              </div>
              <div v-else class="slot-empty"><span>{{ slot }}</span></div>
              <div v-if="getImage(activeScene.id,'start',slot-1)" class="slot-overlay">
                <button class="slot-overlay-btn" @click.stop="openPreview(activeScene,'start',slot-1)" :title="'预览'">⛶</button>
                <button class="slot-overlay-btn slot-overlay-del" @click.stop="deleteSlot(activeScene,'start',slot-1)" :title="'删除'">🗑</button>
              </div>
              <div class="selected-badge" v-if="activeScene._selected_start === slot-1">✓</div>
            </div>
            <button class="image-slot slot-add"
              :disabled="running || !!sceneGenerating[activeScene.id] || !selectedWorkflow"
              @click="addOneMore(activeScene,'start')" :title="'再生成一张'">＋</button>
          </div>
        </div>

        <!-- End frame -->
        <div class="detail-frame-section">
          <div class="detail-frame-header">
            <span class="frame-badge badge-purple">尾帧</span>
            <span class="frame-prompt text-muted truncate">{{ activeScene.end_frame_prompt || '(无提示词)' }}</span>
            <button class="btn btn-ghost btn-xs" :disabled="running" @click="regenFrame(activeScene,'end')">↺ 重新生成所有</button>
          </div>
          <div class="image-slots">
            <div
              v-for="slot in getFrameSlotCount(activeScene.id, 'end')" :key="slot-1"
              class="image-slot"
              :class="{
                selected: activeScene._selected_end === slot-1,
                loading:  isLoading(activeScene.id,'end',slot-1),
                errored:  isErrored(activeScene.id,'end',slot-1)
              }"
              @click="selectImage(activeScene,'end',slot-1)"
            >
              <img v-if="getImage(activeScene.id,'end',slot-1)"
                   :src="getImage(activeScene.id,'end',slot-1)" alt="尾帧" />
              <div v-else-if="isLoading(activeScene.id,'end',slot-1)" class="slot-loading">
                <div class="spinner spinner-sm"/>
                <span class="slot-progress-text">{{ getProgress(activeScene.id,'end',slot-1) }}</span>
              </div>
              <div v-else-if="isErrored(activeScene.id,'end',slot-1)" class="slot-error">
                <span>⚠</span><span class="slot-err-msg">{{ getError(activeScene.id,'end',slot-1) }}</span>
              </div>
              <div v-else class="slot-empty"><span>{{ slot }}</span></div>
              <div v-if="getImage(activeScene.id,'end',slot-1)" class="slot-overlay">
                <button class="slot-overlay-btn" @click.stop="openPreview(activeScene,'end',slot-1)" :title="'预览'">⛶</button>
                <button class="slot-overlay-btn slot-overlay-del" @click.stop="deleteSlot(activeScene,'end',slot-1)" :title="'删除'">🗑</button>
              </div>
              <div class="selected-badge" v-if="activeScene._selected_end === slot-1">✓</div>
            </div>
            <button class="image-slot slot-add"
              :disabled="running || !!sceneGenerating[activeScene.id] || !selectedWorkflow"
              @click="addOneMore(activeScene,'end')" :title="'再生成一张'">＋</button>
          </div>
        </div>
      </div>

      <!-- Right panel: no scene selected -->
      <div v-else class="scene-detail-panel empty-detail">
        <div class="state-icon">👈</div>
        <p class="text-muted">从左侧选择一个分镜</p>
      </div>
    </div>

    <!-- == Lightbox == -->
    <div v-if="lightbox" class="lightbox-overlay" @click.self="closePreview">
      <button class="lightbox-close" @click="closePreview">✕</button>
      <button class="lightbox-nav lightbox-prev" @click="lightboxNav(-1)">‹</button>
      <div class="lightbox-body">
        <img :src="lightbox.src" class="lightbox-img" />
        <div class="lightbox-footer">{{ lightboxTitle }} · 第 {{ lightbox.slotIndex + 1 }} 张</div>
      </div>
      <button class="lightbox-nav lightbox-next" @click="lightboxNav(1)">›</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import axios from 'axios'

const props = defineProps({ projectId: String })
const emit = defineEmits(['dirty', 'saved'])

const API = 'http://localhost:18520/api'

const scenes          = ref([])
const loadingScenes   = ref(false)
const loadError       = ref('')
const workflows       = ref([])
const selectedWorkflow = ref('')
const genCount        = ref(3)
const imgWidth        = ref(1920)
const imgHeight       = ref(1080)

const activeSceneId = ref(null)
const activeScene   = computed(() => scenes.value.find(s => s.id === activeSceneId.value) ?? null)
watch(scenes, (list) => { if (list.length && !activeSceneId.value) activeSceneId.value = list[0].id }, { immediate: true })

// Persist selected workflow back to global settings whenever user changes it
let _workflowWatchInitialized = false
watch(selectedWorkflow, async (val) => {
  if (!_workflowWatchInitialized) { _workflowWatchInitialized = true; return }
  try {
    const res = await axios.get(API + '/settings')
    const s = res.data
    s.image_engine = { ...(s.image_engine || {}), default_workflow: val }
    await axios.post(API + '/settings', s)
  } catch {}
})

function hasAnyImage(scene) {
  for (const ft of ['start', 'end']) {
    const count = getFrameSlotCount(scene.id, ft)
    for (let s = 0; s < count; s++) {
      if (getImage(scene.id, ft, s)) return true
    }
  }
  return false
}

const running          = ref(false)
const paused           = ref(false)
const batchDone        = ref(false)
const batchCurrentIdx  = ref(-1)
const batchResumeFrom  = ref(0)
const sceneGenerating  = ref({})
const frameSlotCounts  = ref({})

const lightbox = ref(null)
const lightboxTitle = computed(() => {
  if (!lightbox.value) return ''
  const s = scenes.value.find(x => x.id === lightbox.value.sceneId)
  const label = lightbox.value.frameType === 'start' ? '首帧' : '尾帧'
  return s ? ('分镜 ' + String(s.index).padStart(2,'0') + ' · ' + label) : label
})

const slotImages    = ref({})
const slotLoading   = ref({})
const slotError     = ref({})
const slotProgress  = ref({})

function getFrameSlotCount(sceneId, frameType) {
  return frameSlotCounts.value[sceneId + ':' + frameType] ?? genCount.value
}
function setFrameSlotCount(sceneId, frameType, n) {
  frameSlotCounts.value = { ...frameSlotCounts.value, [sceneId + ':' + frameType]: n }
}
function slotKey(sceneId, frameType, slot) {
  return sceneId + ':' + frameType + ':' + slot
}
function getImage(sceneId, frameType, slot) {
  return slotImages.value[slotKey(sceneId, frameType, slot)] || null
}
function isLoading(sceneId, frameType, slot) {
  return !!slotLoading.value[slotKey(sceneId, frameType, slot)]
}
function isErrored(sceneId, frameType, slot) {
  return !!slotError.value[slotKey(sceneId, frameType, slot)]
}
function getError(sceneId, frameType, slot) {
  return slotError.value[slotKey(sceneId, frameType, slot)] || ''
}
function getProgress(sceneId, frameType, slot) {
  return slotProgress.value[slotKey(sceneId, frameType, slot)] || ''
}

const totalCount = computed(() => scenes.value.length * 2 * genCount.value)
const completedCount = computed(() =>
  Object.values(slotImages.value).filter(Boolean).length +
  Object.values(slotError.value).filter(Boolean).length
)
const progressPct = computed(() =>
  totalCount.value > 0 ? Math.round((completedCount.value / totalCount.value) * 100) : 0
)

async function loadData() {
  loadError.value = ''
  loadingScenes.value = true
  try {
    const [scenesRes, settingsRes, workflowsRes, imagesRes] = await Promise.all([
      axios.get(API + '/projects/' + props.projectId + '/scenes'),
      axios.get(API + '/settings'),
      axios.get(API + '/image-engine/workflows').catch(() => ({ data: [] })),
      axios.get(API + '/projects/' + props.projectId + '/images').catch(() => ({ data: { slots: [], counts: {}, selected: {} } }))
    ])
    scenes.value = ((scenesRes.data?.scenes) || []).map(s => ({
      ...s,
      _selected_start: s._selected_start ?? 0,
      _selected_end:   s._selected_end   ?? 0
    }))
    const imgCfg = settingsRes.data?.image_engine || {}
    genCount.value  = imgCfg.default_gen_count ?? 3
    imgWidth.value  = imgCfg.image_width  ?? 1920
    imgHeight.value = imgCfg.image_height ?? 1080
    if (imgCfg.default_workflow) selectedWorkflow.value = imgCfg.default_workflow
    workflows.value = workflowsRes.data || []
    const imgState = imagesRes.data
    const newSlotImages = {}
    for (const slot of imgState.slots || []) {
      newSlotImages[slotKey(slot.scene_id, slot.frame_type, slot.slot_index)] = 'data:image/png;base64,' + slot.data
    }
    slotImages.value = newSlotImages
    frameSlotCounts.value = imgState.counts || {}
    const selectedMap = imgState.selected || {}
    for (const scene of scenes.value) {
      const ss = selectedMap[scene.id + ':start']
      const se = selectedMap[scene.id + ':end']
      if (ss !== undefined) scene._selected_start = ss
      if (se !== undefined) scene._selected_end = se
    }
  } catch (e) {
    loadError.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loadingScenes.value = false
  }
}

async function saveImages() {
  const slots = []
  for (const [key, dataUrl] of Object.entries(slotImages.value)) {
    if (!dataUrl) continue
    const parts = key.split(':')
    const sceneId = parts[0], frameType = parts[1], slotIndex = Number(parts[2])
    const data = dataUrl.replace(/^data:image\/\w+;base64,/, '')
    slots.push({ scene_id: sceneId, frame_type: frameType, slot_index: slotIndex, data })
  }
  const selected = {}
  for (const scene of scenes.value) {
    selected[scene.id + ':start'] = scene._selected_start ?? 0
    selected[scene.id + ':end']   = scene._selected_end   ?? 0
  }
  try {
    await axios.put(API + '/projects/' + props.projectId + '/images', {
      slots, counts: frameSlotCounts.value, selected
    })
  } catch (e) {
    console.error('Failed to save images:', e)
  }
}

function onKeyDown(e) {
  if (!lightbox.value) return
  if (e.key === 'Escape')      closePreview()
  if (e.key === 'ArrowLeft')   lightboxNav(-1)
  if (e.key === 'ArrowRight')  lightboxNav(1)
}
onMounted(() => {
  loadData()
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('lumi:save-project', saveImages)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('lumi:save-project', saveImages)
})

let currentReader = null

function handleSlotEvent(evt) {
  const { event, scene_id, frame_type, slot_index } = evt
  if (!scene_id) return
  const key = slotKey(scene_id, frame_type, slot_index)
  if (event === 'progress') {
    slotProgress.value[key] = evt.value + '/' + evt.max
  } else if (event === 'completed') {
    slotLoading.value[key]  = false
    slotProgress.value[key] = ''
    const first = (evt.images || [])[0]
    if (first?.data) slotImages.value[key] = 'data:image/png;base64,' + first.data
  } else if (event === 'error') {
    slotLoading.value[key] = false
    slotError.value[key]   = evt.message || '错误'
  }
}

async function generateSceneSlots(scene, { skipExisting = false } = {}) {
  let frames = []
  if (scene.start_frame_prompt)
    frames.push({ scene_id: scene.id, frame_type: 'start', prompt: scene.start_frame_prompt })
  if (scene.end_frame_prompt)
    frames.push({ scene_id: scene.id, frame_type: 'end',   prompt: scene.end_frame_prompt })
  if (!frames.length) return

  if (skipExisting) {
    frames = frames.filter(f => {
      for (let s = 0; s < genCount.value; s++) {
        if (!slotImages.value[slotKey(f.scene_id, f.frame_type, s)]) return true
      }
      return false
    })
    if (!frames.length) return
  }

  for (const f of frames) {
    setFrameSlotCount(f.scene_id, f.frame_type, genCount.value)
    for (let s = 0; s < genCount.value; s++) {
      const key = slotKey(f.scene_id, f.frame_type, s)
      slotLoading.value[key]  = true
      slotImages.value[key]   = undefined
      slotError.value[key]    = ''
      slotProgress.value[key] = ''
    }
  }

  function markFramesError(msg) {
    for (const f of frames) {
      for (let s = 0; s < genCount.value; s++) {
        const key = slotKey(f.scene_id, f.frame_type, s)
        slotLoading.value[key] = false
        slotError.value[key]   = msg
      }
    }
  }

  let response
  try {
    response = await fetch(API + '/image-engine/generate-batch-stream', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflow_name:   selectedWorkflow.value,
        gen_count:       genCount.value,
        negative_prompt: '',
        width:           imgWidth.value,
        height:          imgHeight.value,
        frames
      })
    })
  } catch (e) {
    const msg = '网络错误: ' + e.message
    markFramesError(msg)
    throw new Error(msg)
  }

  if (!response.ok) {
    let detail = 'HTTP ' + response.status
    try { const j = await response.json(); detail = j.detail || detail } catch {}
    markFramesError(detail)
    throw new Error(detail)
  }

  await new Promise((resolve) => {
    ;(async () => {
      const reader  = response.body.getReader()
      currentReader = reader
      const decoder = new TextDecoder()
      let buffer = ''
      try {
        while (true) {
          let result
          try { result = await reader.read() } catch { break }
          const { done, value } = result
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (raw === '[DONE]') { resolve(); return }
            try { handleSlotEvent(JSON.parse(raw)) } catch {}
          }
        }
      } finally {
        for (const f of frames) {
          for (let s = 0; s < genCount.value; s++) {
            const key = slotKey(f.scene_id, f.frame_type, s)
            if (slotLoading.value[key]) slotLoading.value[key] = false
          }
        }
        currentReader = null
        resolve()
      }
    })()
  })
}

async function _runBatchFrom(fromIdx) {
  running.value         = true
  paused.value          = false
  batchCurrentIdx.value = -1
  for (let i = fromIdx; i < scenes.value.length; i++) {
    if (paused.value) { batchResumeFrom.value = i; break }
    batchCurrentIdx.value = i
    batchResumeFrom.value = i
    try {
      await generateSceneSlots(scenes.value[i], { skipExisting: true })
    } catch (e) {
      if (!paused.value) { loadError.value = e.message; batchResumeFrom.value = i; paused.value = true }
      break
    }
    if (paused.value) { batchResumeFrom.value = i; break }
  }
  running.value         = false
  batchCurrentIdx.value = -1
  if (!paused.value) batchDone.value = true
  emit('dirty')
}

function startBatch() {
  slotError.value = {}; slotProgress.value = {}
  slotLoading.value = {}
  batchDone.value = false; batchResumeFrom.value = 0
  _runBatchFrom(0)
}
function pauseBatch()  { paused.value = true; currentReader?.cancel() }
function resumeBatch() { batchDone.value = false; _runBatchFrom(batchResumeFrom.value) }
function cancelBatch() {
  paused.value = false; running.value = false; batchDone.value = false
  batchCurrentIdx.value = -1; currentReader?.cancel(); currentReader = null
}

async function generateOneScene(scene) {
  if (running.value || sceneGenerating.value[scene.id]) return
  sceneGenerating.value = { ...sceneGenerating.value, [scene.id]: true }
  try {
    await generateSceneSlots(scene)
    emit('dirty')
  } finally {
    const next = { ...sceneGenerating.value }
    delete next[scene.id]
    sceneGenerating.value = next
  }
}

async function regenFrame(scene, frameType) {
  const prompt = frameType === 'start' ? scene.start_frame_prompt : scene.end_frame_prompt
  if (!prompt || !selectedWorkflow.value) return
  setFrameSlotCount(scene.id, frameType, genCount.value)
  for (let s = 0; s < genCount.value; s++) {
    const key = slotKey(scene.id, frameType, s)
    slotLoading.value[key] = true; slotImages.value[key] = undefined
    slotError.value[key] = ''; slotProgress.value[key] = ''
  }
  const promises = Array.from({ length: genCount.value }, (_, s) =>
    runSingleSlot(scene.id, frameType, s, prompt)
  )
  await Promise.allSettled(promises)
  emit('dirty')
}

async function runSingleSlot(sceneId, frameType, slotIndex, prompt) {
  const key = slotKey(sceneId, frameType, slotIndex)
  try {
    const response = await fetch(API + '/image-engine/generate-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflow_name: selectedWorkflow.value, positive_prompt: prompt,
        negative_prompt: '', width: imgWidth.value, height: imgHeight.value,
        scene_id: sceneId, frame_type: frameType, slot_index: slotIndex
      })
    })
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        try { handleSlotEvent(JSON.parse(raw)) } catch {}
      }
    }
  } catch (e) {
    slotError.value[key] = e.message; slotLoading.value[key] = false
  }
}

function selectImage(scene, frameType, slotIndex) {
  if (!getImage(scene.id, frameType, slotIndex)) return
  if (frameType === 'start') scene._selected_start = slotIndex
  else                        scene._selected_end   = slotIndex
  emit('dirty')
}

function openPreview(scene, frameType, slotIndex) {
  const src = getImage(scene.id, frameType, slotIndex)
  if (!src) return
  lightbox.value = { src, sceneId: scene.id, frameType, slotIndex }
}
function closePreview() { lightbox.value = null }
function lightboxNav(dir) {
  if (!lightbox.value) return
  const { sceneId, frameType, slotIndex } = lightbox.value
  const count = getFrameSlotCount(sceneId, frameType)
  let next = (slotIndex + dir + count) % count
  for (let i = 0; i < count; i++) {
    const img = getImage(sceneId, frameType, next)
    if (img) { lightbox.value = { ...lightbox.value, src: img, slotIndex: next }; return }
    next = (next + dir + count) % count
  }
}

function deleteSlot(scene, frameType, slotIndex) {
  const count = getFrameSlotCount(scene.id, frameType)
  for (let i = slotIndex; i < count - 1; i++) {
    const from = slotKey(scene.id, frameType, i + 1)
    const to   = slotKey(scene.id, frameType, i)
    slotImages.value[to] = slotImages.value[from]; slotError.value[to] = slotError.value[from]
    slotProgress.value[to] = slotProgress.value[from]; slotLoading.value[to] = slotLoading.value[from]
  }
  const lastKey = slotKey(scene.id, frameType, count - 1)
  const imgs = { ...slotImages.value }; delete imgs[lastKey]; slotImages.value = imgs
  const errs = { ...slotError.value };  delete errs[lastKey]; slotError.value  = errs
  const prgs = { ...slotProgress.value }; delete prgs[lastKey]; slotProgress.value = prgs
  const lds  = { ...slotLoading.value };  delete lds[lastKey];  slotLoading.value  = lds
  setFrameSlotCount(scene.id, frameType, Math.max(1, count - 1))
  const selKey = frameType === 'start' ? '_selected_start' : '_selected_end'
  if (scene[selKey] >= count - 1) scene[selKey] = Math.max(0, count - 2)
  else if (scene[selKey] > slotIndex) scene[selKey]--
  if (lightbox.value?.sceneId === scene.id && lightbox.value?.frameType === frameType
      && lightbox.value?.slotIndex === slotIndex) closePreview()
  emit('dirty')
}

async function addOneMore(scene, frameType) {
  const prompt = frameType === 'start' ? scene.start_frame_prompt : scene.end_frame_prompt
  if (!prompt || !selectedWorkflow.value) return
  const newSlot = getFrameSlotCount(scene.id, frameType)
  setFrameSlotCount(scene.id, frameType, newSlot + 1)
  const key = slotKey(scene.id, frameType, newSlot)
  slotLoading.value[key] = true; slotImages.value[key] = undefined
  slotError.value[key] = ''; slotProgress.value[key] = ''
  await runSingleSlot(scene.id, frameType, newSlot, prompt)
  emit('dirty')
}
</script>

<style scoped>
.images-tab {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.img-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex-shrink: 0;
  gap: 12px;
  flex-wrap: wrap;
}
.toolbar-left  { display: flex; align-items: center; gap: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.toolbar-title { font-weight: 700; font-size: 15px; margin: 0; }
.select-compact { height: 32px; padding: 0 8px; min-width: 180px; max-width: 240px; font-size: 13px; }
.gen-count-group { display: flex; align-items: center; gap: 6px; }
.input-num { height: 32px; width: 56px; text-align: center; padding: 0 6px; font-size: 13px; }
.batch-progress-bar-wrap {
  padding: 8px 16px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.batch-progress-label {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.batch-progress-track { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
.batch-progress-fill  { height: 100%; background: var(--accent); border-radius: 2px; transition: width .3s; }
.full-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
}
.state-icon { font-size: 40px; }
.images-main {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}
.scene-list-panel {
  width: 260px;
  min-width: 200px;
  max-width: 300px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
}
.scene-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background .12s;
  min-height: 56px;
}
.scene-list-item:hover         { background: var(--bg-input); }
.scene-list-item.active        { background: rgba(99,179,237,.12); }
.scene-list-item.batch-current { background: rgba(251,191,36,.08); }
.scene-list-thumbs { display: flex; flex-direction: column; gap: 2px; flex-shrink: 0; }
.mini-thumb {
  width: 40px; height: 28px; border-radius: 3px; overflow: hidden;
  background: var(--bg-input); border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
}
.mini-thumb img { width: 100%; height: 100%; object-fit: cover; }
.mini-empty  { font-size: 9px; color: var(--text-muted); font-weight: 600; }
.mini-spinner { display: flex; align-items: center; justify-content: center; }
.spinner-xs  { width: 12px; height: 12px; border-width: 1.5px; }
.scene-list-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.scene-list-num  { font-size: 18px; font-weight: 800; color: var(--accent); line-height: 1; }
.scene-list-desc { font-size: 12px; color: var(--text); line-height: 1.3; }
.scene-list-status { font-size: 11px; }
.dot-active { color: #f6ad55; }
.dot-done   { color: #68d391; }
.scene-list-gen-btn {
  flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%;
  border: 1px solid var(--border); background: var(--bg-input);
  color: var(--text); font-size: 12px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .12s, color .12s;
}
.scene-list-gen-btn:hover:not(:disabled) { background: var(--accent); color: #fff; border-color: var(--accent); }
.scene-list-gen-btn:disabled { opacity: .4; cursor: not-allowed; }
.scene-detail-panel {
  flex: 1; overflow-y: auto; padding: 16px 20px;
  display: flex; flex-direction: column; gap: 16px; min-width: 0;
}
.scene-detail-panel.empty-detail {
  align-items: center; justify-content: center; color: var(--text-muted);
}
.detail-header {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; background: var(--bg-input);
  border-radius: 8px; flex-shrink: 0;
}
.detail-num  { font-size: 22px; font-weight: 800; color: var(--accent); min-width: 32px; }
.detail-desc { font-size: 14px; flex: 1; min-width: 0; }
.detail-frame-section {
  border: 1px solid var(--border); border-radius: 8px;
  overflow: hidden; flex-shrink: 0;
}
.detail-frame-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; background: var(--bg-input);
  border-bottom: 1px solid var(--border);
}
.frame-badge  { font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 600; flex-shrink: 0; }
.badge-blue   { background: rgba(99,179,237,.15); color: #63b3ed; }
.badge-purple { background: rgba(183,148,244,.15); color: #b794f4; }
.frame-prompt { font-size: 12px; flex: 1; min-width: 0; }
.image-slots { display: flex; gap: 12px; flex-wrap: wrap; padding: 12px; }
.image-slot {
  width: 192px; height: 128px; border-radius: 6px;
  border: 2px solid var(--border); overflow: hidden; cursor: pointer;
  position: relative; background: var(--bg-input);
  transition: border-color .15s, box-shadow .15s;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.image-slot:hover  { border-color: var(--accent); }
.image-slot.selected { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(99,179,237,.35); }
.image-slot.loading  { cursor: default; }
.image-slot.errored  { border-color: var(--danger, #fc8181); cursor: default; }
.image-slot img      { width: 100%; height: 100%; object-fit: cover; }
.slot-loading { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.slot-progress-text { font-size: 11px; color: var(--text-muted); }
.slot-error { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px; }
.slot-err-msg { font-size: 10px; color: var(--danger, #fc8181); text-align: center; word-break: break-word; }
.slot-empty   { font-size: 24px; color: var(--border); user-select: none; }
.selected-badge {
  position: absolute; top: 4px; right: 4px;
  background: var(--accent); color: #fff; border-radius: 50%;
  width: 18px; height: 18px; font-size: 11px;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
}
.slot-overlay {
  position: absolute; inset: 0; background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center; gap: 8px;
  opacity: 0; transition: opacity .15s; border-radius: 4px; pointer-events: none;
}
.image-slot:hover .slot-overlay { opacity: 1; pointer-events: auto; }
.slot-overlay-btn {
  background: rgba(255,255,255,.15); border: 1px solid rgba(255,255,255,.35);
  color: #fff; border-radius: 4px; width: 32px; height: 32px; font-size: 15px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background .1s;
}
.slot-overlay-btn:hover  { background: rgba(255,255,255,.3); }
.slot-overlay-del:hover  { background: rgba(229,62,62,.7); }
.slot-add {
  background: transparent; border: 2px dashed var(--border);
  color: var(--text-muted); font-size: 28px; cursor: pointer;
  transition: border-color .15s, color .15s; flex-shrink: 0;
}
.slot-add:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.slot-add:disabled { opacity: .4; cursor: not-allowed; }
.spinner-sm { width: 20px; height: 20px; border-width: 2px; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.btn-xs { padding: 2px 6px; font-size: 12px; height: 24px; line-height: 1; }
.btn-warning { background: #d97706; color: #fff; border-color: #d97706; }
.btn-warning:hover { opacity: .85; }
.lightbox-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.88); display: flex; align-items: center; justify-content: center;
}
.lightbox-close {
  position: absolute; top: 16px; right: 20px;
  background: rgba(255,255,255,.12); border: none; color: #fff;
  font-size: 20px; width: 36px; height: 36px; border-radius: 50%;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.lightbox-close:hover { background: rgba(255,255,255,.25); }
.lightbox-nav {
  background: rgba(255,255,255,.1); border: none; color: #fff;
  font-size: 44px; line-height: 1; width: 52px; height: 80px;
  border-radius: 6px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin: 0 12px; transition: background .15s;
}
.lightbox-nav:hover { background: rgba(255,255,255,.2); }
.lightbox-body {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  max-width: calc(100vw - 160px); max-height: calc(100vh - 80px);
}
.lightbox-img {
  max-width: 100%; max-height: calc(100vh - 120px);
  object-fit: contain; border-radius: 6px; display: block;
}
.lightbox-footer { color: rgba(255,255,255,.6); font-size: 13px; }
</style>
