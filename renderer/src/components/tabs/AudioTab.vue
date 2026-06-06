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
          {{ allClips.length }} 个音频片段 · 引擎: {{ engineLabel }} · 每段 {{ genCount }} 个版本
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

    <!-- A1: 上次失败镜次提示 + 一键重试 -->
    <div v-if="lastErrorCount && !running" class="last-errors-banner">
      <span>⚠ 上次失败：{{ lastErrorCount }} 个片段（{{ lastErrorStage === 'audio' ? '音频' : lastErrorStage }}）</span>
      <button class="btn btn-warning btn-xs" @click="retryFailedBatch">↻ 只重试失败片段</button>
      <button class="btn btn-ghost btn-xs" @click="dismissLastErrors">✕ 忽略</button>
      <details class="last-errors-detail">
        <summary class="text-muted" style="font-size:11px;cursor:pointer">查看详情</summary>
        <ul>
          <li v-for="(msg, k) in lastErrors" :key="k"><code>{{ k }}</code>: {{ msg }}</li>
        </ul>
      </details>
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
        <label class="dlg-label">叙述音色</label>
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
      <!-- 双音色模式：对话/心理活动单独音色 -->
      <div class="reading-ctrl-group" title="打开后：引号「」“”‘’里的对话/心理活动优先按角色 voice 取音色（在「角色管理」里给每个角色配男/女声），未识别到说话人时用下方的「对话音色」作为默认；其余叙述用上面的「叙述音色」">
        <label class="dlg-label" style="display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" v-model="dualVoiceEnabled" :disabled="running" />
          区分音色
        </label>
      </div>
      <div class="reading-ctrl-group" v-if="dualVoiceEnabled">
        <label class="dlg-label">对话音色（fallback）</label>
        <select v-model="msDialogueVoice" class="input select-compact ms-voice-select" :disabled="running">
          <option v-for="v in MS_VOICES" :key="v.value" :value="v.value">{{ v.label }}</option>
        </select>
        <span class="text-muted" style="font-size:11px;margin-left:8px">
          ⓘ 未识别到说话人时使用
        </span>
      </div>
    </div>

    <!-- ── Reading mode: per-character voice matrix（双音色才显示） ── -->
    <!-- 真正的"按性别区分"靠这里：每个角色一个音色下拉 + 试听 -->
    <div v-if="isReadingMode && readingScenes.length && dualVoiceEnabled"
         class="char-voice-matrix card"
         style="margin:8px 12px;padding:10px 12px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <strong style="font-size:13px">👥 角色音色（男女区分核心）</strong>
        <span class="text-muted" style="font-size:11px">
          每个角色单独配音色 → 男声 / 女声 / 童声分明。改完保存到角色管理。
        </span>
        <button class="btn btn-ghost btn-xs" @click="reloadCharacters" style="margin-left:auto">↻ 刷新</button>
        <button class="btn btn-secondary btn-xs" :disabled="charsSaving" @click="saveCharVoices">
          {{ charsSaving ? '保存中…' : '💾 保存' }}
        </button>
      </div>
      <div v-if="!projectCharacters.length" class="text-muted" style="font-size:12px">
        当前项目没有角色 — 先去「角色管理」添加角色再回来
      </div>
      <div v-else class="char-voice-rows">
        <div v-for="(c, i) in projectCharacters" :key="c.name + i" class="char-voice-row">
          <span class="char-voice-name">
            {{ c.name }}
            <span v-if="c.role" class="text-muted" style="font-size:11px">（{{ c.role }}）</span>
          </span>
          <select v-model="c.voice" class="input select-compact ms-voice-select" :disabled="running"
                  @change="onCharVoiceChanged(c)">
            <option value="">— 用对话音色 —</option>
            <optgroup v-for="g in charVoiceGroups(c.voice)" :key="g.gender" :label="g.label">
              <option v-for="v in g.items" :key="v.value" :value="v.value">{{ v.label }}</option>
            </optgroup>
          </select>
          <button class="btn btn-ghost btn-xs" :disabled="!c.voice || charTesting === c.name"
                  @click="testCharVoice(c)" :title="'试听该角色音色'">
            {{ charTesting === c.name ? '…' : '▶ 试听' }}
          </button>
          <audio v-if="c._testData" :key="c._testRev"
                 :src="`data:audio/mpeg;base64,${c._testData}`"
                 autoplay
                 style="display:none" />
        </div>
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
          :src="`data:audio/${scene._format === 'wav' ? 'wav' : 'mpeg'};base64,${scene.data}`"
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

          <!-- Voice settings (engine-aware) -->
          <!-- IndexTTS 引擎专属：音色参考 / 情感参考 / 情感权重 -->
          <div class="dlg-settings" v-if="engineType === 'indextts'">
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
          <!-- 微软神经语音：每段按角色自动取音色，不需要音色参考 / 情感控制 -->
          <div class="dlg-settings" v-else-if="engineType === 'msedge'">
            <div class="dlg-setting-group" style="flex:1">
              <label class="dlg-label">微软音色</label>
              <span class="text-muted" style="font-size:12px">
                {{ msedgeVoiceForClip(clip) }}
                <span v-if="!charsVoiceMap[clip.character]" style="opacity:.7">
                  （未指定，使用默认。可在角色管理给「{{ clip.character || '该角色' }}」设置专属音色）
                </span>
              </span>
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
import { filterVoices, groupByGender } from '../../data/msedgeVoices'

// settings.audio_engine.msedge_available_voices；空 = 未测过，不过滤
const availableVoiceList = ref([])

// 顶部"叙述音色 / 对话音色"两个下拉用的扁平列表
// （连同当前已选 voice 一起允许，避免被过滤后下拉里看不到自己的项）
const MS_VOICES = computed(() => filterVoices(availableVoiceList.value, [
  msVoice?.value, msDialogueVoice?.value,
]))

// 角色音色矩阵下拉用的分组列表 helper
function charVoiceGroups(currentValue) {
  return groupByGender(filterVoices(availableVoiceList.value, [currentValue]))
}

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
const msVoice        = ref('zh-CN-XiaoxiaoNeural')  // 叙述音色
const msRate         = ref('+0%')
// 双音色：对话 / 心理活动用第二音色（默认男声沉稳；引号包围的内容会被识别）
const dualVoiceEnabled = ref(false)
const msDialogueVoice  = ref('zh-CN-YunxiNeural')
let   _stopReading   = false

// ── Current audio engine (for toolbar hint; non-reading modes use settings.audio_engine.engine_type) ──
const engineType     = ref('indextts')

// A1: 上次批量失败片段
const lastErrors      = ref({})
const lastErrorStage  = ref('')
const lastErrorCount  = computed(() => Object.keys(lastErrors.value || {}).length)

async function reloadLastErrors() {
  if (!props.projectId) return
  try {
    const r = await fetch(`http://localhost:18520/api/projects/${props.projectId}/last-run-errors`)
    if (!r.ok) return
    const d = await r.json()
    // audio tab 关心 audio stage（reading 模式的 ms-tts 失败本轮先不入库）
    if (d.stage === 'audio') {
      lastErrors.value     = d.errors || {}
      lastErrorStage.value = d.stage
    } else {
      lastErrors.value = {}; lastErrorStage.value = ''
    }
  } catch { lastErrors.value = {}; lastErrorStage.value = '' }
}

async function dismissLastErrors() {
  lastErrors.value = {}
  try { await fetch(`http://localhost:18520/api/projects/${props.projectId}/last-run-errors`, { method: 'DELETE' }) } catch {}
}

async function retryFailedBatch() {
  if (isReadingMode.value) {
    // 朗读模式：失败的 reading scenes 直接重跑 ms-tts
    const failedSceneIds = new Set(Object.keys(lastErrors.value).map(k => k.split(':')[0]))
    for (const s of readingScenes.value) {
      if (failedSceneIds.has(String(s.sceneId))) {
        try { await generateMsTts(s) } catch {}
      }
    }
  } else {
    // 非朗读：失败的 dialogue_id 重跑 regenClip
    const failedDlgIds = new Set(Object.keys(lastErrors.value).map(k => k.split(':')[1]))
    for (const clip of allClips.value) {
      if (failedDlgIds.has(clip.id)) {
        try { await regenClip(clip) } catch {}
      }
    }
  }
  await reloadLastErrors()
}
const engineLabel    = computed(() => ({
  indextts:  'IndexTTS-2.0',
  gptsovits: 'GPT-SoVITS',
  msedge:    '微软神经语音 (Edge TTS)',
  manual:    '手动导入',
}[engineType.value] || engineType.value))

// 角色 → msedge voice 的映射（来自 characters.json 的 voice 字段；msedge 引擎才有意义）
const charsVoiceMap  = ref({})
// 朗读模式双音色面板用：完整角色列表 [{name, role, voice, _testData?, _testRev?}]
const projectCharacters = ref([])
const charsSaving       = ref(false)
const charTesting       = ref('')
// 默认 voice（来自 settings；msedge 引擎下角色没填时退回到它）
const defaultMsVoice = computed(() => msVoice.value || 'zh-CN-XiaoxiaoNeural')

function msedgeVoiceForClip(clip) {
  return charsVoiceMap.value[clip?.character || ''] || defaultMsVoice.value
}

async function reloadCharacters() {
  try {
    const r = await fetch(`http://localhost:18520/api/projects/${props.projectId}/characters`)
    if (!r.ok) return
    const d = await r.json()
    projectCharacters.value = (d.characters || []).map(c => ({
      name: c.name || '', role: c.role || '', voice: c.voice || '',
      _raw: c, _testData: '', _testRev: 0,
    }))
    // 同步 voice 映射给生成逻辑用
    const map = {}
    for (const c of projectCharacters.value) {
      if (c.name && c.voice) map[c.name] = c.voice
    }
    charsVoiceMap.value = map
  } catch { /* ignore */ }
}

function onCharVoiceChanged(c) {
  // 即时更新内存中的映射，保存按钮按下时统一 PUT
  if (c.name) {
    if (c.voice) charsVoiceMap.value[c.name] = c.voice
    else delete charsVoiceMap.value[c.name]
  }
}

async function saveCharVoices() {
  charsSaving.value = true
  try {
    // 拉最新一次保留其它字段，把当前面板的 voice 覆盖回去
    const r = await fetch(`http://localhost:18520/api/projects/${props.projectId}/characters`)
    const d = r.ok ? await r.json() : { characters: [] }
    const byName = new Map((d.characters || []).map(c => [c.name, c]))
    for (const pc of projectCharacters.value) {
      const existing = byName.get(pc.name) || { name: pc.name, role: pc.role }
      existing.voice = pc.voice || ''
      byName.set(pc.name, existing)
    }
    const payload = { characters: Array.from(byName.values()) }
    const wr = await fetch(`http://localhost:18520/api/projects/${props.projectId}/characters`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    })
    if (!wr.ok) throw new Error(`HTTP ${wr.status}`)
  } catch (e) {
    alert('角色音色保存失败：' + e.message)
  } finally {
    charsSaving.value = false
  }
}

async function testCharVoice(c) {
  if (!c.voice) return
  charTesting.value = c.name
  c._testData = ''
  try {
    const res = await fetch('http://localhost:18520/api/audio-engine/ms-tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text:  `${c.name}，${c.role || '角色'}试音。这是一段测试音频。`,
        voice: c.voice,
        rate:  msRate.value || '+0%',
      }),
    })
    if (!res.ok) throw new Error(await res.text())
    const r = await res.json()
    c._testData = r.data
    c._testRev  = (c._testRev || 0) + 1
  } catch (e) {
    alert(`${c.name} 试听失败：${e.message}`)
  } finally {
    charTesting.value = ''
  }
}

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
        engineType.value = s.audio_engine?.engine_type || 'indextts'
        availableVoiceList.value = s.audio_engine?.msedge_available_voices || []
        // msedge engine: 顶部 ms 选择器只在 reading 模式可见；非 reading 模式
        // 走 batch-stream，后端按 settings.msedge_voice/rate 处理
        if (engineType.value === 'msedge') {
          msVoice.value = s.audio_engine?.msedge_voice || msVoice.value
          msRate.value  = s.audio_engine?.msedge_rate  || msRate.value
        }
      }
    } catch { /* ignore */ }

    // 加载 characters.json 拿到 name → voice 映射 + 完整角色列表（reading 双音色面板用）：
    //   - msedge 引擎：非朗读模式按角色配音色
    //   - 朗读模式：双音色开关下，按角色识别说话人 → 用角色 voice
    if (engineType.value === 'msedge' || isReadingMode.value) {
      await reloadCharacters()
    }

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
            _format:     saved.format      || 'mp3',  // 区分单/双音色（决定 <audio> mime）
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
  // A1: 顺便拉一下上次失败镜次
  await reloadLastErrors()
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
          format:      scene._format || 'mp3',   // 单音色 mp3 / 双音色 wav
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
    project_id: props.projectId,   // A1: 后端持久化失败镜次
    dialogues: allClips.value.map(c => ({
      scene_id:    String(c.sceneId),
      dialogue_id: c.id,
      text:        c.text,
      voice_ref:   c._voiceRef || null,
      emo_ref:     c._emoRef   || null,
      emo_weight:  c._emoWeight,
      lang:        'zh',
      // msedge 引擎下按角色填音色；其它引擎忽略此字段
      msedge_voice: engineType.value === 'msedge' ? msedgeVoiceForClip(c) : null,
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
    await reloadLastErrors()   // A1
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
    gen_count:  genCount.value,
    project_id: props.projectId,
    dialogues: [{
      scene_id:    String(clip.sceneId),
      dialogue_id: clip.id,
      text:        clip.text,
      voice_ref:   clip._voiceRef || null,
      emo_ref:     clip._emoRef   || null,
      emo_weight:  clip._emoWeight,
      lang:        'zh',
      msedge_voice: engineType.value === 'msedge' ? msedgeVoiceForClip(clip) : null,
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
// 把整段文本按 「」“”‘’ "" '' 引号分组为
// [{kind:'narration'|'dialogue', text, character?}]
//   - narration：引号外的叙述
//   - dialogue ：引号内的对话/心理活动；character 字段尽力识别"说话人"
//     识别策略：取该引号之前最近的 ~40 个字符窗口，扫描已知角色名做 substring 匹配，
//     命中最后一个 → 该说话者；没命中 → character=''（生成时按"对话音色"fallback）
function _segmentForDualVoice(text, knownNames = []) {
  const segs = []
  const re = /[「“‘"'](.+?)[」”’"']/gs
  let cursor = 0
  let m
  const findSpeaker = (window) => {
    if (!knownNames.length || !window) return ''
    let best = { name: '', pos: -1 }
    for (const n of knownNames) {
      if (!n) continue
      const i = window.lastIndexOf(n)
      if (i > best.pos) best = { name: n, pos: i }
    }
    return best.name
  }
  while ((m = re.exec(text)) !== null) {
    if (m.index > cursor) {
      const lead = text.slice(cursor, m.index).trim()
      if (lead) segs.push({ kind: 'narration', text: lead })
    }
    const inside = (m[1] || '').trim()
    if (inside) {
      // 取引号前最近 ~40 个字符 + 之前一段叙述里最后的角色名
      const window = text.slice(Math.max(0, m.index - 40), m.index)
      const speaker = findSpeaker(window)
      segs.push({ kind: 'dialogue', text: inside, character: speaker })
    }
    cursor = m.index + m[0].length
  }
  const tail = text.slice(cursor).trim()
  if (tail) segs.push({ kind: 'narration', text: tail })
  if (!segs.length) segs.push({ kind: 'narration', text: text.trim() })
  return segs
}

async function _msTtsClipWav(text, voice) {
  const res = await fetch('http://localhost:18520/api/audio-engine/ms-tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice, rate: msRate.value, format: 'wav' }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
  return res.json()  // {data: <b64 wav>, duration_ms, format:'wav'}
}

// A3: 朗读模式单条增量保存 —— 只写当前 scene，不全量重传 audio.json
async function _saveOneReadingScene(scene) {
  if (!props.projectId || !scene?.data) return
  try {
    await fetch(`http://localhost:18520/api/projects/${props.projectId}/audio/slot`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        key:   `__ms_reading__${scene.sceneId}`,
        entry: {
          data:        scene.data,
          duration_ms: scene.duration_ms,
          format:      scene._format || 'mp3',
        },
      }),
    })
  } catch (e) {
    console.warn('audio slot save failed', e)
  }
}

async function generateMsTts(scene) {
  scene.generating = true
  scene.data = null
  scene._rev = (scene._rev || 0) + 1
  try {
    // 双音色模式：按引号拆段 → 每段 ms-tts(WAV) → stitch-scene 合成
    // 对话段优先按"说话角色的 voice"取音色，没填则退回"对话音色"，再退回叙述音色
    if (dualVoiceEnabled.value) {
      const knownNames = Object.keys(charsVoiceMap.value || {})
      const segs = _segmentForDualVoice(scene.text, knownNames)
      const clips = []
      for (const seg of segs) {
        let v
        if (seg.kind === 'dialogue') {
          v = (seg.character && charsVoiceMap.value[seg.character])
            || msDialogueVoice.value
            || msVoice.value
        } else {
          v = msVoice.value
        }
        const r = await _msTtsClipWav(seg.text, v)
        clips.push({ data: r.data, pre_silence_ms: 0, post_silence_ms: 80 })
      }
      const stitched = await fetch('http://localhost:18520/api/audio-engine/stitch-scene', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clips }),
      })
      if (!stitched.ok) throw new Error(`stitch HTTP ${stitched.status}: ${await stitched.text()}`)
      const result = await stitched.json()
      scene.data        = result.data
      scene._rev        = (scene._rev || 0) + 1
      scene.duration_ms = result.duration_ms
      scene._format     = 'wav'
      emit('dirty')
      await _saveOneReadingScene(scene)   // A3: 单条增量写盘
      return
    }
    // 单音色（原行为）：直接 ms-tts MP3
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
    scene._format     = 'mp3'
    emit('dirty')
    await _saveOneReadingScene(scene)   // A3: 单条增量写盘
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
  const CONCURRENCY = 5
  const list = readingScenes.value
  let cursor = 0
  async function worker() {
    while (cursor < list.length) {
      if (_stopReading) break
      const scene = list[cursor++]
      await generateMsTts(scene)
      completedCount.value++
    }
  }
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, list.length) }, worker))
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
  window.addEventListener('lumi:save-project', _onGlobalSave)
})
function _onGlobalSave(e) { if (e?.detail?.projectId && e.detail.projectId !== props.projectId) return; saveAudio() }
onUnmounted(() => {
  window.removeEventListener('lumi:save-project', _onGlobalSave)
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
.char-voice-matrix .char-voice-rows {
  display:grid; grid-template-columns: minmax(120px, 1fr) minmax(180px, 1.4fr) auto;
  gap:6px 10px; align-items:center;
}
.char-voice-matrix .char-voice-row {
  display:contents;
}
.char-voice-matrix .char-voice-name { font-size:13px; padding:2px 0; }
.ms-voice-select    { min-width:180px; }
.reading-text {
  font-size:13px; color:var(--text-secondary); line-height:1.6;
  padding:6px 2px; border-top:1px dashed var(--border-color); margin-top:2px;
}
.reading-player    { height:36px; width:100%; margin-top:6px; }
.reading-generating { display:flex; align-items:center; gap:8px; padding:6px 2px; font-size:12px; }

.audio-tab { display:flex; flex-direction:column; height:100%; overflow:hidden; }
.last-errors-banner {
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:6px 16px; background:rgba(220,60,60,.08);
  border-bottom:1px solid rgba(220,60,60,.4); font-size:12px; flex-shrink:0;
}
.last-errors-banner .last-errors-detail { width:100%; }
.last-errors-banner ul { margin:4px 0 0 18px; padding:0; font-size:11px; line-height:1.5; }
.last-errors-banner code { background:rgba(255,255,255,.08); padding:1px 4px; border-radius:3px; }
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
