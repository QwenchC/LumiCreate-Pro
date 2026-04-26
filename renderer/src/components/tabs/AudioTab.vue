<template>
  <div class="tab-panel audio-tab">

    <!-- ── Toolbar ── -->
    <div class="audio-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">音频生成</h3>
        <span class="text-muted" style="font-size:13px" v-if="dialogues.length">
          {{ dialogues.length }} 条台词 · 每条 {{ genCount }} 个版本
        </span>
      </div>
      <div class="toolbar-right">
        <div class="gen-count-group">
          <label class="text-muted" style="font-size:12px;white-space:nowrap">版本数</label>
          <input class="input input-num" type="number" min="1" max="10" v-model.number="genCount" :disabled="running" />
        </div>
        <button class="btn btn-danger btn-sm" v-if="running" @click="stopBatch">⏹ 停止</button>
        <button class="btn btn-primary btn-sm" v-else :disabled="!dialogues.length" @click="runBatch">
          ▶ 批量生成
        </button>
      </div>
    </div>

    <!-- ── States ── -->
    <div v-if="loadError" class="empty-state">
      <div class="empty-icon">⚠</div>
      <p>{{ loadError }}</p>
      <button class="btn btn-secondary btn-sm" @click="loadData">重试</button>
    </div>

    <div v-else-if="loadingScenes" class="empty-state">
      <div class="spinner" /><p class="text-muted">加载分镜中…</p>
    </div>

    <div v-else-if="!dialogues.length" class="empty-state">
      <div class="empty-icon">🎞</div>
      <p>请先在「分镜设计」添加台词并保存</p>
    </div>

    <!-- ── Batch progress ── -->
    <div v-if="(running || batchDone) && dialogues.length" class="batch-progress-bar-wrap">
      <div class="batch-progress-label">
        <span>批量生成进度</span>
        <span>{{ completedCount }} / {{ totalCount }}</span>
      </div>
      <div class="batch-progress-track">
        <div class="batch-progress-fill" :style="{ width: progressPct + '%' }" />
      </div>
    </div>

    <!-- ── Dialogue list ── -->
    <div class="dialogue-list" v-if="dialogues.length">
      <div v-for="item in dialogues" :key="item.id" class="dialogue-card card">

        <!-- Card header -->
        <div class="dlg-header">
          <span class="scene-num">{{ String(item.sceneIndex).padStart(2, '0') }}</span>
          <span class="dlg-character">{{ item.character }}</span>
          <span class="dlg-emotion badge badge-blue" v-if="item.emotion">{{ item.emotion }}</span>
          <button
            class="btn btn-ghost btn-xs regen-btn"
            :disabled="running"
            @click="regenDialogue(item)"
            title="重新生成全部版本"
          >↺</button>
        </div>

        <!-- Dialogue text -->
        <div class="dlg-text">"{{ item.text }}"</div>

        <!-- TTS settings row -->
        <div class="dlg-settings">
          <div class="dlg-setting-group">
            <label class="dlg-label">声音</label>
            <select class="input select-compact" v-model="item._speaker" :disabled="running">
              <option value="">— 默认 —</option>
              <option v-for="m in voiceModels" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>
          <div class="dlg-setting-group">
            <label class="dlg-label">速度</label>
            <input class="input input-num" type="number" min="0.5" max="2.0" step="0.1"
              v-model.number="item._speed" :disabled="running" style="width:64px" />
          </div>
          <div class="dlg-setting-group" style="flex:1">
            <label class="dlg-label">参考音频路径</label>
            <input class="input" type="text" placeholder="（可选）ref_audio.wav"
              v-model="item._refAudio" :disabled="running" />
          </div>
        </div>

        <!-- Audio version slots -->
        <div class="audio-slots">
          <div
            v-for="slot in genCount"
            :key="slot - 1"
            class="audio-slot"
            :class="{
              selected:  item._selected === slot - 1,
              loading:   isLoading(item.id, slot - 1),
              errored:   isErrored(item.id, slot - 1),
            }"
          >
            <!-- Loading -->
            <div v-if="isLoading(item.id, slot - 1)" class="slot-inner slot-loading-state">
              <div class="spinner spinner-sm" />
              <span class="text-muted" style="font-size:11px">生成中…</span>
            </div>

            <!-- Error -->
            <div v-else-if="isErrored(item.id, slot - 1)" class="slot-inner slot-err-state">
              <span style="font-size:18px">⚠</span>
              <span class="text-muted" style="font-size:10px;word-break:break-all">{{ getError(item.id, slot - 1) }}</span>
            </div>

            <!-- Audio ready -->
            <div v-else-if="getAudio(item.id, slot - 1)" class="slot-inner slot-ready-state">
              <span class="slot-num">V{{ slot }}</span>
              <button class="btn btn-ghost btn-xs play-btn" @click="playAudio(item.id, slot - 1)" title="播放">
                {{ isPlaying(item.id, slot - 1) ? '⏸' : '▶' }}
              </button>
              <span class="slot-select-btn" @click="selectSlot(item, slot - 1)">
                {{ item._selected === slot - 1 ? '✓ 使用中' : '选用' }}
              </span>
            </div>

            <!-- Empty -->
            <div v-else class="slot-inner slot-empty-state">
              <span class="text-muted">V{{ slot }}</span>
            </div>
          </div>
        </div>

      </div><!-- /dialogue-card -->
    </div><!-- /dialogue-list -->

    <!-- Hidden audio element for playback -->
    <audio ref="audioEl" style="display:none" @ended="onAudioEnded" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps({ projectId: String })
const emit = defineEmits(['dirty', 'saved'])

const API = 'http://localhost:18520/api'

// ── State ──────────────────────────────────────────────────────────────────────
const scenes        = ref([])
const dialogues     = ref([])   // flat list: {id, sceneIndex, character, emotion, text, _speaker, _speed, _refAudio, _selected}
const loadingScenes = ref(false)
const loadError     = ref('')
const voiceModels   = ref([])
const genCount      = ref(3)
const running       = ref(false)
const batchDone     = ref(false)
const stopFlag      = ref(false)

// Slot state maps
const slotAudio   = ref({})   // key → base64 wav string
const slotLoading = ref({})
const slotError   = ref({})

// Playback
const audioEl       = ref(null)
const playingKey    = ref(null)

// ── Helpers ────────────────────────────────────────────────────────────────────
function slotKey(dlgId, slot) { return `${dlgId}:${slot}` }
function getAudio(dlgId, slot)  { return slotAudio.value[slotKey(dlgId, slot)] || null }
function isLoading(dlgId, slot) { return !!slotLoading.value[slotKey(dlgId, slot)] }
function isErrored(dlgId, slot) { return !!slotError.value[slotKey(dlgId, slot)] }
function getError(dlgId, slot)  { return slotError.value[slotKey(dlgId, slot)] || '' }
function isPlaying(dlgId, slot) { return playingKey.value === slotKey(dlgId, slot) }

const totalCount = computed(() => dialogues.value.length * genCount.value)
const completedCount = computed(() =>
  Object.values(slotAudio.value).filter(Boolean).length +
  Object.values(slotError.value).filter(Boolean).length
)
const progressPct = computed(() =>
  totalCount.value ? Math.round((completedCount.value / totalCount.value) * 100) : 0
)

// ── Load data ──────────────────────────────────────────────────────────────────
async function loadData() {
  loadError.value   = ''
  loadingScenes.value = true
  try {
    const [scenesRes, settingsRes, modelsRes] = await Promise.all([
      axios.get(`${API}/projects/${props.projectId}/scenes`),
      axios.get(`${API}/settings`),
      axios.get(`${API}/audio-engine/voice-models`).catch(() => ({ data: [] }))
    ])
    const rawScenes = scenesRes.data?.scenes || []
    const audioCfg  = settingsRes.data?.audio_engine || {}
    genCount.value  = audioCfg.default_gen_count ?? 3
    voiceModels.value = modelsRes.data || []

    // Flatten all dialogues from all scenes
    const flat = []
    for (const scene of rawScenes) {
      for (const dlg of (scene.dialogues || [])) {
        flat.push({
          id:         `${scene.id}:${dlg.id ?? dlg.character + flat.length}`,
          sceneId:    scene.id,
          sceneIndex: scene.index,
          character:  dlg.character || '',
          emotion:    dlg.emotion   || '',
          text:       dlg.text      || '',
          _speaker:   '',
          _speed:     1.0,
          _refAudio:  '',
          _selected:  dlg._selected_audio ?? 0,
        })
      }
    }
    dialogues.value = flat
    scenes.value    = rawScenes
  } catch (e) {
    loadError.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loadingScenes.value = false
  }
}

onMounted(loadData)

// ── Audio playback ─────────────────────────────────────────────────────────────
function playAudio(dlgId, slot) {
  const key  = slotKey(dlgId, slot)
  const data = slotAudio.value[key]
  if (!data) return
  if (playingKey.value === key) {
    audioEl.value.pause()
    playingKey.value = null
    return
  }
  audioEl.value.src = `data:audio/wav;base64,${data}`
  audioEl.value.play()
  playingKey.value = key
}
function onAudioEnded() { playingKey.value = null }

function selectSlot(item, slot) {
  item._selected = slot
  emit('dirty')
}

// ── Batch SSE generation ───────────────────────────────────────────────────────
let currentReader = null

async function runBatch() {
  running.value  = true
  batchDone.value = false
  stopFlag.value  = false

  slotAudio.value   = {}
  slotError.value   = {}
  slotLoading.value = {}
  for (const dlg of dialogues.value) {
    for (let s = 0; s < genCount.value; s++) {
      slotLoading.value[slotKey(dlg.id, s)] = true
    }
  }

  try {
    const response = await fetch(`${API}/audio-engine/generate-batch-stream`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gen_count: genCount.value,
        dialogues: dialogues.value.map(d => ({
          scene_id:    d.sceneId,
          dialogue_id: d.id,
          text:        d.text,
          lang:        'zh',
          speaker:     d._speaker || null,
          ref_audio_path: d._refAudio || null,
        }))
      })
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
        if (raw === '[DONE]') { batchDone.value = true; break }
        try { handleEvent(JSON.parse(raw)) } catch {}
      }
    }
  } catch (e) {
    if (!stopFlag.value) loadError.value = `生成失败: ${e.message}`
  } finally {
    running.value   = false
    currentReader   = null
    emit('dirty')
  }
}

function handleEvent(evt) {
  const { event, dialogue_id, slot_index } = evt
  if (!dialogue_id) return
  const key = slotKey(dialogue_id, slot_index)
  if (event === 'completed') {
    slotLoading.value[key] = false
    slotAudio.value[key]   = evt.data
  } else if (event === 'error') {
    slotLoading.value[key] = false
    slotError.value[key]   = evt.message || '错误'
  }
}

function stopBatch() {
  stopFlag.value = true
  currentReader?.cancel()
  running.value = false
}

// ── Single dialogue regeneration ───────────────────────────────────────────────
async function regenDialogue(item) {
  if (!item.text) return
  for (let s = 0; s < genCount.value; s++) {
    const key = slotKey(item.id, s)
    slotLoading.value[key] = true
    slotAudio.value[key]   = undefined
    slotError.value[key]   = ''
  }
  const promises = Array.from({ length: genCount.value }, (_, s) => runSingleSlot(item, s))
  await Promise.allSettled(promises)
  emit('dirty')
}

async function runSingleSlot(item, slotIndex) {
  const key = slotKey(item.id, slotIndex)
  try {
    const response = await fetch(`${API}/audio-engine/generate-stream`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text:          item.text,
        lang:          'zh',
        speaker:       item._speaker || null,
        ref_audio_path: item._refAudio || null,
        speed:         item._speed,
        scene_id:      item.sceneId,
        dialogue_id:   item.id,
        slot_index:    slotIndex
      })
    })
    const reader  = response.body.getReader()
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
        try { handleEvent(JSON.parse(raw)) } catch {}
      }
    }
  } catch (e) {
    slotError.value[key]   = e.message
    slotLoading.value[key] = false
  }
}
</script>

<style scoped>
/* ── Layout ── */
.audio-tab {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Toolbar ── */
.audio-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 10px;
}
.toolbar-left  { display: flex; align-items: center; gap: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.toolbar-title { font-weight: 700; font-size: 15px; margin: 0; }
.gen-count-group { display: flex; align-items: center; gap: 6px; }
.input-num  { height: 32px; width: 56px; text-align: center; padding: 0 6px; font-size: 13px; }

/* ── Batch progress ── */
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
.batch-progress-fill  { height: 100%; background: var(--accent); border-radius: 2px; transition: width .3s ease; }

/* ── Empty/error states ── */
.empty-state {
  flex: 1;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 10px; color: var(--text-muted);
}
.empty-icon { font-size: 48px; }

/* ── Dialogue list ── */
.dialogue-list {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex; flex-direction: column; gap: 12px;
}

/* ── Dialogue card ── */
.dialogue-card { padding: 0; overflow: hidden; flex-shrink: 0; }

.dlg-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px 8px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-input);
}
.scene-num      { font-size: 16px; font-weight: 800; color: var(--accent); min-width: 26px; }
.dlg-character  { font-size: 14px; font-weight: 600; }
.dlg-emotion    { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.badge-blue { background: rgba(99,179,237,.15); color: #63b3ed; }
.regen-btn { margin-left: auto; }

.dlg-text {
  padding: 10px 14px;
  font-size: 14px;
  color: var(--text);
  line-height: 1.5;
  border-bottom: 1px solid var(--border);
}

.dlg-settings {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.dlg-setting-group { display: flex; align-items: center; gap: 6px; }
.dlg-label { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.select-compact { height: 28px; padding: 0 6px; font-size: 12px; min-width: 140px; }

/* ── Audio slots ── */
.audio-slots {
  display: flex; gap: 8px; flex-wrap: wrap;
  padding: 10px 14px 12px;
}
.audio-slot {
  width: 120px;
  height: 72px;
  border-radius: 8px;
  border: 2px solid var(--border);
  background: var(--bg-input);
  overflow: hidden;
  position: relative;
  transition: border-color .15s;
}
.audio-slot.selected  { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(99,179,237,.3); }
.audio-slot.errored   { border-color: var(--danger, #fc8181); }

.slot-inner {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 4px; padding: 4px;
}
.slot-loading-state { gap: 6px; }
.slot-ready-state   { gap: 4px; }
.slot-empty-state   { opacity: .5; }
.slot-err-state     { gap: 2px; }

.slot-num { font-size: 11px; font-weight: 700; color: var(--text-muted); }
.play-btn { font-size: 16px; padding: 0; height: 28px; width: 28px; }
.slot-select-btn {
  font-size: 10px; cursor: pointer;
  color: var(--accent);
  padding: 2px 6px; border-radius: 4px;
  border: 1px solid var(--accent);
  user-select: none;
}
.slot-select-btn:hover { background: rgba(99,179,237,.15); }

/* ── Spinner ── */
.spinner-sm { width: 20px; height: 20px; border-width: 2px; }
.btn-danger { background: var(--danger,#e53e3e); color:#fff; border-color:var(--danger,#e53e3e); }
.btn-danger:hover { opacity:.85; }
.btn-xs { padding: 2px 6px; font-size: 12px; height: 24px; line-height: 1; }
</style>
