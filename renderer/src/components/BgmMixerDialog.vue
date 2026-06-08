<template>
  <Teleport to="body">
    <div class="bm-overlay" @click.self="$emit('close')">
      <div class="bm-modal card">
        <div class="bm-header">
          <h3>🎵 添加背景音乐</h3>
          <span class="text-muted" style="font-size:12px">
            源视频：<code>{{ sourceLabel }}</code>
          </span>
          <button class="btn btn-ghost btn-xs" style="margin-left:auto"
                  @click="$emit('close')">✕</button>
        </div>

        <!-- ── 1. Pick track ── -->
        <div class="bm-section">
          <div class="bm-section-title">
            <span>1. 选择音乐</span>
            <div class="bm-scope-toggle">
              <label :class="{ active: scope === 'project' }">
                <input type="radio" v-model="scope" value="project" />
                仅本项目
              </label>
              <label :class="{ active: scope === 'global' }">
                <input type="radio" v-model="scope" value="global" />
                全部
              </label>
            </div>
            <button class="btn btn-ghost btn-xs" @click="loadTracks">↻</button>
          </div>
          <div v-if="loading" class="bm-empty">加载中…</div>
          <div v-else-if="!tracks.length" class="bm-empty">
            尚无音乐 — 请先在主屏「🎵 音乐库」生成几首
          </div>
          <div v-else class="bm-track-list">
            <label v-for="t in tracks" :key="t.id" class="bm-track-row"
                   :class="{ selected: selectedTrackId === t.id }">
              <input type="radio" v-model="selectedTrackId" :value="t.id" />
              <div class="bm-track-info">
                <div class="bm-track-name">{{ t.name }}</div>
                <div class="bm-track-meta text-muted">
                  {{ formatSecs(t.duration_secs) }} · {{ t.bpm }} BPM · {{ t.language }} · seed {{ t.seed }}
                </div>
              </div>
              <audio :src="audioUrl(t.id)" controls preload="none" class="bm-audio"
                     @click.stop @play.stop />
            </label>
          </div>
        </div>

        <!-- ── 2. Mix params ── -->
        <div class="bm-section">
          <div class="bm-section-title">2. 混音参数</div>
          <div class="bm-param-grid">
            <div class="bm-param">
              <label>BGM 音量</label>
              <div class="bm-slider-row">
                <input type="range" min="-30" max="0" step="1"
                       v-model.number="form.bgm_volume_db" />
                <span class="bm-val">{{ form.bgm_volume_db }} dB</span>
              </div>
              <span class="text-muted bm-hint">越负越轻；推荐 -10 ~ -15</span>
            </div>
            <div class="bm-param">
              <label>原音量（旁白 / 对话）</label>
              <div class="bm-slider-row">
                <input type="range" min="-12" max="6" step="1"
                       v-model.number="form.original_volume_db" />
                <span class="bm-val">{{ form.original_volume_db }} dB</span>
              </div>
              <span class="text-muted bm-hint">0 = 原值；推荐 0 或略提</span>
            </div>
            <div class="bm-param">
              <label>淡入 (ms)</label>
              <input type="number" min="0" max="10000" step="100"
                     v-model.number="form.fade_in_ms" class="input bm-num" />
            </div>
            <div class="bm-param">
              <label>淡出 (ms)</label>
              <input type="number" min="0" max="10000" step="100"
                     v-model.number="form.fade_out_ms" class="input bm-num" />
            </div>
            <div class="bm-param bm-loop">
              <label>
                <input type="checkbox" v-model="form.loop_bgm" />
                BGM 短于视频时循环（推荐勾上）
              </label>
            </div>
          </div>
        </div>

        <!-- ── 3. Actions ── -->
        <div class="bm-section bm-actions">
          <div v-if="busy" class="bm-progress">
            <div class="spinner" /> ffmpeg 混音中…（视频流不重编码，通常 < 30s）
          </div>
          <div v-else-if="result" class="bm-result">
            ✓ 已生成 <code>{{ result.output_filename }}</code>
            <button v-if="electronAvailable"
                    class="btn btn-secondary btn-xs"
                    @click="openOutput">📂 打开</button>
          </div>
          <div v-else-if="error" class="bm-error">⚠ {{ error }}</div>
          <div class="bm-actions-buttons">
            <button class="btn btn-ghost" :disabled="busy" @click="$emit('close')">关闭</button>
            <button class="btn btn-primary"
                    :disabled="busy || !selectedTrackId"
                    @click="runMix">
              {{ busy ? '⏳ 处理中…' : '▶ 开始混音' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'

const API = 'http://127.0.0.1:18520/api'

const props = defineProps({
  projectId: { type: String, required: true },
  source:    { type: String, required: true },   // 'final_video' | 'final_video_subbed'
})
defineEmits(['close', 'mixed'])

const sourceLabel = computed(() =>
  props.source === 'final_video_subbed' ? 'final_video_subbed.mp4' : 'final_video.mp4'
)

const scope = ref('global')   // 默认全局，因为项目级可能没有任何 track
const tracks = ref([])
const selectedTrackId = ref(null)
const loading = ref(false)

const form = reactive({
  bgm_volume_db:      -12,
  original_volume_db: 0,
  fade_in_ms:         800,
  fade_out_ms:        1500,
  loop_bgm:           true,
})

const busy   = ref(false)
const result = ref(null)
const error  = ref('')

const electronAvailable = computed(() => !!window.electronAPI?.openPath)

async function loadTracks() {
  loading.value = true
  try {
    const q = scope.value === 'project'
      ? `?project_id=${encodeURIComponent(props.projectId)}`
      : ''
    const r = await fetch(`${API}/music/tracks${q}`)
    if (r.ok) {
      const d = await r.json()
      tracks.value = d.tracks || []
      // 自动选第一首
      if (!selectedTrackId.value && tracks.value.length) {
        selectedTrackId.value = tracks.value[0].id
      }
    }
  } catch (e) { console.warn(e) }
  loading.value = false
}

function audioUrl(id) { return `${API}/music/file/${id}` }

function formatSecs(s) {
  s = Number(s) || 0
  const m = Math.floor(s / 60), r = s - m * 60
  return `${m}:${String(r).padStart(2, '0')}`
}

async function runMix() {
  if (busy.value || !selectedTrackId.value) return
  error.value  = ''
  result.value = null
  busy.value   = true
  try {
    const r = await fetch(`${API}/video-engine/mix-bgm`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        project_id: props.projectId,
        source:     props.source,
        track_id:   selectedTrackId.value,
        ...form,
      }),
    })
    if (!r.ok) {
      let detail = 'HTTP ' + r.status
      try { const j = await r.json(); detail = j.detail || detail } catch {}
      throw new Error(detail)
    }
    result.value = await r.json()
    // 通知父组件刷新视频引用
    // emit 在 defineEmits 上下文内
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    busy.value = false
  }
}

function openOutput() {
  if (!result.value || !window.electronAPI?.openPath) return
  window.electronAPI.openPath(result.value.output_path)
}

// scope 变化时重新加载
import { watch } from 'vue'
watch(scope, () => loadTracks())

onMounted(loadTracks)
</script>

<style scoped>
.bm-overlay {
  position: fixed; inset: 0; z-index: 10001;
  background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center;
}
.bm-modal {
  width: min(720px, 96vw); max-height: calc(100vh - 40px);
  background: var(--bg-panel, #1e1e1e);
  border: 1px solid var(--border, #333); border-radius: 10px;
  display: flex; flex-direction: column; overflow: hidden;
}
.bm-header {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; border-bottom: 1px solid var(--border);
}
.bm-header h3 { margin: 0; font-size: 15px; }
.bm-header code { background: var(--bg-input); padding: 1px 6px; border-radius: 3px; font-size: 11px; }

.bm-section {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 8px;
}
.bm-section:last-child { border-bottom: none; }
.bm-section-title {
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; font-weight: 600; color: var(--text-muted);
}
.bm-scope-toggle {
  display: inline-flex; gap: 0; margin-left: auto;
  border: 1px solid var(--border); border-radius: 4px; overflow: hidden;
}
.bm-scope-toggle label {
  padding: 3px 8px; font-size: 11px; cursor: pointer;
  background: transparent; color: var(--text-muted);
}
.bm-scope-toggle label.active {
  background: var(--bg-input); color: var(--text); font-weight: 600;
}
.bm-scope-toggle input { display: none; }

.bm-empty { padding: 20px; text-align: center; color: var(--text-muted); font-size: 13px; }

.bm-track-list {
  display: flex; flex-direction: column; gap: 4px;
  max-height: 220px; overflow-y: auto;
}
.bm-track-row {
  display: grid; grid-template-columns: 20px 1fr 240px;
  gap: 10px; align-items: center; padding: 6px 8px;
  border: 1px solid var(--border); border-radius: 4px;
  background: var(--bg-input); cursor: pointer;
  transition: border-color .15s;
}
.bm-track-row:hover { border-color: var(--accent); }
.bm-track-row.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }
.bm-track-info { min-width: 0; }
.bm-track-name { font-size: 13px; font-weight: 600; }
.bm-track-meta { font-size: 10px; margin-top: 1px; }
.bm-audio { width: 100%; height: 28px; }

.bm-param-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px;
}
.bm-param { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.bm-param.bm-loop { grid-column: 1 / -1; }
.bm-param label { font-size: 11px; color: var(--text-muted); }
.bm-slider-row { display: flex; align-items: center; gap: 8px; }
.bm-slider-row input[type=range] { flex: 1; }
.bm-val { font-size: 11px; min-width: 50px; text-align: right; font-family: monospace; }
.bm-hint { font-size: 10px; }
.bm-num { width: 100px; height: 28px; font-size: 12px; }

.bm-actions {
  background: var(--bg-input);
}
.bm-actions-buttons {
  display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px;
}
.bm-progress { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-muted); }
.bm-result {
  color: #68d391; font-size: 13px;
  display: flex; align-items: center; gap: 10px;
}
.bm-result code { background: var(--bg-panel); padding: 1px 6px; border-radius: 3px; font-size: 12px; }
.bm-error {
  color: var(--danger, #fc8181); font-size: 12px;
  background: rgba(229,62,62,.08); padding: 6px 10px; border-radius: 4px;
}

.spinner { width: 16px; height: 16px; border: 2px solid var(--border);
            border-top-color: var(--accent); border-radius: 50%;
            animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
