<template>
  <div class="tab-panel audio-tab">

    <!-- ── Toolbar ── -->
    <div class="audio-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">音频生成</h3>
        <span class="text-muted" style="font-size:13px" v-if="isReadingMode">
          📖 朗读模式 · 微软神经语音 · {{ readingScenes.length }} 段
        </span>
        <span class="text-muted" style="font-size:13px" v-else-if="allClips.length">
          {{ allClips.length }} 个音频片段 · 每段 {{ genCount }} 个版本
        </span>
      </div>
      <div class="toolbar-right">
        <div class="gen-count-group" v-if="!isReadingMode">
          <label class="text-muted" style="font-size:12px;white-space:nowrap">版本数</label>
          <input class="input input-num" type="number" min="1" max="10" v-model.number="genCount" :disabled="running" />
        </div>
        <button class="btn btn-danger btn-sm" v-if="running" @click="stopBatch">⏹ 停止</button>
        <button class="btn btn-primary btn-sm" v-else :disabled="!canBatch" @click="runBatch">
          ▶ {{ isReadingMode ? '全部生成语音' : '批量生成' }}
        </button>
      </div>
    </div>

    <!-- ── States ── -->
    <div v-if="loadError" class="empty-state">
      <div class="empty-icon">⚠</div><p>{{ loadError }}</p>
      <button class="btn btn-secondary btn-sm" @click="loadData">重试</button>
    </div>
    <div v-else-if="loadingScenes" class="empty-state">
      <div class="spinner" /><p class="text-muted">加载分镜中…</p>
    </div>
    <div v-else-if="!allClips.length && !isReadingMode" class="empty-state">
      <div class="empty-icon">🎤</div>
      <p>请先在「分镜设计」添加台词并保存</p>
    </div>
    <div v-else-if="isReadingMode && !readingScenes.length" class="empty-state">
      <div class="empty-icon">📖</div>
      <p>朗读模式：请先在「分镜设计」完成分镜并保存</p>
    </div>

    <!-- ── Batch progress ── -->
    <div v-if="(running || batchDone) && (allClips.length || readingScenes.length)" class="batch-progress-bar-wrap">
      <div class="batch-progress-label">
        <span>批量生成进度</span>
        <span>{{ completedCount }} / {{ totalCount }}</span>
      </div>
      <div class="batch-progress-track">
        <div class="batch-progress-fill" :style="{ width: progressPct + '%' }" />
      </div>
    </div>

    <!-- ── Reading mode: voice controls ── -->
    <div v-if="isReadingMode && readingScenes.length" class="reading-controls">
      <div class="reading-ctrl-group">
        <label class="dlg-label">微软语音</label>
        <select v-model="msVoice" class="input select-compact ms-voice-select" :disabled="running">
          <option v-for="v in MS_VOICES" :key="v.value" :value="v.value">{{ v.label }}</option>
        </select>
      </div>
      <div class="reading-ctrl-group">
        <label class="dlg-label">语速</label>
        <select v-model="msRate" class="input select-compact" :disabled="running">
          <option value="-50%">很慢</option>
          <option value="-25%">慢</option>
          <option value="+0%">正常</option>
          <option value="+25%">快</option>
          <option value="+50%">很快</option>
        </select>
      </div>
    </div>

    <!-- ── Reading mode: scene audio list ── -->
    <div class="scenes-audio-list" v-if="isReadingMode && readingScenes.length">
      <div v-for="scene in readingScenes" :key="scene.sceneId" class="scene-audio-group card">
        <div class="scene-group-header">
          <span class="scene-num">{{ String(scene.sceneIndex).padStart(2,'0') }}</span>
          <span class="scene-group-title">{{ scene.description || `场景 ${scene.sceneIndex}` }}</span>
          <span class="text-muted" style="font-size:11px;margin-left:auto">
            {{ scene.duration_ms ? (scene.duration_ms / 1000).toFixed(1) + 's' : (scene.generating ? '生成中…' : '') }}
          </span>
          <button class="btn btn-ghost btn-xs regen-btn" :disabled="running" @click="generateMsTts(scene)">
            {{ scene.generating ? '生成中…' : '↺ 生成' }}
          </button>
        </div>
        <div class="reading-text">{{ scene.text.slice(0, 150) }}{{ scene.text.length > 150 ? '…' : '' }}</div>
        <div v-if="scene.generating" class="reading-generating text-muted">
          <span class="spinner" style="width:16px;height:16px;border-width:2px" /> 语音生成中…
        </div>
        <audio
          v-else-if="scene.data"
          :key="scene._rev"
          :src="'data:audio/mpeg;base64,' + scene.data"
          controls
          class="reading-player"
          @loadedmetadata="e => onReadingAudioLoaded(scene, e)"
        />
      </div>
    </div>

    <!-- ── Normal mode: scene groups ── -->
    <div class="scenes-audio-list" v-if="allClips.length && !isReadingMode">
      <div v-for="scene in scenesWithClips" :key="scene.sceneId" class="scene-audio-group card">

        <!-- Scene header -->
        <div class="scene-group-header">
          <span class="scene-num">{{ String(scene.sceneIndex).padStart(2,'0') }}</span>
          <span class="scene-group-title">{{ scene.description || `场景 ${scene.sceneIndex}` }}</span>
          <span class="badge badge-blue" style="margin-left:auto">{{ scene.clips.length }} 段</span>
          <button
            class="btn btn-secondary btn-xs"
            :disabled="running || scene.stitching || !sceneHasAllAudio(scene)"
            @click="stitchScene(scene)"
            :title="sceneHasAllAudio(scene) ? '合并本场景全部音频片段' : '请先生成本场景全部音频'"
          >
            {{ scene.stitching ? '合并中…' : '⛓ 合并' }}
          </button>
        </div>

        <!-- Merged audio preview -->
        <div v-if="scene.stitchedData" class="stitched-preview">
          <span class="dlg-label">合并音频</span>
          <audio
            :ref="el => setSceneAudioRef(scene.sceneId, el)"
            :src="'data:audio/wav;base64,' + scene.stitchedData"
            controls
            class="stitched-player"
          />
          <span class="text-muted" style="font-size:11px">{{ formatMs(scene.stitchedDurationMs) }}</span>
        </div>

        <!-- Clip cards -->
        <div v-for="clip in scene.clips" :key="clip.id" class="dialogue-card">

          <!-- Clip header row -->
          <div class="dlg-header">
            <span class="dlg-character">{{ clip.character }}</span>
            <span class="dlg-emotion badge badge-purple" v-if="clip.emotion">{{ clip.emotion }}</span>
            <div class="silence-group">
              <label class="dlg-label">前静音</label>
              <input class="input input-num-sm" type="number" min="0" max="5000" step="100"
                v-model.number="clip.pre_silence_ms" :disabled="running" />
              <span class="text-muted" style="font-size:11px">ms</span>
            </div>
            <div class="silence-group">
              <label class="dlg-label">后静音</label>
              <input class="input input-num-sm" type="number" min="0" max="5000" step="100"
                v-model.number="clip.post_silence_ms" :disabled="running" />
              <span class="text-muted" style="font-size:11px">ms</span>
            </div>
            <button class="btn btn-ghost btn-xs regen-btn" :disabled="running" @click="regenClip(clip)" title="重新生成">↺</button>
          </div>

          <!-- Dialogue text -->
          <div class="dlg-text">"{{ clip.text }}"</div>

          <!-- Voice settings -->
          <div class="dlg-settings">
            <div class="dlg-setting-group">
              <label class="dlg-label">音色参考</label>
              <select class="input select-compact" v-model="clip._voiceRef" :disabled="running">
                <option value="">— 默认 —</option>
                <option v-for="f in voiceRefs" :key="f" :value="f">{{ f }}</option>
              </select>
            </div>
            <div class="dlg-setting-group">
              <label class="dlg-label">情感控制</label>
              <select class="input select-compact" v-model="clip._emoMethod" :disabled="running">
                <option value="与音色参考音频相同">与音色参考相同</option>
                <option value="使用情感参考音频">使用情感参考音频</option>
              </select>
            </div>
            <div class="dlg-setting-group" v-if="clip._emoMethod === '使用情感参考音频'">
              <label class="dlg-label">情感参考</label>
              <select class="input select-compact" v-model="clip._emoRef" :disabled="running">
                <option value="">— 无 —</option>
                <option v-for="f in emoRefs" :key="f" :value="f">{{ f }}</option>
              </select>
            </div>
            <div class="dlg-setting-group">
              <label class="dlg-label">情感权重 {{ clip._emoWeight.toFixed(1) }}</label>
              <input type="range" min="0" max="1.6" step="0.1"
                v-model.number="clip._emoWeight" :disabled="running" class="slider-compact" />
            </div>
          </div>

          <!-- Audio slots -->
          <div class="slot-row">
            <div v-for="slot in clip.slots" :key="slot.index"
              class="slot-card"
              :class="{ 'slot-selected': slot.index === clip.selectedSlot, 'slot-generating': slot.generating }"
              @click="clip.selectedSlot = slot.index">
              <div class="slot-label">V{{ slot.index + 1 }}</div>
              <div v-if="slot.generating" class="slot-status text-muted">生成中…</div>
              <div v-else-if="slot.data" class="slot-status">
                <audio :ref="el => setAudioRef(clip.id, slot.index, el)"
                  :src="'data:audio/wav;base64,' + slot.data"
                  style="display:none" />
                <button class="btn btn-ghost btn-xs" @click.stop="playSlot(clip.id, slot.index)">▶</button>
                <span class="text-muted" style="font-size:11px">{{ slot.duration || '' }}</span>
              </div>
              <div v-else class="slot-status text-muted">—</div>
            </div>
          </div>

        </div><!-- end clip card -->
      </div><!-- end scene group -->
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({ projectId: String })
const emit  = defineEmits(['dirty', 'saved'])
// ── state ──────────────────────────────────────────────────────────────────
const MS_VOICES = [
  { value: 'zh-CN-XiaoxiaoNeural', label: '晓晓（女·亲切温柔）' },
  { value: 'zh-CN-XiaoyiNeural',   label: '晓伊（女·活泼下馆）' },
  { value: 'zh-CN-XiaohanNeural',  label: '晓涵（女·沉稳大气）' },
  { value: 'zh-CN-XiaomoNeural',   label: '晓墨（女·多情感）' },
  { value: 'zh-CN-XiaoruiNeural',  label: '晓瑞（女·温和柔和）' },
  { value: 'zh-CN-XiaoyanNeural',  label: '晓颜（女·专业主播）' },
  { value: 'zh-CN-YunxiNeural',    label: '云希（男·活泼）' },
  { value: 'zh-CN-YunyangNeural',  label: '云扬（男·新闻播报）' },
  { value: 'zh-CN-YunyeNeural',    label: '云野（男·悠闲）' },
  { value: 'zh-CN-YunjianNeural',  label: '云健（男·劲岁运动）' },
]

const loadingScenes = ref(false)
const loadError     = ref('')
const scenesWithClips = ref([])  // [{ sceneId, sceneIndex, description, clips: [...] }]
const voiceRefs     = ref([])
const emoRefs       = ref([])
const genCount      = ref(3)
const running       = ref(false)
const batchDone     = ref(false)
const completedCount = ref(0)
const totalCount     = ref(0)
const abortController = ref(null)
const audioRefs       = {}  // { "clipId:slotIndex": HTMLAudioElement }

// ── Reading mode state ───────────────────────────────────────────────────────────
const isReadingMode  = ref(false)
const readingScenes  = ref([])   // [{ sceneId, sceneIndex, description, text, generating, data, duration_ms }]
const msVoice        = ref('zh-CN-XiaoxiaoNeural')
const msRate         = ref('+0%')
let   _stopReading   = false

// ── derived ─────────────────────────────────────────────────────────────────
const allClips = computed(() => scenesWithClips.value.flatMap(s => s.clips))
const canBatch = computed(() =>
  isReadingMode.value ? readingScenes.value.length > 0 : allClips.value.length > 0
)
const progressPct = computed(() =>
  totalCount.value > 0 ? Math.round((completedCount.value / totalCount.value) * 100) : 0
)

// ── audio element refs ────────────────────────────────────────────────────────
function setAudioRef(clipId, slotIndex, el) {
  if (el) audioRefs[`${clipId}:${slotIndex}`] = el
}
function playSlot(clipId, slotIndex) {
  const el = audioRefs[`${clipId}:${slotIndex}`]
  if (el) { el.currentTime = 0; el.play() }
}

// ── load ─────────────────────────────────────────────────────────────────────
async function loadData() {
  if (!props.projectId) return
  loadingScenes.value = true
  loadError.value = ''
  try {
    // Detect reading mode from manuscript config
    try {
      const cr = await fetch(`http://localhost:18520/api/projects/${props.projectId}/manuscript`)
      if (cr.ok) {
        const cd = await cr.json()
        isReadingMode.value = (cd.config?.dialogue_mode === 'reading')
      }
    } catch { /* ignore */ }

    // Load scenes
    const r = await fetch(`http://localhost:18520/api/projects/${props.projectId}/scenes`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const scenesData = await r.json()
    const scenes = scenesData.scenes || scenesData || []

    // Load existing audio
    let savedAudio = {}
    try {
      const ar = await fetch(`http://localhost:18520/api/projects/${props.projectId}/audio`)
      if (ar.ok) savedAudio = await ar.json()
    } catch { /* ignore */ }

    // Load settings for defaults
    try {
      const sr = await fetch('http://localhost:18520/api/settings')
      if (sr.ok) {
        const s = await sr.json()
        genCount.value = s.audio_engine?.default_gen_count ?? 3
      }
    } catch { /* ignore */ }

    // Load ref file lists
    try {
      const [vr, er] = await Promise.all([
        fetch('http://localhost:18520/api/audio-engine/voice-refs').then(r => r.ok ? r.json() : []),
        fetch('http://localhost:18520/api/audio-engine/emotion-refs').then(r => r.ok ? r.json() : []),
      ])
      voiceRefs.value = vr
      emoRefs.value = er
    } catch { /* ignore */ }

    // Build scenesWithClips
    const result = []
    if (isReadingMode.value) {
      // ── Reading mode: one MS TTS clip per scene ───────────────────────────
      readingScenes.value = scenes
        .filter(s => (s.dialogues || [])[0]?.text)
        .map(s => {
          const key   = `__ms_reading__${s.id || s.index}`
          const saved = savedAudio[key] || {}
          return {
            sceneId:     s.id || s.index,
            sceneIndex:  s.index,
            description: s.description,
            text:        s.dialogues[0].text,
            generating:  false,
            data:        saved.data        || null,
            duration_ms: saved.duration_ms || 0,
            _rev:        0,   // bump on each (re)generate to force <audio> re-render
          }
        })
    } else {
      // ── Normal mode: IndexTTS / GPT-SoVITS ───────────────────────────────
      // Load settings for defaults
      try {
        const sr = await fetch('http://localhost:18520/api/settings')
        if (sr.ok) {
          const s = await sr.json()
          genCount.value = s.audio_engine?.default_gen_count ?? 3
        }
      } catch { /* ignore */ }

      // Load ref file lists
      try {
        const [vr, er] = await Promise.all([
          fetch('http://localhost:18520/api/audio-engine/voice-refs').then(r => r.ok ? r.json() : []),
          fetch('http://localhost:18520/api/audio-engine/emotion-refs').then(r => r.ok ? r.json() : []),
        ])
        voiceRefs.value = vr
        emoRefs.value = er
      } catch { /* ignore */ }

      for (const scene of scenes) {
        const rawClips = scene.audio_clips || scene_dialogues_to_clips(scene)
        if (!rawClips.length) continue
        const clips = rawClips.map((ac, idx) => {
          const clipId = `${scene.id || scene.index}:${idx}`
          const saved  = savedAudio[clipId] || {}
          return {
            id:             clipId,
            sceneId:        scene.id || scene.index,
            character:      ac.character || '',
            emotion:        ac.emotion   || '',
            text:           ac.text      || '',
            pre_silence_ms:  ac.pre_silence_ms  ?? 500,
            post_silence_ms: ac.post_silence_ms ?? 1000,
            _voiceRef:  saved.voiceRef  || '',
            _emoRef:    saved.emoRef    || '',
            _emoMethod: saved.emoMethod || '与音色参考音频相同',
            _emoWeight: saved.emoWeight ?? 0.8,
            selectedSlot: saved.selectedSlot ?? 0,
            slots: Array.from({ length: genCount.value }, (_, i) => ({
              index:      i,
              data:       saved.slots?.[i]?.data || null,
              duration:   saved.slots?.[i]?.duration || '',
              generating: false,
            })),
          }
        })
        result.push({
          sceneId: scene.id || scene.index,
          sceneIndex: scene.index,
          description: scene.description,
          clips,
          stitching: false,
          stitchedData: savedAudio[`__stitched__${scene.id || scene.index}`]?.data || null,
          stitchedDurationMs: savedAudio[`__stitched__${scene.id || scene.index}`]?.duration_ms || 0,
        })
      }
      scenesWithClips.value = result
    }
  } catch (e) {
    loadError.value = e.message
  } finally {
    loadingScenes.value = false
  }
}

function scene_dialogues_to_clips(scene) {
  return (scene.dialogues || []).map(d => ({
    character:       d.character || '',
    emotion:         d.emotion   || '',
    text:            d.text      || '',
    pre_silence_ms:  500,
    post_silence_ms: 1000,
  }))
}

// ── save ─────────────────────────────────────────────────────────────────────
async function saveAudio() {
  if (!props.projectId) return
  const payload = {}
  if (isReadingMode.value) {
    for (const scene of readingScenes.value) {
      if (scene.data) {
        payload[`__ms_reading__${scene.sceneId}`] = {
          data:        scene.data,
          duration_ms: scene.duration_ms,
        }
      }
    }
  } else {
    for (const clip of allClips.value) {
      payload[clip.id] = {
        voiceRef:     clip._voiceRef,
        emoRef:       clip._emoRef,
        emoMethod:    clip._emoMethod,
        emoWeight:    clip._emoWeight,
        selectedSlot: clip.selectedSlot,
        slots: clip.slots.map(s => ({ data: s.data, duration: s.duration })),
      }
    }
    for (const scene of scenesWithClips.value) {
      if (scene.stitchedData) {
        payload[`__stitched__${scene.sceneId}`] = {
          data: scene.stitchedData,
          duration_ms: scene.stitchedDurationMs,
        }
      }
    }
  }
  await fetch(
    `http://localhost:18520/api/projects/${props.projectId}/audio`,
    { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }
  )
  emit('saved')
}

// ── generate ─────────────────────────────────────────────────────────────────
async function runBatch() {
  if (running.value || !canBatch.value) return
  if (isReadingMode.value) { await generateAllMsTts(); return }
  running.value  = true
  batchDone.value = false
  completedCount.value = 0
  totalCount.value = allClips.value.length * genCount.value
  abortController.value = new AbortController()

  const payload = {
    gen_count: genCount.value,
    dialogues: allClips.value.map(c => ({
      scene_id:    String(c.sceneId),
      dialogue_id: c.id,
      text:        c.text,
      voice_ref:   c._voiceRef || null,
      emo_ref:     c._emoRef   || null,
      emo_weight:  c._emoWeight,
      lang:        'zh',
    })),
  }

  // Reset slot states
  for (const clip of allClips.value) {
    clip.slots = Array.from({ length: genCount.value }, (_, i) => ({
      index: i, data: null, duration: '', generating: true,
    }))
  }

  try {
    const resp = await fetch('http://localhost:18520/api/audio-engine/generate-batch-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: abortController.value.signal,
    })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (raw === '[DONE]') break
        try { handleEvent(JSON.parse(raw)) } catch { /* ignore */ }
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') loadError.value = e.message
  } finally {
    running.value = false
    batchDone.value = true
    // clear generating states
    for (const clip of allClips.value)
      for (const slot of clip.slots) slot.generating = false
    await saveAudio()
  }
}

function handleEvent(ev) {
  if (ev.event === 'batch_done') return
  const clip = allClips.value.find(c => c.id === ev.dialogue_id)
  if (!clip) return
  const slot = clip.slots[ev.slot_index]
  if (!slot) return
  if (ev.event === 'completed') {
    slot.data = ev.data
    slot.generating = false
    completedCount.value++
    emit('dirty')
  } else if (ev.event === 'error') {
    slot.generating = false
    completedCount.value++
  }
}

async function regenClip(clip) {
  if (running.value) return
  running.value = true
  for (const slot of clip.slots) slot.generating = true

  const payload = {
    gen_count: genCount.value,
    dialogues: [{
      scene_id:    String(clip.sceneId),
      dialogue_id: clip.id,
      text:        clip.text,
      voice_ref:   clip._voiceRef || null,
      emo_ref:     clip._emoRef   || null,
      emo_weight:  clip._emoWeight,
      lang:        'zh',
    }],
  }
  try {
    const resp = await fetch('http://localhost:18520/api/audio-engine/generate-batch-stream', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (raw === '[DONE]') break
        try { handleEvent(JSON.parse(raw)) } catch {}
      }
    }
  } finally {
    running.value = false
    for (const slot of clip.slots) slot.generating = false
    await saveAudio()
  }
}

function stopBatch() {
  _stopReading = true
  abortController.value?.abort()
  running.value = false
}

// ── Microsoft Edge TTS ───────────────────────────────────────────────────────────
async function generateMsTts(scene) {
  scene.generating = true
  scene.data = null      // clear old audio so the player disappears immediately
  scene._rev = (scene._rev || 0) + 1
  try {
    const res = await fetch('http://localhost:18520/api/audio-engine/ms-tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: scene.text, voice: msVoice.value, rate: msRate.value }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
    const result = await res.json()
    scene.data        = result.data
    scene._rev        = (scene._rev || 0) + 1   // bump again so :key changes
    scene.duration_ms = result.duration_ms       // will be updated from metadata below
    emit('dirty')
    await saveAudio()
  } catch (e) {
    console.error('MS TTS failed:', e)
  } finally {
    scene.generating = false
  }
}

function onReadingAudioLoaded(scene, e) {
  const dur = e.target.duration
  if (dur && isFinite(dur)) {
    scene.duration_ms = Math.round(dur * 1000)
  }
}

async function generateAllMsTts() {
  running.value        = true
  batchDone.value      = false
  completedCount.value = 0
  totalCount.value     = readingScenes.value.length
  _stopReading         = false
  for (const scene of readingScenes.value) {
    if (_stopReading) break
    await generateMsTts(scene)
    completedCount.value++
  }
  running.value   = false
  batchDone.value = true
}

// ── stitch ───────────────────────────────────────────────────────────────────
const sceneAudioRefs = {}

function setSceneAudioRef(sceneId, el) {
  if (el) sceneAudioRefs[sceneId] = el
}

function sceneHasAllAudio(scene) {
  return scene.clips.length > 0 && scene.clips.every(c => {
    const slot = c.slots[c.selectedSlot]
    return slot && slot.data
  })
}

function formatMs(ms) {
  if (!ms) return ''
  const s = (ms / 1000).toFixed(1)
  return `${s}s`
}

async function stitchScene(scene) {
  if (scene.stitching) return
  scene.stitching = true
  try {
    const clips = scene.clips.map(c => ({
      data:            c.slots[c.selectedSlot]?.data || '',
      pre_silence_ms:  c.pre_silence_ms,
      post_silence_ms: c.post_silence_ms,
    })).filter(c => c.data)

    const res = await fetch('http://localhost:18520/api/audio-engine/stitch-scene', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clips }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const result = await res.json()
    scene.stitchedData = result.data
    scene.stitchedDurationMs = result.duration_ms
    emit('dirty')
    await saveAudio()
  } catch (e) {
    console.error('stitch failed', e)
  } finally {
    scene.stitching = false
  }
}

// ── lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadData()
  window.addEventListener('lumi:save-project', saveAudio)
})
onUnmounted(() => {
  window.removeEventListener('lumi:save-project', saveAudio)
})
</script>

<style scoped>
/* ── Reading mode ── */
.reading-controls {
  display:flex; flex-wrap:wrap; align-items:center; gap:14px;
  padding:8px 16px; flex-shrink:0;
  border-bottom:1px solid var(--border-color);
  background:var(--bg-secondary);
}
.reading-ctrl-group { display:flex; align-items:center; gap:6px; }
.ms-voice-select    { min-width:180px; }
.reading-text {
  font-size:13px; color:var(--text-secondary); line-height:1.6;
  padding:6px 2px; border-top:1px dashed var(--border-color); margin-top:2px;
}
.reading-player    { height:36px; width:100%; margin-top:6px; }
.reading-generating { display:flex; align-items:center; gap:8px; padding:6px 2px; font-size:12px; }

.audio-tab { display:flex; flex-direction:column; height:100%; overflow:hidden; }
.audio-toolbar {
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 16px 8px; gap:12px; flex-shrink:0;
}
.toolbar-left  { display:flex; align-items:center; gap:12px; }
.toolbar-right { display:flex; align-items:center; gap:8px; }
.toolbar-title { margin:0; font-size:15px; font-weight:600; }
.gen-count-group { display:flex; align-items:center; gap:6px; }
.input-num { width:56px; text-align:center; }
.input-num-sm { width:60px; text-align:center; padding:2px 4px; font-size:12px; }

.batch-progress-bar-wrap {
  padding:0 16px 8px; flex-shrink:0;
}
.batch-progress-label { display:flex; justify-content:space-between; font-size:12px; color:var(--text-muted); margin-bottom:4px; }
.batch-progress-track { height:6px; border-radius:4px; background:var(--bg-tertiary); overflow:hidden; }
.batch-progress-fill  { height:100%; background:var(--accent); transition:width .3s; }

.scenes-audio-list {
  flex:1; overflow-y:auto; padding:0 16px 16px; display:flex; flex-direction:column; gap:12px;
}
.scene-audio-group {
  flex-shrink:0; padding:12px; display:flex; flex-direction:column; gap:8px;
}
.scene-group-header {
  display:flex; align-items:center; gap:8px; padding-bottom:8px;
  border-bottom:1px solid var(--border-color);
}
.scene-group-title { font-weight:500; font-size:13px; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

.stitched-preview {
  display:flex; align-items:center; gap:8px; padding:6px 4px 2px;
  border-top:1px dashed var(--border-color); margin-top:2px;
}
.stitched-player { height:32px; flex:1; min-width:0; }

.dialogue-card {
  flex-shrink:0; border:1px solid var(--border-color); border-radius:8px;
  padding:10px 12px; display:flex; flex-direction:column; gap:6px;
  background:var(--bg-secondary);
}
.dlg-header  { display:flex; align-items:center; flex-wrap:wrap; gap:6px; }
.dlg-character { font-weight:600; font-size:13px; }
.dlg-emotion   { font-size:11px; }
.dlg-text      { font-size:13px; color:var(--text-secondary); font-style:italic; }
.regen-btn     { margin-left:auto; }

.silence-group { display:flex; align-items:center; gap:4px; }
.dlg-label  { font-size:11px; color:var(--text-muted); white-space:nowrap; }

.dlg-settings { display:flex; flex-wrap:wrap; gap:8px; }
.dlg-setting-group { display:flex; align-items:center; gap:6px; }
.select-compact { min-width:120px; max-width:200px; font-size:12px; padding:3px 6px; }
.slider-compact { width:100px; }

.slot-row { display:flex; gap:6px; flex-wrap:wrap; }
.slot-card {
  border:1px solid var(--border-color); border-radius:6px;
  padding:4px 10px; cursor:pointer; min-width:70px;
  display:flex; align-items:center; gap:6px;
  transition:border-color .15s, background .15s;
  background:var(--bg-primary);
}
.slot-card:hover  { border-color:var(--accent); }
.slot-selected    { border-color:var(--accent); background:color-mix(in srgb, var(--accent) 12%, transparent); }
.slot-generating  { opacity:.7; }
.slot-label  { font-size:11px; font-weight:600; color:var(--text-muted); }
.slot-status { font-size:12px; display:flex; align-items:center; gap:4px; }
.scene-num { font-size:11px; font-weight:700; background:var(--accent); color:#fff; border-radius:4px; padding:1px 6px; }

.empty-state {
  flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; opacity:.7;
}
.empty-icon { font-size:40px; }
.spinner { width:24px; height:24px; border:2px solid var(--border-color); border-top-color:var(--accent); border-radius:50%; animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
</style>
